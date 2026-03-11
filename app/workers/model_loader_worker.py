"""Worker to load InsightFace model in background on app startup."""

import time

from app.workers.base_worker import BaseWorker
from app.services.face_service import face_service

MAX_RETRIES = 3
RETRY_DELAY = 3  # seconds


class ModelLoaderWorker(BaseWorker):
    """Loads the InsightFace model without blocking the UI."""

    def __init__(self, model_name: str = "buffalo_sc", parent=None):
        super().__init__(parent)
        self.model_name = model_name

    def run(self):
        last_error = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                if attempt == 1:
                    self.status_message.emit("กำลังโหลดโมเดล...")
                else:
                    self.status_message.emit(
                        f"โหลดโมเดลอีกครั้ง ({attempt}/{MAX_RETRIES})..."
                    )
                face_service.load_model(
                    model_name=self.model_name,
                    on_progress=lambda msg: self.status_message.emit(msg),
                )
                self.finished_with_result.emit({"success": True})
                return
            except Exception as e:
                last_error = e
                if attempt < MAX_RETRIES:
                    self.status_message.emit(
                        f"โหลดไม่สำเร็จ รอลองใหม่ ({attempt}/{MAX_RETRIES})..."
                    )
                    time.sleep(RETRY_DELAY)

        self.error.emit(f"โหลดโมเดลไม่สำเร็จหลังลอง {MAX_RETRIES} ครั้ง: {last_error}")
