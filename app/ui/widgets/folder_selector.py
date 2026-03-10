"""Panel 1: Main folder selection and event subfolder picker."""

import os
from pathlib import Path

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QFileDialog, QListWidget, QListWidgetItem,
    QGroupBox,
)

from app.services.photo_processor import IMAGE_EXTENSIONS


class FolderSelector(QWidget):
    """Panel for selecting main photos folder and viewing event subfolders."""

    folder_changed = Signal(str)             # main folder path
    subfolders_selected = Signal(list)        # list of (path, name, photo_count)

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self._setup_ui()

        if self.config.main_photos_folder and os.path.isdir(self.config.main_photos_folder):
            self.folder_input.setText(self.config.main_photos_folder)
            self._scan_subfolders()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 15, 10, 10)
        layout.setSpacing(15)

        # Title
        title = QLabel("ตั้งค่าโฟลเดอร์")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #1D1D1F;")
        layout.addWidget(title)

        desc = QLabel("เลือกโฟลเดอร์หลักที่เก็บรูปภาพ โฟลเดอร์ย่อยจะถูกใช้เป็นกิจกรรม")
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #86868B; margin-bottom: 10px;")
        layout.addWidget(desc)

        # Folder picker
        folder_group = QGroupBox("โฟลเดอร์รูปภาพหลัก")
        folder_layout = QHBoxLayout(folder_group)
        self.folder_input = QLineEdit()
        self.folder_input.setReadOnly(True)
        self.folder_input.setPlaceholderText("กดปุ่ม เรียกดู เพื่อเลือกโฟลเดอร์...")
        self.browse_btn = QPushButton("เรียกดู...")
        self.browse_btn.setFixedWidth(100)
        self.browse_btn.clicked.connect(self._browse_folder)
        folder_layout.addWidget(self.folder_input)
        folder_layout.addWidget(self.browse_btn)
        layout.addWidget(folder_group)

        # Subfolder list
        subfolder_group = QGroupBox("โฟลเดอร์ย่อย (กิจกรรม)")
        subfolder_layout = QVBoxLayout(subfolder_group)

        self.subfolder_list = QListWidget()
        self.subfolder_list.setSelectionMode(QListWidget.NoSelection)
        subfolder_layout.addWidget(self.subfolder_list)

        # Buttons
        btn_layout = QHBoxLayout()
        self.select_all_btn = QPushButton("เลือกทั้งหมด")
        self.select_all_btn.clicked.connect(self._select_all)
        self.deselect_all_btn = QPushButton("ยกเลิกทั้งหมด")
        self.deselect_all_btn.clicked.connect(self._deselect_all)
        self.refresh_btn = QPushButton("รีเฟรช")
        self.refresh_btn.clicked.connect(self._scan_subfolders)
        btn_layout.addWidget(self.select_all_btn)
        btn_layout.addWidget(self.deselect_all_btn)
        btn_layout.addWidget(self.refresh_btn)
        btn_layout.addStretch()
        subfolder_layout.addLayout(btn_layout)

        # Summary
        self.summary_label = QLabel("")
        self.summary_label.setStyleSheet("color: #86868B; font-style: italic;")
        subfolder_layout.addWidget(self.summary_label)

        layout.addWidget(subfolder_group)
        layout.addStretch()

    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "เลือกโฟลเดอร์รูปภาพหลัก",
            self.config.main_photos_folder or os.path.expanduser("~"),
        )
        if folder:
            self.folder_input.setText(folder)
            self.config.main_photos_folder = folder
            self.config.save()
            self.folder_changed.emit(folder)
            self._scan_subfolders()

    def _scan_subfolders(self):
        self.subfolder_list.clear()
        folder = self.folder_input.text()
        if not folder or not os.path.isdir(folder):
            return

        subfolders = []
        for entry in sorted(Path(folder).iterdir()):
            if entry.is_dir() and not entry.name.startswith('.'):
                photo_count = sum(
                    1 for f in entry.rglob("*")
                    if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS
                )
                subfolders.append((str(entry), entry.name, photo_count))

        for path, name, count in subfolders:
            item = QListWidgetItem()
            item.setText(f"{name}    ({count} รูป)")
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)
            item.setData(Qt.UserRole, path)
            self.subfolder_list.addItem(item)

        self.summary_label.setText(
            f"พบ {len(subfolders)} โฟลเดอร์ย่อย"
        )

    def _select_all(self):
        for i in range(self.subfolder_list.count()):
            self.subfolder_list.item(i).setCheckState(Qt.Checked)

    def _deselect_all(self):
        for i in range(self.subfolder_list.count()):
            self.subfolder_list.item(i).setCheckState(Qt.Unchecked)

    def get_selected_folders(self) -> list:
        """Return list of (path, name, photo_count) for checked subfolders."""
        selected = []
        for i in range(self.subfolder_list.count()):
            item = self.subfolder_list.item(i)
            if item.checkState() == Qt.Checked:
                path = item.data(Qt.UserRole)
                name = os.path.basename(path)
                # Re-count photos (recursive)
                photo_count = sum(
                    1 for f in Path(path).rglob("*")
                    if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS
                )
                selected.append((path, name, photo_count))
        return selected
