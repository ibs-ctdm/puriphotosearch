"""Batch photo processing pipeline for face detection."""

import logging
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, List, Optional, Tuple

import cv2
import numpy as np

from app.services.face_service import face_service, _imread_safe

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif",
    # RAW camera formats
    ".arw", ".cr2", ".cr3", ".nef", ".nrw", ".orf", ".raf",
    ".rw2", ".pef", ".srw", ".dng", ".raw", ".3fr", ".erf",
}
MAX_WORKERS = 4
BATCH_SIZE = 20


class PhotoProcessor:
    """Process event folders: scan images, detect faces, store embeddings."""

    @staticmethod
    def scan_folder(folder_path: str) -> List[str]:
        """Find all image files in a folder (non-recursive).

        Scans only direct files in the given folder.
        Each subfolder is processed separately via the folder tree.
        Returns sorted list of absolute file paths.
        """
        folder = Path(folder_path)
        if not folder.is_dir():
            raise ValueError(f"Not a directory: {folder_path}")

        images = []
        for f in folder.iterdir():
            if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS:
                images.append(str(f.resolve()))

        images.sort()
        return images

    @staticmethod
    def _detect_single(image_path: str) -> Tuple[str, List[dict]]:
        """Detect faces in a single image (runs in thread pool)."""
        try:
            faces = face_service.detect_faces(image_path)
            return (image_path, faces)
        except Exception as e:
            logger.warning(f"Face detection failed for {image_path}: {e}")
            return (image_path, [])

    @staticmethod
    def process_event_folder(
        db_path: str,
        event_folder_id: int,
        image_paths: List[str],
        on_progress: Optional[Callable] = None,
        is_cancelled: Optional[Callable] = None,
    ) -> dict:
        """Process all images in an event folder.

        Args:
            db_path: Path to SQLite database
            event_folder_id: ID of the event_folder record
            image_paths: List of image file paths to process
            on_progress: Callback(current_count, total_count, current_filename)
            is_cancelled: Callback() -> bool
        """
        total = len(image_paths)
        photos_processed = 0
        faces_detected = 0
        errors = 0

        conn = sqlite3.connect(db_path)

        try:
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                futures = {}
                for path in image_paths:
                    future = executor.submit(PhotoProcessor._detect_single, path)
                    futures[future] = path

                batch_photos = []
                batch_faces = []

                for future in as_completed(futures):
                    if is_cancelled and is_cancelled():
                        executor.shutdown(wait=False, cancel_futures=True)
                        break

                    try:
                        image_path, faces = future.result()
                    except Exception as e:
                        logger.error(f"Future failed: {e}")
                        errors += 1
                        photos_processed += 1
                        if on_progress:
                            on_progress(photos_processed, total, "Error")
                        continue

                    filename = os.path.basename(image_path)

                    # Get image dimensions
                    try:
                        img = _imread_safe(image_path)
                        h, w = img.shape[:2] if img is not None else (0, 0)
                    except Exception:
                        h, w = 0, 0

                    file_size = os.path.getsize(image_path) if os.path.exists(image_path) else 0

                    batch_photos.append((
                        event_folder_id, image_path, filename,
                        file_size, w, h, len(faces), 1,
                    ))

                    for face in faces:
                        embedding_blob = face["embedding"].astype(np.float32).tobytes()
                        bbox = face["bbox"]
                        batch_faces.append((
                            image_path,
                            embedding_blob,
                            bbox[0], bbox[1], bbox[2], bbox[3],
                            face["confidence"],
                        ))

                    faces_detected += len(faces)
                    photos_processed += 1

                    if on_progress:
                        on_progress(photos_processed, total, filename)

                    if len(batch_photos) >= BATCH_SIZE:
                        PhotoProcessor._commit_batch(conn, batch_photos, batch_faces)
                        batch_photos.clear()
                        batch_faces.clear()

                # Final batch
                if batch_photos:
                    PhotoProcessor._commit_batch(conn, batch_photos, batch_faces)

            # Update event_folder counts
            conn.execute("""
                UPDATE event_folders
                SET photo_count = ?, face_count = ?, is_processed = 1,
                    processed_at = datetime('now')
                WHERE id = ?
            """, (photos_processed, faces_detected, event_folder_id))
            conn.commit()

        finally:
            conn.close()

        return {
            "photos_processed": photos_processed,
            "faces_detected": faces_detected,
            "errors": errors,
        }

    @staticmethod
    def _commit_batch(conn, batch_photos, batch_faces):
        """Insert a batch of photos and their faces into the database."""
        cursor = conn.cursor()

        for photo_data in batch_photos:
            cursor.execute("""
                INSERT OR IGNORE INTO photos
                (event_folder_id, file_path, filename, file_size, width, height, face_count, is_processed)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, photo_data)

        for face_data in batch_faces:
            image_path = face_data[0]
            row = cursor.execute(
                "SELECT id FROM photos WHERE file_path = ?", (image_path,)
            ).fetchone()
            if row:
                photo_id = row[0]
                cursor.execute("""
                    INSERT INTO faces
                    (photo_id, embedding, bbox_x1, bbox_y1, bbox_x2, bbox_y2, confidence)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (photo_id,) + face_data[1:])

        conn.commit()
