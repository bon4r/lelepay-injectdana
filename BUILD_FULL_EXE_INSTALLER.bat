@echo off
echo ============================================
echo   BUILD FULL INSTALLER - INJECT DANA v3.0
echo   (Build .exe + Create Installer)
echo ============================================
echo.

cd /d "%~dp0"

REM === Step 1: Build .exe dengan PyInstaller ===
echo [STEP 1] Building INJECT_DANA.exe...
echo.

call BUILD_EXE_INJECT_DANA.bat

if not exist "dist\INJECT_DANA.exe" (
    echo.
    echo [ERROR] INJECT_DANA.exe tidak ditemukan di dist\
    echo         Build .exe gagal!
    pause
    exit /b 1
)

echo.
echo [OK] INJECT_DANA.exe berhasil di-build
echo.

REM === Step 2: Build Installer dengan Inno Setup ===
echo [STEP 2] Creating installer...
echo.

REM === Cek Inno Setup ===
set ISCC_PATH=
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" (
    set "ISCC_PATH=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
)
if exist "C:\Program Files\Inno Setup 6\ISCC.exe" (
    set "ISCC_PATH=C:\Program Files\Inno Setup 6\ISCC.exe"
)
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" (
    set "ISCC_PATH=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
)

if "%ISCC_PATH%"=="" (
    echo.
    echo [WARNING] Inno Setup 6 tidak ditemukan!
    echo          Installer tidak dibuat, tapi .exe sudah siap.
    echo.
    echo Output: dist\INJECT_DANA.exe
    echo.
    echo Untuk distribusi tanpa installer:
    echo 1. Upload dist\INJECT_DANA.exe ke GitHub Releases
    echo 2. User download dan jalankan langsung
    echo.
    pause
    exit /b 0
)

echo [INFO] Inno Setup found: %ISCC_PATH%
echo.

"%ISCC_PATH%" inject_dana_exe_installer.iss

if errorlevel 1 (
    echo.
    echo [ERROR] Gagal compile installer!
    pause
    exit /b 1
)

echo.
echo ============================================
echo   BUILD COMPLETE!
echo ============================================
echo.
echo Output files:
echo   1. dist\INJECT_DANA.exe (standalone, bisa langsung dijalankan)
echo   2. Output\INJECT_DANA_v3.0_Setup.exe (installer)
echo.
echo CARA DISTRIBUSI:
echo.
echo Option A - GitHub Releases (dengan auto-update):
echo   1. Buat repository di GitHub
echo   2. Buat Release baru dengan tag v3.0
echo   3. Upload INJECT_DANA.exe ke Release assets
echo   4. Edit inject_dana_updater.py:
echo      - Ganti GITHUB_OWNER dengan username GitHub kamu
echo      - Ganti GITHUB_REPO dengan nama repository
echo.
echo Option B - Installer:
echo   1. Kirim Output\INJECT_DANA_v3.0_Setup.exe ke user
echo   2. User jalankan installer
echo.
echo ============================================
pause
