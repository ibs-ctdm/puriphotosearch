"""Panel 3: Process event folders for face detection."""

import os

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTreeWidget, QTreeWidgetItem, QHeaderView, QMessageBox,
    QProgressBar, QGroupBox,
)

from app.database import add_or_get_event_folder, get_all_event_folders, reset_event_folder
from app.services.photo_processor import PhotoProcessor
from app.workers.process_worker import ProcessWorker
from app.ui.widgets.progress_dialog import ProgressDialog


class EventProcessor(QWidget):
    """Panel for processing event folders to detect faces."""

    processing_complete = Signal()  # emitted when processing finishes

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self._folders_to_process = []
        self._current_folder_idx = 0
        self._updating_checks = False
        self._processing_cancelled = False
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 15, 10, 10)
        layout.setSpacing(15)

        title = QLabel("ประมวลผลใบหน้าในโฟลเดอร์")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #1D1D1F;")
        layout.addWidget(title)

        desc = QLabel(
            "สแกนรูปภาพในแต่ละโฟลเดอร์เพื่อตรวจจับใบหน้า "
            "ต้องทำขั้นตอนนี้ก่อนจึงจะค้นหาได้"
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #86868B;")
        layout.addWidget(desc)

        # Folder tree (hierarchical)
        self.table = QTreeWidget()
        self.table.setColumnCount(4)
        self.table.setHeaderLabels(["โฟลเดอร์", "รูปภาพ", "ใบหน้า", "สถานะ"])
        self.table.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.header().setSectionResizeMode(1, QHeaderView.Fixed)
        self.table.header().setSectionResizeMode(2, QHeaderView.Fixed)
        self.table.header().setSectionResizeMode(3, QHeaderView.Fixed)
        self.table.header().resizeSection(1, 70)
        self.table.header().resizeSection(2, 70)
        self.table.header().resizeSection(3, 110)
        self.table.setSelectionMode(QTreeWidget.NoSelection)
        self.table.setEditTriggers(QTreeWidget.NoEditTriggers)
        self.table.setRootIsDecorated(True)
        self.table.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.table)

        # Buttons
        btn_layout = QHBoxLayout()


        self.reprocess_btn = QPushButton("ประมวลผล")
        self.reprocess_btn.setStyleSheet("""
            QPushButton {
                background: #F5811F; color: white;
                padding: 8px 18px; border-radius: 8px;
                font-weight: bold; font-size: 13px; border: none;
            }
            QPushButton:hover { background: #E0710A; }
            QPushButton:disabled { background: #C7C7CC; }
        """)

        self.process_btn = QPushButton("ประมวลผลทั้งหมด")
        self.process_btn.setStyleSheet("""
            QPushButton {
                background: #fc1c45; color: white;
                padding: 8px 18px; border-radius: 8px;
                font-weight: bold; font-size: 13px; border: none;
            }
            QPushButton:hover { background: #e0710a; }
            QPushButton:disabled { background: #C7C7CC; }
        """)
        self.process_btn.clicked.connect(self._start_processing)

        self.reprocess_btn.clicked.connect(self._reprocess_selected)

        self.select_all_btn = QPushButton("เลือกทั้งหมด")
        self.select_all_btn.clicked.connect(self._select_all)

        self.deselect_all_btn = QPushButton("ยกเลิกทั้งหมด")
        self.deselect_all_btn.clicked.connect(self._deselect_all)

        self.refresh_btn = QPushButton("รีเฟรช")
        self.refresh_btn.clicked.connect(self.refresh_table)

        btn_layout.addWidget(self.process_btn)
        btn_layout.addWidget(self.reprocess_btn)
        btn_layout.addWidget(self.select_all_btn)
        btn_layout.addWidget(self.deselect_all_btn)
        btn_layout.addWidget(self.refresh_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # Progress area
        progress_group = QGroupBox("ความคืบหน้า")
        progress_layout = QVBoxLayout(progress_group)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_label = QLabel("พร้อม")
        self.progress_detail = QLabel("")
        self.progress_detail.setStyleSheet("color: #86868B;")
        self.cancel_btn = QPushButton("ยกเลิก")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel_processing)

        progress_layout.addWidget(self.progress_label)
        progress_layout.addWidget(self.progress_bar)
        progress_layout.addWidget(self.progress_detail)
        progress_layout.addWidget(self.cancel_btn, alignment=Qt.AlignLeft)
        layout.addWidget(progress_group)

    def set_folders(self, folders: list):
        """Set the list of event folders from FolderSelector."""
        self._selected_folders = folders
        self.refresh_table()

    def refresh_table(self):
        """Refresh the tree with current folder statuses from DB."""
        if not hasattr(self, '_selected_folders'):
            return

        self._updating_checks = True
        self.table.clear()
        self.table.setHeaderLabels(["โฟลเดอร์", "รูปภาพ", "ใบหน้า", "สถานะ"])

        db_folders = {f["folder_path"]: f for f in get_all_event_folders()}

        # Build tree hierarchy from flat folder paths
        # Sort by path so parents come before children
        sorted_folders = sorted(self._selected_folders, key=lambda x: x[0])

        # Map path -> QTreeWidgetItem for parent lookup
        path_to_item = {}

        for path, name, photo_count in sorted_folders:
            db_info = db_folders.get(path)

            item = QTreeWidgetItem()
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setText(0, name)
            item.setCheckState(0, Qt.Checked)
            item.setText(1, f"{photo_count:,}")
            item.setData(0, Qt.UserRole, path)

            if db_info and db_info["is_processed"]:
                item.setText(2, f"{db_info['face_count']:,}")
                item.setText(3, "\u2705 เสร็จแล้ว")
                item.setForeground(3, Qt.darkGreen)
            else:
                item.setText(2, "-")
                item.setText(3, "รอประมวลผล")
                item.setForeground(3, Qt.darkYellow)

            # Find parent: check if any already-added path is a parent of this one
            parent_item = None
            parent_dir = os.path.dirname(path)
            while parent_dir:
                if parent_dir in path_to_item:
                    parent_item = path_to_item[parent_dir]
                    break
                next_dir = os.path.dirname(parent_dir)
                if next_dir == parent_dir:  # reached filesystem root
                    break
                parent_dir = next_dir

            if parent_item:
                parent_item.addChild(item)
            else:
                self.table.addTopLevelItem(item)

            path_to_item[path] = item

        self.table.expandAll()
        self._updating_checks = False

    def _on_item_changed(self, item, column):
        """Cascade checkbox changes to children."""
        if self._updating_checks:
            return
        self._updating_checks = True
        state = item.checkState(0)
        self._set_children_check_state(item, state)
        self._updating_checks = False

    def _set_children_check_state(self, item, state):
        """Recursively set check state on all children."""
        for i in range(item.childCount()):
            child = item.child(i)
            child.setCheckState(0, state)
            self._set_children_check_state(child, state)

    def _select_all(self):
        self._updating_checks = True
        for i in range(self.table.topLevelItemCount()):
            item = self.table.topLevelItem(i)
            item.setCheckState(0, Qt.Checked)
            self._set_children_check_state(item, Qt.Checked)
        self._updating_checks = False

    def _deselect_all(self):
        self._updating_checks = True
        for i in range(self.table.topLevelItemCount()):
            item = self.table.topLevelItem(i)
            item.setCheckState(0, Qt.Unchecked)
            self._set_children_check_state(item, Qt.Unchecked)
        self._updating_checks = False

    def _collect_checked_items(self, parent=None):
        """Recursively collect all checked QTreeWidgetItems."""
        items = []
        if parent is None:
            for i in range(self.table.topLevelItemCount()):
                item = self.table.topLevelItem(i)
                if item.checkState(0) == Qt.Checked:
                    items.append(item)
                items.extend(self._collect_checked_items(item))
        else:
            for i in range(parent.childCount()):
                child = parent.child(i)
                if child.checkState(0) == Qt.Checked:
                    items.append(child)
                items.extend(self._collect_checked_items(child))
        return items

    def _start_processing(self):
        """Process all checked + unprocessed folders sequentially."""
        db_folders = {f["folder_path"]: f for f in get_all_event_folders()}

        checked_items = self._collect_checked_items()
        self._folders_to_process = []
        for item in checked_items:
            path = item.data(0, Qt.UserRole)
            name = item.text(0)
            count = int(item.text(1)) if item.text(1).isdigit() else 0
            db_info = db_folders.get(path)
            if not db_info or not db_info["is_processed"]:
                if count > 0:
                    self._folders_to_process.append((path, name, count))

        if not self._folders_to_process:
            QMessageBox.information(self, "แจ้งเตือน", "ทุกโฟลเดอร์ถูกประมวลผลแล้ว")
            return

        self._current_folder_idx = 0
        self._processing_cancelled = False
        self.process_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self._process_next_folder()

    def _process_next_folder(self):
        if self._processing_cancelled:
            self._on_cancelled()
            return
        if self._current_folder_idx >= len(self._folders_to_process):
            self._on_all_done()
            return

        path, name, _ = self._folders_to_process[self._current_folder_idx]
        self.progress_label.setText(
            f"กำลังประมวลผลโฟลเดอร์ {self._current_folder_idx + 1}/{len(self._folders_to_process)}: {name}"
        )

        # Scan and register folder
        image_paths = PhotoProcessor.scan_folder(path)
        event_folder_id = add_or_get_event_folder(path)

        self._worker = ProcessWorker(event_folder_id, image_paths)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_with_result.connect(self._on_folder_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_progress(self, current, total, message):
        percent = int(current / max(total, 1) * 100)
        self.progress_bar.setValue(percent)
        self.progress_detail.setText(f"{current:,}/{total:,} - {message}")

    def _on_folder_done(self, result):
        if self._processing_cancelled:
            self._on_cancelled()
            return
        self._current_folder_idx += 1
        self.refresh_table()
        self._process_next_folder()

    def _on_all_done(self):
        self.progress_label.setText("ประมวลผลทุกโฟลเดอร์เสร็จสิ้น!")
        self.progress_bar.setValue(100)
        self.process_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.processing_complete.emit()

    def _on_error(self, message):
        if self._processing_cancelled:
            self._on_cancelled()
            return
        QMessageBox.warning(self, "ข้อผิดพลาดในการประมวลผล", message)
        self._current_folder_idx += 1
        self._process_next_folder()

    def _cancel_processing(self):
        self._processing_cancelled = True
        if self._worker:
            self._worker.cancel()
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setText("กำลังยกเลิก...")

    def _on_cancelled(self):
        self.progress_label.setText("ยกเลิกการประมวลผลแล้ว")
        self.process_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setText("ยกเลิก")
        self.refresh_table()

    def _reprocess_selected(self):
        checked_items = self._collect_checked_items()
        if not checked_items:
            QMessageBox.information(self, "แจ้งเตือน", "กรุณาติ๊กเลือกโฟลเดอร์ที่ต้องการประมวลผลใหม่ก่อน")
            return

        reply = QMessageBox.question(
            self, "ยืนยันการประมวลผลใหม่",
            "การดำเนินการนี้จะลบข้อมูลใบหน้าเดิมและประมวลผลโฟลเดอร์ที่ติ๊กไว้ใหม่ ต้องการดำเนินการต่อหรือไม่?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        db_folders = {f["folder_path"]: f for f in get_all_event_folders()}
        self._folders_to_process = []

        for item in checked_items:
            path = item.data(0, Qt.UserRole)
            name = item.text(0)
            count = int(item.text(1)) if item.text(1).isdigit() else 0
            if path in db_folders:
                reset_event_folder(db_folders[path]["id"])
            if count > 0:
                self._folders_to_process.append((path, name, count))

        if self._folders_to_process:
            self._current_folder_idx = 0
            self._processing_cancelled = False
            self.process_btn.setEnabled(False)
            self.cancel_btn.setEnabled(True)
            self.cancel_btn.setText("ยกเลิก")
            self._process_next_folder()
