"""Photo grid results display with similarity scores."""

import os
import sys
import subprocess

from PySide6.QtCore import Qt, QTimer, Property
from PySide6.QtGui import QPainter, QColor, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QGridLayout,
)

from app.ui.widgets.photo_thumbnail import PhotoThumbnail


class ResultsGallery(QWidget):
    """Gallery widget showing search results as a grid of thumbnails."""

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

        # Open folder button
        btn_layout = QHBoxLayout()
        self.open_folder_btn = QPushButton("เปิดโฟลเดอร์ผลลัพธ์ใน Finder")
        self.open_folder_btn.setVisible(False)
        self.open_folder_btn.clicked.connect(self._open_folder)
        btn_layout.addWidget(self.open_folder_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # Scroll area for photo grid
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.grid_container = QWidget()
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setSpacing(8)
        self.grid_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        self.scroll.setWidget(self.grid_container)
        layout.addWidget(self.scroll)

        # Loading overlay (hidden by default)
        self._loading_widget = SpinnerWidget(self.scroll)
        self._loading_widget.setVisible(False)

        self._output_folder = None

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
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.header_label.setText("")
        self.detail_label.setText("")
        self.open_folder_btn.setVisible(False)
        self._output_folder = None

    def show_single_person_results(self, person_name: str, matches: list, organized: dict = None):
        """Display results for a single person search."""
        self.clear()

        if not matches:
            self.header_label.setText(f"ไม่พบรูปภาพของ {person_name}")
            return

        self.header_label.setText(f"พบ {len(matches)} รูปภาพของ {person_name}")

        if organized:
            self._output_folder = organized.get("output_folder")
            self.detail_label.setText(
                f"คัดลอก {organized['copied']} รูปไปที่: {self._output_folder}"
            )
            self.open_folder_btn.setVisible(True)

        self._populate_grid(matches)

    def show_all_persons_results(self, search_results: dict, organized: dict = None):
        """Display results for all-persons search."""
        self.clear()

        total_matches = sum(
            len(data["matches"]) for data in search_results.values()
        )
        persons_found = len(search_results)

        self.header_label.setText(
            f"พบ {total_matches} รูปภาพ จาก {persons_found} บุคคล"
        )

        if organized:
            self.detail_label.setText(
                f"จัดเรียง {organized['persons_organized']} โฟลเดอร์บุคคล, "
                f"คัดลอก {organized['total_copied']} รูปทั้งหมด"
            )

            if organized.get("details"):
                self._output_folder = organized["details"][0].get("output_folder", "")
                if self._output_folder:
                    import os
                    self._output_folder = os.path.dirname(self._output_folder)
                self.open_folder_btn.setVisible(True)

        # Show matches grouped by person
        all_matches = []
        for person_id, data in search_results.items():
            for match in data["matches"]:
                match["person_name"] = data["name"]
                all_matches.append(match)

        all_matches.sort(key=lambda x: x["similarity"], reverse=True)
        self._populate_grid(all_matches[:200])

    def _populate_grid(self, matches: list, cols: int = 5):
        for i, match in enumerate(matches):
            thumb = PhotoThumbnail(
                file_path=match["file_path"],
                size=150,
                similarity=match["similarity"],
            )
            thumb.clicked.connect(self._on_photo_clicked)
            self.grid_layout.addWidget(thumb, i // cols, i % cols)

    def _on_photo_clicked(self, file_path: str):
        """Open photo in default viewer."""
        if sys.platform == "darwin":
            subprocess.run(["open", file_path], check=False)
        elif sys.platform == "win32":
            os.startfile(file_path)
        else:
            subprocess.run(["xdg-open", file_path], check=False)

    def _open_folder(self):
        if self._output_folder:
            if sys.platform == "darwin":
                subprocess.run(["open", self._output_folder], check=False)
            elif sys.platform == "win32":
                os.startfile(self._output_folder)
            else:
                subprocess.run(["xdg-open", self._output_folder], check=False)


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
