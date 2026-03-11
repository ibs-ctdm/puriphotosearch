"""Add persons from folder scan — opened from Person Manager."""

import os
from pathlib import Path

from PySide6.QtCore import Signal, Qt, QSize, QStringListModel
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QMessageBox, QScrollArea, QTreeWidget, QTreeWidgetItem,
    QGroupBox, QProgressBar, QStackedWidget, QWidget, QGridLayout,
    QCheckBox, QCompleter,
)

from app.config import AppConfig
from app.database import get_all_persons
from app.services.photo_processor import IMAGE_EXTENSIONS
from app.workers.scan_mode_worker import ScanClusterWorker, ExecuteScanWorker


class ScanModeDialog(QDialog):
    """Dialog for scanning folders and adding persons to DB."""

    person_changed = Signal()  # emitted when new persons added to DB

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self._clusters = []
        self._updating_checks = False

        self.setWindowTitle("เพิ่มจากโฟลเดอร์")
        self.resize(900, 650)
        self.setMinimumSize(700, 500)

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        title = QLabel("+ เพิ่มจากโฟลเดอร์")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #1D1D1F;")
        layout.addWidget(title)

        desc = QLabel(
            "สแกนใบหน้าในโฟลเดอร์ → จัดกลุ่มใบหน้าที่เหมือนกัน → ตั้งชื่อเพื่อเพิ่มบุคคลใหม่ลงฐานข้อมูล\n"
            "หากมีกลุ่มที่เป็นคนเดียวกัน ให้ติ๊กเลือกแล้วกด \"รวมเป็นคนเดียว\" ก่อนตั้งชื่อ"
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
        self._folder_tree.setRootIsDecorated(True)
        self._folder_tree.setItemsExpandable(True)
        self._folder_tree.setAnimated(True)
        self._folder_tree.itemChanged.connect(self._on_item_changed)
        self._folder_tree.itemExpanded.connect(self._on_item_expanded)
        self._folder_tree.itemCollapsed.connect(self._update_folder_icons)
        self._folder_tree.itemClicked.connect(self._on_item_clicked)
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

    _DUMMY_ROLE = Qt.UserRole + 10  # marker for placeholder child

    def _populate_tree(self):
        self._folder_tree.clear()
        config = AppConfig.load()
        folder = config.main_photos_folder
        if not folder or not os.path.isdir(folder):
            return

        self._updating_checks = True
        for entry in sorted(Path(folder).iterdir()):
            if entry.is_dir() and not entry.name.startswith('.'):
                item = self._make_lazy_item(entry)
                if item is not None:
                    self._folder_tree.addTopLevelItem(item)
        self._updating_checks = False

    def _make_lazy_item(self, dir_path: Path) -> QTreeWidgetItem | None:
        """Create a tree item for a folder — only scan immediate contents (fast)."""
        photo_count = 0
        has_subdirs = False
        try:
            for f in dir_path.iterdir():
                if f.name.startswith('.'):
                    continue
                if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS:
                    photo_count += 1
                elif f.is_dir():
                    has_subdirs = True
        except PermissionError:
            return None

        if photo_count == 0 and not has_subdirs:
            return None

        item = QTreeWidgetItem()
        base_text = f"{dir_path.name}    ({photo_count:,} รูป)" if photo_count else dir_path.name
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(0, Qt.Unchecked)
        item.setData(0, Qt.UserRole, str(dir_path))
        item.setData(0, Qt.UserRole + 1, base_text)

        if has_subdirs:
            # Add dummy child so the expand arrow appears
            dummy = QTreeWidgetItem()
            dummy.setData(0, self._DUMMY_ROLE, True)
            item.addChild(dummy)
            item.setText(0, f"▶  {base_text}")
        else:
            item.setText(0, base_text)

        return item

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int):
        """Single-click expands/collapses folders that have children."""
        if item.childCount() > 0:
            item.setExpanded(not item.isExpanded())

    def _on_item_expanded(self, item: QTreeWidgetItem):
        """Lazy-load: replace dummy child with real sub-folder items on first expand."""
        # Check if first child is the dummy placeholder
        if item.childCount() == 1 and item.child(0).data(0, self._DUMMY_ROLE):
            item.takeChildren()  # remove dummy
            dir_path = Path(item.data(0, Qt.UserRole))
            self._updating_checks = True
            parent_checked = item.checkState(0) == Qt.Checked
            for entry in sorted(dir_path.iterdir()):
                if entry.is_dir() and not entry.name.startswith('.'):
                    child = self._make_lazy_item(entry)
                    if child is not None:
                        if parent_checked:
                            child.setCheckState(0, Qt.Checked)
                        item.addChild(child)
            self._updating_checks = False

            # If no real children were added, item has no expand arrow
            if item.childCount() == 0:
                base_text = item.data(0, Qt.UserRole + 1)
                item.setText(0, base_text or item.text(0))
                return

        self._update_folder_icons(item)

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
            if child.data(0, self._DUMMY_ROLE):
                continue  # skip placeholder
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

    def _update_folder_icons(self, item: QTreeWidgetItem):
        base_text = item.data(0, Qt.UserRole + 1)
        if base_text and item.childCount() > 0:
            if item.isExpanded():
                item.setText(0, f"▼  {base_text}")
            else:
                item.setText(0, f"▶  {base_text}")

    def _get_checked_folders(self) -> list[str]:
        result = []
        for i in range(self._folder_tree.topLevelItemCount()):
            self._collect_checked(self._folder_tree.topLevelItem(i), result)
        return result

    def _collect_checked(self, item, result):
        if item.data(0, self._DUMMY_ROLE):
            return  # skip placeholder
        if item.checkState(0) == Qt.Checked:
            path = item.data(0, Qt.UserRole)
            if path:
                dir_p = Path(path)
                # Add this folder if it has photos
                photo_count = sum(
                    1 for f in dir_p.iterdir()
                    if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS
                )
                if photo_count > 0:
                    result.append(path)
                # If children not yet loaded (has dummy), scan subdirs recursively
                has_dummy = (
                    item.childCount() == 1
                    and item.child(0).data(0, self._DUMMY_ROLE)
                )
                if has_dummy:
                    self._collect_subdirs_recursive(dir_p, result)
                    return
        for i in range(item.childCount()):
            self._collect_checked(item.child(i), result)

    def _collect_subdirs_recursive(self, dir_path: Path, result: list):
        """Collect all photo-containing subdirectories (for unexpanded checked folders)."""
        try:
            for entry in sorted(dir_path.iterdir()):
                if entry.is_dir() and not entry.name.startswith('.'):
                    photo_count = sum(
                        1 for f in entry.iterdir()
                        if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS
                    )
                    if photo_count > 0:
                        result.append(str(entry))
                    self._collect_subdirs_recursive(entry, result)
        except PermissionError:
            pass

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

    # ── Step 3: Results — 2-column grid with merge ────────────

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
        scroll.setStyleSheet("QScrollArea { border: none; }")

        self._cards_container = QWidget()
        self._cards_layout = QGridLayout(self._cards_container)
        self._cards_layout.setSpacing(10)
        self._cards_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        scroll.setWidget(self._cards_container)
        lay.addWidget(scroll, stretch=1)

        # Bottom buttons
        btn_row = QHBoxLayout()

        back_btn = QPushButton("← กลับ")
        back_btn.clicked.connect(self._go_back)
        btn_row.addWidget(back_btn)

        btn_row.addStretch()

        self._merge_btn = QPushButton("รวมเป็นคนเดียว")
        self._merge_btn.setEnabled(False)
        self._merge_btn.setStyleSheet(
            "QPushButton { background: #007AFF; color: white;"
            "padding: 10px 20px; border-radius: 8px;"
            "font-weight: bold; font-size: 13px; border: none; }"
            "QPushButton:hover { background: #0056CC; }"
            "QPushButton:disabled { background: #C7C7CC; }"
        )
        self._merge_btn.clicked.connect(self._merge_selected)
        btn_row.addWidget(self._merge_btn)

        self._execute_btn = QPushButton("เพิ่ม")
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
        self._update_summary()
        self._build_cluster_cards()
        self._stack.setCurrentIndex(2)

    def _update_summary(self):
        total_faces = sum(len(c["faces"]) for c in self._clusters)
        known = sum(1 for c in self._clusters if c["is_known"])
        unknown = len(self._clusters) - known
        self._result_summary.setText(
            f"พบ {len(self._clusters):,} กลุ่ม จาก {total_faces:,} ใบหน้า  "
            f"({known:,} คนในฐานข้อมูล, {unknown:,} คนใหม่)"
        )

    def _build_cluster_cards(self):
        # Clear old cards
        while self._cards_layout.count():
            item = self._cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._name_inputs = []
        self._merge_checkboxes = []

        # Load existing person names for autocomplete
        try:
            persons = get_all_persons()
            self._person_names = [p["name"] for p in persons]
        except Exception:
            self._person_names = []

        for i, cluster in enumerate(self._clusters):
            card = self._make_cluster_card(i, cluster)
            self._cards_layout.addWidget(card, i // 2, i % 2)

        self._update_merge_btn()

    def _make_cluster_card(self, index: int, cluster: dict) -> QWidget:
        card = QWidget()
        card.setStyleSheet(
            "QWidget#clusterCard { border: 1px solid #D2D2D7;"
            "border-radius: 10px; background: white; }"
        )
        card.setObjectName("clusterCard")

        col = QVBoxLayout(card)
        col.setContentsMargins(10, 8, 10, 8)
        col.setSpacing(6)

        # Top row: thumbnail + checkbox
        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        # Thumbnail
        thumb_label = QLabel()
        thumb_label.setFixedSize(80, 80)
        thumb_label.setAlignment(Qt.AlignCenter)
        thumb_label.setStyleSheet(
            "border: 1px solid #E8E8ED; border-radius: 8px; background: #F5F5F7;"
        )
        thumb_data = cluster.get("thumbnail")
        if thumb_data:
            img = QImage.fromData(thumb_data)
            if not img.isNull():
                px = QPixmap.fromImage(img).scaled(
                    QSize(80, 80), Qt.KeepAspectRatio, Qt.SmoothTransformation,
                )
                thumb_label.setPixmap(px)
        top_row.addWidget(thumb_label)

        # Info beside thumbnail
        info_col = QVBoxLayout()
        info_col.setSpacing(3)

        photo_count = len({f["photo_path"] for f in cluster["faces"]})
        count_label = QLabel(f"พบ {photo_count:,} รูป")
        count_label.setStyleSheet("font-size: 12px; color: #424245; font-weight: bold; border: none;")
        info_col.addWidget(count_label)

        if cluster["is_known"]:
            badge = QLabel("มีในฐานข้อมูล")
            badge.setStyleSheet(
                "color: white; background: #34C759; padding: 2px 8px;"
                "border-radius: 4px; font-size: 11px; font-weight: bold;"
            )
            badge.setFixedWidth(90)
            info_col.addWidget(badge)

        info_col.addStretch()

        # Merge checkbox at bottom-right of info area
        merge_cb = QCheckBox("เลือก")
        merge_cb.setStyleSheet("font-size: 11px; color: #86868B; border: none;")
        merge_cb.stateChanged.connect(lambda: self._update_merge_btn())
        info_col.addWidget(merge_cb)
        self._merge_checkboxes.append((merge_cb, index))

        top_row.addLayout(info_col, stretch=1)
        col.addLayout(top_row)

        # Name input row with autocomplete
        name_input = QLineEdit()
        name_input.setPlaceholderText("พิมพ์ชื่อหรือเลือกจากรายการ")
        name_input.setStyleSheet(
            "padding: 5px 8px; border: 1px solid #D2D2D7;"
            "border-radius: 6px; font-size: 12px;"
        )
        if cluster.get("person_name"):
            name_input.setText(cluster["person_name"])

        # Autocomplete from existing persons
        if self._person_names:
            completer = QCompleter(self._person_names, name_input)
            completer.setCaseSensitivity(Qt.CaseInsensitive)
            completer.setFilterMode(Qt.MatchContains)
            completer.setCompletionMode(QCompleter.PopupCompletion)
            completer.popup().setStyleSheet(
                "QListView { border: 1px solid #D2D2D7; border-radius: 6px;"
                "background: white; font-size: 12px; padding: 2px; }"
                "QListView::item { padding: 4px 8px; }"
                "QListView::item:selected { background: #FFF3E8; color: #1D1D1F; }"
            )
            name_input.setCompleter(completer)

        col.addWidget(name_input)

        self._name_inputs.append((name_input, cluster))
        return card

    # ── Merge ─────────────────────────────────────────────────

    def _update_merge_btn(self):
        checked = sum(1 for cb, _ in self._merge_checkboxes if cb.isChecked())
        self._merge_btn.setEnabled(checked >= 2)
        if checked >= 2:
            self._merge_btn.setText(f"รวม {checked:,} กลุ่มเป็นคนเดียว")
        else:
            self._merge_btn.setText("รวมเป็นคนเดียว")

    def _merge_selected(self):
        selected_indices = [idx for cb, idx in self._merge_checkboxes if cb.isChecked()]
        if len(selected_indices) < 2:
            return

        # Merge into the first selected cluster
        base_cluster = self._clusters[selected_indices[0]]
        for idx in selected_indices[1:]:
            other = self._clusters[idx]
            base_cluster["faces"].extend(other["faces"])
            # Keep thumbnail from first cluster
            if not base_cluster.get("thumbnail") and other.get("thumbnail"):
                base_cluster["thumbnail"] = other["thumbnail"]
            # If any cluster is known, the merged one is also known
            if other["is_known"]:
                base_cluster["is_known"] = True
                if other.get("person_id"):
                    base_cluster["person_id"] = other["person_id"]
                if other.get("person_name") and not base_cluster.get("person_name"):
                    base_cluster["person_name"] = other["person_name"]

        # Remove merged clusters (in reverse order to preserve indices)
        for idx in sorted(selected_indices[1:], reverse=True):
            self._clusters.pop(idx)

        # Rebuild
        self._update_summary()
        self._build_cluster_cards()

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
                "กรุณาตั้งชื่ออย่างน้อย 1 คนก่อนเพิ่ม",
            )
            return

        self._execute_btn.setEnabled(False)
        self._execute_btn.setText("กำลังเพิ่ม...")

        self._worker = ExecuteScanWorker(named, skip_file_organize=True)
        self._worker.status_message.connect(self._on_scan_status)
        self._worker.progress.connect(self._on_exec_progress)
        self._worker.finished_with_result.connect(self._on_exec_done)
        self._worker.error.connect(self._on_exec_error)
        self._worker.start()

    def _on_exec_progress(self, current: int, total: int, msg: str):
        self._execute_btn.setText(f"กำลังเพิ่ม... ({current:,}/{total:,})")

    def _on_exec_done(self, result: dict):
        self._execute_btn.setEnabled(True)
        self._execute_btn.setText("เพิ่ม")

        added = result.get("persons_added", 0)
        total = result.get("total_processed", 0)

        QMessageBox.information(
            self, "เสร็จสิ้น",
            f"เพิ่มบุคคลใหม่ {added:,} คน จากทั้งหมด {total:,} คน",
        )

        if added > 0:
            self.person_changed.emit()

    def _on_exec_error(self, msg: str):
        self._execute_btn.setEnabled(True)
        self._execute_btn.setText("เพิ่ม")
        QMessageBox.warning(self, "ข้อผิดพลาด", msg)
