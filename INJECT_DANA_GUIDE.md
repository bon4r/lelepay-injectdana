# INJECT DANA v2.5 - User Guide
## Auto Suntikan via Telegram + myBCA HP

---

## Daftar Isi
1. [Pendahuluan](#pendahuluan)
2. [Requirements](#requirements)
3. [Instalasi](#instalasi)
4. [Konfigurasi Awal](#konfigurasi-awal)
5. [Fitur-Fitur](#fitur-fitur)
6. [Fitur Anti Double-Processing](#fitur-anti-double-processing)
7. [Cara Penggunaan](#cara-penggunaan)
8. [Troubleshooting](#troubleshooting)

---

## Pendahuluan

**INJECT DANA** adalah aplikasi otomasi untuk memproses request suntikan dana dari grup Telegram ke rekening bank via myBCA HP. Aplikasi ini:

- Login sebagai USER Telegram (bukan bot) via QR code
- Monitor grup Telegram untuk request "KONFIRMASI SUNTIK"
- Admin klik tombol Proses di GUI → auto transfer via myBCA HP
- **Anti double-processing**: Verifikasi "Diproses oleh: @username" agar 2 admin tidak transfer request yang sama
- Setelah sukses: auto klik PROSES di Telegram, pilih bank, kirim biaya, screenshot

---

## Requirements

### Software
- Windows 10/11
- Python 3.14+ (sudah include di installer)
- ADB Platform-Tools (sudah include di installer)

### Hardware
- HP Android dengan myBCA HP terinstall
- USB cable untuk koneksi ADB
- USB Debugging harus diaktifkan di HP

### Akun
- Akun Telegram (untuk login ke bot)
- Akun myBCA HP yang sudah aktif
- Akses ke grup Telegram (ZNXGEMPAY atau sejenisnya)

---

## Instalasi

### Cara 1: Installer (Recommended)

1. Jalankan `INJECT_DANA_Installer_v2.1.exe`
2. Pilih folder instalasi (default: Documents\INJECT_DANA)
3. Centang semua components:
   - ✅ INJECT DANA Scripts (Wajib)
   - ✅ Python 3.14 + PySide6 GUI
   - ✅ ADB Platform-Tools
4. Centang **"Install Python packages"** di Tasks
5. Klik Install dan tunggu selesai
6. Klik Finish

### Cara 2: Manual (Developer)

```batch
pip install PySide6 telethon uiautomator2 qrcode[pil] Pillow requests
```

---

## Konfigurasi Awal

### 1. Hubungkan HP via USB

1. Aktifkan **USB Debugging** di HP:
   - Settings → About Phone → Tap "Build Number" 7x
   - Settings → Developer Options → Enable USB Debugging
   
2. Colok HP ke PC via USB

3. Di HP, allow "USB debugging" dari PC ini (centang "Always allow")

4. Test koneksi:
   ```batch
   adb devices
   ```
   Harus muncul device ID

### 2. Setup Bank Accounts

1. Buka aplikasi INJECT DANA
2. Pergi ke tab **CONFIG**
3. Di section **Bank Accounts (myBCA HP)**:
   - Klik **+ Tambah**
   - Isi:
     - **Device ID**: ID dari `adb devices` (contoh: `HIYPZTD6DY65B6A6`)
     - **Nama Akun**: Nama pemilik rekening (contoh: `WILDAN SHAPUTRA`)
     - **No Rekening**: Nomor rekening BCA (contoh: `2833341308`)
     - **Password**: Password myBCA HP
     - **PIN**: PIN transaksi 6 digit
   - Klik OK
4. Klik **Save Config**

### 3. Login Telegram

1. Pastikan sudah di tab **MAIN**
2. Klik **▶ Start**
3. Akan muncul **QR Code dialog**
4. Di HP/Telegram desktop:
   - Buka Telegram → Settings → Devices → Link Desktop Device
   - Scan QR code
5. Tunggu sampai status TG berubah jadi **● Online** (hijau)

### 4. Konfigurasi Bot (Opsional)

Di file `inject_dana_config.json`:
```json
{
  "api_id": "YOUR_API_ID",
  "api_hash": "YOUR_API_HASH",
  "group_chat_id": -1001655728988,
  "bot_username": "znxgemini_bot",
  "biaya_bifast": 2500,
  "biaya_realtime": 6500
}
```

---

## Fitur-Fitur

### Tab MAIN

#### 1. Control Panel
| Tombol | Fungsi |
|--------|--------|
| **▶ Start** | Mulai monitoring Telegram dan connect semua bank HP |
| **⏹ Stop** | Hentikan semua proses |
| **💾 Save** | Simpan konfigurasi |
| **TG: ● Online** | Status koneksi Telegram |

#### 2. Tabel Bank (myBCA HP)
Menampilkan status semua HP yang terhubung:
| Kolom | Keterangan |
|-------|------------|
| Device | ID device ADB |
| Nama | Nama pemilik rekening |
| Rekening | Nomor rekening BCA |
| Saldo | Saldo terakhir (auto refresh) |
| Status | Ready/Busy/Error |

#### 3. Tabel Request Suntikan
Menampilkan semua request yang masuk dari Telegram:

| Kolom | Keterangan |
|-------|------------|
| Time | Waktu request masuk |
| Nama | Nama penerima |
| Bank | Bank tujuan (BCA/BNI/MANDIRI/dll) |
| No Rek | Nomor rekening tujuan |
| Nominal | Jumlah transfer |
| Asset | Asset type (PGD/EMAS/dll) |
| Status | Pending/Progress/Sukses/Gagal/Batal/Timeout |
| Bank Used | Bank yang dipakai untuk transfer |
| 📷 | Screenshot bukti transfer |
| ▶ | Tombol Proses |
| ↻ | Tombol Retry |
| ❌ | Tombol Batal |

#### 4. Action Buttons (per row)
| Tombol | Fungsi |
|--------|--------|
| **📷** | Lihat screenshot (jika sudah proses) |
| **▶** | Proses transfer (untuk status Pending) |
| **↻** | Retry (untuk status Gagal/Batal/Timeout/Error) |
| **❌** | Batalkan request |

#### 5. Log Panel (Kanan)
- Menampilkan status real-time
- Log aktivitas dan error
- Profile Telegram yang login (avatar, nama, username)

### Tab CONFIG

#### 1. Telegram Login
- Status login Telegram
- Tombol **Logout** untuk logout dari session

#### 2. Bank Accounts (myBCA HP)
Manage akun-akun bank yang digunakan:
| Tombol | Fungsi |
|--------|--------|
| **+ Tambah** | Tambah akun bank baru |
| **✏ Edit** | Edit akun yang dipilih |
| **✕ Hapus** | Hapus akun yang dipilih |

#### 3. Options
| Setting | Keterangan |
|---------|------------|
| **Auto Process** | Jika dicentang, request langsung diproses tanpa konfirmasi manual (HATI-HATI!) |
| **Biaya BI-FAST** | Biaya transfer BI-FAST (default: Rp 2.500) |
| **Biaya Real Time** | Biaya transfer real-time (default: Rp 6.500) |

---

## Fitur Anti Double-Processing

### Problem

Ketika **2 admin di PC berbeda** sama-sama menjalankan INJECT DANA:
- Keduanya lihat request yang sama di Telegram
- Keduanya klik PROSES hampir bersamaan
- **Tanpa proteksi**: Keduanya bisa transfer ke rekening yang sama → **DOUBLE TRANSFER!**

### Solusi v2.5

Aplikasi sekarang memverifikasi **"Diproses oleh: @username"** yang muncul di message Telegram setelah PROSES diklik:

```
💉 Suntikan siap diproses!

🏦 No Rek: 6767129426
👤 Nama: RINI TRISNAWATI
🏦 Bank: BCA
💰 Nominal: 10 JT

👷 Diproses oleh: @fzein  ← INI YANG DICEK!

Pilih bank tujuan transfer:
```

### Cara Kerja

| Step | Admin A (@fzein) | Admin B (@ridwan) |
|------|-----------------|-------------------|
| 1 | Fetch message → tidak ada "Diproses oleh" | Fetch message → tidak ada "Diproses oleh" |
| 2 | Klik PROSES | Klik PROSES (hampir bersamaan) |
| 3 | Bot edit: "Diproses oleh: @fzein" | (klik tidak efektif) |
| 4 | Verify → "@fzein" = **KITA** → ✓ | Verify → "@fzein" ≠ @ridwan → **ABORT** |
| 5 | **Lanjut transfer** | **SKIP** (tidak transfer) |

### Layer Proteksi

1. **Pre-Click Check**
   - Fresh fetch message dari Telegram
   - Cek apakah sudah ada "Diproses oleh: @xxx"
   - Jika ada dan bukan username kita → SKIP

2. **Post-Click Verification** (3x retry, total ~9 detik)
   - Setelah klik PROSES, tunggu 3 detik
   - Fetch ulang message, extract "Diproses oleh: @xxx"
   - Jika @xxx = username kita → VERIFIED ✓
   - Jika @xxx = user lain → ABORT, tidak transfer

3. **Shared Claim File** (untuk PC yang sama)
   - File `inject_dana_claimed.json` dengan file locking
   - Mencegah 2 instance di PC yang sama claim bersamaan

4. **Final Guard** (sebelum transfer)
   - Cek ulang success file
   - Cek ulang claimed file
   - Jika sudah di-handle → SKIP

### Log Output

Contoh log saat berhasil claim:
```
[12:30:15] [BCA RIDWAN] claim: Fresh fetch message... (my_username=@ridwan)
[12:30:16] [BCA RIDWAN] claim: Clicked PROSES, verifying 'Diproses oleh'...
[12:30:19] [BCA RIDWAN] claim: VERIFIED ✓ - Diproses oleh @ridwan (KITA!)
[12:30:20] [BCA RIDWAN] Request claimed! Lanjut transfer...
```

Contoh log saat di-skip (orang lain claim duluan):
```
[12:30:15] [BCA SALSA] claim: Fresh fetch message... (my_username=@salsa)
[12:30:16] [BCA SALSA] claim: Clicked PROSES, verifying 'Diproses oleh'...
[12:30:19] [BCA SALSA] claim: ABORT - Diproses oleh @ridwan (bukan kita @salsa)
[12:30:19] [INJ-123] SKIP - Request sudah selesai/diklaim user lain
```

---

## Cara Penggunaan

### Workflow Normal

1. **Start aplikasi**
   - Jalankan INJECT DANA dari shortcut
   - Klik **▶ Start**
   - Login Telegram via QR code (sekali saja, session tersimpan)

2. **Monitoring**
   - Aplikasi otomatis monitor grup Telegram
   - Request "KONFIRMASI SUNTIK" akan muncul di tabel

3. **Proses Request**
   - Pilih request di tabel
   - Klik tombol **▶** di kolom action
   - Aplikasi akan:
     - Transfer via myBCA HP
     - Klik tombol "PROSES" di Telegram
     - Pilih bank yang dipakai
     - Kirim biaya transfer
     - Ambil & kirim screenshot

4. **Check Result**
   - Status berubah jadi **Sukses** atau **Gagal**
   - Screenshot bisa dilihat dengan klik tombol **📷**

### Retry Failed Request

1. Pilih request dengan status Gagal/Error/Timeout
2. Klik tombol **↻** (Retry)
3. Request akan di-reset dan bisa diproses ulang

### Batalkan Request

1. Pilih request dengan status Pending
2. Klik tombol **❌** (Batal)
3. Status berubah jadi "Batal"

### Auto-Fetch Pending Requests

Saat aplikasi baru dibuka dan Telegram connected, aplikasi akan otomatis:
- Scan 100 pesan terakhir di grup
- Ambil request "KONFIRMASI SUNTIK" yang belum diproses
- Tampilkan di tabel

---

## Troubleshooting

### Telegram tidak connect

**Gejala**: Status TG tetap "○ Offline"

**Solusi**:
1. Pastikan `api_id` dan `api_hash` sudah diisi di config
2. Logout dan login ulang via QR code
3. Pastikan koneksi internet stabil

### HP tidak terdeteksi

**Gejala**: Tabel bank kosong atau status "Error"

**Solusi**:
1. Cek koneksi USB
2. Pastikan USB Debugging aktif
3. Allow USB debugging dari PC ini
4. Jalankan ulang:
   ```batch
   adb kill-server
   adb start-server
   adb devices
   ```

### Transfer gagal

**Gejala**: Status "Gagal" atau "Timeout"

**Kemungkinan penyebab**:
- Saldo tidak cukup
- Password/PIN salah
- myBCA HP butuh update
- Session expired (perlu login ulang di myBCA)

**Solusi**:
1. Cek saldo mencukupi
2. Verifikasi password & PIN di config
3. Manual login myBCA HP sekali
4. Retry request

### QR Code tidak muncul

**Gejala**: Dialog QR kosong atau error

**Solusi**:
1. Pastikan package `qrcode` terinstall:
   ```batch
   pip install qrcode[pil]
   ```
2. Restart aplikasi

### Request tidak masuk ke tabel

**Gejala**: Ada request di Telegram tapi tidak muncul di GUI

**Solusi**:
1. Pastikan `group_chat_id` benar
2. Pastikan `bot_username` benar
3. Request harus format "KONFIRMASI SUNTIK" dari bot

---

## File-File Penting

| File | Fungsi |
|------|--------|
| `INJECT_DANA.py` | Script utama |
| `inject_dana_config.json` | Konfigurasi (API, banks, settings) |
| `inject_success.json` | Daftar ticket yang sudah sukses diproses |
| `inject_dana_claimed.json` | **NEW v2.5** - Daftar ticket yang sedang diklaim (anti-double) |
| `inject_dana_pending.json` | Cache pending requests |
| `screenshots/INJECT_DANA/` | Folder screenshot bukti transfer |
| `RUN_INJECT_DANA.bat` | Script untuk menjalankan aplikasi |
| `POST_INSTALL_INJECT_DANA.bat` | Script setup packages |

---

## Catatan Keamanan

⚠️ **PENTING**:
- Jangan share file `inject_dana_config.json` karena berisi session Telegram dan kredensial bank
- Gunakan fitur **Auto Process** dengan hati-hati
- Selalu backup konfigurasi sebelum update
- Session Telegram tersimpan, logout jika menggunakan PC bersama

---

## Version History

### v2.5 (28 Feb 2026)
- **Anti double-processing untuk 2 admin di PC berbeda**
  - Verifikasi "Diproses oleh: @username" dari bot Telegram
  - Jika request diklaim oleh admin lain → otomatis SKIP, tidak transfer
  - Shared claim file dengan file locking (untuk mencegah race condition di PC sama)
  - Post-click verification 3x retry (total ~9 detik) untuk memastikan kita yang berhasil klaim
  - Final guard sebelum transfer: cek ulang success file + claimed file
- Pre-click check: Fresh fetch message sebelum klik PROSES
- Simpan `_my_username` dari session Telegram untuk verifikasi

### v2.4 (27 Feb 2026)
- Speed optimize - adaptive waits, resourceId lookups, fast PIN
- Hapus xpath untuk navigasi lebih cepat

### v2.3 (26 Feb 2026)
- Multi-HP parallel dengan round-robin dispatch
- HP baru auto-detect & auto-start worker
- Cek saldo sebelum claim (tidak claim jika saldo tidak cukup)
- Saldo tidak cukup = requeue ke HP lain, bukan gagal

### v2.2 (25 Feb 2026)
- Anti double-processing dasar (klik PROSES sebelum transfer)

### v2.1 (23 Feb 2026)
- Tambah action buttons (Proses, Retry, Batal) per row
- Auto-fetch pending requests dari Telegram saat connect
- Perbaikan column resize di tabel
- Hapus context menu (klik kanan)
- Clean installer config (tanpa session)

### v2.0 (22 Feb 2026)
- Initial release
- QR Code login Telegram
- Multi-bank support
- Realtime monitoring
- Auto screenshot & report

---

## Support

Jika ada kendala atau pertanyaan:
1. Cek log di panel kanan
2. Lihat file log di folder `logs/`
3. Hubungi admin LELEPAY Team

---

*INJECT DANA v2.5 - LELEPAY Team © 2026*
