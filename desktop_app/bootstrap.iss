; Access Control System - Bootstrap Installer
; Tiny downloader that fetches the payload installer and runs it.
; Requires Inno Setup 6.1 or newer (for TDownloadWizardPage).
; This is the <1-2 MB file that the user actually downloads.

#define AppName          "Access Control System"
#define AppVersion       "1.2.5"
#define AppPublisher     "Hillary Oduor"
#define PayloadURL       "http://127.0.0.1:8000/Access_Control_System_1.2.5_Payload.exe"
#define PayloadFileName  "Access_Control_System_1.2.5_Payload.exe"
#define AppGUID          "{8C4A1B2E-3F5D-4E8B-9A7C-1D2E3F4A5B6D}"
#define AppExeName       "Access_Control_System.exe"

[Setup]
AppId={{#AppGUID}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\ICTAuthority\AccessControl
DisableDirPage=yes
DisableProgramGroupPage=yes
LicenseFile=LICENSE.txt
OutputDir=installer
OutputBaseFilename=Access_Control_System_Setup
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
SetupIconFile=..\icon.ico
MinVersion=10.0
Uninstallable=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Run]
; Prompt to launch the app after installation completes.
; Skip if the user ran setup silently.
Filename: "{localappdata}\ICTAuthority\AccessControl\{#AppExeName}"; \
    Description: "Launch {#AppName}"; \
    Flags: nowait postinstall skipifsilent

[Code]
const
  PayloadUrl  = '{#PayloadURL}';
  PayloadName = '{#PayloadFileName}';

var
  DownloadPage: TDownloadWizardPage;

procedure InitializeWizard;
begin
  DownloadPage := CreateDownloadPage(
    'Downloading ' + '{#AppName}',
    'Setup is downloading the application files. This may take a few minutes.',
    nil
  );
end;

function OnDownloadProgress(const Url, FileName: String;
  const Progress, ProgressMax: Int64): Boolean;
begin
  Result := True;   // keep the download going
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = wpReady then
  begin
    DownloadPage.Clear;
    DownloadPage.Add(PayloadUrl, PayloadName, '');
    DownloadPage.Show;
    try
      try
        DownloadPage.Download;
      except
        MsgBox('Could not download the application.' + #13#10#13#10 +
               'Please check your internet connection and try again.' + #13#10#13#10 +
               GetExceptionMessage,
               mbCriticalError, MB_OK);
        Result := False;
      end;
    finally
      DownloadPage.Hide;
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
  PayloadPath: String;
begin
  if CurStep = ssPostInstall then
  begin
    PayloadPath := ExpandConstant('{tmp}\') + PayloadName;

    if not FileExists(PayloadPath) then
    begin
      MsgBox('Downloaded payload was not found at:' + #13#10 + PayloadPath,
             mbCriticalError, MB_OK);
      Exit;
    end;

    if not Exec(PayloadPath,
                '/SILENT /SUPPRESSMSGBOXES /NORESTART /SP-',
                '', SW_SHOW, ewWaitUntilTerminated, ResultCode) then
    begin
      MsgBox('Could not launch the installer. Exit code: ' +
             IntToStr(ResultCode), mbCriticalError, MB_OK);
    end;
  end;
end;