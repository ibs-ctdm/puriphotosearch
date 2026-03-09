@echo off
REM =============================================================================
REM PuriPhotoSearch Windows Build Script
REM Creates PuriPhotoSearch.exe installer
REM =============================================================================

setlocal enabledelayedexpansion

set APP_NAME=PuriPhotoSearch
set APP_VERSION=1.0.0
set PROJECT_DIR=%~dp0
set DIST_DIR=%PROJECT_DIR%dist
set BUILD_DIR=%PROJECT_DIR%build

echo ============================================
echo   Building %APP_NAME% v%APP_VERSION%
echo ============================================
echo.

REM ----- Step 1: Check Python -----
echo [1/5] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo Error: python not found. Install Python 3.9+ first.
    exit /b 1
)
python -c "import sys; print(f'  Python version: {sys.version_info.major}.{sys.version_info.minor}')"

REM ----- Step 2: Create/activate virtual environment -----
echo.
echo [2/5] Setting up virtual environment...
if not exist "%PROJECT_DIR%venv" (
    echo   Creating virtual environment...
    python -m venv "%PROJECT_DIR%venv"
)
set PYTHON=%PROJECT_DIR%venv\Scripts\python.exe
set PIP=%PROJECT_DIR%venv\Scripts\pip.exe
echo   Using venv Python: %PYTHON%

REM ----- Step 3: Install dependencies -----
echo.
echo [3/5] Installing dependencies...
%PIP% install --upgrade pip >nul 2>&1
%PIP% install -r "%PROJECT_DIR%requirements.txt"
%PIP% install matplotlib
echo   Dependencies installed.

REM ----- Step 4: Download InsightFace model -----
echo.
echo [4/5] Downloading face recognition model...
set MODEL_DIR=%PROJECT_DIR%models
set MODEL_CHECK=%MODEL_DIR%\models\buffalo_sc

if exist "%MODEL_CHECK%" (
    echo   Model already downloaded.
) else (
    echo   Downloading buffalo_sc model...
    %PYTHON% "%PROJECT_DIR%scripts\download_model.py" "%MODEL_DIR%"
)

REM ----- Step 5: Build with PyInstaller -----
echo.
echo [5/5] Building %APP_NAME% with PyInstaller...

if exist "%DIST_DIR%\%APP_NAME%" rmdir /s /q "%DIST_DIR%\%APP_NAME%"
if exist "%BUILD_DIR%\%APP_NAME%" rmdir /s /q "%BUILD_DIR%\%APP_NAME%"

%PYTHON% -m PyInstaller "%PROJECT_DIR%photosearch_win.spec" ^
    --clean ^
    --noconfirm ^
    --distpath "%DIST_DIR%" ^
    --workpath "%BUILD_DIR%"

if not exist "%DIST_DIR%\%APP_NAME%\%APP_NAME%.exe" (
    echo Error: Build failed - %APP_NAME%.exe not found.
    exit /b 1
)

echo.
echo ============================================
echo   Build Complete!
echo ============================================
echo.
echo   Output: %DIST_DIR%\%APP_NAME%\%APP_NAME%.exe
echo.
echo   To run: double-click %APP_NAME%.exe in the dist\%APP_NAME% folder
echo   To distribute: zip the entire dist\%APP_NAME% folder
echo.

endlocal
