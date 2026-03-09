"""Panel 4: Search & organize interface."""

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QRadioButton, QButtonGroup, QSlider, QGroupBox,
    QMessageBox, QSplitter,
)

from app.database import get_all_persons, get_processed_event_folders
from app.workers.search_worker import SearchSingleWorker, SearchAllWorker
from app.ui.widgets.results_gallery import ResultsGallery
from app.ui.widgets.progress_dialog import ProgressDialog


class SearchPanel(QWidget):
    """Panel for searching persons in event folders and organizing results."""

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self._worker = None
        self._persons = []
        self._event_folders = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 15, 10, 10)
        layout.setSpacing(10)

        title = QLabel("ค้นหาและจัดเรียง")
        title.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(title)

        # Controls
        controls_group = QGroupBox("ตัวเลือกการค้นหา")
        controls_layout = QVBoxLayout(controls_group)

        # Event folder selector
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("โฟลเดอร์กิจกรรม:"))
        self.event_combo = QComboBox()
        self.event_combo.setMinimumWidth(300)
        row1.addWidget(self.event_combo)
        row1.addStretch()
        controls_layout.addLayout(row1)

        # Search mode
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("โหมดค้นหา:"))
        self.mode_group = QButtonGroup(self)
        self.single_radio = QRadioButton("บุคคลเดียว")
        self.all_radio = QRadioButton("ทุกบุคคล")
        self.single_radio.setChecked(True)
        self.mode_group.addButton(self.single_radio, 0)
        self.mode_group.addButton(self.all_radio, 1)
        row2.addWidget(self.single_radio)
        row2.addWidget(self.all_radio)
        row2.addStretch()
        controls_layout.addLayout(row2)

        self.single_radio.toggled.connect(self._on_mode_changed)

        # Person selector (single mode only)
        self.person_row = QHBoxLayout()
        self.person_row_label = QLabel("บุคคล:")
        self.person_row.addWidget(self.person_row_label)
        self.person_combo = QComboBox()
        self.person_combo.setMinimumWidth(300)
        self.person_row.addWidget(self.person_combo)
        self.person_row.addStretch()
        controls_layout.addLayout(self.person_row)

        # Threshold slider
        row4 = QHBoxLayout()
        row4.addWidget(QLabel("ค่าความคล้าย:"))
        self.threshold_slider = QSlider(Qt.Horizontal)
        self.threshold_slider.setRange(20, 90)
        self.threshold_slider.setValue(int(self.config.similarity_threshold * 100))
        self.threshold_slider.setFixedWidth(200)
        self.threshold_slider.valueChanged.connect(self._on_threshold_changed)
        row4.addWidget(self.threshold_slider)
        self.threshold_label = QLabel(f"{self.config.similarity_threshold:.2f}")
        self.threshold_label.setStyleSheet("font-weight: bold; min-width: 40px;")
        row4.addWidget(self.threshold_label)
        row4.addStretch()
        controls_layout.addLayout(row4)

        # Search button
        btn_layout = QHBoxLayout()
        self.search_btn = QPushButton("ค้นหาและจัดเรียง")
        self.search_btn.setStyleSheet("""
            QPushButton {
                background: #FF9800; color: white;
                padding: 10px 24px; border-radius: 4px;
                font-weight: bold; font-size: 14px;
            }
            QPushButton:hover { background: #F57C00; }
            QPushButton:disabled { background: #bbb; }
        """)
        self.search_btn.clicked.connect(self._start_search)
        btn_layout.addWidget(self.search_btn)
        btn_layout.addStretch()
        controls_layout.addLayout(btn_layout)

        layout.addWidget(controls_group)

        # Results gallery
        self.results_gallery = ResultsGallery()
        layout.addWidget(self.results_gallery, stretch=1)

    def refresh_data(self):
        """Reload persons and event folders from database."""
        # Persons
        self._persons = get_all_persons()
        self.person_combo.clear()
        for p in self._persons:
            self.person_combo.addItem(p["name"], p["id"])

        # Event folders
        self._event_folders = get_processed_event_folders()
        self.event_combo.clear()
        for ef in self._event_folders:
            self.event_combo.addItem(
                f"{ef['folder_name']}  ({ef['face_count']} ใบหน้า)",
                ef["id"],
            )

    def _on_mode_changed(self, checked):
        is_single = self.single_radio.isChecked()
        self.person_combo.setVisible(is_single)
        self.person_row_label.setVisible(is_single)

    def _on_threshold_changed(self, value):
        threshold = value / 100.0
        self.threshold_label.setText(f"{threshold:.2f}")

    def _start_search(self):
        if not self._event_folders:
            QMessageBox.warning(self, "คำเตือน", "ยังไม่มีโฟลเดอร์ที่ประมวลผลแล้ว กรุณาประมวลผลโฟลเดอร์ก่อน")
            return

        event_idx = self.event_combo.currentIndex()
        if event_idx < 0:
            return

        event_folder = self._event_folders[event_idx]
        threshold = self.threshold_slider.value() / 100.0

        self.results_gallery.clear()
        self.search_btn.setEnabled(False)

        if self.single_radio.isChecked():
            # Single person mode
            person_idx = self.person_combo.currentIndex()
            if person_idx < 0 or not self._persons:
                QMessageBox.warning(self, "คำเตือน", "ยังไม่ได้เลือกบุคคล กรุณาเพิ่มบุคคลก่อน")
                self.search_btn.setEnabled(True)
                return

            person = self._persons[person_idx]
            self._worker = SearchSingleWorker(
                person_dict=person,
                event_folder_id=event_folder["id"],
                event_folder_path=event_folder["folder_path"],
                threshold=threshold,
            )
            self._worker.finished_with_result.connect(self._on_single_result)
        else:
            # All persons mode
            if not self._persons:
                QMessageBox.warning(self, "คำเตือน", "ยังไม่มีบุคคลในฐานข้อมูล กรุณาเพิ่มบุคคลก่อน")
                self.search_btn.setEnabled(True)
                return

            self._worker = SearchAllWorker(
                persons=self._persons,
                event_folder_id=event_folder["id"],
                event_folder_path=event_folder["folder_path"],
                threshold=threshold,
            )
            self._worker.finished_with_result.connect(self._on_all_result)

        self._worker.status_message.connect(self._on_status)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_status(self, message):
        self.results_gallery.header_label.setText(message)

    def _on_single_result(self, result):
        self.search_btn.setEnabled(True)
        self.results_gallery.show_single_person_results(
            person_name=result["person_name"],
            matches=result["matches"],
            organized=result.get("organized"),
        )

    def _on_all_result(self, result):
        self.search_btn.setEnabled(True)
        self.results_gallery.show_all_persons_results(
            search_results=result.get("search_results", {}),
            organized=result.get("organized"),
        )

    def _on_error(self, message):
        self.search_btn.setEnabled(True)
        QMessageBox.warning(self, "ข้อผิดพลาดในการค้นหา", message)
