"""Panel 2: Person database CRUD management."""

import os

from PySide6.QtCore import Signal, Qt, QSize
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QInputDialog, QMessageBox, QScrollArea,
    QGridLayout, QGroupBox, QDialog, QRadioButton, QButtonGroup,
)

from app.config import AppConfig
from app.database import (
    get_all_persons, delete_person, update_person_name,
    get_person_embeddings, delete_person_embedding, set_primary_embedding,
)
from app.workers.person_worker import AddPersonWorker, AddEmbeddingWorker
from app.ui.widgets.person_card import PersonCard
from app.ui.widgets.progress_dialog import ProgressDialog
from app.ui.widgets.photo_browser_dialog import PhotoBrowserDialog
from app.ui.widgets.face_crop_dialog import FaceCropDialog
from app.ui.widgets.scan_mode_dialog import ScanModeDialog


class PersonManager(QWidget):
    """Panel for managing the person database (add, edit, delete persons)."""

    person_changed = Signal()  # emitted when persons are added/edited/deleted

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self._setup_ui()
        self.refresh_persons()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 15, 10, 10)
        layout.setSpacing(15)

        # Header
        header_layout = QHBoxLayout()
        title = QLabel("ฐานข้อมูลบุคคล")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #1D1D1F;")
        header_layout.addWidget(title)

        self.count_label = QLabel("")
        self.count_label.setStyleSheet("color: #86868B; font-size: 14px;")
        header_layout.addWidget(self.count_label)
        header_layout.addStretch()

        self.scan_btn = QPushButton("โหมดสแกนและตั้งชื่อ")
        self.scan_btn.setStyleSheet("""
            QPushButton {
                background: #5BA4CF; color: white;
                padding: 8px 18px; border-radius: 8px;
                font-weight: bold; font-size: 13px; border: none;
            }
            QPushButton:hover { background: #4A8CB5; }
        """)
        self.scan_btn.clicked.connect(self._open_scan_mode)
        header_layout.addWidget(self.scan_btn)

        self.add_btn = QPushButton("+ เพิ่มบุคคล")
        self.add_btn.setStyleSheet("""
            QPushButton {
                background: #F5811F; color: white;
                padding: 8px 18px; border-radius: 8px;
                font-weight: bold; font-size: 13px; border: none;
            }
            QPushButton:hover { background: #E0710A; }
        """)
        self.add_btn.clicked.connect(self._add_person)
        header_layout.addWidget(self.add_btn)

        layout.addLayout(header_layout)

        desc = QLabel("อัปโหลดรูปใบหน้าที่ชัดเจนของแต่ละบุคคลที่ต้องการค้นหา")
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #86868B;")
        layout.addWidget(desc)

        # Scroll area for person cards
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.grid_container = QWidget()
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setSpacing(10)
        self.grid_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        scroll.setWidget(self.grid_container)
        layout.addWidget(scroll)

    def refresh_persons(self):
        """Reload all persons from database and rebuild the grid."""
        # Clear grid
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        persons = get_all_persons()
        self.count_label.setText(f"({len(persons)} คน)")

        cols = 4
        for i, person in enumerate(persons):
            card = PersonCard(
                person_id=person["id"],
                name=person["name"],
                thumbnail=person.get("thumbnail"),
                embedding_count=person.get("embedding_count", 1),
            )
            card.edit_clicked.connect(self._edit_person)
            card.delete_clicked.connect(self._delete_person)
            card.add_photo_clicked.connect(self._add_photo_to_person)
            card.manage_photos_clicked.connect(self._manage_photos)
            self.grid_layout.addWidget(card, i // cols, i % cols)

    def _browse_and_crop(self) -> tuple:
        """Open photo browser then face crop dialog.

        Returns (cropped_path, embedding) or (None, None).
        """
        config = AppConfig.load()
        root = config.main_photos_folder or os.path.expanduser("~")

        browser = PhotoBrowserDialog(root, self)
        if browser.exec() != QDialog.Accepted:
            return None, None
        photo_path = browser.get_selected_path()
        if not photo_path:
            return None, None

        crop_dialog = FaceCropDialog(photo_path, self)
        if crop_dialog.exec() != QDialog.Accepted:
            return None, None
        cropped = crop_dialog.get_cropped_path() or photo_path
        embedding = crop_dialog.get_selected_embedding()
        return cropped, embedding

    def _add_person(self):
        file_path, embedding = self._browse_and_crop()
        if not file_path:
            return

        name, ok = QInputDialog.getText(
            self, "ชื่อบุคคล",
            "กรอกชื่อบุคคล:",
        )
        if not ok or not name.strip():
            return

        name = name.strip()

        # Show progress
        self._progress = ProgressDialog("กำลังเพิ่มบุคคล", self)
        self._progress.set_status(f"กำลังประมวลผลใบหน้าของ {name}...")

        self._worker = AddPersonWorker(name, file_path, embedding=embedding)
        self._worker.status_message.connect(self._progress.set_status)
        self._worker.finished_with_result.connect(self._on_person_added)
        self._worker.error.connect(self._on_add_error)
        self._progress.cancelled.connect(self._worker.cancel)
        self._worker.start()
        self._progress.show()

    def _on_person_added(self, result):
        if hasattr(self, '_progress'):
            self._progress.close()
        self.refresh_persons()
        self.person_changed.emit()
        QMessageBox.information(
            self, "สำเร็จ",
            f"เพิ่มบุคคลแล้ว: {result['name']}",
        )

    def _on_add_error(self, message):
        if hasattr(self, '_progress'):
            self._progress.close()
        QMessageBox.warning(self, "ข้อผิดพลาด", message)

    def _open_scan_mode(self):
        dialog = ScanModeDialog(self)
        dialog.person_changed.connect(self._on_scan_persons_added)
        dialog.exec()

    def _on_scan_persons_added(self):
        self.refresh_persons()
        self.person_changed.emit()

    def _edit_person(self, person_id: int, current_name: str):
        new_name, ok = QInputDialog.getText(
            self, "แก้ไขชื่อบุคคล",
            "กรอกชื่อใหม่:",
            text=current_name,
        )
        if ok and new_name.strip() and new_name.strip() != current_name:
            update_person_name(person_id, new_name.strip())
            self.refresh_persons()
            self.person_changed.emit()

    def _delete_person(self, person_id: int, name: str):
        reply = QMessageBox.question(
            self, "ยืนยันการลบ",
            f"คุณแน่ใจหรือไม่ว่าต้องการลบ '{name}'?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            delete_person(person_id)
            self.refresh_persons()
            self.person_changed.emit()

    def _add_photo_to_person(self, person_id: int, name: str):
        file_path, embedding = self._browse_and_crop()
        if not file_path:
            return

        self._progress = ProgressDialog("กำลังเพิ่มรูปอ้างอิง", self)
        self._progress.set_status(f"กำลังประมวลผลใบหน้าเพิ่มเติมสำหรับ {name}...")

        self._worker = AddEmbeddingWorker(person_id, name, file_path, embedding=embedding)
        self._worker.status_message.connect(self._progress.set_status)
        self._worker.finished_with_result.connect(self._on_embedding_added)
        self._worker.error.connect(self._on_add_error)
        self._progress.cancelled.connect(self._worker.cancel)
        self._worker.start()
        self._progress.show()

    def _on_embedding_added(self, result):
        if hasattr(self, '_progress'):
            self._progress.close()
        self.refresh_persons()
        self.person_changed.emit()
        QMessageBox.information(
            self, "สำเร็จ",
            f"เพิ่มรูปอ้างอิงสำหรับ {result['person_name']} แล้ว",
        )

    def _manage_photos(self, person_id: int, name: str):
        dialog = EmbeddingsDialog(person_id, name, self)
        if dialog.exec():
            self.refresh_persons()
            self.person_changed.emit()


class EmbeddingsDialog(QDialog):
    """Dialog to view, delete, and set primary reference photo for a person."""

    def __init__(self, person_id: int, person_name: str, parent=None):
        super().__init__(parent)
        self.person_id = person_id
        self.person_name = person_name
        self._changed = False

        self.setWindowTitle(f"รูปอ้างอิงของ {person_name}")
        self.setMinimumSize(500, 400)

        layout = QVBoxLayout(self)

        header = QLabel(f"รูปอ้างอิงทั้งหมดของ {person_name}")
        header.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(header)

        desc = QLabel(
            "เลือก 'รูปหลัก' เพื่อใช้แสดงเป็นรูปประจำตัว  |  "
            "กด 'ลบ' เพื่อลบรูปที่ไม่ต้องการ (ต้องเหลืออย่างน้อย 1 รูป)"
        )
        desc.setStyleSheet("color: #86868B;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # Scroll area for embedding cards
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.grid_container = QWidget()
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setSpacing(10)
        self.grid_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        scroll.setWidget(self.grid_container)
        layout.addWidget(scroll)

        self.primary_group = QButtonGroup(self)
        self.primary_group.buttonClicked.connect(self._on_primary_changed)

        # Close button
        close_btn = QPushButton("ปิด")
        close_btn.setFixedWidth(100)
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignRight)

        self._load_embeddings()

    def _load_embeddings(self):
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Reset button group
        for btn in self.primary_group.buttons():
            self.primary_group.removeButton(btn)

        self._embeddings = get_person_embeddings(self.person_id)
        total = len(self._embeddings)

        for i, emb in enumerate(self._embeddings):
            card = QWidget()
            card.setFixedSize(140, 220)
            border_color = "#F5811F" if emb.get("is_primary") else "#D2D2D7"
            card.setStyleSheet(
                f"QWidget {{ border: 2px solid {border_color}; "
                f"border-radius: 10px; background: white; }}"
            )
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(6, 6, 6, 6)
            card_layout.setSpacing(3)

            # Thumbnail
            thumb_label = QLabel()
            thumb_label.setFixedSize(120, 120)
            thumb_label.setAlignment(Qt.AlignCenter)
            thumb_label.setStyleSheet("border: 1px solid #E8E8ED; border-radius: 6px;")
            if emb.get("thumbnail"):
                image = QImage.fromData(emb["thumbnail"])
                if not image.isNull():
                    pixmap = QPixmap.fromImage(image).scaled(
                        QSize(120, 120), Qt.KeepAspectRatio, Qt.SmoothTransformation
                    )
                    thumb_label.setPixmap(pixmap)
            else:
                thumb_label.setText("ไม่มีรูป")
            card_layout.addWidget(thumb_label, alignment=Qt.AlignCenter)

            # Primary radio
            radio = QRadioButton("รูปหลัก")
            radio.setStyleSheet("font-size: 11px; border: none;")
            emb_id = emb["id"]
            radio.setProperty("emb_id", emb_id)
            if emb.get("is_primary"):
                radio.setChecked(True)
            self.primary_group.addButton(radio)
            card_layout.addWidget(radio, alignment=Qt.AlignCenter)

            # Delete button (disabled if only 1 left)
            del_btn = QPushButton("ลบ")
            del_btn.setFixedHeight(24)
            del_btn.setStyleSheet("font-size: 11px; color: #FF3B30; border: none;")
            del_btn.clicked.connect(
                lambda checked, eid=emb_id: self._delete_embedding(eid)
            )
            if total <= 1:
                del_btn.setEnabled(False)
                del_btn.setToolTip("ต้องมีอย่างน้อย 1 รูปอ้างอิง")
            card_layout.addWidget(del_btn)

            self.grid_layout.addWidget(card, i // 3, i % 3)

    def _on_primary_changed(self, button):
        emb_id = button.property("emb_id")
        set_primary_embedding(self.person_id, emb_id)
        self._changed = True
        self._load_embeddings()

    def _delete_embedding(self, embedding_id: int):
        reply = QMessageBox.question(
            self, "ยืนยันการลบ",
            "ต้องการลบรูปอ้างอิงนี้หรือไม่?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            # If deleting primary, reassign to first remaining
            emb = next((e for e in self._embeddings if e["id"] == embedding_id), None)
            was_primary = emb and emb.get("is_primary")
            delete_person_embedding(embedding_id)
            if was_primary:
                remaining = get_person_embeddings(self.person_id)
                if remaining:
                    set_primary_embedding(self.person_id, remaining[0]["id"])
            self._changed = True
            self._load_embeddings()

    def accept(self):
        if self._changed:
            super().accept()
        else:
            super().reject()
