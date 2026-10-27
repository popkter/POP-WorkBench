#define MyAppName "泡泡的工作台"
#define MyAppDisplayName "泡泡的工作台 · Pop’s Workbench"
; Keep build paths and executable names compatible with existing OTA clients.
#define MyAppBuildName "泡泡工具箱"
#ifndef Edition
#define Edition "Bundled"
#endif
#ifndef OutputName
#define OutputName "PopTools-Setup"
#endif
#ifndef MyAppVersion
#define MyAppVersion "0.0.0"
#endif
#ifndef MyAppVersionInfoVersion
#define MyAppVersionInfoVersion "0.0.0.0"
#endif
#define MyAppPublisher "PopTools"
#define MyAppExeName "泡泡工具箱.exe"
#define MyAppUserModelId "PopTools.ZhangPaopaoToolbox"

[Setup]
#ifdef InstallerTest
AppId=PopTools-Installer-Smoke-Test
Uninstallable=no
CreateUninstallRegKey=no
#else
AppId={{2D39A497-EC7D-4A4E-A09F-5CC3768725B4}
#endif
AppName={#MyAppDisplayName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename={#OutputName}
#ifdef InstallerTest
Compression=none
#else
Compression=lzma2/max
#endif
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\src\poptools\resources\icons\app-icon.ico
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
; Older PopTools builds treated Restart Manager's close request as a request
; to minimize to the tray. Try a graceful close first, then terminate those
; legacy builds after the user has confirmed that Setup may close the app.
#ifdef InstallerTest
CloseApplications=no
#else
CloseApplications=force
#endif
RestartApplications=no
SetupLogging=yes
#ifdef InstallerTest
UsePreviousAppDir=no
#else
UsePreviousAppDir=yes
#endif
ChangesEnvironment=no
VersionInfoVersion={#MyAppVersionInfoVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppDisplayName} 安装程序
VersionInfoProductName={#MyAppDisplayName}

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务："; Flags: unchecked

[Files]
Source: "..\dist\{#MyAppBuildName}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\dist\{#MyAppBuildName}\*"; DestDir: "{tmp}\plugin-migration"; Flags: dontcopy recursesubdirs createallsubdirs
Source: "..\build\edition-{#Edition}.json"; DestDir: "{app}"; DestName: "edition.json"; Flags: ignoreversion
#if Edition == "Bundled"
Source: "..\build\plugin-seeds\python\*"; DestDir: "{code:PluginDataDirectory}\plugins\python\seed\runtime"; Flags: ignoreversion recursesubdirs createallsubdirs uninsneveruninstall
Source: "..\build\plugin-seeds\python-package.json"; DestDir: "{code:PluginDataDirectory}\plugins\python\seed"; DestName: "package.json"; Flags: ignoreversion uninsneveruninstall
Source: "..\build\plugin-seeds\scrcpy\*"; DestDir: "{code:PluginDataDirectory}\plugins\android\seed\runtime"; Flags: ignoreversion recursesubdirs createallsubdirs uninsneveruninstall
Source: "..\build\plugin-seeds\android-package.json"; DestDir: "{code:PluginDataDirectory}\plugins\android\seed"; DestName: "package.json"; Flags: ignoreversion uninsneveruninstall
Source: "..\build\plugin-seeds\powershell\*"; DestDir: "{code:PluginDataDirectory}\plugins\powershell\seed\runtime"; Flags: ignoreversion recursesubdirs createallsubdirs uninsneveruninstall
Source: "..\build\plugin-seeds\powershell-package.json"; DestDir: "{code:PluginDataDirectory}\plugins\powershell\seed"; DestName: "package.json"; Flags: ignoreversion uninsneveruninstall
#endif

[InstallDelete]
Type: filesandordirs; Name: "{app}\_internal"
Type: filesandordirs; Name: "{app}\runtime"
#ifndef InstallerTest
; Old and new shortcuts must not compete for the same notification identity.
Type: files; Name: "{group}\泡泡工具箱.lnk"
Type: files; Name: "{userprograms}\泡泡工具箱\泡泡工具箱.lnk"
Type: files; Name: "{autodesktop}\泡泡工具箱.lnk"
#endif

#ifndef InstallerTest
[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; AppUserModelID: "{#MyAppUserModelId}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; AppUserModelID: "{#MyAppUserModelId}"; Tasks: desktopicon

[Registry]
; Per-user Explorer entries do not require administrator privileges.
Root: HKCU; Subkey: "Software\Classes\AppUserModelId\{#MyAppUserModelId}"; ValueType: string; ValueName: "DisplayName"; ValueData: "{#MyAppDisplayName}"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\AppUserModelId\{#MyAppUserModelId}"; ValueType: string; ValueName: "IconUri"; ValueData: "{app}\_internal\poptools\resources\icons\app-icon.ico"
Root: HKCU; Subkey: "Software\Classes\Directory\Background\shell\PoTerminal"; ValueType: string; ValueName: ""; ValueData: "在此打开泡泡的工作台终端"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\Directory\Background\shell\PoTerminal\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" --terminal --cwd ""%V"""
Root: HKCU; Subkey: "Software\Classes\Directory\shell\PoTerminal"; ValueType: string; ValueName: ""; ValueData: "在此打开泡泡的工作台终端"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\Directory\shell\PoTerminal\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" --terminal --cwd ""%1"""

#endif
[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent

[Code]
function PluginDataDirectory(Param: String): String;
begin
  Result := GetEnv('POPTOOLS_DATA_DIR');
  if Result = '' then Result := ExpandConstant('{localappdata}\PopTools');
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  Result := '';
  ExtractTemporaryFiles('{tmp}\plugin-migration\*');
  if not Exec(ExpandConstant('{tmp}\plugin-migration\{#MyAppExeName}'),
      '--migrate-plugins "' + ExpandConstant('{app}') + '"', '', SW_HIDE,
      ewWaitUntilTerminated, ResultCode) or (ResultCode <> 0) then
    Result := '插件环境迁移失败，已保留旧安装。请关闭正在运行的插件程序后重试。';
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
begin
  if CurStep = ssPostInstall then
    if not Exec(ExpandConstant('{app}\{#MyAppExeName}'), '--prepare-runtime', '',
        SW_HIDE, ewWaitUntilTerminated, ResultCode) or (ResultCode <> 0) then
      RaiseException('插件初始化未完成，已保留插件文件。请启动应用重试。');
end;

function GetWindowThreadProcessId(Wnd: HWND; var ProcessId: DWORD): DWORD;
  external 'GetWindowThreadProcessId@user32.dll stdcall';

function CloseRunningApplication(): Boolean;
var
  AppWindow: HWND;
  ProcessId: DWORD;
  ResultCode: Integer;
begin
  Result := True;
#ifdef InstallerTest
  Exit;
#endif
  AppWindow := FindWindowByWindowName('{#MyAppDisplayName}');
  if AppWindow = 0 then
    AppWindow := FindWindowByWindowName('{#MyAppName}');
  if AppWindow = 0 then
    AppWindow := FindWindowByWindowName('{#MyAppBuildName}');
  if AppWindow = 0 then
    Exit;

  if (not WizardSilent) and
     (MsgBox(
       '{#MyAppName} 正在运行。继续安装将关闭当前应用，是否继续？',
       mbConfirmation, MB_YESNO or MB_DEFBUTTON2) <> idYes) then
  begin
    Result := False;
    Exit;
  end;

  ProcessId := 0;
  GetWindowThreadProcessId(AppWindow, ProcessId);
  if ProcessId <> 0 then
  begin
    Log(Format('Closing running {#MyAppName} process %d before installation.', [ProcessId]));
    Exec(
      ExpandConstant('{cmd}'),
      Format('/D /Q /C taskkill /PID %d /T /F', [ProcessId]),
      '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Sleep(500);
  end;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = wpReady then
    Result := CloseRunningApplication();
end;
