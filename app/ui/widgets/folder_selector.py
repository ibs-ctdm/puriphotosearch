"""Folder selection + face processing panel (left side of MainPanel)."""

import os
import subprocess
import tempfile
from pathlib import Path

from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QPainter, QPixmap, QColor, QPainterPath
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QFileDialog, QTreeWidget, QTreeWidgetItem,
    QHeaderView, QProgressBar, QMessageBox, QStyle,
)

from app.database import add_or_get_event_folder, get_all_event_folders, reset_event_folder
from app.services.photo_processor import PhotoProcessor, IMAGE_EXTENSIONS
from app.workers.process_worker import ProcessWorker


class FolderSelector(QWidget):
    """Panel for selecting folders, viewing status, and processing faces."""

    folder_changed = Signal(str)
    processing_complete = Signal()
    folder_count_changed = Signal(int)

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self._updating_checks = False
        self._worker = None
        self._folders_to_process = []
        self._current_folder_idx = 0
        self._processing_cancelled = False
        self._setup_ui()

        if self.config.main_photos_folder and os.path.isdir(self.config.main_photos_folder):
            self.folder_input.setText(self.config.main_photos_folder)
            self._scan_subfolders()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 8, 5, 5)
        layout.setSpacing(6)

        # Folder picker (no GroupBox wrapper)
        folder_row = QHBoxLayout()
        folder_row.setSpacing(4)
        self.folder_input = QLineEdit()
        self.folder_input.setReadOnly(True)
        self.folder_input.setPlaceholderText("เลือกโฟลเดอร์...")
        self.browse_btn = QPushButton("เลือก...")
        self.browse_btn.setFixedWidth(80)
        self.browse_btn.clicked.connect(self._browse_folder)
        folder_row.addWidget(self.folder_input)
        folder_row.addWidget(self.browse_btn)
        layout.addLayout(folder_row)

        # Subfolder tree (4 columns: Folder, Open, Photos, Faces)
        self.subfolder_tree = QTreeWidget()
        self.subfolder_tree.setColumnCount(4)
        self.subfolder_tree.setHeaderLabels(["             โฟลเดอร์", "", "รูป", "หน้า"])
        self.subfolder_tree.header().setStretchLastSection(False)
        self.subfolder_tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.subfolder_tree.header().setSectionResizeMode(1, QHeaderView.Fixed)
        self.subfolder_tree.header().setSectionResizeMode(2, QHeaderView.Fixed)
        self.subfolder_tree.header().setSectionResizeMode(3, QHeaderView.Fixed)
        self.subfolder_tree.header().resizeSection(1, 30)
        self.subfolder_tree.header().resizeSection(2, 45)
        self.subfolder_tree.header().resizeSection(3, 45)
        self.subfolder_tree.setSelectionMode(QTreeWidget.NoSelection)
        self.subfolder_tree.setEditTriggers(QTreeWidget.NoEditTriggers)
        self.subfolder_tree.setRootIsDecorated(True)
        self.subfolder_tree.setItemsExpandable(True)
        self.subfolder_tree.setAnimated(True)
        self.subfolder_tree.setIndentation(22)
        self.subfolder_tree.itemChanged.connect(self._on_item_changed)
        self.subfolder_tree.itemExpanded.connect(self._update_folder_icons)
        self.subfolder_tree.itemCollapsed.connect(self._update_folder_icons)
        self.subfolder_tree.itemDoubleClicked.connect(self._open_folder_in_finder)
        self.subfolder_tree.itemClicked.connect(self._on_tree_item_clicked)

        # Custom orange branch indicators
        arrow_dir = os.path.join(tempfile.gettempdir(), "puri_arrows")
        os.makedirs(arrow_dir, exist_ok=True)
        for fname, pts in [("closed.png", [(4, 1), (11, 6), (4, 11)]),
                           ("open.png", [(1, 4), (11, 4), (6, 11)])]:
            px = QPixmap(12, 12)
            px.fill(Qt.transparent)
            p = QPainter(px)
            p.setRenderHint(QPainter.Antialiasing)
            p.setBrush(QColor("#F5811F"))
            p.setPen(Qt.NoPen)
            tri = QPainterPath()
            tri.moveTo(pts[0][0], pts[0][1])
            tri.lineTo(pts[1][0], pts[1][1])
            tri.lineTo(pts[2][0], pts[2][1])
            tri.closeSubpath()
            p.drawPath(tri)
            p.end()
            px.save(os.path.join(arrow_dir, fname))

        closed_img = os.path.join(arrow_dir, "closed.png").replace("\\", "/")
        open_img = os.path.join(arrow_dir, "open.png").replace("\\", "/")
        self.subfolder_tree.setStyleSheet(f"""
            QTreeView::branch:has-children:!has-siblings:closed,
            QTreeView::branch:closed:has-children:has-siblings {{
                image: url({closed_img});
            }}
            QTreeView::branch:open:has-children:!has-siblings,
            QTreeView::branch:open:has-children:has-siblings {{
                image: url({open_img});
            }}
        """)
        layout.addWidget(self.subfolder_tree, 1)

        # Header checkbox (select all / deselect all) — overlaid on column 0
        from PySide6.QtWidgets import QCheckBox
        self._header_checkbox = QCheckBox(self.subfolder_tree.header())
        self._header_checkbox.setFixedSize(18, 18)

        # Paint a white checkmark icon for the checked state
        check_img_path = os.path.join(arrow_dir, "check.png")
        ck_px = QPixmap(14, 14)
        ck_px.fill(Qt.transparent)
        ck_p = QPainter(ck_px)
        ck_p.setRenderHint(QPainter.Antialiasing)
        from PySide6.QtGui import QPen
        pen = QPen(QColor("white"))
        pen.setWidth(2)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        ck_p.setPen(pen)
        ck_p.drawLine(3, 7, 6, 10)
        ck_p.drawLine(6, 10, 11, 4)
        ck_p.end()
        ck_px.save(check_img_path)
        check_img = check_img_path.replace("\\", "/")

        self._header_checkbox.setStyleSheet(f"""
            QCheckBox::indicator {{ width: 14px; height: 14px; }}
            QCheckBox::indicator:checked {{
                background: #F5811F; border: 1px solid #F5811F; border-radius: 3px;
                image: url({check_img});
            }}
        """)
        self._header_checkbox.stateChanged.connect(self._on_header_checkbox_changed)

        # Collapse/Expand toggle button — overlaid on column 0
        self._all_expanded = True
        self._collapse_btn = QPushButton("▼", self.subfolder_tree.header())
        self._collapse_btn.setFixedSize(22, 22)
        self._collapse_btn.setCursor(Qt.PointingHandCursor)
        self._collapse_btn.setToolTip("ยุบทั้งหมด")
        self._collapse_btn.setStyleSheet("""
            QPushButton {
                border: none; background: transparent; padding: 0;
                font-size: 11px; color: #F5811F; font-weight: bold;
            }
            QPushButton:hover { background: #FFF3E8; border-radius: 4px; }
        """)
        self._collapse_btn.clicked.connect(self._toggle_collapse_all)

        # Refresh icon button — overlaid on column 1 header area
        self._refresh_btn = QPushButton(self.subfolder_tree.header())
        self._refresh_btn.setIcon(self.style().standardIcon(QStyle.SP_BrowserReload))
        self._refresh_btn.setFixedSize(22, 22)
        self._refresh_btn.setCursor(Qt.PointingHandCursor)
        self._refresh_btn.setToolTip("รีเฟรช")
        self._refresh_btn.setStyleSheet("""
            QPushButton { border: none; background: transparent; padding: 0; }
            QPushButton:hover { background: #F0F0F5; border-radius: 4px; }
        """)
        self._refresh_btn.clicked.connect(self._scan_subfolders)

        # Search input overlaid on header
        self._folder_filter = QLineEdit(self.subfolder_tree.header())
        self._folder_filter.setPlaceholderText("ค้นหาโฟลเดอร์...")
        self._folder_filter.setClearButtonEnabled(True)
        self._folder_filter.setStyleSheet(
            "padding: 2px 6px; border: 1px solid #D2D2D7;"
            "border-radius: 4px; font-size: 11px; background: white;"
        )
        self._folder_filter.textChanged.connect(self._filter_folders)

        self.subfolder_tree.header().geometriesChanged.connect(self._position_header_widgets)
        self.subfolder_tree.header().sectionResized.connect(
            lambda: self._position_header_widgets()
        )
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, self._position_header_widgets)

        # Summary
        self.summary_label = QLabel("")
        self.summary_label.setVisible(False)
        layout.addWidget(self.summary_label)

        # Compact progress bar (hidden by default)
        self.progress_row = QWidget()
        self.progress_row.setVisible(False)
        progress_h = QHBoxLayout(self.progress_row)
        progress_h.setContentsMargins(0, 0, 0, 0)
        progress_h.setSpacing(6)

        self.progress_label = QLabel("")
        self.progress_label.setStyleSheet("color: #1D1D1F; font-size: 11px;")
        progress_h.addWidget(self.progress_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setFixedHeight(14)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #D2D2D7; border-radius: 7px;
                background: #F0F0F5; text-align: center;
                font-size: 10px; color: #636366;
            }
            QProgressBar::chunk {
                background: #F5811F; border-radius: 6px;
            }
        """)
        progress_h.addWidget(self.progress_bar, 1)

        self.progress_detail = QLabel("")
        self.progress_detail.setStyleSheet("color: #86868B; font-size: 10px;")
        progress_h.addWidget(self.progress_detail)

        self.cancel_btn = QPushButton("ยกเลิก")
        self.cancel_btn.setFixedHeight(22)
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background: #F5811F; color: white;
                padding: 0 10px; border-radius: 6px;
                font-size: 11px; font-weight: bold; border: none;
            }
            QPushButton:hover { background: #E0710A; }
        """)
        self.cancel_btn.clicked.connect(self._cancel_processing)
        progress_h.addWidget(self.cancel_btn)

        layout.addWidget(self.progress_row)

    # -- Folder browsing --

    def _on_tree_item_clicked(self, item, column):
        """Single-click on icon column (1) opens folder in Finder."""
        if column == 1:
            path = item.data(0, Qt.UserRole)
            if path and os.path.isdir(path):
                subprocess.run(["open", path], check=False)

    def _open_folder_in_finder(self, item, column):
        path = item.data(0, Qt.UserRole)
        if path and os.path.isdir(path):
            subprocess.run(["open", path], check=False)

    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "เลือกโฟลเดอร์รูปภาพหลัก",
            self.config.main_photos_folder or os.path.expanduser("~"),
        )
        if folder:
            self.folder_input.setText(folder)
            self.config.main_photos_folder = folder
            self.config.save()
            self.folder_changed.emit(folder)
            self._scan_subfolders()

    def _get_all_checked_paths(self) -> set:
        """Collect all checked paths from the current tree."""
        paths = set()
        def _collect(item):
            if item.checkState(0) == Qt.Checked:
                path = item.data(0, Qt.UserRole)
                if path:
                    paths.add(path)
            for i in range(item.childCount()):
                _collect(item.child(i))
        for i in range(self.subfolder_tree.topLevelItemCount()):
            _collect(self.subfolder_tree.topLevelItem(i))
        return paths

    def _restore_check_states(self, checked_paths: set):
        """Restore check states from a set of paths."""
        def _restore(item):
            path = item.data(0, Qt.UserRole)
            if path and path in checked_paths:
                item.setCheckState(0, Qt.Checked)
            for i in range(item.childCount()):
                _restore(item.child(i))
        for i in range(self.subfolder_tree.topLevelItemCount()):
            _restore(self.subfolder_tree.topLevelItem(i))

    def _scan_subfolders(self):
        # Preserve check states across refresh
        checked_paths = self._get_all_checked_paths()

        self.subfolder_tree.clear()
        folder = self.folder_input.text()
        if not folder or not os.path.isdir(folder):
            return

        db_folders = {f["folder_path"]: f for f in get_all_event_folders()}

        self._updating_checks = True
        folder_count = 0
        for entry in sorted(Path(folder).iterdir()):
            if entry.is_dir() and not entry.name.startswith('.'):
                item = self._build_tree_item(entry, db_folders)
                if item is not None:
                    self.subfolder_tree.addTopLevelItem(item)
                    folder_count += self._count_tree_items(item)

        # Restore checked paths
        if checked_paths:
            self._restore_check_states(checked_paths)

        self.subfolder_tree.expandAll()
        self._updating_checks = False

        self.summary_label.setText(f"พบ {folder_count} โฟลเดอร์")
        self.folder_count_changed.emit(folder_count)

    def _build_tree_item(self, dir_path: Path, db_folders: dict) -> QTreeWidgetItem | None:
        """Recursively build a 3-column tree item with DB status."""
        photo_count = sum(
            1 for f in dir_path.iterdir()
            if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS
        )

        children = []
        for entry in sorted(dir_path.iterdir()):
            if entry.is_dir() and not entry.name.startswith('.'):
                child = self._build_tree_item(entry, db_folders)
                if child is not None:
                    children.append(child)

        if photo_count == 0 and not children:
            return None

        item = QTreeWidgetItem()
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(0, Qt.Unchecked)
        item.setData(0, Qt.UserRole, str(dir_path))

        # Column 0: folder name with expand/collapse prefix
        item.setData(0, Qt.UserRole + 1, dir_path.name)
        if children:
            item.setText(0, f"\u25bc {dir_path.name}")
        else:
            item.setText(0, dir_path.name)

        # Column 1: open folder icon
        item.setIcon(1, self.style().standardIcon(QStyle.SP_DirOpenIcon))

        # Column 2: photo count
        item.setText(2, str(photo_count))

        # Column 3: combined status (faces + processed state)
        db_info = db_folders.get(str(dir_path))
        if db_info and db_info["is_processed"]:
            item.setText(3, str(db_info['face_count']))
            item.setForeground(3, Qt.darkGreen)
        else:
            item.setText(3, "รอ")
            item.setForeground(3, Qt.darkYellow)

        for child in children:
            item.addChild(child)

        return item

    def _count_tree_items(self, item: QTreeWidgetItem) -> int:
        count = 1
        for i in range(item.childCount()):
            count += self._count_tree_items(item.child(i))
        return count

    def _update_folder_icons(self, item: QTreeWidgetItem):
        """Update expand/collapse prefix based on state."""
        base = item.data(0, Qt.UserRole + 1)
        if base and item.childCount() > 0:
            prefix = "\u25bc" if item.isExpanded() else "\u25b6"
            item.setText(0, f"{prefix} {base}")

    # -- Checkbox cascading --

    def _on_item_changed(self, item: QTreeWidgetItem, column: int):
        if self._updating_checks:
            return
        self._updating_checks = True
        state = item.checkState(0)
        self._set_children_check_state(item, state)
        self._updating_checks = False

    def _set_children_check_state(self, item: QTreeWidgetItem, state):
        for i in range(item.childCount()):
            child = item.child(i)
            child.setCheckState(0, state)
            self._set_children_check_state(child, state)

    def _toggle_collapse_all(self):
        """Toggle collapse/expand all tree items."""
        if self._all_expanded:
            self.subfolder_tree.collapseAll()
            self._collapse_btn.setText("▶")
            self._collapse_btn.setToolTip("ขยายทั้งหมด")
        else:
            self.subfolder_tree.expandAll()
            self._collapse_btn.setText("▼")
            self._collapse_btn.setToolTip("ยุบทั้งหมด")
        self._all_expanded = not self._all_expanded
        self._update_folder_icons()

    def _position_header_widgets(self):
        """Position the checkbox, collapse btn, search input, and refresh button on the header."""
        header = self.subfolder_tree.header()
        h = header.height()

        # Checkbox in column 0 — left side with small offset
        cb_x = header.sectionPosition(0) + 4
        cb_y = (h - self._header_checkbox.height()) // 2
        self._header_checkbox.move(cb_x, cb_y)

        # Collapse/expand toggle — next to checkbox
        col_x = cb_x + self._header_checkbox.width() + 4
        col_y = (h - self._collapse_btn.height()) // 2
        self._collapse_btn.move(col_x, col_y)

        # Search input — right portion of column 0, full header height
        sec0_w = header.sectionSize(0)
        filter_w = min(180, sec0_w - 100)
        if filter_w > 60:
            filter_h = h - 4
            self._folder_filter.setFixedSize(filter_w, filter_h)
            fx = header.sectionPosition(0) + sec0_w - filter_w - 4
            fy = 2
            self._folder_filter.move(fx, fy)
            self._folder_filter.setVisible(True)
        else:
            self._folder_filter.setVisible(False)

        # Refresh icon in column 1 area
        sec1_x = header.sectionPosition(1)
        sec1_w = header.sectionSize(1)
        rb_x = sec1_x + (sec1_w - self._refresh_btn.width()) // 2
        rb_y = (h - self._refresh_btn.height()) // 2
        self._refresh_btn.move(rb_x, rb_y)

    def _on_header_checkbox_changed(self, state):
        """Toggle all tree items based on header checkbox state."""
        check = Qt.Checked if state else Qt.Unchecked
        self._updating_checks = True
        for i in range(self.subfolder_tree.topLevelItemCount()):
            item = self.subfolder_tree.topLevelItem(i)
            item.setCheckState(0, check)
            self._set_children_check_state(item, check)
        self._updating_checks = False

    def _filter_folders(self, text: str):
        """Filter folder tree items by substring match (recursive)."""
        text_lower = text.lower()
        for i in range(self.subfolder_tree.topLevelItemCount()):
            item = self.subfolder_tree.topLevelItem(i)
            self._filter_folder_item(item, text_lower)

    def _filter_folder_item(self, item, text_lower: str) -> bool:
        """Recursively filter a tree item. Returns True if visible."""
        name = (item.data(0, Qt.UserRole + 1) or item.text(0)).lower()
        name_match = not text_lower or text_lower in name

        # Check children first
        any_child_visible = False
        for i in range(item.childCount()):
            if self._filter_folder_item(item.child(i), text_lower):
                any_child_visible = True

        visible = name_match or any_child_visible
        item.setHidden(not visible)
        return visible

    def _select_all(self):
        self._header_checkbox.setChecked(True)

    def _deselect_all(self):
        self._header_checkbox.setChecked(False)

    # -- Processing --

    def _collect_checked_items(self, parent=None):
        """Recursively collect all checked QTreeWidgetItems."""
        items = []
        if parent is None:
            for i in range(self.subfolder_tree.topLevelItemCount()):
                item = self.subfolder_tree.topLevelItem(i)
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

    def _process_next_folder(self):
        if self._processing_cancelled:
            self._on_cancelled()
            return
        if self._current_folder_idx >= len(self._folders_to_process):
            self._on_all_done()
            return

        self.progress_row.setVisible(True)
        path, name, _ = self._folders_to_process[self._current_folder_idx]
        self.progress_label.setText(
            f"{self._current_folder_idx + 1}/{len(self._folders_to_process)}: {name}"
        )

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
        self.progress_detail.setText(f"{current}/{total}")

    def _on_folder_done(self, result):
        if self._processing_cancelled:
            self._on_cancelled()
            return
        self._current_folder_idx += 1
        self._scan_subfolders()
        self._process_next_folder()

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
        self.progress_row.setVisible(False)
        self.progress_bar.setValue(0)
        self.cancel_btn.setEnabled(True)
        self.cancel_btn.setText("ยกเลิก")
        self._scan_subfolders()

    # -- Public API for MainPanel --

    def get_selected_folders(self) -> list:
        """Return list of (path, name, photo_count) for all checked folders."""
        selected = []
        for i in range(self.subfolder_tree.topLevelItemCount()):
            self._collect_checked(self.subfolder_tree.topLevelItem(i), selected)
        return selected

    def _collect_checked(self, item: QTreeWidgetItem, result: list):
        if item.checkState(0) == Qt.Checked:
            path = item.data(0, Qt.UserRole)
            name = item.data(0, Qt.UserRole + 1) or item.text(0)
            count = int(item.text(2)) if item.text(2).isdigit() else 0
            if count > 0:
                result.append((path, name, count))
        for i in range(item.childCount()):
            self._collect_checked(item.child(i), result)

    def get_checked_folder_paths(self) -> list[str]:
        """Return list of paths for all checked folders that have photos."""
        return [path for path, name, count in self.get_selected_folders()]

    def get_unprocessed_checked_folders(self) -> list[tuple]:
        """Return list of (path, name, count) for checked folders not yet processed."""
        db_folders = {f["folder_path"]: f for f in get_all_event_folders()}
        result = []
        for path, name, count in self.get_selected_folders():
            db_info = db_folders.get(path)
            if not db_info or not db_info["is_processed"]:
                result.append((path, name, count))
        return result

    def start_auto_processing(self, on_complete_callback):
        """Auto-process unprocessed checked folders, then call callback when done."""
        unprocessed = self.get_unprocessed_checked_folders()
        if not unprocessed:
            on_complete_callback()
            return

        self._auto_process_callback = on_complete_callback
        self._folders_to_process = unprocessed
        self._current_folder_idx = 0
        self._processing_cancelled = False
        self.cancel_btn.setEnabled(True)
        self.cancel_btn.setText("ยกเลิก")
        self.progress_row.setVisible(True)

        # Override _on_all_done temporarily
        self._auto_processing = True
        self._process_next_folder()

    def _on_all_done(self):
        self.progress_row.setVisible(False)
        self.progress_bar.setValue(0)
        self.processing_complete.emit()

        if hasattr(self, '_auto_processing') and self._auto_processing:
            self._auto_processing = False
            if hasattr(self, '_auto_process_callback'):
                self._auto_process_callback()
