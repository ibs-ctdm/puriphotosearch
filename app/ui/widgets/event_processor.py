"""Panel 3: Process event folders for face detection."""

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
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
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 15, 10, 10)
        layout.setSpacing(15)

        title = QLabel("ประมวลผลโฟลเดอร์กิจกรรม")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #1D1D1F;")
        layout.addWidget(title)

        desc = QLabel(
            "สแกนรูปภาพในแต่ละโฟลเดอร์กิจกรรมเพื่อตรวจจับใบหน้า "
            "ต้องทำขั้นตอนนี้ก่อนจึงจะค้นหาได้"
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #86868B;")
        layout.addWidget(desc)

        # Folder table
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["โฟลเดอร์", "รูปภาพ", "ใบหน้า", "สถานะ"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.table)

        # Buttons
        btn_layout = QHBoxLayout()
        self.process_btn = QPushButton("ประมวลผลที่ยังไม่ได้ทำ")
        self.process_btn.setStyleSheet("""
            QPushButton {
                background: #F5811F; color: white;
                padding: 8px 18px; border-radius: 8px;
                font-weight: bold; font-size: 13px; border: none;
            }
            QPushButton:hover { background: #E0710A; }
            QPushButton:disabled { background: #C7C7CC; }
        """)
        self.process_btn.clicked.connect(self._start_processing)

        self.reprocess_btn = QPushButton("ประมวลผลใหม่ (ที่เลือก)")
        self.reprocess_btn.clicked.connect(self._reprocess_selected)

        self.refresh_btn = QPushButton("รีเฟรช")
        self.refresh_btn.clicked.connect(self.refresh_table)

        btn_layout.addWidget(self.process_btn)
        btn_layout.addWidget(self.reprocess_btn)
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
        """Refresh the table with current folder statuses from DB."""
        if not hasattr(self, '_selected_folders'):
            return

        db_folders = {f["folder_path"]: f for f in get_all_event_folders()}
        self.table.setRowCount(len(self._selected_folders))

        for i, (path, name, photo_count) in enumerate(self._selected_folders):
            db_info = db_folders.get(path)

            self.table.setItem(i, 0, QTableWidgetItem(name))
            self.table.setItem(i, 1, QTableWidgetItem(str(photo_count)))

            if db_info and db_info["is_processed"]:
                self.table.setItem(i, 2, QTableWidgetItem(str(db_info["face_count"])))
                status_item = QTableWidgetItem("\u2705 เสร็จแล้ว")
                status_item.setForeground(Qt.darkGreen)
            else:
                self.table.setItem(i, 2, QTableWidgetItem("-"))
                status_item = QTableWidgetItem("รอประมวลผล")
                status_item.setForeground(Qt.darkYellow)

            status_item.setData(Qt.UserRole, path)
            self.table.setItem(i, 3, status_item)

    def _start_processing(self):
        """Process all unprocessed folders sequentially."""
        db_folders = {f["folder_path"]: f for f in get_all_event_folders()}

        self._folders_to_process = []
        for path, name, count in self._selected_folders:
            db_info = db_folders.get(path)
            if not db_info or not db_info["is_processed"]:
                if count > 0:
                    self._folders_to_process.append((path, name, count))

        if not self._folders_to_process:
            QMessageBox.information(self, "แจ้งเตือน", "ทุกโฟลเดอร์ถูกประมวลผลแล้ว")
            return

        self._current_folder_idx = 0
        self.process_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self._process_next_folder()

    def _process_next_folder(self):
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
        self.progress_detail.setText(f"{current}/{total} - {message}")

    def _on_folder_done(self, result):
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
        QMessageBox.warning(self, "ข้อผิดพลาดในการประมวลผล", message)
        self._current_folder_idx += 1
        self._process_next_folder()

    def _cancel_processing(self):
        if self._worker:
            self._worker.cancel()
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setText("กำลังยกเลิก...")

    def _reprocess_selected(self):
        selected_rows = set(idx.row() for idx in self.table.selectedIndexes())
        if not selected_rows:
            QMessageBox.information(self, "แจ้งเตือน", "กรุณาเลือกโฟลเดอร์ที่ต้องการประมวลผลใหม่ก่อน")
            return

        reply = QMessageBox.question(
            self, "ยืนยันการประมวลผลใหม่",
            "การดำเนินการนี้จะลบข้อมูลใบหน้าเดิมและประมวลผลโฟลเดอร์ที่เลือกใหม่ ต้องการดำเนินการต่อหรือไม่?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        db_folders = {f["folder_path"]: f for f in get_all_event_folders()}
        self._folders_to_process = []

        for row in selected_rows:
            path = self._selected_folders[row][0]
            name = self._selected_folders[row][1]
            count = self._selected_folders[row][2]
            if path in db_folders:
                reset_event_folder(db_folders[path]["id"])
            if count > 0:
                self._folders_to_process.append((path, name, count))

        if self._folders_to_process:
            self._current_folder_idx = 0
            self.process_btn.setEnabled(False)
            self.cancel_btn.setEnabled(True)
            self.cancel_btn.setText("ยกเลิก")
            self._process_next_folder()
