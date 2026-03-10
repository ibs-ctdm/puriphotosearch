"""Scan-first-Name-later mode dialog — opened from Person Manager."""

import os
from pathlib import Path

from PySide6.QtCore import Signal, Qt, QSize
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QMessageBox, QScrollArea, QTreeWidget, QTreeWidgetItem,
    QGroupBox, QProgressBar, QStackedWidget, QWidget,
)

from app.config import AppConfig
from app.services.photo_processor import IMAGE_EXTENSIONS
from app.workers.scan_mode_worker import ScanClusterWorker, ExecuteScanWorker


class ScanModeDialog(QDialog):
    """Dialog for Scan-first-Name-later workflow."""

    person_changed = Signal()  # emitted when new persons added to DB

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self._clusters = []
        self._updating_checks = False

        self.setWindowTitle("โหมดสแกนและตั้งชื่อ")
        self.resize(900, 650)
        self.setMinimumSize(700, 500)

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        title = QLabel("โหมดสแกนและตั้งชื่อ")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #1D1D1F;")
        layout.addWidget(title)

        desc = QLabel(
            "สแกนใบหน้าในโฟลเดอร์ก่อน แล้วตั้งชื่อบุคคลทีหลัง "
            "ระบบจะจัดกลุ่มใบหน้าที่เหมือนกัน และจำคนที่มีในฐานข้อมูลให้อัตโนมัติ\n"
            "หากตั้งชื่อเดียวกันให้หลายกลุ่ม ระบบจะรวมเป็นบุคคลเดียวกัน"
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #86868B;")
        layout.addWidget(desc)

        # Stacked widget for 3 steps
        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_step1())  # 0: select folders
        self._stack.addWidget(self._build_step2())  # 1: scanning
        self._stack.addWidget(self._build_step3())  # 2: results
        layout.addWidget(self._stack, stretch=1)

    # ── Step 1: Select folders from tree ───────────────────────

    def _build_step1(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 6, 0, 0)
        lay.setSpacing(8)

        group = QGroupBox("เลือกโฟลเดอร์ที่จะสแกน")
        glayout = QVBoxLayout(group)

        self._folder_tree = QTreeWidget()
        self._folder_tree.setHeaderHidden(True)
        self._folder_tree.setSelectionMode(QTreeWidget.NoSelection)
        self._folder_tree.itemChanged.connect(self._on_item_changed)
        glayout.addWidget(self._folder_tree)

        # Select/deselect buttons
        btn_row = QHBoxLayout()
        select_all = QPushButton("เลือกทั้งหมด")
        select_all.clicked.connect(self._select_all)
        deselect_all = QPushButton("ยกเลิกทั้งหมด")
        deselect_all.clicked.connect(self._deselect_all)
        btn_row.addWidget(select_all)
        btn_row.addWidget(deselect_all)
        btn_row.addStretch()
        glayout.addLayout(btn_row)

        lay.addWidget(group, stretch=1)

        # Scan button
        scan_row = QHBoxLayout()
        scan_row.addStretch()
        self._scan_btn = QPushButton("เริ่มสแกน")
        self._scan_btn.setStyleSheet(
            "QPushButton { background: #F5811F; color: white;"
            "padding: 10px 28px; border-radius: 8px;"
            "font-weight: bold; font-size: 14px; border: none; }"
            "QPushButton:hover { background: #E0710A; }"
            "QPushButton:disabled { background: #C7C7CC; }"
        )
        self._scan_btn.clicked.connect(self._start_scan)
        scan_row.addWidget(self._scan_btn)
        lay.addLayout(scan_row)

        # Populate tree
        self._populate_tree()

        return w

    def _populate_tree(self):
        self._folder_tree.clear()
        config = AppConfig.load()
        folder = config.main_photos_folder
        if not folder or not os.path.isdir(folder):
            return

        self._updating_checks = True
        for entry in sorted(Path(folder).iterdir()):
            if entry.is_dir() and not entry.name.startswith('.'):
                item = self._build_tree_item(entry)
                if item is not None:
                    self._folder_tree.addTopLevelItem(item)
        self._folder_tree.expandAll()
        self._updating_checks = False

    def _build_tree_item(self, dir_path: Path) -> QTreeWidgetItem | None:
        photo_count = sum(
            1 for f in dir_path.iterdir()
            if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS
        )
        children = []
        for entry in sorted(dir_path.iterdir()):
            if entry.is_dir() and not entry.name.startswith('.'):
                child = self._build_tree_item(entry)
                if child is not None:
                    children.append(child)
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

    def _on_item_changed(self, item, column):
        if self._updating_checks:
            return
        self._updating_checks = True
        state = item.checkState(0)
        self._set_children_check_state(item, state)
        self._updating_checks = False

    def _set_children_check_state(self, item, state):
        for i in range(item.childCount()):
            child = item.child(i)
            child.setCheckState(0, state)
            self._set_children_check_state(child, state)

    def _select_all(self):
        self._updating_checks = True
        for i in range(self._folder_tree.topLevelItemCount()):
            item = self._folder_tree.topLevelItem(i)
            item.setCheckState(0, Qt.Checked)
            self._set_children_check_state(item, Qt.Checked)
        self._updating_checks = False

    def _deselect_all(self):
        self._updating_checks = True
        for i in range(self._folder_tree.topLevelItemCount()):
            item = self._folder_tree.topLevelItem(i)
            item.setCheckState(0, Qt.Unchecked)
            self._set_children_check_state(item, Qt.Unchecked)
        self._updating_checks = False

    def _get_checked_folders(self) -> list[str]:
        """Return list of checked folder paths that contain photos."""
        result = []
        for i in range(self._folder_tree.topLevelItemCount()):
            self._collect_checked(self._folder_tree.topLevelItem(i), result)
        return result

    def _collect_checked(self, item, result):
        if item.checkState(0) == Qt.Checked:
            path = item.data(0, Qt.UserRole)
            photo_count = sum(
                1 for f in Path(path).iterdir()
                if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS
            )
            if photo_count > 0:
                result.append(path)
        for i in range(item.childCount()):
            self._collect_checked(item.child(i), result)

    # ── Step 2: Scanning progress ─────────────────────────────

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

    # ── Step 3: Results card list ─────────────────────────────

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

    # ── Actions ───────────────────────────────────────────────

    def _start_scan(self):
        folders = self._get_checked_folders()
        if not folders:
            QMessageBox.information(
                self, "แจ้งเตือน",
                "กรุณาเลือกโฟลเดอร์ที่มีรูปภาพอย่างน้อย 1 โฟลเดอร์",
            )
            return

        config = AppConfig.load()
        threshold = config.similarity_threshold

        self._stack.setCurrentIndex(1)
        self._scan_progress.setValue(0)
        self._scan_detail.setText("")

        self._worker = ScanClusterWorker(folders, threshold)
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
            f"พบ {len(self._clusters)} คน จาก {total_faces} ใบหน้า "
            f"ใน {total_photos} รูป  "
            f"({known} คนในฐานข้อมูล, {unknown} คนใหม่)"
        )

        self._build_cluster_cards()
        self._stack.setCurrentIndex(2)

    def _build_cluster_cards(self):
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
        count_label = QLabel(f"พบ {photo_count} รูป")
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

    # ── Execute ───────────────────────────────────────────────

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

        self._worker = ExecuteScanWorker(named)
        self._worker.status_message.connect(self._on_scan_status)
        self._worker.progress.connect(self._on_exec_progress)
        self._worker.finished_with_result.connect(self._on_exec_done)
        self._worker.error.connect(self._on_exec_error)
        self._worker.start()

    def _on_exec_progress(self, current: int, total: int, msg: str):
        self._execute_btn.setText(f"กำลังดำเนินการ... ({current}/{total})")

    def _on_exec_done(self, result: dict):
        self._execute_btn.setEnabled(True)
        self._execute_btn.setText("ดำเนินการ")

        added = result.get("persons_added", 0)
        copied = result.get("photos_copied", 0)
        total = result.get("total_processed", 0)

        QMessageBox.information(
            self, "เสร็จสิ้น",
            f"ดำเนินการ {total} คนเสร็จแล้ว\n"
            f"คัดลอกรูป: {copied} รูป\n"
            f"เพิ่มบุคคลใหม่: {added} คน",
        )

        if added > 0:
            self.person_changed.emit()

    def _on_exec_error(self, msg: str):
        self._execute_btn.setEnabled(True)
        self._execute_btn.setText("ดำเนินการ")
        QMessageBox.warning(self, "ข้อผิดพลาด", msg)
