@echo off
REM ============================================
REM   POST-INSTALL INJECT DANA v2.3
REM   Install semua Python packages yang dibutuhkan
REM ============================================

cd /d "%~dp0"

echo ============================================
echo   INJECT DANA - Post Installation Setup
echo ============================================
echo.

REM === 1. Cari Python ===
echo [1/4] Mencari Python...

set "PY="
set "PIP="

REM Cek bundled Python dulu
if exist "%~dp0python\python.exe" (
    "%~dp0python\python.exe" --version 2>nul
    if %ERRORLEVEL% EQU 0 (
        echo [OK] Bundled Python ditemukan
        set "PY=%~dp0python\python.exe"
        set "PIP=%~dp0python\python.exe -m pip"
        goto BOOTSTRAP_PIP
    )
)

REM Fallback ke system Python
where python >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo [OK] System Python ditemukan
    set "PY=python"
    set "PIP=python -m pip"
    goto BOOTSTRAP_PIP
)

echo [ERROR] Python tidak ditemukan!
echo Install Python 3.14+ dari python.org
pause
exit /b 1

:BOOTSTRAP_PIP
echo.
echo [2/4] Memastikan pip tersedia...

REM Cek apakah pip sudah ada
%PY% -m pip --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [!] pip belum ada, bootstrapping via ensurepip...
    %PY% -m ensurepip --upgrade 2>nul
    if %ERRORLEVEL% NEQ 0 (
        echo [!] ensurepip gagal, download get-pip.py...
        powershell -ExecutionPolicy Bypass -Command "Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile '%~dp0get-pip.py'"
        if exist "%~dp0get-pip.py" (
            %PY% "%~dp0get-pip.py"
            del "%~dp0get-pip.py" 2>nul
        ) else (
            echo [ERROR] Gagal download get-pip.py!
            echo Pastikan koneksi internet aktif.
            pause
            exit /b 1
        )
    )
    echo [OK] pip berhasil di-bootstrap
) else (
    echo [OK] pip sudah tersedia
)

echo.
echo [3/4] Setting up ADB...

REM Cek apakah ADB sudah di PATH
where adb >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo [OK] ADB sudah tersedia di PATH
    goto INSTALL_PACKAGES
)

REM Cek bundled ADB
if exist "%~dp0platform-tools\adb.exe" (
    echo [OK] ADB ditemukan di platform-tools\
    set "PATH=%~dp0platform-tools;%PATH%"
    
    REM Tambahkan ke user PATH permanen
    powershell -ExecutionPolicy Bypass -Command ^
        "$currentPath = [Environment]::GetEnvironmentVariable('PATH', 'User'); ^
         $adbPath = '%~dp0platform-tools'; ^
         if ($currentPath -notlike \"*$adbPath*\") { ^
             [Environment]::SetEnvironmentVariable('PATH', \"$currentPath;$adbPath\", 'User'); ^
             Write-Host '[OK] ADB ditambahkan ke PATH' ^
         } else { ^
             Write-Host '[OK] ADB sudah di PATH' ^
         }"
) else (
    echo [WARNING] ADB tidak ditemukan!
    echo Download dari: https://developer.android.com/tools/releases/platform-tools
    echo Atau jalankan ulang installer dengan komponen ADB.
)

:INSTALL_PACKAGES
echo.
echo [4/4] Installing Python packages...
echo.
echo Packages yang akan diinstall:
echo   - PySide6     (GUI Modern)
echo   - Telethon    (Telegram Login)
echo   - uiautomator2 (Android Control)
echo   - qrcode      (QR Code Login)
echo   - Pillow      (Image Processing)
echo   - requests    (HTTP)
echo.

REM Upgrade pip dulu
echo [PIP] Upgrading pip...
%PIP% install --upgrade pip 2>nul

REM Install setuptools + wheel (WAJIB untuk build packages)
echo.
echo [PIP] Installing setuptools + wheel...
%PIP% install --upgrade setuptools wheel

REM Install semua packages
echo.
echo [PIP] Installing PySide6...
%PIP% install PySide6>=6.10.0

echo.
echo [PIP] Installing Telethon...
%PIP% install telethon>=1.42.0

echo.
echo [PIP] Installing uiautomator2...
%PIP% install uiautomator2>=3.5.0

echo.
echo [PIP] Installing qrcode + Pillow...
%PIP% install "qrcode[pil]>=8.0" Pillow>=12.0.0

echo.
echo [PIP] Installing requests...
%PIP% install requests>=2.32.0

echo.
echo ============================================
echo   SETUP SELESAI!
echo ============================================
echo.
echo Langkah selanjutnya:
echo   1. Colok HP via USB
echo   2. Aktifkan USB Debugging di HP
echo   3. Jalankan INJECT DANA dari Desktop
echo.
echo Untuk login Telegram:
echo   Klik Start di app -^> Scan QR Code dari HP
echo.
pause
