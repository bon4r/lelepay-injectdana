@echo off
echo ============================================
echo   BUILD INJECT DANA v3.0.10
echo   (Standalone EXE + Installer)
echo ============================================
echo.

cd /d "%~dp0"

REM === STEP 1: Build EXE dengan PyInstaller ===
echo.
echo [STEP 1] Building EXE with PyInstaller...
echo.

REM Check Python
where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python not found in PATH!
    pause
    exit /b 1
)

REM Check if INJECT_DANA.py exists
if not exist "INJECT_DANA.py" (
    echo [ERROR] INJECT_DANA.py tidak ditemukan!
    pause
    exit /b 1
)

REM Check icon
if not exist "lelepay_logo_real.ico" (
    echo [ERROR] lelepay_logo_real.ico tidak ditemukan!
    pause
    exit /b 1
)

REM Activate venv if exists
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
    echo [OK] Virtual environment activated
)

REM Build EXE
echo Building INJECT_DANA.exe...
pyinstaller --onefile --windowed --name INJECT_DANA --icon=lelepay_logo_real.ico --clean INJECT_DANA.py

if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] PyInstaller build failed!
    pause
    exit /b 1
)

if not exist "dist\INJECT_DANA.exe" (
    echo [ERROR] dist\INJECT_DANA.exe tidak terbuat!
    pause
    exit /b 1
)

echo.
echo [OK] dist\INJECT_DANA.exe created successfully!
for %%A in (dist\INJECT_DANA.exe) do echo     Size: %%~zA bytes
echo.

REM === STEP 2: Build Installer ===
echo.
echo [STEP 2] Building Installer with Inno Setup...
echo.

REM === Cek dependencies ===
if not exist "installer_deps\platform-tools\adb.exe" (
    echo [WARNING] ADB Platform-tools belum ada!
    echo Download dari https://developer.android.com/tools/releases/platform-tools
)

if not exist "inject_dana_installer.iss" (
    echo [ERROR] inject_dana_installer.iss tidak ditemukan!
    pause
    exit /b 1
)

echo [OK] INJECT_DANA.exe ditemukan
echo [OK] inject_dana_installer.iss ditemukan

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
    echo [INFO] Inno Setup 6 tidak ditemukan - skip installer build
    echo Download dari: https://jrsoftware.org/isdl.php
    echo.
    echo Tapi EXE sudah siap di: dist\INJECT_DANA.exe
    echo.
    pause
    exit /b 0
)

echo [OK] Inno Setup ditemukan: %ISCC_PATH%
echo.

REM === Buat folder Output jika belum ada ===
if not exist "Output" mkdir Output

REM === Build Installer! ===
echo Memulai kompilasi installer...
echo.

"%ISCC_PATH%" "inject_dana_installer.iss"

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ============================================
    echo   BUILD SUKSES!
    echo ============================================
    echo.
    
    echo Files created:
    echo   1. dist\INJECT_DANA.exe (standalone)
    echo   2. Output\INJECT_DANA_Installer_v3.0.10.exe
    echo.
    echo FITUR:
    echo   [x] Standalone EXE - no Python needed
    echo   [x] Auto-update dari server
    echo   [x] ADB Platform-Tools (optional)
    echo   [x] Telegram QR Login + 2FA
    echo   [x] Shortcut Desktop + Start Menu
    echo.
    echo User cukup:
    echo   1. Klik 2x installer
    echo   2. Next -^> Next -^> Install -^> Finish
    echo   3. Colok HP USB Debugging ON
    echo   4. Jalankan INJECT DANA
    echo   5. Scan QR code Telegram
    echo.

    REM Buka folder output
    if exist "%~dp0Output" (
        explorer "%~dp0Output"
    )
) else (
    echo.
    echo [ERROR] Installer build gagal! Cek error di atas.
    echo.
    echo Tapi EXE sudah siap di: dist\INJECT_DANA.exe
)

echo.
pause
