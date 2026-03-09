"""Main application window with sidebar navigation."""

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QStackedWidget,
    QStatusBar, QMenuBar, QMessageBox,
)

from app.config import AppConfig, APP_NAME, APP_VERSION
from app.database import get_db_stats
from app.workers.model_loader_worker import ModelLoaderWorker
from app.ui.widgets.folder_selector import FolderSelector
from app.ui.widgets.person_manager import PersonManager
from app.ui.widgets.event_processor import EventProcessor
from app.ui.widgets.search_panel import SearchPanel
from app.ui.widgets.settings_dialog import SettingsDialog


class MainWindow(QMainWindow):
    """Main application window with sidebar navigation and stacked panels."""

    def __init__(self, config: AppConfig, parent=None):
        super().__init__(parent)
        self.config = config

        self.setWindowTitle(f"Puri Photo Search v{APP_VERSION}")
        self.setMinimumSize(1000, 700)

        self._setup_menu()
        self._setup_ui()
        self._setup_status_bar()
        self._load_model()

    def _setup_menu(self):
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("ไฟล์")
        quit_action = QAction("ออก", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        # Edit menu
        edit_menu = menubar.addMenu("แก้ไข")
        settings_action = QAction("ตั้งค่า...", self)
        settings_action.setShortcut("Ctrl+,")
        settings_action.triggered.connect(self._show_settings)
        edit_menu.addAction(settings_action)

        # Help menu
        help_menu = menubar.addMenu("ช่วยเหลือ")
        about_action = QAction("เกี่ยวกับ", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Sidebar
        self.sidebar = QListWidget()
        self.sidebar.setFixedWidth(140)
        self.sidebar.setIconSize(QSize(32, 32))
        self.sidebar.setStyleSheet("""
            QListWidget {
                background: #f5f5f5;
                border: none;
                border-right: 1px solid #ddd;
                font-size: 12px;
                color: #555;
            }
            QListWidget::item {
                padding: 12px 8px;
                border-bottom: 1px solid #eee;
                color: #555;
            }
            QListWidget::item:selected {
                background: #e3f2fd;
                color: #1976D2;
                font-weight: bold;
            }
            QListWidget::item:hover {
                background: #eeeeee;
            }
        """)

        items = [
            ("1. ตั้งค่าโฟลเดอร์", "เลือกโฟลเดอร์รูปภาพ"),
            ("2. ฐานข้อมูลบุคคล", "จัดการรายชื่อบุคคล"),
            ("3. ประมวลผล", "ตรวจจับใบหน้า"),
            ("4. ค้นหา", "ค้นหาและจัดเรียง"),
        ]
        for text, tooltip in items:
            item = QListWidgetItem(text)
            item.setToolTip(tooltip)
            item.setSizeHint(QSize(130, 55))
            self.sidebar.addItem(item)

        self.sidebar.currentRowChanged.connect(self._on_panel_changed)

        # Stacked panels
        self.stack = QStackedWidget()

        self.folder_panel = FolderSelector(self.config)
        self.person_panel = PersonManager()
        self.process_panel = EventProcessor()
        self.search_panel = SearchPanel(self.config)

        self.stack.addWidget(self.folder_panel)
        self.stack.addWidget(self.person_panel)
        self.stack.addWidget(self.process_panel)
        self.stack.addWidget(self.search_panel)

        # Connect signals
        self.folder_panel.folder_changed.connect(self._on_folder_changed)
        self.person_panel.person_changed.connect(self._on_person_changed)
        self.process_panel.processing_complete.connect(self._on_processing_complete)

        main_layout.addWidget(self.sidebar)
        main_layout.addWidget(self.stack, 1)

        # Select first panel
        self.sidebar.setCurrentRow(0)

    def _setup_status_bar(self):
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.model_status = QWidget()
        model_layout = QHBoxLayout(self.model_status)
        model_layout.setContentsMargins(0, 0, 0, 0)
        self.model_label = QLabel("โมเดล: กำลังโหลด...")
        self.model_label.setStyleSheet("color: #FF9800;")
        model_layout.addWidget(self.model_label)

        self.db_stats_label = QLabel("")
        self.db_stats_label.setStyleSheet("color: #666;")

        self.status_bar.addWidget(self.model_status)
        self.status_bar.addPermanentWidget(self.db_stats_label)
        self._update_db_stats()

    def _load_model(self):
        self._model_worker = ModelLoaderWorker(self.config.face_model_name)
        self._model_worker.status_message.connect(
            lambda msg: self.model_label.setText(f"โมเดล: {msg}")
        )
        self._model_worker.finished_with_result.connect(self._on_model_loaded)
        self._model_worker.error.connect(self._on_model_error)
        self._model_worker.start()

    def _on_model_loaded(self, result):
        self.model_label.setText("โมเดล: พร้อมใช้งาน")
        self.model_label.setStyleSheet("color: #4CAF50; font-weight: bold;")

    def _on_model_error(self, message):
        self.model_label.setText("โมเดล: เกิดข้อผิดพลาด")
        self.model_label.setStyleSheet("color: #d32f2f;")
        QMessageBox.critical(self, "ข้อผิดพลาดโมเดล", message)

    def _on_panel_changed(self, index):
        self.stack.setCurrentIndex(index)

        # Refresh data when switching to certain panels
        if index == 2:  # Process panel
            folders = self.folder_panel.get_selected_folders()
            self.process_panel.set_folders(folders)
        elif index == 3:  # Search panel
            self.search_panel.refresh_data()

    def _on_folder_changed(self, folder_path):
        self._update_db_stats()

    def _on_person_changed(self):
        self._update_db_stats()

    def _on_processing_complete(self):
        self._update_db_stats()

    def _update_db_stats(self):
        stats = get_db_stats()
        self.db_stats_label.setText(
            f"บุคคล: {stats['persons']}  |  รูปภาพ: {stats['photos']}  |  ใบหน้า: {stats['faces']}"
        )

    def _show_settings(self):
        dialog = SettingsDialog(self.config, self)
        if dialog.exec():
            self._update_db_stats()

    def _show_about(self):
        QMessageBox.about(
            self, f"เกี่ยวกับ Puri Photo Search",
            f"<h2>Puri Photo Search v{APP_VERSION}</h2>"
            f"<p>โปรแกรมจัดเรียงรูปภาพด้วยการจดจำใบหน้า สำหรับ macOS</p>"
            f"<p>ขับเคลื่อนโดย InsightFace (ArcFace) และ PySide6</p>"
        )
