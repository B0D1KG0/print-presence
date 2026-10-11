; Inno Setup script for Print Presence (https://jrsoftware.org/isinfo.php).
; build.bat compiles it automatically when Inno Setup 6 is installed:
;   ISCC.exe /DAppVersion=0.8.0 installer\PrintPresence.iss
; Expects dist\PrintPresence.exe to be built first.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

#define AppName "Print Presence"
#define AppExe "PrintPresence.exe"
#define AppUrl "https://github.com/B0D1KG0/print-presence"

[Setup]
; Never change AppId: Windows uses it to recognise updates of the same app.
AppId={{6C1E2B57-3F0A-4C7B-9C8E-5B0D1C0E7A21}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=B0D1KG0
AppPublisherURL={#AppUrl}
AppSupportURL={#AppUrl}/issues
AppUpdatesURL={#AppUrl}/releases
; Per-user install into %LOCALAPPDATA%\Programs — no administrator rights needed.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
SetupIconFile=..\assets\app.ico
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
OutputDir=..\dist
OutputBaseFilename=PrintPresence-Setup
LicenseFile=..\LICENSE
; Close a running copy (it may be hidden in the tray) before updating.
CloseApplications=force
RestartApplications=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "ru"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "uk"; MessagesFile: "compiler:Languages\Ukrainian.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; DestName: "LICENSE.txt"; Flags: ignoreversion
Source: "..\THIRD-PARTY-NOTICES.md"; DestDir: "{app}"; DestName: "THIRD-PARTY-NOTICES.txt"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Stop the app (and its tray icon) before removing files.
Filename: "{sys}\taskkill.exe"; Parameters: "/im {#AppExe} /f"; Flags: runhidden; RunOnceId: "StopApp"

[Registry]
; Remove the "Launch with Windows" entry the app may have created.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "PrintPresence"; Flags: uninsdeletevalue dontcreatekey

; Settings in %APPDATA%\PrintPresence are kept on uninstall, so a reinstall keeps the printers.
