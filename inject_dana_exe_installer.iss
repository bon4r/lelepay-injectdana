; ===========================================
; INJECT DANA v3.0 - EXE Installer
; Distribusi .exe (sudah termasuk Python)
; ===========================================
; Cara compile:
; 1. Jalankan BUILD_EXE_INJECT_DANA.bat dulu untuk build .exe
; 2. Lalu jalankan BUILD_INSTALLER_EXE.bat untuk buat installer
; ===========================================

#define MyAppName "INJECT DANA"
#define MyAppVersion "3.0"
#define MyAppPublisher "LELEPAY Team"
#define MyAppURL "https://github.com/bon4r/lelepay-injectdana"
#define MyAppExeName "INJECT_DANA.exe"

[Setup]
AppId={{B2C3D4E5-F6A7-8901-BCDE-F12345678902}
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
OutputBaseFilename=INJECT_DANA_v{#MyAppVersion}_Setup

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
WelcomeLabel2=INJECT DANA - Auto Suntikan via Telegram + myBCA HP%n%nFITUR v3.0:%n  ✅ Fair distribution untuk multi-user%n  ✅ Force cancel request stuck%n  ✅ Auto-update dari GitHub%n  ✅ Standalone .exe (tanpa install Python)%n%nTIDAK PERLU install Python!%nCukup klik Next → Install → Finish.
FinishedHeadingLabel=Instalasi Selesai!
FinishedLabel={#MyAppName} v{#MyAppVersion} telah terinstall.%n%nLANGKAH SELANJUTNYA:%n1. Colok HP via USB, aktifkan USB Debugging%n2. Jalankan INJECT DANA dari Desktop/Start Menu%n3. Login Telegram via QR Code%n4. Configure bank accounts

[Tasks]
Name: "desktopicon"; Description: "Buat shortcut di Desktop"; GroupDescription: "Shortcut:"

[Files]
; === MAIN EXE (dari PyInstaller build) ===
Source: "dist\INJECT_DANA.exe"; DestDir: "{app}"; Flags: ignoreversion

; === ICON ===
Source: "lelepay_logo_real.ico"; DestDir: "{app}"; Flags: ignoreversion

; === ADB PLATFORM-TOOLS (opsional, untuk USB debugging) ===
Source: "installer_deps\platform-tools\*"; DestDir: "{app}\platform-tools"; Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist

[Icons]
; Start Menu
Name: "{group}\INJECT DANA"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\lelepay_logo_real.ico"; Comment: "Jalankan INJECT DANA v{#MyAppVersion}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"

; Desktop (jika dipilih)
Name: "{autodesktop}\INJECT DANA"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\lelepay_logo_real.ico"; Tasks: desktopicon

[Run]
; Jalankan aplikasi setelah install (optional)
Filename: "{app}\{#MyAppExeName}"; Description: "Jalankan INJECT DANA"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: files; Name: "{app}\inject_dana_config.json"
Type: files; Name: "{app}\inject_dana_pending.json"
Type: files; Name: "{app}\inject_success.json"
Type: files; Name: "{app}\inject_dana_claimed.json"
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
Root: HKCU; Subkey: "Software\INJECT_DANA"; ValueType: string; ValueName: "Version"; ValueData: "{#MyAppVersion}"; Flags: uninsdeletekey

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
var
  ConfigPath, DefaultConfig: String;
begin
  if CurStep = ssPostInstall then
  begin
    ConfigPath := ExpandConstant('{app}\inject_dana_config.json');
    
    // Buat config default jika belum ada
    if not FileExists(ConfigPath) then
    begin
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
      SaveStringToFile(ConfigPath, DefaultConfig, False);
    end;

    // Buat folder screenshots & logs
    ForceDirectories(ExpandConstant('{app}\screenshots'));
    ForceDirectories(ExpandConstant('{app}\logs'));
  end;
end;
