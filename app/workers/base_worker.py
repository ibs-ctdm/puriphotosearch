"""Base QThread worker with standard signals."""

from PySide6.QtCore import QThread, Signal


class BaseWorker(QThread):
    """Base worker thread with common progress/error/finished signals."""

    progress = Signal(int, int, str)       # (current, total, message)
    error = Signal(str)                     # error message
    finished_with_result = Signal(object)   # result dict
    status_message = Signal(str)            # status text update

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def is_cancelled(self) -> bool:
        return self._cancelled
