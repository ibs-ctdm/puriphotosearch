"""SQLite database initialization and CRUD helpers."""

import logging
import os
import sqlite3
import time
from typing import List, Optional

import numpy as np

from app.config import APP_SUPPORT_DIR, DB_PATH

logger = logging.getLogger(__name__)


def get_connection(timeout: float = 30.0) -> sqlite3.Connection:
    """Get a new SQLite connection with WAL mode and foreign keys.

    Uses a generous timeout to avoid 'database is locked' errors on Windows.
    """
    os.makedirs(APP_SUPPORT_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=timeout)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.row_factory = sqlite3.Row
    return conn


def _cleanup_stale_wal() -> None:
    """Remove stale WAL/SHM files that may linger after a crash on Windows."""
    for suffix in ("-wal", "-shm"):
        path = DB_PATH + suffix
        try:
            if os.path.exists(path):
                os.remove(path)
                logger.info("Removed stale file: %s", path)
        except OSError:
            pass


def init_database(max_retries: int = 3) -> None:
    """Create all tables if they don't exist.

    Retries on 'database is locked' to handle stale locks from prior crashes.
    """
    for attempt in range(1, max_retries + 1):
        try:
            _create_tables()
            return
        except sqlite3.OperationalError as exc:
            if "locked" in str(exc) and attempt < max_retries:
                logger.warning(
                    "Database locked on init (attempt %d/%d), retrying in %ds...",
                    attempt, max_retries, attempt,
                )
                _cleanup_stale_wal()
                time.sleep(attempt)
            else:
                raise


