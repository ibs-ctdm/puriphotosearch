"""Combined panel: left folder tree + right tabs (search / scan)."""

import os
import subprocess

from PySide6.QtCore import Signal, Qt, QSize, QRectF
from PySide6.QtGui import QPixmap, QImage, QIcon, QPainter, QPainterPath, QFont, QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QSlider, QCheckBox, QRadioButton, QButtonGroup, QFileDialog,
    QSplitter, QTabWidget, QStackedWidget, QScrollArea,
    QLineEdit, QProgressBar, QMessageBox,
    QTreeWidget, QTreeWidgetItem, QHeaderView, QStyle,
)

from app.config import AppConfig
from app.database import (
    get_all_persons, get_all_groups, get_processed_event_folders,
    add_or_get_event_folder,
)
from app.workers.search_worker import SearchAllWorker
from app.workers.scan_mode_worker import ScanClusterWorker, ExecuteScanWorker
from app.ui.widgets.folder_selector import FolderSelector
from app.ui.widgets.results_gallery import ResultsGallery


class MainPanel(QWidget):
    """Combined panel with folder tree (left) and search/scan tabs (right)."""

    person_changed = Signal()
    processing_complete = Signal()

    def __init__(self, config: AppConfig, parent=None):
        super().__init__(parent)
        self.config = config
        self._search_worker = None
        self._scan_worker = None
        self._persons = []
        self._clusters = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet("""
            QSplitter::handle { background: #D2D2D7; }
        """)

        # === LEFT: Folder selector ===
        self.folder_panel = FolderSelector(self.config)
        self.folder_panel.folder_changed.connect(self._on_folder_changed)
        self.folder_panel.processing_complete.connect(self._on_processing_complete)
        splitter.addWidget(self.folder_panel)

        # === RIGHT: Tabs ===
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border: none;
                border-top: 1px solid #D2D2D7;
                background: white;
            }
            QTabBar {
                background: white;
            }
            QTabBar::tab {
                padding: 10px 20px;
                font-size: 13px;
                border: none;
                border-bottom: 2px solid transparent;
                background: white;
                color: #86868B;
            }
            QTabBar::tab:selected {
                color: #F5811F;
                font-weight: bold;
                border-bottom: 2px solid #F5811F;
                background: white;
            }
            QTabBar::tab:hover:!selected {
                color: #424245;
            }
        """)

        self.tabs.addTab(self._build_scan_tab(), "สแกนก่อนตั้งชื่อทีหลัง")
        self.tabs.addTab(self._build_search_tab(), "ค้นหาจากรายชื่อ")
        self.tabs.currentChanged.connect(self._on_tab_changed)
        right_layout.addWidget(self.tabs)

        splitter.addWidget(right_widget)

        # 1:1 split
        splitter.setSizes([500, 500])
        layout.addWidget(splitter)

    # ================================================================
    # Tab 1: Search from DB
    # ================================================================

    def _build_search_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        # Search filter
        self._person_filter = QLineEdit()
        self._person_filter.setPlaceholderText("ค้นหาชื่อบุคคล...")
        self._person_filter.setClearButtonEnabled(True)
        self._person_filter.setStyleSheet(
            "padding: 6px 10px; border: 1px solid #D2D2D7;"
            "border-radius: 8px; font-size: 13px; background: white;"
        )
        self._person_filter.textChanged.connect(self._filter_persons)
        layout.addWidget(self._person_filter)

        # Select all / deselect all + threshold on same row
        sel_row = QHBoxLayout()
        sel_all_btn = QPushButton("เลือกทั้งหมด")
        sel_all_btn.setStyleSheet("font-size: 12px; padding: 3px 10px;")
        sel_all_btn.clicked.connect(self._select_all_persons)
        desel_all_btn = QPushButton("ยกเลิกทั้งหมด")
        desel_all_btn.setStyleSheet("font-size: 12px; padding: 3px 10px;")
        desel_all_btn.clicked.connect(self._deselect_all_persons)
        sel_row.addWidget(sel_all_btn)
        sel_row.addWidget(desel_all_btn)
        sel_row.addStretch()
        threshold_lbl = QLabel("ค่าความคล้าย:")
        threshold_lbl.setStyleSheet("font-size: 12px;")
        sel_row.addWidget(threshold_lbl)
        self.threshold_slider = QSlider(Qt.Horizontal)
        self.threshold_slider.setRange(20, 90)
        self.threshold_slider.setValue(int(self.config.similarity_threshold * 100))
        self.threshold_slider.setFixedWidth(100)
        self.threshold_slider.valueChanged.connect(self._on_threshold_changed)
        sel_row.addWidget(self.threshold_slider)
        self.threshold_label = QLabel(f"{self.config.similarity_threshold:.2f}")
        self.threshold_label.setStyleSheet("font-weight: bold; font-size: 12px; min-width: 30px;")
        sel_row.addWidget(self.threshold_label)
        layout.addLayout(sel_row)

        # Person tree with checkboxes (grouped by group_name)
        self._person_tree = QTreeWidget()
        self._person_tree.setHeaderHidden(True)
        self._person_tree.setRootIsDecorated(True)
        self._person_tree.setSelectionMode(QTreeWidget.NoSelection)
        self._person_tree.setIconSize(QSize(28, 28))

        # Custom orange branch indicators (reuse temp arrow images)
        import tempfile
        arrow_dir = os.path.join(tempfile.gettempdir(), "puri_arrows")
        os.makedirs(arrow_dir, exist_ok=True)
        for fname, pts in [("closed.png", [(4, 1), (11, 6), (4, 11)]),
                           ("open.png", [(1, 4), (11, 4), (6, 11)])]:
            arrow_path = os.path.join(arrow_dir, fname)
            if not os.path.exists(arrow_path):
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
                px.save(arrow_path)

        closed_img = os.path.join(arrow_dir, "closed.png").replace("\\", "/")
        open_img = os.path.join(arrow_dir, "open.png").replace("\\", "/")
        self._person_tree.setStyleSheet(f"""
            QTreeWidget {{
                border: 1px solid #D2D2D7; border-radius: 8px;
                background: white; font-size: 13px;
            }}
            QTreeWidget::item {{
                padding: 4px 2px;
            }}
            QTreeWidget::item:hover {{
                background: #FFF3E8;
            }}
            QTreeView::branch:has-children:!has-siblings:closed,
            QTreeView::branch:closed:has-children:has-siblings {{
                image: url({closed_img});
            }}
            QTreeView::branch:open:has-children:!has-siblings,
            QTreeView::branch:open:has-children:has-siblings {{
                image: url({open_img});
            }}
        """)
        self._updating_person_checks = False
        self._person_tree.itemChanged.connect(self._on_person_tree_item_changed)
        layout.addWidget(self._person_tree, stretch=1)

        # Destination selector
        self._search_dest_row = self._build_destination_row()
        layout.addWidget(self._search_dest_row)

        # Action button at bottom
        btn_row = QHBoxLayout()

        self._reset_search_btn = QPushButton("← เริ่มต้นใหม่")
        self._reset_search_btn.setStyleSheet("""
            QPushButton {
                padding: 10px 20px; border-radius: 8px;
                font-size: 13px; border: 1px solid #D2D2D7;
                background: white; color: #1D1D1F;
            }
            QPushButton:hover { background: #F0F0F5; }
        """)
        self._reset_search_btn.clicked.connect(self._reset_search_view)
        self._reset_search_btn.setVisible(False)
        btn_row.addWidget(self._reset_search_btn)

        btn_row.addStretch()
        self.search_btn = QPushButton("ดำเนินการ")
        self.search_btn.setStyleSheet("""
            QPushButton {
                background: #F5811F; color: white;
                padding: 10px 28px; border-radius: 8px;
                font-weight: bold; font-size: 14px; border: none;
            }
            QPushButton:hover { background: #E0710A; }
            QPushButton:disabled { background: #C7C7CC; }
        """)
        self.search_btn.clicked.connect(self._start_search)
        btn_row.addWidget(self.search_btn)
        layout.addLayout(btn_row)

        # Results gallery (hidden until search completes)
        self.results_gallery = ResultsGallery()
        self.results_gallery.setVisible(False)
        layout.addWidget(self.results_gallery, stretch=1)

        return w

    def _on_person_tree_item_changed(self, item, column):
        """Handle cascading checkboxes: group ↔ children."""
        if self._updating_person_checks:
            return
        self._updating_person_checks = True

        if item.data(0, Qt.UserRole + 1) == "group":
            # Group header changed → set all children to same state
            state = item.checkState(0)
            for i in range(item.childCount()):
                item.child(i).setCheckState(0, state)
        else:
            # Person item changed → update parent group header
            parent = item.parent()
            if parent:
                self._update_group_check_state(parent)

        self._updating_person_checks = False

    def _update_group_check_state(self, group_item):
        """Update group header check state based on children."""
        total = group_item.childCount()
        if total == 0:
            return
        checked = sum(
            1 for i in range(total)
            if group_item.child(i).checkState(0) == Qt.Checked
        )
        if checked == 0:
            group_item.setCheckState(0, Qt.Unchecked)
        elif checked == total:
            group_item.setCheckState(0, Qt.Checked)
        else:
            group_item.setCheckState(0, Qt.PartiallyChecked)

    def _filter_persons(self, text: str):
        """Filter person tree items by substring match (hierarchical)."""
        text_lower = text.lower()
        for i in range(self._person_tree.topLevelItemCount()):
            group_item = self._person_tree.topLevelItem(i)
            visible_children = 0
            for j in range(group_item.childCount()):
                child = group_item.child(j)
                name = child.text(0).lower()
                hidden = bool(text_lower) and text_lower not in name
                child.setHidden(hidden)
                if not hidden:
                    visible_children += 1
            # Hide group header if all children are hidden
            group_item.setHidden(visible_children == 0 and bool(text_lower))

    def _select_all_persons(self):
        self._updating_person_checks = True
        for i in range(self._person_tree.topLevelItemCount()):
            group_item = self._person_tree.topLevelItem(i)
            if group_item.isHidden():
                continue
            for j in range(group_item.childCount()):
                child = group_item.child(j)
                if not child.isHidden():
                    child.setCheckState(0, Qt.Checked)
            self._update_group_check_state(group_item)
        self._updating_person_checks = False

    def _deselect_all_persons(self):
        self._updating_person_checks = True
        for i in range(self._person_tree.topLevelItemCount()):
            group_item = self._person_tree.topLevelItem(i)
            for j in range(group_item.childCount()):
                group_item.child(j).setCheckState(0, Qt.Unchecked)
            group_item.setCheckState(0, Qt.Unchecked)
        self._updating_person_checks = False

    def _on_tab_changed(self, index: int):
        if index == 1:
            self.refresh_data()

    def refresh_data(self):
        """Reload persons from database into person tree, grouped by group_name."""
        # Preserve checked person IDs
        checked_ids = set()
        for i in range(self._person_tree.topLevelItemCount()):
            top = self._person_tree.topLevelItem(i)
            # Check children (person items under group headers)
            for j in range(top.childCount()):
                child = top.child(j)
                if child.checkState(0) == Qt.Checked:
                    p = child.data(0, Qt.UserRole)
                    if p:
                        checked_ids.add(p["id"])
            # Also check top-level person items (flat fallback)
            p = top.data(0, Qt.UserRole)
            if p and top.checkState(0) == Qt.Checked:
                checked_ids.add(p["id"])

        self._persons = get_all_persons()
        groups = get_all_groups()

        self._updating_person_checks = True
        self._person_tree.clear()

        # Group persons by group_name
        from collections import defaultdict
        persons_by_group = defaultdict(list)
        ungrouped = []
        for p in self._persons:
            if p.get("group_name"):
                persons_by_group[p["group_name"]].append(p)
            else:
                ungrouped.append(p)

        # Build group headers + children
        for group_name in groups:
            members = persons_by_group.get(group_name, [])
            group_item = QTreeWidgetItem()
            group_item.setFlags(group_item.flags() | Qt.ItemIsUserCheckable)
            group_item.setCheckState(0, Qt.Unchecked)
            group_item.setText(0, f"{group_name} ({len(members)})")
            group_item.setData(0, Qt.UserRole, None)
            group_item.setData(0, Qt.UserRole + 1, "group")
            bold_font = QFont()
            bold_font.setBold(True)
            group_item.setFont(0, bold_font)

            for p in members:
                child = self._make_person_item(p, p["id"] in checked_ids)
                group_item.addChild(child)

            self._person_tree.addTopLevelItem(group_item)

        # Ungrouped persons
        if ungrouped:
            ug_item = QTreeWidgetItem()
            ug_item.setFlags(ug_item.flags() | Qt.ItemIsUserCheckable)
            ug_item.setCheckState(0, Qt.Unchecked)
            ug_item.setText(0, f"ยังไม่จัดกลุ่ม ({len(ungrouped)})")
            ug_item.setData(0, Qt.UserRole, None)
            ug_item.setData(0, Qt.UserRole + 1, "group")
            bold_font = QFont()
            bold_font.setBold(True)
            ug_item.setFont(0, bold_font)

            for p in ungrouped:
                child = self._make_person_item(p, p["id"] in checked_ids)
                ug_item.addChild(child)

            self._person_tree.addTopLevelItem(ug_item)

        self._person_tree.expandAll()

        # Update group header check states based on children
        for i in range(self._person_tree.topLevelItemCount()):
            self._update_group_check_state(self._person_tree.topLevelItem(i))

        self._updating_person_checks = False

        # Re-apply filter
        self._filter_persons(self._person_filter.text())

    def _make_person_item(self, p: dict, checked: bool) -> QTreeWidgetItem:
        """Create a person tree item with circular thumbnail icon."""
        item = QTreeWidgetItem()
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(0, Qt.Checked if checked else Qt.Unchecked)
        item.setText(0, p["name"])
        item.setData(0, Qt.UserRole, p)

        thumb = p.get("thumbnail")
        if thumb:
            img = QImage.fromData(thumb)
            if not img.isNull():
                sz = 28
                scaled = QPixmap.fromImage(img).scaled(
                    QSize(sz, sz), Qt.KeepAspectRatioByExpanding,
                    Qt.SmoothTransformation,
                )
                if scaled.width() > sz or scaled.height() > sz:
                    x = (scaled.width() - sz) // 2
                    y = (scaled.height() - sz) // 2
                    scaled = scaled.copy(x, y, sz, sz)
                circ = QPixmap(sz, sz)
                circ.fill(Qt.transparent)
                painter = QPainter(circ)
                painter.setRenderHint(QPainter.Antialiasing)
                clip = QPainterPath()
                clip.addEllipse(QRectF(0, 0, sz, sz))
                painter.setClipPath(clip)
                painter.drawPixmap(0, 0, scaled)
                painter.end()
                item.setIcon(0, QIcon(circ))

        return item

    def _on_threshold_changed(self, value):
        threshold = value / 100.0
        self.threshold_label.setText(f"{threshold:.2f}")

    # ── Destination selector (shared state, separate widgets per tab) ──

    def _build_destination_row(self) -> QWidget:
        """Build an output destination selector row.

        Each call creates new widgets but they all sync to self._custom_dest_path.
        """
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 4, 0, 4)
        row_layout.setSpacing(6)

        lbl = QLabel("ปลายทาง:")
        lbl.setStyleSheet("font-size: 12px; color: #636366;")
        row_layout.addWidget(lbl)

        radio_event = QRadioButton("ในโฟลเดอร์กิจกรรม")
        radio_event.setChecked(True)
        radio_event.setStyleSheet("font-size: 12px;")
        radio_custom = QRadioButton("โฟลเดอร์ที่ระบุ")
        radio_custom.setStyleSheet("font-size: 12px;")

        group = QButtonGroup(row)
        group.addButton(radio_event, 0)
        group.addButton(radio_custom, 1)

        row_layout.addWidget(radio_event)
        row_layout.addWidget(radio_custom)

        path_input = QLineEdit()
        path_input.setReadOnly(True)
        path_input.setPlaceholderText("เลือกโฟลเดอร์...")
        path_input.setStyleSheet(
            "padding: 4px 8px; border: 1px solid #D2D2D7;"
            "border-radius: 4px; font-size: 11px; background: #FAFAFA;"
        )
        path_input.setVisible(False)
        row_layout.addWidget(path_input, stretch=1)

        browse_btn = QPushButton("เรียกดู...")
        browse_btn.setStyleSheet(
            "font-size: 12px; padding: 4px 10px;"
            "border: 1px solid #D2D2D7; border-radius: 4px; background: white;"
        )
        browse_btn.setCursor(Qt.PointingHandCursor)
        browse_btn.setVisible(False)
        row_layout.addWidget(browse_btn)

        def on_mode_changed(id_: int, checked: bool):
            if not checked:
                return
            is_custom = id_ == 1
            path_input.setVisible(is_custom)
            browse_btn.setVisible(is_custom)

        def on_browse():
            path = QFileDialog.getExistingDirectory(
                self, "เลือกโฟลเดอร์ปลายทาง",
                self._custom_dest_path or os.path.expanduser("~"),
            )
            if path:
                self._custom_dest_path = path
                path_input.setText(path)

        group.idToggled.connect(on_mode_changed)
        browse_btn.clicked.connect(on_browse)

        # Store references for reading state
        row._radio_custom = radio_custom
        if not hasattr(self, "_custom_dest_path"):
            self._custom_dest_path = ""

        return row

    def _get_custom_dest_dir(self) -> str | None:
        """Return custom dest dir if any destination row has 'custom' selected."""
        # Check search tab dest row
        if (hasattr(self, "_search_dest_row")
                and self._search_dest_row._radio_custom.isChecked()
                and self._custom_dest_path):
            return self._custom_dest_path
        # Check scan tab dest row
        if (hasattr(self, "_scan_dest_row")
                and self._scan_dest_row._radio_custom.isChecked()
                and self._custom_dest_path):
            return self._custom_dest_path
        return None

    def _start_search(self):
        """Start search — auto-process unprocessed folders first if needed."""
        selected = self.folder_panel.get_selected_folders()
        if not selected:
            QMessageBox.warning(
                self, "คำเตือน",
                "กรุณาเลือก (ติ๊ก) โฟลเดอร์ทางซ้ายก่อน",
            )
            return

        # Collect checked persons from tree (children under group headers)
        checked_persons = []
        for i in range(self._person_tree.topLevelItemCount()):
            group_item = self._person_tree.topLevelItem(i)
            for j in range(group_item.childCount()):
                child = group_item.child(j)
                if child.checkState(0) == Qt.Checked:
                    p = child.data(0, Qt.UserRole)
                    if p:
                        checked_persons.append(p)

        if not checked_persons:
            QMessageBox.warning(
                self, "คำเตือน",
                "กรุณาเลือก (ติ๊ก) บุคคลอย่างน้อย 1 คน",
            )
            return

        # Save search params
        self._search_persons = checked_persons
        self._search_threshold = self.threshold_slider.value() / 100.0

        # Show results area, hide person list
        self._person_tree.setVisible(False)
        self.results_gallery.setVisible(True)
        self.results_gallery.clear()
        self.results_gallery.show_loading("กำลังเตรียมข้อมูล...")
        self.search_btn.setEnabled(False)

        self.folder_panel.start_auto_processing(self._run_search_after_processing)

    def _run_search_after_processing(self):
        """Called after auto-processing completes — now run the actual search."""
        from app.database import get_all_event_folders

        selected_paths = self.folder_panel.get_checked_folder_paths()
        if not selected_paths:
            self.search_btn.setEnabled(True)
            self.results_gallery.hide_loading()
            return

        # Get processed event folder IDs for selected paths
        db_folders = {f["folder_path"]: f for f in get_all_event_folders()}
        processed_folders = []
        for path in selected_paths:
            db_info = db_folders.get(path)
            if db_info and db_info["is_processed"]:
                processed_folders.append(db_info)

        if not processed_folders:
            QMessageBox.warning(self, "คำเตือน", "ไม่มีโฟลเดอร์ที่ประมวลผลแล้ว")
            self.search_btn.setEnabled(True)
            self.results_gallery.hide_loading()
            return

        # Multi-folder sequential search (person/mode/threshold already saved in _start_search)
        self._pending_folders = processed_folders
        self._person_search_results = {}  # keyed by person_name
        self._search_folder_idx = 0
        self.results_gallery.show_loading("กำลังค้นหา...")
        self._search_next_folder()

    def _search_next_folder(self):
        if self._search_folder_idx >= len(self._pending_folders):
            self._on_search_all_done()
            return

        ef = self._pending_folders[self._search_folder_idx]
        status_msg = f"กำลังค้นหาในโฟลเดอร์ {self._search_folder_idx + 1}/{len(self._pending_folders)}: {ef['folder_name']}"
        self.results_gallery.show_loading(status_msg)

        self._search_worker = SearchAllWorker(
            persons=self._search_persons,
            event_folder_id=ef["id"],
            event_folder_path=ef["folder_path"],
            threshold=self._search_threshold,
            custom_dest_dir=self._get_custom_dest_dir(),
        )
        self._search_worker.finished_with_result.connect(self._on_all_folder_result)
        self._search_worker.status_message.connect(self._on_search_status)
        self._search_worker.error.connect(self._on_search_error)
        self._search_worker.start()

    def _on_search_status(self, message):
        self.results_gallery._loading_widget.set_message(message)

    def _on_all_folder_result(self, result):
        ef = self._pending_folders[self._search_folder_idx]
        search_results = result.get("search_results", {})
        organized = result.get("organized")

        # Map person_name -> organized detail for this folder
        org_details = {}
        if organized and organized.get("details"):
            for detail in organized["details"]:
                org_details[detail["person_name"]] = detail

        for person_id, data in search_results.items():
            person_name = data["name"]
            if person_name not in self._person_search_results:
                self._person_search_results[person_name] = {
                    "person_name": person_name,
                    "matches": [],
                    "folders": [],
                    "copied": 0,
                }

            psr = self._person_search_results[person_name]

            # Add matches
            for match in data["matches"]:
                match["person_name"] = person_name
                psr["matches"].append(match)

            # Add output folders from organized result
            detail = org_details.get(person_name)
            if detail:
                psr["copied"] += detail.get("copied", 0)
                for output_folder in detail.get("output_folders", []):
                    psr["folders"].append({
                        "display_name": f"{ef['folder_name']}/{person_name}",
                        "path": output_folder,
                    })

        self._search_folder_idx += 1
        self._search_next_folder()

    def _on_search_all_done(self):
        self.search_btn.setEnabled(True)
        self.results_gallery.hide_loading()
        self._reset_search_btn.setVisible(True)
        self.search_btn.setVisible(False)

        person_results = list(self._person_search_results.values())
        self.results_gallery.show_person_grouped_results(person_results)

        # Refresh folder tree to show newly created person subfolders
        self.folder_panel._scan_subfolders()

    def _reset_search_view(self):
        """Reset search tab back to person list view."""
        self.results_gallery.setVisible(False)
        self._person_tree.setVisible(True)
        self._reset_search_btn.setVisible(False)
        self.search_btn.setVisible(True)
        self.search_btn.setEnabled(True)

    def _on_search_error(self, message):
        self.search_btn.setEnabled(True)
        self.results_gallery.hide_loading()
        self.results_gallery.setVisible(False)
        self._person_tree.setVisible(True)
        QMessageBox.warning(self, "ข้อผิดพลาดในการค้นหา", message)

    # ================================================================
    # Tab 2: Scan & Name
    # ================================================================

    def _build_scan_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        self._scan_stack = QStackedWidget()
        self._scan_stack.addWidget(self._build_scan_step0())  # intro + start
        self._scan_stack.addWidget(self._build_scan_step1())  # progress
        self._scan_stack.addWidget(self._build_scan_step2())  # results
        layout.addWidget(self._scan_stack)

        return w

    def _build_scan_step0(self) -> QWidget:
        """Step 0: description + start scan button + summary table (hidden)."""
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 20, 0, 0)
        lay.setSpacing(12)

        desc = QLabel(
            "สแกนใบหน้าในโฟลเดอร์ที่เลือกทางซ้าย แล้วตั้งชื่อบุคคลทีหลัง\n"
            "ระบบจะจัดกลุ่มใบหน้าที่เหมือนกัน และจำคนที่มีในฐานข้อมูลให้อัตโนมัติ ส่วนคนที่ยังไม่มีก็ให้ตั้งชื่อใหม่ได้ทันที"
        )
        desc.setWordWrap(True)
        desc.setAlignment(Qt.AlignCenter)
        desc.setStyleSheet("color: #86868B; font-size: 13px;")
        lay.addWidget(desc)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._scan_start_btn = QPushButton("เริ่มสแกนใหม่")
        self._scan_start_btn.setStyleSheet("""
            QPushButton {
                background: #F5811F; color: white;
                padding: 10px 28px; border-radius: 8px;
                font-weight: bold; font-size: 14px; border: none;
            }
            QPushButton:hover { background: #E0710A; }
            QPushButton:disabled { background: #C7C7CC; }
        """)
        self._scan_start_btn.clicked.connect(self._start_scan)
        btn_row.addWidget(self._scan_start_btn)
        lay.addLayout(btn_row)

        # Summary table (hidden until execute completes)
        self._summary_header = QLabel("")
        self._summary_header.setStyleSheet(
            "font-size: 14px; font-weight: bold; color: #1D1D1F;"
        )
        self._summary_header.setVisible(False)
        lay.addWidget(self._summary_header)

        self._summary_table = QTreeWidget()
        self._summary_table.setHeaderLabels(["ชื่อบุคคล", "จำนวนรูป", "โฟลเดอร์", ""])
        self._summary_table.setRootIsDecorated(False)
        self._summary_table.setAlternatingRowColors(True)
        self._summary_table.header().setStretchLastSection(False)
        self._summary_table.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._summary_table.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._summary_table.header().setSectionResizeMode(2, QHeaderView.Stretch)
        self._summary_table.header().setSectionResizeMode(3, QHeaderView.Fixed)
        self._summary_table.header().resizeSection(3, 30)
        self._summary_table.setStyleSheet("""
            QTreeWidget {
                border: 1px solid #D2D2D7; border-radius: 8px;
                font-size: 13px; background: white;
            }
            QTreeWidget::item {
                padding: 6px 4px;
            }
            QTreeWidget::item:hover {
                background: #FFF3E8;
            }
            QHeaderView::section {
                background: #FAFAFA; border: none;
                border-bottom: 1px solid #D2D2D7;
                padding: 6px 8px; font-weight: bold; font-size: 12px;
            }
        """)
        self._summary_table.itemDoubleClicked.connect(self._open_summary_folder)
        self._summary_table.itemClicked.connect(self._on_summary_item_clicked)
        self._summary_table.setVisible(False)
        lay.addWidget(self._summary_table, stretch=1)

        self._summary_hint = QLabel("ดับเบิ้ลคลิกเพื่อเปิดโฟลเดอร์")
        self._summary_hint.setStyleSheet("color: #C7C7CC; font-size: 11px;")
        self._summary_hint.setVisible(False)
        lay.addWidget(self._summary_hint)

        return w

    def _on_summary_item_clicked(self, item, column):
        """Single-click on icon column (3) opens folder in Finder."""
        if column == 3:
            path = item.data(0, Qt.UserRole)
            if path and os.path.isdir(path):
                subprocess.run(["open", path], check=False)

    def _open_summary_folder(self, item, column):
        """Double-click on summary table row to open folder in Finder."""
        path = item.data(0, Qt.UserRole)
        if path and os.path.isdir(path):
            subprocess.run(["open", path], check=False)

    def _build_scan_step1(self) -> QWidget:
        """Step 1: scanning progress."""
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 30, 0, 0)

        self._scan_status_label = QLabel("กำลังสแกน...")
        self._scan_status_label.setStyleSheet(
            "font-size: 16px; font-weight: bold; color: #1D1D1F;"
        )
        lay.addWidget(self._scan_status_label)

        self._scan_progress = QProgressBar()
        self._scan_progress.setRange(0, 100)
        self._scan_progress.setStyleSheet("""
            QProgressBar {
                border: 1px solid #D2D2D7; border-radius: 7px;
                background: #F0F0F5; text-align: center;
                font-size: 10px; color: #636366;
            }
            QProgressBar::chunk {
                background: #F5811F; border-radius: 6px;
            }
        """)
        lay.addWidget(self._scan_progress)

        self._scan_detail_label = QLabel("")
        self._scan_detail_label.setStyleSheet("color: #86868B;")
        lay.addWidget(self._scan_detail_label)

        cancel_btn = QPushButton("ยกเลิก")
        cancel_btn.clicked.connect(self._cancel_scan)
        lay.addWidget(cancel_btn, alignment=Qt.AlignLeft)

        lay.addStretch()
        return w

    def _build_scan_step2(self) -> QWidget:
        """Step 2: cluster cards with name inputs."""
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        self._scan_result_summary = QLabel("")
        self._scan_result_summary.setStyleSheet(
            "font-size: 14px; font-weight: bold; color: #1D1D1F;"
        )
        lay.addWidget(self._scan_result_summary)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; }")

        self._cards_container = QWidget()
        self._cards_layout = QGridLayout(self._cards_container)
        self._cards_layout.setSpacing(8)
        self._cards_layout.setAlignment(Qt.AlignTop)

        scroll.setWidget(self._cards_container)
        lay.addWidget(scroll, stretch=1)

        # Destination selector
        self._scan_dest_row = self._build_destination_row()
        lay.addWidget(self._scan_dest_row)

        # Bottom buttons
        btn_row = QHBoxLayout()

        back_btn = QPushButton("← ย้อนกลับ")
        back_btn.clicked.connect(lambda: self._scan_stack.setCurrentIndex(0))
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

        self._execute_btn = QPushButton("ดำเนินการ")
        self._execute_btn.setStyleSheet("""
            QPushButton {
                background: #F5811F; color: white;
                padding: 10px 28px; border-radius: 8px;
                font-weight: bold; font-size: 14px; border: none;
            }
            QPushButton:hover { background: #E0710A; }
            QPushButton:disabled { background: #C7C7CC; }
        """)
        self._execute_btn.clicked.connect(self._execute_scan)
        btn_row.addWidget(self._execute_btn)

        lay.addLayout(btn_row)
        return w

    # -- Scan actions --

    def _start_scan(self):
        folders = self.folder_panel.get_checked_folder_paths()
        if not folders:
            QMessageBox.information(
                self, "แจ้งเตือน",
                "กรุณาเลือก (ติ๊ก) โฟลเดอร์ทางซ้ายอย่างน้อย 1 โฟลเดอร์",
            )
            return

        threshold = self.config.similarity_threshold

        # Hide summary from previous run
        self._summary_header.setVisible(False)
        self._summary_table.setVisible(False)
        self._summary_hint.setVisible(False)

        self._scan_stack.setCurrentIndex(1)
        self._scan_progress.setValue(0)
        self._scan_detail_label.setText("")

        self._scan_worker = ScanClusterWorker(folders, threshold)
        self._scan_worker.status_message.connect(
            lambda msg: self._scan_status_label.setText(msg)
        )
        self._scan_worker.progress.connect(self._on_scan_progress)
        self._scan_worker.finished_with_result.connect(self._on_scan_done)
        self._scan_worker.error.connect(self._on_scan_error)
        self._scan_worker.start()

    def _cancel_scan(self):
        if self._scan_worker:
            self._scan_worker.cancel()
        self._scan_stack.setCurrentIndex(0)

    def _on_scan_progress(self, current: int, total: int, msg: str):
        if total == 0:
            # Indeterminate mode (e.g. clustering phase)
            self._scan_progress.setRange(0, 0)
        else:
            self._scan_progress.setRange(0, 100)
            pct = int(current / max(total, 1) * 100)
            self._scan_progress.setValue(pct)
        self._scan_detail_label.setText(msg)

    def _on_scan_error(self, msg: str):
        QMessageBox.warning(self, "ข้อผิดพลาด", msg)
        self._scan_stack.setCurrentIndex(0)

    def _on_scan_done(self, result: dict):
        self._clusters = result.get("clusters", [])
        total_photos = result.get("total_photos", 0)
        total_faces = result.get("total_faces", 0)
        known = sum(1 for c in self._clusters if c["is_known"])
        unknown = len(self._clusters) - known

        self._scan_result_summary.setText(
            f"พบ {len(self._clusters)} คน จาก {total_faces} ใบหน้า "
            f"ใน {total_photos} รูป  "
            f"({known} คนในฐานข้อมูล, {unknown} คนใหม่)"
        )

        self._build_cluster_cards()
        self._scan_stack.setCurrentIndex(2)

        # Refresh folder tree to update face counts
        self.folder_panel._scan_subfolders()

    def _build_cluster_cards(self):
        while self._cards_layout.count():
            item = self._cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._name_inputs = []
        self._merge_checkboxes = []

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

        row = QHBoxLayout(card)
        row.setContentsMargins(10, 8, 10, 8)
        row.setSpacing(12)

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

        merge_cb = QCheckBox("เลือกเพื่อรวมเป็นคนเดียว")
        merge_cb.setStyleSheet("font-size: 11px; color: #86868B; border: none;")
        merge_cb.stateChanged.connect(lambda: self._update_merge_btn())
        info_col.addWidget(merge_cb)
        self._merge_checkboxes.append((merge_cb, index))

        name_row = QHBoxLayout()
        name_label = QLabel("ชื่อ")
        name_label.setStyleSheet("font-size: 13px; color: #424245;")
        name_label.setFixedWidth(15)
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

    def _update_merge_btn(self):
        checked = sum(1 for cb, _ in self._merge_checkboxes if cb.isChecked())
        self._merge_btn.setEnabled(checked >= 2)
        if checked >= 2:
            self._merge_btn.setText(f"รวม {checked} กลุ่มเป็นคนเดียว")
        else:
            self._merge_btn.setText("รวมเป็นคนเดียว")

    def _merge_selected(self):
        selected_indices = [idx for cb, idx in self._merge_checkboxes if cb.isChecked()]
        if len(selected_indices) < 2:
            return

        # Confirmation dialog
        reply = QMessageBox.question(
            self, "ยืนยันการรวม",
            f"ยืนยันรวม {len(selected_indices)} รายการเป็นคนเดียว?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        # Find the best base: prefer a cluster that has a name typed in the input
        base_idx = selected_indices[0]
        for idx in selected_indices:
            name_input, _ = self._name_inputs[idx]
            if name_input.text().strip():
                base_idx = idx
                break

        # Reorder so base is first, others merge into it
        other_indices = [idx for idx in selected_indices if idx != base_idx]

        base_cluster = self._clusters[base_idx]
        for idx in other_indices:
            other = self._clusters[idx]
            base_cluster["faces"].extend(other["faces"])
            if not base_cluster.get("thumbnail") and other.get("thumbnail"):
                base_cluster["thumbnail"] = other["thumbnail"]
            if other["is_known"]:
                base_cluster["is_known"] = True
                if other.get("person_id"):
                    base_cluster["person_id"] = other["person_id"]
            # If base has no name yet, take name from other
            if not base_cluster.get("person_name") and other.get("person_name"):
                base_cluster["person_name"] = other["person_name"]
            # Also check typed name from input
            other_input, _ = self._name_inputs[idx]
            base_input, _ = self._name_inputs[base_idx]
            if not base_input.text().strip() and other_input.text().strip():
                base_input.setText(other_input.text().strip())

        # Remove merged clusters (in reverse order to preserve indices)
        for idx in sorted(other_indices, reverse=True):
            self._clusters.pop(idx)

        # Rebuild cards and update summary
        self._update_scan_summary()
        self._build_cluster_cards()

    def _update_scan_summary(self):
        total_faces = sum(len(c["faces"]) for c in self._clusters)
        known = sum(1 for c in self._clusters if c["is_known"])
        unknown = len(self._clusters) - known
        self._scan_result_summary.setText(
            f"พบ {len(self._clusters)} คน จาก {total_faces} ใบหน้า  "
            f"({known} คนในฐานข้อมูล, {unknown} คนใหม่)"
        )

    def _execute_scan(self):
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

        self._scan_worker = ExecuteScanWorker(
            named, custom_dest_dir=self._get_custom_dest_dir(),
        )
        self._scan_worker.status_message.connect(
            lambda msg: self._scan_status_label.setText(msg)
        )
        self._scan_worker.progress.connect(self._on_exec_progress)
        self._scan_worker.finished_with_result.connect(self._on_exec_done)
        self._scan_worker.error.connect(self._on_exec_error)
        self._scan_worker.start()

    def _on_exec_progress(self, current: int, total: int, msg: str):
        self._execute_btn.setText(f"กำลังดำเนินการ... ({current}/{total})")

    def _on_exec_done(self, result: dict):
        self._execute_btn.setEnabled(True)
        self._execute_btn.setText("ดำเนินการ")

        added = result.get("persons_added", 0)
        copied = result.get("photos_copied", 0)
        total = result.get("total_processed", 0)
        person_details = result.get("person_details", [])

        if added > 0:
            self.person_changed.emit()

        # Refresh folder tree to show updated status
        self.folder_panel._scan_subfolders()

        # Go back to step 0 and show summary table
        self._scan_stack.setCurrentIndex(0)

        self._summary_header.setText(
            f"ดำเนินการเสร็จสิ้น — {total} คน, คัดลอก {copied} รูป"
            + (f", เพิ่มบุคคลใหม่ {added} คน" if added > 0 else "")
        )
        self._summary_header.setVisible(True)

        # Populate summary table
        self._summary_table.clear()
        for detail in person_details:
            name = detail["name"]
            copied_count = detail.get("copied", 0)
            folders = detail.get("output_folders", [])

            if folders:
                for folder_path in folders:
                    item = QTreeWidgetItem([
                        name,
                        str(copied_count),
                        folder_path,
                        "",
                    ])
                    item.setIcon(3, self.style().standardIcon(QStyle.SP_DirOpenIcon))
                    item.setData(0, Qt.UserRole, folder_path)
                    if detail.get("is_new"):
                        item.setForeground(0, Qt.darkGreen)
                    self._summary_table.addTopLevelItem(item)
                    # Only show count on first row for this person
                    copied_count = ""
            else:
                item = QTreeWidgetItem([name, str(copied_count), "—", ""])
                if detail.get("is_new"):
                    item.setForeground(0, Qt.darkGreen)
                self._summary_table.addTopLevelItem(item)

        self._summary_table.setVisible(True)
        self._summary_hint.setVisible(True)

    def _on_exec_error(self, msg: str):
        self._execute_btn.setEnabled(True)
        self._execute_btn.setText("ดำเนินการ")
        QMessageBox.warning(self, "ข้อผิดพลาด", msg)

    # -- Signal handlers --

    def _on_folder_changed(self, folder_path):
        self.refresh_data()

    def _on_processing_complete(self):
        self.refresh_data()
        self.processing_complete.emit()
