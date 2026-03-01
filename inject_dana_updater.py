#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
INJECT DANA - Auto Updater
Checks GitHub releases for updates and downloads new version.
"""

import os
import sys
import json
import threading
import tempfile
import subprocess
import re
from typing import Optional, Tuple, Callable

# ===== Konfigurasi GitHub =====
# Repository: https://github.com/bon4r/lelepay-injectdana
# Cara upload release:
# 1. Buka https://github.com/bon4r/lelepay-injectdana/releases
# 2. Klik "Create a new release" atau "Draft a new release"
# 3. Tag: v3.1 (versi baru harus lebih tinggi dari v3.0)
# 4. Upload file INJECT_DANA.exe ke Release assets
# 5. Publish release
GITHUB_OWNER = "bon4r"
GITHUB_REPO = "lelepay-injectdana"
CURRENT_VERSION = "3.0"  # Akan diupdate dari app

# ===== Custom Server (Primary) =====
# Upload releases.json dan INJECT_DANA.exe ke VPS
VPS_BASE_URL = "http://178.128.87.151/releases"
VPS_RELEASES_JSON = f"{VPS_BASE_URL}/releases.json"

# GitHub API URLs (Fallback)
GITHUB_API_RELEASES = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"

# ===== HTTP Request (tanpa request library) =====
def _http_get(url: str, timeout: int = 10) -> Optional[dict]:
    """Simple HTTP GET request."""
    try:
        import requests
        resp = requests.get(url, timeout=timeout, headers={
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "INJECT_DANA_Updater"
        })
        if resp.status_code == 200:
            return resp.json()
        return None
    except Exception:
        return None


def _download_file(url: str, dest_path: str, progress_callback: Callable[[int, int], None] = None) -> bool:
    """Download file with progress callback."""
    try:
        import requests
        resp = requests.get(url, stream=True, timeout=60, headers={
            "User-Agent": "INJECT_DANA_Updater"
        })
        if resp.status_code != 200:
            return False
        
        total_size = int(resp.headers.get('content-length', 0))
        downloaded = 0
        
        with open(dest_path, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback:
                        progress_callback(downloaded, total_size)
        return True
    except Exception as e:
        print(f"[Updater] Download error: {e}")
        return False


def parse_version(version_str: str) -> Tuple[int, ...]:
    """Parse version string to tuple for comparison."""
    # Remove 'v' prefix if exists
    v = version_str.strip().lower()
    if v.startswith('v'):
        v = v[1:]
    
    # Extract numbers
    parts = re.findall(r'\d+', v)
    return tuple(int(p) for p in parts) if parts else (0,)


def _check_vps_for_update(current_version: str) -> Optional[dict]:
    """Check VPS server for updates (faster than GitHub)."""
    try:
        data = _http_get(VPS_RELEASES_JSON)
        if not data:
            return None
        
        latest_version = data.get("version", "")
        
        # Compare versions
        current_tuple = parse_version(current_version)
        latest_tuple = parse_version(latest_version)
        
        if latest_tuple > current_tuple:
            return {
                "version": latest_version,
                "current": current_version,
                "body": data.get("body", ""),
                "html_url": data.get("html_url", ""),
                "download_url": data.get("download_url"),
                "download_size": data.get("download_size", 0),
                "asset_name": data.get("asset_name", "INJECT_DANA.exe"),
            }
        return None
    except Exception as e:
        print(f"[Updater] VPS check error: {e}")
        return None


def _check_github_for_update(current_version: str) -> Optional[dict]:
    """Check GitHub releases for new version (fallback)."""
    try:
        data = _http_get(GITHUB_API_RELEASES)
        if not data:
            return None
        
        tag_name = data.get("tag_name", "")
        latest_version = tag_name
        
        # Compare versions
        current_tuple = parse_version(current_version)
        latest_tuple = parse_version(latest_version)
        
        if latest_tuple > current_tuple:
            # Find .exe asset
            assets = data.get("assets", [])
            exe_asset = None
            for asset in assets:
                name = (asset.get("name") or "").lower()
                if name.endswith(".exe"):
                    exe_asset = asset
                    break
            
            return {
                "version": latest_version,
                "current": current_version,
                "body": data.get("body", ""),
                "html_url": data.get("html_url", ""),
                "download_url": exe_asset.get("browser_download_url") if exe_asset else None,
                "download_size": exe_asset.get("size", 0) if exe_asset else 0,
                "asset_name": exe_asset.get("name") if exe_asset else None,
            }
        return None
    except Exception as e:
        print(f"[Updater] GitHub check error: {e}")
        return None


def check_for_update(current_version: str) -> Optional[dict]:
    """
    Check for new version. Tries VPS first (faster), falls back to GitHub.
    Returns dict with update info if available, None otherwise.
    """
    # Try VPS first (faster download)
    result = _check_vps_for_update(current_version)
    if result:
        print("[Updater] Update found on VPS server")
        return result
    
    # Fallback to GitHub
    result = _check_github_for_update(current_version)
    if result:
        print("[Updater] Update found on GitHub")
        return result
    
    return None


def download_update(update_info: dict, dest_folder: str = None, 
                    progress_callback: Callable[[int, int], None] = None) -> Optional[str]:
    """
    Download update .exe file.
    Returns path to downloaded file, or None if failed.
    """
    if not update_info or not update_info.get("download_url"):
        return None
    
    try:
        if not dest_folder:
            dest_folder = tempfile.gettempdir()
        
        filename = update_info.get("asset_name") or f"INJECT_DANA_{update_info['version']}.exe"
        dest_path = os.path.join(dest_folder, filename)
        
        success = _download_file(update_info["download_url"], dest_path, progress_callback)
        if success and os.path.exists(dest_path):
            return dest_path
        return None
    except Exception as e:
        print(f"[Updater] Download error: {e}")
        return None


def apply_update(exe_path: str, current_exe: str = None) -> bool:
    """
    Apply update by replacing current exe and restarting.
    
    Strategy:
    1. Create a batch script to:
       - Wait for current app to close
       - Copy new exe over old exe
       - Start new exe
       - Delete batch script
    2. Start batch script
    3. Exit current app
    """
    if not current_exe:
        current_exe = sys.executable
    
    # Don't update if running from source
    if not current_exe.lower().endswith('.exe'):
        print("[Updater] Running from source, cannot auto-update")
        return False
    
    try:
        # Create update batch script
        batch_content = f'''@echo off
echo INJECT DANA - Installing Update...
echo.
echo Waiting for app to close...
timeout /t 2 /nobreak >nul

:WAIT_LOOP
tasklist /FI "IMAGENAME eq {os.path.basename(current_exe)}" 2>NUL | find /I /N "{os.path.basename(current_exe)}" >NUL
if "%ERRORLEVEL%"=="0" (
    timeout /t 1 /nobreak >nul
    goto WAIT_LOOP
)

echo Copying new version...
copy /Y "{exe_path}" "{current_exe}"
if errorlevel 1 (
    echo [ERROR] Failed to copy new version!
    pause
    exit /b 1
)

echo Starting updated app...
start "" "{current_exe}"

echo.
echo Update complete!
timeout /t 2 /nobreak >nul

REM Cleanup
del "%~f0"
'''
        
        batch_path = os.path.join(tempfile.gettempdir(), "inject_dana_update.bat")
        with open(batch_path, 'w') as f:
            f.write(batch_content)
        
        # Start the update script
        subprocess.Popen(
            f'cmd /c "{batch_path}"',
            shell=True,
            creationflags=subprocess.CREATE_NEW_CONSOLE
        )
        
        return True
    except Exception as e:
        print(f"[Updater] Apply error: {e}")
        return False


# ===== Background Update Checker =====
class UpdateChecker(threading.Thread):
    """Background thread to check for updates."""
    
    def __init__(self, current_version: str, callback: Callable[[dict], None] = None):
        super().__init__(daemon=True)
        self.current_version = current_version
        self.callback = callback
        self._result = None
    
    def run(self):
        self._result = check_for_update(self.current_version)
        if self._result and self.callback:
            self.callback(self._result)
    
    @property
    def result(self) -> Optional[dict]:
        return self._result


# ===== Test =====
if __name__ == "__main__":
    print("Checking for updates...")
    update = check_for_update("1.0")
    if update:
        print(f"Update available: {update['version']}")
        print(f"Download URL: {update.get('download_url')}")
    else:
        print("No update available or error checking")
