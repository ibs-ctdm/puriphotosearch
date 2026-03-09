"""Worker for batch face detection on event folders."""

from app.workers.base_worker import BaseWorker
from app.services.photo_processor import PhotoProcessor
from app.config import DB_PATH


class ProcessWorker(BaseWorker):
    """Process all photos in an event folder on a background thread."""

    def __init__(self, event_folder_id: int, image_paths: list, parent=None):
        super().__init__(parent)
        self.event_folder_id = event_folder_id
        self.image_paths = image_paths

    def run(self):
        try:
            result = PhotoProcessor.process_event_folder(
                db_path=DB_PATH,
                event_folder_id=self.event_folder_id,
                image_paths=self.image_paths,
                on_progress=lambda c, t, f: self.progress.emit(c, t, f"Processing: {f}"),
                is_cancelled=self.is_cancelled,
            )
            self.finished_with_result.emit(result)
        except Exception as e:
            self.error.emit(str(e))
