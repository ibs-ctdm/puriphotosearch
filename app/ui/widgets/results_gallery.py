"""Photo grid results display with similarity scores, grouped by folder."""

import os
import sys
import subprocess

from PySide6.QtCore import Qt, QTimer, Property
from PySide6.QtGui import QPainter, QColor, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QGridLayout, QStyle,
)

from app.ui.widgets.photo_thumbnail import PhotoThumbnail


class ResultsGallery(QWidget):
    """Gallery widget showing search results grouped by folder."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Header
        self.header_label = QLabel("")
        self.header_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #1D1D1F;")
        layout.addWidget(self.header_label)

        self.detail_label = QLabel("")
        self.detail_label.setStyleSheet("color: #86868B;")
        layout.addWidget(self.detail_label)

        # Scroll area for folder sections
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("QScrollArea { border: none; }")

        self.scroll_content = QWidget()
        self.content_layout = QVBoxLayout(self.scroll_content)
        self.content_layout.setSpacing(12)
        self.content_layout.setAlignment(Qt.AlignTop)

        self.scroll.setWidget(self.scroll_content)
        layout.addWidget(self.scroll)

        # Loading overlay (hidden by default)
        self._loading_widget = SpinnerWidget(self.scroll)
        self._loading_widget.setVisible(False)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._loading_widget.isVisible():
            self._loading_widget.setGeometry(self.scroll.geometry())

    def show_loading(self, message="กำลังประมวลผล..."):
        """Show loading spinner overlay on the results area."""
        self._loading_widget.set_message(message)
        self._loading_widget.setGeometry(self.scroll.geometry())
        self._loading_widget.setVisible(True)
        self._loading_widget.raise_()
        self._loading_widget.start()

    def hide_loading(self):
        """Hide loading spinner overlay."""
        self._loading_widget.stop()
        self._loading_widget.setVisible(False)

    def clear(self):
        """Clear all results."""
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.header_label.setText("")
        self.detail_label.setText("")

    def show_folder_grouped_results(self, folder_results: list, person_name: str = None):
        """Display results grouped by source folder.

        Args:
            folder_results: list of dicts with keys:
                folder_name, folder_path, matches, open_folder, copied
            person_name: if single-person mode, the person's name
        """
        self.clear()

        folders_with_matches = [fr for fr in folder_results if fr.get("matches")]
        total_matches = sum(len(fr["matches"]) for fr in folders_with_matches)
        total_copied = sum(fr.get("copied", 0) for fr in folder_results)

        if not folders_with_matches:
            if person_name:
                self.header_label.setText(f"ไม่พบรูปภาพของ {person_name}")
            else:
                self.header_label.setText("ไม่พบรูปภาพ")
            return

        if person_name:
            self.header_label.setText(f"พบ {total_matches:,} รูปภาพของ {person_name}")
        else:
            self.header_label.setText(
                f"พบ {total_matches:,} รูปภาพ จาก {len(folders_with_matches):,} โฟลเดอร์"
            )

        if total_copied > 0:
            self.detail_label.setText(f"คัดลอก {total_copied:,} รูป")

        for fr in folders_with_matches:
            # Folder header (clickable to open output folder)
            header = self._make_folder_header(
                fr["folder_name"],
                len(fr["matches"]),
                fr.get("open_folder", fr["folder_path"]),
            )
            self.content_layout.addWidget(header)

            # Photo grid for this folder
            grid_widget = self._make_photo_grid(fr["matches"])
            self.content_layout.addWidget(grid_widget)

        self.content_layout.addStretch()

    def show_person_grouped_results(self, person_results: list):
        """Display results grouped by person.

        Args:
            person_results: list of dicts with keys:
                person_name, matches, folders [{display_name, path}], copied
        """
        self.clear()

        results_with_matches = [pr for pr in person_results if pr.get("matches")]
        total_matches = sum(len(pr["matches"]) for pr in results_with_matches)
        total_copied = sum(pr.get("copied", 0) for pr in person_results)

        if not results_with_matches:
            self.header_label.setText("ไม่พบรูปภาพ")
            return

        self.header_label.setText(
            f"พบ {total_matches:,} รูปภาพ ของ {len(results_with_matches):,} คน"
        )
        if total_copied > 0:
            self.detail_label.setText(f"คัดลอก {total_copied:,} รูป")

        for pr in results_with_matches:
            # Person name header
            person_label = QLabel(f"{pr['person_name']}  ({len(pr['matches']):,} รูป)")
            person_label.setStyleSheet(
                "font-size: 15px; font-weight: bold; color: #1D1D1F;"
                "padding: 8px 0 2px 0;"
            )
            self.content_layout.addWidget(person_label)

            # Folder buttons
            for folder_info in pr.get("folders", []):
                btn = self._make_folder_header(
                    folder_info["display_name"], 0, folder_info["path"],
                )
                self.content_layout.addWidget(btn)

            # Photo grid
            grid = self._make_photo_grid(pr["matches"])
            self.content_layout.addWidget(grid)

        self.content_layout.addStretch()

    def _make_folder_header(self, folder_name: str, match_count: int, open_folder: str) -> QWidget:
        """Create a clickable folder header row."""
        text = f"  {folder_name}  ({match_count:,} รูป)" if match_count else f"  {folder_name}"
        btn = QPushButton(text)
        btn.setIcon(self.style().standardIcon(QStyle.SP_DirOpenIcon))
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet("""
            QPushButton {
                text-align: left;
                font-size: 13px;
                font-weight: bold;
                color: #1D1D1F;
                border: none;
                background: #F5F5F7;
                border-radius: 6px;
                padding: 8px 12px;
            }
            QPushButton:hover {
                background: #FFF3E8;
                color: #F5811F;
            }
        """)
        if open_folder:
            btn.clicked.connect(lambda checked, p=open_folder: self._open_path(p))
        return btn

    def _make_photo_grid(self, matches: list, cols: int = 5) -> QWidget:
        """Create a grid of photo thumbnails."""
        grid_widget = QWidget()
        grid_layout = QGridLayout(grid_widget)
        grid_layout.setSpacing(8)
        grid_layout.setContentsMargins(0, 0, 0, 0)
        grid_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        for i, match in enumerate(matches):
            thumb = PhotoThumbnail(
                file_path=match["file_path"],
                size=150,
                similarity=match["similarity"],
            )
            thumb.clicked.connect(self._on_photo_clicked)
            grid_layout.addWidget(thumb, i // cols, i % cols)

        return grid_widget

    def _on_photo_clicked(self, file_path: str):
        """Open photo in default viewer."""
        if sys.platform == "darwin":
            subprocess.run(["open", file_path], check=False)
        elif sys.platform == "win32":
            os.startfile(file_path)
        else:
            subprocess.run(["xdg-open", file_path], check=False)

    def _open_path(self, path: str):
        """Open a folder in the system file manager."""
        if os.path.isdir(path):
            if sys.platform == "darwin":
                subprocess.run(["open", path], check=False)
            elif sys.platform == "win32":
                os.startfile(path)
            else:
                subprocess.run(["xdg-open", path], check=False)


class SpinnerWidget(QWidget):
    """Overlay widget with a spinning arc and status message."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._angle = 0
        self._message = "กำลังประมวลผล..."
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._rotate)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)

    def set_message(self, message: str):
        self._message = message
        self.update()

    def start(self):
        self._angle = 0
        self._timer.start(30)

    def stop(self):
        self._timer.stop()

    def _rotate(self):
        self._angle = (self._angle + 8) % 360
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Semi-transparent background
        painter.fillRect(self.rect(), QColor(255, 255, 255, 200))

        cx = self.width() / 2
        cy = self.height() / 2 - 20

        # Spinning arc
        arc_size = 48
        pen = painter.pen()
        pen.setWidth(4)
        pen.setColor(QColor("#F5811F"))
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        from PySide6.QtCore import QRectF
        arc_rect = QRectF(cx - arc_size / 2, cy - arc_size / 2, arc_size, arc_size)
        painter.drawArc(arc_rect, self._angle * 16, 270 * 16)

        # Message text
        painter.setPen(QColor("#1D1D1F"))
        font = QFont()
        font.setPointSize(14)
        painter.setFont(font)
        from PySide6.QtCore import QRect
        text_rect = QRect(0, int(cy + arc_size / 2 + 12), self.width(), 40)
        painter.drawText(text_rect, Qt.AlignHCenter | Qt.AlignTop, self._message)
