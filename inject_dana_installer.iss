; ===========================================
; INJECT DANA v3.0.10 - Standalone EXE Installer
; INCLUDES: Bundled EXE + ADB (No Python needed!)
; ===========================================
; Cara compile:
; 1. Build INJECT_DANA.exe dulu (pyinstaller)
; 2. Jalankan BUILD_INJECT_DANA.bat untuk kompile installer
; 3. Hasil: Output/INJECT_DANA_Installer_v3.0.10.exe
; ===========================================

#define MyAppName "INJECT DANA"
#define MyAppVersion "3.0.10"
#define MyAppPublisher "LELEPAY Team"
#define MyAppURL "https://lelepay.com"
#define MyAppExeName "INJECT_DANA.exe"

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

; Enable update
AppUpdatesEnabled=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Messages]
WelcomeLabel1=Selamat Datang di Setup {#MyAppName} v{#MyAppVersion}
WelcomeLabel2=INJECT DANA - Auto Suntikan via Telegram + myBCA HP%n%nSEMUA SUDAH BUNDLED DALAM 1 EXE:%n  - Telegram Login QR Code + 2FA%n  - ADB Platform-Tools%n  - uiautomator2%n  - Auto Update dari server%n%nBaru di v3.0.10:%n  - Standalone EXE (no Python needed)%n  - Auto Update dari server%n  - Fix emoji display%n  - App icon%n%nTIDAK PERLU install apa-apa lagi!%nCukup klik Next -> Install -> Finish.
FinishedHeadingLabel=Instalasi Selesai!
FinishedLabel={#MyAppName} v{#MyAppVersion} telah terinstall.%n%nLANGKAH SELANJUTNYA:%n1. Colok HP via USB, aktifkan USB Debugging%n2. Jalankan INJECT DANA dari Desktop/Start Menu%n3. Scan QR Code Telegram%n%nAPLIKASI AKAN AUTO-UPDATE saat ada versi baru!

[Types]
Name: "full"; Description: "Full Installation (RECOMMENDED)"
Name: "exeonly"; Description: "EXE Only (sudah ada ADB)"

[Components]
Name: "main"; Description: "INJECT DANA EXE (Wajib)"; Types: full exeonly; Flags: fixed
Name: "adb"; Description: "ADB Platform-Tools (~10 MB)"; Types: full

[Tasks]
Name: "addtopath"; Description: "Tambahkan ADB ke System PATH"; GroupDescription: "Konfigurasi:"; Components: adb
Name: "desktopicon"; Description: "Buat shortcut di Desktop"; GroupDescription: "Shortcut:"; Flags: checked

[Files]
; === MAIN EXE (bundled with Python + all deps) ===
Source: "dist\INJECT_DANA.exe"; DestDir: "{app}"; Components: main; Flags: ignoreversion

; === ADB PLATFORM-TOOLS ===
Source: "installer_deps\platform-tools\*"; DestDir: "{app}\platform-tools"; Components: adb; Flags: ignoreversion recursesubdirs createallsubdirs

; === ICON ===
Source: "lelepay_logo_real.ico"; DestDir: "{app}"; Components: main; Flags: ignoreversion

[Icons]
; Start Menu
Name: "{group}\INJECT DANA"; Filename: "{app}\INJECT_DANA.exe"; WorkingDir: "{app}"; IconFilename: "{app}\lelepay_logo_real.ico"; Comment: "Jalankan INJECT DANA v{#MyAppVersion}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"

; Desktop (jika dipilih)
Name: "{autodesktop}\INJECT DANA"; Filename: "{app}\INJECT_DANA.exe"; WorkingDir: "{app}"; IconFilename: "{app}\lelepay_logo_real.ico"; Tasks: desktopicon

[Run]
; Jalankan aplikasi setelah install (optional)
Filename: "{app}\INJECT_DANA.exe"; Description: "Jalankan INJECT DANA sekarang"; Flags: nowait postinstall skipifsilent

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
Type: files; Name: "{app}\*.session"
Type: filesandordirs; Name: "{app}\screenshots"
Type: filesandordirs; Name: "{app}\logs"
Type: dirifempty; Name: "{app}\platform-tools"
Type: dirifempty; Name: "{app}"

[Registry]
Root: HKCU; Subkey: "Software\INJECT_DANA"; ValueType: string; ValueName: "InstallPath"; ValueData: "{app}"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\INJECT_DANA"; ValueType: string; ValueName: "Version"; ValueData: "{#MyAppVersion}"; Flags: uninsdeletekey

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
  AdbPath, ConfigPath: String;
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
    
    // Buat config jika belum ada
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
    // Refresh environment variables
    Exec('powershell.exe', '-Command "Add-Type -TypeDefinition ''using System; using System.Runtime.InteropServices; public class Env { [DllImport(\"user32.dll\", SetLastError = true, CharSet = CharSet.Auto)] public static extern IntPtr SendMessageTimeout(IntPtr hWnd, uint Msg, UIntPtr wParam, string lParam, uint fuFlags, uint uTimeout, out UIntPtr lpdwResult); }''; $result = [UIntPtr]::Zero; [Env]::SendMessageTimeout([IntPtr]0xFFFF, 0x1A, [UIntPtr]::Zero, ''Environment'', 2, 5000, [ref]$result)"', '', SW_HIDE, ewNoWait, ResultCode);
  end;
end;
