# PuriPhotoSearch — Desktop Face Recognition Photo Organizer

> Cross-platform desktop app (macOS & Windows) for organizing photos by face recognition.
> Scan photo folders → detect & cluster faces → name people → auto-copy matched photos to person-named subfolders.

**Version:** 1.8.7 | **Language:** Python 3.13 | **UI Language:** Thai | **Offline:** 100% local processing

![PuriPhotoSearch](PuriPhotoSearch.png)

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| UI Framework | PySide6 (Qt6 for Python) |
| Face Detection | InsightFace (ArcFace / `buffalo_sc` model) |
| ML Runtime | ONNX Runtime |
| Image Processing | OpenCV (headless), Pillow |
| Database | SQLite (WAL mode) |
| Packaging | PyInstaller (.dmg for macOS, .exe for Windows) |
| CI/CD | GitHub Actions (build, code sign, notarize, release) |

---

## Directory Structure

```
photosearch-mac/
├── main.py                              # Entry point
├── requirements.txt                     # Python dependencies
├── photosearch.spec                     # PyInstaller spec (macOS)
├── photosearch_win.spec                 # PyInstaller spec (Windows)
├── build.sh / build_win.bat             # Build scripts
├── promptpay.jpg                        # Donation QR (bundled in app)
│
├── .github/workflows/build.yml          # CI/CD pipeline
├── scripts/download_model.py            # Download InsightFace model
│
├── resources/
│   ├── icon.png / icon.icns / icon.ico  # App icons
│   ├── appLogo.png                      # Navbar logo
│   └── styles/
│       ├── app.qss                      # Main stylesheet
│       └── checkmark.svg
│
├── models/                              # Pre-downloaded InsightFace weights
│   └── insightface_models/              # (bundled in PyInstaller if present)
│
├── app/                                 # Main application package
│   ├── config.py                        # Settings, paths, AppConfig dataclass
│   ├── database.py                      # SQLite schema + CRUD operations
│   ├── models.py                        # Data classes (Person, Photo, etc.)
│   │
│   ├── services/                        # Business logic
│   │   ├── face_service.py              # InsightFace singleton wrapper
│   │   ├── search_service.py            # Cosine similarity search
│   │   ├── photo_processor.py           # Batch face detection pipeline
│   │   ├── face_cluster_service.py      # Face clustering & identity matching
│   │   └── file_organizer.py            # Copy photos to person subfolders
│   │
│   ├── workers/                         # QThread workers (non-blocking UI)
│   │   ├── base_worker.py               # Base class with signals
│   │   ├── model_loader_worker.py       # Load InsightFace on startup
│   │   ├── person_worker.py             # Add person + embeddings
│   │   ├── process_worker.py            # Batch face detection
│   │   ├── search_worker.py             # Search persons in folders
│   │   └── scan_mode_worker.py          # Scan → cluster → name workflow
│   │
│   └── ui/                              # User interface
│       ├── main_window.py               # Main window, navbar, panels
│       └── widgets/
│           ├── main_panel.py            # Core: folder tree + search/scan tabs
│           ├── folder_selector.py       # Recursive folder tree with stats
│           ├── person_manager.py        # Person CRUD + groups + drag-drop
│           ├── person_card.py           # Person card widget
│           ├── event_processor.py       # Process event folders
│           ├── scan_mode_panel.py       # Scan-first-name-later UI
│           ├── scan_mode_dialog.py      # Name clusters dialog
│           ├── results_gallery.py       # Search results display
│           ├── face_crop_dialog.py      # Crop & preview faces
│           ├── progress_dialog.py       # Progress indicator
│           ├── photo_browser_dialog.py  # File picker with thumbnails
│           ├── photo_thumbnail.py       # Single thumbnail widget
│           ├── settings_dialog.py       # App preferences
│           ├── help_panel.py            # User manual (Thai)
│           └── searchable_person_combo.py  # Searchable dropdown
│
└── sample-photosearch/                  # Reference backend (FastAPI) — not deployed
    ├── backend/                         # FastAPI + PostgreSQL + pgvector
    └── frontend/                        # Vue 3 + Vite
```

---

## Database Schema (SQLite)

**Location:** `~/Library/Application Support/PuriPhotoSearch/photosearch.db` (macOS) /
`%APPDATA%/PuriPhotoSearch/photosearch.db` (Windows)

### Tables

