"""Modal progress dialog with cancel support."""

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QProgressBar, QPushButton,
)


class ProgressDialog(QDialog):
    """Modal progress dialog with cancel support."""

    cancelled = Signal()

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(450)
        self.setModal(True)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowCloseButtonHint)

        layout = QVBoxLayout(self)

        self.status_label = QLabel("กำลังเริ่มต้น...")
        self.status_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #1D1D1F;")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setTextVisible(True)
        self.detail_label = QLabel("")
        self.detail_label.setStyleSheet("color: #86868B;")
        self.cancel_button = QPushButton("ยกเลิก")

        layout.addWidget(self.status_label)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.detail_label)
        layout.addSpacing(10)
        layout.addWidget(self.cancel_button, alignment=Qt.AlignCenter)

        self.cancel_button.clicked.connect(self._on_cancel)

    def update_progress(self, current: int, total: int, message: str = ""):
        percent = int(current / max(total, 1) * 100)
        self.progress_bar.setValue(percent)
        self.status_label.setText(f"{current} / {total}")
        if message:
            self.detail_label.setText(message)

    def set_status(self, message: str):
        self.detail_label.setText(message)

    def _on_cancel(self):
        self.cancel_button.setEnabled(False)
        self.cancel_button.setText("กำลังยกเลิก...")
        self.cancelled.emit()
