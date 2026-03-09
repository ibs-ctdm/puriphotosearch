"""Application configuration with persistent settings."""

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path

APP_NAME = "PuriPhotoSearch"
APP_VERSION = "1.0.0"

# macOS standard paths
APP_SUPPORT_DIR = os.path.join(
    os.path.expanduser("~"), "Library", "Application Support", APP_NAME
)
DB_PATH = os.path.join(APP_SUPPORT_DIR, "photosearch.db")
CONFIG_PATH = os.path.join(APP_SUPPORT_DIR, "settings.json")
MODEL_CACHE_DIR = os.path.join(APP_SUPPORT_DIR, "models")
LOG_DIR = os.path.join(os.path.expanduser("~"), "Library", "Logs")


@dataclass
class AppConfig:
    """User-configurable settings, persisted to JSON."""

    # Paths
    main_photos_folder: str = ""

    # Face recognition
    similarity_threshold: float = 0.45
    face_model_name: str = "buffalo_sc"
    max_image_dim: int = 1280
    face_workers: int = 4

    # UI preferences
    thumbnail_size: int = 200
    results_per_page: int = 50

    # Processing
    batch_commit_size: int = 20

    def save(self) -> None:
        """Persist settings to disk."""
        os.makedirs(APP_SUPPORT_DIR, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls) -> "AppConfig":
        """Load settings from disk, or return defaults."""
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
            except Exception:
                pass
        return cls()
