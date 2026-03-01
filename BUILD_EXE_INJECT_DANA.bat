@echo off
echo ============================================
echo   BUILD EXE - INJECT DANA v3.0
echo   (PyInstaller - Single .exe)
echo ============================================
echo.

cd /d "%~dp0"

REM === Cek virtual environment ===
if exist ".venv\Scripts\activate.bat" (
    echo [INFO] Activating virtual environment...
    call .venv\Scripts\activate.bat
) else (
    echo [WARNING] Virtual environment not found, using system Python
)

REM === Install PyInstaller jika belum ada ===
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo [INFO] Installing PyInstaller...
    pip install pyinstaller
)

REM === Buat icon jika belum ada ===
if not exist "lelepay_logo_real.ico" (
    echo [WARNING] lelepay_logo_real.ico tidak ditemukan!
    echo           Build tanpa icon...
    set ICON_OPT=
) else (
    set ICON_OPT=--icon=lelepay_logo_real.ico
)

echo.
echo [INFO] Building INJECT_DANA.exe...
echo.

REM === PyInstaller options ===
REM --onefile      = Single .exe file
REM --windowed     = No console window (GUI app)
REM --clean        = Clean PyInstaller cache
REM --name         = Output filename
REM --add-data     = Include additional files

pyinstaller ^
    --onefile ^
    --windowed ^
    --clean ^
    --name "INJECT_DANA" ^
    %ICON_OPT% ^
    --add-data "lelepay_logo_real.ico;." ^
    --hidden-import=PySide6.QtCore ^
    --hidden-import=PySide6.QtGui ^
    --hidden-import=PySide6.QtWidgets ^
    --hidden-import=telethon ^
    --hidden-import=uiautomator2 ^
    --hidden-import=qrcode ^
    --hidden-import=PIL ^
    --hidden-import=requests ^
    --collect-all telethon ^
    --collect-all uiautomator2 ^
    INJECT_DANA.py

if errorlevel 1 (
    echo.
    echo [ERROR] Build failed!
    pause
    exit /b 1
)

echo.
echo [SUCCESS] Build complete!
echo.
echo Output: dist\INJECT_DANA.exe
echo.

REM === Copy config template ===
if not exist "dist\inject_dana_config.json" (
    echo [INFO] Copying config template...
    copy inject_dana_config_installer.json dist\inject_dana_config.json >nul
)

REM === Copy updater ===
if exist "inject_dana_updater.py" (
    echo [INFO] Note: Updater is bundled inside .exe
)

echo.
echo ============================================
echo   CARA DISTRIBUSI:
echo ============================================
echo 1. Upload dist\INJECT_DANA.exe ke GitHub Releases
echo 2. User download dan jalankan .exe
echo 3. App akan auto-check update dari GitHub
echo ============================================
echo.

pause
