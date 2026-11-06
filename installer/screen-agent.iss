; Inno Setup script for Screen Agent.
; Builds a per-user installer (no admin needed): Start-menu + optional
; desktop shortcut, optional auto-start on sign-in, and an uninstaller.

#define MyAppName "Screen Agent"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "VoilaCode"
#define MyAppExeName "ScreenAgent.exe"

[Setup]
AppId={{8F3A6C2E-1B4D-4E7A-9C21-7A5E9D0B3F10}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
SourceDir=..
DefaultDirName={autopf}\ScreenAgent
DisableProgramGroupPage=yes
OutputDir=installer_out
OutputBaseFilename=ScreenAgent-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"
Name: "startup"; Description: "Start Screen Agent when I sign in"; GroupDescription: "Startup:"

[Files]
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "ScreenAgent"; ValueData: """{app}\{#MyAppExeName}"""; Flags: uninsdeletevalue; Tasks: startup

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch Screen Agent"; Flags: nowait postinstall skipifsilent
