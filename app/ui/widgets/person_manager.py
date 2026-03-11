"""Panel 2: Person database CRUD management."""

import os

from PySide6.QtCore import Signal, Qt, QSize, QRect, QPoint, QRectF
from PySide6.QtGui import QPixmap, QImage, QIcon, QPainter, QPainterPath, QColor, QBrush
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QInputDialog, QMessageBox, QScrollArea,
    QGridLayout, QGroupBox, QDialog, QRadioButton, QButtonGroup,
    QLayout, QSizePolicy, QLineEdit, QSplitter, QListWidget,
    QListWidgetItem, QTreeWidget, QTreeWidgetItem, QHeaderView, QMenu,
)

from app.config import AppConfig
from app.database import (
    get_all_persons, delete_person, update_person_name,
    get_person_embeddings, delete_person_embedding, set_primary_embedding,
    get_all_groups, create_group, set_person_group, rename_group, delete_group,
)
from app.workers.person_worker import AddPersonWorker, AddEmbeddingWorker
from app.ui.widgets.person_card import (
    PersonCard, _make_icon, _draw_grid, _draw_list, _draw_folder,
    _draw_pencil, _draw_plus, _draw_trash,
)
from app.ui.widgets.progress_dialog import ProgressDialog
from app.ui.widgets.photo_browser_dialog import PhotoBrowserDialog
from app.ui.widgets.face_crop_dialog import FaceCropDialog
from app.ui.widgets.scan_mode_dialog import ScanModeDialog


