#!/bin/bash
# =============================================================================
# PuriPhotoSearch macOS Build Script
# Creates PuriPhotoSearch.app and PuriPhotoSearch.dmg
# =============================================================================

set -e

APP_NAME="PuriPhotoSearch"
APP_VERSION="1.0.0"
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
DIST_DIR="${PROJECT_DIR}/dist"
BUILD_DIR="${PROJECT_DIR}/build"
DMG_NAME="${APP_NAME}-${APP_VERSION}.dmg"

echo "============================================"
echo "  Building ${APP_NAME} v${APP_VERSION}"
echo "============================================"
echo ""

# ----- Step 1: Check Python -----
echo "[1/6] Checking Python..."
PYTHON="python3"
if ! command -v $PYTHON &> /dev/null; then
    echo "Error: python3 not found. Install Python 3.9+ first."
    exit 1
fi

PY_VERSION=$($PYTHON -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "  Python version: ${PY_VERSION}"

# ----- Step 2: Create/activate virtual environment -----
echo ""
echo "[2/6] Setting up virtual environment..."
VENV_DIR="${PROJECT_DIR}/venv"

if [ ! -d "${VENV_DIR}" ]; then
    echo "  Creating virtual environment at ${VENV_DIR}..."
    $PYTHON -m venv "${VENV_DIR}"
fi

# Activate venv - use the venv's Python from now on
PYTHON="${VENV_DIR}/bin/python3"
PIP="${VENV_DIR}/bin/pip"
echo "  Using venv Python: ${PYTHON}"

# ----- Step 3: Install dependencies -----
echo ""
echo "[3/6] Installing dependencies..."
$PIP install --upgrade pip > /dev/null 2>&1
$PIP install -r "${PROJECT_DIR}/requirements.txt"
echo "  Dependencies installed."

# ----- Step 4: Download InsightFace model -----
echo ""
echo "[4/6] Downloading face recognition model..."
MODEL_DIR="${PROJECT_DIR}/models"
MODEL_CHECK="${MODEL_DIR}/models/buffalo_sc"

if [ -d "${MODEL_CHECK}" ] && [ "$(ls -A ${MODEL_CHECK} 2>/dev/null)" ]; then
    echo "  Model already downloaded at ${MODEL_CHECK}"
else
    echo "  Downloading buffalo_sc model (this may take a minute)..."
    $PYTHON "${PROJECT_DIR}/scripts/download_model.py" "${MODEL_DIR}"
fi

# ----- Step 5: Build .app with PyInstaller -----
echo ""
echo "[5/6] Building ${APP_NAME}.app with PyInstaller..."

# Clean previous build
rm -rf "${DIST_DIR}/${APP_NAME}" "${DIST_DIR}/${APP_NAME}.app" "${BUILD_DIR}/${APP_NAME}"

$PYTHON -m PyInstaller "${PROJECT_DIR}/photosearch.spec" \
    --clean \
    --noconfirm \
    --distpath "${DIST_DIR}" \
    --workpath "${BUILD_DIR}"

if [ ! -d "${DIST_DIR}/${APP_NAME}.app" ]; then
    echo "Error: Build failed - ${APP_NAME}.app not found."
    exit 1
fi

echo "  ${APP_NAME}.app created successfully."

# ----- Step 6: Create .dmg -----
echo ""
echo "[6/6] Creating ${DMG_NAME}..."

DMG_PATH="${DIST_DIR}/${DMG_NAME}"
DMG_TEMP="${DIST_DIR}/${APP_NAME}-temp.dmg"
DMG_STAGING="${DIST_DIR}/dmg_staging"

# Clean previous dmg
rm -f "${DMG_PATH}" "${DMG_TEMP}"
rm -rf "${DMG_STAGING}"

# Create staging directory
mkdir -p "${DMG_STAGING}"
cp -R "${DIST_DIR}/${APP_NAME}.app" "${DMG_STAGING}/"
ln -s /Applications "${DMG_STAGING}/Applications"

# Create DMG
hdiutil create \
    -volname "${APP_NAME}" \
    -srcfolder "${DMG_STAGING}" \
    -ov \
    -format UDBZ \
    "${DMG_PATH}"

# Clean up staging
rm -rf "${DMG_STAGING}"

if [ ! -f "${DMG_PATH}" ]; then
    echo "Error: DMG creation failed."
    exit 1
fi

DMG_SIZE=$(du -h "${DMG_PATH}" | cut -f1)

echo ""
echo "============================================"
echo "  Build Complete!"
echo "============================================"
echo ""
echo "  App:  ${DIST_DIR}/${APP_NAME}.app"
echo "  DMG:  ${DMG_PATH} (${DMG_SIZE})"
echo ""
echo "  To install:"
echo "    1. Open ${DMG_NAME}"
echo "    2. Drag ${APP_NAME} to Applications"
echo "    3. Open from Applications"
echo ""
