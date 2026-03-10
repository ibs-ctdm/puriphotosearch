#!/bin/bash
# =============================================================================
# PuriPhotoSearch macOS Build Script
# Creates signed & notarized PuriPhotoSearch.app and PuriPhotoSearch.dmg
# =============================================================================

set -e

APP_NAME="PuriPhotoSearch"
APP_VERSION="1.0.0"
BUNDLE_ID="com.puriphotosearch.macos"
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
DIST_DIR="${PROJECT_DIR}/dist"
BUILD_DIR="${PROJECT_DIR}/build"
DMG_NAME="${APP_NAME}-${APP_VERSION}.dmg"

# Code signing identity
SIGN_IDENTITY="Developer ID Application: Phra Anavach Purivaro (7ZFZ2CSF6M)"
TEAM_ID="7ZFZ2CSF6M"
APPLE_ID="aun_puri@hotmail.com"

# App-specific password (set via env var or prompt)
if [ -z "${APP_PASSWORD}" ]; then
    echo "Enter App-Specific Password for notarization (or set APP_PASSWORD env var):"
    read -s APP_PASSWORD
fi

echo "============================================"
echo "  Building ${APP_NAME} v${APP_VERSION}"
echo "  (Signed & Notarized)"
echo "============================================"
echo ""

# ----- Step 1: Check Python -----
echo "[1/8] Checking Python..."
PYTHON="python3"
if ! command -v $PYTHON &> /dev/null; then
    echo "Error: python3 not found. Install Python 3.9+ first."
    exit 1
fi

PY_VERSION=$($PYTHON -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "  Python version: ${PY_VERSION}"

# ----- Step 2: Create/activate virtual environment -----
echo ""
echo "[2/8] Setting up virtual environment..."
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
echo "[3/8] Installing dependencies..."
$PIP install --upgrade pip > /dev/null 2>&1
$PIP install -r "${PROJECT_DIR}/requirements.txt"
echo "  Dependencies installed."

# ----- Step 4: Download InsightFace model -----
echo ""
echo "[4/8] Downloading face recognition model..."
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
echo "[5/8] Building ${APP_NAME}.app with PyInstaller..."

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

# ----- Step 6: Code Sign -----
echo ""
echo "[6/8] Code signing ${APP_NAME}.app..."

# Sign all embedded frameworks/dylibs first, then the app itself
codesign --force --deep --options runtime \
    --sign "${SIGN_IDENTITY}" \
    --entitlements /dev/stdin \
    "${DIST_DIR}/${APP_NAME}.app" <<'ENTITLEMENTS'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>com.apple.security.cs.allow-unsigned-executable-memory</key>
    <true/>
    <key>com.apple.security.cs.allow-jit</key>
    <true/>
    <key>com.apple.security.cs.disable-library-validation</key>
    <true/>
</dict>
</plist>
ENTITLEMENTS

# Verify signing
codesign --verify --deep --strict "${DIST_DIR}/${APP_NAME}.app"
echo "  Code signing verified."

# ----- Step 7: Create .dmg -----
echo ""
echo "[7/8] Creating ${DMG_NAME}..."

DMG_PATH="${DIST_DIR}/${DMG_NAME}"
DMG_STAGING="${DIST_DIR}/dmg_staging"

# Clean previous dmg
rm -f "${DMG_PATH}"
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

# Sign the DMG too
codesign --force --sign "${SIGN_IDENTITY}" "${DMG_PATH}"

if [ ! -f "${DMG_PATH}" ]; then
    echo "Error: DMG creation failed."
    exit 1
fi

echo "  ${DMG_NAME} created and signed."

# ----- Step 8: Notarize -----
echo ""
echo "[8/8] Notarizing ${DMG_NAME} (this may take a few minutes)..."

xcrun notarytool submit "${DMG_PATH}" \
    --apple-id "${APPLE_ID}" \
    --password "${APP_PASSWORD}" \
    --team-id "${TEAM_ID}" \
    --wait

# Staple the notarization ticket to the DMG
xcrun stapler staple "${DMG_PATH}"

DMG_SIZE=$(du -h "${DMG_PATH}" | cut -f1)

echo ""
echo "============================================"
echo "  Build Complete! (Signed & Notarized)"
echo "============================================"
echo ""
echo "  App:  ${DIST_DIR}/${APP_NAME}.app"
echo "  DMG:  ${DMG_PATH} (${DMG_SIZE})"
echo ""
echo "  The DMG is signed and notarized."
echo "  Users can open it without Gatekeeper warnings."
echo ""
echo "  To install:"
echo "    1. Open ${DMG_NAME}"
echo "    2. Drag ${APP_NAME} to Applications"
echo "    3. Open from Applications"
echo ""