class PersonManager(QWidget):
    """Panel for managing the person database (add, edit, delete persons)."""

    person_changed = Signal()  # emitted when persons are added/edited/deleted

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self._persons = []
        self._multi_select_mode = False
        self._selected_person_ids = set()
        self._drag_highlight_item = None
        config = AppConfig.load()
        self._current_view_mode = config.person_view_mode or "card"
        self._setup_ui()
        self.refresh_persons()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 15, 10, 10)
        layout.setSpacing(15)

        # Header
        header_layout = QHBoxLayout()
        title = QLabel("รายชื่อ")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #1D1D1F;")
        header_layout.addWidget(title)

        self.count_label = QLabel("")
        self.count_label.setStyleSheet("color: #86868B; font-size: 14px;")
        header_layout.addWidget(self.count_label)
        header_layout.addStretch()

        self.scan_btn = QPushButton("เพิ่มบุคคลจากการสแกนโฟลเดอร์")
        self.scan_btn.setStyleSheet("""
            QPushButton {
                background: #0F7B3F; color: white;
                padding: 8px 18px; border-radius: 8px;
                font-weight: bold; font-size: 13px; border: none;
            }
            QPushButton:hover { background: #0A5C2E; }
        """)
        self.scan_btn.clicked.connect(self._open_scan_mode)
        header_layout.addWidget(self.scan_btn)

        self.add_btn = QPushButton("+ เพิ่มบุคคล")
        self.add_btn.setStyleSheet("""
            QPushButton {
                background: #F5811F; color: white;
                padding: 8px 18px; border-radius: 8px;
                font-weight: bold; font-size: 13px; border: none;
            }
            QPushButton:hover { background: #E0710A; }
        """)
        self.add_btn.clicked.connect(self._add_person)
        header_layout.addWidget(self.add_btn)

        layout.addLayout(header_layout)

        # Splitter: left group sidebar | right content
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet("QSplitter::handle { background: #D2D2D7; }")

        # === LEFT: Group sidebar ===
        group_panel = QWidget()
        group_layout = QVBoxLayout(group_panel)
        group_layout.setContentsMargins(0, 0, 5, 0)
        group_layout.setSpacing(6)

        group_header = QHBoxLayout()
        group_title = QLabel("กลุ่ม")
        group_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #1D1D1F;")
        group_header.addWidget(group_title)
        group_hint = QLabel("(ลากรูปเข้ากลุ่มได้เลย)")
        group_hint.setStyleSheet("font-size: 11px; color: #86868B;")
        group_header.addWidget(group_hint)
        group_header.addStretch()

        add_group_btn = QPushButton("+ สร้างกลุ่ม")
        add_group_btn.setStyleSheet(
            "QPushButton { border: 1px solid #D2D2D7; border-radius: 4px;"
            "background: white; font-size: 12px; padding: 4px 8px; }"
            "QPushButton:hover { background: #F0F0F5; }"
        )
        add_group_btn.clicked.connect(self._create_group)
        group_header.addWidget(add_group_btn)
        group_layout.addLayout(group_header)

        self.group_list = QListWidget()
        self.group_list.setStyleSheet("""
            QListWidget {
                border: 1px solid #D2D2D7; border-radius: 8px;
                background: white; font-size: 13px;
            }
            QListWidget::item { padding: 6px 10px; }
            QListWidget::item:selected { background: #FFF3E8; color: #F5811F; }
            QListWidget::item:hover:!selected { background: #F5F5F7; }
        """)
        self.group_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.group_list.customContextMenuRequested.connect(self._group_context_menu)
        self.group_list.currentItemChanged.connect(self._on_group_selected)
        self.group_list.setAcceptDrops(True)
        self.group_list.setDragDropMode(QListWidget.DropOnly)
        self.group_list.dragEnterEvent = self._group_drag_enter
        self.group_list.dragMoveEvent = self._group_drag_move
        self.group_list.dropEvent = self._group_drop
        self.group_list.dragLeaveEvent = self._group_drag_leave
        group_layout.addWidget(self.group_list)

        splitter.addWidget(group_panel)

        # === RIGHT: Content area ===
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(5, 0, 0, 0)
        right_layout.setSpacing(8)

        # Search row + view toggle
        search_row = QHBoxLayout()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("ค้นหาบุคคล...")
        self.search_input.setMaximumWidth(250)
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setStyleSheet(
            "QLineEdit { padding: 8px 12px; border: 1px solid #D2D2D7;"
            "border-radius: 8px; font-size: 13px; background: white; }"
            "QLineEdit:focus { border-color: #F5811F; }"
        )
        self.search_input.textChanged.connect(self._filter_persons)
        search_row.addWidget(self.search_input)

        self._multi_select_btn = QPushButton("เลือกหลายรายการ")
        self._multi_select_btn.setCheckable(True)
        self._multi_select_btn.setCursor(Qt.PointingHandCursor)
        self._multi_select_btn.setStyleSheet(
            "QPushButton { border: 1px solid #D2D2D7; border-radius: 6px;"
            "background: white; font-size: 12px; padding: 6px 12px; }"
            "QPushButton:hover { background: #F0F0F5; }"
            "QPushButton:checked { background: #FFF3E8; border-color: #F5811F; color: #F5811F; }"
        )
        self._multi_select_btn.clicked.connect(self._toggle_multi_select)
        search_row.addWidget(self._multi_select_btn)

        search_row.addStretch()

        # View toggle buttons
        toggle_style = (
            "QPushButton { border: 1px solid #D2D2D7; border-radius: 6px; background: white; }"
            "QPushButton:hover { background: #F0F0F5; }"
            "QPushButton:checked { background: #FFF3E8; border-color: #F5811F; }"
        )

        self._card_view_btn = QPushButton()
        self._card_view_btn.setIconSize(QSize(18, 18))
        self._card_view_btn.setFixedSize(30, 30)
        self._card_view_btn.setToolTip("มุมมองการ์ด")
        self._card_view_btn.setCursor(Qt.PointingHandCursor)
        self._card_view_btn.setCheckable(True)
        self._card_view_btn.setStyleSheet(toggle_style)
        self._card_view_btn.clicked.connect(lambda: self._set_view_mode("card"))
        search_row.addWidget(self._card_view_btn)

        self._list_view_btn = QPushButton()
        self._list_view_btn.setIconSize(QSize(18, 18))
        self._list_view_btn.setFixedSize(30, 30)
        self._list_view_btn.setToolTip("มุมมองรายการ")
        self._list_view_btn.setCursor(Qt.PointingHandCursor)
        self._list_view_btn.setCheckable(True)
        self._list_view_btn.setStyleSheet(toggle_style)
        self._list_view_btn.clicked.connect(lambda: self._set_view_mode("list"))
        search_row.addWidget(self._list_view_btn)

        right_layout.addLayout(search_row)

        # Card view (scroll area)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.flow_container = QWidget()
        self.flow_layout = FlowLayout(self.flow_container, spacing=10)
        self._scroll.setWidget(self.flow_container)
        right_layout.addWidget(self._scroll)

        # List view (hidden by default)
        self._list_widget = QTreeWidget()
        self._list_widget.setHeaderLabels(["", "ชื่อ", "รูปอ้างอิง", "กลุ่ม", ""])
        self._list_widget.setRootIsDecorated(False)
        self._list_widget.setAlternatingRowColors(True)
        self._list_widget.setIconSize(QSize(36, 36))
        self._list_widget.header().setStretchLastSection(False)
        self._list_widget.header().setSectionResizeMode(0, QHeaderView.Fixed)
        self._list_widget.header().setSectionResizeMode(1, QHeaderView.Stretch)
        self._list_widget.header().setSectionResizeMode(2, QHeaderView.Fixed)
        self._list_widget.header().setSectionResizeMode(3, QHeaderView.Fixed)
        self._list_widget.header().setSectionResizeMode(4, QHeaderView.Fixed)
        self._list_widget.header().resizeSection(0, 44)
        self._list_widget.header().resizeSection(2, 80)
        self._list_widget.header().resizeSection(3, 100)
        self._list_widget.header().resizeSection(4, 140)
        self._list_widget.setStyleSheet("""
            QTreeWidget {
                border: 1px solid #D2D2D7; border-radius: 8px;
                background: white; font-size: 13px;
            }
            QTreeWidget::item { padding: 4px 2px; }
            QTreeWidget::item:hover { background: #FFF3E8; }
            QHeaderView::section {
                background: #FAFAFA; border: none;
                border-bottom: 1px solid #D2D2D7;
                padding: 6px 8px; font-weight: bold; font-size: 12px;
            }
        """)
        self._list_widget.setVisible(False)
        right_layout.addWidget(self._list_widget)

        splitter.addWidget(right_panel)
        splitter.setSizes([180, 600])

        layout.addWidget(splitter)

        # Apply initial view mode
        self._apply_view_mode()

    # ── View toggle ──

    def _apply_view_mode(self):
        is_card = self._current_view_mode == "card"
        self._card_view_btn.setChecked(is_card)
        self._list_view_btn.setChecked(not is_card)
        self._card_view_btn.setIcon(
            _make_icon(_draw_grid, "#F5811F" if is_card else "#8E8E93")
        )
        self._list_view_btn.setIcon(
            _make_icon(_draw_list, "#F5811F" if not is_card else "#8E8E93")
        )
        self._scroll.setVisible(is_card)
        self._list_widget.setVisible(not is_card)
        self._multi_select_btn.setVisible(is_card)

    def _set_view_mode(self, mode: str):
        self._current_view_mode = mode
        self._apply_view_mode()
        if mode == "list":
            self._populate_list_view()
            if self._multi_select_mode:
                self._multi_select_btn.setChecked(False)
                self._toggle_multi_select()
        # Save preference
        config = AppConfig.load()
        config.person_view_mode = mode
        config.save()

    # ── Group sidebar ──

    def _refresh_groups(self):
        self.group_list.blockSignals(True)
        current_data = None
        if self.group_list.currentItem():
            current_data = self.group_list.currentItem().data(Qt.UserRole)

        self.group_list.clear()

        # Count members per group
        group_counts = {}
        ungrouped_count = 0
        for p in self._persons:
            g = p.get("group_name")
            if g:
                group_counts[g] = group_counts.get(g, 0) + 1
            else:
                ungrouped_count += 1

        # "ทั้งหมด" always at top
        all_item = QListWidgetItem(f"ทั้งหมด ({len(self._persons)})")
        all_item.setData(Qt.UserRole, None)
        self.group_list.addItem(all_item)

        # Actual groups
        groups = get_all_groups()
        for group_name in groups:
            count = group_counts.get(group_name, 0)
            item = QListWidgetItem(f"{group_name} ({count})")
            item.setData(Qt.UserRole, group_name)
            self.group_list.addItem(item)

        # "ยังไม่จัดกลุ่ม" at the bottom
        ungrouped_item = QListWidgetItem(f"ยังไม่จัดกลุ่ม ({ungrouped_count})")
        ungrouped_item.setData(Qt.UserRole, "__ungrouped__")
        self.group_list.addItem(ungrouped_item)

        # Restore selection
        restored = False
        if current_data is not None:
            for i in range(self.group_list.count()):
                item = self.group_list.item(i)
                if item.data(Qt.UserRole) == current_data:
                    self.group_list.setCurrentRow(i)
                    restored = True
                    break
        if not restored:
            self.group_list.setCurrentRow(0)

        self.group_list.blockSignals(False)

    def _on_group_selected(self, current, previous):
        self._filter_persons_combined()

    def _group_drag_enter(self, event):
        if event.mimeData().hasFormat("application/x-person-id"):
            event.acceptProposedAction()
        else:
            event.ignore()

    def _group_drag_move(self, event):
        if event.mimeData().hasFormat("application/x-person-id"):
            event.acceptProposedAction()
            item = self.group_list.itemAt(event.position().toPoint())
            # Orange highlight on hovered group row
            if item != self._drag_highlight_item:
                if self._drag_highlight_item:
                    self._drag_highlight_item.setData(Qt.BackgroundRole, None)
                self._drag_highlight_item = None
                if item:
                    group_data = item.data(Qt.UserRole)
                    if group_data is not None:  # Not "ทั้งหมด"
                        item.setBackground(QBrush(QColor("#FFD9B3")))
                        self._drag_highlight_item = item
        else:
            event.ignore()

    def _group_drag_leave(self, event):
        if self._drag_highlight_item:
            self._drag_highlight_item.setData(Qt.BackgroundRole, None)
            self._drag_highlight_item = None

    def _group_drop(self, event):
        # Clear drag highlight
        if self._drag_highlight_item:
            self._drag_highlight_item.setData(Qt.BackgroundRole, None)
            self._drag_highlight_item = None

        if not event.mimeData().hasFormat("application/x-person-id"):
            event.ignore()
            return

        raw = event.mimeData().data("application/x-person-id").data().decode()
        person_ids = [int(x) for x in raw.split(",") if x.strip()]

        item = self.group_list.itemAt(event.position().toPoint())
        if not item:
            event.ignore()
            return

        group_data = item.data(Qt.UserRole)
        if group_data is None:
            # "ทั้งหมด" — ignore drop
            event.ignore()
            return

        for pid in person_ids:
            if group_data == "__ungrouped__":
                set_person_group(pid, None)
            else:
                set_person_group(pid, group_data)

        event.acceptProposedAction()
        # Clear multi-select after drop
        if self._multi_select_mode:
            self._selected_person_ids.clear()
        self.refresh_persons()

    def _create_group(self):
        name, ok = QInputDialog.getText(self, "สร้างกลุ่มใหม่", "ชื่อกลุ่ม:")
        if ok and name.strip():
            create_group(name.strip())
            self._refresh_groups()

    def _group_context_menu(self, pos):
        item = self.group_list.itemAt(pos)
        if not item:
            return
        group_data = item.data(Qt.UserRole)
        if group_data is None or group_data == "__ungrouped__":
            return

        menu = QMenu(self)
        rename_action = menu.addAction("เปลี่ยนชื่อกลุ่ม")
        delete_action = menu.addAction("ลบกลุ่ม")

        action = menu.exec(self.group_list.mapToGlobal(pos))
        if action == rename_action:
            new_name, ok = QInputDialog.getText(
                self, "เปลี่ยนชื่อกลุ่ม", "ชื่อกลุ่มใหม่:", text=group_data
            )
            if ok and new_name.strip() and new_name.strip() != group_data:
                rename_group(group_data, new_name.strip())
                self._refresh_groups()
                self.refresh_persons()
        elif action == delete_action:
            reply = QMessageBox.question(
                self, "ยืนยันการลบกลุ่ม",
                f"ลบกลุ่ม '{group_data}'?\n(บุคคลในกลุ่มจะไม่ถูกลบ เพียงถูกย้ายไป 'ยังไม่จัดกลุ่ม')",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                delete_group(group_data)
                self._refresh_groups()
                self.refresh_persons()

    def _assign_to_group(self, person_id: int, name: str):
        groups = get_all_groups()
        items = ["ลบออกจากกลุ่ม"] + groups + ["+ สร้างกลุ่มใหม่..."]
        # Find current group to pre-select
        current_group = None
        for p in self._persons:
            if p["id"] == person_id:
                current_group = p.get("group_name")
                break
        if current_group and current_group in groups:
            default_idx = items.index(current_group)
        else:
            default_idx = 0
        item, ok = QInputDialog.getItem(
            self, "จัดกลุ่ม",
            f"เลือกกลุ่มสำหรับ '{name}':",
            items, default_idx, False,
        )
        if not ok:
            return
        if item == "ยังไม่จัดกลุ่ม (ลบออกจากกลุ่ม)":
            set_person_group(person_id, None)
        elif item == "+ สร้างกลุ่มใหม่...":
            new_name, ok2 = QInputDialog.getText(self, "สร้างกลุ่มใหม่", "ชื่อกลุ่ม:")
            if ok2 and new_name.strip():
                create_group(new_name.strip())
                set_person_group(person_id, new_name.strip())
            else:
                return
        else:
            set_person_group(person_id, item)
        self.refresh_persons()
        self._refresh_groups()

    # ── Multi-select ──

    def _toggle_multi_select(self):
        self._multi_select_mode = self._multi_select_btn.isChecked()
        self._selected_person_ids.clear()
        for i in range(self.flow_layout.count()):
            item = self.flow_layout.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), PersonCard):
                item.widget().set_multi_select_mode(self._multi_select_mode)

    def _on_card_selected(self, person_id: int, selected: bool):
        if selected:
            self._selected_person_ids.add(person_id)
        else:
            self._selected_person_ids.discard(person_id)

    def _get_drag_person_ids(self, initiator_id: int) -> set:
        if self._multi_select_mode and self._selected_person_ids:
            ids = set(self._selected_person_ids)
            ids.add(initiator_id)
            return ids
        return {initiator_id}

    # ── Persons display ──

    def refresh_persons(self):
        """Reload all persons from database and rebuild the grid."""
        self._persons = get_all_persons()
        self.count_label.setText(f"({len(self._persons)} คน)")

        # Rebuild card view
        self.flow_container = QWidget()
        self.flow_layout = FlowLayout(self.flow_container, spacing=10)
        self._scroll.setWidget(self.flow_container)

        for person in self._persons:
            card = PersonCard(
                person_id=person["id"],
                name=person["name"],
                thumbnail=person.get("thumbnail"),
                embedding_count=person.get("embedding_count", 1),
                group_name=person.get("group_name"),
            )
            card.edit_clicked.connect(self._edit_person)
            card.delete_clicked.connect(self._delete_person)
            card.add_photo_clicked.connect(self._add_photo_to_person)
            card.manage_photos_clicked.connect(self._manage_photos)
            card.assign_group_clicked.connect(self._assign_to_group)
            card.selected_changed.connect(self._on_card_selected)
            card._get_drag_ids = self._get_drag_person_ids
            if self._multi_select_mode:
                card.set_multi_select_mode(True)
                if person["id"] in self._selected_person_ids:
                    card.set_selected(True)
            self.flow_layout.addWidget(card)

        self._refresh_groups()
        self._filter_persons_combined()

        # Also refresh list view if currently shown
        if self._current_view_mode == "list":
            self._populate_list_view()

    def _filter_persons(self, text: str):
        """Triggered by search input text change."""
        self._filter_persons_combined()

    def _filter_persons_combined(self):
        """Combined filter: group + search text, applies to card view."""
        search_query = self.search_input.text().strip().lower()
        selected_group = None
        if self.group_list.currentItem():
            selected_group = self.group_list.currentItem().data(Qt.UserRole)

        for i in range(self.flow_layout.count()):
            item = self.flow_layout.itemAt(i)
            if item and item.widget():
                card = item.widget()
                # Group filter
                group_match = True
                if selected_group == "__ungrouped__":
                    group_match = card.group_name is None
                elif selected_group is not None:
                    group_match = card.group_name == selected_group

                # Search filter
                search_match = not search_query or search_query in card.person_name.lower()

                card.setVisible(group_match and search_match)

        self.flow_layout.invalidate()
        self.flow_container.updateGeometry()

        # Also update list view if visible
        if self._current_view_mode == "list":
            self._populate_list_view()

    # ── List view ──

    def _populate_list_view(self):
        self._list_widget.clear()

        search_query = self.search_input.text().strip().lower()
        selected_group = None
        if self.group_list.currentItem():
            selected_group = self.group_list.currentItem().data(Qt.UserRole)

        for person in self._persons:
            # Apply group filter
            p_group = person.get("group_name")
            if selected_group == "__ungrouped__" and p_group is not None:
                continue
            if selected_group and selected_group != "__ungrouped__" and p_group != selected_group:
                continue
            # Apply search filter
            if search_query and search_query not in person["name"].lower():
                continue

            item = QTreeWidgetItem()
            item.setData(0, Qt.UserRole, person)

            # Column 0: circular thumbnail
            thumb = person.get("thumbnail")
            if thumb:
                img = QImage.fromData(thumb)
                if not img.isNull():
                    sz = 36
                    scaled = QPixmap.fromImage(img).scaled(
                        QSize(sz, sz), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
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

            # Column 1: name
            item.setText(1, person["name"])

            # Column 2: embedding count
            item.setText(2, str(person.get("embedding_count", 1)))

            # Column 3: group
            item.setText(3, person.get("group_name") or "—")

            self._list_widget.addTopLevelItem(item)

            # Column 4: action buttons
            actions = self._make_list_actions(person)
            self._list_widget.setItemWidget(item, 4, actions)

    def _make_list_actions(self, person: dict) -> QWidget:
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(2, 0, 2, 0)
        h.setSpacing(2)

        pid, pname = person["id"], person["name"]

        btn_style = (
            "QPushButton { border: none; background: transparent;"
            "border-radius: 4px; padding: 2px; }"
            "QPushButton:hover { background: #F0F0F5; }"
        )
        del_btn_style = (
            "QPushButton { border: none; background: transparent;"
            "border-radius: 4px; padding: 2px; }"
            "QPushButton:hover { background: #FFE5E5; }"
        )

        actions = [
            (_draw_pencil, "แก้ไขชื่อ", btn_style, lambda: self._edit_person(pid, pname)),
            (_draw_plus, "เพิ่มรูป", btn_style, lambda: self._add_photo_to_person(pid, pname)),
            (_draw_folder, "จัดกลุ่ม", btn_style, lambda: self._assign_to_group(pid, pname)),
            (_draw_trash, "ลบ", del_btn_style, lambda: self._delete_person(pid, pname)),
        ]

        for draw_fn, tip, style, callback in actions:
            btn = QPushButton()
            btn.setIcon(_make_icon(draw_fn, "#8E8E93"))
            btn.setIconSize(QSize(16, 16))
            btn.setFixedSize(28, 28)
            btn.setToolTip(tip)
            btn.setStyleSheet(style)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(callback)
            h.addWidget(btn)

        return w

    # ── Person CRUD actions ──

    def _browse_and_crop(self) -> tuple:
        """Open photo browser then face crop dialog.

        Returns (cropped_path, embedding) or (None, None).
        """
        config = AppConfig.load()
        root = config.main_photos_folder or os.path.expanduser("~")

        browser = PhotoBrowserDialog(root, self)
        if browser.exec() != QDialog.Accepted:
            return None, None
        photo_path = browser.get_selected_path()
        if not photo_path:
            return None, None

        crop_dialog = FaceCropDialog(photo_path, self)
        if crop_dialog.exec() != QDialog.Accepted:
            return None, None
        cropped = crop_dialog.get_cropped_path() or photo_path
        embedding = crop_dialog.get_selected_embedding()
        return cropped, embedding

    def _add_person(self):
        file_path, embedding = self._browse_and_crop()
        if not file_path:
            return

        name, ok = QInputDialog.getText(
            self, "ชื่อบุคคล",
            "กรอกชื่อบุคคล:",
        )
        if not ok or not name.strip():
            return

        name = name.strip()

        # Show progress
        self._progress = ProgressDialog("กำลังเพิ่มบุคคล", self)
        self._progress.set_status(f"กำลังประมวลผลใบหน้าของ {name}...")

        self._worker = AddPersonWorker(name, file_path, embedding=embedding)
        self._worker.status_message.connect(self._progress.set_status)
        self._worker.finished_with_result.connect(self._on_person_added)
        self._worker.error.connect(self._on_add_error)
        self._progress.cancelled.connect(self._worker.cancel)
        self._worker.start()
        self._progress.show()

    def _on_person_added(self, result):
        if hasattr(self, '_progress'):
            self._progress.close()
        self.refresh_persons()
        self.person_changed.emit()
        QMessageBox.information(
            self, "สำเร็จ",
            f"เพิ่มบุคคลแล้ว: {result['name']}",
        )

    def _on_add_error(self, message):
        if hasattr(self, '_progress'):
            self._progress.close()
        QMessageBox.warning(self, "ข้อผิดพลาด", message)

    def _open_scan_mode(self):
        dialog = ScanModeDialog(self)
        dialog.person_changed.connect(self._on_scan_persons_added)
        dialog.exec()

    def _on_scan_persons_added(self):
        self.refresh_persons()
        self.person_changed.emit()

    def _edit_person(self, person_id: int, current_name: str):
        new_name, ok = QInputDialog.getText(
            self, "แก้ไขชื่อบุคคล",
            "กรอกชื่อใหม่:",
            text=current_name,
        )
        if ok and new_name.strip() and new_name.strip() != current_name:
            update_person_name(person_id, new_name.strip())
            self.refresh_persons()
            self.person_changed.emit()

    def _delete_person(self, person_id: int, name: str):
        reply = QMessageBox.question(
            self, "ยืนยันการลบ",
            f"คุณแน่ใจหรือไม่ว่าต้องการลบ '{name}'?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            delete_person(person_id)
            self.refresh_persons()
            self.person_changed.emit()

    def _add_photo_to_person(self, person_id: int, name: str):
        file_path, embedding = self._browse_and_crop()
        if not file_path:
            return

        self._progress = ProgressDialog("กำลังเพิ่มรูปอ้างอิง", self)
        self._progress.set_status(f"กำลังประมวลผลใบหน้าเพิ่มเติมสำหรับ {name}...")

        self._worker = AddEmbeddingWorker(person_id, name, file_path, embedding=embedding)
        self._worker.status_message.connect(self._progress.set_status)
        self._worker.finished_with_result.connect(self._on_embedding_added)
        self._worker.error.connect(self._on_add_error)
        self._progress.cancelled.connect(self._worker.cancel)
        self._worker.start()
        self._progress.show()

    def _on_embedding_added(self, result):
        if hasattr(self, '_progress'):
            self._progress.close()
        self.refresh_persons()
        self.person_changed.emit()
        QMessageBox.information(
            self, "สำเร็จ",
            f"เพิ่มรูปอ้างอิงสำหรับ {result['person_name']} แล้ว",
        )

    def _manage_photos(self, person_id: int, name: str):
        dialog = EmbeddingsDialog(person_id, name, self)
        if dialog.exec():
            self.refresh_persons()
            self.person_changed.emit()


class FlowLayout(QLayout):
    """Layout that arranges widgets left-to-right, wrapping to the next row."""

    def __init__(self, parent=None, spacing=10):
        super().__init__(parent)
        self._items = []
        self._spacing = spacing

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), apply_geometry=False)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, apply_geometry=True)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        size += QSize(m.left() + m.right(), m.top() + m.bottom())
        return size

    def _do_layout(self, rect, apply_geometry):
        m = self.contentsMargins()
        effective = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x = effective.x()
        y = effective.y()
        row_height = 0

        for item in self._items:
            widget = item.widget()
            if widget and not widget.isVisible():
                continue

            w = item.sizeHint().width()
            h = item.sizeHint().height()

            if x + w > effective.right() + 1 and x > effective.x():
                x = effective.x()
                y += row_height + self._spacing
                row_height = 0

            if apply_geometry:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))

            x += w + self._spacing
            row_height = max(row_height, h)

        return y + row_height - rect.y() + m.bottom()


