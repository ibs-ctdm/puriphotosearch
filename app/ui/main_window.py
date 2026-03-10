"""Main application window with sidebar navigation."""

import os
import sys

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QAction, QIcon, QPixmap
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QStackedWidget,
    QStatusBar, QMenuBar, QMessageBox, QFrame, QPushButton,
)

from app.config import AppConfig, APP_NAME, APP_VERSION
from app.database import get_db_stats
from app.workers.model_loader_worker import ModelLoaderWorker
from app.ui.widgets.folder_selector import FolderSelector
from app.ui.widgets.person_manager import PersonManager
from app.ui.widgets.event_processor import EventProcessor
from app.ui.widgets.search_panel import SearchPanel
from app.ui.widgets.scan_mode_panel import ScanModePanel
from app.ui.widgets.settings_dialog import SettingsDialog

# Resolve icon path — works both in dev and PyInstaller bundle
if getattr(sys, 'frozen', False):
    _BASE_DIR = sys._MEIPASS
else:
    _BASE_DIR = os.path.join(os.path.dirname(__file__), "..", "..")
_ICON_PATH = os.path.join(_BASE_DIR, "resources", "icon.png")


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

        # ===== Sidebar =====
        sidebar_widget = QWidget()
        sidebar_widget.setFixedWidth(170)
        sidebar_widget.setStyleSheet("""
            QWidget#sidebar {
                background: #F0F7FC;
                border-right: 1px solid #D2D2D7;
            }
        """)
        sidebar_widget.setObjectName("sidebar")
        sidebar_layout = QVBoxLayout(sidebar_widget)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)

        # --- Logo area ---
        logo_container = QWidget()
        logo_container.setStyleSheet("background: transparent;")
        logo_layout = QVBoxLayout(logo_container)
        logo_layout.setContentsMargins(12, 16, 12, 12)
        logo_layout.setSpacing(6)
        logo_layout.setAlignment(Qt.AlignCenter)

        # Logo image
        logo_label = QLabel()
        logo_label.setAlignment(Qt.AlignCenter)
        logo_label.setStyleSheet("background: transparent; border: none;")
        if os.path.exists(_ICON_PATH):
            pixmap = QPixmap(_ICON_PATH).scaled(
                QSize(120, 60), Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            logo_label.setPixmap(pixmap)
        else:
            logo_label.setText("Puri")
            logo_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #F5811F;")
        logo_layout.addWidget(logo_label)

        sidebar_layout.addWidget(logo_container)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("background: #D2D2D7; max-height: 1px; border: none;")
        sidebar_layout.addWidget(sep)

        # --- Navigation list ---
        self.sidebar = QListWidget()
        self.sidebar.setStyleSheet("""
            QListWidget {
                background: transparent;
                border: none;
                font-size: 13px;
                color: #424245;
                outline: none;
                padding-top: 4px;
            }
            QListWidget::item {
                padding: 14px 12px;
                border: none;
                border-left: 3px solid transparent;
                margin: 1px 6px;
                border-radius: 8px;
            }
            QListWidget::item:selected {
                background: #FFF3E8;
                color: #F5811F;
                font-weight: bold;
                border-left: 3px solid #F5811F;
            }
            QListWidget::item:hover:!selected {
                background: #E8EFF5;
            }
        """)

        items = [
            ("1. ตั้งค่าโฟลเดอร์", "เลือกโฟลเดอร์รูปภาพ"),
            ("2. ฐานข้อมูลบุคคล", "จัดการรายชื่อบุคคล"),
            ("3. ประมวลผล", "ตรวจจับใบหน้า"),
            ("4. ค้นหา", "ค้นหาและจัดเรียง"),
            ("5. สแกนและตั้งชื่อ", "สแกนใบหน้าก่อน ตั้งชื่อทีหลัง"),
        ]
        for text, tooltip in items:
            item = QListWidgetItem(text)
            item.setToolTip(tooltip)
            item.setSizeHint(QSize(150, 48))
            self.sidebar.addItem(item)

        self.sidebar.currentRowChanged.connect(self._on_panel_changed)
        sidebar_layout.addWidget(self.sidebar)

        sidebar_layout.addStretch()

        # Version label at bottom
        version_label = QLabel(f"v{APP_VERSION}")
        version_label.setAlignment(Qt.AlignCenter)
        version_label.setStyleSheet(
            "color: #C7C7CC; font-size: 11px; padding: 8px; background: transparent;"
        )
        sidebar_layout.addWidget(version_label)

        # Stacked panels
        self.stack = QStackedWidget()

        self.folder_panel = FolderSelector(self.config)
        self.person_panel = PersonManager()
        self.process_panel = EventProcessor()
        self.search_panel = SearchPanel(self.config)
        self.scan_panel = ScanModePanel()

        # Wrap first 3 panels with "Next" button
        panels = [self.folder_panel, self.person_panel, self.process_panel]
        for i, panel in enumerate(panels):
            self.stack.addWidget(self._wrap_with_next(panel, i))
        self.stack.addWidget(self.search_panel)  # Panel 4: no next button
        self.stack.addWidget(self.scan_panel)     # Panel 5: no next button

        # Connect signals
        self.folder_panel.folder_changed.connect(self._on_folder_changed)
        self.person_panel.person_changed.connect(self._on_person_changed)
        self.process_panel.processing_complete.connect(self._on_processing_complete)
        self.scan_panel.person_changed.connect(self._on_person_changed)

        main_layout.addWidget(sidebar_widget)
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
        self.model_label.setStyleSheet("color: #F5811F; font-weight: 500;")
        model_layout.addWidget(self.model_label)

        self.db_stats_label = QLabel("")
        self.db_stats_label.setStyleSheet("color: #86868B;")

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
        self.model_label.setStyleSheet("color: #34C759; font-weight: bold;")

    def _on_model_error(self, message):
        self.model_label.setText("โมเดล: เกิดข้อผิดพลาด")
        self.model_label.setStyleSheet("color: #FF3B30;")
        QMessageBox.critical(self, "ข้อผิดพลาดโมเดล", message)

    def _wrap_with_next(self, panel: QWidget, panel_index: int) -> QWidget:
        """Wrap a panel widget with a 'Next' button at the bottom-right."""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(panel, 1)

        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 0, 16, 12)
        btn_layout.addStretch()
        next_btn = QPushButton("ถัดไป →")
        next_btn.setStyleSheet("""
            QPushButton {
                background: #F5811F; color: white;
                padding: 10px 28px; border-radius: 8px;
                font-size: 14px; font-weight: bold; border: none;
            }
            QPushButton:hover { background: #E0710A; }
        """)
        next_btn.clicked.connect(lambda: self._go_next(panel_index))
        btn_layout.addWidget(next_btn)
        layout.addLayout(btn_layout)
        return container

    def _go_next(self, current_index: int):
        """Navigate to the next sidebar item."""
        next_index = current_index + 1
        if next_index < self.sidebar.count():
            self.sidebar.setCurrentRow(next_index)

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
