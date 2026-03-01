@echo off
echo ============================================
echo   BUILD INSTALLER - INJECT DANA v2.9
echo   (Termasuk Python + PySide6 + ADB)
echo ============================================
echo.

cd /d "%~dp0"

REM === Cek dependencies ===
if not exist "installer_deps\python\python.exe" (
    echo [WARNING] Python embeddable belum di-download!
    echo.
    echo Jalankan DOWNLOAD_DEPS.bat terlebih dahulu.
    echo.
    set /p confirm="Lanjutkan tanpa Python bundled? (y/n): "
    if /i not "%confirm%"=="y" (
        echo Jalankan DOWNLOAD_DEPS.bat dulu.
        pause
        exit /b 1
    )
)

if not exist "installer_deps\platform-tools\adb.exe" (
    echo [WARNING] ADB Platform-tools belum ada!
)

REM === Cek file utama ===
if not exist "INJECT_DANA.py" (
    echo [ERROR] INJECT_DANA.py tidak ditemukan!
    pause
    exit /b 1
)

if not exist "inject_dana_installer.iss" (
    echo [ERROR] inject_dana_installer.iss tidak ditemukan!
    pause
    exit /b 1
)

echo [OK] INJECT_DANA.py ditemukan
echo [OK] inject_dana_installer.iss ditemukan

REM === Cek batch files ===
if not exist "RUN_INJECT_DANA.bat" (
    echo [ERROR] RUN_INJECT_DANA.bat tidak ditemukan!
    pause
    exit /b 1
)
if not exist "POST_INSTALL_INJECT_DANA.bat" (
    echo [ERROR] POST_INSTALL_INJECT_DANA.bat tidak ditemukan!
    pause
    exit /b 1
)

echo [OK] RUN_INJECT_DANA.bat ditemukan
echo [OK] POST_INSTALL_INJECT_DANA.bat ditemukan

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
    echo [ERROR] Inno Setup 6 tidak ditemukan!
    echo.
    echo Download dari: https://jrsoftware.org/isdl.php
    echo Install, lalu jalankan ulang script ini.
    echo.
    pause
    exit /b 1
)

echo [OK] Inno Setup ditemukan: %ISCC_PATH%
echo.

REM === Buat folder Output jika belum ada ===
if not exist "Output" mkdir Output

REM === Config sudah hardcoded di installer.iss dengan API ID/HASH ===
echo [INFO] Config dengan API ID/HASH sudah di-hardcode di installer
echo.

REM === Build! ===
echo Memulai kompilasi installer...
echo.

"%ISCC_PATH%" "inject_dana_installer.iss"

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ============================================
    echo   BUILD SUKSES!
    echo ============================================
    echo.
    
    echo File installer:
    echo   %~dp0Output\INJECT_DANA_Installer_v2.3.exe
    echo.
    echo INSTALLER INI SUDAH TERMASUK:
    echo   [x] Python 3.14
    echo   [x] ADB Platform-Tools
    echo   [x] INJECT_DANA.py
    echo   [x] Auto-install PySide6, Telethon, uiautomator2, qrcode
    echo   [x] Shortcut Desktop + Start Menu
    echo   [x] Auto-setup ADB PATH
    echo   [x] Config BERSIH ^(tanpa session Telegram^)
    echo.
    echo Kapten cukup:
    echo   1. Klik 2x installer
    echo   2. Next -^> Next -^> Install -^> Finish
    echo   3. Tunggu packages install selesai
    echo   4. Colok HP, klik shortcut INJECT DANA
    echo   5. Scan QR code dari Telegram HP
    echo.

    REM Buka folder output
    if exist "%~dp0Output" (
        explorer "%~dp0Output"
    )
) else (
    echo.
    echo [ERROR] Build gagal! Cek error di atas.
)

echo.
pause
