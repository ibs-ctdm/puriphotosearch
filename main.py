"""PhotoSearch Desktop App - Entry point."""

import sys
import os
import io
import logging

# Fix for PyInstaller --windowed on Windows: stdout/stderr are None
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")


def _get_bundle_dir() -> str:
    """Get the base directory for bundled resources.

    When running from PyInstaller bundle, files are extracted to sys._MEIPASS.
    When running from source, use the script's directory.
    """
    if getattr(sys, "frozen", False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


BUNDLE_DIR = _get_bundle_dir()

# Set environment for InsightFace model cache
# When bundled, models are inside the bundle; otherwise use Application Support
if getattr(sys, "frozen", False):
    os.environ["INSIGHTFACE_HOME"] = os.path.join(BUNDLE_DIR, "insightface_models")
else:
    os.environ.setdefault(
        "INSIGHTFACE_HOME",
        os.path.join(
            os.path.expanduser("~"),
            "Library", "Application Support", "PuriPhotoSearch", "models",
        ),
    )

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon

from app.config import AppConfig, APP_NAME, APP_VERSION, LOG_DIR
from app.database import init_database
from app.ui.main_window import MainWindow

# Configure logging
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(LOG_DIR, f"{APP_NAME}.log")),
    ],
)
logger = logging.getLogger(__name__)


def main():
    logger.info(f"Starting {APP_NAME} v{APP_VERSION}")
    logger.info(f"Bundle dir: {BUNDLE_DIR}")
    logger.info(f"Frozen: {getattr(sys, 'frozen', False)}")

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("PuriPhotoSearch")

    # Set app icon
    icon_path = os.path.join(BUNDLE_DIR, "resources", "appLogo.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    # Load stylesheet (works both from source and bundle)
    style_path = os.path.join(BUNDLE_DIR, "resources", "styles", "app.qss")
    if os.path.exists(style_path):
        with open(style_path) as f:
            app.setStyleSheet(f.read())

    # Initialize database
    init_database()

    # Load config
    config = AppConfig.load()

    # Create and show main window
    window = MainWindow(config)
    window.resize(1200, 800)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
