"""Face clustering: group detected faces by identity and match against DB."""

import logging
from typing import Dict, List, Optional

import numpy as np

from app.database import get_all_persons
from app.services.search_service import SearchService

logger = logging.getLogger(__name__)

CLUSTER_THRESHOLD = 0.45  # Same as search threshold


def cluster_faces(
    faces: List[dict],
    threshold: float = CLUSTER_THRESHOLD,
) -> List[dict]:
    """Group faces into clusters (same person) and match against DB.

    Args:
        faces: list of {photo_path, embedding (np.ndarray 512-d),
               confidence, bbox}
        threshold: cosine similarity threshold for clustering

    Returns:
        list of cluster dicts:
        {
            "faces": [face_dict, ...],
            "best_face": face_dict,       # highest confidence
            "person_id": int | None,      # matched DB person id
            "person_name": str | None,    # matched DB person name
            "is_known": bool,
        }
    """
    if not faces:
        return []

    # Load existing persons from DB
    persons = get_all_persons()
    person_data = []
    for p in persons:
        if p.get("embeddings"):
            person_data.append({
                "id": p["id"],
                "name": p["name"],
                "embeddings": p["embeddings"],
            })

    # Step 1: match each face against DB persons
    assigned = [False] * len(faces)
    # Clusters keyed by person_id for known persons
    known_clusters: Dict[int, dict] = {}
    # Unknown clusters list
    unknown_clusters: List[dict] = []

    if person_data:
        face_embeddings = np.stack([f["embedding"] for f in faces])

        for pd in person_data:
            sims = SearchService.multi_embedding_similarity(
                pd["embeddings"], face_embeddings,
            )
            for i, sim in enumerate(sims):
                if assigned[i]:
                    continue
                if sim >= threshold:
                    assigned[i] = True
                    pid = pd["id"]
                    if pid not in known_clusters:
                        known_clusters[pid] = {
                            "faces": [],
                            "person_id": pid,
                            "person_name": pd["name"],
                            "is_known": True,
                        }
                    known_clusters[pid]["faces"].append(faces[i])

    # Step 2: cluster remaining faces (greedy)
    unassigned = [i for i, a in enumerate(assigned) if not a]

    cluster_assigned = [False] * len(unassigned)

    for idx_a, global_a in enumerate(unassigned):
        if cluster_assigned[idx_a]:
            continue

        cluster = {
            "faces": [faces[global_a]],
            "person_id": None,
            "person_name": None,
            "is_known": False,
        }
        cluster_assigned[idx_a] = True

        centroid = faces[global_a]["embedding"].copy()

        for idx_b in range(idx_a + 1, len(unassigned)):
            if cluster_assigned[idx_b]:
                continue
            global_b = unassigned[idx_b]
            emb_b = faces[global_b]["embedding"]

            sim = _cosine_sim(centroid, emb_b)
            if sim >= threshold:
                cluster["faces"].append(faces[global_b])
                cluster_assigned[idx_b] = True
                # Update centroid (running average)
                n = len(cluster["faces"])
                centroid = centroid * ((n - 1) / n) + emb_b * (1 / n)

        unknown_clusters.append(cluster)

    # Combine all clusters
    all_clusters = list(known_clusters.values()) + unknown_clusters

    # Set best_face for each cluster (highest confidence)
    for c in all_clusters:
        c["best_face"] = max(c["faces"], key=lambda f: f.get("confidence", 0))

    # Sort: known first (alphabetical), then unknown (by face count desc)
    known = sorted(
        [c for c in all_clusters if c["is_known"]],
        key=lambda c: c["person_name"] or "",
    )
    unknown = sorted(
        [c for c in all_clusters if not c["is_known"]],
        key=lambda c: len(c["faces"]),
        reverse=True,
    )

    return known + unknown


def select_diverse_embeddings(
    faces: List[dict], max_count: int = 5,
) -> List[dict]:
    """Select up to max_count diverse faces from a cluster.

    Uses greedy farthest-point selection to maximize diversity.
    """
    if len(faces) <= max_count:
        return list(faces)

    # Start with the best face (highest confidence)
    selected = [max(faces, key=lambda f: f.get("confidence", 0))]
    remaining = [f for f in faces if f is not selected[0]]

    while len(selected) < max_count and remaining:
        # For each remaining face, find min distance to any selected
        best_face = None
        best_min_dist = -1

        for face in remaining:
            min_sim = min(
                _cosine_sim(face["embedding"], s["embedding"])
                for s in selected
            )
            # We want the face most different from those already selected
            # (lowest similarity = most different)
            if best_face is None or min_sim < best_min_dist:
                best_min_dist = min_sim
                best_face = face

        selected.append(best_face)
        remaining = [f for f in remaining if f is not best_face]

    return selected


def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two vectors."""
    na = np.linalg.norm(a) + 1e-10
    nb = np.linalg.norm(b) + 1e-10
    return float(np.dot(a, b) / (na * nb))
