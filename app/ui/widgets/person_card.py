"""Individual person card widget for the person manager grid."""

from PySide6.QtCore import Signal, Qt, QSize, QRect, QPointF, QMimeData
from PySide6.QtGui import (
    QPixmap, QImage, QIcon, QPainter, QPen, QColor, QPainterPath, QDrag,
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
)

CARD_W = 150
PHOTO_MARGIN = 6
PHOTO_SIZE = CARD_W - PHOTO_MARGIN * 2
ICON_SIZE = 18


class _SelectIndicator(QWidget):
    """Custom checkbox: orange rounded box with white checkmark when checked."""

    toggled = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._checked = False
        self.setFixedSize(24, 24)
        self.setCursor(Qt.PointingHandCursor)

    def isChecked(self):
        return self._checked

    def setChecked(self, checked):
        if self._checked != checked:
            self._checked = checked
            self.toggled.emit(checked)
            self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        s = self.width()

        if self._checked:
            # Orange filled rounded rect
            p.setBrush(QColor("#F5811F"))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(2, 2, s - 4, s - 4, 5, 5)
            # White checkmark
            pen = QPen(QColor("white"))
            pen.setWidthF(2.5)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            p.setPen(pen)
            p.drawLine(QPointF(s * 0.22, s * 0.50), QPointF(s * 0.42, s * 0.72))
            p.drawLine(QPointF(s * 0.42, s * 0.72), QPointF(s * 0.78, s * 0.28))
        else:
            # Empty rounded rect with border
            pen = QPen(QColor(180, 180, 180, 230))
            pen.setWidthF(2)
            p.setPen(pen)
            p.setBrush(QColor(255, 255, 255, 217))
            p.drawRoundedRect(2, 2, s - 4, s - 4, 5, 5)

        p.end()


# ── Vector icon factory ──────────────────────────────────────────

def _make_icon(draw_fn, color: str, size: int = ICON_SIZE) -> QIcon:
    """Create a QIcon by painting with QPainter."""
    px = QPixmap(size, size)
    px.fill(Qt.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(color))
    pen.setWidthF(1.6)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    draw_fn(p, size)
    p.end()
    return QIcon(px)


def _draw_plus(p: QPainter, s: int):
    m = s * 0.25
    c = s / 2
    p.drawLine(QPointF(c, m), QPointF(c, s - m))
    p.drawLine(QPointF(m, c), QPointF(s - m, c))


def _draw_pencil(p: QPainter, s: int):
    # Simple pencil: diagonal line + small triangle tip
    p.drawLine(QPointF(s * 0.7, s * 0.15), QPointF(s * 0.2, s * 0.65))
    p.drawLine(QPointF(s * 0.2, s * 0.65), QPointF(s * 0.15, s * 0.85))
    p.drawLine(QPointF(s * 0.15, s * 0.85), QPointF(s * 0.35, s * 0.8))
    p.drawLine(QPointF(s * 0.35, s * 0.8), QPointF(s * 0.85, s * 0.3))
    p.drawLine(QPointF(s * 0.85, s * 0.3), QPointF(s * 0.7, s * 0.15))


def _draw_grid(p: QPainter, s: int):
    m = s * 0.15
    e = s - m
    mid = s / 2
    # Outer rect
    p.drawRoundedRect(QRect(int(m), int(m), int(e - m), int(e - m)), 2, 2)
    # Cross lines
    p.drawLine(QPointF(mid, m), QPointF(mid, e))
    p.drawLine(QPointF(m, mid), QPointF(e, mid))


def _draw_folder(p: QPainter, s: int):
    # Folder body
    p.drawLine(QPointF(s * 0.12, s * 0.30), QPointF(s * 0.12, s * 0.82))
    p.drawLine(QPointF(s * 0.12, s * 0.82), QPointF(s * 0.88, s * 0.82))
    p.drawLine(QPointF(s * 0.88, s * 0.82), QPointF(s * 0.88, s * 0.35))
    p.drawLine(QPointF(s * 0.88, s * 0.35), QPointF(s * 0.52, s * 0.35))
    # Folder tab
    p.drawLine(QPointF(s * 0.52, s * 0.35), QPointF(s * 0.45, s * 0.22))
    p.drawLine(QPointF(s * 0.45, s * 0.22), QPointF(s * 0.12, s * 0.22))
    p.drawLine(QPointF(s * 0.12, s * 0.22), QPointF(s * 0.12, s * 0.30))


def _draw_list(p: QPainter, s: int):
    """Three horizontal lines (list icon)."""
    m = s * 0.2
    e = s - m
    for y_frac in [0.28, 0.50, 0.72]:
        y = s * y_frac
        p.drawLine(QPointF(m, y), QPointF(e, y))


