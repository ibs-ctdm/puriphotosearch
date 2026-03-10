"""Panel 1: Main folder selection and event subfolder picker."""

import os
from pathlib import Path

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QFileDialog, QTreeWidget, QTreeWidgetItem,
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
        self._updating_checks = False
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

        # Subfolder tree
        subfolder_group = QGroupBox("โฟลเดอร์ย่อย (กิจกรรม)")
        subfolder_layout = QVBoxLayout(subfolder_group)

        self.subfolder_tree = QTreeWidget()
        self.subfolder_tree.setHeaderHidden(True)
        self.subfolder_tree.setSelectionMode(QTreeWidget.NoSelection)
        self.subfolder_tree.itemChanged.connect(self._on_item_changed)
        subfolder_layout.addWidget(self.subfolder_tree)

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
        self.subfolder_tree.clear()
        folder = self.folder_input.text()
        if not folder or not os.path.isdir(folder):
            return

        self._updating_checks = True
        folder_count = 0
        for entry in sorted(Path(folder).iterdir()):
            if entry.is_dir() and not entry.name.startswith('.'):
                item = self._build_tree_item(entry)
                if item is not None:
                    self.subfolder_tree.addTopLevelItem(item)
                    folder_count += self._count_tree_items(item)

        self.subfolder_tree.expandAll()
        self._updating_checks = False

        self.summary_label.setText(f"พบ {folder_count} โฟลเดอร์")

    def _build_tree_item(self, dir_path: Path) -> QTreeWidgetItem | None:
        """Recursively build a tree item for a directory and its subdirectories."""
        # Count direct photos in this folder
        photo_count = sum(
            1 for f in dir_path.iterdir()
            if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS
        )

        # Recursively build children
        children = []
        for entry in sorted(dir_path.iterdir()):
            if entry.is_dir() and not entry.name.startswith('.'):
                child = self._build_tree_item(entry)
                if child is not None:
                    children.append(child)

        # Skip folders that have no photos and no children with photos
        if photo_count == 0 and not children:
            return None

        item = QTreeWidgetItem()
        item.setText(0, f"{dir_path.name}    ({photo_count} รูป)")
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(0, Qt.Checked)
        item.setData(0, Qt.UserRole, str(dir_path))

        for child in children:
            item.addChild(child)

        return item

    def _count_tree_items(self, item: QTreeWidgetItem) -> int:
        """Count an item and all its descendants."""
        count = 1
        for i in range(item.childCount()):
            count += self._count_tree_items(item.child(i))
        return count

    def _on_item_changed(self, item: QTreeWidgetItem, column: int):
        """Cascade checkbox changes to children."""
        if self._updating_checks:
            return

        self._updating_checks = True
        state = item.checkState(0)
        self._set_children_check_state(item, state)
        self._updating_checks = False

    def _set_children_check_state(self, item: QTreeWidgetItem, state):
        """Recursively set check state on all children."""
        for i in range(item.childCount()):
            child = item.child(i)
            child.setCheckState(0, state)
            self._set_children_check_state(child, state)

    def _select_all(self):
        self._updating_checks = True
        for i in range(self.subfolder_tree.topLevelItemCount()):
            item = self.subfolder_tree.topLevelItem(i)
            item.setCheckState(0, Qt.Checked)
            self._set_children_check_state(item, Qt.Checked)
        self._updating_checks = False

    def _deselect_all(self):
        self._updating_checks = True
        for i in range(self.subfolder_tree.topLevelItemCount()):
            item = self.subfolder_tree.topLevelItem(i)
            item.setCheckState(0, Qt.Unchecked)
            self._set_children_check_state(item, Qt.Unchecked)
        self._updating_checks = False

    def get_selected_folders(self) -> list:
        """Return list of (path, name, photo_count) for all checked folders."""
        selected = []
        for i in range(self.subfolder_tree.topLevelItemCount()):
            self._collect_checked(self.subfolder_tree.topLevelItem(i), selected)
        return selected

    def _collect_checked(self, item: QTreeWidgetItem, result: list):
        """Recursively collect all checked items."""
        if item.checkState(0) == Qt.Checked:
            path = item.data(0, Qt.UserRole)
            name = os.path.basename(path)
            photo_count = sum(
                1 for f in Path(path).iterdir()
                if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS
            )
            if photo_count > 0:
                result.append((path, name, photo_count))

        for i in range(item.childCount()):
            self._collect_checked(item.child(i), result)