```sql
-- People registered for face recognition
persons (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    group_name  TEXT,                    -- optional grouping
    created_at  TEXT DEFAULT datetime('now'),
    updated_at  TEXT
)

-- Multiple reference photos per person (embeddings)
person_embeddings (
    id          INTEGER PRIMARY KEY,
    person_id   INTEGER REFERENCES persons(id) ON DELETE CASCADE,
    photo_path  TEXT NOT NULL,
    embedding   BLOB NOT NULL,           -- 512-dim float32 array as bytes
    thumbnail   BLOB,                    -- 150×150 JPEG
    is_primary  INTEGER DEFAULT 0,
    created_at  TEXT
)

-- Photo directories to process
event_folders (
    id             INTEGER PRIMARY KEY,
    folder_path    TEXT NOT NULL UNIQUE,
    folder_name    TEXT NOT NULL,
    photo_count    INTEGER DEFAULT 0,
    face_count     INTEGER DEFAULT 0,
    is_processed   INTEGER DEFAULT 0,
    processed_at   TEXT,
    created_at     TEXT
)

-- Image files within event folders
photos (
    id               INTEGER PRIMARY KEY,
    event_folder_id  INTEGER REFERENCES event_folders(id) ON DELETE CASCADE,
    file_path        TEXT NOT NULL UNIQUE,
    filename         TEXT NOT NULL,
    file_size        INTEGER,
    width            INTEGER,
    height           INTEGER,
    face_count       INTEGER,
    is_processed     INTEGER,
    created_at       TEXT
)

-- Detected faces in photos
faces (
    id         INTEGER PRIMARY KEY,
    photo_id   INTEGER REFERENCES photos(id) ON DELETE CASCADE,
    embedding  BLOB NOT NULL,            -- 512-dim float32
    bbox_x1    REAL, bbox_y1 REAL,       -- bounding box
    bbox_x2    REAL, bbox_y2 REAL,
    confidence REAL,
    created_at TEXT
)

-- User-created person groups
person_groups (
    id         INTEGER PRIMARY KEY,
    name       TEXT NOT NULL UNIQUE,
    created_at TEXT
)
```

### Indexes

```sql
idx_persons_name             ON persons(name)
idx_persons_group            ON persons(group_name)
idx_person_embeddings_person ON person_embeddings(person_id)
idx_photos_event             ON photos(event_folder_id, is_processed)
idx_faces_photo              ON faces(photo_id)
```

---

## Application Architecture

### Startup Flow

```
main.py
  ├── Detect PyInstaller bundle (sys.frozen)
  ├── Set INSIGHTFACE_HOME env for model path
  ├── Setup logging (console + file)
  ├── Create QApplication
  ├── Load stylesheet (app.qss)
  ├── init_database() — create tables (retry 3x)
  ├── Load AppConfig from settings.json
  ├── Create MainWindow (1200×800)
  └── Start ModelLoaderWorker (background) → load InsightFace
```

### UI Hierarchy

```
MainWindow (QMainWindow)
├── Navbar (top) — Logo + 3 buttons: สแกนรูปภาพ | รายชื่อ | วิธีใช้งาน
├── Status Bar — Model status + DB stats (persons, faces, photos)
└── QStackedWidget — 3 panels
    │
    ├── [0] MainPanel — Core scanning & search
    │   ├── Left: FolderSelector
    │   │   ├── Folder path input + browse button
    │   │   ├── QTreeWidget (recursive folder tree)
    │   │   │   ├── Header: checkbox (select all) + collapse button + search
    │   │   │   └── Items: checkbox + folder name + photo count + face count
    │   │   ├── EventProcessor (auto-process selected folders)
    │   │   └── Progress bar + stats
    │   │
    │   └── Right: QTabWidget (2 tabs)
    │       ├── Tab "สแกนก่อนตั้งชื่อทีหลัง" (Scan first, name later)
    │       │   ├── Scan button → ScanClusterWorker
    │       │   ├── Cluster results → ScanModeDialog (name each cluster)
    │       │   ├── Destination selector (in-place or custom folder)
    │       │   └── Execute button → ExecuteScanWorker
    │       │
    │       └── Tab "ค้นหาจากรายชื่อ" (Search from person list)
    │           ├── Person tree (grouped, with checkboxes)
    │           ├── Collapse/expand button + select all
    │           ├── Destination selector
    │           ├── Search button → SearchAllWorker
    │           └── ResultsGallery (matched photos display)
    │
    ├── [1] PersonManager — Person database management
    │   ├── Left sidebar: Group list + add/rename/delete group
    │   ├── Toolbar: Add person, view toggle (card/list), multi-select
    │   ├── Person grid/list: PersonCard widgets (drag & drop to groups)
    │   └── Dialogs: PhotoBrowserDialog, FaceCropDialog, EmbeddingsDialog
    │
    └── [2] HelpPanel — Usage instructions (Thai) + donation QR
```

### Threading Model

All heavy operations run in QThread workers to keep UI responsive:

```
Main Thread (UI)
    │
    ├── ModelLoaderWorker      → Load InsightFace model on startup
    ├── ProcessWorker          → Detect faces in folder (4 parallel threads)
    ├── ScanClusterWorker      → Scan + detect + cluster faces
    ├── ExecuteScanWorker      → Name clusters + add to DB + copy photos
    ├── SearchSingleWorker     → Search one person in folder
    ├── SearchAllWorker        → Search all selected persons
    ├── AddPersonWorker        → Extract embedding + create person
    └── AddEmbeddingWorker     → Add reference photo to person
```

**Signal pattern (all workers inherit from BaseWorker):**

```python
worker.progress.emit(current, total, message)   # → update progress bar
worker.error.emit(message)                       # → show error dialog
worker.finished_with_result.emit(result_dict)    # → handle results
worker.status_message.emit(text)                 # → status bar text
```

---

## Core Services

### 1. FaceService (`services/face_service.py`)

Singleton wrapper around InsightFace.

```python
load_model(model_name='buffalo_sc')     # Load ONNX model (~200MB)
detect_faces(image_path) → [           # Detect all faces in image
    {'bbox': [x1,y1,x2,y2], 'embedding': ndarray(512,), 'confidence': float}
]
get_best_embedding(image_path) → ndarray(512,)  # Embedding of largest face
```

- Singleton: model loaded once, reused across app
- Auto-scales images to max 1280px
- Unicode path support (Windows: reads as binary → cv2.imdecode)

### 2. SearchService (`services/search_service.py`)

Vector similarity search using cosine similarity.

```python
batch_cosine_similarity(query_512d, embeddings_Nx512) → similarities_N

# Multi-embedding: person has multiple reference photos
multi_embedding_similarity(person_embeddings, face_embeddings) → max similarity
# Takes MAXIMUM similarity across all reference photos (best angle match)

search_person_in_event(db, person_id, event_folder_id, threshold=0.45) → matches
# Returns: [{photo_id, file_path, similarity, bbox}] filtered & deduplicated
```

### 3. PhotoProcessor (`services/photo_processor.py`)

Batch face detection with parallel processing.

```python
scan_folder(folder_path) → [image_paths]  # Find .jpg/.png/.webp/.bmp/.tiff
process_event_folder(db, folder_id, images)
# ThreadPoolExecutor(4 workers) → detect faces → batch commit every 20 photos
```

### 4. FaceClusterService (`services/face_cluster_service.py`)

Group detected faces by identity.

```python
cluster_faces(faces, threshold) → [
    {faces, best_face, person_id, person_name, is_known}
]
# Step 1: Match against known persons in DB
# Step 2: Cluster remaining faces (greedy centroid-based)

select_diverse_embeddings(faces, max_count=6)
# Farthest-point selection for angle/lighting diversity
```

### 5. FileOrganizer (`services/file_organizer.py`)

Copy matched photos to person-named subfolders.

```python
organize_single_person(matches, person_name, custom_dest_dir=None)
# Mode 1 (default): <event_folder>/<person_name>/<original_file>
# Mode 2 (custom):  <custom_dest>/<person_name>/<source_folder>_<original_file>
```

---

## Key Workflows

### Workflow 1: Scan First, Name Later (สแกนก่อนตั้งชื่อทีหลัง)

```
User selects folders → Click "เริ่มสแกนใหม่"
    │
    ├── ScanClusterWorker:
    │   ├── For each selected folder:
    │   │   ├── Scan for images (.jpg, .png, etc.)
    │   │   ├── Detect faces (4 parallel threads)
    │   │   └── Store embeddings in DB
    │   ├── cluster_faces() → group by identity
    │   └── Generate thumbnails for each cluster
    │
    ├── ScanModeDialog: Show clusters → User names each group
    │   ├── Type name → will create person
    │   ├── Leave blank → skip
    │   └── Merge clusters with same face
    │
    └── ExecuteScanWorker:
        ├── For each named cluster:
        │   ├── select_diverse_embeddings(max=6)
        │   ├── add_person() with primary embedding
        │   ├── add_person_embedding() for extras
        │   └── Copy matched photos to subfolders
        └── Emit results
```

### Workflow 2: Search from Person List (ค้นหาจากรายชื่อ)

```
User registers persons → selects folders → checks persons → Click "ดำเนินการ"
    │
    └── SearchAllWorker:
        ├── For each selected person:
        │   ├── Fetch person embeddings from DB
        │   ├── Fetch all face embeddings from selected folders
        │   ├── Compute multi_embedding_similarity()
        │   ├── Filter by threshold (0.45)
        │   ├── Deduplicate (best face per photo)
        │   └── Copy matched photos to person subfolder
        └── Show results in ResultsGallery
```

### Workflow 3: Add a Person

```
PersonManager → "เพิ่มบุคคล" → select photo → crop face → enter name
    │
    └── AddPersonWorker:
        ├── FaceService.get_best_embedding(photo)
        ├── Create 150×150 center-crop JPEG thumbnail
        ├── DB: INSERT INTO persons (name)
        ├── DB: INSERT INTO person_embeddings (embedding, thumbnail, is_primary=1)
        └── Signal: person_added(person_id, name)
```

---

## Configuration

### AppConfig (`app/config.py`)

```python
@dataclass
class AppConfig:
    main_photos_folder: str = ""         # Last used folder
    similarity_threshold: float = 0.45   # Face match threshold (0-1)
    face_model_name: str = "buffalo_sc"  # InsightFace model
    max_image_dim: int = 1280            # Max image dimension for detection
    face_workers: int = 4                # Parallel detection threads
    thumbnail_size: int = 200            # UI thumbnail size
    results_per_page: int = 50           # Results pagination
    person_view_mode: str = "card"       # "card" or "list"
    batch_commit_size: int = 20          # DB batch commit size
```

**Persisted to:** `settings.json` in app data directory

### Platform Paths

| Path | macOS | Windows |
|------|-------|---------|
| App data | `~/Library/Application Support/PuriPhotoSearch/` | `%APPDATA%/PuriPhotoSearch/` |
| Database | `<app_data>/photosearch.db` | `<app_data>/photosearch.db` |
| Settings | `<app_data>/settings.json` | `<app_data>/settings.json` |
| Models | `<app_data>/models/` | `<app_data>/models/` |
| Logs | `~/Library/Logs/PuriPhotoSearch.log` | `<app_data>/logs/PuriPhotoSearch.log` |

---

## Signal/Slot Connections

### MainWindow ↔ Panels

```
MainPanel.processing_complete    → MainWindow._on_processing_complete()  → refresh stats
MainPanel.person_changed         → MainWindow._on_person_changed()       → refresh stats
PersonManager.person_changed     → MainWindow._on_person_changed()       → refresh stats
FolderSelector.folder_count_changed → MainWindow status bar update
```

### MainPanel Internal

```
FolderSelector.folder_changed        → refresh folder context
FolderSelector.processing_complete   → update stats, enable search
FolderSelector.processing_cancelled  → reset search/scan UI
SearchWorker.progress                → update progress bar
SearchWorker.finished_with_result    → display ResultsGallery
ScanWorker.progress                  → update progress bar
ScanWorker.finished_with_result      → show ScanModeDialog
```

### PersonManager

```
PersonCard.edit_clicked          → show edit dialog
PersonCard.delete_clicked        → confirm & delete
PersonCard.add_photo_clicked     → file picker → AddEmbeddingWorker
PersonCard.assign_group_clicked  → group assignment
PersonCard.toggled               → multi-select mode
```

---

## Build & Release

### Local Development

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python main.py
```

InsightFace model (`buffalo_sc`) downloads automatically on first launch.

### Local Build

```bash
# macOS
python scripts/download_model.py models
python -m PyInstaller photosearch.spec --clean --noconfirm

# Windows
python scripts/download_model.py models
python -m PyInstaller photosearch_win.spec --clean --noconfirm
```

### CI/CD (GitHub Actions)

**Trigger:** Push tag `v*` (e.g., `v1.8.7`) or manual dispatch

```
build.yml
├── build-macos (macos-latest)
│   ├── Python 3.13 + dependencies
│   ├── Download InsightFace model
│   ├── PyInstaller → PuriPhotoSearch.app
│   ├── Code sign (Developer ID Application)
│   ├── Create .dmg
│   ├── Notarize (Apple notary service)
│   └── Upload artifact
│
├── build-windows (windows-latest)
│   ├── Python 3.13 + dependencies
│   ├── Download InsightFace model
│   ├── PyInstaller → PuriPhotoSearch.exe
│   ├── Create .zip
│   └── Upload artifact
│
└── release (ubuntu-latest)
    ├── Download artifacts
    └── Create GitHub Release with .dmg + .zip
