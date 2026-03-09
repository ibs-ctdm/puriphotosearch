"""Photo grid results display with similarity scores."""

import subprocess

from PySide6.QtCore import Qt
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
        self.header_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(self.header_label)

        self.detail_label = QLabel("")
        self.detail_label.setStyleSheet("color: #666;")
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
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.grid_container = QWidget()
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setSpacing(8)
        self.grid_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        scroll.setWidget(self.grid_container)
        layout.addWidget(scroll)

        self._output_folder = None

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
        subprocess.run(["open", file_path], check=False)

    def _open_folder(self):
        if self._output_folder:
            subprocess.run(["open", self._output_folder], check=False)
