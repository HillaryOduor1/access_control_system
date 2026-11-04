; Access Control System - Payload Installer
; Wraps the PyInstaller onedir output into a normal Inno Setup installer.
; This is the ~30 MB file that actually contains the application.

#define AppName      "Access Control System"
#define AppVersion   "1.2.5"
#define AppPublisher "Hillary Oduor"
#define AppExeName   "Access_Control_System.exe"
#define AppGUID      "{8C4A1B2E-3F5D-4E8B-9A7C-1D2E3F4A5B6C}"

[Setup]
AppId={{#AppGUID}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\ICTAuthority\AccessControl
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=no
OutputDir=installer
OutputBaseFilename=Access_Control_System_{#AppVersion}_Payload
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
SetupIconFile=..\icon.ico
UninstallDisplayIcon={app}\{#AppExeName}
LicenseFile=LICENSE.txt
MinVersion=10.0

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"; Flags: checkedonce
Name: "startmenu";   Description: "Create a Start Menu shortcut"; GroupDescription: "Additional icons:"; Flags: checkedonce

[Files]
; PyInstaller onedir output
Source: "dist\Access_Control_System\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}";           Filename: "{app}\{#AppExeName}"; Tasks: startmenu
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}";       Tasks: startmenu
Name: "{autodesktop}\{#AppName}";     Filename: "{app}\{#AppExeName}";  Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent