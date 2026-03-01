@echo off
REM ============================================
REM   RUN INJECT DANA v2.4
REM ============================================

cd /d "%~dp0"
title INJECT DANA v2.4

echo ============================================
echo   INJECT DANA v2.4 - Starting...
echo ============================================
echo.

REM === Tambahkan bundled ADB ke PATH session ini ===
if exist "%~dp0platform-tools\adb.exe" (
    set "PATH=%~dp0platform-tools;%PATH%"
)

REM === Cek bundled Python dulu ===
if exist "%~dp0python\python.exe" (
    echo [OK] Menggunakan bundled Python
    echo.

    REM Cek apakah PySide6 sudah terinstall
    "%~dp0python\python.exe" -c "import PySide6" >nul 2>&1
    if %ERRORLEVEL% NEQ 0 (
        echo [!] PySide6 belum terinstall. Menjalankan setup packages...
        echo.
        call "%~dp0POST_INSTALL_INJECT_DANA.bat"
        echo.
        echo [OK] Setup selesai. Menjalankan INJECT DANA...
        echo.
    )

    "%~dp0python\python.exe" INJECT_DANA.py
    if %ERRORLEVEL% NEQ 0 (
        echo.
        echo ============================================
        echo   [ERROR] INJECT DANA crashed!
        echo   Error code: %ERRORLEVEL%
        echo ============================================
        echo.
        echo Coba jalankan POST_INSTALL_INJECT_DANA.bat
        echo lalu jalankan ulang shortcut ini.
        echo.
        pause
    )
    goto END
)

REM === Fallback ke system Python ===
echo [!] Bundled Python tidak ditemukan, mencari system Python...
where python >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo [OK] Menggunakan system Python
    echo.

    REM Cek PySide6
    python -c "import PySide6" >nul 2>&1
    if %ERRORLEVEL% NEQ 0 (
        echo [!] PySide6 belum terinstall. Installing packages...
        echo.
        python -m pip install PySide6 telethon uiautomator2 "qrcode[pil]" Pillow requests
        echo.
    )

    python INJECT_DANA.py
    if %ERRORLEVEL% NEQ 0 (
        echo.
        echo ============================================
        echo   [ERROR] INJECT DANA crashed!
        echo   Error code: %ERRORLEVEL%
        echo ============================================
        echo.
        pause
    )
    goto END
)

echo.
echo ============================================
echo   [ERROR] Python tidak ditemukan!
echo ============================================
echo.
echo Solusi:
echo   1. Install ulang INJECT DANA (Full Installation)
echo   2. Atau install Python dari python.org
echo      lalu jalankan: pip install PySide6 telethon uiautomator2 qrcode Pillow
echo.
pause

:END
