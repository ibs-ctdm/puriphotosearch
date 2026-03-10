"""Photo browser dialog for selecting a person reference photo."""

import os
from pathlib import Path
from functools import partial

from PySide6.QtCore import Qt, QSize, Signal, QThread
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QGridLayout,
)

from app.services.photo_processor import IMAGE_EXTENSIONS

THUMB_SIZE = 200
GRID_COLS = 4


class ThumbnailLoader(QThread):
    """Background thread to load thumbnails without blocking the UI."""

    thumbnail_ready = Signal(str, QPixmap)  # (file_path, pixmap)

    def __init__(self, image_paths: list, size: int = THUMB_SIZE, parent=None):
        super().__init__(parent)
        self._paths = image_paths
        self._size = size
        self._cancelled = False

    def run(self):
        for path in self._paths:
            if self._cancelled:
                break
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(
                    QSize(self._size, self._size),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
                self.thumbnail_ready.emit(path, scaled)

    def cancel(self):
        self._cancelled = True


class PhotoBrowserDialog(QDialog):
    """Dialog that lets users browse folders and pick a photo with large thumbnails."""

    def __init__(self, root_folder: str, parent=None):
        super().__init__(parent)
        self._root = root_folder
        self._current = root_folder
        self._selected_path = None
        self._loader = None

        self.setWindowTitle("เลือกรูปภาพ")
        self.resize(950, 680)
        self.setMinimumSize(700, 500)

        self._setup_ui()
        self._navigate(self._current)

    # ── UI ────────────────────────────────────────────────────────

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Navigation bar
        nav = QHBoxLayout()
        self.back_btn = QPushButton("← ย้อนกลับ")
        self.back_btn.setFixedWidth(110)
        self.back_btn.clicked.connect(self._go_back)
        nav.addWidget(self.back_btn)

        self.path_label = QLabel()
        self.path_label.setStyleSheet(
            "color: #424245; font-size: 13px; padding: 4px 8px;"
            "background: #F5F5F7; border-radius: 6px;"
        )
        nav.addWidget(self.path_label, stretch=1)
        layout.addLayout(nav)

        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self._grid_container = QWidget()
        self._grid = QGridLayout(self._grid_container)
        self._grid.setSpacing(12)
        self._grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        scroll.setWidget(self._grid_container)
        layout.addWidget(scroll, stretch=1)

        # Cancel button
        bottom = QHBoxLayout()
        bottom.addStretch()
        cancel_btn = QPushButton("ยกเลิก")
        cancel_btn.setFixedWidth(100)
        cancel_btn.clicked.connect(self.reject)
        bottom.addWidget(cancel_btn)
        layout.addLayout(bottom)

    # ── Navigation ────────────────────────────────────────────────

    def _navigate(self, folder_path: str):
        self._stop_loader()
        self._current = folder_path

        # Update path label (relative to root)
        try:
            rel = os.path.relpath(folder_path, self._root)
        except ValueError:
            rel = folder_path
        if rel == ".":
            rel = os.path.basename(self._root)
        self.path_label.setText(f"📁  {rel}")

        # Back button state
        self.back_btn.setEnabled(folder_path != self._root)

        # Clear grid
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        folder = Path(folder_path)

        # Collect subfolders and images
        subdirs = []
        images = []
        for entry in sorted(folder.iterdir()):
            if entry.name.startswith('.'):
                continue
            if entry.is_dir():
                subdirs.append(entry)
            elif entry.is_file() and entry.suffix.lower() in IMAGE_EXTENSIONS:
                images.append(str(entry))

        idx = 0

        # Folder cards
        for d in subdirs:
            card = self._make_folder_card(d)
            self._grid.addWidget(card, idx // GRID_COLS, idx % GRID_COLS)
            idx += 1

        # Image placeholders (thumbnails loaded async)
        self._thumb_labels = {}
        for img_path in images:
            card, label = self._make_image_card(img_path)
            self._grid.addWidget(card, idx // GRID_COLS, idx % GRID_COLS)
            self._thumb_labels[img_path] = label
            idx += 1

        # Load thumbnails in background
        if images:
            self._loader = ThumbnailLoader(images, THUMB_SIZE)
            self._loader.thumbnail_ready.connect(self._on_thumb_ready)
            self._loader.start()

    def _go_back(self):
        parent = os.path.dirname(self._current)
        if parent and self._current != self._root:
            self._navigate(parent)

    # ── Card builders ─────────────────────────────────────────────

    def _make_folder_card(self, dir_path: Path) -> QWidget:
        card = QWidget()
        card.setFixedSize(THUMB_SIZE + 10, THUMB_SIZE + 30)
        card.setStyleSheet(
            "QWidget { border: 1px solid #D2D2D7; border-radius: 10px;"
            "background: #F5F5F7; }"
            "QWidget:hover { background: #E8E8ED; border-color: #F5811F; }"
        )
        card.setCursor(Qt.PointingHandCursor)

        lay = QVBoxLayout(card)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(4)

        icon_label = QLabel("📁")
        icon_label.setStyleSheet("font-size: 48px; border: none;")
        icon_label.setAlignment(Qt.AlignCenter)
        lay.addWidget(icon_label, stretch=1)

        name_label = QLabel(dir_path.name)
        name_label.setStyleSheet(
            "font-size: 12px; font-weight: bold; color: #424245; border: none;"
        )
        name_label.setAlignment(Qt.AlignCenter)
        name_label.setWordWrap(True)
        lay.addWidget(name_label)

        # Count photos in this folder (direct only)
        count = sum(
            1 for f in dir_path.iterdir()
            if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS
        )
        if count > 0:
            count_label = QLabel(f"({count} รูป)")
            count_label.setStyleSheet("font-size: 11px; color: #86868B; border: none;")
            count_label.setAlignment(Qt.AlignCenter)
            lay.addWidget(count_label)

        card.mouseDoubleClickEvent = lambda e, p=str(dir_path): self._navigate(p)
        return card

    def _make_image_card(self, file_path: str):
        card = QWidget()
        card.setFixedSize(THUMB_SIZE + 10, THUMB_SIZE + 30)
        card.setStyleSheet(
            "QWidget { border: 1px solid #D2D2D7; border-radius: 10px;"
            "background: white; }"
            "QWidget:hover { border: 2px solid #F5811F; }"
        )
        card.setCursor(Qt.PointingHandCursor)

        lay = QVBoxLayout(card)
        lay.setContentsMargins(5, 5, 5, 3)
        lay.setSpacing(2)

        thumb_label = QLabel()
        thumb_label.setFixedSize(THUMB_SIZE, THUMB_SIZE)
        thumb_label.setAlignment(Qt.AlignCenter)
        thumb_label.setStyleSheet("border: none; background: #F5F5F7; border-radius: 6px;")
        thumb_label.setText("⏳")
        lay.addWidget(thumb_label, alignment=Qt.AlignCenter)

        name = os.path.basename(file_path)
        if len(name) > 22:
            name = name[:19] + "..."
        name_label = QLabel(name)
        name_label.setStyleSheet("font-size: 10px; color: #86868B; border: none;")
        name_label.setAlignment(Qt.AlignCenter)
        lay.addWidget(name_label)

        card.mousePressEvent = lambda e, p=file_path: self._select_image(p)
        return card, thumb_label

    # ── Events ────────────────────────────────────────────────────

    def _on_thumb_ready(self, path: str, pixmap: QPixmap):
        label = self._thumb_labels.get(path)
        if label and not label.isHidden():
            label.setPixmap(pixmap)

    def _select_image(self, path: str):
        self._selected_path = path
        self.accept()

    def get_selected_path(self) -> str | None:
        return self._selected_path

    # ── Cleanup ───────────────────────────────────────────────────

    def _stop_loader(self):
        if self._loader and self._loader.isRunning():
            self._loader.cancel()
            self._loader.wait(2000)
            self._loader = None

    def closeEvent(self, event):
        self._stop_loader()
        super().closeEvent(event)

    def reject(self):
        self._stop_loader()
        super().reject()
