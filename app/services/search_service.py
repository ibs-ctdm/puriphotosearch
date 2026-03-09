"""Vector similarity search using numpy cosine similarity."""

import logging
import sqlite3
from typing import List, Dict

import numpy as np

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 512


class SearchService:
    """In-memory cosine similarity search against face embeddings."""

    @staticmethod
    def batch_cosine_similarity(query: np.ndarray, embeddings: np.ndarray) -> np.ndarray:
        """Compute cosine similarity of query against a matrix of embeddings.

        Args:
            query: shape (512,)
            embeddings: shape (N, 512)

        Returns:
            similarities: shape (N,) with values in [-1, 1]
        """
        query_norm = query / (np.linalg.norm(query) + 1e-10)
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True) + 1e-10
        embeddings_norm = embeddings / norms
        return embeddings_norm @ query_norm

    @staticmethod
    def multi_embedding_similarity(
        person_embeddings: List[np.ndarray], face_embeddings: np.ndarray
    ) -> np.ndarray:
        """Compute max cosine similarity across multiple person embeddings.

        For each face, computes similarity against ALL person embeddings
        and takes the maximum. This improves matching when person has
        photos from different angles/lighting.

        Args:
            person_embeddings: list of M arrays, each shape (512,)
            face_embeddings: shape (N, 512) matrix of face embeddings

        Returns:
            max_similarities: shape (N,) — max similarity per face
        """
        if len(person_embeddings) == 1:
            return SearchService.batch_cosine_similarity(
                person_embeddings[0], face_embeddings
            )

        # Stack person embeddings: (M, 512)
        person_matrix = np.stack(person_embeddings)
        # Normalize person embeddings
        p_norms = np.linalg.norm(person_matrix, axis=1, keepdims=True) + 1e-10
        person_normed = person_matrix / p_norms
        # Normalize face embeddings
        f_norms = np.linalg.norm(face_embeddings, axis=1, keepdims=True) + 1e-10
        faces_normed = face_embeddings / f_norms
        # Compute all similarities: (N, M) = faces @ persons^T
        all_sims = faces_normed @ person_normed.T
        # Take max across person embeddings for each face
        return np.max(all_sims, axis=1)

    @staticmethod
    def search_person_in_event(
        db_path: str,
        person_embeddings: List[np.ndarray],
        event_folder_id: int,
        threshold: float = 0.45,
    ) -> List[dict]:
        """Find all photos in an event folder matching a person.

        Args:
            person_embeddings: list of numpy embeddings for the person

        Returns list of dicts sorted by similarity descending:
            [{photo_id, file_path, filename, similarity, face_id}, ...]
        """
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute("""
                SELECT f.id as face_id, f.embedding, f.confidence,
                       p.id as photo_id, p.file_path, p.filename
                FROM faces f
                JOIN photos p ON f.photo_id = p.id
                WHERE p.event_folder_id = ?
            """, (event_folder_id,)).fetchall()

            if not rows:
                return []

            face_ids = []
            photo_data = []
            embeddings_list = []

            for row in rows:
                emb = np.frombuffer(row["embedding"], dtype=np.float32).copy()
                if emb.shape[0] == EMBEDDING_DIM:
                    embeddings_list.append(emb)
                    face_ids.append(row["face_id"])
                    photo_data.append({
                        "photo_id": row["photo_id"],
                        "file_path": row["file_path"],
                        "filename": row["filename"],
                    })

            if not embeddings_list or not person_embeddings:
                return []

            embeddings_matrix = np.stack(embeddings_list)
            similarities = SearchService.multi_embedding_similarity(
                person_embeddings, embeddings_matrix
            )

            # Filter by threshold, deduplicate by photo (keep best face per photo)
            photo_best = {}
            for i, sim in enumerate(similarities):
                if sim >= threshold:
                    pid = photo_data[i]["photo_id"]
                    if pid not in photo_best or sim > photo_best[pid]["similarity"]:
                        photo_best[pid] = {
                            "photo_id": pid,
                            "file_path": photo_data[i]["file_path"],
                            "filename": photo_data[i]["filename"],
                            "similarity": float(sim),
                            "face_id": face_ids[i],
                        }

            return sorted(
                photo_best.values(),
                key=lambda x: x["similarity"],
                reverse=True,
            )

        finally:
            conn.close()

    @staticmethod
    def search_all_persons_in_event(
        db_path: str,
        persons: List[dict],
        event_folder_id: int,
        threshold: float = 0.45,
    ) -> Dict[int, dict]:
        """Search all persons against an event folder.

        Returns:
            {person_id: {"name": str, "matches": [...]}, ...}
        """
        results = {}
        for person in persons:
            matches = SearchService.search_person_in_event(
                db_path=db_path,
                person_embeddings=person["embeddings"],
                event_folder_id=event_folder_id,
                threshold=threshold,
            )
            if matches:
                results[person["id"]] = {
                    "name": person["name"],
                    "matches": matches,
                }
        return results
