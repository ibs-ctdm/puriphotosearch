# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec file for PuriPhotoSearch macOS app."""

import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

# Paths
PROJECT_DIR = os.path.dirname(os.path.abspath(SPEC))
MODEL_DIR = os.path.join(PROJECT_DIR, "models")

# Collect ONNX Runtime shared libraries
onnx_datas = collect_data_files("onnxruntime")
onnx_bins = collect_dynamic_libs("onnxruntime")

# Collect InsightFace package data
insightface_datas = collect_data_files("insightface")

# Build datas list
datas = [
    *onnx_datas,
    *insightface_datas,
    # App resources
    (os.path.join(PROJECT_DIR, "resources"), "resources"),
    # Donation QR code
    (os.path.join(PROJECT_DIR, "promptpay.jpg"), "."),
]

# Bundle the pre-downloaded model if it exists
if os.path.isdir(MODEL_DIR):
    datas.append((MODEL_DIR, "insightface_models"))

# Collect binaries
binaries = [
    *onnx_bins,
]

a = Analysis(
    [os.path.join(PROJECT_DIR, "main.py")],
    pathex=[PROJECT_DIR],
    binaries=binaries,
    datas=datas,
    hiddenimports=[
        "onnxruntime",
        "insightface",
        "insightface.app",
        "insightface.app.face_analysis",
        "insightface.model_zoo",
        "insightface.utils",
        "cv2",
        "numpy",
        "numpy.core._methods",
        "numpy.lib.format",
        "PySide6",
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
        "PIL",
        "sqlite3",
        "scipy",
        "scipy.special",
        "albumentations",
        "charset_normalizer",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "pandas",
        "IPython",
        "jupyter",
        "notebook",
        "pytest",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PuriPhotoSearch",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    target_arch=None,  # Use current architecture
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="PuriPhotoSearch",
)

app = BUNDLE(
    coll,
    name="PuriPhotoSearch.app",
    icon=os.path.join(PROJECT_DIR, "resources", "icon.icns"),
    bundle_identifier="com.puriphotosearch.macos",
    info_plist={
        "CFBundleName": "PuriPhotoSearch",
        "CFBundleDisplayName": "Puri Photo Search",
        "CFBundleVersion": "1.8.7",
        "CFBundleShortVersionString": "1.8.7",
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "11.0",
        "NSPhotoLibraryUsageDescription": (
            "PuriPhotoSearch needs access to your photos for face recognition."
        ),
    },
)
