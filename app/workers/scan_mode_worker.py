"""Workers for the Scan-first-Name-later mode."""

import logging
import os
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import cv2
import numpy as np

from app.workers.base_worker import BaseWorker
from app.services.face_service import face_service, _imread_safe
from app.services.face_cluster_service import cluster_faces, select_diverse_embeddings
from app.services.file_organizer import FileOrganizer
from app.services.photo_processor import IMAGE_EXTENSIONS
from app.database import add_person, add_person_embedding

logger = logging.getLogger(__name__)

MAX_WORKERS = 4


def _make_face_thumbnail(image_path: str, bbox, size: int = 150) -> bytes:
    """Crop face from image using bbox and return JPEG thumbnail bytes."""
    img = _imread_safe(image_path)
    if img is None:
        raise ValueError(f"Cannot read: {image_path}")

    h, w = img.shape[:2]
    x1, y1, x2, y2 = [int(v) for v in bbox]

    # Expand to square with padding
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
    side = int(max(x2 - x1, y2 - y1) * 1.35)
    half = side // 2
    sx1 = max(cx - half, 0)
    sy1 = max(cy - half, 0)
    sx2 = min(cx + half, w)
    sy2 = min(cy + half, h)

    crop = img[sy1:sy2, sx1:sx2]
    if crop.size == 0:
        crop = img
    thumb = cv2.resize(crop, (size, size), interpolation=cv2.INTER_AREA)
    _, buf = cv2.imencode(".jpg", thumb, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return buf.tobytes()


class ScanClusterWorker(BaseWorker):
    """Scan all photos in selected folders, detect faces, and cluster them."""

    def __init__(self, folder_paths: list, threshold: float = 0.45, parent=None):
        super().__init__(parent)
        self.folder_paths = folder_paths
        self.threshold = threshold

    def run(self):
        try:
            self.status_message.emit("กำลังสแกนรูปภาพ...")

            # Collect all images from all selected folders (non-recursive per folder)
            image_paths = []
            for folder in self.folder_paths:
                folder_p = Path(folder)
                for f in folder_p.iterdir():
                    if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS:
                        image_paths.append(str(f.resolve()))
            image_paths.sort()

            if not image_paths:
                self.error.emit("ไม่พบรูปภาพในโฟลเดอร์ที่เลือก")
                return

            total = len(image_paths)
            self.status_message.emit(f"พบ {total:,} รูปภาพ กำลังตรวจจับใบหน้า...")

            # Detect faces in parallel
            all_faces = []
            done = 0

            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                futures = {
                    executor.submit(self._detect, p): p for p in image_paths
                }
                for future in as_completed(futures):
                    if self.is_cancelled():
                        executor.shutdown(wait=False, cancel_futures=True)
                        return

                    done += 1
                    path = futures[future]
                    try:
                        faces = future.result()
                        all_faces.extend(faces)
                    except Exception as e:
                        logger.warning(f"Detection failed for {path}: {e}")

                    self.progress.emit(
                        done, total,
                        f"ตรวจจับใบหน้า {done:,}/{total:,}",
                    )

            if not all_faces:
                self.error.emit("ไม่พบใบหน้าในรูปภาพ")
                return

            self.status_message.emit(
                f"พบ {len(all_faces):,} ใบหน้า กำลังจัดกลุ่ม..."
            )

            # Indeterminate progress during clustering
            self.progress.emit(0, 0, "กำลังจัดกลุ่มใบหน้า...")

            # Cluster
            clusters = cluster_faces(all_faces, self.threshold)

            # Generate thumbnails for best face in each cluster (with progress)
            self.status_message.emit(
                f"พบ {len(clusters):,} กลุ่ม กำลังสร้างภาพตัวอย่าง..."
            )
            for i, c in enumerate(clusters):
                bf = c["best_face"]
                try:
                    c["thumbnail"] = _make_face_thumbnail(
                        bf["photo_path"], bf["bbox"],
                    )
                except Exception:
                    c["thumbnail"] = None
                self.progress.emit(
                    i + 1, len(clusters),
                    f"สร้างภาพตัวอย่าง {i + 1:,}/{len(clusters):,}",
                )

            self.finished_with_result.emit({
                "clusters": clusters,
                "total_photos": total,
                "total_faces": len(all_faces),
            })

        except Exception as e:
            self.error.emit(f"เกิดข้อผิดพลาด: {str(e)}")

    @staticmethod
    def _detect(image_path: str) -> list:
        """Detect faces in a single image."""
        results = face_service.detect_faces(image_path)
        return [
            {
                "photo_path": image_path,
                "embedding": r["embedding"],
                "confidence": r["confidence"],
                "bbox": r["bbox"],
            }
            for r in results
        ]


class ExecuteScanWorker(BaseWorker):
    """Execute: merge same-name clusters, optionally copy photos, add new persons to DB."""

    def __init__(self, named_clusters: list, skip_file_organize: bool = False,
                 custom_dest_dir: str = None, parent=None):
        super().__init__(parent)
        self.named_clusters = named_clusters  # [{name, cluster}, ...]
        self.skip_file_organize = skip_file_organize
        self.custom_dest_dir = custom_dest_dir

    def run(self):
        try:
            # Group clusters by name (merge same-name clusters)
            grouped = defaultdict(list)
            for item in self.named_clusters:
                grouped[item["name"]].append(item["cluster"])

            total = len(grouped)
            persons_added = 0
            photos_copied = 0
            person_details = []  # per-person summary

            for i, (name, clusters) in enumerate(grouped.items()):
                if self.is_cancelled():
                    break

                self.status_message.emit(
                    f"กำลังดำเนินการ {i + 1}/{total}: {name}..."
                )

                # Merge all faces from clusters with the same name
                all_faces = []
                is_known = False
                person_id = None
                for cluster in clusters:
                    all_faces.extend(cluster["faces"])
                    if cluster["is_known"]:
                        is_known = True
                        person_id = cluster.get("person_id")

                # 1) Copy photos to person folders (grouped by parent dir)
                copied_count = 0
                org_result = {}
                if not self.skip_file_organize:
                    photo_paths = list({f["photo_path"] for f in all_faces})
                    org_result = FileOrganizer.organize_single_person(
                        event_folder_path="",
                        person_name=name,
                        matched_photo_paths=photo_paths,
                        custom_dest_dir=self.custom_dest_dir,
                        is_cancelled=self.is_cancelled,
                    )
                    copied_count = org_result.get("copied", 0)
                photos_copied += copied_count

                # 2) Add to DB if new person (not already in DB)
                if not is_known:
                    diverse = select_diverse_embeddings(
                        all_faces, max_count=6,
                    )

                    # Add first as primary
                    first = diverse[0]
                    try:
                        thumb = _make_face_thumbnail(
                            first["photo_path"], first["bbox"],
                        )
                    except Exception:
                        thumb = b""

                    person_id = add_person(
                        name=name,
                        photo_path=first["photo_path"],
                        embedding=first["embedding"],
                        thumbnail=thumb,
                    )
                    persons_added += 1

                    # Add remaining as extra embeddings
                    for face in diverse[1:]:
                        try:
                            thumb = _make_face_thumbnail(
                                face["photo_path"], face["bbox"],
                            )
                        except Exception:
                            thumb = b""

                        add_person_embedding(
                            person_id=person_id,
                            photo_path=face["photo_path"],
                            embedding=face["embedding"],
                            thumbnail=thumb,
                        )

                person_details.append({
                    "name": name,
                    "copied": copied_count,
                    "output_folders": org_result.get("output_folders", []),
                    "is_new": not is_known,
                })

                self.progress.emit(i + 1, total, name)

            self.finished_with_result.emit({
                "persons_added": persons_added,
                "photos_copied": photos_copied,
                "total_processed": total,
                "person_details": person_details,
            })

        except Exception as e:
            self.error.emit(f"เกิดข้อผิดพลาด: {str(e)}")