def _draw_trash(p: QPainter, s: int):
    # Lid
    p.drawLine(QPointF(s * 0.2, s * 0.25), QPointF(s * 0.8, s * 0.25))
    p.drawLine(QPointF(s * 0.38, s * 0.25), QPointF(s * 0.38, s * 0.15))
    p.drawLine(QPointF(s * 0.38, s * 0.15), QPointF(s * 0.62, s * 0.15))
    p.drawLine(QPointF(s * 0.62, s * 0.15), QPointF(s * 0.62, s * 0.25))
    # Body
    p.drawLine(QPointF(s * 0.27, s * 0.25), QPointF(s * 0.3, s * 0.85))
    p.drawLine(QPointF(s * 0.3, s * 0.85), QPointF(s * 0.7, s * 0.85))
    p.drawLine(QPointF(s * 0.7, s * 0.85), QPointF(s * 0.73, s * 0.25))
    # Inner lines
    p.drawLine(QPointF(s * 0.42, s * 0.38), QPointF(s * 0.42, s * 0.72))
    p.drawLine(QPointF(s * 0.58, s * 0.38), QPointF(s * 0.58, s * 0.72))


class PersonCard(QFrame):
    """Card: padded image → name → icon toolbar, all inside a rounded card."""

    edit_clicked = Signal(int, str)
    delete_clicked = Signal(int, str)
    add_photo_clicked = Signal(int, str)
    manage_photos_clicked = Signal(int, str)
    assign_group_clicked = Signal(int, str)
    selected_changed = Signal(int, bool)

    def __init__(self, person_id: int, name: str, thumbnail: bytes = None,
                 embedding_count: int = 1, group_name: str = None, parent=None):
        super().__init__(parent)
        self.person_id = person_id
        self.person_name = name
        self.group_name = group_name
        self._multi_select = False
        self._get_drag_ids = None
        self._was_drag = False
        self._press_on_card = False

        self.setFixedWidth(CARD_W)
        self.setObjectName("personCard")
        self.setStyleSheet("""
            QFrame#personCard {
                border: 1px solid #D2D2D7;
                border-radius: 12px;
                background: white;
            }
            QFrame#personCard:hover {
                border: 1.5px solid #F5811F;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(PHOTO_MARGIN, PHOTO_MARGIN, PHOTO_MARGIN, 4)
        layout.setSpacing(0)

        # ── Photo with badge ──
        photo_container = QWidget()
        photo_container.setFixedSize(PHOTO_SIZE, PHOTO_SIZE)
        photo_container.setStyleSheet("border: none; background: transparent;")

        self.photo_label = QLabel(photo_container)
        self.photo_label.setFixedSize(PHOTO_SIZE, PHOTO_SIZE)
        self.photo_label.setAlignment(Qt.AlignCenter)
        self.photo_label.setStyleSheet(
            "background: #F0F0F5; border: none; border-radius: 8px;"
        )
        self.photo_label.move(0, 0)

        if embedding_count > 1:
            badge = QLabel(str(embedding_count), photo_container)
            badge.setFixedSize(22, 22)
            badge.setAlignment(Qt.AlignCenter)
            badge.setStyleSheet(
                "background: #F5811F; color: white; font-size: 10px;"
                "font-weight: bold; border-radius: 11px; border: 2px solid white;"
            )
            badge.move(PHOTO_SIZE - 20, 2)
            badge.raise_()
            badge.setCursor(Qt.PointingHandCursor)
            badge.mousePressEvent = (
                lambda e: self.manage_photos_clicked.emit(self.person_id, self.person_name)
            )

        # Selection indicator (hidden by default, shown in multi-select mode)
        self._select_cb = _SelectIndicator(photo_container)
        self._select_cb.move(4, 4)
        self._select_cb.setVisible(False)
        self._select_cb.toggled.connect(self._on_select_toggled)
        self._select_cb.raise_()

        layout.addWidget(photo_container, alignment=Qt.AlignCenter)

        if thumbnail:
            self._set_thumbnail(thumbnail)
        else:
            self.photo_label.setText("ไม่มีรูป")
            self.photo_label.setStyleSheet(
                "background: #F0F0F5; color: #86868B; font-size: 12px;"
                "border: none; border-radius: 8px;"
            )

        # ── Name ──
        self.name_label = QLabel(name)
        self.name_label.setAlignment(Qt.AlignCenter)
        self.name_label.setWordWrap(True)
        self.name_label.setStyleSheet(
            "font-weight: bold; font-size: 13px; color: #1D1D1F;"
            "padding: 5px 4px 2px 4px; border: none;"
        )
        layout.addWidget(self.name_label)

        # ── Separator ──
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("background: #EBEBEB; max-height: 1px; border: none;")
        layout.addWidget(sep)

        # ── Icon toolbar (vector icons) ──
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(0)
        btn_layout.setContentsMargins(0, 1, 0, 1)

        normal_color = "#8E8E93"
        buttons = [
            (_draw_plus, normal_color, "เพิ่มรูปอ้างอิง", False, self.add_photo_clicked),
            (_draw_pencil, normal_color, "แก้ไขชื่อ", False, self.edit_clicked),
            (_draw_grid, normal_color, "จัดการรูปอ้างอิง", False, self.manage_photos_clicked),
            (_draw_folder, normal_color, "จัดกลุ่ม", False, self.assign_group_clicked),
            (_draw_trash, normal_color, "ลบบุคคล", True, self.delete_clicked),
        ]

        btn_style = (
            "QPushButton { border: none; background: transparent;"
            "border-radius: 6px; padding: 4px 0; }"
            "QPushButton:hover { background: #F0F0F5; }"
        )
        del_btn_style = (
            "QPushButton { border: none; background: transparent;"
            "border-radius: 6px; padding: 4px 0; }"
            "QPushButton:hover { background: #FFE5E5; }"
        )

        for draw_fn, color, tip, is_del, signal in buttons:
            icon = _make_icon(draw_fn, color)
            btn = QPushButton()
            btn.setIcon(icon)
            btn.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
            btn.setToolTip(tip)
            btn.setFixedHeight(28)
            btn.setStyleSheet(del_btn_style if is_del else btn_style)
            btn.setCursor(Qt.PointingHandCursor)
            pid, pname = self.person_id, self.person_name
            btn.clicked.connect(lambda _, s=signal, i=pid, n=pname: s.emit(i, n))
            btn_layout.addWidget(btn, 1)

        layout.addLayout(btn_layout)

    def _set_thumbnail(self, data: bytes):
        image = QImage.fromData(data)
        if not image.isNull():
            pixmap = QPixmap.fromImage(image).scaled(
                QSize(PHOTO_SIZE, PHOTO_SIZE),
                Qt.KeepAspectRatioByExpanding,
                Qt.SmoothTransformation,
            )
            # Center-crop to fill
            if pixmap.width() > PHOTO_SIZE or pixmap.height() > PHOTO_SIZE:
                x = (pixmap.width() - PHOTO_SIZE) // 2
                y = (pixmap.height() - PHOTO_SIZE) // 2
                pixmap = pixmap.copy(x, y, PHOTO_SIZE, PHOTO_SIZE)
            self.photo_label.setPixmap(pixmap)

    def update_name(self, new_name: str):
        self.person_name = new_name
        self.name_label.setText(new_name)

    # ── Multi-select support ──

    def set_multi_select_mode(self, enabled: bool):
        self._multi_select = enabled
        self._select_cb.setVisible(enabled)
        if not enabled:
            self._select_cb.setChecked(False)

    def set_selected(self, selected: bool):
        self._select_cb.setChecked(selected)

    @property
    def is_selected(self):
        return self._select_cb.isChecked()

    def _on_select_toggled(self, checked: bool):
        self.selected_changed.emit(self.person_id, checked)

    # ── Drag & drop ──

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start = event.pos()
            self._was_drag = False
            self._press_on_card = True
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.LeftButton) or not hasattr(self, '_drag_start'):
            return
        if (event.pos() - self._drag_start).manhattanLength() < 20:
            return
        self._was_drag = True
        drag = QDrag(self)
        mime = QMimeData()
        # Multi-select: include all selected IDs
        if self._get_drag_ids:
            drag_ids = self._get_drag_ids(self.person_id)
        else:
            drag_ids = {self.person_id}
        mime.setData("application/x-person-id",
                     ",".join(str(i) for i in drag_ids).encode())
        mime.setText(self.person_name)
        drag.setMimeData(mime)
        px = self.grab().scaled(QSize(80, 80), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        if len(drag_ids) > 1:
            painter = QPainter(px)
            painter.setRenderHint(QPainter.Antialiasing)
            badge_sz = 24
            badge_rect = QRect(px.width() - badge_sz, 0, badge_sz, badge_sz)
            painter.setBrush(QColor("#F5811F"))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(badge_rect)
            painter.setPen(QColor("white"))
            f = painter.font()
            f.setPixelSize(13)
            f.setBold(True)
            painter.setFont(f)
            painter.drawText(badge_rect, Qt.AlignCenter, str(len(drag_ids)))
            painter.end()
        drag.setPixmap(px)
        drag.exec(Qt.MoveAction)

    def mouseReleaseEvent(self, event):
        if (event.button() == Qt.LeftButton
                and self._multi_select
                and self._press_on_card
                and not self._was_drag):
            self._select_cb.setChecked(not self._select_cb.isChecked())
        self._press_on_card = False
        self._was_drag = False
        super().mouseReleaseEvent(event)