```

**Required GitHub Secrets:**
- `APPLE_CERTIFICATE_BASE64` — Developer ID certificate (p12, base64)
- `APPLE_CERTIFICATE_PASSWORD` — Certificate password
- `APPLE_ID` — Apple ID for notarization
- `APPLE_APP_PASSWORD` — App-specific password

---

## Windows-Specific Handling

| Issue | Solution |
|-------|----------|
| Database locked | `PRAGMA busy_timeout=30000`, retry init 3x, clean stale WAL/SHM |
| Unicode file paths | Read image as binary bytes → `cv2.imdecode()` |
| Null stdout/stderr | PyInstaller `--windowed` closes stdout → redirect to `os.devnull` |

---

## Styling

**Color Scheme (macOS-inspired):**

| Element | Color |
|---------|-------|
| Primary (accent) | `#F5811F` (orange) |
| Background | `#FAFAFA` |
| Text primary | `#1C1C1E` / `#1D1D1F` |
| Text secondary | `#86868B` |
| Border | `#D2D2D7` / `#E5E5EA` |
| Error | `#FF3B30` (red) |

UI is written entirely in **Thai** with English labels for technical elements.
Main stylesheet: `resources/styles/app.qss`

---

## Dependencies

```
PySide6>=6.6.0               # Qt6 UI framework
insightface==0.7.3           # ArcFace face recognition
onnxruntime>=1.20.0          # ONNX model inference
numpy>=1.24.0                # Numerical computing
opencv-python-headless>=4.10.0  # Image processing
Pillow>=10.0.0               # Image manipulation
pyinstaller>=6.0.0           # App bundling
```

---

## Key Design Decisions

1. **Singleton FaceService** — Model is ~200MB, load once, reuse everywhere
2. **QThread Workers** — Face detection takes seconds per image; without threads UI freezes
3. **Batch DB Commits** — Commit every 20 photos to reduce SQLite lock contention
4. **Multi-Embedding Similarity** — Multiple reference photos per person → take MAX similarity across all angles for better accuracy
5. **Greedy Centroid Clustering** — Fast face clustering without heavy dependencies
6. **SQLite over PostgreSQL** — Desktop app needs no server; embedded DB is sufficient
7. **PyInstaller Bundling** — Self-contained .dmg/.exe, no Python install needed
8. **WAL Mode** — Allows concurrent reads during writes (important for large scans)
9. **Farthest-Point Embedding Selection** — Select diverse angles/lighting from clusters for better recognition

---

## System Requirements

- macOS 11+ (Big Sur) or Windows 10+
- Python 3.13 (for development)
- ~200MB disk space (including model)

---

## For AI Developers

**To continue working on this project, understand:**

1. **Entry:** `main.py` → `MainWindow` → QStackedWidget with 3 panels
2. **Core Loop:** User action → Worker thread → Qt Signal → UI update → Database
3. **Adding features:** Create widget in `app/ui/widgets/`, add worker in `app/workers/` if async needed
4. **Database changes:** Modify `database.py` (add migration logic for schema changes)
5. **Search algorithm changes:** Modify `search_service.py`
6. **Build changes:** Update `.spec` files + GitHub Actions workflow

**Key files by feature area:**

| Area | Files |
|------|-------|
| Person CRUD | `person_worker.py`, `person_manager.py`, `person_card.py` |
| Face detection | `face_service.py`, `photo_processor.py`, `process_worker.py` |
| Search | `search_service.py`, `search_worker.py`, `results_gallery.py` |
| Scan & cluster | `face_cluster_service.py`, `scan_mode_worker.py`, `scan_mode_panel.py`, `scan_mode_dialog.py` |
| File organization | `file_organizer.py` |
| Folder tree | `folder_selector.py`, `event_processor.py` |
| Settings | `config.py`, `settings_dialog.py` |
| Main layout | `main_window.py`, `main_panel.py` |
| Build & deploy | `photosearch.spec`, `photosearch_win.spec`, `.github/workflows/build.yml` |
