"""Panel 5: Scan-first-Name-later mode."""

import os

from PySide6.QtCore import Signal, Qt, QSize
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QFileDialog, QMessageBox, QScrollArea,
    QGroupBox, QProgressBar, QStackedWidget,
)

from app.config import AppConfig
from app.workers.scan_mode_worker import ScanClusterWorker, ExecuteScanWorker


class ScanModePanel(QWidget):
    """Panel for Scan-first-Name-later workflow."""

    person_changed = Signal()  # emitted when new persons added to DB

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self._clusters = []
        self._folder_path = ""
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 15, 10, 10)
        layout.setSpacing(10)

        title = QLabel("สแกนและตั้งชื่อ")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #1D1D1F;")
        layout.addWidget(title)

        desc = QLabel(
            "สแกนใบหน้าในโฟลเดอร์ก่อน แล้วตั้งชื่อบุคคลทีหลัง "
            "ระบบจะจัดกลุ่มใบหน้าที่เหมือนกัน และจำคนที่มีในฐานข้อมูลให้อัตโนมัติ"
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #86868B;")
        layout.addWidget(desc)

        # Stacked widget for 3 steps
        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_step1())  # 0: select folder
        self._stack.addWidget(self._build_step2())  # 1: scanning
        self._stack.addWidget(self._build_step3())  # 2: results
        layout.addWidget(self._stack, stretch=1)

    # ── Step 1: Select folder ────────────────────────────────────

    def _build_step1(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 10, 0, 0)

        group = QGroupBox("เลือกโฟลเดอร์ที่จะสแกน")
        glayout = QVBoxLayout(group)

        row = QHBoxLayout()
        self._folder_input = QLineEdit()
        self._folder_input.setReadOnly(True)
        self._folder_input.setPlaceholderText("กดปุ่ม เรียกดู เพื่อเลือกโฟลเดอร์...")
        browse_btn = QPushButton("เรียกดู...")
        browse_btn.setFixedWidth(100)
        browse_btn.clicked.connect(self._browse_folder)
        row.addWidget(self._folder_input)
        row.addWidget(browse_btn)
        glayout.addLayout(row)

        self._scan_btn = QPushButton("เริ่มสแกน")
        self._scan_btn.setStyleSheet(
            "QPushButton { background: #F5811F; color: white;"
            "padding: 10px 24px; border-radius: 8px;"
            "font-weight: bold; font-size: 14px; border: none; }"
            "QPushButton:hover { background: #E0710A; }"
            "QPushButton:disabled { background: #C7C7CC; }"
        )
        self._scan_btn.setEnabled(False)
        self._scan_btn.clicked.connect(self._start_scan)
        glayout.addWidget(self._scan_btn, alignment=Qt.AlignLeft)

        lay.addWidget(group)
        lay.addStretch()
        return w

    # ── Step 2: Scanning progress ────────────────────────────────

    def _build_step2(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 30, 0, 0)

        self._scan_status = QLabel("กำลังสแกน...")
        self._scan_status.setStyleSheet(
            "font-size: 16px; font-weight: bold; color: #1D1D1F;"
        )
        lay.addWidget(self._scan_status)

        self._scan_progress = QProgressBar()
        self._scan_progress.setRange(0, 100)
        lay.addWidget(self._scan_progress)

        self._scan_detail = QLabel("")
        self._scan_detail.setStyleSheet("color: #86868B;")
        lay.addWidget(self._scan_detail)

        cancel_btn = QPushButton("ยกเลิก")
        cancel_btn.clicked.connect(self._cancel_scan)
        lay.addWidget(cancel_btn, alignment=Qt.AlignLeft)

        lay.addStretch()
        return w

    # ── Step 3: Results card list ────────────────────────────────

    def _build_step3(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        self._result_summary = QLabel("")
        self._result_summary.setStyleSheet(
            "font-size: 14px; font-weight: bold; color: #1D1D1F;"
        )
        lay.addWidget(self._result_summary)

        # Scroll area for cluster cards
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self._cards_container = QWidget()
        self._cards_layout = QVBoxLayout(self._cards_container)
        self._cards_layout.setSpacing(8)
        self._cards_layout.setAlignment(Qt.AlignTop)

        scroll.setWidget(self._cards_container)
        lay.addWidget(scroll, stretch=1)

        # Bottom buttons
        btn_row = QHBoxLayout()

        back_btn = QPushButton("← สแกนใหม่")
        back_btn.clicked.connect(self._go_back)
        btn_row.addWidget(back_btn)

        btn_row.addStretch()

        self._execute_btn = QPushButton("ดำเนินการ")
        self._execute_btn.setStyleSheet(
            "QPushButton { background: #F5811F; color: white;"
            "padding: 10px 28px; border-radius: 8px;"
            "font-weight: bold; font-size: 14px; border: none; }"
            "QPushButton:hover { background: #E0710A; }"
            "QPushButton:disabled { background: #C7C7CC; }"
        )
        self._execute_btn.clicked.connect(self._execute)
        btn_row.addWidget(self._execute_btn)

        lay.addLayout(btn_row)
        return w

    # ── Actions ──────────────────────────────────────────────────

    def _browse_folder(self):
        config = AppConfig.load()
        start = config.main_photos_folder or os.path.expanduser("~")
        folder = QFileDialog.getExistingDirectory(
            self, "เลือกโฟลเดอร์ที่จะสแกน", start,
        )
        if folder:
            self._folder_input.setText(folder)
            self._folder_path = folder
            self._scan_btn.setEnabled(True)

    def _start_scan(self):
        if not self._folder_path:
            return

        config = AppConfig.load()
        threshold = config.similarity_threshold

        self._stack.setCurrentIndex(1)
        self._scan_progress.setValue(0)
        self._scan_detail.setText("")

        self._worker = ScanClusterWorker(self._folder_path, threshold)
        self._worker.status_message.connect(self._on_scan_status)
        self._worker.progress.connect(self._on_scan_progress)
        self._worker.finished_with_result.connect(self._on_scan_done)
        self._worker.error.connect(self._on_scan_error)
        self._worker.start()

    def _cancel_scan(self):
        if self._worker:
            self._worker.cancel()
        self._stack.setCurrentIndex(0)

    def _go_back(self):
        self._stack.setCurrentIndex(0)

    def _on_scan_status(self, msg: str):
        self._scan_status.setText(msg)

    def _on_scan_progress(self, current: int, total: int, msg: str):
        pct = int(current / max(total, 1) * 100)
        self._scan_progress.setValue(pct)
        self._scan_detail.setText(msg)

    def _on_scan_error(self, msg: str):
        QMessageBox.warning(self, "ข้อผิดพลาด", msg)
        self._stack.setCurrentIndex(0)

    def _on_scan_done(self, result: dict):
        self._clusters = result.get("clusters", [])
        total_photos = result.get("total_photos", 0)
        total_faces = result.get("total_faces", 0)
        known = sum(1 for c in self._clusters if c["is_known"])
        unknown = len(self._clusters) - known

        self._result_summary.setText(
            f"พบ {len(self._clusters):,} คน จาก {total_faces:,} ใบหน้า "
            f"ใน {total_photos:,} รูป  "
            f"({known:,} คนในฐานข้อมูล, {unknown:,} คนใหม่)"
        )

        self._build_cluster_cards()
        self._stack.setCurrentIndex(2)

    def _build_cluster_cards(self):
        # Clear existing
        while self._cards_layout.count():
            item = self._cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._name_inputs = []

        for i, cluster in enumerate(self._clusters):
            card = self._make_cluster_card(i, cluster)
            self._cards_layout.addWidget(card)

    def _make_cluster_card(self, index: int, cluster: dict) -> QWidget:
        card = QWidget()
        card.setStyleSheet(
            "QWidget#clusterCard { border: 1px solid #D2D2D7;"
            "border-radius: 10px; background: white; }"
        )
        card.setObjectName("clusterCard")

        row = QHBoxLayout(card)
        row.setContentsMargins(10, 8, 10, 8)
        row.setSpacing(12)

        # Thumbnail
        thumb_label = QLabel()
        thumb_label.setFixedSize(100, 100)
        thumb_label.setAlignment(Qt.AlignCenter)
        thumb_label.setStyleSheet(
            "border: 1px solid #E8E8ED; border-radius: 8px; background: #F5F5F7;"
        )
        thumb_data = cluster.get("thumbnail")
        if thumb_data:
            img = QImage.fromData(thumb_data)
            if not img.isNull():
                px = QPixmap.fromImage(img).scaled(
                    QSize(100, 100), Qt.KeepAspectRatio, Qt.SmoothTransformation,
                )
                thumb_label.setPixmap(px)
        row.addWidget(thumb_label)

        # Info + name input
        info_col = QVBoxLayout()
        info_col.setSpacing(4)

        photo_count = len({f["photo_path"] for f in cluster["faces"]})
        count_label = QLabel(f"พบ {photo_count:,} รูป")
        count_label.setStyleSheet("font-size: 13px; color: #424245; font-weight: bold;")
        info_col.addWidget(count_label)

        if cluster["is_known"]:
            badge = QLabel("มีในฐานข้อมูล")
            badge.setStyleSheet(
                "color: white; background: #34C759; padding: 2px 8px;"
                "border-radius: 4px; font-size: 11px; font-weight: bold;"
            )
            badge.setFixedWidth(90)
            info_col.addWidget(badge)

        name_row = QHBoxLayout()
        name_label = QLabel("ชื่อ:")
        name_label.setStyleSheet("font-size: 13px; color: #424245;")
        name_label.setFixedWidth(30)
        name_row.addWidget(name_label)

        name_input = QLineEdit()
        name_input.setPlaceholderText("ไม่ตั้งชื่อ = ข้าม")
        name_input.setStyleSheet(
            "padding: 6px 10px; border: 1px solid #D2D2D7;"
            "border-radius: 6px; font-size: 13px;"
        )
        if cluster.get("person_name"):
            name_input.setText(cluster["person_name"])
        name_row.addWidget(name_input)

        info_col.addLayout(name_row)
        info_col.addStretch()

        row.addLayout(info_col, stretch=1)

        self._name_inputs.append((name_input, cluster))
        return card

    # ── Execute ──────────────────────────────────────────────────

    def _execute(self):
        named = []
        for name_input, cluster in self._name_inputs:
            name = name_input.text().strip()
            if name:
                named.append({"name": name, "cluster": cluster})

        if not named:
            QMessageBox.information(
                self, "แจ้งเตือน",
                "กรุณาตั้งชื่ออย่างน้อย 1 คนก่อนดำเนินการ",
            )
            return

        self._execute_btn.setEnabled(False)
        self._execute_btn.setText("กำลังดำเนินการ...")

        self._worker = ExecuteScanWorker(named, self._folder_path)
        self._worker.status_message.connect(self._on_scan_status)
        self._worker.progress.connect(self._on_exec_progress)
        self._worker.finished_with_result.connect(self._on_exec_done)
        self._worker.error.connect(self._on_exec_error)
        self._worker.start()

    def _on_exec_progress(self, current: int, total: int, msg: str):
        self._execute_btn.setText(f"กำลังดำเนินการ... ({current:,}/{total:,})")

    def _on_exec_done(self, result: dict):
        self._execute_btn.setEnabled(True)
        self._execute_btn.setText("ดำเนินการ")

        added = result.get("persons_added", 0)
        copied = result.get("photos_copied", 0)
        total = result.get("total_processed", 0)

        QMessageBox.information(
            self, "เสร็จสิ้น",
            f"ดำเนินการ {total:,} คนเสร็จแล้ว\n"
            f"คัดลอกรูป: {copied:,} รูป\n"
            f"เพิ่มบุคคลใหม่: {added:,} คน",
        )

        if added > 0:
            self.person_changed.emit()

    def _on_exec_error(self, msg: str):
        self._execute_btn.setEnabled(True)
        self._execute_btn.setText("ดำเนินการ")
        QMessageBox.warning(self, "ข้อผิดพลาด", msg)
