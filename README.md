# LELEPAY - INJECT DANA

Auto Suntikan Dana via Telegram + myBCA HP

## Features v3.0

- ✅ **Fair Distribution** - Random delay untuk distribusi job merata antar multi-user
- ✅ **Force Cancel** - Cancel request yang stuck (Dispatched/In Progress)
- ✅ **Auto-Update** - Cek update otomatis dari GitHub
- ✅ **Anti Double Transfer** - Mencegah transfer ganda saat restart
- ✅ **Big Amount Threshold** - Request > 20 juta tidak di-auto proses
- ✅ **Multi-HP Support** - Bisa pakai multiple HP untuk parallel processing

## Requirements

- Windows 10/11
- Python 3.14+ (atau download installer yang bundled Python)
- HP Android dengan USB Debugging aktif
- Aplikasi myBCA di HP

## Installation

### Option A: Download Installer (Recommended)
1. Download `INJECT_DANA_v3.0_Setup.exe` dari [Releases](https://github.com/bon4r/lelepay-injectdana/releases)
2. Jalankan installer
3. Selesai!

### Option B: Download EXE Standalone
1. Download `INJECT_DANA.exe` dari [Releases](https://github.com/bon4r/lelepay-injectdana/releases)
2. Jalankan langsung (tidak perlu install)

### Option C: Run from Source
1. Clone repository ini
2. Install dependencies:
   ```bash
   pip install -r inject_dana_requirements.txt
   ```
3. Jalankan:
   ```bash
   python INJECT_DANA.py
   ```

## Auto-Update

Aplikasi akan otomatis cek update saat startup. Jika ada versi baru:
1. Muncul popup notifikasi
2. Klik "Download & Install"
3. Aplikasi akan restart dengan versi terbaru

## Build EXE

Untuk build .exe sendiri:
1. Install PyInstaller: `pip install pyinstaller`
2. Jalankan `BUILD_EXE_INJECT_DANA.bat`
3. Output: `dist\INJECT_DANA.exe`

## Changelog

### v3.0 (1 Mar 2026)
- Fair distribution untuk multi-user (random delay 0.5-3s)
- Force cancel request stuck
- Auto-update dari GitHub
- Hapus disconnect HP dari tabel Bank (klik kanan)

### v2.8
- Fix double transfer pada restart app

### v2.7
- Big Amount threshold (>20jt tidak auto-proses)
- Verifikasi nama penerima

## License

MIT License - Free to use for LELEPAY team.
