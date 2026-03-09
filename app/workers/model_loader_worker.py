"""Worker to load InsightFace model in background on app startup."""

from app.workers.base_worker import BaseWorker
from app.services.face_service import face_service


class ModelLoaderWorker(BaseWorker):
    """Loads the InsightFace model without blocking the UI."""

    def __init__(self, model_name: str = "buffalo_sc", parent=None):
        super().__init__(parent)
        self.model_name = model_name

    def run(self):
        try:
            self.status_message.emit("Loading face recognition model...")
            face_service.load_model(
                model_name=self.model_name,
                on_progress=lambda msg: self.status_message.emit(msg),
            )
            self.finished_with_result.emit({"success": True})
        except Exception as e:
            self.error.emit(f"Failed to load model: {str(e)}")
