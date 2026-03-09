"""Individual person card widget for the person manager grid."""

from PySide6.QtCore import Signal, Qt, QSize
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
)


class PersonCard(QWidget):
    """Card widget showing a person's thumbnail, name, and action buttons."""

    edit_clicked = Signal(int, str)           # (person_id, current_name)
    delete_clicked = Signal(int, str)         # (person_id, name)
    add_photo_clicked = Signal(int, str)      # (person_id, name)
    manage_photos_clicked = Signal(int, str)  # (person_id, name)

    def __init__(self, person_id: int, name: str, thumbnail: bytes = None,
                 embedding_count: int = 1, parent=None):
        super().__init__(parent)
        self.person_id = person_id
        self.person_name = name

        self.setFixedSize(160, 240)
        self.setStyleSheet("""
            PersonCard {
                border: 1px solid #ddd;
                border-radius: 8px;
                background: white;
            }
            PersonCard:hover {
                border-color: #4CAF50;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 6)
        layout.setSpacing(4)

        # Thumbnail
        self.photo_label = QLabel()
        self.photo_label.setFixedSize(120, 120)
        self.photo_label.setAlignment(Qt.AlignCenter)
        self.photo_label.setStyleSheet("border: 1px solid #eee; border-radius: 4px;")
        layout.addWidget(self.photo_label, alignment=Qt.AlignCenter)

        if thumbnail:
            self._set_thumbnail(thumbnail)
        else:
            self.photo_label.setText("ไม่มีรูป")

        # Name
        self.name_label = QLabel(name)
        self.name_label.setAlignment(Qt.AlignCenter)
        self.name_label.setStyleSheet("font-weight: bold; font-size: 12px; margin-top: 4px;")
        self.name_label.setWordWrap(True)
        layout.addWidget(self.name_label)

        # Embedding count (clickable to manage)
        count_text = f"({embedding_count} รูปอ้างอิง)"
        self.count_btn = QPushButton(count_text)
        self.count_btn.setFlat(True)
        self.count_btn.setCursor(Qt.PointingHandCursor)
        self.count_btn.setStyleSheet(
            "color: #1976D2; font-size: 10px; text-decoration: underline; border: none;"
        )
        self.count_btn.clicked.connect(
            lambda: self.manage_photos_clicked.emit(self.person_id, self.person_name)
        )
        layout.addWidget(self.count_btn)

        # Buttons row 1: edit + delete
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(4)

        edit_btn = QPushButton("แก้ไข")
        edit_btn.setFixedHeight(24)
        edit_btn.setStyleSheet("font-size: 11px;")
        edit_btn.clicked.connect(lambda: self.edit_clicked.emit(self.person_id, self.person_name))

        delete_btn = QPushButton("ลบ")
        delete_btn.setFixedHeight(24)
        delete_btn.setStyleSheet("font-size: 11px; color: #d32f2f;")
        delete_btn.clicked.connect(lambda: self.delete_clicked.emit(self.person_id, self.person_name))

        btn_layout.addWidget(edit_btn)
        btn_layout.addWidget(delete_btn)
        layout.addLayout(btn_layout)

        # Button row 2: add photo
        add_photo_btn = QPushButton("+ เพิ่มรูป")
        add_photo_btn.setFixedHeight(24)
        add_photo_btn.setStyleSheet(
            "font-size: 11px; color: #1976D2; font-weight: bold;"
        )
        add_photo_btn.clicked.connect(
            lambda: self.add_photo_clicked.emit(self.person_id, self.person_name)
        )
        layout.addWidget(add_photo_btn)

    def _set_thumbnail(self, data: bytes):
        image = QImage.fromData(data)
        if not image.isNull():
            pixmap = QPixmap.fromImage(image).scaled(
                QSize(120, 120), Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            self.photo_label.setPixmap(pixmap)

    def update_name(self, new_name: str):
        self.person_name = new_name
        self.name_label.setText(new_name)
