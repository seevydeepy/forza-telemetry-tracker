#define AppName "Forza Telemetry Tracker"
#define AppVersion GetEnv("FORZA_TRACKER_VERSION")
#if AppVersion == ""
  #define AppVersion "0.1.0"
#endif
#define AppPublisher "Forza Telemetry Tracker"
#define AppExeName "ForzaTelemetryTracker.exe"
#define SourceRoot GetEnv("FORZA_TRACKER_INSTALLER_SOURCE")
#if SourceRoot == ""
  #define SourceRoot "..\..\dist\ForzaTelemetryTracker"
#endif
#define WebView2Installer GetEnv("WEBVIEW2_STANDALONE_INSTALLER")

[Setup]
AppId={{F2C92642-C179-40B7-9C51-8ED72157D2A3}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL=https://github.com/seevydeepy/forza-telemetry-tracker
AppSupportURL=https://github.com/seevydeepy/forza-telemetry-tracker/issues
AppUpdatesURL=https://github.com/seevydeepy/forza-telemetry-tracker/releases
AppComments=Unofficial community telemetry tool. Not affiliated with, endorsed by, or sponsored by Microsoft, Xbox Game Studios, Turn 10 Studios, Playground Games, or the Forza franchise owners.
DefaultDirName={localappdata}\Programs\Forza Telemetry Tracker
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\..\dist\installer
OutputBaseFilename=ForzaTelemetryTrackerSetup-v{#AppVersion}-x64
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
UninstallDisplayIcon={app}\{#AppExeName}

[Files]
Source: "{#SourceRoot}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
#if WebView2Installer != ""
Source: "{#WebView2Installer}"; Flags: dontcopy
#endif

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

[Code]
const
  WebView2AlreadyInstalledExitCode = -2147219416; // Inno reports 0x80040828 as a signed Integer.
  WebView2ClientKey = 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';

function HasWebView2Version(const RootKey: Integer; const RootName: String): Boolean;
var
  Version: String;
begin
  Result := RegQueryStringValue(RootKey, WebView2ClientKey, 'pv', Version) and
    (Version <> '') and (Version <> '0.0.0.0');
  if Result then begin
    Log('Detected Microsoft Edge WebView2 Runtime ' + Version + ' in ' + RootName + '\' + WebView2ClientKey + '.');
  end;
end;

function IsWebView2Installed: Boolean;
begin
  // Microsoft documents the 64-bit Windows per-machine key in the 32-bit registry view.
  Result :=
    HasWebView2Version(HKCU, 'HKCU') or
    HasWebView2Version(HKLM32, 'HKLM32') or
    HasWebView2Version(HKLM, 'HKLM') or
    HasWebView2Version(HKLM64, 'HKLM64');
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  Result := '';
#if WebView2Installer != ""
  if not IsWebView2Installed then begin
    ExtractTemporaryFile(ExtractFileName('{#WebView2Installer}'));
    if not Exec(ExpandConstant('{tmp}\') + ExtractFileName('{#WebView2Installer}'), '/silent /install', '', SW_SHOW, ewWaitUntilTerminated, ResultCode) then begin
      Result := 'Unable to launch Microsoft Edge WebView2 Runtime installer.';
      exit;
    end;
    if ResultCode <> 0 then begin
      if ResultCode = WebView2AlreadyInstalledExitCode then begin
        Log('Microsoft Edge WebView2 Runtime installer reported that the runtime is already installed; continuing.');
        exit;
      end;
      Result := 'Microsoft Edge WebView2 Runtime installation failed with exit code ' + IntToStr(ResultCode) + '.';
      exit;
    end;
  end;
#endif
end;
