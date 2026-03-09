"""Single photo thumbnail widget with optional similarity score overlay."""

import os

from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QPixmap, QPainter, QFont, QColor
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class PhotoThumbnail(QWidget):
    """A thumbnail widget showing a photo with optional similarity score."""

    clicked = Signal(str)  # file_path

    def __init__(self, file_path: str, size: int = 150, similarity: float = None, parent=None):
        super().__init__(parent)
        self.file_path = file_path
        self.thumb_size = size
        self.similarity = similarity

        self.setFixedSize(size + 10, size + 30)
        self.setCursor(Qt.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)

        self.image_label = QLabel()
        self.image_label.setFixedSize(size, size)
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("border: 1px solid #ddd; border-radius: 4px;")
        layout.addWidget(self.image_label)

        # Filename label
        filename = os.path.basename(file_path)
        if len(filename) > 18:
            filename = filename[:15] + "..."
        info_text = filename
        if similarity is not None:
            info_text = f"{similarity:.2f} - {filename}"

        self.info_label = QLabel(info_text)
        self.info_label.setAlignment(Qt.AlignCenter)
        self.info_label.setStyleSheet("font-size: 10px; color: #666;")
        layout.addWidget(self.info_label)

        self._load_thumbnail()

    def _load_thumbnail(self):
        if not os.path.exists(self.file_path):
            self.image_label.setText("Not found")
            return

        pixmap = QPixmap(self.file_path)
        if pixmap.isNull():
            self.image_label.setText("Error")
            return

        scaled = pixmap.scaled(
            QSize(self.thumb_size, self.thumb_size),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )

        # Draw similarity badge if present
        if self.similarity is not None:
            painter = QPainter(scaled)
            painter.setRenderHint(QPainter.Antialiasing)

            # Badge background
            badge_color = QColor(76, 175, 80) if self.similarity >= 0.5 else QColor(255, 152, 0)
            painter.setBrush(badge_color)
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(4, 4, 45, 20, 4, 4)

            # Badge text
            painter.setPen(QColor(255, 255, 255))
            font = QFont()
            font.setPixelSize(11)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(8, 18, f"{self.similarity:.2f}")
            painter.end()

        self.image_label.setPixmap(scaled)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.file_path)
