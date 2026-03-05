#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
INJECT DANA v3.0 - Auto Suntikan via Telethon + myBCA HP
=========================================================
1 Mar 2026

v3.0.19: Fix dispatch ke HP disconnect
    - Dispatcher skip worker yang ADB-nya sudah putus (real-time check)
    - Status bank otomatis jadi Disconnected dan saldo reset
    - Cegah request salah kirim ke rekening dari device yang sudah cabut
v3.0: Fair distribution untuk multi-user
  - Random delay 0.5-3 detik sebelum claim request
  - Distribusi job lebih merata antar 3 PC
  - Bukan selalu PC tercepat yang menang
v2.9: Force cancel untuk request stuck
  - Request Dispatched/In Progress bisa di-force cancel
  - Klik ? pada request stuck ? konfirmasi ? Gagal (Force)
  - Hapus disconnect HP dari tabel Bank (klik kanan)
v2.8: Fix double transfer pada restart app
  - Bug: Saat app restart, pesan yang sama bisa di-proses 2x
  - Cause: fetch_pending + NewMessage event duplicate
  - Fix: Track processed msg IDs dalam TelethonWorker
  - _processed_msg_ids set mencegah msg yang sama diproses ulang
v2.7: Big Amount threshold + Verifikasi nama
  - Request > 20 juta tidak di-auto proses (status "Big Amount")
  - Klik manual tombol ? di GUI untuk proses Big Amount
  - Verifikasi nama penerima dari bank sebelum transfer
  - Jika nama tidak cocok ? ABORT, status "Gagal - Nama Salah"
v2.6: Verifikasi nama penerima sebelum transfer
  - Scrape nama penerima dari bank setelah isi rekening
  - Bandingkan dengan nama di request Telegram
  - Jika TIDAK COCOK ? ABORT transfer, status "Gagal - Nama Salah"
  - Mencegah salah transfer ke rekening yang berbeda
v2.5: Anti double-processing untuk 2 admin di PC berbeda
  - Verifikasi "Diproses oleh: @username" dari bot Telegram
  - Cek username siapa yang klik PROSES ? bukan kita = SKIP
  - Shared claim file dengan file locking (untuk PC sama)
  - Post-click verification 3x retry dengan timeout 60s
  - Final guard sebelum transfer: cek ulang success + claimed file
v2.4: Speed optimize - adaptive waits, resourceId lookups, fast PIN, no xpath
v2.3: Multi-HP parallel + auto hotplug + saldo check before claim
  - Round-robin dispatch ke semua HP (bukan 1 HP saja)
  - HP baru dicolok auto-detect & auto-start worker
  - Cek saldo sebelum claim (klik PROSES)
  - Saldo tidak cukup = requeue ke HP lain, bukan gagal
v2.2: Anti double-processing (klik PROSES sebelum transfer)
v2.1: Telegram connection stability fix

Architecture:
  - Login Telegram sebagai USER (Telethon) di GUI
  - Monitor grup untuk request suntikan
  - Klik PROSES dulu (claim) untuk mencegah double processing
  - Verifikasi "Diproses oleh: @username" untuk anti-double 2 admin
  - Verifikasi nama penerima cocok dengan request
  - Big Amount (>20jt) tidak di-auto proses
  - Admin klik PROSES di GUI -> auto transfer myBCA HP
  - Setelah sukses: auto pilih bank, kirim biaya, screenshot

Requires:
  pip install telethon uiautomator2 requests
