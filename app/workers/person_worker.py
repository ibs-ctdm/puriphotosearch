"""Worker for extracting face embedding from a person's reference photo."""

import cv2
import numpy as np
from PySide6.QtCore import Signal

from app.workers.base_worker import BaseWorker
from app.services.face_service import face_service, _imread_safe
from app.database import add_person, add_person_embedding


def _make_thumbnail(photo_path: str) -> bytes:
    """Generate a 150x150 center-crop JPEG thumbnail from a photo."""
    img = _imread_safe(photo_path)
    if img is None:
        raise ValueError(f"Cannot read image: {photo_path}")
    h, w = img.shape[:2]
    size = min(h, w)
    y_start = (h - size) // 2
    x_start = (w - size) // 2
    crop = img[y_start:y_start + size, x_start:x_start + size]
    thumb = cv2.resize(crop, (150, 150), interpolation=cv2.INTER_AREA)
    _, thumb_bytes = cv2.imencode(".jpg", thumb, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return thumb_bytes.tobytes()


class AddPersonWorker(BaseWorker):
    """Extract embedding from photo and add person to database."""

    person_added = Signal(int, str)  # (person_id, person_name)

    def __init__(self, name: str, photo_path: str, embedding=None, parent=None):
        super().__init__(parent)
        self.name = name
        self.photo_path = photo_path
        self.embedding = embedding  # optional pre-computed embedding

    def run(self):
        try:
            self.status_message.emit("กำลังตรวจจับใบหน้า...")

            if self.embedding is not None:
                embedding = self.embedding
            else:
                embedding = face_service.get_best_embedding(self.photo_path)
            thumbnail = _make_thumbnail(self.photo_path)

            person_id = add_person(
                name=self.name,
                photo_path=self.photo_path,
                embedding=embedding,
                thumbnail=thumbnail,
            )

            self.person_added.emit(person_id, self.name)
            self.finished_with_result.emit({
                "person_id": person_id,
                "name": self.name,
            })

        except ValueError as e:
            self.error.emit(str(e))
        except Exception as e:
            self.error.emit(f"ไม่สามารถเพิ่มบุคคลได้: {str(e)}")


class AddEmbeddingWorker(BaseWorker):
    """Extract embedding from an additional photo and add to existing person."""

    def __init__(self, person_id: int, person_name: str, photo_path: str, embedding=None, parent=None):
        super().__init__(parent)
        self.person_id = person_id
        self.person_name = person_name
        self.photo_path = photo_path
        self.embedding = embedding  # optional pre-computed embedding

    def run(self):
        try:
            self.status_message.emit(
                f"กำลังตรวจจับใบหน้าเพิ่มเติมสำหรับ {self.person_name}..."
            )

            if self.embedding is not None:
                embedding = self.embedding
            else:
                embedding = face_service.get_best_embedding(self.photo_path)
            thumbnail = _make_thumbnail(self.photo_path)

            emb_id = add_person_embedding(
                person_id=self.person_id,
                photo_path=self.photo_path,
                embedding=embedding,
                thumbnail=thumbnail,
            )

            self.finished_with_result.emit({
                "person_id": self.person_id,
                "person_name": self.person_name,
                "embedding_id": emb_id,
            })

        except ValueError as e:
            self.error.emit(str(e))
        except Exception as e:
            self.error.emit(f"ไม่สามารถเพิ่มรูปได้: {str(e)}")
