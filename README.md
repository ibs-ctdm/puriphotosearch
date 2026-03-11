# PuriPhotoSearch

โปรแกรมค้นหาและจัดเรียงรูปภาพด้วยการจดจำใบหน้า สำหรับ macOS

![PuriPhotoSearch](PuriPhotoSearch.png)

## ความสามารถ

- **รายชื่อ** — เพิ่มบุคคลพร้อมรูปอ้างอิงหลายรูป (หลายมุม/แสง) เพื่อเพิ่มความแม่นยำ
- **ตรวจจับใบหน้าอัตโนมัติ** — สแกนโฟลเดอร์กิจกรรม ตรวจจับและเก็บ embedding ใบหน้าทุกรูป
- **ค้นหาด้วย AI** — ค้นหาบุคคลจากรูปกิจกรรม ใช้ cosine similarity เปรียบเทียบกับทุกรูปอ้างอิง (max similarity)
- **จัดเรียงอัตโนมัติ** — คัดลอกรูปที่พบลงโฟลเดอร์ย่อยแยกตามชื่อบุคคล
- **เลือกรูปหลัก** — กำหนดรูปประจำตัวของแต่ละบุคคลได้

## เทคโนโลยี

| ส่วน        | เทคโนโลยี                          |
| ----------- | ---------------------------------- |
| UI          | PySide6 (Qt for Python)            |
| จดจำใบหน้า  | InsightFace (ArcFace / buffalo_sc) |
| Inference   | ONNX Runtime                       |
| ฐานข้อมูล   | SQLite                             |
| ประมวลผลภาพ | OpenCV, Pillow                     |
| Packaging   | PyInstaller, hdiutil               |

## โครงสร้างโปรเจค

```
├── main.py                      # จุดเริ่มต้นโปรแกรม
├── app/
│   ├── config.py                # ค่าตั้งต้น, path, settings
│   ├── database.py              # SQLite schema + CRUD
│   ├── services/
│   │   ├── face_service.py      # InsightFace singleton
│   │   ├── search_service.py    # cosine similarity search
│   │   ├── photo_processor.py   # สแกนและประมวลผลรูป
│   │   └── file_organizer.py    # คัดลอกรูปไปโฟลเดอร์ย่อย
│   ├── workers/                 # QThread workers (ไม่บล็อก UI)
│   │   ├── person_worker.py     # เพิ่มบุคคล/embedding
│   │   ├── process_worker.py    # ประมวลผลใบหน้า
│   │   └── search_worker.py     # ค้นหาบุคคล
│   └── ui/
│       ├── main_window.py       # หน้าต่างหลัก + sidebar
│       └── widgets/             # UI components ทั้งหมด
├── resources/
│   ├── icon.png                 # ไอคอนโปรแกรม
│   └── styles/app.qss          # stylesheet
├── scripts/
│   └── download_model.py        # ดาวน์โหลดโมเดล InsightFace
├── build.sh                     # script สร้าง .app และ .dmg
└── requirements.txt             # dependencies
```

## ขั้นตอนการใช้งาน

1. **ตั้งค่าโฟลเดอร์** — เลือกโฟลเดอร์หลักที่มีโฟลเดอร์ย่อย (กิจกรรม) อยู่ภายใน
2. **รายชื่อ** — เพิ่มบุคคลพร้อมรูปใบหน้า (เพิ่มได้หลายรูปต่อคน)
3. **ประมวลผล** — สแกนโฟลเดอร์กิจกรรมเพื่อตรวจจับใบหน้าทุกรูป
4. **ค้นหา** — เลือกบุคคลและโฟลเดอร์กิจกรรม กดค้นหาเพื่อหารูปที่มีบุคคลนั้น

## ติดตั้งและรัน (Development)

```bash
# สร้าง virtual environment
python3 -m venv venv
source venv/bin/activate

# ติดตั้ง dependencies
pip install -r requirements.txt

# รันโปรแกรม
python main.py
```

โมเดล InsightFace (buffalo_sc) จะถูกดาวน์โหลดอัตโนมัติเมื่อเปิดโปรแกรมครั้งแรก

## สร้าง .dmg สำหรับแจกจ่าย

```bash
chmod +x build.sh
./build.sh
```

ผลลัพธ์จะอยู่ที่ `dist/PuriPhotoSearch.dmg` — ลากไฟล์ .app ลง Applications ได้เลย

## ข้อมูลแอป

- ฐานข้อมูลและการตั้งค่าเก็บที่ `~/Library/Application Support/PuriPhotoSearch/`
- Log files เก็บที่ `~/Library/Logs/PuriPhotoSearch/`

## ความต้องการระบบ

- macOS 11+ (Big Sur ขึ้นไป)
- Python 3.9+ (สำหรับ development)
- พื้นที่ดิสก์ ~200MB (รวมโมเดล)