"""

from __future__ import annotations

import os, sys, re, json, time, queue, threading, subprocess, asyncio, logging, shutil
from dataclasses import dataclass
from typing import Optional, Dict, List, Tuple

# ===== PySide6 (Qt) =====
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTabWidget, QVBoxLayout, QHBoxLayout,
    QGroupBox, QPushButton, QLabel, QLineEdit, QCheckBox, QTextEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QSplitter, QDialog,
    QFormLayout, QDialogButtonBox, QMessageBox, QMenu, QAbstractItemView,
    QStyle
)
from PySide6.QtCore import Qt, QTimer, Signal, QSize
from PySide6.QtGui import QColor, QFont, QIcon, QPixmap, QPainter, QAction, QCursor, QBrush, QPainterPath

# ===== QR Code =====
try:
    import qrcode
    HAS_QRCODE = True
except ImportError:
    qrcode = None
    HAS_QRCODE = False

# ===== Telethon =====
try:
    from telethon import TelegramClient, events
    from telethon.tl.types import (
        MessageMediaPhoto, KeyboardButtonCallback,
        ReplyInlineMarkup, KeyboardButtonRow,
    )
    from telethon.tl.custom import Button
    from telethon.sessions import StringSession
    from telethon.errors import SessionPasswordNeededError
    HAS_TELETHON = True
except ImportError:
    HAS_TELETHON = False
    print("[WARNING] telethon not installed. pip install telethon")

# ===== uiautomator2 =====
try:
    import uiautomator2 as u2
    
    # Monkey-patch with_package_resource for frozen EXE
    # PyInstaller bundles assets in _MEIPASS but importlib.resources can't find them
    if getattr(sys, 'frozen', False) and u2:
        import uiautomator2.utils as _u2_utils
        import contextlib
        import pathlib
        
        _original_wpr = _u2_utils.with_package_resource
        
        @contextlib.contextmanager
        def _patched_with_package_resource(filename):
            """Check _MEIPASS first for bundled assets."""
            meipass = getattr(sys, '_MEIPASS', None)
            if meipass:
                meipass_path = pathlib.Path(meipass) / "uiautomator2" / filename
                if meipass_path.exists():
                    yield meipass_path
                    return
                # Also check directly in _MEIPASS
                direct_path = pathlib.Path(meipass) / filename
                if direct_path.exists():
                    yield direct_path
                    return
            # Fallback to original
            with _original_wpr(filename) as f:
                yield f
        
        _u2_utils.with_package_resource = _patched_with_package_resource
        # Also patch in core and _input modules
        try:
            import uiautomator2.core as _u2_core
            _u2_core.with_package_resource = _patched_with_package_resource
        except Exception:
            pass
        try:
            import uiautomator2._input as _u2_input
            _u2_input.with_package_resource = _patched_with_package_resource
        except Exception:
            pass
        
except ImportError:
    u2 = None

# ===== requests =====
try:
    import requests as http_requests
except ImportError:
    http_requests = None

# ===== Auto-updater =====
try:
    import inject_dana_updater as updater
    HAS_UPDATER = True
except ImportError:
    updater = None
    HAS_UPDATER = False


# ======================================================================
# CONFIG
# ======================================================================
APP_VERSION = "3.0.19"  # Current app version for update check

# Subprocess flags to hide terminal windows on Windows
SUBPROCESS_FLAGS = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0

# Handle both frozen (EXE) and non-frozen (script) cases for paths
if getattr(sys, 'frozen', False):
    # Running as bundled EXE - use exe location for config files
    SCRIPT_DIR = os.path.dirname(sys.executable)
    # Find Python executable for subprocess calls (search common locations)
    _python_paths = [
        shutil.which("python"),
        shutil.which("python3"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Python", "Python314", "python.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Python", "Python313", "python.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Python", "Python312", "python.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Python", "Python311", "python.exe"),
        "C:\\Python314\\python.exe",
        "C:\\Python313\\python.exe",
        "C:\\Python312\\python.exe",
    ]
    PYTHON_EXE = None
    for p in _python_paths:
        if p and os.path.isfile(p):
            PYTHON_EXE = p
            break
else:
    # Running as script
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    PYTHON_EXE = sys.executable

CONFIG_FILE = os.path.join(SCRIPT_DIR, "inject_dana_config.json")
SESSION_FILE = os.path.join(SCRIPT_DIR, "inject_dana_session")
SCREENSHOT_FOLDER = os.path.join(SCRIPT_DIR, "screenshots", "INJECT_DANA")
SUCCESS_FILE = os.path.join(SCRIPT_DIR, "inject_success.json")
PENDING_FILE = os.path.join(SCRIPT_DIR, "inject_dana_pending.json")

# Big Amount threshold - request > 20 juta tidak di-auto proses
BIG_AMOUNT_THRESHOLD = 20_000_000

DEFAULT_CONFIG = {
    "api_id": "34768359",
    "api_hash": "22c3fa3db2a61b8976c431e7b9027fe5",
    "phone": "",
    "session_string": "",
    "group_chat_id": -1001655728988,       # Chat ID grup yang di-monitor
    "bot_username": "",        # Username bot Charlie Gemini (tanpa @)
    "banks": [],               # [{device_id, password, pin, name, rekening}]
    "auto_process": False,     # False = tampil dulu di GUI
    "biaya_bifast": 2500,
    "biaya_realtime": 6500,
}

def load_config() -> dict:
    print(f"[DEBUG] CONFIG_FILE path: {CONFIG_FILE}")
    print(f"[DEBUG] CONFIG_FILE exists: {os.path.exists(CONFIG_FILE)}")
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            print(f"[DEBUG] Loaded api_id: {cfg.get('api_id', 'NOT FOUND')}")
            for k, v in DEFAULT_CONFIG.items():
                if k not in cfg:
                    cfg[k] = v
            return cfg
        except Exception as e:
            print(f"[DEBUG] Config load error: {e}")
            pass
    print(f"[DEBUG] Using DEFAULT_CONFIG, api_id: {DEFAULT_CONFIG.get('api_id')}")
    return DEFAULT_CONFIG.copy()

def save_config(cfg: dict):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[CONFIG] Save error: {e}")


def save_pending_requests(requests: dict):
    """Save pending requests to file for persistence."""
    try:
        data = []
        for rid, req in requests.items():
            # Only save non-completed requests
            if req.status not in ["Sukses"]:
                data.append({
                    "request_id": req.request_id,
                    "chat_id": req.chat_id,
                    "message_id": req.message_id,
                    "original_msg_id": req.original_msg_id,
                    "no_rek": req.no_rek,
                    "nama_bank": req.nama_bank,
                    "jenis_bank": req.jenis_bank,
                    "nominal": req.nominal,
                    "nominal_raw": req.nominal_raw,
                    "asset_web": req.asset_web,
                    "saldo_akhir": req.saldo_akhir,
                    "request_by": req.request_by,
                    "status": req.status,
                    "bank_used": req.bank_used,
                    "bank_device": req.bank_device,
                    "screenshot_path": req.screenshot_path,
                    "biaya_bank": req.biaya_bank,
                    "raw_text": req.raw_text,
                    "timestamp": req.timestamp,
                    "proses_callback_data": req.proses_callback_data.hex() if req.proses_callback_data else "",
                })
        with open(PENDING_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[PENDING] Save error: {e}")


def load_pending_requests() -> List[SuntikanRequest]:
    """Load pending requests from file."""
    requests = []
    if os.path.exists(PENDING_FILE):
        try:
            with open(PENDING_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            for item in data:
                cb_data = bytes.fromhex(item.get("proses_callback_data", "")) if item.get("proses_callback_data") else b""
                req = SuntikanRequest(
                    request_id=item.get("request_id", ""),
                    chat_id=item.get("chat_id", 0),
                    message_id=item.get("message_id", 0),
                    original_msg_id=item.get("original_msg_id", 0),
                    no_rek=item.get("no_rek", ""),
                    nama_bank=item.get("nama_bank", ""),
                    jenis_bank=item.get("jenis_bank", ""),
                    nominal=item.get("nominal", 0),
                    nominal_raw=item.get("nominal_raw", ""),
                    asset_web=item.get("asset_web", ""),
                    saldo_akhir=item.get("saldo_akhir", ""),
                    request_by=item.get("request_by", ""),
                    status=item.get("status", "Pending"),
                    bank_used=item.get("bank_used", ""),
                    bank_device=item.get("bank_device", ""),
                    screenshot_path=item.get("screenshot_path", ""),
                    biaya_bank=item.get("biaya_bank", 0),
                    raw_text=item.get("raw_text", ""),
                    timestamp=item.get("timestamp", ""),
                    proses_callback_data=cb_data,
                )
                # Reset "Dispatched"/"On Progress"/"Claiming..." ke "Pending" saat reload
                if req.status in ("Dispatched", "On Progress", "Claiming..."):
                    req.status = "Pending"
                requests.append(req)
        except Exception as e:
            print(f"[PENDING] Load error: {e}")
    return requests


# ======================================================================
# ANTI-DOUBLE
# ======================================================================
_success_lock = threading.Lock()
CLAIMED_FILE = os.path.join(SCRIPT_DIR, "inject_dana_claimed.json")
_claimed_lock = threading.Lock()

def _load_success() -> set:
    with _success_lock:
        if os.path.exists(SUCCESS_FILE):
            try:
                with open(SUCCESS_FILE, "r") as f:
                    return set(json.load(f))
            except Exception:
                pass
    return set()

def _save_success(ticket: str):
    with _success_lock:
        # Read directly (don't call _load_success to avoid deadlock)
        tickets = set()
        if os.path.exists(SUCCESS_FILE):
            try:
                with open(SUCCESS_FILE, "r") as f:
                    tickets = set(json.load(f))
            except Exception:
                pass
        tickets.add(ticket)
        try:
            with open(SUCCESS_FILE, "w") as f:
                json.dump(list(tickets), f)
        except Exception:
            pass


def _try_claim_file(rid: str, claimer_id: str) -> bool:
    """Atomically try to claim a request via shared file.
    Returns True if WE successfully claimed it (or already claimed by us).
    Returns False if another instance already claimed it.
    Uses file locking for cross-process safety.
    """
    import msvcrt
    with _claimed_lock:
        try:
            # Ensure file exists
            if not os.path.exists(CLAIMED_FILE):
                with open(CLAIMED_FILE, "w") as f:
                    json.dump({}, f)
            with open(CLAIMED_FILE, "r+") as f:
                # Lock the file (exclusive, non-blocking ? retry with blocking)
                try:
                    msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, max(1, os.path.getsize(CLAIMED_FILE)))
                except OSError:
                    # Another process holds the lock, wait up to 5s
                    try:
                        msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, max(1, os.path.getsize(CLAIMED_FILE)))
                    except OSError:
                        return False  # Cannot acquire lock
                try:
                    f.seek(0)
                    content = f.read().strip()
                    claimed = json.loads(content) if content else {}
                    if rid in claimed:
                        # Already claimed - check if by us
                        return claimed[rid] == claimer_id
                    # Not claimed yet - claim it
                    claimed[rid] = claimer_id
                    f.seek(0)
                    f.truncate()
                    json.dump(claimed, f)
                    f.flush()
                    return True
                finally:
                    # Unlock
                    try:
                        f.seek(0)
                        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, max(1, os.path.getsize(CLAIMED_FILE)))
                    except Exception:
                        pass
        except Exception as e:
            print(f"[CLAIM] _try_claim_file error: {e}")
            return False


def _is_claimed_by_other(rid: str, claimer_id: str) -> bool:
    """Check if request was claimed by a DIFFERENT instance."""
    try:
        if os.path.exists(CLAIMED_FILE):
            with open(CLAIMED_FILE, "r") as f:
                claimed = json.load(f)
            if rid in claimed and claimed[rid] != claimer_id:
                return True
    except Exception:
        pass
    return False


# ======================================================================
# SCREENSHOT
# ======================================================================
def save_screenshot(device, rid: str, bank_name: str = "") -> str:
    try:
        os.makedirs(SCREENSHOT_FOLDER, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        fname = re.sub(r'[^\w\-.]', '_', f"inject_{rid}_{bank_name}_{ts}.png")
        path = os.path.join(SCREENSHOT_FOLDER, fname)
        img = device.screenshot()
        img.save(path)
        return path
    except Exception as e:
        print(f"[SS] {e}")
        return ""


# ======================================================================
# DATA MODEL
# ======================================================================
@dataclass
class SuntikanRequest:
    request_id: str
    chat_id: int = 0
    message_id: int = 0          # ID pesan konfirmasi Charlie Gemini (yang punya tombol PROSES)
    original_msg_id: int = 0     # ID pesan request asli
    no_rek: str = ""
    nama_bank: str = ""
    jenis_bank: str = ""
    nominal: int = 0
    nominal_raw: str = ""
    asset_web: str = ""
    saldo_akhir: str = ""
    request_by: str = ""
    status: str = "Pending"
    bank_used: str = ""
    bank_device: str = ""
    screenshot_path: str = ""
    biaya_bank: int = 0
    raw_text: str = ""
    timestamp: str = ""
    # Telegram callback data
    proses_callback_data: bytes = b""  # Callback data tombol PROSES
    proses_already_clicked: bool = False  # Flag if PROSES already clicked during claim


# ======================================================================
# PARSER
# ======================================================================
def _parse_nominal(raw: str) -> int:
    raw = (raw or "").strip().lower()
    m = re.match(r'([\d.,]+)\s*(?:jt|juta)', raw)
    if m:
        return int(float(m.group(1).replace(',', '.')) * 1_000_000)
    m = re.match(r'([\d.,]+)\s*(?:rb|ribu)', raw)
    if m:
        return int(float(m.group(1).replace(',', '.')) * 1_000)
    digits = re.sub(r'[^\d]', '', raw)
    return int(digits) if digits else 0


def parse_konfirmasi_message(text: str) -> Optional[dict]:
    """
    Parse pesan KONFIRMASI SUNTIK DANA atau "Suntikan siap diproses" dari Charlie Gemini.
    
    Format 1 (KONFIRMASI):
    KONFIRMASI SUNTIK DANA
    No Rek: 1370796064
    Jenis Bank: BCA
    Nama: SULTAN MUHAMAD PAUJI
    Nominal: 10 jt (10.000.000)
    Saldo Akhir: 5,655,768 (5.655.768)
    
    Format 2 (Siap Proses):
    ?? Suntikan siap diproses!
    ?? No Rek: 0092758751
    ?? Nama: LAELA LESTARI
    ?? Bank: BCA
    ?? Nominal: 15 JT
    """
    if not text:
        return None
    text_upper = text.upper()
    if "KONFIRMASI SUNTIK" not in text_upper and "SUNTIKAN SIAP DIPROSES" not in text_upper:
        return None

    data = {}
    # No Rek - support with/without emoji prefix
    m = re.search(r'No\s*Rek\s*:\s*(\d+)', text)
    if m: data["no_rek"] = m.group(1)

    # Jenis Bank / Bank - support both formats
    m = re.search(r'(?:Jenis\s*)?Bank\s*:\s*(\S+)', text)
    if m: data["jenis_bank"] = m.group(1).strip()

    # Nama
    m = re.search(r'Nama\s*:\s*(.+)', text)
    if m: data["nama_bank"] = m.group(1).strip()

    # Nominal - ambil yang di dalam kurung jika ada
    m = re.search(r'Nominal\s*:\s*(.+)', text)
    if m:
        raw = m.group(1).strip()
        # Coba ambil angka dalam kurung: "10 jt (10.000.000)" -> 10000000
        m2 = re.search(r'\(([\d.,]+)\)', raw)
        if m2:
            data["nominal"] = re.sub(r'[^\d]', '', m2.group(1))
        else:
            data["nominal"] = raw

    # Saldo Akhir (optional in format 2)
    m = re.search(r'Saldo\s*Akhir\s*:\s*(.+)', text)
    if m: data["saldo_akhir"] = m.group(1).strip()

    return data if "no_rek" in data else None


def parse_request_message(text: str) -> Optional[dict]:
    """
    Parse pesan request asli dari user.
    Format:
    No Rek Bank : 1370796064
    Nama Bank : SULTAN MUHAMAD PAUJI
    Jenis Bank : BCA
    Nominal Suntik : 10 jt
    Asset WEB : PGBET
    Saldo Akhir : 5,655,768
    Request By : FerryH
    """
    if not text:
        return None

    data = {}
    m = re.search(r'No\s*Rek(?:\s*Bank)?\s*:\s*(\S+)', text, re.I)
    if m: data["no_rek"] = re.sub(r'[^\d]', '', m.group(1))

    m = re.search(r'Nama\s*(?:Bank)?\s*:\s*(.+)', text, re.I)
    if m: data["nama_bank"] = m.group(1).strip()

    m = re.search(r'Jenis\s*Bank\s*:\s*(.+)', text, re.I)
    if m: data["jenis_bank"] = m.group(1).strip()

    m = re.search(r'Nominal\s*(?:Suntik|Transfer)?\s*:\s*(.+)', text, re.I)
    if m: data["nominal"] = m.group(1).strip()

    m = re.search(r'Asset\s*WEB\s*:\s*(.+)', text, re.I)
    if m: data["asset_web"] = m.group(1).strip()

    m = re.search(r'Saldo\s*Akhir\s*:\s*(.+)', text, re.I)
    if m: data["saldo_akhir"] = m.group(1).strip()

    m = re.search(r'Request\s*By\s*:\s*(.+)', text, re.I)
    if m: data["request_by"] = m.group(1).strip()

    return data if "no_rek" in data else None


# ======================================================================
# ADB HELPERS
# ======================================================================
def adb_shell(device_id: str, *args) -> str:
    try:
        cmd = ["adb", "-s", device_id, "shell"] + list(args)
        return subprocess.check_output(cmd, timeout=10, stderr=subprocess.STDOUT, creationflags=SUBPROCESS_FLAGS).decode("utf-8", errors="ignore")
    except Exception as e:
        return f"ERROR: {e}"


# ======================================================================
# MyBCA TRANSFER WORKER
# ======================================================================
class MyBcaTransferWorker(threading.Thread):
    KEYPAD = {
        '1': (131, 1050), '2': (360, 1050), '3': (589, 1050),
        '4': (131, 1178), '5': (360, 1178), '6': (589, 1178),
        '7': (131, 1306), '8': (360, 1306), '9': (589, 1306),
        '0': (360, 1434),
    }

    def __init__(self, ui_q: queue.Queue, job_q: queue.Queue,
                 device_id: str, password: str, pin: str,
                 bank_name: str = "", rekening: str = "",
                 app=None):
        super().__init__(daemon=True)
        self.ui_q = ui_q
        self.job_q = job_q
        self.device_id = device_id
        self.password = password
        self.pin = pin
        self.bank_name = bank_name
        self.rekening = rekening
        self.app = app  # Reference to InjectDanaApp for accessing tg_worker
        self.d = None
        self._stop = threading.Event()
        self._done: set = set()
        self._inflight: set = set()
        self.current_saldo: int = 0
        self._ready: bool = False  # True setelah login + saldo berhasil
        self._t_start: float = time.monotonic()
        self._t_last: float = self._t_start

    def stop(self):
        self._stop.set()

    def _log(self, msg):
        ts = time.strftime("%H:%M:%S")
        full = f"[{ts}] [{self.bank_name or self.device_id}] {msg}"
        self.ui_q.put(("log", full))
        print(full)

    # -- Step-timing helpers (from transfer.py) ----------------------
    def _timer_reset(self):
        now = time.monotonic()
        self._t_start = now
        self._t_last = now

    def _log_step(self, step: str) -> float:
        now = time.monotonic()
        delta = now - self._t_last
        total = now - self._t_start
        self._log(f"[TIMER] {step}: {delta:.2f}s (total: {total:.2f}s)")
        self._t_last = now
        return delta

    def _log_total(self, label: str = "Total") -> float:
        total = time.monotonic() - self._t_start
        self._log(f"[TIMER] === {label}: {total:.2f}s ===")
        return total

    def _is_device_alive(self) -> bool:
        """Check if ADB device is still connected."""
        try:
            out = subprocess.check_output(
                ["adb", "-s", self.device_id, "get-state"],
                timeout=5, stderr=subprocess.STDOUT, creationflags=SUBPROCESS_FLAGS
            ).decode("utf-8", errors="ignore").strip()
            return out == "device"
        except Exception:
            return False

    def _reinit_uiautomator2(self) -> bool:
        """Reinitialize uiautomator2 when INJECT_EVENTS permission error occurs."""
        self._log("Reinitializing uiautomator2...")
        self.ui_q.put(("update_bank", (self.device_id, "status", "Reinit U2...")))
        try:
            # Stop ATX agent first
            self._adb("am", "force-stop", "com.github.uiautomator")
            time.sleep(1)
            self._adb("am", "force-stop", "com.github.uiautomator.test")
            time.sleep(1)
            
            # Run python -m uiautomator2 init
            if not PYTHON_EXE:
                self._log("Python not found, cannot run uiautomator2 init")
                return False
            self._log("Running: python -m uiautomator2 init")
            result = subprocess.run(
                [PYTHON_EXE, "-m", "uiautomator2", "init", "--serial", self.device_id],
                capture_output=True, text=True, timeout=60, creationflags=SUBPROCESS_FLAGS
            )
            if result.returncode == 0:
                self._log("uiautomator2 reinit OK")
                time.sleep(2)
                # Reconnect
                self.d = u2.connect(self.device_id)
                self.d.healthcheck = False
                self._log(f"Reconnected to {self.device_id}")
                self.ui_q.put(("update_bank", (self.device_id, "status", "Connected")))
                return True
            else:
                self._log(f"Reinit failed: {result.stderr}")
                return False
        except Exception as e:
            self._log(f"Reinit error: {e}")
            return False

    def _connect(self) -> bool:
        if not u2:
            self._log("ERROR: uiautomator2 not installed!")
            return False
        
        def _try_connect():
            """Connect + test ATX. Returns True if OK."""
            self.d = u2.connect(self.device_id)
            self.d.jsonrpc.deviceInfo()  # Will throw if ATX not running
            self.d.healthcheck = False
            return True
        
        # Attempt 1: connect langsung
        try:
            _try_connect()
            self._log(f"Connected to {self.device_id}")
            self.ui_q.put(("update_bank", (self.device_id, "status", "Connected")))
            return True
        except Exception as e1:
            self._log(f"ATX not responding ({e1}), auto-installing...")
        
        # ATX belum ada ? install
        self.ui_q.put(("update_bank", (self.device_id, "status", "Installing ATX...")))
        try:
            if not PYTHON_EXE:
                self._log("Python not found on system, cannot install ATX")
                self.ui_q.put(("update_bank", (self.device_id, "status", "Python not found")))
                return False
            self._log("Running: python -m uiautomator2 init")
            result = subprocess.run(
                [PYTHON_EXE, "-m", "uiautomator2", "init", "--serial", self.device_id],
                capture_output=True, text=True, timeout=120, creationflags=SUBPROCESS_FLAGS
            )
            if result.returncode != 0:
                self._log(f"ATX install failed: {result.stderr[:300]}")
                self.ui_q.put(("update_bank", (self.device_id, "status", "ATX Failed")))
                return False
            self._log("ATX install OK, reconnecting...")
            time.sleep(3)
        except Exception as e2:
            self._log(f"ATX install error: {e2}")
            self.ui_q.put(("update_bank", (self.device_id, "status", "ATX Failed")))
            return False
        
        # Attempt 2: connect setelah install
        try:
            _try_connect()
            self._log(f"Connected to {self.device_id}")
            self.ui_q.put(("update_bank", (self.device_id, "status", "Connected")))
            return True
        except Exception as e3:
            self._log(f"Connect failed after ATX install: {e3}")
            self.ui_q.put(("update_bank", (self.device_id, "status", "Error")))
            return False

    def _adb(self, *args): return adb_shell(self.device_id, *args)
    def _shell(self, cmd, timeout=5):
        """Fast ADB shell via uiautomator2 RPC (HTTP) instead of subprocess."""
        try:
            out = self.d.shell(cmd, timeout=timeout)
            return out[0] if isinstance(out, (list, tuple)) else (out or "")
        except Exception:
            return ""
    def _tap(self, x, y): self._shell(f"input tap {x} {y}")

    # ===== OPTIMIZED: Batch PIN Entry =====
    _PIN_BATCH_SLEEP = 0.25
    
    def _enter_pin_batch(self, pin: str) -> bool:
        """Enter PIN via single ADB shell with chained taps. Much faster than sequential."""
        try:
            cmds = []
            for ch in str(pin):
                if ch not in self.KEYPAD:
                    return False
                x, y = self.KEYPAD[ch]
                cmds.append(f"input tap {x} {y}")
            
            batch_cmd = f" && sleep {self._PIN_BATCH_SLEEP} && ".join(cmds)
            subprocess.check_output(
                ["adb", "-s", self.device_id, "shell", batch_cmd],
                timeout=10, creationflags=SUBPROCESS_FLAGS
            )
            self._log("PIN: batch mode OK")
            return True
        except Exception as e:
            self._log(f"PIN: batch failed: {e}")
            return False

    def _input_text(self, text):
        """Fast text input via u2 RPC shell."""
        if not text: return
        safe = text.replace(" ", "%s")
        self._shell(f"input text {safe}")

    def _force_stop_mybca(self):
        try:
            self._adb("am", "force-stop", "com.bca.mybca.omni.android")
            time.sleep(1)
        except Exception: pass

    def _launch_mybca(self):
        try:
            self._adb("input", "keyevent", "KEYCODE_WAKEUP")
            time.sleep(0.3)
            self._adb("input", "keyevent", "KEYCODE_HOME")
            time.sleep(0.5)
        except Exception: pass
        try:
            if self.d:
                self.d.app_start("com.bca.mybca.omni.android")
            else:
                self._adb("monkey", "-p", "com.bca.mybca.omni.android",
                           "-c", "android.intent.category.LAUNCHER", "1")
        except Exception: pass
        time.sleep(2)

    def _wake_and_start(self):
        self._launch_mybca()
        time.sleep(1)

    def _is_at_home(self) -> bool:
        """Cek apakah myBCA sudah di halaman beranda (bukan Transfer menu)"""
        try:
            # Beranda has: "Menu Utama" or "HALO" or "Mutasi Rekening"
            # Transfer menu page has: "Rekening BCA", "Bank Lain" list
            if self.d(text="Menu Utama").exists: return True
            if self.d(textContains="HALO,").exists: return True
            if self.d(text="Mutasi Rekening").exists: return True
            # Check for bottom nav "Beranda" being selected (darker)
            if self.d(textContains="Saldo Aktif").exists: return True
        except Exception: pass
        return False

    def _handle_session_expired(self) -> bool:
        """Handle popup 'Sesi Anda telah habis'"""
        try:
            if self.d(textContains="Sesi Anda telah habis").exists or \
               self.d(textContains="sesi Anda telah habis").exists:
                self._log("Session expired popup, klik OK...")
                ok = self.d(text="OK")
                if ok.exists(timeout=0.5):
                    ok.click()
                else:
                    # Fallback: cari resource ID
                    ok2 = self.d(resourceId="com.bca.mybca.omni.android:id/2131362375")
                    if ok2.exists:
                        b = ok2.info.get("bounds", {})
                        cx = (b.get("left",0) + b.get("right",0)) // 2
                        cy = (b.get("top",0) + b.get("bottom",0)) // 2
                        self.d.click(cx, cy)
                time.sleep(1.0)
                return True
        except Exception: pass
        return False

    def _force_restart_mybca(self):
        self._force_stop_mybca()
        self._launch_mybca()

    def _ensure_logged_in(self) -> bool:
        if not self.d: return False
        try:
            # Handle session expired popup
            self._handle_session_expired()

            # === FAST PATH: sudah di beranda ===
            for _ in range(5):
                if self._stop.is_set(): return False
                if self._is_at_home():
                    try:
                        beranda = self.d(text="Beranda")
                        if beranda.exists: beranda.click(); time.sleep(0.5)
                    except Exception: pass
                    self._log("Sudah login, di beranda.")
                    return True
                time.sleep(0.6)

            # === Cek stuck di layar aneh ===
            is_at_login = self.d(text="Password").exists or self.d(text="Masuk").exists
            if not self._is_at_home() and not is_at_login:
                self._log("MyBCA stuck di layar lain, force restart...")
                self._force_restart_mybca()
                time.sleep(2)
                self._handle_session_expired()
                for _ in range(5):
                    if self._is_at_home():
                        self._log("Beranda muncul setelah restart.")
                        return True
                    time.sleep(0.6)

            # === SLOW PATH: login flow ===
            self._log("Logging in...")

            # STEP 1: Klik Masuk pertama (splash screen)
            MASUK1_X, MASUK1_Y = 360, 1125
            for _ in range(10):
                if self._stop.is_set(): return False
                try:
                    if self.d(text="Password").exists: break
                    if self.d(text="Masuk").exists:
                        self.d.click(MASUK1_X, MASUK1_Y)
                        time.sleep(0.8)
                        continue
                except Exception: pass
                time.sleep(0.4)

            # STEP 2: Isi password
            if not self.d(text="Password").exists:
                self._log("Field Password tidak muncul!")
                self.ui_q.put(("update_bank", (self.device_id, "status", "Login Failed")))
                return False

            try:
                self.d(text="Password").click()
                time.sleep(0.5)
                self._input_text(self.password)
                time.sleep(0.8)
            except Exception as e:
                error_str = str(e)
                # Check for INJECT_EVENTS permission error
                if "INJECT_EVENTS" in error_str or "SecurityException" in error_str:
                    self._log("INJECT_EVENTS permission error - attempting auto-recovery...")
                    if self._reinit_uiautomator2():
                        # Retry after reinit
                        self._log("Retrying login after reinit...")
                        time.sleep(2)
                        self._force_stop_mybca()
                        time.sleep(1)
                        self._launch_mybca()
                        time.sleep(2)
                        # Try password click again (non-recursive to avoid stack overflow)
                        try:
                            self.d(text="Password").click()
                            time.sleep(0.5)
                            self._input_text(self.password)
                            time.sleep(0.8)
                        except Exception as e2:
                            self._log(f"Retry also failed: {e2}")
                            self.ui_q.put(("update_bank", (self.device_id, "status", "Login Failed")))
                            return False
                    else:
                        self._log(f"Gagal isi password: {e}")
                        self.ui_q.put(("update_bank", (self.device_id, "status", "Login Failed")))
                        return False
                else:
                    self._log(f"Gagal isi password: {e}")
                    self.ui_q.put(("update_bank", (self.device_id, "status", "Login Failed")))
                    return False

            # STEP 3: Klik Masuk kedua (submit)
            MASUK2_X, MASUK2_Y = 312, 598
            for _ in range(12):
                if self._stop.is_set(): return False
                try:
                    if self._is_at_home():
                        break
                    if self.d(text="Masuk").exists:
                        self.d.click(MASUK2_X, MASUK2_Y)
                except Exception: pass
                time.sleep(0.8)

            # STEP 4: Tunggu Transfer menu muncul
            for _ in range(15):
                if self._stop.is_set(): return False
                if self._is_at_home():
                    self._log("Login OK!")
                    return True
                time.sleep(1.0)

            self._log("Login GAGAL")
            self.ui_q.put(("update_bank", (self.device_id, "status", "Login Failed")))
            return False
        except Exception as e:
            self._log(f"Login error: {e}")
            self.ui_q.put(("update_bank", (self.device_id, "status", "Login Failed")))
            return False

    def _parse_saldo_text(self, text: str) -> int:
        """Parse text saldo -> integer. 'IDR 43,904,348.10' -> 43904348"""
        cleaned = text.upper().replace('IDR', '').replace('RP', '').strip()
        # Buang desimal .00 atau .10 di akhir
        if re.search(r'\.\d{2}$', cleaned):
            cleaned = re.sub(r'\.\d{2}$', '', cleaned)
        digits = re.sub(r'[^\d]', '', cleaned)
        return int(digits) if digits else 0

    def _try_parse_saldo_from_text(self, text: str) -> int:
        """Coba parse saldo dari berbagai format. Return 0 jika gagal."""
        t = text.strip()
        if not t or len(t) < 4:
            return 0
        # Blacklist
        up = t.upper()
        blacklist = ["REKENING", "ACCOUNT", "TRANSFER", "MENU", "BERANDA",
                     "AKTIVITAS", "QRIS", "UNTUKMU", "AKUN", "NFC", "FLAZZ",
                     "CARDLESS", "PRODUK", "PROTEKSI", "BAYAR", "INVESTASI",
                     "LIFESTYLE", "BCA ID", "HALO", "MUTASI", "GEBYAR", "SALDO AKTIF"]
        for bl in blacklist:
            if bl in up:
                return 0

        val = 0
        # Format 1: US commas "9,919,704" or "16,161,000.00"
        if re.match(r'^\d{1,3}(,\d{3})+(\.\d{2})?$', t):
            val = self._parse_saldo_text(t)
        # Format 2: ID dots "9.919.704" or "9.919.704,00"
        elif re.match(r'^\d{1,3}(\.\d{3})+(,\d{2})?$', t):
            cleaned = t
            if re.search(r',\d{2}$', cleaned):
                cleaned = re.sub(r',\d{2}$', '', cleaned)
            cleaned = cleaned.replace('.', '')
            try: val = int(cleaned)
            except: val = 0
        # Format 3: Plain digits "9919704"
        elif re.match(r'^\d{6,12}$', t):
            val = int(t)
        # Format 4: Prefixed "IDR 16,161,000.00" or "Rp 43,904,348.10"
        else:
            m = re.search(r'(?:IDR|Rp)\s*([\d,.]+)', t, re.I)
            if m:
                val = self._parse_saldo_text(m.group(1))

        if 10_000 <= val <= 100_000_000_000:
            return val
        return 0

    def _is_on_info_rekening(self) -> bool:
        """Cek apakah salah masuk halaman Informasi Rekening."""
        try:
            if self.d(text="Informasi Rekening").exists:
                return True
            if self.d(textContains="Informasi Rekening").exists:
                return True
            if self.d(text="Detail Rekening").exists:
                return True
            if self.d(text="Saldo Aktif").exists and self.d(textContains="Nomor Rekening").exists:
                return True
        except:
            pass
        return False

    def _back_to_home_from_saldo(self):
        """Kembali ke beranda dari halaman info rekening."""
        for _ in range(3):
            try:
                self.d.press("back")
                time.sleep(0.8)
                beranda = self.d(text="Beranda")
                if beranda.exists:
                    beranda.click()
                    time.sleep(1.0)
                    return
                transfer = self.d(text="Transfer")
                if transfer.exists:
                    return
            except:
                pass
        try:
            self.d(text="Beranda").click()
            time.sleep(1.0)
        except:
            pass

    def _saldo_sudah_terlihat(self) -> bool:
        """Return True jika saldo sudah muncul (ada angka, bukan bullet)."""
        try:
            for el in self.d(className="android.widget.TextView"):
                try:
                    text = (el.get_text() or "").strip()
                    if '?' in text or '***' in text:
                        continue
                    if "Rekening" in text or "rekening" in text:
                        continue
                    # Match: "70,776,080" / "70,776,080.00" / "Rp 70,776,080" / "IDR 70,776,080.00"
                    if re.search(r'(?:^|(?:Rp|IDR)\s*)\d{1,3}(,\d{3}){1,}(\.\d{2})?\s*$', text):
                        return True
                    # Match ID format: "70.776.080" / "70.776.080,00"
                    if re.search(r'^\d{1,3}(\.\d{3}){1,}(,\d{2})?$', text):
                        return True
                except:
                    pass
        except:
            pass
        return False

    def _click_eye_icon(self) -> bool:
        """Klik ikon mata untuk menampilkan saldo tersembunyi."""
        try:
            if not self.d:
                return False
            # Cek dulu - mungkin sudah terlihat
            if self._saldo_sudah_terlihat():
                self._log("Saldo sudah terlihat, tidak perlu klik eye")
                return True

            self._log("Saldo tersembunyi, mencari eye icon...")
            eye_clicked = False

            # Method 1: Cari eye via uiautomator (ImageView clickable di area saldo)
            try:
                images = self.d(className="android.widget.ImageView", clickable=True)
                for img in images:
                    try:
                        bounds = img.info.get('bounds', {})
                        left = bounds.get('left', 0)
                        top = bounds.get('top', 0)
                        right = bounds.get('right', 0)
                        bottom = bounds.get('bottom', 0)
                        cx = (left + right) // 2
                        cy = (top + bottom) // 2
                        w = right - left
                        h = bottom - top
                        if 300 < cy < 550 and cx > 450 and w < 120 and h < 120:
                            self._log(f"Klik eye ImageView di ({cx}, {cy}) size={w}x{h}")
                            img.click()
                            eye_clicked = True
                            time.sleep(1.0)
                            if self._is_on_info_rekening():
                                self._log("Eye klik salah -> Informasi Rekening, back...")
                                self._back_to_home_from_saldo()
                                time.sleep(0.5)
                                eye_clicked = False
                                continue
                            if self._saldo_sudah_terlihat():
                                self._log("Saldo muncul setelah klik eye!")
                                return True
                            time.sleep(1.0)
                            if self._saldo_sudah_terlihat():
                                self._log("Saldo muncul setelah klik eye (retry)!")
                                return True
                            break
                    except:
                        continue
            except:
                pass

            # Method 2: Hardcoded coords fallback
            if not eye_clicked:
                for ex, ey in [(624, 460), (650, 450), (600, 470)]:
                    try:
                        self._log(f"Klik eye coord ({ex}, {ey})...")
                        self.d.click(ex, ey)
                        time.sleep(1.0)
                        if self._is_on_info_rekening():
                            self._log("Klik salah -> Informasi Rekening, back...")
                            self._back_to_home_from_saldo()
                            time.sleep(0.5)
                            break
                        if self._saldo_sudah_terlihat():
                            self._log("Saldo muncul!")
                            return True
                    except:
                        continue

            self._log("Eye icon gagal, akan coba scrape langsung")
            return False
        except Exception as e:
            self._log(f"Error klik eye icon: {e}")
            return False

    def _find_saldo_in_screen(self) -> int:
        """Cari saldo di layar saat ini dengan 3 pass."""
        try:
            # Cek salah masuk Info Rekening
            if self._is_on_info_rekening():
                self._log("Salah masuk Informasi Rekening, back...")
                self._back_to_home_from_saldo()
                return 0

            # PASS 1: TextView
            candidates = []
            for el in self.d(className="android.widget.TextView"):
                try:
                    text = (el.get_text() or "").strip()
                    if not text:
                        continue
                    if '?' in text or '***' in text:
                        continue
                    if re.search(r'\d', text) and 'ekening' not in text:
                        candidates.append(text)
                    val = self._try_parse_saldo_from_text(text)
                    if val > 0:
                        self._log(f"Saldo (TextView): Rp {val:,}")
                        return val
                except:
                    continue

            # PASS 2: dump_hierarchy (non-TextView)
            try:
                import xml.etree.ElementTree as ET
                hierarchy_xml = self.d.dump_hierarchy()
                root = ET.fromstring(hierarchy_xml)
                for node in root.iter('node'):
                    text = (node.attrib.get('text', '') or '').strip()
                    if not text or len(text) < 4:
                        continue
                    cls = node.attrib.get('class', '')
                    if cls == 'android.widget.TextView':
                        continue
                    if '?' in text or '***' in text:
                        continue
                    val = self._try_parse_saldo_from_text(text)
                    if val > 0:
                        self._log(f"Saldo (hierarchy {cls}): Rp {val:,}")
                        return val

                # PASS 3: content-desc
                for node in root.iter('node'):
                    desc = (node.attrib.get('content-desc', '') or '').strip()
                    if not desc or len(desc) < 4:
                        continue
                    val = self._try_parse_saldo_from_text(desc)
                    if val > 0:
                        cls = node.attrib.get('class', '')
                        self._log(f"Saldo (content-desc {cls}): Rp {val:,}")
                        return val
            except Exception as e:
                self._log(f"dump_hierarchy error: {e}")

            if candidates:
                self._log(f"Kandidat saldo (gagal parse): {candidates[:8]}")
            else:
                try:
                    all_dump = []
                    for el in self.d(className="android.widget.TextView"):
                        try:
                            t = (el.get_text() or "").strip()
                            if t and len(t) > 1:
                                all_dump.append(t)
                        except:
                            pass
                    if all_dump:
                        self._log(f"DEBUG all texts: {all_dump[:15]}")
                except:
                    pass
        except:
            pass
        return 0

    def _scrape_saldo(self) -> int:
        """Scrape saldo dari beranda myBCA (dengan klik eye icon)."""
        try:
            if not self.d:
                return 0

            # Step 1: Pastikan di beranda
            try:
                beranda = self.d(text="Beranda")
                if beranda.exists:
                    beranda.click()
                    time.sleep(1.0)
            except:
                pass

            # Step 2: Cek apakah saldo sudah terlihat atau masih tersembunyi
            # Jika tersembunyi, langsung klik eye icon dulu (skip parse yg pasti gagal)
            if not self._saldo_sudah_terlihat():
                self._click_eye_icon()
                time.sleep(0.5)

            # Step 3: Parse saldo
            saldo = self._find_saldo_in_screen()
            if saldo > 0:
                self.current_saldo = saldo
                return saldo

            # Step 4: Retry sekali
            time.sleep(1.0)
            saldo = self._find_saldo_in_screen()
            if saldo > 0:
                self.current_saldo = saldo
                return saldo

            self._log("Saldo tidak terdeteksi (tidak critical)")
        except Exception as e:
            self._log(f"Scrape saldo error: {e}")
        return self.current_saldo

    def _hide_keyboard(self):
        """Sembunyikan keyboard - samain PGTOTOALLBANK."""
        try:
            self._shell("input keyevent 4")
            time.sleep(0.2)
        except Exception:
            pass

    def _finalize_amount_entry(self):
        """Finalisasi input nominal: tap Done ? di keypad + defocus - samain PGTOTOALLBANK."""
        try:
            self._shell("input tap 620 1500")  # Done ? keypad
            time.sleep(0.25)
            self._shell("input tap 360 120")   # defocus area
            time.sleep(0.25)
        except Exception:
            pass

    def _tap_lanjut_top(self) -> bool:
        """Tap tombol Lanjut atas - 1 resourceId check + fallback tap."""
        try:
            el = self.d(resourceId="com.bca.mybca.omni.android:id/2131362714")
            if el.exists:
                el.click()
                return True
        except Exception: pass
        self._shell("input tap 360 444")
        return True

    def _tap_lanjut_bottom(self) -> bool:
        """Tap tombol Lanjut bawah - 1 resourceId check + fallback tap."""
        try:
            btn = self.d(resourceId="com.bca.mybca.omni.android:id/2131362712")
            if btn.exists:
                btn.click()
                return True
        except Exception: pass
        # Fallback: tap teks "Lanjut" atau koordinat
        try:
            btn = self.d(text="Lanjut")
            if btn.exists:
                btn.click()
                return True
        except Exception: pass
        self._shell("input tap 360 1450")
        return True

    def _wait_pin_pad(self, timeout=12.0) -> bool:
        """Tunggu sampai layar PIN transaksi muncul - samain PGTOTOALLBANK."""
        end = time.time() + timeout
        while time.time() < end:
            try:
                if (self.d(textContains="PIN").exists
                    or self.d(textContains="PIN Transaksi").exists
                    or self.d(textContains="Verifikasi").exists):
                    return True
            except Exception: pass
            time.sleep(0.25)
        return False

    # -- Adaptive-wait helpers ---------------------------------------
    def _wait_submenu_after_transfer(self, timeout=4.0) -> bool:
        """Poll sampai submenu Transfer muncul - lightweight .exists."""
        end = time.time() + timeout
        while time.time() < end:
            try:
                if self.d(textContains="Rekening BCA").exists or self.d(textContains="Bank Lain").exists:
                    return True
            except Exception: pass
            time.sleep(0.2)
        return False

    def _wait_after_lanjut_interbank(self, timeout=8.0) -> str:
        """Poll setelah Lanjut di flow interbank - lightweight .exists per cycle.
        Return: 'form' | 'layanan' | 'error' | 'timeout'
        """
        end = time.time() + timeout
        while time.time() < end:
            try:
                # Most common: form with Nominal field
                if self.d(textContains="Nominal").exists:
                    return "form"
                # Service selection (BI FAST / Real Time)
                if self.d(textContains="BI FAST").exists or self.d(textContains="Real Time").exists:
                    return "layanan"
                # Error popup
                if self.d(textContains="Oops").exists or self.d(textContains="tidak valid").exists:
                    return "error"
            except Exception: pass
            time.sleep(0.15)
        return "timeout"

    def _wait_nama_screen(self, timeout=12.0) -> str:
        """Poll setelah Lanjut rekening - tunggu layar Nama/Nominal muncul.
        Return: 'ok' | 'error' | 'timeout'
        """
        end = time.time() + timeout
        while time.time() < end:
            try:
                if self.d(textContains="Nominal").exists or self.d(textContains="Nama Penerima").exists:
                    return "ok"
                if self.d(textContains="Oops").exists or self.d(textContains="tidak valid").exists:
                    return "error"
            except Exception: pass
            time.sleep(0.25)
        return "timeout"

    def _wait_konfirmasi_bca(self, timeout=8.0) -> str:
        """Poll setelah Lanjut nominal - tunggu layar Konfirmasi/PIN muncul.
        Return: 'konfirmasi' | 'pin' | 'error' | 'timeout'
        """
        end = time.time() + timeout
        while time.time() < end:
            try:
                if self.d(textContains="Konfirmasi").exists:
                    return "konfirmasi"
                if self.d(textContains="Detail").exists:
                    return "konfirmasi"
                if self.d(textContains="PIN").exists:
                    return "pin"
                if self.d(textContains="Oops").exists or self.d(textContains="tidak valid").exists:
                    return "error"
            except Exception: pass
            time.sleep(0.3)
        return "timeout"
    # -- End adaptive-wait helpers -----------------------------------

    def _input_trx_pin(self) -> bool:
        """Input PIN transaksi - samakan dengan PGTOTOALLBANK: batch + 0.3s delay."""
        keypad = self.KEYPAD
        pin_str = str(self.pin or "").strip()
        if len(pin_str) != 6 or not pin_str.isdigit():
            self._log(f"PIN harus 6 digit, got '{pin_str}'")
            return False
        
        # Tunggu keypad fully interactive sebelum tap pertama
        time.sleep(0.5)
        
        # Batch mode: single ADB call, sleep 0.3 between ALL taps (same as PGTOTOALLBANK)
        try:
            cmds = []
            for ch in pin_str:
                if ch in keypad:
                    x, y = keypad[ch]
                    cmds.append(f"input tap {x} {y}")
            if cmds:
                batch_cmd = " && sleep 0.3 && ".join(cmds)
                subprocess.check_output(
                    ["adb", "-s", self.device_id, "shell", batch_cmd],
                    timeout=15, creationflags=SUBPROCESS_FLAGS
                )
                self._log("PIN: batch OK")
                time.sleep(0.3)
                return True
        except Exception as e:
            self._log(f"PIN batch failed: {e}, fallback sequential...")
        
        # Fallback: sequential, 0.3s per digit
        for ch in pin_str:
            if ch in keypad:
                x, y = keypad[ch]
                self._adb("input", "tap", str(x), str(y))
                time.sleep(0.3)
        time.sleep(0.3)
        return True

    def _handle_popup_error(self) -> bool:
        """Handle popup error (Oops, tidak dapat digunakan, dll)"""
        try:
            # Poket Rupiah / tidak dapat digunakan
            if self.d(textContains="tidak dapat digunakan").exists:
                self._log("Popup: tidak dapat digunakan")
                ok = self.d(text="OK")
                if ok.exists(timeout=0.5): ok.click()
                time.sleep(0.5)
                return True
            # Oops
            if self.d(textContains="Oops").exists:
                self._log("Popup: Oops")
                ok = self.d(text="OK")
                if ok.exists(timeout=0.5): ok.click()
                time.sleep(0.5)
                return True
        except Exception: pass
        return False

    def _check_saldo_tidak_cukup(self) -> bool:
        try:
            if self.d(textContains="Saldo tidak cukup").exists:
                self._log("SALDO TIDAK CUKUP!")
                ok = self.d(text="OK")
                if ok.exists(timeout=0.5): ok.click()
                time.sleep(0.5)
                self._back_to_home()
                return True
        except Exception: pass
        return False

    def _goto_transfer(self):
        try:
            el = self.d(text="Transfer")
            if el.exists(timeout=5): el.click(); self._wait_submenu_after_transfer(timeout=4.0); return True
        except Exception: pass
        self._log("Menu Transfer tidak ditemukan!")
        return False

    def _goto_rekening_bca(self) -> bool:
        try:
            if not self._goto_transfer(): return False

            # Klik Rekening BCA
            el = self.d(text="Rekening BCA")
            if not el.exists: el = self.d(textContains="Rekening BCA")
            if not el.exists:
                self._log("Menu Rekening BCA tidak ditemukan"); return False
            el.click()
            # Poll sampai submenu muncul (.exists, no dump_hierarchy)
            for _ in range(15):
                if self.d(textContains="Transfer ke tujuan baru").exists or self.d(textContains="Rekening Tujuan").exists:
                    break
                time.sleep(0.4)

            # Klik Transfer ke tujuan baru
            el2 = self.d(textContains="Transfer ke tujuan baru")
            if el2.exists:
                el2.click()
                time.sleep(0.5)
                for _ in range(20):
                    if self.d(textContains="Rekening Tujuan").exists or self.d(textContains="No. Rekening Tujuan").exists:
                        return True
                    if self.d(className="android.widget.EditText").exists and self.d(textContains="Lanjut").exists:
                        return True
                    time.sleep(0.25)
            return self.d(textContains="Rekening Tujuan").exists
        except Exception as e:
            self._log(f"goto_rek_bca: {e}"); return False

    def _goto_bank_lain(self) -> bool:
        try:
            if not self._goto_transfer(): return False

            el = self.d(text="Bank Lain")
            if not el.exists: el = self.d(textContains="Bank Lain")
            if not el.exists:
                self._log("Menu Bank Lain tidak ditemukan"); return False
            el.click()
            # Poll sampai submenu (.exists, no dump_hierarchy)
            for _ in range(15):
                if self.d(textContains="Transfer ke tujuan baru").exists or self.d(textContains="Cari Bank").exists:
                    break
                time.sleep(0.4)

            el2 = self.d(textContains="Transfer ke tujuan baru")
            if el2.exists:
                el2.click()
                time.sleep(0.5)
                for _ in range(15):
                    if self.d(textContains="Rekening Tujuan").exists or self.d(textContains="Cari Bank").exists:
                        return True
                    time.sleep(0.4)
            return self.d(textContains="Rekening Tujuan").exists
        except Exception as e:
            self._log(f"goto_bank_lain: {e}"); return False

    def _select_dest_bank(self, name: str) -> bool:
        try:
            s = self.d(textContains="Cari Bank")
            if not s.exists: s = self.d(className="android.widget.EditText")
            if s.exists:
                s.click(); time.sleep(0.3); self._input_text(name)
                # Poll sampai search result muncul (.exists)
                for _ in range(10):
                    if self.d(textContains=name.upper()).exists:
                        break
                    time.sleep(0.4)
            r = self.d(textContains=name.upper())
            if r.exists:
                r.click()
                # Poll sampai pindah layar (.exists)
                for _ in range(15):
                    if self.d(textContains="Rekening Tujuan").exists or self.d(textContains="Nominal").exists:
                        return True
                    time.sleep(0.4)
                return True
            return False
        except Exception as e: self._log(f"select_bank: {e}"); return False

    def _fill_rekening_bca(self, no_rek: str) -> bool:
        """Sesama BCA: isi rekening tujuan, klik Lanjut - samain PGTOTOALLBANK."""
        self._log(f"Isi rekening: {no_rek}")

        # 1) Tunggu field rekening muncul (max 6s, adaptif internet lambat)
        try:
            found = False
            end_t = time.time() + 6.0
            while time.time() < end_t:
                el = self.d(resourceId="com.bca.mybca.omni.android:id/2131366100")
                if not el.exists:
                    el = self.d(resourceId="com.bca.mybca.omni.android:id/2131365075")
                if not el.exists:
                    el = self.d(textContains="Rekening Tujuan")
                if not el.exists:
                    el = self.d(textContains="No. Rekening Tujuan")
                if el.exists:
                    el.click(); time.sleep(0.3); found = True; break
                time.sleep(0.4)
            if not found:
                self._shell("input tap 360 400")  # fallback
                time.sleep(0.3)
        except Exception as e:
            self._log(f"Error klik field rekening: {e}")
            return False

        # 2) Pastikan fokus ke EditText
        try:
            edt = self.d(className="android.widget.EditText")
            if edt.exists:
                edt.click(); time.sleep(0.15)
        except Exception: pass

        # 3) Input rekening (set_text, fallback DEL+ADB)
        try:
            edt = self.d(className="android.widget.EditText")
            if edt.exists:
                try:
                    edt.set_text(no_rek)
                except Exception:
                    edt.click(); time.sleep(0.15)
                    for _ in range(25):
                        self._shell("input keyevent KEYCODE_DEL")
                    self._input_text(no_rek)
            else:
                self._input_text(no_rek)
            time.sleep(0.6)
        except Exception as e:
            self._log(f"Error input rekening: {e}")
            return False

        # 4) Klik Lanjut
        try:
            lanjut = self.d(resourceId="com.bca.mybca.omni.android:id/2131362714")
            if not lanjut.exists:
                lanjut = self.d(resourceId="com.bca.mybca.omni.android:id/2131362331")
            if not lanjut.exists:
                lanjut = self.d(text="Lanjut")
            if lanjut.exists:
                lanjut.click(); time.sleep(0.5)
            else:
                self._shell("input tap 360 580")  # fallback
                time.sleep(0.5)
        except Exception as e:
            self._log(f"Error klik Lanjut: {e}")
            return False

        # 5) Cek popup error
        if self._handle_popup_error():
            return False

        # 6) Tunggu layar pindah (max 5s) - samain PGTOTOALLBANK
        for _ in range(20):
            if self.d(textContains="Nominal").exists or self.d(textContains="Nama").exists:
                return True
            time.sleep(0.25)

        self._log("Timeout tunggu Nama Penerima")
        return False

    def _fill_rekening_interbank(self, no_rek: str) -> bool:
        """Antar bank: isi rekening tujuan, klik Lanjut - samain PGTOTOALLBANK."""
        self._log(f"Isi rekening: {no_rek}")

        # 1) Tunggu field rekening muncul (max 6s)
        try:
            found = False
            end_t = time.time() + 6.0
            while time.time() < end_t:
                el = self.d(resourceId="com.bca.mybca.omni.android:id/2131366100")
                if not el.exists:
                    el = self.d(resourceId="com.bca.mybca.omni.android:id/2131365075")
                if not el.exists:
                    el = self.d(textContains="Rekening Tujuan")
                if not el.exists:
                    el = self.d(textContains="No. Rekening Tujuan")
                if el.exists:
                    el.click(); time.sleep(0.3); found = True; break
                time.sleep(0.4)
            if not found:
                self._shell("input tap 360 400")
                time.sleep(0.3)
        except Exception as e:
            self._log(f"Error klik field rekening: {e}")
            return False

        # 2) Pastikan fokus ke EditText
        try:
            edt = self.d(className="android.widget.EditText")
            if edt.exists:
                edt.click(); time.sleep(0.15)
        except Exception: pass

        # 3) Input rekening
        try:
            edt = self.d(className="android.widget.EditText")
            if edt.exists:
                try:
                    edt.set_text(no_rek)
                except Exception:
                    edt.click(); time.sleep(0.15)
                    for _ in range(25):
                        self._shell("input keyevent KEYCODE_DEL")
                    self._input_text(no_rek)
            else:
                self._input_text(no_rek)
            time.sleep(0.6)
        except Exception as e:
            self._log(f"Error input rekening: {e}")
            return False

        # 4) Klik Lanjut
        try:
            lanjut = self.d(resourceId="com.bca.mybca.omni.android:id/2131362714")
            if not lanjut.exists:
                lanjut = self.d(resourceId="com.bca.mybca.omni.android:id/2131362331")
            if not lanjut.exists:
                lanjut = self.d(text="Lanjut")
            if lanjut.exists:
                lanjut.click(); time.sleep(0.5)
            else:
                self._shell("input tap 360 580")
                time.sleep(0.5)
        except Exception as e:
            self._log(f"Error klik Lanjut: {e}")
            return False

        # 5) Cek popup error
        if self._handle_popup_error():
            return False

        # 6) Tunggu layar pindah (max 5s)
        for _ in range(20):
            if self.d(textContains="Nominal").exists or self.d(textContains="Nama").exists:
                return True
            time.sleep(0.25)

        self._log("Timeout tunggu form transfer")
        return False

    def _scrape_nama_penerima(self) -> str:
        """Scrape nama penerima - single dump, no retry (cosmetic only)."""
        try:
            xml = self.d.dump_hierarchy()
            texts = re.findall(r'text="([^"]+)"', xml)
            texts = [t.strip() for t in texts if t.strip()]

            blacklist_upper = {
                "NAMA PENERIMA", "NOMINAL", "CATATAN", "LANJUT", "REKENING TUJUAN",
                "TRANSFER KE REKENING BCA", "TRANSFER KE BANK LAIN",
                "REKENING", "RP", "IDR", "PILIH", "CARI", "TUJUAN", "BATAL",
                "KEMBALI", "TRANSFER", "BERANDA", "AKTIVITAS", "UNTUKMU",
                "AKUN SAYA", "MENU UTAMA", "ATUR", "BAYAR & ISI ULANG",
                "BANK LAIN", "REKENING BCA", "BCA ID", "SALDO AKTIF",
            }

            # Cari teks setelah "Nama Penerima"
            for i, t in enumerate(texts):
                if "Penerima" in t or "PENERIMA" in t:
                    for j in range(i+1, min(i+5, len(texts))):
                        cand = texts[j].strip()
                        if cand and len(cand) > 2 and cand.upper() not in blacklist_upper:
                            if all(c.isalpha() or c in ' .,-\'' for c in cand):
                                return cand
                    break

            # Fallback: cari nama-like text
            for t in texts:
                if t.upper() in blacklist_upper: continue
                if 3 <= len(t) <= 50 and all(c.isalpha() or c in ' .,-\'' for c in t):
                    if any(c.isdigit() for c in t): continue
                    return t
        except Exception: pass
        return ""

    def _fill_nominal_and_pin_bca(self, nominal: int) -> bool:
        """Sesama BCA: isi nominal, 2x Lanjut, input PIN - samain PGTOTOALLBANK."""
        self._log(f"Isi nominal: Rp {nominal:,}")

        # isi nominal - samain PGTOTOALLBANK
        try:
            el = self.d(resourceId="com.bca.mybca.omni.android:id/2131366105")
            if not el.exists:
                el = self.d(resourceId="com.bca.mybca.omni.android:id/2131365080")
            if not el.exists:
                el = self.d(textContains="Nominal")
            if el.exists:
                el.click()
                time.sleep(0.3)
                self._input_text(str(nominal))
                time.sleep(0.3)
                self._finalize_amount_entry()
            else:
                self._log("Field Nominal tidak ditemukan")
                return False
        except Exception as e:
            self._log(f"Gagal isi nominal: {e}")
            return False

        # Lanjut #1 (setelah nominal)
        try:
            lanjut1 = self.d(resourceId="com.bca.mybca.omni.android:id/2131365886")
            if not lanjut1.exists:
                lanjut1 = self.d(text="Lanjut")
            if lanjut1.exists:
                lanjut1.click()
            else:
                self._shell("input tap 360 1200")
        except Exception: pass

        # Tunggu konfirmasi - samain PGTOTOALLBANK
        state = self._wait_konfirmasi_bca(timeout=8.0)
        if state == "error":
            self._handle_popup_error()
            self._check_saldo_tidak_cukup()
            return False
        if state == "pin":
            self._log("Input PIN...")
            self._input_trx_pin()
            return True

        # Lanjut #2 (konfirmasi ? PIN)
        try:
            lanjut2 = self.d(resourceId="com.bca.mybca.omni.android:id/2131362411")
            if not lanjut2.exists:
                lanjut2 = self.d(text="Lanjut")
            if lanjut2.exists:
                lanjut2.click()
            else:
                self._shell("input tap 360 1420")
        except Exception: pass
        time.sleep(0.3)

        # Tunggu PIN - samain PGTOTOALLBANK
        if self._wait_pin_pad(timeout=12.0):
            self._log("Input PIN...")
            self._input_trx_pin()
            return True

        if self._check_saldo_tidak_cukup(): return False
        self._log("Layar PIN tidak muncul!")
        return False

    def _fill_nominal_and_pin_interbank(self, nominal: int) -> bool:
        """Antar bank: isi nominal, pilih BI-FAST, 2x Lanjut, input PIN - samain PGTOTOALLBANK."""
        self._log(f"Isi nominal: Rp {nominal:,}")

        # isi nominal - samain PGTOTOALLBANK
        try:
            el = self.d(resourceId="com.bca.mybca.omni.android:id/2131366105")
            if not el.exists:
                el = self.d(resourceId="com.bca.mybca.omni.android:id/2131365080")
            if not el.exists:
                el = self.d(textContains="Nominal")
            if el.exists:
                el.click()
                time.sleep(0.3)
                self._input_text(str(nominal))
                time.sleep(0.3)
                self._finalize_amount_entry()
            else:
                self._log("Field Nominal tidak ditemukan")
                return False
        except Exception as e:
            self._log(f"Gagal isi nominal: {e}")
            return False

        # -- Buka Layanan Transfer + Pilih BI FAST --
        try:
            opened = False
            for attempt in range(3):
                lt = self.d(resourceId="com.bca.mybca.omni.android:id/2131366231")
                if not lt.exists:
                    lt = self.d(resourceId="com.bca.mybca.omni.android:id/2131365206")
                if not lt.exists:
                    lt = self.d(textContains="Layanan Transfer")
                if lt.exists:
                    lt.click()
                    time.sleep(0.5)
                    if self.d(textContains="BI FAST").exists or self.d(textContains="Pilih Layanan").exists:
                        opened = True
                        break
                time.sleep(0.35)
            if not opened:
                self._log("Sheet Layanan Transfer gagal buka")
        except Exception: pass

        # Pilih BI FAST
        bf_selected = False
        try:
            for _ in range(4):
                bf = self.d(textContains="BI FAST")
                if bf.exists:
                    bf.click(); time.sleep(0.3)
                    bf_selected = True
                    break
                time.sleep(0.3)
        except Exception: pass

        if not bf_selected:
            # Fallback: Real Time / Online
            for rt_txt in ["Realtime Online", "Real Time", "Online"]:
                try:
                    rt = self.d(textContains=rt_txt)
                    if rt.exists:
                        rt.click(); time.sleep(0.3)
                        break
                except Exception: continue

        # Lanjut (setelah layanan transfer)
        try:
            lanjut = self.d(resourceId="com.bca.mybca.omni.android:id/2131365886")
            if not lanjut.exists:
                lanjut = self.d(text="Lanjut")
            if lanjut.exists:
                lanjut.click()
            else:
                self._shell("input tap 360 1200")
        except Exception: pass

        # Tunggu konfirmasi/PIN
        state = self._wait_konfirmasi_bca(timeout=8.0)
        if state == "error":
            # BI FAST error ? cek & fallback Realtime Online
            bifast_err = False
            for err_txt in ["pilih layanan", "gunakan layanan", "tidak valid", "pemeliharaan"]:
                if self.d(textContains=err_txt).exists:
                    bifast_err = True
                    break
            if bifast_err:
                try:
                    ok_btn = self.d(text="OK")
                    if ok_btn.exists: ok_btn.click(); time.sleep(0.5)
                except Exception: pass
                self._log("BI FAST rejected ? fallback Realtime Online")
                for rt_txt in ["Realtime Online", "Real Time", "Online"]:
                    try:
                        rt = self.d(textContains=rt_txt)
                        if rt.exists: rt.click(); time.sleep(0.3); break
                    except Exception: continue
                # Re-tap Lanjut
                try:
                    lanjut = self.d(text="Lanjut")
                    if lanjut.exists: lanjut.click()
                    else: self._shell("input tap 360 1200")
                except Exception: pass
                state = self._wait_konfirmasi_bca(timeout=8.0)
            else:
                self._handle_popup_error()
                self._check_saldo_tidak_cukup()
                return False

        if state == "pin":
            self._log("Input PIN...")
            self._input_trx_pin()
            return True

        # Lanjut konfirmasi ? PIN
        try:
            lanjut2 = self.d(resourceId="com.bca.mybca.omni.android:id/2131362411")
            if not lanjut2.exists:
                lanjut2 = self.d(text="Lanjut")
            if lanjut2.exists:
                lanjut2.click()
            else:
                self._shell("input tap 360 1420")
        except Exception: pass
        time.sleep(0.3)

        if self._wait_pin_pad(timeout=12.0):
            self._log("Input PIN...")
            self._input_trx_pin()
            return True

        if self._check_saldo_tidak_cukup(): return False
        self._log("Layar PIN tidak muncul!")
        return False

    def _check_result(self, timeout_s=60) -> Tuple[str, str]:
        """Cek hasil transfer: (status, screenshot_path)"""
        end_time = time.time() + timeout_s
        while time.time() < end_time:
            try:
                # SUKSES
                if self.d(textContains="Transfer Berhasil").exists or \
                   self.d(textContains="Transaksi Berhasil").exists:
                    self._log("Transfer BERHASIL!")
                    ss = ""
                    try:
                        self._log("Saving screenshot...")
                        ss = save_screenshot(self.d, "SUKSES", self.bank_name)
                        self._log(f"Screenshot saved: {ss}")
                    except Exception as e:
                        self._log(f"Screenshot error: {e}")
                    try:
                        self._log("Klik Selesai...")
                        selesai = self.d(text="Selesai")
                        if selesai.exists(timeout=1):
                            selesai.click()
                            self._log("Selesai clicked")
                        else:
                            self._tap(360, 1466)
                            self._log("Selesai fallback tap")
                    except Exception as e:
                        self._log(f"Selesai error: {e}")
                    time.sleep(0.5)
                    self._log("Return SUKSES")
                    return ("SUKSES", ss)

                # GAGAL
                if self.d(textContains="Transfer Gagal").exists:
                    self._log("Transfer GAGAL!")
                    ss_fail = ""
                    try:
                        ss_fail = save_screenshot(self.d, "GAGAL", self.bank_name)
                        self._log(f"Screenshot GAGAL: {ss_fail}")
                    except Exception: pass
                    try:
                        selesai = self.d(text="Selesai")
                        if selesai.exists(timeout=1): selesai.click()
                    except Exception: pass
                    return ("GAGAL", ss_fail)

                # SALDO TIDAK CUKUP
                if self.d(textContains="Saldo tidak cukup").exists:
                    self._log("SALDO TIDAK CUKUP!")
                    ss_saldo = ""
                    try:
                        ss_saldo = save_screenshot(self.d, "SALDO_HABIS", self.bank_name)
                    except Exception: pass
                    has_ok = self.d(text="OK").exists
                    has_selesai = self.d(text="Selesai").exists
                    if has_ok and not has_selesai:
                        try: self.d(text="OK").click()
                        except Exception: pass
                        self._back_to_home()
                    return ("SALDO_HABIS", ss_saldo)

            except Exception: pass
            time.sleep(0.6)

        self._log("Timeout cek hasil")
        return ("GAGAL", "")

    def _back_to_home(self):
        """Kembali ke beranda dengan smart navigation."""
        for attempt in range(8):
            # Check if already at home
            if self._is_at_home():
                self._log("Sudah di beranda.")
                return
            
            # Check for exit confirmation popup and dismiss it
            try:
                if self.d(textContains="yakin ingin keluar").exists:
                    tidak_btn = self.d(text="Tidak")
                    if tidak_btn.exists:
                        tidak_btn.click()
                        self._log("Popup keluar - klik Tidak")
                        time.sleep(0.5)
                        continue
            except Exception:
                pass
            
            # Check for other popups with OK/Tutup
            try:
                for btn_text in ["OK", "Tutup", "TUTUP", "Kembali"]:
                    btn = self.d(text=btn_text)
                    if btn.exists:
                        btn.click()
                        time.sleep(0.3)
                        break
            except Exception:
                pass
            
            # Try clicking Beranda tab
            try:
                beranda = self.d(text="Beranda")
                if beranda.exists:
                    beranda.click()
                    time.sleep(0.5)
                    if self._is_at_home():
                        return
            except Exception:
                pass
            
            # Press back
            self._adb("input", "keyevent", "KEYCODE_BACK")
            time.sleep(0.4)
        
        self._log("Back to home selesai")

    def _verify_nama_penerima(self, expected: str, actual: str) -> bool:
        """
        Verifikasi apakah nama penerima dari bank cocok dengan request.
        Return True jika cocok (boleh lanjut transfer), False jika tidak cocok.
        """
        if not actual:
            # Tidak bisa scrape nama - skip verifikasi
            return True
        
        # Normalize
        exp = expected.upper().strip()
        act = actual.upper().strip()
        
        # Exact match
        if exp == act:
            return True
        
        # Partial match - salah satu mengandung yang lain
        if exp in act or act in exp:
            return True
        
        # First word match (nama depan)
        exp_words = exp.split()
        act_words = act.split()
        if exp_words and act_words and exp_words[0] == act_words[0]:
            return True
        
        # Check significant word overlap (minimal 2 kata sama)
        common_words = set(exp_words) & set(act_words)
        if len(common_words) >= 2:
            return True
        
        # Completely different names
        return False

    def _determine_biaya(self, jenis_bank: str) -> int:
        if jenis_bank.upper() == "BCA": return 0
        return 2500

    def _do_transfer(self, req: SuntikanRequest) -> Tuple[str, str, int]:
        rid = req.request_id
        bank = req.jenis_bank.upper()
        is_bca = bank == "BCA"
        self._log(f"[{rid}] Transfer: {req.nama_bank} Rp {req.nominal:,} ({bank})")
        self.ui_q.put(("update_bank", (self.device_id, "status", "Transferring...")))

        if not self._ensure_logged_in():
            return ("GAGAL", "", 0)

        if is_bca:
            # ===== FLOW SESAMA BCA =====
            if not self._goto_rekening_bca():
                self._back_to_home(); return ("GAGAL", "", 0)
            if not self._fill_rekening_bca(req.no_rek):
                self._back_to_home(); return ("GAGAL", "", 0)
            nama = self._scrape_nama_penerima()
            if nama: self._log(f"[{rid}] Penerima: {nama}")
            # Verifikasi nama penerima
            if nama and not self._verify_nama_penerima(req.nama_bank, nama):
                self._log(f"[{rid}] ? NAMA TIDAK COCOK! Expected: {req.nama_bank}, Got: {nama}")
                self._back_to_home()
                self.ui_q.put(("update_bank", (self.device_id, "status", "Ready")))
                return ("NAMA_SALAH", "", 0)
            if not self._fill_nominal_and_pin_bca(req.nominal):
                if self._check_saldo_tidak_cukup():
                    self.ui_q.put(("update_bank", (self.device_id, "status", "Ready")))
                    return ("SALDO_HABIS", "", 0)
                self._back_to_home(); return ("GAGAL", "", 0)
        else:
            # ===== FLOW ANTAR BANK =====
            if not self._goto_bank_lain():
                self._back_to_home(); return ("GAGAL", "", 0)
            if not self._select_dest_bank(bank):
                self._back_to_home(); return ("GAGAL", "", 0)
            if not self._fill_rekening_interbank(req.no_rek):
                self._back_to_home(); return ("GAGAL", "", 0)
            nama = self._scrape_nama_penerima()
            if nama: self._log(f"[{rid}] Penerima: {nama}")
            # Verifikasi nama penerima
            if nama and not self._verify_nama_penerima(req.nama_bank, nama):
                self._log(f"[{rid}] ? NAMA TIDAK COCOK! Expected: {req.nama_bank}, Got: {nama}")
                self._back_to_home()
                self.ui_q.put(("update_bank", (self.device_id, "status", "Ready")))
                return ("NAMA_SALAH", "", 0)
            if not self._fill_nominal_and_pin_interbank(req.nominal):
                if self._check_saldo_tidak_cukup():
                    self.ui_q.put(("update_bank", (self.device_id, "status", "Ready")))
                    return ("SALDO_HABIS", "", 0)
                self._back_to_home(); return ("GAGAL", "", 0)

        # Cek hasil
        status, ss = self._check_result()
        biaya = self._determine_biaya(bank) if status == "SUKSES" else 0
        self.ui_q.put(("update_bank", (self.device_id, "status", "Ready")))
        return (status, ss, biaya)

    def run(self):
        self._log("Worker started")
        self._done = _load_success()
        if not self._connect(): self._log("Device N/A"); return
        self._force_stop_mybca(); time.sleep(0.5)
        self._wake_and_start(); time.sleep(1.5)
        if self._ensure_logged_in():
            self.ui_q.put(("update_bank", (self.device_id, "status", "Ready")))
            self._log("Ready"); time.sleep(1)
            self._scrape_saldo()
            if self.current_saldo > 0:
                self._log(f"Saldo: Rp {self.current_saldo:,}")
                self.ui_q.put(("update_bank", (self.device_id, "saldo", f"Rp {self.current_saldo:,}")))
            self._ready = True
            # Notify app: worker ready, bisa terima job pending
            self.ui_q.put(("worker_ready", self.device_id))
        else:
            self._ready = False
            self._log("Login gagal, lanjut...")

        while not self._stop.is_set():
            # -- Periodic health check (every ~10s while idle) --
            got_job = False
            for _ in range(10):  # 10 x 1s = 10s health check interval
                if self._stop.is_set():
                    break
                try:
                    req = self.job_q.get(timeout=1.0)
                    got_job = True
                    break
                except queue.Empty:
                    continue

            if self._stop.is_set():
                break

            if not got_job:
                # No job for 10s, check device health
                if not self._is_device_alive():
                    self._log("Device disconnected!")
                    self._ready = False
                    self.ui_q.put(("update_bank", (self.device_id, "status", "Disconnected")))
                    self.ui_q.put(("update_bank", (self.device_id, "saldo", "-")))
                    self.current_saldo = 0
                    # ===== FIX: Drain stale requests dari queue dan requeue =====
                    # Supaya tidak diproses ulang saat reconnect nanti
                    while not self.job_q.empty():
                        try:
                            stale_req = self.job_q.get_nowait()
                            self._log(f"[{stale_req.request_id}] Drain stale request dari disconnected worker")
                            self.ui_q.put(("update_request", (stale_req.request_id, "Pending", "")))
                            self.ui_q.put(("requeue", stale_req))
                        except queue.Empty:
                            break
                    # Wait until device reconnects
                    while not self._stop.is_set():
                        time.sleep(3)
                        if self._is_device_alive():
                            self._log("Device reconnected!")
                            self.ui_q.put(("update_bank", (self.device_id, "status", "Reconnecting...")))
                            if self._connect():
                                self._force_stop_mybca(); time.sleep(0.5)
                                self._wake_and_start(); time.sleep(1.5)
                                if self._ensure_logged_in():
                                    self._scrape_saldo()
                                    if self.current_saldo > 0:
                                        self._log(f"Saldo: Rp {self.current_saldo:,}")
                                        self.ui_q.put(("update_bank", (self.device_id, "saldo", f"Rp {self.current_saldo:,}")))
                                    self._ready = True
                                    self.ui_q.put(("worker_ready", self.device_id))
                                else:
                                    self._ready = False
                                    self._log("Login gagal setelah reconnect")
                            break
                continue

            # -- Process job --
            rid = req.request_id
            # ===== FIX: Reload global success set untuk cek apakah worker lain sudah selesaikan =====
            self._done = _load_success()
            if rid in self._done or rid in self._inflight:
                self._log(f"[{rid}] Sudah selesai/inflight, skip")
                continue
            # ===== FIX: Cek status request (bisa berubah via shared object) =====
            if req.status in ("Sukses", "Skipped - Done", "Gagal"):
                self._log(f"[{rid}] Request sudah selesai (status={req.status}), skip")
                continue

            # Check device before transfer
            if not self._is_device_alive():
                self._log(f"[{rid}] Device disconnected, requeue")
                self.ui_q.put(("update_bank", (self.device_id, "status", "Disconnected")))
                self.ui_q.put(("update_request", (rid, "Pending", "")))
                self.ui_q.put(("requeue", req))
                continue

            self._inflight.add(rid)

            # ===== CEK SALDO DULU sebelum claim =====
            # Jangan claim (klik PROSES) kalau saldo tidak cukup
            if self.current_saldo > 0 and self.current_saldo < req.nominal:
                self._log(f"[{rid}] Saldo tidak cukup! Butuh Rp {req.nominal:,} tapi saldo Rp {self.current_saldo:,}. Requeue...")
                self._inflight.discard(rid)
                self.ui_q.put(("update_request", (rid, "Pending", "")))
                self.ui_q.put(("requeue", req))
                continue

            # ===== CLAIM REQUEST: Klik PROSES dulu sebelum transfer =====
            # Ini mencegah double processing jika ada 2 user running
            claimer_id = f"{self.bank_name}_{self.device_id}_{os.getpid()}"
            if self.app and hasattr(self.app, 'tg_worker') and self.app.tg_worker:
                self.ui_q.put(("update_request", (rid, "Claiming...", self.bank_name)))
                claimed = self.app.tg_worker.claim_request(req, claimer_id=claimer_id)
                if not claimed:
                    self._log(f"[{rid}] SKIP - Request sudah selesai/diklaim user lain")
                    self._inflight.discard(rid)
                    self.ui_q.put(("update_request", (rid, "Skipped - Done", "")))
                    continue
                self._log(f"[{rid}] Request claimed! Lanjut transfer...")
            else:
                self._log(f"[{rid}] TG worker not ready, coba claim via file saja...")
                # Tanpa TG, tetap coba claim di shared file
                if not _try_claim_file(rid, claimer_id):
                    self._log(f"[{rid}] SKIP - Sudah diklaim instance lain (file)")
                    self._inflight.discard(rid)
                    self.ui_q.put(("update_request", (rid, "Skipped - Done", "")))
                    continue

            # ===== FINAL GUARD: Cek ulang sebelum transfer =====
            self._done = _load_success()
            if rid in self._done:
                self._log(f"[{rid}] SKIP - Sudah ada di success file (final guard)")
                self._inflight.discard(rid)
                self.ui_q.put(("update_request", (rid, "Skipped - Done", "")))
                continue
            if _is_claimed_by_other(rid, claimer_id):
                self._log(f"[{rid}] SKIP - Diklaim instance lain (final guard)")
                self._inflight.discard(rid)
                self.ui_q.put(("update_request", (rid, "Skipped - Done", "")))
                continue
            
            self.ui_q.put(("update_request", (rid, "On Progress", self.bank_name)))
            try:
                self._log(f"[{rid}] Calling _do_transfer...")
                status, ss, biaya = self._do_transfer(req)
                self._log(f"[{rid}] _do_transfer returned: status={status}, ss={ss}, biaya={biaya}")
                if status == "SUKSES":
                    _save_success(rid); self._done.add(rid)
                    req.status = "Sukses"; req.screenshot_path = ss
                    req.bank_used = self.bank_name; req.bank_device = self.device_id
                    req.biaya_bank = biaya
                    self.current_saldo = max(0, self.current_saldo - req.nominal)
                    self.ui_q.put(("update_bank", (self.device_id, "saldo", f"Rp {self.current_saldo:,}")))
                    self.ui_q.put(("update_request", (rid, "Sukses", self.bank_name)))
                    self.ui_q.put(("transfer_done", req))
                    self._log(f"[{rid}] SUKSES! Sisa: Rp {self.current_saldo:,}")
                elif status == "SALDO_HABIS":
                    req.status = "Gagal - Saldo"
                    self.ui_q.put(("update_request", (rid, "Gagal - Saldo", self.bank_name)))
                    self.ui_q.put(("requeue", req))
                elif status == "NAMA_SALAH":
                    req.status = "Gagal - Nama Salah"
                    self.ui_q.put(("update_request", (rid, "Gagal - Nama Salah", self.bank_name)))
                    self.ui_q.put(("transfer_failed", req))
                    self._log(f"[{rid}] DIBATALKAN - Nama penerima tidak cocok dengan request!")
                else:
                    self._done.add(rid); req.status = "Gagal"
                    self.ui_q.put(("update_request", (rid, "Gagal", self.bank_name)))
                    self.ui_q.put(("transfer_failed", req))
            except Exception as e:
                self._log(f"[{rid}] ERROR: {e}")
                self.ui_q.put(("update_request", (rid, "Gagal", self.bank_name)))
            finally:
                self._inflight.discard(rid)
                # Notify app: worker idle, bisa dispatch pending requests
                self.ui_q.put(("worker_idle", self.device_id))
        self._log("Worker stopped")


# ======================================================================
# TELETHON USER SESSION WORKER
# ======================================================================
class TelethonWorker(threading.Thread):
    """
    Login sebagai USER Telegram (bukan bot).
    - Monitor grup untuk pesan KONFIRMASI SUNTIK DANA + tombol PROSES
    - Setelah transfer sukses: klik PROSES, pilih bank, kirim biaya, screenshot
    """

    def __init__(self, ui_q: queue.Queue, cfg: dict):
        super().__init__(daemon=True)
        self.ui_q = ui_q
        self.cfg = cfg
        self._stop = threading.Event()
        self.client: Optional[TelegramClient] = None
        self._loop = None
        self._login_event = threading.Event()
        self._otp_queue: queue.Queue = queue.Queue()
        self._2fa_queue: queue.Queue = queue.Queue()
        self._qr_cancel = threading.Event()  # signal to cancel QR and fall back to phone
        self._logged_in = False
        self._my_username = ""  # Username Telegram kita (untuk verifikasi klaim)
        self.me = None  # Current user info
        self._processed_msg_ids: set = set()  # Track processed msg IDs to prevent duplicates
        self._processed_msg_lock = threading.Lock()  # Thread-safe access

    def stop(self):
        self._stop.set()
        if self.client and self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self.client.disconnect(), self._loop)

    def submit_otp(self, code: str):
        self._otp_queue.put(code)

    def submit_2fa(self, password: str):
        self._2fa_queue.put(password)

    def cancel_qr_login(self):
        """Signal to skip QR login and fall back to phone OTP."""
        self._qr_cancel.set()

    def _log(self, msg):
        ts = time.strftime("%H:%M:%S")
        full = f"[{ts}] [TG] {msg}"
        self.ui_q.put(("log", full))
        print(full)

    def _generate_and_send_qr(self, url: str):
        """Generate QR code image from url and send to GUI via ui_q."""
        try:
            import io
            qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_M,
                                box_size=8, border=2)
            qr.add_data(url)
            qr.make(fit=True)
            img = qr.make_image(fill_color="white", back_color="#1e1e2e")
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            self.ui_q.put(("tg_qr_code", buf.getvalue()))
        except Exception as e:
            self._log(f"QR generate error: {e}")

    async def _send_message(self, chat_id: int, text: str):
        """Kirim pesan ke chat"""
        if self.client:
            await self.client.send_message(chat_id, text)

    async def _send_photo(self, chat_id: int, photo_path: str, caption: str = ""):
        """Kirim foto ke chat"""
        if self.client and os.path.exists(photo_path):
            await self.client.send_file(chat_id, photo_path, caption=caption)

    async def _click_button(self, chat_id: int, msg_id: int, data: bytes):
        """Klik inline button (callback query)"""
        if self.client:
            try:
                msg = await self.client.get_messages(chat_id, ids=msg_id)
                if msg and msg.buttons:
                    # Try by callback data first
                    if data:
                        for row in msg.buttons:
                            for btn in row:
                                if hasattr(btn, 'data') and btn.data == data:
                                    await btn.click()
                                    self._log(f"Clicked button: {btn.text}")
                                    return True
                    # Fallback: click by text "PROSES"
                    for row in msg.buttons:
                        for btn in row:
                            if "PROSES" in (btn.text or "").upper():
                                await btn.click()
                                self._log(f"Clicked button (by text): {btn.text}")
                                return True
            except Exception as e:
                self._log(f"Click button error: {e}")
        return False

    def claim_request(self, req: SuntikanRequest, claimer_id: str = "") -> bool:
        """
        Klik tombol PROSES sebelum transfer untuk claim request.
        
        ANTI-DOUBLE untuk 2 USER DI PC BERBEDA:
        - Pre-click: FRESH fetch message dari Telegram (bukan cache)
        - Post-click: Verifikasi message TEXT berubah (bukan hanya tombol hilang)
        - Final check: Re-fetch sekali lagi sebelum return True
        
        Return True jika:
          - Berhasil klik PROSES DAN verifikasi text berubah
          - ATAU proses_already_clicked=True (retry di instance yang sama)
        Return False jika:
          - PROSES sudah tidak ada (diklaim user lain) ? SKIP
          - Verifikasi gagal (text tidak berubah = klik tidak efektif)
        """
        rid = req.request_id

        # ===== LAYER 1: Cek shared claim file dulu (untuk PC yang sama) =====
        if claimer_id:
            if _is_claimed_by_other(rid, claimer_id):
                self._log(f"[{rid}] claim: Sudah diklaim instance lain (claimed file) - SKIP!")
                return False

        # Jika sudah diklaim di instance ini, cek dulu apakah sudah selesai oleh worker lain
        if req.proses_already_clicked:
            if req.status == "Sukses":
                self._log(f"[{rid}] claim: Request sudah SUKSES oleh worker lain - SKIP!")
                return False
            global_done = _load_success()
            if rid in global_done:
                self._log(f"[{rid}] claim: Request ada di success file (worker lain) - SKIP!")
                return False
            if claimer_id and _is_claimed_by_other(rid, claimer_id):
                self._log(f"[{rid}] claim: Sudah diklaim instance lain saat retry - SKIP!")
                return False
            self._log(f"[{rid}] claim: Sudah diklaim instance ini (retry)")
            return True
        
        # ===== LAYER 2: Coba claim di shared file (atomic, untuk PC sama) =====
        if claimer_id:
            if not _try_claim_file(rid, claimer_id):
                self._log(f"[{rid}] claim: Gagal claim di shared file (instance lain sudah claim) - SKIP!")
                return False
            self._log(f"[{rid}] claim: Berhasil claim di shared file")

        if not self.client or not self._loop or not self._loop.is_running():
            self._log(f"[{rid}] claim_request: TG not ready")
            return True
        
        if not req.message_id or not req.chat_id:
            self._log(f"[{rid}] claim_request: No message_id or chat_id")
            return True
        
        # ===== RANDOM DELAY untuk distribusi fair =====
        # Delay 0-3 detik supaya tidak selalu PC yang sama menang race
        import random
        delay = random.uniform(0.5, 3.0)
        self._log(f"[{rid}] claim: Random delay {delay:.1f}s untuk fair distribution...")
        time.sleep(delay)
        
        async def _do_claim():
            try:
                chat_id = req.chat_id
                my_username = self._my_username.lower().strip()  # Username kita
                
                # ===== HELPER: Extract username dari "Diproses oleh: @xxx" =====
                def extract_diproses_by(text: str) -> str:
                    """Extract username dari 'Diproses oleh: @username' atau 'Diproses oleh: username'"""
                    import re
                    m = re.search(r'diproses\s+oleh\s*:\s*@?(\w+)', text, re.IGNORECASE)
                    if m:
                        return m.group(1).lower()
                    return ""
                
                # ===== PRE-CLICK: Fresh fetch dari Telegram (anti-stale) =====
                self._log(f"[{rid}] claim: Fresh fetch message... (my_username=@{my_username})")
                msg = await self.client.get_messages(chat_id, ids=req.message_id)
                if not msg:
                    self._log(f"[{rid}] claim: Message not found")
                    return False
                
                # Simpan text SEBELUM klik (untuk verifikasi nanti)
                text_before = (msg.text or "").strip()
                text_before_upper = text_before.upper()
                
                # ===== CEK APAKAH SUDAH ADA "Diproses oleh:" =====
                claimed_by = extract_diproses_by(text_before)
                if claimed_by:
                    # Sudah ada yang claim!
                    if my_username and claimed_by == my_username:
                        # Diklaim oleh KITA sebelumnya (retry scenario)
                        self._log(f"[{rid}] claim: Sudah diklaim oleh KITA (@{claimed_by}) sebelumnya - OK")
                        return True
                    else:
                        # Diklaim oleh ORANG LAIN
                        self._log(f"[{rid}] claim: Sudah diklaim oleh @{claimed_by} (bukan kita @{my_username}) - SKIP!")
                        return False
                
                # Cek apakah sudah diproses via text indicator lain
                if "SIAP DIPROSES" in text_before_upper or "SEDANG DIPROSES" in text_before_upper:
                    self._log(f"[{rid}] claim: Message sudah 'siap diproses' (diklaim user lain) - SKIP!")
                    return False
                
                if not msg.buttons:
                    self._log(f"[{rid}] claim: No buttons (sudah selesai)")
                    return False
                
                # Cari tombol PROSES (fresh check)
                proses_btn = None
                for row in msg.buttons:
                    for btn in row:
                        btn_text = (btn.text or "").upper()
                        if "PROSES" in btn_text:
                            proses_btn = btn
                            break
                    if proses_btn:
                        break
                
                if not proses_btn:
                    self._log(f"[{rid}] claim: PROSES tidak ada (fresh check) - diklaim user lain - SKIP!")
                    return False
                
                # ===== KLIK PROSES =====
                try:
                    await proses_btn.click()
                    click_time = time.time()
                    self._log(f"[{rid}] claim: Clicked PROSES, verifying 'Diproses oleh'...")
                    req.proses_already_clicked = True
                except Exception as click_err:
                    self._log(f"[{rid}] claim: Click error: {click_err}")
                    return False
                
                # ===== POST-CLICK VERIFICATION (using "Diproses oleh: @username") =====
                # Ini verifikasi PALING AKURAT - siapa yang klik PROSES
                
                verified = False
                for attempt in range(3):  # Max 3 attempts, total ~9 detik
                    await asyncio.sleep(3)
                    
                    try:
                        msg2 = await self.client.get_messages(chat_id, ids=req.message_id)
                        if not msg2:
                            self._log(f"[{rid}] claim: Verify #{attempt+1} - message hilang")
                            continue
                        
                        text_after = (msg2.text or "").strip()
                        
                        # ===== UTAMA: Cek "Diproses oleh: @username" =====
                        claimed_by_after = extract_diproses_by(text_after)
                        
                        if claimed_by_after:
                            # Ada "Diproses oleh:" sekarang
                            if my_username and claimed_by_after == my_username:
                                # KITA yang claim! ?
                                self._log(f"[{rid}] claim: VERIFIED ? - Diproses oleh @{claimed_by_after} (KITA!)")
                                verified = True
                                break
                            else:
                                # ORANG LAIN yang berhasil claim
                                self._log(f"[{rid}] claim: ABORT - Diproses oleh @{claimed_by_after} (bukan kita @{my_username})")
                                return False
                        
                        # Fallback: Cek tombol PROSES masih ada/tidak
                        still_has_proses = False
                        if msg2.buttons:
                            for row2 in msg2.buttons:
                                for btn2 in row2:
                                    if "PROSES" in (btn2.text or "").upper():
                                        still_has_proses = True
                                        break
                                if still_has_proses:
                                    break
                        
                        if still_has_proses:
                            # Tombol masih ada - klik tidak berhasil, retry
                            self._log(f"[{rid}] claim: Verify #{attempt+1} - PROSES masih ada, retry klik...")
                            for row2 in msg2.buttons:
                                for btn2 in row2:
                                    if "PROSES" in (btn2.text or "").upper():
                                        try:
                                            await btn2.click()
                                        except Exception:
                                            pass
                                        break
                            continue
                        else:
                            # Tombol hilang tapi tidak ada "Diproses oleh:" - anomaly
                            # Coba cek "siap diproses" sebagai fallback
                            text_after_upper = text_after.upper()
                            if "SIAP DIPROSES" in text_after_upper or "SEDANG DIPROSES" in text_after_upper:
                                # Ada indicator sukses tapi tidak tahu siapa - assume kita kalau text berubah
                                if text_after != text_before:
                                    self._log(f"[{rid}] claim: Verify #{attempt+1} - siap diproses + text changed - assume OK")
                                    verified = True
                                    break
                                else:
                                    self._log(f"[{rid}] claim: Verify #{attempt+1} - siap diproses tapi text sama - SKIP safety")
                                    return False
                            self._log(f"[{rid}] claim: Verify #{attempt+1} - tombol hilang tapi tidak ada 'Diproses oleh'")
                            continue
                            
                    except Exception as ve:
                        self._log(f"[{rid}] claim: Verify #{attempt+1} error: {ve}")
                        continue
                
                if not verified:
                    # Gagal verifikasi setelah 3 attempts - SKIP untuk safety
                    # Final check
                    try:
                        msg_final = await self.client.get_messages(chat_id, ids=req.message_id)
                        if msg_final:
                            final_claimed_by = extract_diproses_by(msg_final.text or "")
                            if final_claimed_by:
                                if my_username and final_claimed_by == my_username:
                                    self._log(f"[{rid}] claim: Final - Diproses oleh @{final_claimed_by} (KITA!) ?")
                                    return True
                                else:
                                    self._log(f"[{rid}] claim: Final - Diproses oleh @{final_claimed_by} (bukan kita) - SKIP!")
                                    return False
                    except Exception:
                        pass
                    
                    self._log(f"[{rid}] claim: Verification failed after 3 attempts - SKIP!")
                    return False
                
                return True
                
            except Exception as e:
                self._log(f"[{rid}] claim error: {e}")
                return False
        
        # Run async function on TelethonWorker's event loop
        try:
            future = asyncio.run_coroutine_threadsafe(_do_claim(), self._loop)
            result = future.result(timeout=60.0)  # 60s timeout (3 verify attempts x 3s each + buffer)
            return result
        except Exception as e:
            self._log(f"[{rid}] claim_request exception: {e}")
            return False

    async def _wait_bot_message(self, chat_id: int, bot_username: str,
                                 timeout: float = 15.0, after_id: int = 0) -> Optional[object]:
        """Tunggu pesan baru dari bot setelah msg_id tertentu"""
        end = time.time() + timeout
        attempt = 0
        while time.time() < end:
            attempt += 1
            try:
                msgs = await self.client.get_messages(chat_id, limit=10)
                for msg in msgs:
                    if msg.id <= after_id:
                        continue
                    # Check sender
                    sender_id = msg.sender_id
                    is_bot = False
                    s_name = ""
                    try:
                        sender = await msg.get_sender()
                        if sender:
                            if hasattr(sender, 'username') and sender.username:
                                s_name = sender.username.lower()
                            if hasattr(sender, 'bot') and sender.bot:
                                is_bot = True
                    except Exception:
                        pass
                    if is_bot or (bot_username and s_name == bot_username.lower()):
                        if attempt <= 2:
                            self._log(f"_wait_bot found msg.id={msg.id} from={s_name} is_bot={is_bot}")
                        return msg
                if attempt == 1:
                    # Debug: log what messages we see
                    seen = []
                    for m in msgs[:5]:
                        seen.append(f"id={m.id} sid={m.sender_id} text={repr((m.text or '')[:40])}")
                    self._log(f"_wait_bot attempt1 after_id={after_id}: {seen}")
            except Exception as e:
                self._log(f"_wait_bot error: {e}")
            await asyncio.sleep(1.5)
        self._log(f"_wait_bot TIMEOUT after {attempt} attempts")
        return None

    async def _click_button_in_msg(self, msg, text_match: str) -> bool:
        """Klik inline button dalam pesan berdasarkan text match"""
        if not msg or not msg.buttons:
            return False
        for row in msg.buttons:
            for btn in row:
                btn_text = (btn.text or "").upper()
                if text_match.upper() in btn_text:
                    await btn.click()
                    self._log(f"Clicked: {btn.text}")
                    return True
        # Fallback: klik tombol pertama
        try:
            await msg.buttons[0][0].click()
            self._log(f"Clicked first button: {msg.buttons[0][0].text}")
            return True
        except Exception:
            pass
        return False

    def do_post_transfer(self, req: SuntikanRequest):
        """Dipanggil setelah transfer sukses - handle semua interaksi TG"""
        self._log(f"[{req.request_id}] do_post_transfer called")
        if not self.client:
            self._log(f"[{req.request_id}] TG client is None, skip")
            return
        if not self._loop:
            self._log(f"[{req.request_id}] TG loop is None, skip")
            return
        if not self._loop.is_running():
            self._log(f"[{req.request_id}] TG loop not running, skip")
            return

        async def _post():
            try:
                chat_id = req.chat_id
                bot_username = self.cfg.get("bot_username", "").lower().strip("@ ")
                last_msg_id = req.message_id

                self._log(f"[{req.request_id}] Post-transfer TG mulai...")
                self._log(f"[{req.request_id}] chat_id={chat_id}, msg_id={req.message_id}, already_clicked={req.proses_already_clicked}")

                # ===== STEP 1: Klik tombol PROSES (skip jika sudah diklik saat claim) =====
                if not req.proses_already_clicked:
                    if req.message_id:
                        clicked = await self._click_button(chat_id, req.message_id, req.proses_callback_data)
                        if not clicked:
                            self._log(f"[{req.request_id}] Gagal klik PROSES (mungkin sudah diklik)")
                    else:
                        self._log(f"[{req.request_id}] Tidak ada message_id untuk PROSES")
                else:
                    self._log(f"[{req.request_id}] PROSES sudah diklik saat claim, skip ke pilih bank")

                # ===== STEP 2: Tunggu bot respond (pilih bank) =====
                # Bot EDIT pesan yang sama setelah klik PROSES (bukan kirim baru)
                await asyncio.sleep(3)  # Tunggu bot proses
                self._log(f"[{req.request_id}] Tunggu bot respond (pilih bank)...")

                # Re-fetch the SAME message to get updated buttons
                bot_msg = None
                for _retry in range(10):
                    try:
                        bot_msg = await self.client.get_messages(chat_id, ids=req.message_id)
                        if bot_msg and bot_msg.buttons:
                            # Cek apakah buttons sudah berubah (bukan PROSES/BATAL lagi)
                            first_btn = bot_msg.buttons[0][0].text or ""
                            if "PROSES" not in first_btn.upper() and "BATAL" not in first_btn.upper():
                                self._log(f"[{req.request_id}] Bot msg updated! First btn: {first_btn}")
                                break
                    except Exception as e:
                        self._log(f"[{req.request_id}] Re-fetch error: {e}")
                    await asyncio.sleep(2)
                else:
                    # Fallback: coba cari pesan baru juga
                    bot_msg = await self._wait_bot_message(chat_id, bot_username, timeout=10.0, after_id=req.message_id)

                if bot_msg and bot_msg.buttons:
                    last_msg_id = bot_msg.id
                    self._log(f"[{req.request_id}] Bot msg: {(bot_msg.text or '')[:80]}")
                    # Cari tombol yang cocok dengan bank yang dipakai
                    bank_name = (req.bank_used or "").upper()
                    clicked = False
                    # Coba sampai 5 halaman (Next pagination)
                    current_msg_id = bot_msg.id
                    for page in range(5):
                        # Reload message to get fresh buttons (after Next click)
                        if page > 0:
                            try:
                                await asyncio.sleep(2)
                                bot_msg = await self.client.get_messages(chat_id, ids=current_msg_id)
                            except Exception:
                                pass
                        if not bot_msg or not bot_msg.buttons:
                            break
                        all_btns = []
                        for row in bot_msg.buttons:
                            for btn in row:
                                btn_text = (btn.text or "").upper()
                                all_btns.append(btn.text or "")
                                if bank_name and bank_name in btn_text:
                                    await btn.click()
                                    self._log(f"[{req.request_id}] Selected bank (page {page+1}): {btn.text}")
                                    clicked = True
                                    break
                            if clicked:
                                break
                        if clicked:
                            break
                        self._log(f"[{req.request_id}] Page {page+1} buttons: {all_btns}")
                        # Bank tidak ditemukan, cari tombol Next/Selanjutnya
                        next_clicked = False
                        for row in bot_msg.buttons:
                            for btn in row:
                                bt = (btn.text or "").upper()
                                if "NEXT" in bt or "SELANJUT" in bt or bt == ">>" or bt == "\u25b6":
                                    await btn.click()
                                    self._log(f"[{req.request_id}] Clicked Next: {btn.text}")
                                    next_clicked = True
                                    break
                            if next_clicked:
                                break
                        if not next_clicked:
                            self._log(f"[{req.request_id}] No Next button, bank not found")
                            break
                    if not clicked:
                        self._log(f"[{req.request_id}] Bank '{bank_name}' tidak ditemukan")
                        try:
                            if bot_msg and bot_msg.buttons:
                                await bot_msg.buttons[0][0].click()
                                self._log(f"[{req.request_id}] Selected bank (fallback): {bot_msg.buttons[0][0].text}")
                        except Exception as e:
                            self._log(f"[{req.request_id}] Gagal pilih bank: {e}")
                else:
                    self._log(f"[{req.request_id}] Timeout tunggu bot respond pilih bank")
                    return

                # ===== STEP 3: Tunggu bot tanya biaya =====
                # Bot mungkin EDIT pesan yang sama lagi, atau kirim baru
                await asyncio.sleep(3)
                self._log(f"[{req.request_id}] Tunggu bot tanya biaya...")

                # Coba re-fetch pesan yang sama dulu (bot edit)
                biaya_msg = None
                for _retry in range(8):
                    try:
                        refetched = await self.client.get_messages(chat_id, ids=current_msg_id)
                        if refetched and refetched.text:
                            txt_up = refetched.text.upper()
                            if "BIAYA" in txt_up or "FEE" in txt_up or "ADMIN" in txt_up:
                                biaya_msg = refetched
                                self._log(f"[{req.request_id}] Biaya prompt (edit): {(refetched.text or '')[:60]}")
                                break
                    except Exception:
                        pass
                    # Juga coba cari pesan baru
                    try:
                        new_msg = await self._wait_bot_message(chat_id, bot_username, timeout=3.0, after_id=last_msg_id)
                        if new_msg:
                            last_msg_id = new_msg.id
                            biaya_msg = new_msg
                            self._log(f"[{req.request_id}] Biaya prompt (new msg): {(new_msg.text or '')[:60]}")
                            break
                    except Exception:
                        pass
                    await asyncio.sleep(2)

                # Kirim biaya
                biaya = req.biaya_bank
                if biaya <= 0:
                    biaya = 0 if (req.jenis_bank or "").upper() == "BCA" else int(self.cfg.get("biaya_bifast", 2500))
                await self.client.send_message(chat_id, str(biaya))
                self._log(f"[{req.request_id}] Sent biaya: {biaya}")

                # ===== STEP 4: Tunggu bot tanya screenshot -> kirim foto =====
                await asyncio.sleep(3)
                self._log(f"[{req.request_id}] Tunggu bot tanya screenshot...")

                # Tunggu pesan baru tentang screenshot/bukti
                for _retry in range(8):
                    try:
                        new_msg = await self._wait_bot_message(chat_id, bot_username, timeout=3.0, after_id=last_msg_id)
                        if new_msg:
                            last_msg_id = new_msg.id
                            self._log(f"[{req.request_id}] Screenshot prompt: {(new_msg.text or '')[:60]}")
                            break
                    except Exception:
                        pass
                    # Juga cek edit pada pesan lama
                    try:
                        refetched = await self.client.get_messages(chat_id, ids=current_msg_id)
                        if refetched and refetched.text:
                            txt_up = refetched.text.upper()
                            if "SCREENSHOT" in txt_up or "BUKTI" in txt_up or "FOTO" in txt_up:
                                self._log(f"[{req.request_id}] Screenshot prompt (edit): {(refetched.text or '')[:60]}")
                                break
                    except Exception:
                        pass
                    await asyncio.sleep(2)

                # Kirim screenshot
                if req.screenshot_path and os.path.exists(req.screenshot_path):
                    await self.client.send_file(chat_id, req.screenshot_path)
                    self._log(f"[{req.request_id}] Sent screenshot: {req.screenshot_path}")
                else:
                    await self.client.send_message(chat_id, "/skip")
                    self._log(f"[{req.request_id}] Sent /skip (no screenshot)")

                self._log(f"[{req.request_id}] Post-transfer TG SELESAI!")
            except Exception as e:
                self._log(f"[{req.request_id}] Post-transfer ERROR: {e}")
                import traceback
                traceback.print_exc()

        future = asyncio.run_coroutine_threadsafe(_post(), self._loop)
        # Wait for result in this thread so errors surface
        try:
            future.result(timeout=120)
        except Exception as e:
            self._log(f"[{req.request_id}] Post-transfer future error: {e}")

    async def fetch_pending_requests(self, existing_reks: set = None, limit: int = 100):
        """
        Fetch pending KONFIRMASI SUNTIK DANA messages from Telegram that were missed.
        Returns list of new requests that were added.
        """
        if existing_reks is None:
            existing_reks = set()
        
        group_id = self.cfg.get("group_chat_id", 0)
        bot_username = (self.cfg.get("bot_username", "") or "").lower().lstrip("@")
        
        if not group_id:
            self._log("Group chat ID tidak diset!")
            return []
        
        new_requests = []
        try:
            self._log(f"Fetching last {limit} messages from group...")
            messages = await self.client.get_messages(int(group_id), limit=limit)
            
            konfirmasi_count = 0
            for msg in messages:
                if not msg or not msg.text:
                    continue
                
                text = msg.text
                text_upper = text.upper()
                
                # Detect both KONFIRMASI SUNTIK and "Suntikan siap diproses" (after PROSES clicked)
                is_konfirmasi = "KONFIRMASI SUNTIK" in text_upper
                is_siap_proses = "SUNTIKAN SIAP DIPROSES" in text_upper
                
                if not is_konfirmasi and not is_siap_proses:
                    continue
                
                konfirmasi_count += 1
                
                # Check if sender is bot
                sender_name = ""
                is_bot_msg = False
                try:
                    sender = await msg.get_sender()
                    if sender:
                        if hasattr(sender, 'username') and sender.username:
                            sender_name = sender.username.lower()
                        if hasattr(sender, 'bot') and sender.bot:
                            is_bot_msg = True
                except Exception:
                    pass
                
                if not is_bot_msg and bot_username and sender_name != bot_username:
                    continue
                
                # Parse the konfirmasi message
                parsed = parse_konfirmasi_message(text)
                if not parsed:
                    continue
                
                no_rek = parsed.get("no_rek", "")
                
                # Skip if we already have this request (by no_rek or message_id)
                if no_rek in existing_reks:
                    continue
                if f"msg:{msg.id}" in existing_reks:
                    continue
                
                # Check buttons state
                has_proses_btn = False
                proses_cb = b""
                
                if msg.buttons:
                    for row in msg.buttons:
                        for btn in row:
                            btn_text = (btn.text or "").upper()
                            if "PROSES" in btn_text:
                                has_proses_btn = True
                                if hasattr(btn, 'data'):
                                    proses_cb = btn.data or b""
                                break
                        if has_proses_btn:
                            break
                
                # HANYA fetch request yang masih ada tombol PROSES
                # Kalau PROSES sudah tidak ada (sudah diklik user lain), SKIP
                if not has_proses_btn:
                    continue
                
                # Create new request
                req = SuntikanRequest(
                    request_id=f"INJ-{msg.id}-{int(time.time()*1000) % 10000}",
                    chat_id=int(group_id),
                    message_id=msg.id,
                    no_rek=no_rek,
                    nama_bank=parsed.get("nama_bank", ""),
                    jenis_bank=parsed.get("jenis_bank", ""),
                    nominal=_parse_nominal(str(parsed.get("nominal", "0"))),
                    nominal_raw=str(parsed.get("nominal", "")),
                    saldo_akhir=parsed.get("saldo_akhir", ""),
                    timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
                    raw_text=text,
                    proses_callback_data=proses_cb,
                )
                
                # Try to get asset from reply + check screenshot
                has_screenshot = False
                if msg.reply_to and msg.reply_to.reply_to_msg_id:
                    try:
                        orig = await self.client.get_messages(int(group_id), ids=msg.reply_to.reply_to_msg_id)
                        if orig:
                            # Cek apakah pesan request asli punya foto
                            if orig.media and isinstance(orig.media, MessageMediaPhoto):
                                has_screenshot = True
                            if orig.text:
                                orig_data = parse_request_message(orig.text)
                                if orig_data:
                                    req.asset_web = orig_data.get("asset_web", "")
                                    req.request_by = orig_data.get("request_by", "")
                                    req.original_msg_id = orig.id
                    except Exception:
                        pass
                
                # Fallback: search for asset in chat
                if not req.asset_web and no_rek:
                    try:
                        recent = await self.client.get_messages(
                            int(group_id), limit=50,
                            offset_id=msg.id, reverse=False
                        )
                        for rm in (recent or []):
                            if rm.id == msg.id:
                                continue
                            rtxt = rm.text or ""
                            if no_rek in rtxt:
                                orig_data = parse_request_message(rtxt)
                                if orig_data and orig_data.get("asset_web"):
                                    req.asset_web = orig_data["asset_web"]
                                    req.request_by = orig_data.get("request_by", req.request_by)
                                    req.original_msg_id = rm.id
                                    # Cek screenshot di pesan ini juga
                                    if not has_screenshot and rm.media and isinstance(rm.media, MessageMediaPhoto):
                                        has_screenshot = True
                                    break
                    except Exception:
                        pass
                
                # SKIP request tanpa screenshot
                if not has_screenshot:
                    self._log(f"Skip (no screenshot): {parsed.get('nama_bank', '')} - {no_rek}")
                    continue
                
                # Fallback: parse asset from KONFIRMASI itself
                if not req.asset_web:
                    m_asset = re.search(r'Asset\s*(?:WEB)?\s*:\s*(.+)', text, re.I)
                    if m_asset:
                        req.asset_web = m_asset.group(1).strip()
                
                self._log(f"Found pending: {req.nama_bank} - {req.jenis_bank} - Rp {req.nominal:,} - {req.asset_web}")
                self.ui_q.put(("new_request", req))
                new_requests.append(req)
                existing_reks.add(no_rek)  # Prevent duplicates
                existing_reks.add(f"msg:{msg.id}")  # Also track by msg id
                
                # Track processed msg ID to prevent double from NewMessage event
                with self._processed_msg_lock:
                    self._processed_msg_ids.add(msg.id)
            
            self._log(f"Scanned {len(messages)} msgs, found {konfirmasi_count} KONFIRMASI, {len(new_requests)} new pending")
            
        except Exception as e:
            self._log(f"Fetch pending error: {e}")
            import traceback
            traceback.print_exc()
        
        return new_requests

    def run(self):
        if not HAS_TELETHON:
            self._log("Telethon not installed!")
            return

        api_id = self.cfg.get("api_id", "")
        api_hash = self.cfg.get("api_hash", "")
        phone = self.cfg.get("phone", "")

        if not api_id or not api_hash:
            self._log("API ID & Hash kosong!")
            return

        async def _run():
            self._log("Connecting to Telegram...")
            session = StringSession(self.cfg.get("session_string", ""))
            self.client = TelegramClient(
                session, 
                int(api_id), 
                api_hash,
                connection_retries=5,
                retry_delay=1,
                auto_reconnect=True,
                request_retries=3
            )

            await self.client.connect()

            if not await self.client.is_user_authorized():
                self._log("Need login...")
                logged_in_via_qr = False

                # -- Try QR Code Login first --
                if HAS_QRCODE:
                    self._qr_cancel.clear()
                    self._log("Attempting QR Code login...")
                    qr_was_scanned = False
                    try:
                        qr_login = await self.client.qr_login()
                        self._log(f"QR login initiated, show QR to user")

                        max_attempts = 60  # 60 x 5s = 300s = 5 menit
                        for attempt in range(max_attempts):
                            if self._stop.is_set() or self._qr_cancel.is_set():
                                break
                            
                            # Check if already authorized (user might have scanned)
                            try:
                                if await self.client.is_user_authorized():
                                    logged_in_via_qr = True
                                    self._log("QR Code scanned! Authorized.")
                                    self.ui_q.put(("tg_qr_close", None))
                                    break
                            except SessionPasswordNeededError:
                                # QR scanned but 2FA needed
                                qr_was_scanned = True
                                self._log("QR scanned, 2FA required...")
                                break
                            except Exception:
                                pass
                            
                            # Generate QR image and send to GUI
                            self._generate_and_send_qr(qr_login.url)
                            
                            # Show countdown every 30 seconds
                            remaining = (max_attempts - attempt) * 5
                            if attempt % 6 == 0:  # setiap 30 detik
                                self._log(f"Waiting QR scan... {remaining}s remaining")

                            try:
                                # Wait 5s for scan
                                await asyncio.wait_for(qr_login.wait(), timeout=5)
                                logged_in_via_qr = True
                                qr_was_scanned = True
                                self._log("QR Code scanned! Checking authorization...")
                                self.ui_q.put(("tg_qr_close", None))
                                break
                            except asyncio.TimeoutError:
                                # QR expired, recreate
                                try:
                                    # Ensure still connected before recreate
                                    if not self.client.is_connected():
                                        await self.client.connect()
                                    await qr_login.recreate()
                                except Exception as recreate_err:
                                    err_msg = str(recreate_err)
                                    err_msg_lower = err_msg.lower()
                                    
                                    # QR was scanned and 2FA is needed - handle directly!
                                    if "two-steps verification" in err_msg_lower or "password is required" in err_msg_lower:
                                        self._log("QR scanned! 2FA password required...")
                                        self.ui_q.put(("tg_qr_close", None))
                                        self.ui_q.put(("tg_need_2fa", None))
                                        pwd = await asyncio.get_event_loop().run_in_executor(None, self._2fa_queue.get)
                                        if pwd:
                                            try:
                                                await self.client.sign_in(password=pwd)
                                                logged_in_via_qr = True
                                                self._log("2FA password accepted! Login OK!")
                                            except Exception as e2fa:
                                                self._log(f"2FA sign_in failed: {e2fa}")
                                        else:
                                            self._log("2FA password cancelled")
                                        break
                                    
                                    # DC migration - QR was scanned but need to switch DC
                                    elif "logintoken" in err_msg_lower or "migrate" in err_msg_lower:
                                        self._log("QR scanned! DC migration needed...")
                                        self.ui_q.put(("tg_qr_close", None))
                                        qr_was_scanned = True
                                        # Let the post-loop code handle 2FA
                                        break
                                    
                                    # Connection issues
                                    elif "disconnected" in err_msg_lower or "connection" in err_msg_lower or "eof" in err_msg_lower:
                                        self._log(f"Connection lost, creating fresh session...")
                                        try:
                                            try:
                                                await self.client.disconnect()
                                            except:
                                                pass
                                            await asyncio.sleep(1)
                                            
                                            fresh_session = StringSession()
                                            self.client = TelegramClient(
                                                fresh_session,
                                                int(api_id),
                                                api_hash,
                                                connection_retries=5,
                                                retry_delay=1,
                                                auto_reconnect=True,
                                                request_retries=3
                                            )
                                            await self.client.connect()
                                            
                                            self._log("Restarting QR login with fresh session...")
                                            qr_login = await self.client.qr_login()
                                            self._generate_and_send_qr(qr_login.url)
                                            continue
                                        except SessionPasswordNeededError:
                                            qr_was_scanned = True
                                            self._log("QR was scanned, 2FA required...")
                                            break
                                        except Exception as reconn_err:
                                            self._log(f"Fresh session failed: {reconn_err}")
                                            continue
                                    else:
                                        self._log(f"QR recreate failed: {recreate_err}")
                                        qr_was_scanned = True
                                        break

                        # Close QR dialog
                        self.ui_q.put(("tg_qr_close", None))
                        
                        # Check if 2FA needed after QR scan
                        if qr_was_scanned:
                            self._log("Checking if 2FA password needed...")
                            
                            # First ensure we're connected
                            if not self.client.is_connected():
                                self._log("Reconnecting before 2FA check...")
                                try:
                                    await self.client.connect()
                                except Exception as conn_err:
                                    self._log(f"Reconnect error: {conn_err}")
                            
                            try:
                                me = await self.client.get_me()
                                if me:
                                    logged_in_via_qr = True
                                    self._log("QR Login OK!")
                            except SessionPasswordNeededError:
                                self._log("2FA password required! Masukkan password Telegram Anda.")
                                self.ui_q.put(("tg_need_2fa", None))
                                pwd = await asyncio.get_event_loop().run_in_executor(None, self._2fa_queue.get)
                                if pwd:
                                    try:
                                        await self.client.sign_in(password=pwd)
                                        logged_in_via_qr = True
                                        self._log("2FA password accepted!")
                                    except Exception as e2fa:
                                        self._log(f"2FA sign_in failed: {e2fa}")
                                else:
                                    self._log("2FA password cancelled")
                            except Exception as e2:
                                err_msg2 = str(e2).lower()
                                if "disconnected" in err_msg2 or "connection" in err_msg2:
                                    self._log("Connection lost during check, attempting reconnect...")
                                    try:
                                        await self.client.disconnect()
                                        await asyncio.sleep(1)
                                        await self.client.connect()
                                        
                                        # Try again after reconnect
                                        try:
                                            if await self.client.is_user_authorized():
                                                logged_in_via_qr = True
                                                self._log("QR Login OK after reconnect!")
                                        except SessionPasswordNeededError:
                                            self._log("2FA password required!")
                                            self.ui_q.put(("tg_need_2fa", None))
                                            pwd = await asyncio.get_event_loop().run_in_executor(None, self._2fa_queue.get)
                                            if pwd:
                                                try:
                                                    await self.client.sign_in(password=pwd)
                                                    logged_in_via_qr = True
                                                    self._log("2FA password accepted!")
                                                except Exception as e2fa:
                                                    self._log(f"2FA sign_in failed: {e2fa}")
                                            else:
                                                self._log("2FA password cancelled")
                                    except Exception as reconn_err2:
                                        self._log(f"Reconnect failed: {reconn_err2}")
                                else:
                                    self._log(f"Post-QR check error: {e2}")
                        
                        if not logged_in_via_qr and not qr_was_scanned and not self._qr_cancel.is_set():
                            self._log("QR login timeout (5 min)")
                                
                    except SessionPasswordNeededError:
                        # QR was scanned but 2FA is required
                        self._log("QR scanned! 2FA password required.")
                        self.ui_q.put(("tg_qr_close", None))
                        self.ui_q.put(("tg_need_2fa", None))
                        pwd = await asyncio.get_event_loop().run_in_executor(None, self._2fa_queue.get)
                        if pwd:
                            try:
                                await self.client.sign_in(password=pwd)
                                logged_in_via_qr = True
                                self._log("2FA password accepted! Login OK!")
                            except Exception as e2fa:
                                self._log(f"2FA sign_in failed: {e2fa}")
                        else:
                            self._log("2FA password cancelled")
                    except Exception as e:
                        err_str = str(e)
                        if "Two-steps verification" in err_str or "password is required" in err_str:
                            # QR was scanned but 2FA is required (different exception type)
                            self._log("QR scanned! 2FA password required.")
                            self.ui_q.put(("tg_qr_close", None))
                            self.ui_q.put(("tg_need_2fa", None))
                            pwd = await asyncio.get_event_loop().run_in_executor(None, self._2fa_queue.get)
                            if pwd:
                                try:
                                    await self.client.sign_in(password=pwd)
                                    logged_in_via_qr = True
                                    self._log("2FA password accepted! Login OK!")
                                except Exception as e2fa:
                                    self._log(f"2FA sign_in failed: {e2fa}")
                            else:
                                self._log("2FA password cancelled")
                        else:
                            # Check for other known issues that indicate QR was scanned
                            if "LoginTokenMigrateTo" in err_str or "MigrateTo" in err_str:
                                self._log("QR scanned! DC migration detected, checking 2FA...")
                                self.ui_q.put(("tg_qr_close", None))
                                
                                # Don't disconnect! Just check if 2FA is needed
                                try:
                                    # Give Telethon time to handle DC migration internally
                                    await asyncio.sleep(2)
                                    
                                    if await self.client.is_user_authorized():
                                        logged_in_via_qr = True
                                        self._log("Already authorized after DC migration!")
                                    else:
                                        # Need 2FA
                                        self._log("2FA password required...")
                                        self.ui_q.put(("tg_need_2fa", None))
                                        pwd = await asyncio.get_event_loop().run_in_executor(None, self._2fa_queue.get)
                                        if pwd:
                                            try:
                                                await self.client.sign_in(password=pwd)
                                                logged_in_via_qr = True
                                                self._log("2FA password accepted! Login OK!")
                                            except Exception as e2fa:
                                                self._log(f"2FA sign_in failed: {e2fa}")
                                        else:
                                            self._log("2FA password cancelled")
                                except SessionPasswordNeededError:
                                    self._log("2FA password required...")
                                    self.ui_q.put(("tg_need_2fa", None))
                                    pwd = await asyncio.get_event_loop().run_in_executor(None, self._2fa_queue.get)
                                    if pwd:
                                        try:
                                            await self.client.sign_in(password=pwd)
                                            logged_in_via_qr = True
                                            self._log("2FA password accepted! Login OK!")
                                        except Exception as e2fa:
                                            self._log(f"2FA sign_in failed: {e2fa}")
                                    else:
                                        self._log("2FA password cancelled")
                                except Exception as e2fa:
                                    self._log(f"DC migration/2FA handling failed: {e2fa}")
                            else:
                                self._log(f"QR login error: {e}")
                                self.ui_q.put(("tg_qr_close", None))

                # -- Fall back to Phone OTP if QR didn't work --
                try:
                    is_authed = await self.client.is_user_authorized()
                except SessionPasswordNeededError:
                    # 2FA still needed - should have been handled above
                    self._log("2FA still pending, requesting password...")
                    self.ui_q.put(("tg_need_2fa", None))
                    pwd = await asyncio.get_event_loop().run_in_executor(None, self._2fa_queue.get)
                    if pwd:
                        try:
                            await self.client.sign_in(password=pwd)
                            is_authed = True
                        except Exception as e2fa:
                            self._log(f"2FA sign_in failed: {e2fa}")
                            return
                    else:
                        self._log("2FA cancelled")
                        return
                except Exception:
                    is_authed = False
                
                if not logged_in_via_qr and not is_authed:
                    if self._qr_cancel.is_set():
                        self.ui_q.put(("tg_qr_close", None))
                    if not phone:
                        self._log("========================================")
                        self._log("QR Login gagal - coba lagi:")
                        self._log("1. Klik Stop, lalu Start ulang")
                        self._log("2. Scan QR dengan cepat (< 30 detik)")
                        self._log("3. Jika muncul dialog 2FA, masukkan password")
                        self._log("========================================")
                        return
                    self._log(f"Trying phone login: {phone}")
                    self.ui_q.put(("tg_need_login", phone))
                    await self.client.send_code_request(phone)
                    self._log("OTP sent! Masukkan kode di GUI.")
                    self.ui_q.put(("tg_need_otp", None))

                    code = await asyncio.get_event_loop().run_in_executor(None, self._otp_queue.get)
                    try:
                        await self.client.sign_in(phone, code)
                    except Exception as e:
                        if "Two-steps verification" in str(e) or "password" in str(e).lower():
                            self._log("2FA required")
                            self.ui_q.put(("tg_need_2fa", None))
                            pwd = await asyncio.get_event_loop().run_in_executor(None, self._2fa_queue.get)
                            try:
                                await self.client.sign_in(password=pwd)
                            except Exception as e2fa:
                                self._log(f"2FA sign_in failed: {e2fa}")
                                return
                        else:
                            self._log(f"Login error: {e}")
                            return

            self.me = await self.client.get_me()
            self._logged_in = True
            name = f"{self.me.first_name or ''} {self.me.last_name or ''}".strip()
            uname = self.me.username or ""
            self._my_username = uname.lower()  # Simpan untuk verifikasi klaim
            self._log(f"Logged in as: {name} (@{uname or 'N/A'})")
            self.ui_q.put(("tg_logged_in", name))

            # Download profile photo for sidebar
            photo_path = ""
            try:
                photo_path = await self.client.download_profile_photo(
                    "me", file=os.path.join(os.path.dirname(__file__) or ".", "tg_avatar.jpg")
                )
                if photo_path:
                    self._log(f"Profile photo saved: {photo_path}")
            except Exception as ep:
                self._log(f"Photo download skipped: {ep}")
            self.ui_q.put(("tg_profile", (name, uname, photo_path or "")))

            # Save session
            sess_str = self.client.session.save()
            self.cfg["session_string"] = sess_str
            save_config(self.cfg)
            self._log("Session saved")

            # Monitor group
            group_id = self.cfg.get("group_chat_id", 0)
            bot_username = self.cfg.get("bot_username", "").lower().strip("@ ")

            if group_id:
                @self.client.on(events.NewMessage(chats=int(group_id)))
                async def on_new_message(event):
                    msg = event.message
                    text = msg.text or ""
                    sender = await msg.get_sender()
                    sender_name = ""
                    if sender:
                        if hasattr(sender, 'username') and sender.username:
                            sender_name = sender.username.lower()
                        elif hasattr(sender, 'first_name'):
                            sender_name = sender.first_name or ""

                    # Cek apakah ini pesan KONFIRMASI dari bot
                    is_bot_msg = False
                    if bot_username and sender_name == bot_username:
                        is_bot_msg = True
                    elif sender and hasattr(sender, 'bot') and sender.bot:
                        is_bot_msg = True

                    if is_bot_msg and "KONFIRMASI SUNTIK" in text.upper():
                        parsed = parse_konfirmasi_message(text)
                        if parsed:
                            # Check duplicate: skip if msg.id already processed
                            with self._processed_msg_lock:
                                if msg.id in self._processed_msg_ids:
                                    # Already processed this msg (from fetch or earlier event), skip
                                    return
                                # Mark as processed immediately to prevent race
                                self._processed_msg_ids.add(msg.id)

                            # Extract callback data dari tombol PROSES
                            proses_cb = b""
                            if msg.buttons:
                                for row in msg.buttons:
                                    for btn in row:
                                        if "PROSES" in (btn.text or "").upper():
                                            if hasattr(btn, 'data'):
                                                proses_cb = btn.data or b""
                                            break

                            req = SuntikanRequest(
                                request_id=f"INJ-{msg.id}-{int(time.time()*1000) % 10000}",
                                chat_id=int(group_id),
                                message_id=msg.id,
                                no_rek=parsed.get("no_rek", ""),
                                nama_bank=parsed.get("nama_bank", ""),
                                jenis_bank=parsed.get("jenis_bank", ""),
                                nominal=_parse_nominal(str(parsed.get("nominal", "0"))),
                                nominal_raw=str(parsed.get("nominal", "")),
                                saldo_akhir=parsed.get("saldo_akhir", ""),
                                timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
                                raw_text=text,
                                proses_callback_data=proses_cb,
                            )
                            # Cari asset & request_by dari pesan yang di-reply + check screenshot
                            has_screenshot = False
                            if msg.reply_to and msg.reply_to.reply_to_msg_id:
                                try:
                                    orig = await self.client.get_messages(int(group_id), ids=msg.reply_to.reply_to_msg_id)
                                    if orig:
                                        # Cek apakah pesan request asli punya foto
                                        if orig.media and isinstance(orig.media, MessageMediaPhoto):
                                            has_screenshot = True
                                        if orig.text:
                                            orig_data = parse_request_message(orig.text)
                                            if orig_data:
                                                req.asset_web = orig_data.get("asset_web", "")
                                                req.request_by = orig_data.get("request_by", "")
                                                req.original_msg_id = orig.id
                                                self._log(f"  Asset dari reply-to: {req.asset_web}")
                                            else:
                                                self._log("  Reply-to msg ada tapi format tidak cocok")
                                    else:
                                        self._log("  Reply-to msg kosong")
                                except Exception as e:
                                    self._log(f"  Reply-to lookup error: {e}")
                            else:
                                self._log("  KONFIRMASI bukan reply, cari original di chat...")

                            # Fallback: jika asset masih kosong, cari pesan original di chat
                            if not req.asset_web:
                                try:
                                    recent = await self.client.get_messages(
                                        int(group_id), limit=50,
                                        offset_id=msg.id, reverse=False
                                    )
                                    for rm in (recent or []):
                                        if rm.id == msg.id:
                                            continue
                                        rtxt = rm.text or ""
                                        if req.no_rek and req.no_rek in rtxt:
                                            orig_data = parse_request_message(rtxt)
                                            if orig_data and orig_data.get("asset_web"):
                                                req.asset_web = orig_data["asset_web"]
                                                req.request_by = orig_data.get("request_by", req.request_by)
                                                req.original_msg_id = rm.id
                                                self._log(f"  Asset dari search: {req.asset_web} (msg#{rm.id})")
                                                # Cek screenshot di pesan ini juga
                                                if not has_screenshot and rm.media and isinstance(rm.media, MessageMediaPhoto):
                                                    has_screenshot = True
                                                break
                                except Exception as e:
                                    self._log(f"  Fallback search error: {e}")

                            # SKIP request tanpa screenshot
                            if not has_screenshot:
                                self._log(f"  Skip (no screenshot): {req.nama_bank} - {req.no_rek}")
                                return

                            # Fallback 2: coba parse asset dari KONFIRMASI itu sendiri
                            if not req.asset_web:
                                m_asset = re.search(r'Asset\s*(?:WEB)?\s*:\s*(.+)', text, re.I)
                                if m_asset:
                                    req.asset_web = m_asset.group(1).strip()
                                    self._log(f"  Asset dari KONFIRMASI: {req.asset_web}")

                            self._log(f"New request: {req.nama_bank} - {req.jenis_bank} - Rp {req.nominal:,} - Asset: {req.asset_web or '(kosong)'}")
                            self.ui_q.put(("new_request", req))

                self._log(f"Monitoring group: {group_id}")
            else:
                self._log("Group chat ID tidak diset, tidak monitor")

            self.ui_q.put(("tg_status", "Connected"))

            # Keep running
            while not self._stop.is_set():
                await asyncio.sleep(0.5)

            await self.client.disconnect()
            self._log("Disconnected")

        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(_run())
        except Exception as e:
            self._log(f"TG Error: {e}")
        finally:
            self._loop.close()


# ======================================================================
# GUI  (PySide6 / Qt6)
# ======================================================================

# -- Dark Palette (QSS) --
DARK_QSS = """
QMainWindow, QWidget { background-color: #1e1e2e; color: #cdd6f4; }
QTabWidget::pane { border: 1px solid #45475a; background: #1e1e2e; }
QTabBar::tab { background: #313244; color: #cdd6f4; padding: 8px 18px; border: 1px solid #45475a;
               border-bottom: none; border-top-left-radius: 6px; border-top-right-radius: 6px; margin-right: 2px; }
QTabBar::tab:selected { background: #1e1e2e; color: #89b4fa; font-weight: bold; }
QGroupBox { border: 1px solid #45475a; border-radius: 6px; margin-top: 10px; padding-top: 14px;
            color: #a6adc8; font-weight: bold; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; }
QPushButton { background: #313244; color: #cdd6f4; border: 1px solid #45475a; border-radius: 5px;
              padding: 6px 14px; font-weight: bold; }
QPushButton:hover { background: #45475a; }
QPushButton:pressed { background: #585b70; }
QPushButton#startBtn { background: #a6e3a1; color: #1e1e2e; }
QPushButton#startBtn:hover { background: #94e2d5; }
QPushButton#stopBtn { background: #f38ba8; color: #1e1e2e; }
QPushButton#stopBtn:hover { background: #eba0ac; }
QPushButton#saveBtn { background: #89b4fa; color: #1e1e2e; }
QPushButton#saveBtn:hover { background: #74c7ec; }
QLineEdit { background: #313244; color: #cdd6f4; border: 1px solid #45475a; border-radius: 4px;
            padding: 4px 8px; }
QCheckBox { color: #cdd6f4; spacing: 6px; }
QCheckBox::indicator { width: 16px; height: 16px; }
QTextEdit { background: #11111b; color: #a6e3a1; border: 1px solid #45475a; border-radius: 4px;
            font-family: Consolas, 'Cascadia Code', monospace; font-size: 10pt; font-weight: bold; }
QTableWidget { background: #181825; color: #cdd6f4; border: 1px solid #45475a; border-radius: 4px;
               gridline-color: #313244; selection-background-color: #45475a; }
QTableWidget::item { padding: 3px 6px; }
QHeaderView::section { background: #313244; color: #a6adc8; border: 1px solid #45475a;
                        padding: 5px 8px; font-weight: bold; }
QScrollBar:vertical { background: #181825; width: 10px; }
QScrollBar::handle:vertical { background: #45475a; border-radius: 5px; min-height: 20px; }
QSplitter::handle { background: #45475a; }
QMenu { background: #313244; color: #cdd6f4; border: 1px solid #45475a; }
QMenu::item:selected { background: #45475a; }
QDialog { background: #1e1e2e; color: #cdd6f4; }
QLabel { color: #cdd6f4; }
"""


def _make_camera_icon(size=20) -> QIcon:
    """Create a small camera icon via QPainter."""
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#89b4fa"))
    # Camera body
    p.drawRoundedRect(2, 5, size - 4, size - 8, 3, 3)
    # Lens
    p.setBrush(QColor("#1e1e2e"))
    cx, cy = size // 2, size // 2 + 1
    p.drawEllipse(cx - 4, cy - 4, 8, 8)
    p.setBrush(QColor("#89b4fa"))
    p.drawEllipse(cx - 2, cy - 2, 4, 4)
    # Flash bump
    p.setBrush(QColor("#89b4fa"))
    p.drawRect(size // 2 - 3, 3, 6, 3)
    p.end()
    return QIcon(pix)


class InjectDanaApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"LELEPAY - INJECTION v{APP_VERSION}")
        self.resize(1200, 800)

        # Set window icon - handle both frozen (EXE) and non-frozen (script) cases
        if getattr(sys, 'frozen', False):
            # Running as bundled EXE
            _base_path = sys._MEIPASS
        else:
            # Running as script
            _base_path = os.path.dirname(os.path.abspath(__file__))
        
        _icon_path = os.path.join(_base_path, "lelepay_logo_real.ico")
        if not os.path.isfile(_icon_path):
            _icon_path = os.path.join(_base_path, "lelepay_logo.ico")
        if os.path.isfile(_icon_path):
            self.setWindowIcon(QIcon(_icon_path))

        self.cfg = load_config()
        self.ui_q: queue.Queue = queue.Queue()
        self.requests: Dict[str, SuntikanRequest] = {}
        self.bank_workers: List[MyBcaTransferWorker] = []
        self.bank_queues: Dict[str, queue.Queue] = {}
        self.tg_worker: Optional[TelethonWorker] = None
        self._request_lock = threading.Lock()
        self._rr_index = 0  # Round-robin index for dispatch
        self._camera_icon = _make_camera_icon()

        self._build_gui()
        self._load_config_to_gui()
        # NOTE: Disabled local pending load - use "Tarik Request" button to fetch from Telegram
        # self._load_pending_requests()

        # Poll timer (replaces tk.after)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll_ui_queue)
        self._timer.start(100)

        # ===== Auto-Update Check (background) =====
        self._check_for_updates()

    def _check_for_updates(self):
        """Check for updates in background thread."""
        if not HAS_UPDATER:
            return
        
        def on_update_available(update_info):
            # Queue UI update to show dialog on main thread
            self.ui_q.put(("update_available", update_info))
        
        # Start background check
        checker = updater.UpdateChecker(APP_VERSION, callback=on_update_available)
        checker.start()

    def _show_update_dialog(self, update_info: dict):
        """Show update available dialog."""
        from PySide6.QtWidgets import QMessageBox, QProgressDialog
        
        version = update_info.get("version", "?")
        current = update_info.get("current", APP_VERSION)
        body = update_info.get("body", "")
        download_url = update_info.get("download_url")
        html_url = update_info.get("html_url", "")
        
        msg = QMessageBox(self)
        msg.setWindowTitle("Update Available")
        msg.setIcon(QMessageBox.Information)
        # Remove 'v' prefix if exists to avoid double 'v'
        ver_display = version.lstrip('v') if version.startswith('v') else version
        cur_display = current.lstrip('v') if str(current).startswith('v') else current
        msg.setText(f"Versi baru tersedia: v{ver_display}\n\nVersi saat ini: v{cur_display}")
        
        if body:
            # Truncate body if too long
            if len(body) > 500:
                body = body[:500] + "..."
            msg.setDetailedText(body)
        
        if download_url:
            msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No | QMessageBox.Ignore)
            msg.button(QMessageBox.Yes).setText("Download & Install")
            msg.button(QMessageBox.No).setText("Lihat di GitHub")
            msg.button(QMessageBox.Ignore).setText("Nanti Saja")
            msg.setDefaultButton(QMessageBox.Yes)
        else:
            msg.setStandardButtons(QMessageBox.Ok | QMessageBox.Ignore)
            msg.button(QMessageBox.Ok).setText("Lihat di GitHub")
            msg.button(QMessageBox.Ignore).setText("Nanti Saja")
        
        result = msg.exec()
        
        if result == QMessageBox.Yes and download_url:
            self._download_and_install_update(update_info)
        elif result == QMessageBox.No or result == QMessageBox.Ok:
            if html_url:
                import webbrowser
                webbrowser.open(html_url)

    def _download_and_install_update(self, update_info: dict):
        """Download and install update."""
        from PySide6.QtWidgets import QProgressDialog, QMessageBox
        
        if not HAS_UPDATER:
            return
        
        progress = QProgressDialog("Downloading update...", "Cancel", 0, 100, self)
        progress.setWindowTitle("Downloading Update")
        progress.setMinimumDuration(0)
        progress.setValue(0)
        
        # Download in separate thread to not block UI
        import threading
        download_result = {"path": None, "error": None}
        
        def do_download():
            def progress_callback(downloaded, total):
                if total > 0:
                    pct = int(downloaded * 100 / total)
                    self.ui_q.put(("update_progress", pct))
            
            try:
                path = updater.download_update(update_info, progress_callback=progress_callback)
                download_result["path"] = path
            except Exception as e:
                download_result["error"] = str(e)
            self.ui_q.put(("update_download_done", download_result))
        
        threading.Thread(target=do_download, daemon=True).start()
        
        # Store progress dialog for queue handler to update
        self._update_progress_dlg = progress
        progress.show()

    # ----------------------------------------
    #  BUILD GUI
    # ----------------------------------------
    def _build_gui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root_lay = QVBoxLayout(central)
        root_lay.setContentsMargins(4, 4, 4, 4)

        tabs = QTabWidget()
        root_lay.addWidget(tabs)
        page_main = QWidget()
        page_config = QWidget()
        tabs.addTab(page_main, "  MAIN  ")
        tabs.addTab(page_config, "  CONFIG  ")

        # -- MAIN TAB --
        main_lay = QHBoxLayout(page_main)
        splitter = QSplitter(Qt.Horizontal)
        main_lay.addWidget(splitter)

        left = QWidget()
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(4, 4, 4, 4)
        left.setMinimumWidth(750)  # Minimal lebar supaya tombol action tetap terlihat
        right = QWidget()
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(4, 4, 4, 4)
        right.setMinimumWidth(250)  # Minimal lebar log panel
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([700, 450])
        splitter.setCollapsible(0, False)  # Left panel tidak bisa di-collapse
        splitter.setCollapsible(1, False)  # Right panel tidak bisa di-collapse

        # -- Controls --
        ctrl = QGroupBox("Control")
        ctrl_lay = QHBoxLayout(ctrl)
        left_lay.addWidget(ctrl)

        self.btn_start = QPushButton("Start")
        self.btn_start.setObjectName("startBtn")
        self.btn_start.clicked.connect(self.start_all)
        ctrl_lay.addWidget(self.btn_start)

        self.btn_stop = QPushButton("Stop")
        self.btn_stop.setObjectName("stopBtn")
        self.btn_stop.clicked.connect(self.stop_all)
        self.btn_stop.setEnabled(False)
        ctrl_lay.addWidget(self.btn_stop)

        btn_save = QPushButton("Save")
        btn_save.setObjectName("saveBtn")
        btn_save.clicked.connect(self._save_gui_to_config)
        ctrl_lay.addWidget(btn_save)

        ctrl_lay.addSpacing(20)
        ctrl_lay.addWidget(QLabel("TG:"))
        self.lbl_tg = QLabel("Offline")
        self.lbl_tg.setStyleSheet("color: gray; font-weight: bold;")
        ctrl_lay.addWidget(self.lbl_tg)
        ctrl_lay.addStretch()

        # -- Bank Table --
        grp_bank = QGroupBox("Bank (myBCA HP)")
        grp_bank_lay = QVBoxLayout(grp_bank)
        left_lay.addWidget(grp_bank)

        self.tbl_banks = QTableWidget(0, 5)
        self.tbl_banks.setHorizontalHeaderLabels(["Device", "Nama", "Rekening", "Saldo", "Status"])
        self.tbl_banks.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_banks.setMaximumHeight(140)
        self.tbl_banks.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl_banks.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl_banks.verticalHeader().setVisible(False)
        # Enable right-click context menu
        self.tbl_banks.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tbl_banks.customContextMenuRequested.connect(self._show_bank_context_menu)
        grp_bank_lay.addWidget(self.tbl_banks)

        # -- Request Table --
        grp_req = QGroupBox("Request Suntikan")
        grp_req_lay = QVBoxLayout(grp_req)
        left_lay.addWidget(grp_req, stretch=1)

        self.tbl_req = QTableWidget(0, 12)
        self.tbl_req.setHorizontalHeaderLabels(
            ["Time", "Nama", "Bank", "No Rek", "Nominal", "Asset", "Status", "Bank Used", "SS", "P", "R", "X"]
        )
        self.tbl_req.setMinimumWidth(720)  # Minimal lebar tabel
        hdr = self.tbl_req.horizontalHeader()
        #                    Time  Nama  Bank  NoRek  Nominal Asset Status BankUsed  ??   ?   ?   ?
        for i, w in enumerate([48,  140,   42,   90,    85,    55,   65,   120,     28,  28,  28,  28]):
            self.tbl_req.setColumnWidth(i, w)
        hdr.setStretchLastSection(False)
        # Semua kolom data (0-7) Interactive - bisa di-resize manual
        for col in range(8):
            hdr.setSectionResizeMode(col, QHeaderView.Interactive)
        # Action columns (8-11) fixed width
        for col in [8, 9, 10, 11]:
            hdr.setSectionResizeMode(col, QHeaderView.Fixed)
        self.tbl_req.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.tbl_req.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl_req.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl_req.verticalHeader().setVisible(False)
        self.tbl_req.cellClicked.connect(self._on_req_cell_clicked)
        grp_req_lay.addWidget(self.tbl_req)

        # -- Right: status + log --
        self.lbl_status = QLabel("Idle.")
        self.lbl_status.setStyleSheet(
            "background: #313244; color: #cdd6f4; padding: 6px 10px; border-radius: 4px; font-weight: bold; font-size: 11pt;"
        )
        right_lay.addWidget(self.lbl_status)

        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setFont(QFont("Consolas", 9, QFont.Bold))
        right_lay.addWidget(self.txt_log)

        # -- TG Profile (bottom of right sidebar) --
        self.tg_profile_widget = QWidget()
        tg_prof_lay = QHBoxLayout(self.tg_profile_widget)
        tg_prof_lay.setContentsMargins(8, 8, 8, 8)
        self.tg_profile_widget.setStyleSheet(
            "background: #181825; border-radius: 8px; border: 1px solid #313244;"
        )

        # Avatar (circular)
        self.lbl_tg_avatar = QLabel()
        self.lbl_tg_avatar.setFixedSize(42, 42)
        self._set_default_avatar()
        tg_prof_lay.addWidget(self.lbl_tg_avatar)

        # Name + username
        tg_info_lay = QVBoxLayout()
        tg_info_lay.setSpacing(1)
        self.lbl_tg_name = QLabel("Offline")
        self.lbl_tg_name.setStyleSheet(
            "color: #cdd6f4; font-weight: bold; font-size: 11pt; border: none; background: transparent;"
        )
        tg_info_lay.addWidget(self.lbl_tg_name)
        self.lbl_tg_username = QLabel("Telegram belum terhubung")
        self.lbl_tg_username.setStyleSheet(
            "color: #6c7086; font-size: 9pt; border: none; background: transparent;"
        )
        tg_info_lay.addWidget(self.lbl_tg_username)
        tg_prof_lay.addLayout(tg_info_lay)
        tg_prof_lay.addStretch()

        # Online indicator dot
        self.lbl_tg_dot = QLabel("\u25cf")
        self.lbl_tg_dot.setStyleSheet("color: #585b70; font-size: 14pt; border: none; background: transparent;")
        tg_prof_lay.addWidget(self.lbl_tg_dot)

        self.tg_profile_widget.setFixedHeight(62)
        right_lay.addWidget(self.tg_profile_widget)

        # -- CONFIG TAB --
        cfg_lay = QVBoxLayout(page_config)
        cfg_lay.setContentsMargins(16, 16, 16, 16)

        # Telegram Login
        grp_tg = QGroupBox("Telegram Login")
        tg_main_lay = QVBoxLayout(grp_tg)
        cfg_lay.addWidget(grp_tg)
        
        # Row 1: Status + Logout
        tg_lay = QHBoxLayout()
        tg_main_lay.addLayout(tg_lay)

        self.lbl_tg_login = QLabel("Belum login")
        self.lbl_tg_login.setStyleSheet("color: gray; font-size: 11pt;")
        tg_lay.addWidget(self.lbl_tg_login)
        tg_lay.addStretch()

        btn_logout = QPushButton("Logout")
        btn_logout.setStyleSheet("color: #f38ba8; border: 1px solid #f38ba8; padding: 4px 14px;")
        btn_logout.clicked.connect(self._tg_logout)
        tg_lay.addWidget(btn_logout)
        
        # Phone number field (hidden - only used internally if needed)
        self.ent_phone = QLineEdit()
        self.ent_phone.setVisible(False)

        # Bank Accounts
        grp_ba = QGroupBox("Bank Accounts (myBCA HP)")
        ba_lay = QVBoxLayout(grp_ba)
        cfg_lay.addWidget(grp_ba, stretch=1)

        ba_btn_row = QHBoxLayout()
        ba_lay.addLayout(ba_btn_row)
        btn_add = QPushButton("+ Tambah")
        btn_add.clicked.connect(self._bank_add)
        ba_btn_row.addWidget(btn_add)
        btn_edit = QPushButton("Edit")
        btn_edit.clicked.connect(self._bank_edit)
        ba_btn_row.addWidget(btn_edit)
        btn_remove = QPushButton("Hapus")
        btn_remove.clicked.connect(self._bank_remove)
        ba_btn_row.addWidget(btn_remove)
        ba_btn_row.addStretch()

        self.tbl_bank_cfg = QTableWidget(0, 5)
        self.tbl_bank_cfg.setHorizontalHeaderLabels(["Device ID", "Nama Akun", "No Rekening", "Password", "PIN"])
        self.tbl_bank_cfg.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_bank_cfg.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl_bank_cfg.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl_bank_cfg.verticalHeader().setVisible(False)
        ba_lay.addWidget(self.tbl_bank_cfg)

        # Options
        grp_opt = QGroupBox("Options")
        opt_lay = QVBoxLayout(grp_opt)
        cfg_lay.addWidget(grp_opt)
        self.chk_auto = QCheckBox("Auto Process (otomatis transfer tanpa konfirmasi - HATI-HATI!)")
        opt_lay.addWidget(self.chk_auto)
        row_b = QHBoxLayout()
        opt_lay.addLayout(row_b)
        row_b.addWidget(QLabel("Biaya BI-FAST:"))
        self.ent_biaya_bifast = QLineEdit("2500")
        self.ent_biaya_bifast.setMaximumWidth(80)
        row_b.addWidget(self.ent_biaya_bifast)
        row_b.addSpacing(12)
        row_b.addWidget(QLabel("Biaya Real Time:"))
        self.ent_biaya_realtime = QLineEdit("6500")
        self.ent_biaya_realtime.setMaximumWidth(80)
        row_b.addWidget(self.ent_biaya_realtime)
        row_b.addStretch()

        btn_save_cfg = QPushButton("Save Config")
        btn_save_cfg.setObjectName("saveBtn")
        btn_save_cfg.clicked.connect(self._save_gui_to_config)
        cfg_lay.addWidget(btn_save_cfg, alignment=Qt.AlignCenter)

        # Internal: store bank data list (mirrors tbl_bank_cfg)
        self._bank_data: List[dict] = []

    # ----------------------------------------
    #  TG AVATAR helpers
    # ----------------------------------------
    def _set_default_avatar(self):
        """Draw a default gray circle with user icon."""
        size = 42
        pix = QPixmap(size, size)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor("#45475a"))
        p.setPen(Qt.NoPen)
        p.drawEllipse(0, 0, size, size)
        # Simple user silhouette
        p.setBrush(QColor("#6c7086"))
        p.drawEllipse(size // 2 - 7, 8, 14, 14)  # head
        p.drawEllipse(size // 2 - 12, 24, 24, 16)  # body
        p.end()
        self.lbl_tg_avatar.setPixmap(pix)

    def _set_tg_avatar(self, photo_path: str):
        """Load a photo file and render it as a circular avatar."""
        size = 42
        src = QPixmap(photo_path)
        if src.isNull():
            self._set_default_avatar()
            return
        # Scale to square
        src = src.scaled(size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        # Crop center
        if src.width() > size or src.height() > size:
            x = (src.width() - size) // 2
            y = (src.height() - size) // 2
            src = src.copy(x, y, size, size)
        # Clip to circle
        result = QPixmap(size, size)
        result.fill(Qt.transparent)
        p = QPainter(result)
        p.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addEllipse(0, 0, size, size)
        p.setClipPath(path)
        p.drawPixmap(0, 0, src)
        # Draw border ring
        p.setClipping(False)
        p.setPen(QColor("#89b4fa"))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(1, 1, size - 2, size - 2)
        p.end()
        self.lbl_tg_avatar.setPixmap(result)

    def _set_tg_profile(self, name: str, username: str, photo_path: str = ""):
        """Update the TG profile sidebar widget."""
        self.lbl_tg_name.setText(name or "Unknown")
        self.lbl_tg_username.setText(f"@{username}" if username else "Telegram")
        self.lbl_tg_dot.setStyleSheet("color: #a6e3a1; font-size: 14pt; border: none; background: transparent;")
        if photo_path and os.path.exists(photo_path):
            self._set_tg_avatar(photo_path)
        else:
            # Draw initials avatar
            self._set_initials_avatar(name)

    def _set_initials_avatar(self, name: str):
        """Draw a colored circle with initials."""
        size = 42
        parts = name.strip().split()
        initials = ""
        if parts:
            initials = parts[0][0].upper()
            if len(parts) > 1:
                initials += parts[-1][0].upper()
        if not initials:
            initials = "?"

        # Deterministic color from name
        colors = ["#89b4fa", "#a6e3a1", "#fab387", "#f38ba8", "#cba6f7", "#94e2d5", "#f9e2af", "#74c7ec"]
        cidx = sum(ord(c) for c in name) % len(colors) if name else 0

        pix = QPixmap(size, size)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor(colors[cidx]))
        p.setPen(Qt.NoPen)
        p.drawEllipse(0, 0, size, size)
        p.setPen(QColor("#1e1e2e"))
        p.setFont(QFont("Segoe UI", 15, QFont.Bold))
        from PySide6.QtCore import QRect
        p.drawText(QRect(0, 0, size, size), Qt.AlignCenter, initials)
        p.end()
        self.lbl_tg_avatar.setPixmap(pix)

    # ----------------------------------------
    #  BANK ACCOUNT DIALOG
    # ----------------------------------------
    def _bank_dialog(self, title="Tambah Bank", data=None) -> Optional[dict]:
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.setMinimumWidth(420)
        lay = QFormLayout(dlg)

        fields = [
            ("Device ID", "device_id", False),
            ("Nama Akun", "name", False),
            ("No Rekening", "rekening", False),
            ("Password", "password", True),
            ("PIN", "pin", True),
        ]
        entries: Dict[str, QLineEdit] = {}
        for label, key, secret in fields:
            ent = QLineEdit()
            ent.setFont(QFont("Consolas", 10))
            if secret:
                ent.setEchoMode(QLineEdit.Password)
            if data and key in data:
                ent.setText(data[key])
            entries[key] = ent
            lay.addRow(label + ":", ent)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        lay.addRow(buttons)

        result = {}

        def on_ok():
            did = entries["device_id"].text().strip()
            if not did:
                QMessageBox.warning(dlg, "Warning", "Device ID wajib diisi!")
                return
            for key in entries:
                result[key] = entries[key].text().strip()
            dlg.accept()

        buttons.accepted.connect(on_ok)
        buttons.rejected.connect(dlg.reject)

        if dlg.exec() == QDialog.Accepted:
            return result
        return None

    def _bank_add(self):
        data = self._bank_dialog("Tambah Bank")
        if data:
            self._bank_data.append(data)
            self._refresh_bank_cfg_table()
            self._save_gui_to_config()
            self._log(f"Bank ditambah: {data.get('name','')} ({data.get('device_id','')})")

    def _bank_edit(self):
        row = self.tbl_bank_cfg.currentRow()
        if row < 0 or row >= len(self._bank_data):
            QMessageBox.information(self, "Info", "Pilih bank yang mau diedit.")
            return
        old = self._bank_data[row]
        data = self._bank_dialog("Edit Bank", old)
        if data:
            self._bank_data[row] = data
            self._refresh_bank_cfg_table()
            self._save_gui_to_config()
            self._log(f"Bank diedit: {data.get('name','')} ({data.get('device_id','')})")

    def _bank_remove(self):
        row = self.tbl_bank_cfg.currentRow()
        if row < 0 or row >= len(self._bank_data):
            QMessageBox.information(self, "Info", "Pilih bank yang mau dihapus.")
            return
        name = self._bank_data[row].get("name", "")
        did = self._bank_data[row].get("device_id", "")
        if QMessageBox.question(self, "Konfirmasi", f"Hapus bank '{name}' ({did})?") == QMessageBox.Yes:
            self._bank_data.pop(row)
            self._refresh_bank_cfg_table()
            self._save_gui_to_config()
            self._log(f"Bank dihapus: {name} ({did})")

    def _refresh_bank_cfg_table(self):
        self.tbl_bank_cfg.setRowCount(0)
        for b in self._bank_data:
            r = self.tbl_bank_cfg.rowCount()
            self.tbl_bank_cfg.insertRow(r)
            self.tbl_bank_cfg.setItem(r, 0, QTableWidgetItem(b.get("device_id", "")))
            self.tbl_bank_cfg.setItem(r, 1, QTableWidgetItem(b.get("name", "")))
            self.tbl_bank_cfg.setItem(r, 2, QTableWidgetItem(b.get("rekening", "")))
            self.tbl_bank_cfg.setItem(r, 3, QTableWidgetItem("*" * min(len(b.get("password", "")), 8)))
            self.tbl_bank_cfg.setItem(r, 4, QTableWidgetItem("*" * min(len(b.get("pin", "")), 6)))

    # ----------------------------------------
    #  CONFIG LOAD / SAVE
    # ----------------------------------------
    def _load_config_to_gui(self):
        self.ent_phone.setText(self.cfg.get("phone", ""))
        self.chk_auto.setChecked(self.cfg.get("auto_process", False))
        self.ent_biaya_bifast.setText(str(self.cfg.get("biaya_bifast", 2500)))
        self.ent_biaya_realtime.setText(str(self.cfg.get("biaya_realtime", 6500)))
        self._bank_data = list(self.cfg.get("banks", []))
        self._refresh_bank_cfg_table()
        if self.cfg.get("session_string"):
            self.lbl_tg_login.setText("[OK] Session tersimpan (auto-login saat Start)")
            self.lbl_tg_login.setStyleSheet("color: #a6e3a1; font-weight: bold; font-size: 11pt;")
        else:
            self.lbl_tg_login.setText("Belum login - Klik Start untuk scan QR")
            self.lbl_tg_login.setStyleSheet("color: #f9e2af; font-size: 11pt;")

    def _save_gui_to_config(self):
        self.cfg["phone"] = self.ent_phone.text().strip()
        self.cfg["auto_process"] = self.chk_auto.isChecked()
        try:
            self.cfg["biaya_bifast"] = int(self.ent_biaya_bifast.text().strip())
        except ValueError:
            self.cfg["biaya_bifast"] = 2500
        try:
            self.cfg["biaya_realtime"] = int(self.ent_biaya_realtime.text().strip())
        except ValueError:
            self.cfg["biaya_realtime"] = 6500
        self.cfg["banks"] = list(self._bank_data)
        save_config(self.cfg)
        self._log("Config saved!")

    def _load_pending_requests(self):
        """Load pending requests from file and display in table."""
        pending = load_pending_requests()
        if pending:
            self._log(f"Loading {len(pending)} pending request(s) dari file...")
            with self._request_lock:
                for req in pending:
                    self.requests[req.request_id] = req
                    self._add_request_to_table(req)
            self._log(f"Loaded {len(pending)} pending request(s)")

    def _save_pending_requests(self):
        """Save current requests to file."""
        with self._request_lock:
            save_pending_requests(self.requests)

    def _tg_logout(self):
        """Clear Telegram session and reset login status."""
        if QMessageBox.question(self, "Logout Telegram",
                                "Hapus session Telegram?\nPerlu scan QR lagi saat Start.") != QMessageBox.Yes:
            return
        self.cfg["session_string"] = ""
        save_config(self.cfg)
        self.lbl_tg_login.setText("Logged out - Klik Start untuk scan QR")
        self.lbl_tg_login.setStyleSheet("color: #f9e2af; font-size: 11pt;")
        # Reset sidebar profile
        self.lbl_tg_name.setText("Offline")
        self.lbl_tg_username.setText("Telegram belum terhubung")
        self.lbl_tg_dot.setStyleSheet("color: #585b70; font-size: 14pt; border: none; background: transparent;")
        self._set_default_avatar()
        self._log("Telegram session cleared (logged out)")

    # ----------------------------------------
    #  LOGGING
    # ----------------------------------------
    def _log(self, msg):
        ts = time.strftime("%H:%M:%S")
        full = f"[{ts}] {msg}"
        self.txt_log.append(full)
        sb = self.txt_log.verticalScrollBar()
        sb.setValue(sb.maximum())

    # ----------------------------------------
    #  REQUEST TABLE helpers
    # ----------------------------------------
    def _find_req_row(self, rid: str) -> int:
        for r in range(self.tbl_req.rowCount()):
            item = self.tbl_req.item(r, 0)
            if item and item.data(Qt.UserRole) == rid:
                return r
        return -1

    def _color_for_status(self, status: str) -> QColor:
        s = status.lower()
        if "sukses" in s:
            return QColor("#a6e3a1")
        if "gagal" in s or "batal" in s:
            return QColor("#f38ba8")
        if "progress" in s:
            return QColor("#fab387")
        if "big amount" in s:
            return QColor("#f9e2af")  # yellow for big amount
        return QColor("#89b4fa")  # pending

    def _add_request_to_table(self, req: SuntikanRequest):
        r = 0  # insert at top
        self.tbl_req.insertRow(r)
        ts = req.timestamp.split(" ")[-1][:5] if " " in req.timestamp else req.timestamp
        vals = [ts, req.nama_bank[:20], req.jenis_bank, req.no_rek,
                f"Rp {req.nominal:,}", req.asset_web[:8], req.status, req.bank_used]
        color = self._color_for_status(req.status)
        for c, v in enumerate(vals):
            item = QTableWidgetItem(v)
            item.setForeground(color)
            if c == 0:
                item.setData(Qt.UserRole, req.request_id)  # store rid
            self.tbl_req.setItem(r, c, item)
        # Screenshot column (camera icon button)
        ss_item = QTableWidgetItem()
        ss_item.setIcon(self._camera_icon)
        ss_item.setToolTip("Klik untuk buka screenshot")
        ss_item.setTextAlignment(Qt.AlignCenter)
        ss_item.setData(Qt.UserRole + 1, "")  # will store screenshot path
        self.tbl_req.setItem(r, 8, ss_item)
        
        # Action columns
        # Proses button
        proses_item = QTableWidgetItem("P")
        proses_item.setTextAlignment(Qt.AlignCenter)
        proses_item.setForeground(QColor("#a6e3a1"))
        proses_item.setToolTip("Proses Transfer")
        self.tbl_req.setItem(r, 9, proses_item)
        
        # Retry button
        retry_item = QTableWidgetItem("R")
        retry_item.setTextAlignment(Qt.AlignCenter)
        retry_item.setForeground(QColor("#f9e2af"))
        retry_item.setToolTip("Retry")
        self.tbl_req.setItem(r, 10, retry_item)
        
        # Batal button
        batal_item = QTableWidgetItem("X")
        batal_item.setTextAlignment(Qt.AlignCenter)
        batal_item.setForeground(QColor("#f38ba8"))
        batal_item.setToolTip("Batalkan")
        self.tbl_req.setItem(r, 11, batal_item)

    def _update_request_in_table(self, req=None, rid="", status="", bank_used=""):
        if req:
            rid = req.request_id
            status = req.status
            bank_used = req.bank_used
        row = self._find_req_row(rid)
        if row < 0:
            return
        color = self._color_for_status(status)
        if status:
            item = self.tbl_req.item(row, 6)
            if item:
                item.setText(status)
                item.setForeground(color)
        if bank_used:
            item = self.tbl_req.item(row, 7)
            if item:
                item.setText(bank_used)
        # Update all column colors (except action columns 8-11)
        for c in range(self.tbl_req.columnCount()):
            item = self.tbl_req.item(row, c)
            if item and c not in [8, 9, 10, 11]:
                item.setForeground(color)

    def _update_screenshot_in_table(self, rid: str, ss_path: str):
        row = self._find_req_row(rid)
        if row < 0:
            return
        item = self.tbl_req.item(row, 8)
        if item:
            item.setData(Qt.UserRole + 1, ss_path)
            if ss_path:
                item.setToolTip(f"[IMG] {os.path.basename(ss_path)}\nKlik untuk buka")

    def _on_req_cell_clicked(self, row, col):
        # Col 8 = Screenshot
        if col == 8:
            item = self.tbl_req.item(row, 8)
            if not item:
                return
            ss_path = item.data(Qt.UserRole + 1)
            if ss_path and os.path.exists(ss_path):
                os.startfile(ss_path)
            else:
                # Get rid and check request
                item0 = self.tbl_req.item(row, 0)
                if item0:
                    rid = item0.data(Qt.UserRole)
                    with self._request_lock:
                        req = self.requests.get(rid)
                    if req and req.screenshot_path and os.path.exists(req.screenshot_path):
                        os.startfile(req.screenshot_path)
                    else:
                        self._log("Screenshot tidak tersedia")
            return
        
        # Col 9 = Proses
        if col == 9:
            self.tbl_req.selectRow(row)
            self._manual_proses()
            return
        
        # Col 10 = Retry
        if col == 10:
            self.tbl_req.selectRow(row)
            self._manual_retry()
            return
        
        # Col 11 = Batal
        if col == 11:
            self.tbl_req.selectRow(row)
            self._manual_batal()
            return

    # ----------------------------------------
    #  BANK TABLE helpers
    # ----------------------------------------
    def _show_bank_context_menu(self, pos):
        """Show context menu on right-click for bank table."""
        row = self.tbl_banks.rowAt(pos.y())
        if row < 0:
            return
        
        # Get device info
        item0 = self.tbl_banks.item(row, 0)
        item4 = self.tbl_banks.item(row, 4)  # Status column
        if not item0:
            return
        
        did = item0.data(Qt.UserRole)
        status = item4.text() if item4 else ""
        name_item = self.tbl_banks.item(row, 1)
        name = name_item.text() if name_item else did
        
        menu = QMenu(self)
        
        # Remove from table action
        act_remove = QAction(f"Hapus {name} dari tabel", self)
        act_remove.triggered.connect(lambda: self._remove_bank_from_runtime(did, row))
        menu.addAction(act_remove)
        
        menu.exec(self.tbl_banks.viewport().mapToGlobal(pos))

    def _remove_bank_from_runtime(self, device_id: str, row: int):
        """Remove a bank from runtime table (not from config)."""
        # Stop and remove worker if exists
        worker_to_remove = None
        for w in self.bank_workers:
            if w.device_id == device_id:
                worker_to_remove = w
                break
        
        if worker_to_remove:
            worker_to_remove.stop()
            self.bank_workers.remove(worker_to_remove)
        
        # Remove from queue dict
        self.bank_queues.pop(device_id, None)
        
        # Remove from table
        self.tbl_banks.removeRow(row)
        
        # Update status
        active_count = len([w for w in self.bank_workers if w.is_alive()])
        self.lbl_status.setText(f"Running \u25c6 {active_count} bank(s)")
        
        self._log(f"Bank dihapus dari runtime: {device_id[-8:]}")

    def _find_bank_row(self, device_id: str) -> int:
        for r in range(self.tbl_banks.rowCount()):
            item = self.tbl_banks.item(r, 0)
            if item and item.data(Qt.UserRole) == device_id:
                return r
        return -1

    def _add_bank_to_table(self, did: str, name: str, rek: str, saldo: str = "-", status: str = "Starting..."):
        r = self.tbl_banks.rowCount()
        self.tbl_banks.insertRow(r)
        items_data = [did[-12:], name, rek, saldo, status]
        for c, v in enumerate(items_data):
            item = QTableWidgetItem(v)
            if c == 0:
                item.setData(Qt.UserRole, did)
            self.tbl_banks.setItem(r, c, item)

    def _update_bank_in_table(self, did: str, field: str, value: str):
        row = self._find_bank_row(did)
        if row < 0:
            return
        col_map = {"saldo": 3, "status": 4}
        col = col_map.get(field)
        if col is not None:
            item = self.tbl_banks.item(row, col)
            if item:
                item.setText(value)

    def _manual_proses(self):
        row = self.tbl_req.currentRow()
        if row < 0:
            self._log("Pilih request dulu!")
            return
        item0 = self.tbl_req.item(row, 0)
        if not item0:
            return
        rid = item0.data(Qt.UserRole)
        with self._request_lock:
            req = self.requests.get(rid)
        if req and req.status in ("Pending", "Big Amount"):
            # Force dispatch even for Big Amount
            req.status = "Pending"  # Reset to Pending so _dispatch_request will process
            # Temporarily bypass big amount check
            device = self._find_best_bank(req)
            if not device:
                if self.bank_queues:
                    best_did = None
                    best_qsize = float('inf')
                    for w in self.bank_workers:
                        if not w.is_alive():
                            continue
                        if w.current_saldo > 0 and w.current_saldo < req.nominal:
                            continue
                        if w.job_q.qsize() < best_qsize:
                            best_qsize = w.job_q.qsize()
                            best_did = w.device_id
                    if not best_did:
                        self._log(f"[{rid}] Semua bank saldo tidak cukup")
                        return
                    device = best_did
                else:
                    self._log(f"[{rid}] No bank available!")
                    return
            if device in self.bank_queues:
                self.bank_queues[device].put(req)
                bname = device
                for w in self.bank_workers:
                    if w.device_id == device:
                        bname = w.bank_name or device
                        break
                req.status = "Dispatched"
                self._update_request_in_table(rid=req.request_id, status="Dispatched", bank_used=bname)
                self._log(f"[{req.request_id}] Manual dispatch -> {bname}")
        elif req:
            self._log(f"[{rid}] Tidak bisa diproses (status: {req.status})")

    def _manual_batal(self):
        row = self.tbl_req.currentRow()
        if row < 0:
            self._log("Pilih request dulu!")
            return
        item0 = self.tbl_req.item(row, 0)
        if not item0:
            return
        rid = item0.data(Qt.UserRole)
        with self._request_lock:
            req = self.requests.get(rid)
        if not req:
            self._log(f"Request {rid} tidak ditemukan")
            return
        
        status_lower = req.status.lower()
        
        # Pending - langsung batal
        if req.status == "Pending":
            req.status = "Batal"
            self._update_request_in_table(rid=rid, status="Batal")
            self._log(f"[{rid}] Dibatalkan")
            return
        
        # Dispatched atau In Progress - bisa force cancel
        if "dispatched" in status_lower or "progress" in status_lower:
            reply = QMessageBox.question(
                self, "Force Cancel",
                f"Request {rid} sedang {req.status}.\n\n"
                f"Force cancel akan:\n"
                f"- Set status ke 'Gagal (Force)'\n"
                f"- Hapus dari antrian worker\n\n"
                f"Lanjutkan?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                # Remove from all workers
                for w in self.bank_workers:
                    w._inflight.discard(rid)
                    w._done.discard(rid)
                req.status = "Gagal (Force)"
                self._update_request_in_table(rid=rid, status="Gagal (Force)")
                self._log(f"[{rid}] Force cancelled - status: Gagal (Force)")
            return
        
        # Sukses - tidak bisa dibatalkan
        if req.status == "Sukses":
            self._log(f"[{rid}] Sudah Sukses, tidak bisa dibatalkan")
            return
        
        # Status lain (Gagal, Batal, etc) - tidak perlu cancel
        self._log(f"[{rid}] Status '{req.status}' - tidak perlu dibatalkan")

    def _manual_retry(self):
        """Retry failed request."""
        row = self.tbl_req.currentRow()
        if row < 0:
            self._log("Pilih request dulu!")
            return
        item0 = self.tbl_req.item(row, 0)
        if not item0:
            return
        rid = item0.data(Qt.UserRole)
        with self._request_lock:
            req = self.requests.get(rid)
        if not req:
            self._log(f"Request {rid} tidak ditemukan")
            return
        
        # Allow retry for various statuses (case insensitive check)
        status_lower = req.status.lower()
        can_retry = (
            "gagal" in status_lower or 
            "batal" in status_lower or 
            "timeout" in status_lower or 
            "error" in status_lower or
            "progress" in status_lower or  # stuck in progress
            req.status in ["Pending"]  # allow retry pending too
        )
        
        if req.status == "Sukses":
            self._log(f"[{rid}] Sudah Sukses, tidak perlu retry")
        elif can_retry:
            # Reset status and remove from done set on ALL workers
            for w in self.bank_workers:
                w._done.discard(rid)
                w._inflight.discard(rid)
            req.status = "Pending"
            self._update_request_in_table(rid=rid, status="Pending")
            self._log(f"[{rid}] Retry - status reset ke Pending")
            # Dispatch for processing
            self._dispatch_request(req)
        else:
            self._log(f"[{rid}] Status '{req.status}' tidak bisa di-retry")

    def _do_fetch_pending(self):
        """Background thread to fetch pending from Telegram."""
        if not self.tg_worker or not self.tg_worker._loop:
            return
        # Small delay to ensure loop is ready
        time.sleep(1)
        try:
            future = asyncio.run_coroutine_threadsafe(
                self.tg_worker.fetch_pending_requests(existing_reks=self._get_existing_reks()),
                self.tg_worker._loop
            )
            result = future.result(timeout=60)  # Wait up to 60s
            if result:
                self._log(f"Fetched {len(result)} request(s) dari Telegram")
        except Exception as e:
            self._log(f"Fetch error: {e}")

    def _get_existing_reks(self) -> set:
        """Get set of existing no_rek and message_ids in current requests."""
        with self._request_lock:
            reks = set()
            for req in self.requests.values():
                if req.no_rek:
                    reks.add(req.no_rek)
                if req.message_id:
                    reks.add(f"msg:{req.message_id}")
            return reks

    # ----------------------------------------
    #  START / STOP
    # ----------------------------------------
    def start_all(self):
        # Disable Start, enable Stop
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)

        self._save_gui_to_config()

        # Start Telethon
        if HAS_TELETHON and (self.cfg.get("api_id") and self.cfg.get("api_hash")):
            self.tg_worker = TelethonWorker(self.ui_q, self.cfg)
            self.tg_worker.start()
            self._log("Telegram connecting...")
        else:
            self._log("Telegram tidak distart (API ID/Hash kosong)")

        # Detect connected ADB devices
        connected_devices = set()
        try:
            out = subprocess.check_output(["adb", "devices"], timeout=10, stderr=subprocess.STDOUT, creationflags=SUBPROCESS_FLAGS).decode("utf-8", errors="ignore")
            for line in out.strip().split("\n")[1:]:
                parts = line.strip().split("\t")
                if len(parts) >= 2 and parts[1] == "device":
                    connected_devices.add(parts[0])
            self._log(f"ADB devices connected: {connected_devices or 'none'}")
        except Exception as e:
            self._log(f"ADB devices check failed: {e}, starting all from config")
            connected_devices = None

        # Start bank workers (only connected devices)
        skipped = []
        for bc in self.cfg.get("banks", []):
            did = bc.get("device_id", "")
            if not did:
                continue
            if connected_devices is not None and did not in connected_devices:
                skipped.append(f"{bc.get('name', '')} ({did[-8:]})")
                continue
            jq = queue.Queue()
            self.bank_queues[did] = jq
            w = MyBcaTransferWorker(self.ui_q, jq, did, bc.get("password", ""), bc.get("pin", ""),
                                    bc.get("name", ""), bc.get("rekening", ""),
                                    app=self)
            self.bank_workers.append(w)
            w.start()
            self._add_bank_to_table(did, bc.get("name", ""), bc.get("rekening", ""))

        if skipped:
            self._log(f"Skipped (not connected): {', '.join(skipped)}")
        self.lbl_status.setText(f"Running \u25c6 {len(self.bank_workers)} bank(s)")
        self._log(f"Started {len(self.bank_workers)} bank worker(s)")

        # Start periodic ADB hotplug scanner (detect newly connected devices)
        self._hotplug_timer = QTimer(self)
        self._hotplug_timer.timeout.connect(self._scan_for_new_devices)
        self._hotplug_timer.start(10_000)  # Every 10 seconds

    def _scan_for_new_devices(self):
        """Periodically check for newly plugged ADB devices and auto-start workers."""
        try:
            out = subprocess.check_output(
                ["adb", "devices"], timeout=10, stderr=subprocess.STDOUT, creationflags=SUBPROCESS_FLAGS
            ).decode("utf-8", errors="ignore")
            connected = set()
            for line in out.strip().split("\n")[1:]:
                parts = line.strip().split("\t")
                if len(parts) >= 2 and parts[1] == "device":
                    connected.add(parts[0])

            # Find configured banks whose device is connected but has no running worker
            active_devices = {w.device_id for w in self.bank_workers if w.is_alive()}
            for bc in self.cfg.get("banks", []):
                did = bc.get("device_id", "")
                if not did:
                    continue
                if did in active_devices:
                    continue  # Already running
                if did not in connected:
                    continue  # Not plugged in

                # New device detected! Start worker
                bname = bc.get('name', '') or did[-8:]
                self._log(f"[NEW] HP baru terdeteksi: {bname} ({did[-8:]}) - auto-starting...")
                jq = queue.Queue()
                self.bank_queues[did] = jq
                w = MyBcaTransferWorker(
                    self.ui_q, jq, did,
                    bc.get("password", ""), bc.get("pin", ""),
                    bc.get("name", ""), bc.get("rekening", ""),
                    app=self
                )
                self.bank_workers.append(w)
                w.start()
                self._add_bank_to_table(did, bc.get("name", ""), bc.get("rekening", ""))
                self.lbl_status.setText(f"Running \u25c6 {len(self.bank_workers)} bank(s)")
                # NOTE: Tidak langsung dispatch pending di sini.
                # Worker akan notify 'worker_ready' setelah login+saldo selesai,
                # lalu app dispatch pending requests ke worker yang sudah siap.

            # Clean up dead workers from the list
            dead = [w for w in self.bank_workers if not w.is_alive() and w._stop.is_set()]
            for w in dead:
                self.bank_workers.remove(w)
                self.bank_queues.pop(w.device_id, None)

        except Exception as e:
            print(f"[HOTPLUG] scan error: {e}")  # Log instead of silently ignoring

    def stop_all(self):
        # Stop hotplug scanner if running
        if hasattr(self, '_hotplug_timer') and self._hotplug_timer:
            self._hotplug_timer.stop()
            self._hotplug_timer = None
        if self.tg_worker:
            self.tg_worker.stop()
            self.tg_worker = None
        for w in self.bank_workers:
            w.stop()
        self.bank_workers.clear()
        self.bank_queues.clear()
        self.tbl_banks.setRowCount(0)
        self.lbl_tg.setText("Offline")
        self.lbl_tg.setStyleSheet("color: gray; font-weight: bold;")
        self.lbl_status.setText("Stopped.")
        # Enable Start, disable Stop
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        # Reset TG profile sidebar
        self.lbl_tg_name.setText("Offline")
        self.lbl_tg_username.setText("Telegram belum terhubung")
        self.lbl_tg_dot.setStyleSheet("color: #585b70; font-size: 14pt; border: none; background: transparent;")
        self._set_default_avatar()
        self._log("All stopped")

    # ----------------------------------------
    #  REQUEST DISPATCH
    # ----------------------------------------
    def _find_best_bank(self, req):
        """Find the best IDLE bank worker using round-robin across workers with enough saldo.
        HANYA return worker yang idle (tidak sedang proses transfer).
        Return None jika semua worker sedang sibuk - request tetap Pending."""
        # Ambil worker yang secara thread masih hidup + state ready
        alive = [w for w in self.bank_workers if w.is_alive() and not w._stop.is_set() and w._ready]
        if not alive:
            return None

        # HARD CHECK: verifikasi ADB real-time agar device yang baru disconnect tidak kepilih
        connected_ready = []
        for w in alive:
            try:
                if w._is_device_alive():
                    connected_ready.append(w)
                    continue

                # Sinkronkan state jika ternyata sudah disconnect
                w._ready = False
                w.current_saldo = 0
                self.ui_q.put(("update_bank", (w.device_id, "status", "Disconnected")))
                self.ui_q.put(("update_bank", (w.device_id, "saldo", "-")))
            except Exception:
                # Jika check gagal, anggap tidak aman untuk dispatch
                w._ready = False

        if not connected_ready:
            return None

        # Collect eligible workers (saldo cukup)
        eligible = [w for w in connected_ready if w.current_saldo >= req.nominal]
        if not eligible:
            return None

        # HANYA pilih worker yang IDLE (tidak ada job in-flight dan queue kosong)
        idle = [w for w in eligible if not w._inflight and w.job_q.qsize() == 0]
        if not idle:
            return None  # Semua worker sibuk, jangan dispatch

        # Round-robin across idle pool
        idx = self._rr_index % len(idle)
        chosen = idle[idx]
        self._rr_index += 1
        return chosen.device_id

    def _dispatch_request(self, req):
        # Skip jika sudah di-dispatch / sedang diproses / selesai
        if req.status not in ("Pending", "Gagal - Saldo"):
            return
        
        # Big Amount check - nominal > 20 juta tidak di-auto proses
        if req.nominal > BIG_AMOUNT_THRESHOLD:
            req.status = "Big Amount"
            self._update_request_in_table(rid=req.request_id, status="Big Amount")
            self._log(f"[{req.request_id}] Big Amount (Rp {req.nominal:,}) - klik manual untuk proses")
            return
        
        device = self._find_best_bank(req)
        if not device:
            # Tidak ada worker idle / saldo cukup - tetap Pending, akan di-dispatch saat worker selesai
            self._log(f"[{req.request_id}] Semua worker sibuk / saldo tidak cukup. Tetap Pending, tunggu worker idle...")
            return
        if device in self.bank_queues:
            self.bank_queues[device].put(req)
            bname = device
            for w in self.bank_workers:
                if w.device_id == device:
                    bname = w.bank_name or device
                    break
            req.status = "Dispatched"
            self._update_request_in_table(rid=req.request_id, status="Dispatched", bank_used=bname)
            self._log(f"[{req.request_id}] Dispatched -> {bname}")

    # ----------------------------------------
    #  OTP / 2FA / QR DIALOGS
    # ----------------------------------------
    def _show_qr_dialog(self, qr_png_data: bytes):
        """Show or update the QR code login dialog."""
        if hasattr(self, '_qr_dlg') and self._qr_dlg and self._qr_dlg.isVisible():
            # Update existing dialog with new QR
            pix = QPixmap()
            pix.loadFromData(qr_png_data)
            self._qr_lbl_img.setPixmap(pix)
            self._qr_lbl_status.setText("Scan QR code ini dari Telegram HP...")
            return

        self._qr_dlg = QDialog(self)
        self._qr_dlg.setWindowTitle("Login Telegram - Scan QR Code")
        self._qr_dlg.setMinimumWidth(380)
        lay = QVBoxLayout(self._qr_dlg)
        lay.setSpacing(12)

        # Title
        title = QLabel("Login Telegram")
        title.setStyleSheet("font-size: 16pt; font-weight: bold; color: #89b4fa;")
        title.setAlignment(Qt.AlignCenter)
        lay.addWidget(title)

        # Instructions
        instr = QLabel(
            "1. Buka Telegram di HP\n"
            "2. Buka Settings ? Devices ? Link Desktop Device\n"
            "3. Scan QR code di bawah ini"
        )
        instr.setStyleSheet("color: #a6adc8; font-size: 10pt;")
        instr.setAlignment(Qt.AlignCenter)
        lay.addWidget(instr)

        # QR Image
        self._qr_lbl_img = QLabel()
        self._qr_lbl_img.setAlignment(Qt.AlignCenter)
        pix = QPixmap()
        pix.loadFromData(qr_png_data)
        self._qr_lbl_img.setPixmap(pix)
        self._qr_lbl_img.setStyleSheet("background: #1e1e2e; border-radius: 8px; padding: 8px;")
        lay.addWidget(self._qr_lbl_img, alignment=Qt.AlignCenter)

        # Status
        self._qr_lbl_status = QLabel("Scan QR code ini dari Telegram HP...")
        self._qr_lbl_status.setStyleSheet("color: #f9e2af; font-size: 10pt;")
        self._qr_lbl_status.setAlignment(Qt.AlignCenter)
        lay.addWidget(self._qr_lbl_status)

        # Fallback button: use phone number instead
        btn_phone = QPushButton("Login pakai Nomor HP")
        btn_phone.setStyleSheet(
            "color: #6c7086; border: 1px solid #45475a; padding: 6px 12px; font-size: 9pt;"
        )
        def _fall_back_phone():
            if self.tg_worker:
                self.tg_worker.cancel_qr_login()
            self._qr_dlg.accept()
        btn_phone.clicked.connect(_fall_back_phone)
        lay.addWidget(btn_phone, alignment=Qt.AlignCenter)

        self._qr_dlg.setModal(False)  # non-blocking
        self._qr_dlg.show()

    def _close_qr_dialog(self):
        if hasattr(self, '_qr_dlg') and self._qr_dlg and self._qr_dlg.isVisible():
            self._qr_dlg.accept()
            self._qr_dlg = None

    def _show_otp_dialog(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Telegram OTP")
        dlg.setMinimumWidth(360)
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel("Masukkan kode OTP dari Telegram:"))
        ent = QLineEdit()
        ent.setFont(QFont("Consolas", 14))
        ent.setAlignment(Qt.AlignCenter)
        lay.addWidget(ent)
        btn = QPushButton("Submit")
        lay.addWidget(btn)

        def submit():
            code = ent.text().strip()
            if code and self.tg_worker:
                self.tg_worker.submit_otp(code)
                dlg.accept()

        btn.clicked.connect(submit)
        ent.returnPressed.connect(submit)
        dlg.exec()

    def _show_2fa_dialog(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Telegram 2FA")
        dlg.setMinimumWidth(360)
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel("Masukkan password 2FA:"))
        ent = QLineEdit()
        ent.setEchoMode(QLineEdit.Password)
        ent.setFont(QFont("Consolas", 12))
        lay.addWidget(ent)
        btn = QPushButton("Submit")
        lay.addWidget(btn)

        def submit():
            pwd = ent.text().strip()
            if pwd and self.tg_worker:
                self.tg_worker.submit_2fa(pwd)
                dlg.accept()

        btn.clicked.connect(submit)
        ent.returnPressed.connect(submit)
        dlg.exec()

    # ----------------------------------------
    #  UI QUEUE POLL  (100ms timer)
    # ----------------------------------------
    def _poll_ui_queue(self):
        try:
            for _ in range(50):
                try:
                    msg = self.ui_q.get_nowait()
                except queue.Empty:
                    break
                cmd = msg[0]

                if cmd == "log":
                    self._log(msg[1])

                elif cmd == "tg_status":
                    status = msg[1]
                    self.lbl_tg.setText(f"{status}")
                    self.lbl_tg.setStyleSheet("color: #a6e3a1; font-weight: bold;")
                    # Auto-fetch pending requests when connected
                    if status == "Connected":
                        self._log("Auto-fetching pending requests dari Telegram...")
                        threading.Thread(target=self._do_fetch_pending, daemon=True).start()

                elif cmd == "tg_logged_in":
                    self._close_qr_dialog()
                    self.lbl_tg.setText(f"{msg[1]}")
                    self.lbl_tg.setStyleSheet("color: #a6e3a1; font-weight: bold;")
                    self.lbl_tg_login.setText(f"Login sebagai: {msg[1]}")
                    self.lbl_tg_login.setStyleSheet("color: #a6e3a1; font-weight: bold; font-size: 11pt;")

                elif cmd == "tg_profile":
                    name, uname, photo = msg[1]
                    self._set_tg_profile(name, uname, photo)

                elif cmd == "tg_need_otp":
                    self._close_qr_dialog()
                    self._show_otp_dialog()

                elif cmd == "tg_need_2fa":
                    self._close_qr_dialog()
                    self._show_2fa_dialog()

                elif cmd == "tg_qr_code":
                    self._show_qr_dialog(msg[1])

                elif cmd == "tg_qr_close":
                    self._close_qr_dialog()

                elif cmd == "tg_need_login":
                    self._log(f"Login with phone: {msg[1]}")

                elif cmd == "new_request":
                    req = msg[1]
                    with self._request_lock:
                        self.requests[req.request_id] = req
                    self._add_request_to_table(req)
                    if self.chk_auto.isChecked() and self.bank_workers:
                        self._dispatch_request(req)

                elif cmd == "update_request":
                    rid, status, bank_used = msg[1]
                    self._update_request_in_table(rid=rid, status=status, bank_used=bank_used)
                    with self._request_lock:
                        if rid in self.requests:
                            self.requests[rid].status = status
                            if bank_used:
                                self.requests[rid].bank_used = bank_used

                elif cmd == "update_bank":
                    did, field, value = msg[1]
                    self._update_bank_in_table(did, field, value)

                elif cmd == "transfer_done":
                    req = msg[1]
                    self._log(f"[{req.request_id}] transfer_done received, launching post-transfer...")
                    # Update screenshot in table
                    if req.screenshot_path:
                        self._update_screenshot_in_table(req.request_id, req.screenshot_path)
                    if self.tg_worker and self.tg_worker._logged_in:
                        self._log(f"[{req.request_id}] TG logged in, starting post-transfer thread")
                        threading.Thread(target=self.tg_worker.do_post_transfer, args=(req,), daemon=True).start()
                    else:
                        self._log(f"[{req.request_id}] TG not ready (worker={self.tg_worker is not None}, logged_in={getattr(self.tg_worker, '_logged_in', False)})")

                elif cmd == "transfer_failed":
                    req = msg[1]
                    self._log(f"[{req.request_id}] Transfer failed: {req.status}")

                elif cmd == "requeue":
                    self._dispatch_request(msg[1])

                elif cmd == "worker_ready":
                    # Worker baru selesai login + saldo tersedia, dispatch pending requests
                    device_id = msg[1]
                    bname = device_id
                    for w in self.bank_workers:
                        if w.device_id == device_id:
                            bname = w.bank_name or device_id
                            break
                    self._log(f"[OK] {bname} siap terima job!")
                    # Dispatch SATU pending request saja ke worker yang baru ready
                    if self.chk_auto.isChecked():
                        with self._request_lock:
                            pending = [r for r in self.requests.values() if r.status == "Pending"]
                        if pending:
                            self._log(f"Worker ready, dispatch 1 dari {len(pending)} pending...")
                            self._dispatch_request(pending[0])

                elif cmd == "worker_idle":
                    # Worker selesai proses 1 job, dispatch SATU pending request saja
                    device_id = msg[1]
                    if self.chk_auto.isChecked():
                        with self._request_lock:
                            pending = [r for r in self.requests.values() if r.status in ("Pending", "Gagal - Saldo")]
                        if pending:
                            self._log(f"Worker idle, dispatch 1 dari {len(pending)} pending...")
                            self._dispatch_request(pending[0])

                # ===== AUTO-UPDATE HANDLERS =====
                elif cmd == "update_available":
                    update_info = msg[1]
                    ver = update_info.get('version', '?')
                    ver = ver.lstrip('v') if ver.startswith('v') else ver
                    self._log(f"[!] Update tersedia: v{ver}")
                    self._show_update_dialog(update_info)

                elif cmd == "update_progress":
                    pct = msg[1]
                    if hasattr(self, '_update_progress_dlg') and self._update_progress_dlg:
                        self._update_progress_dlg.setValue(pct)

                elif cmd == "update_download_done":
                    # Close progress dialog
                    if hasattr(self, '_update_progress_dlg') and self._update_progress_dlg:
                        self._update_progress_dlg.close()
                        self._update_progress_dlg = None
                    result = msg[1]
                    if result.get("path"):
                        self._log(f"[OK] Download selesai: {result['path']}")
                        reply = QMessageBox.question(
                            self, "Install Update",
                            "Download selesai!\n\nInstall sekarang?\n(Aplikasi akan restart)",
                            QMessageBox.Yes | QMessageBox.No
                        )
                        if reply == QMessageBox.Yes:
                            if HAS_UPDATER:
                                import sys
                                updater.apply_update(result["path"], sys.executable)
                                self.stop_all()
                                self.close()
                                QApplication.quit()
                                sys.exit(0)
                    else:
                        error = result.get("error", "Unknown error")
                        self._log(f"[X] Download gagal: {error}")
                        QMessageBox.warning(self, "Download Failed", f"Gagal download update:\n{error}")

        except Exception as e:
            print(f"[UI_Q] {e}")

    def closeEvent(self, event):
        self.stop_all()
        event.accept()


# ======================================================================
# MAIN
# ======================================================================
def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(DARK_QSS)
    window = InjectDanaApp()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
