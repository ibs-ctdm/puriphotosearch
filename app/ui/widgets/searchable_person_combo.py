"""Select2-like searchable person combo with circular profile avatars."""

from PySide6.QtCore import Qt, QSize, QRectF, QSortFilterProxyModel
from PySide6.QtGui import (
    QPainter, QPainterPath, QPixmap, QImage, QColor, QFont,
    QStandardItemModel, QStandardItem,
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QComboBox, QStyledItemDelegate, QStyleOptionViewItem,
    QStyle,
)

AVATAR_SIZE = 28
ROW_HEIGHT = 36
AVATAR_MARGIN = 6
TEXT_MARGIN = 8

ROLE_THUMBNAIL = Qt.UserRole + 2
ROLE_PERSON_ID = Qt.UserRole + 3


class CircularAvatarDelegate(QStyledItemDelegate):
    """Paints each dropdown row with a circular avatar + person name."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cache: dict[int, QPixmap] = {}

    def clear_cache(self):
        self._cache.clear()

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        rect = option.rect

        # Hover / selected background
        if option.state & QStyle.StateFlag.State_MouseOver:
            painter.fillRect(rect, QColor("#FFF3E8"))
        else:
            painter.fillRect(rect, QColor("white"))

        # Get data
        name = index.data(Qt.DisplayRole) or ""
        thumbnail = index.data(ROLE_THUMBNAIL)
        person_id = index.data(ROLE_PERSON_ID)

        # Circular avatar (cached)
        avatar = self._get_avatar(person_id, thumbnail, name)
        avatar_y = rect.y() + (rect.height() - AVATAR_SIZE) // 2
        painter.drawPixmap(rect.x() + AVATAR_MARGIN, avatar_y, avatar)

        # Name text
        text_x = rect.x() + AVATAR_MARGIN + AVATAR_SIZE + TEXT_MARGIN
        text_rect = QRectF(
            text_x, rect.y(), rect.width() - text_x + rect.x(), rect.height()
        )
        painter.setPen(QColor("#1D1D1F"))
        font = QFont()
        font.setPixelSize(13)
        painter.setFont(font)
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, name)

        painter.restore()

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), ROW_HEIGHT)

    def _get_avatar(self, person_id, thumbnail: bytes, name: str) -> QPixmap:
        if person_id in self._cache:
            return self._cache[person_id]

        if thumbnail:
            px = self._make_circular_pixmap(thumbnail)
        else:
            px = self._make_initials_pixmap(name)

        if person_id is not None:
            self._cache[person_id] = px
        return px

    @staticmethod
    def _make_circular_pixmap(data: bytes) -> QPixmap:
        image = QImage.fromData(data)
        if image.isNull():
            return CircularAvatarDelegate._make_initials_pixmap("?")

        scaled = QPixmap.fromImage(image).scaled(
            QSize(AVATAR_SIZE, AVATAR_SIZE),
            Qt.KeepAspectRatioByExpanding,
            Qt.SmoothTransformation,
        )
        if scaled.width() > AVATAR_SIZE or scaled.height() > AVATAR_SIZE:
            x = (scaled.width() - AVATAR_SIZE) // 2
            y = (scaled.height() - AVATAR_SIZE) // 2
            scaled = scaled.copy(x, y, AVATAR_SIZE, AVATAR_SIZE)

        result = QPixmap(AVATAR_SIZE, AVATAR_SIZE)
        result.fill(Qt.transparent)

        painter = QPainter(result)
        painter.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addEllipse(QRectF(0, 0, AVATAR_SIZE, AVATAR_SIZE))
        painter.setClipPath(path)
        painter.drawPixmap(0, 0, scaled)
        painter.end()

        return result

    @staticmethod
    def _make_initials_pixmap(name: str) -> QPixmap:
        px = QPixmap(AVATAR_SIZE, AVATAR_SIZE)
        px.fill(Qt.transparent)

        painter = QPainter(px)
        painter.setRenderHint(QPainter.Antialiasing)

        painter.setBrush(QColor("#F5811F"))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QRectF(0, 0, AVATAR_SIZE, AVATAR_SIZE))

        painter.setPen(QColor("white"))
        font = QFont()
        font.setPixelSize(14)
        font.setBold(True)
        painter.setFont(font)
        initial = name[0].upper() if name else "?"
        painter.drawText(QRectF(0, 0, AVATAR_SIZE, AVATAR_SIZE), Qt.AlignCenter, initial)
        painter.end()

        return px


class PersonFilterProxyModel(QSortFilterProxyModel):
    """Substring filter that works with Thai names."""

    def filterAcceptsRow(self, source_row, source_parent):
        pattern = self.filterRegularExpression().pattern()
        if not pattern:
            return True
        index = self.sourceModel().index(source_row, 0, source_parent)
        name = index.data(Qt.DisplayRole) or ""
        return pattern.lower() in name.lower()


class SearchablePersonCombo(QWidget):
    """Editable combo box with avatar thumbnails and type-to-filter."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._combo = QComboBox()
        self._combo.setEditable(True)
        self._combo.setInsertPolicy(QComboBox.NoInsert)

        # Models
        self._source_model = QStandardItemModel()
        self._proxy_model = PersonFilterProxyModel()
        self._proxy_model.setSourceModel(self._source_model)
        self._proxy_model.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self._combo.setModel(self._proxy_model)

        # Delegate
        self._delegate = CircularAvatarDelegate(self._combo.view())
        self._combo.view().setItemDelegate(self._delegate)
        self._combo.view().setMinimumWidth(280)

        # Signals
        self._combo.lineEdit().textEdited.connect(self._on_text_edited)
        self._combo.activated.connect(self._on_item_activated)
        self._combo.lineEdit().editingFinished.connect(self._on_editing_finished)

        # Styling
        self._combo.setStyleSheet("""
            QComboBox {
                padding: 5px 10px;
                border: 1px solid #D2D2D7;
                border-radius: 8px;
                font-size: 13px;
                background: white;
            }
            QComboBox:focus, QComboBox:on {
                border-color: #F5811F;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 24px;
                border: none;
            }
            QComboBox QAbstractItemView {
                border: 1px solid #D2D2D7;
                border-radius: 8px;
                background: white;
                selection-background-color: #FFF3E8;
                outline: none;
            }
        """)

        layout.addWidget(self._combo)

        self._selected_index = -1

    # -- Filtering --

    def _on_text_edited(self, text):
        self._proxy_model.setFilterFixedString(text)
        if text and self._proxy_model.rowCount() > 0:
            self._combo.showPopup()
        elif not text:
            self._proxy_model.setFilterFixedString("")

    def _on_item_activated(self, proxy_index):
        source_index = self._proxy_model.mapToSource(
            self._proxy_model.index(proxy_index, 0)
        )
        self._selected_index = source_index.row()
        name = self._source_model.item(self._selected_index).text()
        self._combo.lineEdit().setText(name)
        self._proxy_model.setFilterFixedString("")

    def _on_editing_finished(self):
        self._proxy_model.setFilterFixedString("")
        if 0 <= self._selected_index < self._source_model.rowCount():
            item = self._source_model.item(self._selected_index)
            if item:
                self._combo.lineEdit().setText(item.text())

    # -- Public API (compatible with QComboBox usage in main_panel.py) --

    def currentIndex(self) -> int:
        return self._selected_index

    def currentData(self):
        if 0 <= self._selected_index < self._source_model.rowCount():
            item = self._source_model.item(self._selected_index)
            return item.data(Qt.UserRole)
        return None

    def findData(self, data) -> int:
        for row in range(self._source_model.rowCount()):
            item = self._source_model.item(row)
            if item.data(Qt.UserRole) == data:
                return row
        return -1

    def setCurrentIndex(self, index: int):
        self._selected_index = index
        if 0 <= index < self._source_model.rowCount():
            item = self._source_model.item(index)
            self._combo.lineEdit().setText(item.text())
        else:
            self._combo.lineEdit().clear()

    def clear(self):
        self._source_model.clear()
        self._delegate.clear_cache()
        self._selected_index = -1
        self._combo.lineEdit().clear()

    def addPersonItem(self, name: str, person_id: int, thumbnail: bytes = None):
        """Add a person with optional circular avatar thumbnail."""
        item = QStandardItem(name)
        item.setData(person_id, Qt.UserRole)
        item.setData(thumbnail, ROLE_THUMBNAIL)
        item.setData(person_id, ROLE_PERSON_ID)
        self._source_model.appendRow(item)

        if self._source_model.rowCount() == 1:
            self.setCurrentIndex(0)

    def setMinimumWidth(self, width):
        self._combo.setMinimumWidth(width)