class EmbeddingsDialog(QDialog):
    """Dialog to view, delete, and set primary reference photo for a person."""

    def __init__(self, person_id: int, person_name: str, parent=None):
        super().__init__(parent)
        self.person_id = person_id
        self.person_name = person_name
        self._changed = False

        self.setWindowTitle(f"รูปอ้างอิงของ {person_name}")
        self.setMinimumSize(500, 400)

        layout = QVBoxLayout(self)

        header = QLabel(f"รูปอ้างอิงทั้งหมดของ {person_name}")
        header.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(header)

        desc = QLabel(
            "เลือก 'รูปหลัก' เพื่อใช้แสดงเป็นรูปประจำตัว  |  "
            "กด 'ลบ' เพื่อลบรูปที่ไม่ต้องการ (ต้องเหลืออย่างน้อย 1 รูป)"
        )
        desc.setStyleSheet("color: #86868B;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # Scroll area for embedding cards
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.grid_container = QWidget()
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setSpacing(10)
        self.grid_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        scroll.setWidget(self.grid_container)
        layout.addWidget(scroll)

        self.primary_group = QButtonGroup(self)
        self.primary_group.buttonClicked.connect(self._on_primary_changed)

        # Close button
        close_btn = QPushButton("ปิด")
        close_btn.setFixedWidth(100)
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignRight)

        self._load_embeddings()

    def _load_embeddings(self):
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Reset button group
        for btn in self.primary_group.buttons():
            self.primary_group.removeButton(btn)

        self._embeddings = get_person_embeddings(self.person_id)
        total = len(self._embeddings)

        for i, emb in enumerate(self._embeddings):
            card = QWidget()
            card.setFixedWidth(140)
            border_color = "#F5811F" if emb.get("is_primary") else "#D2D2D7"
            card.setStyleSheet(
                f"QWidget {{ border: 2px solid {border_color}; "
                f"border-radius: 10px; background: white; }}"
            )
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(6, 6, 6, 6)
            card_layout.setSpacing(4)

            # Thumbnail
            thumb_label = QLabel()
            thumb_label.setFixedSize(120, 120)
            thumb_label.setAlignment(Qt.AlignCenter)
            thumb_label.setStyleSheet("border: 1px solid #E8E8ED; border-radius: 6px;")
            if emb.get("thumbnail"):
                image = QImage.fromData(emb["thumbnail"])
                if not image.isNull():
                    pixmap = QPixmap.fromImage(image).scaled(
                        QSize(120, 120), Qt.KeepAspectRatio, Qt.SmoothTransformation
                    )
                    thumb_label.setPixmap(pixmap)
            else:
                thumb_label.setText("ไม่มีรูป")
            card_layout.addWidget(thumb_label, alignment=Qt.AlignCenter)

            # Bottom row: radio + delete side by side
            emb_id = emb["id"]
            bottom_row = QHBoxLayout()
            bottom_row.setContentsMargins(0, 0, 0, 0)
            bottom_row.setSpacing(2)

            radio = QRadioButton("รูปหลัก")
            radio.setStyleSheet("font-size: 11px; border: none;")
            radio.setProperty("emb_id", emb_id)
            if emb.get("is_primary"):
                radio.setChecked(True)
            self.primary_group.addButton(radio)
            bottom_row.addWidget(radio)

            del_btn = QPushButton("ลบ")
            del_btn.setFixedSize(44, 26)
            del_btn.setStyleSheet(
                "font-size: 12px; color: #FF3B30; font-weight: bold;"
                "border: 1px solid #FF3B30; border-radius: 4px;"
                "background: white;"
            )
            del_btn.clicked.connect(
                lambda checked, eid=emb_id: self._delete_embedding(eid)
            )
            if total <= 1:
                del_btn.setEnabled(False)
                del_btn.setToolTip("ต้องมีอย่างน้อย 1 รูปอ้างอิง")
            bottom_row.addWidget(del_btn)

            card_layout.addLayout(bottom_row)

            self.grid_layout.addWidget(card, i // 3, i % 3)

    def _on_primary_changed(self, button):
        emb_id = button.property("emb_id")
        set_primary_embedding(self.person_id, emb_id)
        self._changed = True
        self._load_embeddings()

    def _delete_embedding(self, embedding_id: int):
        reply = QMessageBox.question(
            self, "ยืนยันการลบ",
            "ต้องการลบรูปอ้างอิงนี้หรือไม่?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            # If deleting primary, reassign to first remaining
            emb = next((e for e in self._embeddings if e["id"] == embedding_id), None)
            was_primary = emb and emb.get("is_primary")
            delete_person_embedding(embedding_id)
            if was_primary:
                remaining = get_person_embeddings(self.person_id)
                if remaining:
                    set_primary_embedding(self.person_id, remaining[0]["id"])
            self._changed = True
            self._load_embeddings()

    def accept(self):
        if self._changed:
            super().accept()
        else:
            super().reject()
