"""Deploy INJECT_DANA.exe to VPS with auto-password."""
import subprocess, sys, os, json

HOST = "178.128.87.151"
USER = "znxbot"
PASS = "znxbot"
EXE_PATH = r"d:\tes2\dist2\INJECT_DANA.exe"
REMOTE_DIR = "/var/www/releases"
VERSION = "3.0.28"

CHANGELOG_HISTORY_TEXT = """\
v3.0.28: Fix runtime_cache access denied saat launch dari updater (hapus runtime_tmpdir relatif + cd /d fix).
v3.0.27: Fix restart updater agar app selalu benar-benar restart (graceful quit + hard-exit fallback).
v3.0.26: Fix python311.dll load error (onefile no-UPX + runtime_cache non-TEMP).
v3.0.25: Fix restart flow (close only on apply success) + updater script unik per run.
v3.0.24: Check Update kini selalu menampilkan changelog versi terbaru.
v3.0.23: Update in-place tanpa bikin file app baru + fix fallback changelog.
v3.0.22: Fix restart update lebih stabil (copy retry loop + fallback launch).
v3.0.21: Fix auto-restart setelah install update + fallback launch lebih robust.
v3.0.20: Tambah tab UPDATE + changelog, dan update install ke nama tetap INJECT_DANA.exe.
"""

CHANGELOG_HISTORY_MD = """## Changelog\n- v3.0.28: Fix runtime_cache access denied saat launch dari updater (hapus runtime_tmpdir relatif + cd /d fix).\n- v3.0.27: Fix restart updater agar app selalu benar-benar restart (graceful quit + hard-exit fallback).\n- v3.0.26: Fix python311.dll load error (onefile no-UPX + runtime_cache non-TEMP).\n- v3.0.25: Fix restart flow (close only on apply success) + updater script unik per run.\n- v3.0.24: Check Update kini selalu menampilkan changelog versi terbaru.\n- v3.0.23: Update in-place tanpa bikin file app baru + fix fallback changelog.\n- v3.0.22: Fix restart update lebih stabil (copy retry loop + fallback launch).\n- v3.0.21: Fix auto-restart setelah install update + fallback launch lebih robust.\n- v3.0.20: Tambah tab UPDATE + changelog, dan update install ke nama tetap INJECT_DANA.exe."""

def run_cmd(cmd, input_text=None):
    print(f">> {cmd}")
    p = subprocess.Popen(cmd, shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, err = p.communicate(input=input_text.encode() if input_text else None, timeout=120)
    print(out.decode(errors='replace'))
    if err:
        print(err.decode(errors='replace'))
    return p.returncode

# Try paramiko first
try:
    import paramiko
    print("Using paramiko...")
    
    # Upload EXE
    print(f"Uploading {EXE_PATH}...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, username=USER, password=PASS, timeout=30)
    
    sftp = ssh.open_sftp()
    remote_tmp = "/tmp/INJECT_DANA.exe"
    sftp.put(EXE_PATH, remote_tmp, callback=lambda sent, total: print(f"\r  {sent*100//total}%", end="", flush=True))
    print("\n  Upload done!")
    sftp.close()
    
    # Move to releases dir
    print("Moving to releases dir...")
    stdin, stdout, stderr = ssh.exec_command(f"echo {PASS} | sudo -S mv {remote_tmp} {REMOTE_DIR}/INJECT_DANA.exe")
    print(stdout.read().decode(), stderr.read().decode())
    
    # Update releases.json via SFTP (write to /tmp then sudo mv)
    print("Updating releases.json...")
    changelog_text = CHANGELOG_HISTORY_TEXT

    releases_json = json.dumps({
        "version": VERSION,
        "download_url": f"http://{HOST}/releases/INJECT_DANA.exe",
        "url": f"http://{HOST}/releases/INJECT_DANA.exe",
        "body": CHANGELOG_HISTORY_MD,
        "changelog": changelog_text,
        "asset_name": "INJECT_DANA.exe"
    }, ensure_ascii=False)
    sftp2 = ssh.open_sftp()
    with sftp2.file("/tmp/releases.json", "w") as f:
        f.write(releases_json)
    sftp2.close()
    stdin, stdout, stderr = ssh.exec_command(f"echo {PASS} | sudo -S mv /tmp/releases.json {REMOTE_DIR}/releases.json")
    print(stdout.read().decode(), stderr.read().decode())
    
    # Verify
    print("Verifying...")
    stdin, stdout, stderr = ssh.exec_command(f"cat {REMOTE_DIR}/releases.json")
    content = stdout.read().decode()
    print(f"releases.json: {content}")
    
    stdin, stdout, stderr = ssh.exec_command(f"ls -la {REMOTE_DIR}/INJECT_DANA.exe")
    print(stdout.read().decode())
    
    ssh.close()
    print("DEPLOY DONE!")
    
except ImportError:
    print("paramiko not installed, installing...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "paramiko", "-q"])
    print("Re-run this script.")
    sys.exit(1)
