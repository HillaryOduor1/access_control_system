; setup.iss - Inno Setup Script for ICTA Access Control
[Setup]
AppName=ICTA Access Control
AppVersion=1.2.0
AppPublisher=ICT Authority
AppPublisherURL=https://ictauthority.go.ke
AppSupportURL=https://ictauthority.go.ke
AppUpdatesURL=https://ictauthority.go.ke
DefaultDirName={pf}\ICTA Access Control
DefaultGroupName=ICTA Access Control
UninstallDisplayIcon={app}\ICTA_Access_Control.exe
Compression=lzma2
SolidCompression=yes
OutputDir=installer
OutputBaseFilename=ICTA_Access_Control_Setup_v1.2.0
SetupIconFile=..\icon.ico
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64
AllowNoIcons=yes
VersionInfoVersion=1.2.0
VersionInfoCompany=ICT Authority
VersionInfoDescription=ICTA Access Control System
VersionInfoTextVersion=1.2.0
VersionInfoCopyright=Copyright (c) ICT Authority. All rights reserved.
VersionInfoProductName=ICTA Access Control
VersionInfoProductVersion=1.2.0
VersionInfoOriginalFileName=ICTA_Access_Control_Setup.exe

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "dist\ICTA_Access_Control\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\icon.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\ICTA Access Control"; Filename: "{app}\ICTA_Access_Control.exe"; WorkingDir: "{app}"
Name: "{group}\Uninstall ICTA Access Control"; Filename: "{uninstallexe}"
Name: "{autodesktop}\ICTA Access Control"; Filename: "{app}\ICTA_Access_Control.exe"; WorkingDir: "{app}"

[Run]
Filename: "{app}\ICTA_Access_Control.exe"; Description: "Launch ICTA Access Control"; Flags: postinstall nowait skipifsilent unchecked