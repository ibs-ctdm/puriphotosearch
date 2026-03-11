"""Settings/preferences dialog."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox,
    QDoubleSpinBox, QPushButton, QGroupBox, QFormLayout,
    QMessageBox,
)

from app.config import DB_PATH
from app.database import get_db_stats


class SettingsDialog(QDialog):
    """Settings dialog for configuring app preferences."""

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("ตั้งค่า")
        self.setMinimumWidth(450)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Face Recognition settings
        face_group = QGroupBox("การจดจำใบหน้า")
        face_layout = QFormLayout(face_group)

        self.threshold_spin = QDoubleSpinBox()
        self.threshold_spin.setRange(0.20, 0.90)
        self.threshold_spin.setSingleStep(0.05)
        self.threshold_spin.setValue(self.config.similarity_threshold)
        face_layout.addRow("ค่าความคล้าย:", self.threshold_spin)

        self.max_dim_spin = QSpinBox()
        self.max_dim_spin.setRange(640, 4096)
        self.max_dim_spin.setSingleStep(320)
        self.max_dim_spin.setValue(self.config.max_image_dim)
        face_layout.addRow("ขนาดรูปสูงสุด:", self.max_dim_spin)

        self.workers_spin = QSpinBox()
        self.workers_spin.setRange(1, 16)
        self.workers_spin.setValue(self.config.face_workers)
        face_layout.addRow("จำนวนเธรด:", self.workers_spin)

        layout.addWidget(face_group)

        # Display settings
        display_group = QGroupBox("การแสดงผล")
        display_layout = QFormLayout(display_group)

        self.thumb_spin = QSpinBox()
        self.thumb_spin.setRange(100, 400)
        self.thumb_spin.setSingleStep(50)
        self.thumb_spin.setValue(self.config.thumbnail_size)
        display_layout.addRow("ขนาดรูปย่อ:", self.thumb_spin)

        layout.addWidget(display_group)

        # Database info
        db_group = QGroupBox("ฐานข้อมูล")
        db_layout = QVBoxLayout(db_group)

        db_path_label = QLabel(f"ที่อยู่: {DB_PATH}")
        db_path_label.setStyleSheet("color: #86868B; font-size: 11px;")
        db_path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        db_layout.addWidget(db_path_label)

        stats = get_db_stats()
        stats_label = QLabel(
            f"บุคคล: {stats['persons']:,}  |  กิจกรรม: {stats['events']:,}  |  "
            f"รูปภาพ: {stats['photos']:,}  |  ใบหน้า: {stats['faces']:,}"
        )
        db_layout.addWidget(stats_label)

        layout.addWidget(db_group)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("ยกเลิก")
        cancel_btn.clicked.connect(self.reject)

        save_btn = QPushButton("บันทึก")
        save_btn.setStyleSheet("""
            QPushButton {
                background: #F5811F; color: white;
                padding: 8px 24px; border-radius: 8px;
                font-weight: bold; border: none;
            }
            QPushButton:hover { background: #E0710A; }
        """)
        save_btn.clicked.connect(self._save)

        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(save_btn)
        layout.addLayout(btn_layout)

    def _save(self):
        self.config.similarity_threshold = self.threshold_spin.value()
        self.config.max_image_dim = self.max_dim_spin.value()
        self.config.face_workers = self.workers_spin.value()
        self.config.thumbnail_size = self.thumb_spin.value()
        self.config.save()
        self.accept()