def _create_tables() -> None:
    """Internal: create all tables."""
    conn = get_connection()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS persons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_persons_name ON persons(name);

            CREATE TABLE IF NOT EXISTS person_embeddings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                person_id INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
                photo_path TEXT NOT NULL,
                embedding BLOB NOT NULL,
                thumbnail BLOB,
                is_primary INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_person_embeddings_person
                ON person_embeddings(person_id);

            CREATE TABLE IF NOT EXISTS event_folders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                folder_path TEXT NOT NULL UNIQUE,
                folder_name TEXT NOT NULL,
                photo_count INTEGER DEFAULT 0,
                face_count INTEGER DEFAULT 0,
                is_processed INTEGER DEFAULT 0,
                processed_at TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS photos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_folder_id INTEGER NOT NULL REFERENCES event_folders(id) ON DELETE CASCADE,
                file_path TEXT NOT NULL UNIQUE,
                filename TEXT NOT NULL,
                file_size INTEGER DEFAULT 0,
                width INTEGER DEFAULT 0,
                height INTEGER DEFAULT 0,
                face_count INTEGER DEFAULT 0,
                is_processed INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_photos_event
                ON photos(event_folder_id, is_processed);

            CREATE TABLE IF NOT EXISTS faces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                photo_id INTEGER NOT NULL REFERENCES photos(id) ON DELETE CASCADE,
                embedding BLOB NOT NULL,
                bbox_x1 REAL DEFAULT 0,
                bbox_y1 REAL DEFAULT 0,
                bbox_x2 REAL DEFAULT 0,
                bbox_y2 REAL DEFAULT 0,
                confidence REAL DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_faces_photo ON faces(photo_id);
        """)
        conn.commit()
    finally:
        conn.close()


# --- Person CRUD ---

def add_person(name: str, photo_path: str, embedding: np.ndarray, thumbnail: bytes) -> int:
    """Insert a new person with their first embedding (marked as primary). Returns person ID."""
    conn = get_connection()
    try:
        cursor = conn.execute("INSERT INTO persons (name) VALUES (?)", (name,))
        person_id = cursor.lastrowid
        conn.execute(
            "INSERT INTO person_embeddings "
            "(person_id, photo_path, embedding, thumbnail, is_primary) "
            "VALUES (?, ?, ?, ?, 1)",
            (person_id, photo_path, embedding.astype(np.float32).tobytes(), thumbnail),
        )
        conn.commit()
        return person_id
    finally:
        conn.close()


def add_person_embedding(
    person_id: int, photo_path: str, embedding: np.ndarray, thumbnail: bytes
) -> int:
    """Add an additional embedding to an existing person. Returns embedding row ID."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO person_embeddings "
            "(person_id, photo_path, embedding, thumbnail, is_primary) "
            "VALUES (?, ?, ?, ?, 0)",
            (person_id, photo_path, embedding.astype(np.float32).tobytes(), thumbnail),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def set_primary_embedding(person_id: int, embedding_id: int) -> None:
    """Set one embedding as primary for a person (unset all others)."""
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE person_embeddings SET is_primary = 0 WHERE person_id = ?",
            (person_id,),
        )
        conn.execute(
            "UPDATE person_embeddings SET is_primary = 1 WHERE id = ? AND person_id = ?",
            (embedding_id, person_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_all_persons() -> list:
    """Return all persons with list of embeddings as numpy arrays.
    Thumbnail comes from the primary embedding."""
    conn = get_connection()
    try:
        persons_rows = conn.execute(
            "SELECT id, name, created_at FROM persons ORDER BY name"
        ).fetchall()

        persons = []
        for prow in persons_rows:
            pid = prow["id"]
            emb_rows = conn.execute(
                "SELECT id, embedding, thumbnail, is_primary "
                "FROM person_embeddings WHERE person_id = ? "
                "ORDER BY is_primary DESC, id",
                (pid,),
            ).fetchall()

            embeddings = []
            thumbnail = None
            for er in emb_rows:
                embeddings.append(
                    np.frombuffer(er["embedding"], dtype=np.float32).copy()
                )
                if thumbnail is None:
                    thumbnail = er["thumbnail"]

            persons.append({
                "id": pid,
                "name": prow["name"],
                "embeddings": embeddings,
                "thumbnail": thumbnail,
                "embedding_count": len(embeddings),
                "created_at": prow["created_at"],
            })
        return persons
    finally:
        conn.close()


def get_person_embeddings(person_id: int) -> list:
    """Return all embeddings for a person."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, photo_path, embedding, thumbnail, is_primary, created_at "
            "FROM person_embeddings WHERE person_id = ? "
            "ORDER BY is_primary DESC, id",
            (person_id,),
        ).fetchall()
        return [{
            "id": row["id"],
            "photo_path": row["photo_path"],
            "embedding": np.frombuffer(row["embedding"], dtype=np.float32).copy(),
            "thumbnail": row["thumbnail"],
            "is_primary": bool(row["is_primary"]),
            "created_at": row["created_at"],
        } for row in rows]
    finally:
        conn.close()


def delete_person_embedding(embedding_id: int) -> None:
    """Delete a single embedding."""
    conn = get_connection()
    try:
        conn.execute("DELETE FROM person_embeddings WHERE id = ?", (embedding_id,))
        conn.commit()
    finally:
        conn.close()


def delete_person(person_id: int) -> None:
    conn = get_connection()
    try:
        conn.execute("DELETE FROM person_embeddings WHERE person_id = ?", (person_id,))
        conn.execute("DELETE FROM persons WHERE id = ?", (person_id,))
        conn.commit()
    finally:
        conn.close()


def update_person_name(person_id: int, new_name: str) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE persons SET name = ?, updated_at = datetime('now') WHERE id = ?",
            (new_name, person_id),
        )
        conn.commit()
    finally:
        conn.close()


# --- Event Folder helpers ---

def add_or_get_event_folder(folder_path: str) -> int:
    """Insert event folder if not exists, return its ID."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id FROM event_folders WHERE folder_path = ?", (folder_path,)
        ).fetchone()
        if row:
            return row["id"]
        folder_name = os.path.basename(folder_path)
        cursor = conn.execute(
            "INSERT INTO event_folders (folder_path, folder_name) VALUES (?, ?)",
            (folder_path, folder_name),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_all_event_folders() -> list:
    """Return all event folders."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, folder_path, folder_name, photo_count, face_count, "
            "is_processed, processed_at "
            "FROM event_folders ORDER BY folder_name"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_processed_event_folders() -> list:
    """Return only processed event folders."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, folder_path, folder_name, photo_count, face_count, processed_at "
            "FROM event_folders WHERE is_processed = 1 ORDER BY folder_name"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def reset_event_folder(event_folder_id: int) -> None:
    """Delete all photos/faces for an event folder and mark as unprocessed."""
    conn = get_connection()
    try:
        conn.execute(
            "DELETE FROM photos WHERE event_folder_id = ?", (event_folder_id,)
        )
        conn.execute(
            "UPDATE event_folders SET is_processed = 0, photo_count = 0, "
            "face_count = 0, processed_at = NULL WHERE id = ?",
            (event_folder_id,),
        )
        conn.commit()
    finally:
        conn.close()


def get_db_stats() -> dict:
    """Return database statistics."""
    conn = get_connection()
    try:
        person_count = conn.execute("SELECT COUNT(*) FROM persons").fetchone()[0]
        event_count = conn.execute("SELECT COUNT(*) FROM event_folders").fetchone()[0]
        photo_count = conn.execute("SELECT COUNT(*) FROM photos").fetchone()[0]
        face_count = conn.execute("SELECT COUNT(*) FROM faces").fetchone()[0]
        return {
            "persons": person_count,
            "events": event_count,
            "photos": photo_count,
            "faces": face_count,
        }
    finally:
        conn.close()
