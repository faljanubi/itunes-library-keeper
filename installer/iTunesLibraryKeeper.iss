; Inno Setup script for iTunes Library Keeper (https://jrsoftware.org/isinfo.php, version 6.3 or newer).
; Build with release.cmd, which runs build.cmd first and also makes the portable zip. Output: dist\iTunesLibraryKeeper-<version>-setup.exe
; The version is read from the built .exe, so only toolkit/version.py and assets/version_info.txt need bumping.

#define AppName    "iTunes Library Keeper"
#define AppExe     "iTunes Library Keeper.exe"
#define SourceDir  AddBackslash(SourcePath) + "..\dist\iTunes Library Keeper"
#define AppVersion GetStringFileInfo(SourceDir + "\" + AppExe, "ProductVersion")
#define Publisher  "Faris Aljanubi"

[Setup]
; Keep AppId fixed forever: it's how Setup finds an existing install to upgrade, and the app
; (toolkit/config.py INSTALLER_APP_ID) uses it to tell an installed copy from the portable one.
AppId={{C2C90B91-802A-4133-B2E6-31E34AE68333}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#Publisher}
AppCopyright=© 2026 {#Publisher}
VersionInfoVersion={#AppVersion}
VersionInfoProductName={#AppName}
VersionInfoDescription={#AppName} Setup
; Installs for the current user by default (no admin prompt); the first page offers "all users".
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
UsePreviousAppDir=yes
; The app is a 64-bit build (Qt 6 has no 32-bit Windows version).
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\dist
OutputBaseFilename=iTunesLibraryKeeper-{#AppVersion}-setup
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
; Fallback if the app ignores --quit (e.g. an old build): Windows Restart Manager offers to close it.
CloseApplications=yes
CloseApplicationsFilter=*.exe,*.dll,*.pyd
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[InstallDelete]
; An upgrade replaces the whole bundle, so files a newer build no longer ships don't linger.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Excludes: "\data"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\LICENSE"; DestDir: "{app}"; DestName: "LICENSE.txt"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"; AppUserModelID: "FarisAljanubi.iTunesLibraryKeeper"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[Code]
const
  ExeName = '{#AppExe}';

{ Full paths of running copies of the app, from WMI ('' entries skipped). }
function RunningCopies(): TArrayOfString;
var
  Locator, Service, Procs, P: Variant;
  I, N: Integer;
begin
  SetArrayLength(Result, 0);
  try
    Locator := CreateOleObject('WbemScripting.SWbemLocator');
    Service := Locator.ConnectServer('.', 'root\CIMV2');
    Procs := Service.ExecQuery('SELECT ExecutablePath FROM Win32_Process WHERE Name = ''' + ExeName + '''');
    N := 0;
    for I := 0 to Procs.Count - 1 do
    begin
      P := Procs.ItemIndex(I);
      if not VarIsNull(P.ExecutablePath) then
      begin
        SetArrayLength(Result, N + 1);
        Result[N] := P.ExecutablePath;
        N := N + 1;
      end;
    end;
  except
    { WMI unavailable: Restart Manager (CloseApplications) still covers setup. }
  end;
end;

{ Ask any running copy to quit through its single-instance channel, then wait up to
  TimeoutSec for it to exit (it finishes a running task first). True if none is left. }
function QuitRunningApp(TimeoutSec: Integer): Boolean;
var
  Copies: TArrayOfString;
  Code, Waited: Integer;
begin
  Copies := RunningCopies();
  if GetArrayLength(Copies) = 0 then
  begin
    Result := True;
    Exit;
  end;
  { Any copy's exe works: the request goes to whichever instance is running. }
  Exec(Copies[0], '--quit', '', SW_HIDE, ewWaitUntilTerminated, Code);
  Waited := 0;
  while (GetArrayLength(RunningCopies()) > 0) and (Waited < TimeoutSec * 2) do
  begin
    Sleep(500);
    Waited := Waited + 1;
  end;
  Result := GetArrayLength(RunningCopies()) = 0;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  if not QuitRunningApp(60) then
    Result := '{#AppName} is still running (it may be finishing a task). ' +
              'Quit it from its notification-area icon, then run Setup again.';
end;

function InitializeUninstall(): Boolean;
begin
  Result := True;
  while not QuitRunningApp(60) do
    if MsgBox('{#AppName} is still running (it may be finishing a task).' + #13#10#13#10 +
              'Quit it from its notification-area icon, then click Retry.',
              mbError, MB_RETRYCANCEL) = IDCANCEL then
    begin
      Result := False;
      Exit;
    end;
end;

{ The app's own "Start with Windows" shortcut (Settings) would point at the removed .exe.
  Only delete it if it points into this install (a portable copy may own it). }
procedure RemoveStartupShortcut();
var
  Lnk, Target: String;
  Shell, Shortcut: Variant;
begin
  Lnk := ExpandConstant('{userstartup}\{#AppName}.lnk');
  if not FileExists(Lnk) then
    Exit;
  try
    Shell := CreateOleObject('WScript.Shell');
    Shortcut := Shell.CreateShortcut(Lnk);
    Target := Shortcut.TargetPath;
  except
    Exit;
  end;
  if CompareText(Target, ExpandConstant('{app}\{#AppExe}')) = 0 then
    DeleteFile(Lnk);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usUninstall then
    RemoveStartupShortcut();
  if CurUninstallStep <> usPostUninstall then
    Exit;
  DataDir := ExpandConstant('{userappdata}\iTunesLibraryKeeper');
  if not DirExists(DataDir) then
    Exit;
  { Default No: settings, history and the removed-tracks list are kept for a reinstall. }
  if UninstallSilent() then
    Exit;
  if MsgBox('Also delete your iTunes Library Keeper settings and history?' + #13#10#13#10 +
            DataDir + #13#10#13#10 +
            'Your iTunes library and music files are not affected either way.',
            mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
  begin
    DelTree(DataDir, True, True, True);
    RegDeleteKeyIncludingSubkeys(HKCU, 'Software\Faris Aljanubi\iTunes Library Keeper');
    RegDeleteKeyIfEmpty(HKCU, 'Software\Faris Aljanubi');
  end;
end;
