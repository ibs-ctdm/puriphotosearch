"""Main application window with top navbar navigation."""

import os
import sys

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QAction, QPixmap
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLabel,
    QPushButton, QStackedWidget,
    QStatusBar, QMessageBox,
)

from app.config import AppConfig, APP_NAME, APP_VERSION
from app.database import get_db_stats
from app.workers.model_loader_worker import ModelLoaderWorker
from app.ui.widgets.main_panel import MainPanel
from app.ui.widgets.person_manager import PersonManager
from app.ui.widgets.settings_dialog import SettingsDialog
from app.ui.widgets.help_panel import HelpPanel

# Resolve icon path — works both in dev and PyInstaller bundle
if getattr(sys, 'frozen', False):
    _BASE_DIR = sys._MEIPASS
else:
    _BASE_DIR = os.path.join(os.path.dirname(__file__), "..", "..")
_ICON_PATH = os.path.join(_BASE_DIR, "resources", "icon.png")


class MainWindow(QMainWindow):
    """Main application window with top navbar and stacked panels."""

    def __init__(self, config: AppConfig, parent=None):
        super().__init__(parent)
        self.config = config
        self._nav_buttons = []

        self.setWindowTitle(f"Puri Photo Search v{APP_VERSION}")
        self.setMinimumSize(1100, 700)

        self._setup_menu()
        self._setup_ui()
        self._setup_status_bar()
        self._load_model()

    def _setup_menu(self):
        menubar = self.menuBar()

        file_menu = menubar.addMenu("ไฟล์")
        quit_action = QAction("ออก", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        edit_menu = menubar.addMenu("แก้ไข")
        settings_action = QAction("ตั้งค่า...", self)
        settings_action.setShortcut("Ctrl+,")
        settings_action.triggered.connect(self._show_settings)
        edit_menu.addAction(settings_action)

        help_menu = menubar.addMenu("ช่วยเหลือ")
        about_action = QAction("เกี่ยวกับ", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ===== Top Navbar =====
        navbar = QWidget()
        navbar.setObjectName("navbar")
        navbar.setFixedHeight(48)
        navbar.setStyleSheet("""
            QWidget#navbar {
                background: #FAFAFA;
                border-bottom: 1px solid #D2D2D7;
            }
        """)
        nav_layout = QHBoxLayout(navbar)
        nav_layout.setContentsMargins(12, 0, 12, 0)
        nav_layout.setSpacing(0)

        # Logo
        logo_label = QLabel()
        logo_label.setStyleSheet("background: transparent; border: none;")
        if os.path.exists(_ICON_PATH):
            pixmap = QPixmap(_ICON_PATH).scaled(
                QSize(80, 36), Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            logo_label.setPixmap(pixmap)
        else:
            logo_label.setText("Puri")
            logo_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #F5811F;")
        nav_layout.addWidget(logo_label)

        nav_layout.addSpacing(20)

        # Nav buttons
        nav_items = [
            ("สแกนรูปภาพ", 0),
            ("รายชื่อ", 1),
            ("วิธีใช้งาน", 2),
        ]
        for text, stack_idx in nav_items:
            btn = QPushButton(text)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    color: #636366;
                    border: none;
                    border-bottom: 2px solid transparent;
                    padding: 12px 16px;
                    font-size: 13px;
                    font-weight: 500;
                }
                QPushButton:checked {
                    background: #FFF3E8;
                    color: #F5811F;
                    font-weight: bold;
                    border-bottom: 2px solid #F5811F;
                }
                QPushButton:hover:!checked {
                    background: #F0F0F5;
                    color: #424245;
                }
            """)
            btn.clicked.connect(lambda checked, idx=stack_idx: self._switch_panel(idx))
            nav_layout.addWidget(btn)
            self._nav_buttons.append(btn)

        nav_layout.addStretch()

        # Version in navbar
        version_label = QLabel(f"v{APP_VERSION}")
        version_label.setStyleSheet("color: #C7C7CC; font-size: 11px; background: transparent;")
        nav_layout.addWidget(version_label)

        main_layout.addWidget(navbar)

        # ===== Stacked panels =====
        self.stack = QStackedWidget()

        self.main_panel = MainPanel(self.config)
        self.person_panel = PersonManager()
        self.help_panel = HelpPanel()

        self.stack.addWidget(self.main_panel)    # 0
        self.stack.addWidget(self.person_panel)   # 1
        self.stack.addWidget(self.help_panel)     # 2

        # Connect signals
        self.main_panel.processing_complete.connect(self._on_processing_complete)
        self.main_panel.person_changed.connect(self._on_person_changed)
        self.person_panel.person_changed.connect(self._on_person_changed)
        self.main_panel.folder_panel.folder_count_changed.connect(self._on_folder_count_changed)

        main_layout.addWidget(self.stack, 1)

        # Default: จัดการรูปภาพ
        self._switch_panel(0)

    def _switch_panel(self, index: int):
        self.stack.setCurrentIndex(index)
        for i, btn in enumerate(self._nav_buttons):
            btn.setChecked(i == index)

        if index == 0:
            self.main_panel.refresh_data()
        elif index == 1:
            self.person_panel.refresh_persons()

    def _setup_status_bar(self):
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        # Model status: green/red dot
        self.model_status = QWidget()
        model_layout = QHBoxLayout(self.model_status)
        model_layout.setContentsMargins(8, 0, 8, 0)
        model_layout.setSpacing(4)
        self._model_dot = QLabel()
        self._model_dot.setFixedSize(10, 10)
        self._model_dot.setStyleSheet(
            "background: #F5811F; border-radius: 5px;"
        )
        self._model_dot.setToolTip("โมเดล: กำลังโหลด...")
        model_layout.addWidget(self._model_dot)

        # Folder count
        self._folder_stats_label = QLabel("")
        self._folder_stats_label.setStyleSheet("color: #86868B; font-size: 11px;")

        self.db_stats_label = QLabel("")
        self.db_stats_label.setStyleSheet("color: #86868B; font-size: 11px;")

        self.status_bar.addWidget(self.model_status)
        self.status_bar.addWidget(self._folder_stats_label)
        self.status_bar.addPermanentWidget(self.db_stats_label)
        self._update_db_stats()

    def _load_model(self):
        self._model_worker = ModelLoaderWorker(self.config.face_model_name)
        self._model_worker.status_message.connect(
            lambda msg: self._model_dot.setToolTip(f"โมเดล: {msg}")
        )
        self._model_worker.finished_with_result.connect(self._on_model_loaded)
        self._model_worker.error.connect(self._on_model_error)
        self._model_worker.start()

    def _on_model_loaded(self, result):
        self._model_dot.setStyleSheet("background: #34C759; border-radius: 5px;")
        self._model_dot.setToolTip("โมเดล: พร้อมใช้งาน")

    def _on_model_error(self, message):
        self._model_dot.setStyleSheet("background: #FF3B30; border-radius: 5px;")
        self._model_dot.setToolTip(f"โมเดล: {message}")

    def _on_person_changed(self):
        self._update_db_stats()
        self.main_panel.refresh_data()

    def _on_folder_count_changed(self, count: int):
        if count > 0:
            self._folder_stats_label.setText(f"พบ {count} โฟลเดอร์")
        else:
            self._folder_stats_label.setText("")

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
