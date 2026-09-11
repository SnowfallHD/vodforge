#ifndef MyAppVersion
  #define MyAppVersion "0.1.0-dev"
#endif

#define MyAppName "VODForge"
#define MyAppPublisher "SnowfallHD"
#define MyAppURL "https://github.com/SnowfallHD/vodforge"
#define MyAppExeName "VODForge.exe"

[Setup]
AppId={{2C217998-2315-41E3-99BA-3A0289331B54}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=dist\release
OutputBaseFilename=VODForge-Windows-Setup-v{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
CloseApplications=yes
RestartApplications=yes
CloseApplicationsFilter={#MyAppExeName}
WizardStyle=modern
SetupIconFile=assets\VODForge.ico

[Files]
Source: "scripts\windows_close_for_update.ps1"; Flags: dontcopy
Source: "dist\VODForge\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall; Check: ShouldLaunchApp

[Code]
function SetEnvironmentVariable(lpName, lpValue: String): Boolean;
  external 'SetEnvironmentVariableW@kernel32.dll stdcall';

function ShouldLaunchApp: Boolean;
begin
  { New updater owns relaunch; legacy updater and manual installs use this entry. }
  Result := ExpandConstant('{param:VODFORGEHANDOFF|0}') <> '1';
  if Result then
    SetEnvironmentVariable('PYINSTALLER_RESET_ENVIRONMENT', '1');
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ScriptPath: String;
  ExitCode: Integer;
begin
  Result := '';
  { Older updaters do not close themselves. Request normal shutdown for this
    installation only; refusal or timeout must stop installation. }
  ExtractTemporaryFile('windows_close_for_update.ps1');
  ScriptPath := ExpandConstant('{tmp}\windows_close_for_update.ps1');
  if not Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
    '-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + ScriptPath +
    '" -ExecutablePath "' + ExpandConstant('{app}\{#MyAppExeName}') + '"',
    '', SW_HIDE, ewWaitUntilTerminated, ExitCode) then
    Result := 'Could not check the running app. Close VODForge and run this installer again.'
  else if ExitCode <> 0 then
    Result := 'VODForge could not close safely. Finish or stop active work, close VODForge, and run this installer again.';
end;
