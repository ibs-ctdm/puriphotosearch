"""Face crop dialog for selecting and cropping a face from a photo."""

import logging
import os
import tempfile

import cv2
import numpy as np

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPixmap, QImage, QPainter, QPen, QColor, QBrush
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QWidget, QMessageBox,
)

from app.services.face_service import face_service, _imread_safe

logger = logging.getLogger(__name__)

PREVIEW_SIZE = 200
FACE_PADDING = 0.35  # 35% padding around detected face bbox


class FaceImageWidget(QLabel):
    """Label that displays an image with clickable face rectangles drawn on top."""

    face_clicked = None  # will be set as a callback

    def __init__(self, pixmap: QPixmap, faces: list, parent=None):
        super().__init__(parent)
        self._original_pixmap = pixmap
        self._faces = faces  # list of [x1, y1, x2, y2]
        self._selected_idx = None
        self._scale = 1.0
        self.face_clicked = None  # callback(index)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self._render()

    def _render(self):
        """Scale pixmap to fit and draw face boxes on it."""
        max_w, max_h = 600, 500
        pw = self._original_pixmap.width()
        ph = self._original_pixmap.height()
        if pw == 0 or ph == 0:
            return
        self._scale = min(max_w / pw, max_h / ph, 1.0)
        disp_w = int(pw * self._scale)
        disp_h = int(ph * self._scale)

        # Create a display pixmap with boxes drawn on
        display = self._original_pixmap.scaled(
            QSize(disp_w, disp_h), Qt.KeepAspectRatio, Qt.SmoothTransformation,
        )

        painter = QPainter(display)
        painter.setRenderHint(QPainter.Antialiasing)

        for i, bbox in enumerate(self._faces):
            x1, y1, x2, y2 = [int(v * self._scale) for v in bbox]

            if i == self._selected_idx:
                pen = QPen(QColor("#F5811F"), 3)
                painter.setPen(pen)
                fill = QColor("#F5811F")
                fill.setAlpha(30)
                painter.setBrush(QBrush(fill))
            else:
                pen = QPen(QColor("#5BA4CF"), 2)
                painter.setPen(pen)
                painter.setBrush(Qt.NoBrush)

            painter.drawRect(x1, y1, x2 - x1, y2 - y1)

            # Label badge
            label = f"หน้า {i + 1}"
            label_y = max(y1 - 20, 0)
            painter.setPen(Qt.NoPen)
            bg_color = QColor("#F5811F") if i == self._selected_idx else QColor("#5BA4CF")
            painter.setBrush(QBrush(bg_color))
            painter.drawRoundedRect(x1, label_y, 50, 18, 4, 4)
            painter.setPen(QColor("white"))
            painter.drawText(x1 + 4, label_y + 13, label)

        painter.end()

        self.setPixmap(display)
        self.setFixedSize(display.size())

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return

        pos = event.position()
        x, y = pos.x(), pos.y()

        for i, bbox in enumerate(self._faces):
            x1, y1, x2, y2 = [int(v * self._scale) for v in bbox]
            if x1 <= x <= x2 and y1 <= y <= y2:
                self._selected_idx = i
                self._render()
                if self.face_clicked:
                    self.face_clicked(i)
                return

    @property
    def selected_index(self):
        return self._selected_idx

    def select_face(self, idx: int):
        self._selected_idx = idx
        self._render()


