"""Panel 5: Usage instructions and credits."""

import os
import sys

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QFrame,
    QSplitter,
)

from app.config import APP_VERSION

# Resolve resource path — works both in dev and PyInstaller bundle
if getattr(sys, 'frozen', False):
    _BASE_DIR = sys._MEIPASS
else:
    _BASE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..")
_QR_PATH = os.path.join(_BASE_DIR, "promptpay.jpg")


class HelpPanel(QWidget):
    """Panel showing usage instructions and credits."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet("QSplitter::handle { background: #E5E5EA; }")

        # ── Left column: instructions ──
        splitter.addWidget(self._build_instructions())

        # ── Right column: donation ──
        splitter.addWidget(self._build_donation())

        # 2:1 ratio
        splitter.setSizes([660, 340])

        outer_layout.addWidget(splitter)

    def _build_instructions(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { border: none; background: white; }")

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 20, 24, 30)
        layout.setSpacing(20)

        # ── Title ──
        title = QLabel("วิธีใช้งาน")
        title.setStyleSheet("font-size: 22px; font-weight: bold; color: #1D1D1F;")
        layout.addWidget(title)

        subtitle = QLabel(f"Puri Photo Search v{APP_VERSION}")
        subtitle.setStyleSheet("font-size: 13px; color: #86868B; margin-top: -2px;")
        layout.addWidget(subtitle)

        # ── Overview ──
        layout.addWidget(self._section_title("ภาพรวม"))
        layout.addWidget(self._desc_label(
            "โปรแกรมมี 2 เมนูหลัก: \"สแกนรูปภาพ\" สำหรับสแกนและค้นหา, "
            "\"รายชื่อ\" สำหรับจัดการฐานข้อมูลบุคคล"
        ))

        # ── Mode 1: Scan first ──
        layout.addWidget(self._section_title("วิธีที่ 1: สแกนก่อนตั้งชื่อทีหลัง (แนะนำ)"))
        layout.addWidget(self._desc_label(
            "เหมาะสำหรับเริ่มใช้งานครั้งแรก หรือยังไม่ได้ลงทะเบียนบุคคลไว้ "
            "ให้ระบบสแกนและจัดกลุ่มใบหน้าให้อัตโนมัติ แล้วค่อยตั้งชื่อทีหลัง"
        ))
        layout.addWidget(self._step_list([
            ("1. เลือกโฟลเดอร์", "เลือกโฟลเดอร์หลักทางซ้าย แล้วติ๊กเลือกโฟลเดอร์ย่อยที่ต้องการ"),
            ("2. เปิดแท็บ \"สแกนก่อนตั้งชื่อทีหลัง\"", "เลือกแท็บนี้ทางขวา แล้วกด \"เริ่มสแกนใหม่\""),
            ("3. ตั้งชื่อบุคคล", "ระบบจะแสดงกลุ่มใบหน้าที่พบ พิมพ์ชื่อในช่องชื่อ (ไม่ตั้งชื่อ = ข้าม)"),
            ("4. เลือกปลายทาง", "เลือก \"ในโฟลเดอร์กิจกรรม\" เพื่อสร้างโฟลเดอร์ย่อยในที่เดิม หรือเลือก \"โฟลเดอร์ที่ระบุ\" เพื่อรวมรูปไปยังโฟลเดอร์ปลายทางที่ต้องการ"),
            ("5. กด \"ดำเนินการ\"", "ระบบจะคัดลอกรูปเข้าโฟลเดอร์ตามชื่อ และเพิ่มบุคคลใหม่เข้าฐานข้อมูลอัตโนมัติ"),
        ]))

        # ── Mode 2: Search from person list ──
        layout.addWidget(self._section_title("วิธีที่ 2: ค้นหาจากรายชื่อ"))
        layout.addWidget(self._desc_label(
            "เหมาะสำหรับกรณีที่ลงทะเบียนบุคคลไว้แล้ว ต้องการค้นหารูปจากโฟลเดอร์ใหม่"
        ))
        layout.addWidget(self._step_list([
            ("1. เพิ่มบุคคล", "ไปที่เมนู \"รายชื่อ\" กด \"+ เพิ่มบุคคล\" เลือกรูปหน้า แล้วตั้งชื่อ"),
            ("2. เลือกโฟลเดอร์", "กลับมาที่เมนู \"สแกนรูปภาพ\" เลือกโฟลเดอร์ทางซ้าย"),
            ("3. เปิดแท็บ \"ค้นหาจากรายชื่อ\"", "ติ๊กเลือกบุคคลที่ต้องการค้นหา"),
            ("4. เลือกปลายทาง", "เลือก \"ในโฟลเดอร์กิจกรรม\" เพื่อสร้างโฟลเดอร์ย่อยในที่เดิม หรือเลือก \"โฟลเดอร์ที่ระบุ\" เพื่อรวมรูปไปยังโฟลเดอร์ปลายทางที่ต้องการ"),
            ("5. กด \"ดำเนินการ\"", "ระบบจะค้นหาและคัดลอกรูปเข้าโฟลเดอร์ตามชื่อให้อัตโนมัติ"),
        ]))

        # ── Person management ──
        layout.addWidget(self._section_title("จัดการรายชื่อ"))
        layout.addWidget(self._desc_label(
            "เมนู \"รายชื่อ\" ใช้จัดการฐานข้อมูลบุคคล สร้างกลุ่ม และจัดหมวดหมู่"
        ))
        layout.addWidget(self._step_list([
            ("เพิ่ม/ลบ/แก้ไขบุคคล", "กด \"+ เพิ่มบุคคล\" เพื่อเพิ่มคนใหม่ หรือใช้ปุ่มบนการ์ดเพื่อแก้ไขชื่อ เพิ่มรูปอ้างอิง หรือลบ"),
            ("จัดกลุ่มบุคคล", "สร้างกลุ่มที่แถบซ้าย แล้วลากรูปบุคคลเข้ากลุ่มได้เลย หรือกดปุ่มจัดกลุ่มบนการ์ด"),
            ("สลับมุมมอง", "กดปุ่มมุมมองขวาบนเพื่อสลับระหว่างมุมมองการ์ดและมุมมองรายการ"),
            ("เลือกหลายรายการ", "กดปุ่ม \"เลือกหลายรายการ\" แล้วติ๊กเลือกบุคคลหลายคน จากนั้นลากเข้ากลุ่มพร้อมกันได้"),
        ]))

        # ── Tips ──
        layout.addWidget(self._section_title("เคล็ดลับ"))
        layout.addWidget(self._step_list([
            ("รูปอ้างอิง", "ใช้รูปที่เห็นหน้าชัดเจน หลายมุม จะช่วยให้ค้นหาแม่นยำขึ้น แนะนำ 1-3 รูปต่อคนเป็นอย่างน้อย"),
            ("ไม่ต้องสแกนซ้ำ", "หากเพิ่มบุคคลใหม่ ไม่ต้องสแกนโฟลเดอร์ซ้ำ สามารถค้นหาบุคคลใหม่ได้เลย"),
            ("Offline ทั้งหมด", "โปรแกรมทำงานแบบ Offline ไม่อัปโหลดรูปไปไหน รูปของคุณอยู่ในเครื่องตลอด"),
            ("รูปต้นฉบับปลอดภัย", "โปรแกรมแค่คัดลอกรูปเข้าโฟลเดอร์ย่อย ไม่ย้ายหรือลบรูปต้นฉบับ"),
        ]))

        layout.addStretch()
        scroll.setWidget(content)
        return scroll

    def _build_donation(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { border: none; background: #FAFAFA; }")

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(20, 20, 20, 30)
        layout.setSpacing(16)

        # ── Donation ──
        donation_title = self._section_title("สนับสนุนอุปกรณ์ในการทำงาน\nร่วมบุญค่า AI หรือเลี้ยงปานะทีมงาน")
        donation_title.setAlignment(Qt.AlignCenter)
        layout.addWidget(donation_title)

        donation_info = QLabel(
            "เลขที่บัญชี  152-0-20291-1\n"
            "พระอนวัช ภูริวโร\n"
            "ธนาคารกรุงไทย"
        )
        donation_info.setAlignment(Qt.AlignCenter)
        donation_info.setStyleSheet(
            "font-size: 14px; color: #1D1D1F; line-height: 1.6;"
        )
        layout.addWidget(donation_info)

        # QR Code
        if os.path.exists(_QR_PATH):
            qr_label = QLabel()
            qr_label.setAlignment(Qt.AlignCenter)
            pixmap = QPixmap(_QR_PATH)
            if not pixmap.isNull():
                pixmap = pixmap.scaled(
                    QSize(220, 220), Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
                qr_label.setPixmap(pixmap)
            qr_label.setStyleSheet("border: none; margin-top: 8px;")
            layout.addWidget(qr_label)

        slogan = QLabel(
            "ความสุขของผู้พัฒนา..\n คือได้สร้างโปรแกรม ที่มีประโยชน์กับทุกท่าน\n"
            "ทุกการสนับสนุนของท่าน คือกำลังใจสำคัญ ในการพัฒนาโปรแกรมต่อไป ขอบคุณทุกน้ำใจที่มอบให้กันนะ\n\n"
            "ปล. สแกนภาพจนเจอรูปที่ถูกใจแล้ว...\n"
            "อย่าลืมแวะมาสแกน QR Code ทำบุญด้วยนะ ^^"
        )
        slogan.setAlignment(Qt.AlignCenter)
        slogan.setWordWrap(True)
        slogan.setStyleSheet(
            "font-size: 15px; color: #1D1D1F;"
            "line-height: 2.0; margin-top: 16px;"
        )
        layout.addWidget(slogan)

        # ── Separator ──
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("background: #E5E5EA; max-height: 1px; border: none;")
        layout.addWidget(sep)

        # ── Credits ──
        credits_title = self._section_title("Designed and Developed by")
        credits_title.setAlignment(Qt.AlignCenter)
        layout.addWidget(credits_title)

        credit_label = QLabel("Purivaro")
        credit_label.setStyleSheet(
            "font-size: 16px; font-weight: bold; color: #1D1D1F;"
        )
        credit_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(credit_label)

        layout.addStretch()
        scroll.setWidget(content)
        return scroll

    def _section_title(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setStyleSheet(
            "font-size: 16px; font-weight: bold; color: #F5811F; margin-top: 4px;"
        )
        return label

    def _desc_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setStyleSheet("font-size: 13px; color: #86868B;")
        return label

    def _step_list(self, steps: list) -> QWidget:
        """Create a styled list of steps [(title, description), ...]."""
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        vbox = QVBoxLayout(container)
        vbox.setContentsMargins(8, 0, 0, 0)
        vbox.setSpacing(10)

        for step_title, step_desc in steps:
            row = QHBoxLayout()
            row.setSpacing(8)
            row.setAlignment(Qt.AlignTop)

            dot = QLabel("●")
            dot.setFixedWidth(14)
            dot.setStyleSheet("color: #F5811F; font-size: 10px; padding-top: 3px;")
            dot.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
            row.addWidget(dot)

            text_widget = QWidget()
            text_layout = QVBoxLayout(text_widget)
            text_layout.setContentsMargins(0, 0, 0, 0)
            text_layout.setSpacing(2)

            title_label = QLabel(step_title)
            title_label.setStyleSheet(
                "font-size: 13px; font-weight: bold; color: #1D1D1F;"
            )
            text_layout.addWidget(title_label)

            desc_label = QLabel(step_desc)
            desc_label.setWordWrap(True)
            desc_label.setStyleSheet("font-size: 13px; color: #636366;")
            text_layout.addWidget(desc_label)

            row.addWidget(text_widget, 1)
            vbox.addLayout(row)

        return container
