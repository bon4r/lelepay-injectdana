; ===========================================
; INJECT DANA v2.9 - Full Installer
; INCLUDES: Python + PySide6 + ADB + Telethon
; ===========================================
; Cara compile:
; 1. Jalankan BUILD_INJECT_DANA.bat
;    (atau buka file ini di Inno Setup → Ctrl+F9)
; 2. Hasil: Output/INJECT_DANA_Installer_v2.9.exe
; ===========================================

#define MyAppName "INJECT DANA"
#define MyAppVersion "2.9"
#define MyAppPublisher "LELEPAY Team"
#define MyAppURL "https://lelepay.com"
#define MyAppExeName "RUN_INJECT_DANA.bat"

[Setup]
AppId={{B2C3D4E5-F6A7-8901-BCDE-F12345678901}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}

; User bisa pilih folder sendiri
DefaultDirName={userdocs}\INJECT_DANA
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes

; Output installer
OutputDir=Output
OutputBaseFilename=INJECT_DANA_Installer_v{#MyAppVersion}

; Kompresi maksimal
Compression=lzma2/ultra64
SolidCompression=yes

; Tampilan
WizardStyle=modern
WizardSizePercent=120

; Tidak perlu admin (install ke user folder)
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

; Icon
SetupIconFile=lelepay_logo_real.ico

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Messages]
WelcomeLabel1=Selamat Datang di Setup {#MyAppName} v{#MyAppVersion}
WelcomeLabel2=INJECT DANA - Auto Suntikan via Telegram + myBCA HP%n%nSEMUA SUDAH TERMASUK:%n  ✅ Python 3.14 + PySide6 (GUI Modern)%n  ✅ Telethon (Telegram Login QR Code)%n  ✅ ADB Platform-Tools%n  ✅ uiautomator2 + QR Code%n%nBAru di v2.9:%n  ✅ Force cancel request stuck%n  ✅ Anti double transfer%n  ✅ Big Amount threshold%n%nTIDAK PERLU install apa-apa lagi!%nCukup klik Next → Install → Finish.
FinishedHeadingLabel=Instalasi Selesai!
FinishedLabel={#MyAppName} v{#MyAppVersion} telah terinstall.%n%nLANGKAH SELANJUTNYA:%n1. Pastikan centang "Install Python Packages"%n2. Klik Finish dan TUNGGU sampai selesai%n3. Colok HP via USB, aktifkan USB Debugging%n4. Jalankan INJECT DANA dari Desktop/Start Menu

[Types]
Name: "full"; Description: "Full Installation (RECOMMENDED)"
Name: "scriptsonly"; Description: "Scripts Only (sudah ada Python & ADB)"

[Components]
Name: "main"; Description: "INJECT DANA Scripts (Wajib)"; Types: full scriptsonly; Flags: fixed
Name: "python"; Description: "Python 3.14 + PySide6 GUI (~120 MB)"; Types: full
Name: "adb"; Description: "ADB Platform-Tools (~10 MB)"; Types: full

[Tasks]
Name: "addtopath"; Description: "Tambahkan ADB ke System PATH"; GroupDescription: "Konfigurasi:"; Components: adb
Name: "desktopicon"; Description: "Buat shortcut di Desktop"; GroupDescription: "Shortcut:"
Name: "installpackages"; Description: "Install Python packages (Telethon, PySide6, dll) - WAJIB pertama kali!"; GroupDescription: "Post-Install:"

[Files]
; === PYTHON 3.14 (dari system copy) ===
Source: "installer_deps\python\*"; DestDir: "{app}\python"; Components: python; Flags: ignoreversion recursesubdirs createallsubdirs

; === ADB PLATFORM-TOOLS ===
Source: "installer_deps\platform-tools\*"; DestDir: "{app}\platform-tools"; Components: adb; Flags: ignoreversion recursesubdirs createallsubdirs

; === MAIN SCRIPT ===
Source: "INJECT_DANA.py"; DestDir: "{app}"; Components: main; Flags: ignoreversion
Source: "lelepay_logo_real.ico"; DestDir: "{app}"; Components: main; Flags: ignoreversion

; === CONFIG akan dibuat via [Code] supaya merge dengan existing ===
; API ID dan HASH selalu diupdate, session dan banks DIPERTAHANKAN

; === BATCH FILES ===
Source: "RUN_INJECT_DANA.bat"; DestDir: "{app}"; Components: main; Flags: ignoreversion
Source: "POST_INSTALL_INJECT_DANA.bat"; DestDir: "{app}"; Components: main; Flags: ignoreversion

; === DEPENDENCIES LIST ===
Source: "inject_dana_requirements.txt"; DestDir: "{app}"; Components: main; Flags: ignoreversion

[Icons]
; Start Menu
Name: "{group}\INJECT DANA"; Filename: "{app}\RUN_INJECT_DANA.bat"; WorkingDir: "{app}"; IconFilename: "{app}\lelepay_logo_real.ico"; Comment: "Jalankan INJECT DANA v2.9"
Name: "{group}\Setup Ulang Packages"; Filename: "{app}\POST_INSTALL_INJECT_DANA.bat"; WorkingDir: "{app}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"

; Desktop (jika dipilih)
Name: "{autodesktop}\INJECT DANA v2.9"; Filename: "{app}\RUN_INJECT_DANA.bat"; WorkingDir: "{app}"; IconFilename: "{app}\lelepay_logo_real.ico"; Tasks: desktopicon

[Run]
; Jalankan POST_INSTALL setelah install selesai
Filename: "{app}\POST_INSTALL_INJECT_DANA.bat"; Description: "Install Python Packages (WAJIB pertama kali!)"; Flags: shellexec waituntilterminated postinstall; Tasks: installpackages
Filename: "{app}\POST_INSTALL_INJECT_DANA.bat"; Description: "Install Python Packages (RECOMMENDED)"; Flags: shellexec waituntilterminated postinstall unchecked skipifsilent

[UninstallRun]
; Hapus dari PATH saat uninstall
Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -Command ""$p = [Environment]::GetEnvironmentVariable('PATH', 'User'); $p = ($p -split ';' | Where-Object {{ $_ -notlike '*{app}*' }}) -join ';'; [Environment]::SetEnvironmentVariable('PATH', $p, 'User')"""; Flags: runhidden

[UninstallDelete]
Type: files; Name: "{app}\inject_dana_config.json"
Type: files; Name: "{app}\inject_dana_pending.json"
Type: files; Name: "{app}\inject_success.json"
Type: files; Name: "{app}\tg_avatar.jpg"
Type: files; Name: "{app}\*.log"
Type: files; Name: "{app}\log_*.txt"
Type: filesandordirs; Name: "{app}\__pycache__"
Type: filesandordirs; Name: "{app}\screenshots"
Type: filesandordirs; Name: "{app}\logs"
Type: dirifempty; Name: "{app}\platform-tools"
Type: dirifempty; Name: "{app}"

[Registry]
Root: HKCU; Subkey: "Software\INJECT_DANA"; ValueType: string; ValueName: "InstallPath"; ValueData: "{app}"; Flags: uninsdeletekey

[Code]
procedure AddToPath(const Path: String);
var
  CurrentPath: String;
begin
  if not RegQueryStringValue(HKEY_CURRENT_USER, 'Environment', 'PATH', CurrentPath) then
    CurrentPath := '';
  if Pos(Uppercase(Path), Uppercase(CurrentPath)) = 0 then
  begin
    if CurrentPath <> '' then
      CurrentPath := CurrentPath + ';';
    CurrentPath := CurrentPath + Path;
    RegWriteStringValue(HKEY_CURRENT_USER, 'Environment', 'PATH', CurrentPath);
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  AdbPath, ConfigPath, ConfigContent, OldSession, OldBanks: String;
  DefaultConfig: String;
begin
  if CurStep = ssPostInstall then
  begin
    ConfigPath := ExpandConstant('{app}\inject_dana_config.json');
    
    // Default config dengan API ID dan HASH (PENTING!)
    DefaultConfig := '{' + #13#10 +
      '  "api_id": "34768359",' + #13#10 +
      '  "api_hash": "22c3fa3db2a61b8976c431e7b9027fe5",' + #13#10 +
      '  "phone": "",' + #13#10 +
      '  "session_string": "",' + #13#10 +
      '  "group_chat_id": -1001655728988,' + #13#10 +
      '  "bot_username": "znxgemini_bot",' + #13#10 +
      '  "banks": [],' + #13#10 +
      '  "auto_process": false,' + #13#10 +
      '  "biaya_bifast": 2500,' + #13#10 +
      '  "biaya_realtime": 6500' + #13#10 +
      '}';
    
    // Selalu tulis config dengan API ID dan HASH
    // Jika sudah ada config lama, user perlu login ulang (session di-keep di aplikasi)
    if not FileExists(ConfigPath) then
    begin
      SaveStringToFile(ConfigPath, DefaultConfig, False);
    end;

    // Buat folder screenshots & logs
    ForceDirectories(ExpandConstant('{app}\screenshots'));
    ForceDirectories(ExpandConstant('{app}\logs'));

    // Setup PATH jika dipilih
    if WizardIsTaskSelected('addtopath') then
    begin
      if WizardIsComponentSelected('adb') then
      begin
        AdbPath := ExpandConstant('{app}\platform-tools');
        AddToPath(AdbPath);
      end;
    end;
  end;
end;

procedure CurPageChanged(CurPageID: Integer);
var
  ResultCode: Integer;
begin
  if CurPageID = wpFinished then
  begin
    Exec('powershell.exe', '-Command "Add-Type -TypeDefinition ''using System; using System.Runtime.InteropServices; public class Env { [DllImport(\"user32.dll\", SetLastError = true, CharSet = CharSet.Auto)] public static extern IntPtr SendMessageTimeout(IntPtr hWnd, uint Msg, UIntPtr wParam, string lParam, uint fuFlags, uint uTimeout, out UIntPtr lpdwResult); }''; $result = [UIntPtr]::Zero; [Env]::SendMessageTimeout([IntPtr]0xFFFF, 0x1A, [UIntPtr]::Zero, ''Environment'', 2, 5000, [ref]$result)"', '', SW_HIDE, ewNoWait, ResultCode);
  end;
end;