class FaceCropDialog(QDialog):
    """Dialog to detect faces and let the user crop a square face region."""

    def __init__(self, photo_path: str, parent=None):
        super().__init__(parent)
        self._photo_path = photo_path
        self._detection_results = []  # full results with embeddings
        self._faces = []  # bbox list only
        self._cv_image = None
        self._cropped_path = None
        self._selected_embedding = None

        self.setWindowTitle("เลือกใบหน้า")
        self.resize(850, 600)
        self.setMinimumSize(650, 450)

        self._load_image()
        self._detect_faces()
        self._setup_ui()

        # Auto-select if only one face
        if len(self._faces) == 1:
            self._on_face_selected(0)

    # ── Init ──────────────────────────────────────────────────────

    def _load_image(self):
        self._cv_image = _imread_safe(self._photo_path)

    def _detect_faces(self):
        try:
            self._detection_results = face_service.detect_faces(self._photo_path)
            self._faces = [r["bbox"] for r in self._detection_results]
        except Exception as e:
            logger.warning(f"Face detection failed: {e}")
            self._detection_results = []
            self._faces = []

    # ── UI ────────────────────────────────────────────────────────

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Header
        if self._faces:
            header_text = f"ตรวจพบ {len(self._faces)} ใบหน้า — กดที่กรอบเพื่อเลือกใบหน้า"
        else:
            header_text = "ไม่พบใบหน้าในภาพ — จะใช้รูปต้นฉบับทั้งรูป"
        header = QLabel(header_text)
        header.setStyleSheet("font-size: 14px; font-weight: bold; color: #1D1D1F;")
        layout.addWidget(header)

        # Main area: image + preview
        main = QHBoxLayout()

        # Left: image with face boxes (no scroll area — image is pre-scaled)
        pixmap = QPixmap(self._photo_path)
        self._face_widget = FaceImageWidget(pixmap, self._faces)
        self._face_widget.face_clicked = self._on_face_selected
        self._face_widget.setStyleSheet("background: #F5F5F7; border: none;")

        image_container = QWidget()
        image_container.setStyleSheet("background: #F5F5F7; border-radius: 8px;")
        img_layout = QVBoxLayout(image_container)
        img_layout.setAlignment(Qt.AlignCenter)
        img_layout.addWidget(self._face_widget)
        main.addWidget(image_container, stretch=3)

        # Right: preview panel
        right = QVBoxLayout()
        right.setSpacing(8)

        preview_title = QLabel("ตัวอย่างรูป crop")
        preview_title.setStyleSheet("font-weight: bold; color: #424245;")
        right.addWidget(preview_title)

        self._preview_label = QLabel()
        self._preview_label.setFixedSize(PREVIEW_SIZE, PREVIEW_SIZE)
        self._preview_label.setAlignment(Qt.AlignCenter)
        self._preview_label.setStyleSheet(
            "border: 2px dashed #D2D2D7; border-radius: 10px;"
            "background: #F5F5F7; color: #86868B;"
        )
        if self._faces:
            self._preview_label.setText("กดเลือกใบหน้า\nจากภาพด้านซ้าย")
        else:
            # No faces — show center-cropped preview
            self._show_center_crop_preview()
        right.addWidget(self._preview_label, alignment=Qt.AlignCenter)

        self._info_label = QLabel("")
        self._info_label.setStyleSheet("color: #86868B; font-size: 12px;")
        self._info_label.setWordWrap(True)
        right.addWidget(self._info_label)

        right.addStretch()
        main.addLayout(right, stretch=1)
        layout.addLayout(main, stretch=1)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("ยกเลิก")
        cancel_btn.setFixedWidth(100)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        self._use_btn = QPushButton("ใช้รูปนี้")
        self._use_btn.setFixedWidth(120)
        self._use_btn.setStyleSheet(
            "QPushButton { background: #F5811F; color: white;"
            "padding: 8px 18px; border-radius: 8px;"
            "font-weight: bold; font-size: 13px; border: none; }"
            "QPushButton:hover { background: #E0710A; }"
            "QPushButton:disabled { background: #C7C7CC; }"
        )
        if self._faces:
            self._use_btn.setEnabled(False)
        else:
            self._use_btn.setEnabled(True)
        self._use_btn.clicked.connect(self._confirm)
        btn_layout.addWidget(self._use_btn)
        layout.addLayout(btn_layout)

    # ── Face selection & crop ─────────────────────────────────────

    def _on_face_selected(self, idx: int):
        self._face_widget.select_face(idx)
        bbox = self._faces[idx]
        # Store the embedding for the selected face
        if idx < len(self._detection_results):
            self._selected_embedding = self._detection_results[idx].get("embedding")
        cropped = self._crop_face(bbox)
        if cropped is not None:
            self._show_preview(cropped)
            self._use_btn.setEnabled(True)
            w, h = cropped.shape[1], cropped.shape[0]
            self._info_label.setText(f"ขนาด crop: {w}x{h} px")

    def _crop_face(self, bbox) -> np.ndarray | None:
        """Crop a square region around the face bbox with padding."""
        if self._cv_image is None:
            return None

        img_h, img_w = self._cv_image.shape[:2]
        x1, y1, x2, y2 = bbox

        # Center of bbox
        cx = (x1 + x2) / 2
        cy = (y1 + y2) / 2
        bw = x2 - x1
        bh = y2 - y1

        # Square side = max(w, h) + padding
        side = max(bw, bh) * (1.0 + FACE_PADDING)
        half = side / 2

        # Square coords, clamped to image bounds
        sx1 = int(max(cx - half, 0))
        sy1 = int(max(cy - half, 0))
        sx2 = int(min(cx + half, img_w))
        sy2 = int(min(cy + half, img_h))

        return self._cv_image[sy1:sy2, sx1:sx2]

    def _show_preview(self, cv_crop: np.ndarray):
        """Show a cv2 BGR crop in the preview label."""
        rgb = cv2.cvtColor(cv_crop, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        qimg = QImage(rgb.data, w, h, w * ch, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(qimg).scaled(
            QSize(PREVIEW_SIZE, PREVIEW_SIZE),
            Qt.KeepAspectRatio, Qt.SmoothTransformation,
        )
        self._preview_label.setPixmap(pixmap)
        self._preview_label.setStyleSheet(
            "border: 2px solid #F5811F; border-radius: 10px;"
        )

    def _show_center_crop_preview(self):
        """When no faces detected, show a center-cropped preview."""
        if self._cv_image is None:
            return
        h, w = self._cv_image.shape[:2]
        side = min(h, w)
        y0 = (h - side) // 2
        x0 = (w - side) // 2
        center = self._cv_image[y0:y0 + side, x0:x0 + side]
        self._show_preview(center)

    # ── Confirm & save ────────────────────────────────────────────

    def _confirm(self):
        selected = self._face_widget.selected_index

        if selected is not None and self._faces:
            bbox = self._faces[selected]
            cropped = self._crop_face(bbox)
        elif self._cv_image is not None:
            # No face detected — use center crop
            h, w = self._cv_image.shape[:2]
            side = min(h, w)
            y0 = (h - side) // 2
            x0 = (w - side) // 2
            cropped = self._cv_image[y0:y0 + side, x0:x0 + side]
        else:
            self.reject()
            return

        if cropped is None or cropped.size == 0:
            QMessageBox.warning(self, "ข้อผิดพลาด", "ไม่สามารถ crop รูปได้")
            return

        # Save to temp file
        tmp = tempfile.NamedTemporaryFile(
            suffix=".jpg", prefix="face_crop_", delete=False,
        )
        tmp.close()
        success, buf = cv2.imencode(".jpg", cropped, [cv2.IMWRITE_JPEG_QUALITY, 95])
        if success:
            buf.tofile(tmp.name)
            self._cropped_path = tmp.name
            self.accept()
        else:
            QMessageBox.warning(self, "ข้อผิดพลาด", "ไม่สามารถบันทึกรูป crop ได้")

    def get_cropped_path(self) -> str | None:
        """Return the path to the cropped face image, or None."""
        return self._cropped_path

    def get_selected_embedding(self):
        """Return the embedding of the selected face, or None."""
        return self._selected_embedding
