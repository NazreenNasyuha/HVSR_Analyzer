; ============================================================================
;  HVSR Analyzer - Inno Setup installer script
; ============================================================================
;  Build the installer:
;    1. Download Inno Setup 6 (free) from  https://jrsoftware.org/isinfo.php
;    2. Open this file in Inno Setup and press Compile, or run:
;         ISCC.exe HVSR_Analyzer_Setup.iss
;    3. The single-file setup  Output\HVSR_Analyzer_Setup.exe  is produced.
;
;  The application is pure Python (standard library only) and requires an
;  installed Python 3.8+ on the target machine.  The installer detects
;  Python on the machine and warns if it is missing or too old.
; ============================================================================

#define MyAppName "HVSR Analyzer"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "NazreenNasyuha"
#define MyAppExeName "run.bat"
#define MyAppCopyright "Copyright (c) 2026 NazreenNasyuha"

[Setup]
AppId={{2CD7AB13-6C35-46CD-B8F0-D407804CD32C}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL=https://github.com/NazreenNasyuha/HVSR_Analyzer
AppSupportURL=https://github.com/NazreenNasyuha/HVSR_Analyzer/issues
AppUpdatesURL=https://github.com/NazreenNasyuha/HVSR_Analyzer/releases
AppCopyright={#MyAppCopyright}
AppComments=Horizontal-to-Vertical Spectral Ratio (HVSR) analysis, pure Python
DefaultDirName={localappdata}\Programs\HVSR Analyzer
DefaultGroupName={#MyAppName}
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
OutputDir=Output
OutputBaseFilename=HVSR_Analyzer_Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile=HVSR_Analyzer.ico
UninstallDisplayIcon={app}\HVSR_Analyzer.ico
LicenseFile=..\LICENSE
VersionInfoVersion=1.0.0.0
VersionInfoCopyright={#MyAppCopyright}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription=HVSR Analyzer - pure-Python HVSR analysis suite
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}
VersionInfoOriginalFileName=HVSR_Analyzer_Setup.exe
ShowLanguageDialog=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\src\main.py";         DestDir: "{app}\src";  Flags: ignoreversion
Source: "..\run.bat";             DestDir: "{app}";      Flags: ignoreversion
Source: "..\src\hvsr_gui.py";         DestDir: "{app}\src";  Flags: ignoreversion
Source: "..\src\hvsr_theme.py";        DestDir: "{app}\src";  Flags: ignoreversion
Source: "..\src\hvsr_plot.py";         DestDir: "{app}\src";  Flags: ignoreversion
Source: "..\src\hvsr_engine.py";         DestDir: "{app}\src";  Flags: ignoreversion
Source: "..\src\hvsr_dsp.py";         DestDir: "{app}\src";  Flags: ignoreversion
Source: "..\src\hvsr_io.py";         DestDir: "{app}\src";  Flags: ignoreversion
Source: "..\src\mseed_io.py";         DestDir: "{app}\src";  Flags: ignoreversion
Source: "..\src\eqd_io.py";         DestDir: "{app}\src";  Flags: ignoreversion
Source: "..\src\sg2_io.py";         DestDir: "{app}\src";  Flags: ignoreversion
Source: "..\src\hvsr_geopsy.py";         DestDir: "{app}\src";  Flags: ignoreversion
Source: "..\src\hvsr_standards.py";         DestDir: "{app}\src";  Flags: ignoreversion
Source: "..\src\hvsr_tour.py";         DestDir: "{app}\src";  Flags: ignoreversion
Source: "..\src\hvsr_inversion.py";         DestDir: "{app}\src";  Flags: ignoreversion
Source: "..\src\chart_render.py";         DestDir: "{app}\src";  Flags: ignoreversion
Source: "..\src\make_sample_data.py";         DestDir: "{app}\src";  Flags: ignoreversion
Source: "..\README.md";           DestDir: "{app}";      Flags: ignoreversion
Source: "..\CHANGELOG.md";        DestDir: "{app}";      Flags: ignoreversion
Source: "..\docs\TUTORIAL.md";     DestDir: "{app}\docs";  Flags: ignoreversion
Source: "..\docs\screenshots\*";  DestDir: "{app}\docs\screenshots";  Flags: ignoreversion
Source: "..\examples\example.eqd";        DestDir: "{app}\examples";  Flags: ignoreversion
Source: "..\examples\example_Z.mseed";     DestDir: "{app}\examples";  Flags: ignoreversion
Source: "..\examples\example_N.mseed";     DestDir: "{app}\examples";  Flags: ignoreversion
Source: "..\examples\example_E.mseed";     DestDir: "{app}\examples";  Flags: ignoreversion
Source: "..\examples\example.sg2";        DestDir: "{app}\examples";  Flags: ignoreversion
Source: "..\examples\README.md";    DestDir: "{app}\examples";  Flags: ignoreversion
Source: "..\LICENSE";             DestDir: "{app}";      Flags: ignoreversion
Source: "HVSR_Analyzer.ico";        DestDir: "{app}";      Flags: ignoreversion
Source: "..\tests\test_engine.py";    DestDir: "{app}\tests";  Flags: ignoreversion
Source: "..\tests\test_io.py";    DestDir: "{app}\tests";  Flags: ignoreversion
Source: "..\tests\test_extras.py";    DestDir: "{app}\tests";  Flags: ignoreversion
Source: "..\tests\test_gui.py";    DestDir: "{app}\tests";  Flags: ignoreversion
Source: "..\tests\test_inversion.py";    DestDir: "{app}\tests";  Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}";        Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\HVSR_Analyzer.ico"; WorkingDir: "{app}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"; IconFilename: "{app}\HVSR_Analyzer.ico"
Name: "{autodesktop}\{#MyAppName}";  Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\HVSR_Analyzer.ico"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Remove runtime-generated data (results, sample data, bytecode caches)
; so a clean uninstall leaves nothing behind.  Installed files are
; removed automatically by Inno.
Type: filesandordirs; Name: "{app}\src\HVSR_Results"
Type: filesandordirs; Name: "{app}\src\HVSR_Results_E2E"
Type: filesandordirs; Name: "{app}\src\sample_data"
Type: filesandordirs; Name: "{app}\src\__pycache__"
Type: filesandordirs; Name: "{app}	ests\__pycache__"
Type: filesandordirs; Name: "{app}\__pycache__"

[Code]
function ParseVersionPair(const V: String; out Major, Minor: Integer): Boolean;
var
  P: Integer;
  T: String;
begin
  Result := False;
  Major := -1;
  Minor := -1;
  { The registry SysVersion value is dot-separated ("3.13") while the
    python -c probe prints space-separated integers ("3 13").  Normalise
    both to a space-separated pair before splitting. }
  T := V;
  StringChangeEx(T, '.', ' ', True);
  P := Pos(' ', T);
  if P > 0 then
  begin
    Major := StrToIntDef(Copy(T, 1, P - 1), -1);
    Delete(T, 1, P);
    P := Pos(' ', T);
    if P > 0 then
      Minor := StrToIntDef(Copy(T, 1, P - 1), -1)
    else
      Minor := StrToIntDef(T, -1);
    Result := (Major > 0) and (Minor >= 0);
  end;
end;

function SufficientVersion(Major, Minor: Integer): Boolean;
begin
  Result := (Major > 3) or ((Major = 3) and (Minor >= 8));
end;

function RegistryPythonVersion(out Major, Minor: Integer): Boolean;
var
  Key: String;
  V: String;
begin
  Result := False;
  Key := 'Software\Python\PythonCore';
  { Check the 64-bit view first (HKLM64) so a machine-wide 64-bit Python
    install is seen even though this installer itself runs 32-bit, then the
    regular HKLM view and finally the per-user HKCU key. }
  if RegQueryStringValue(HKLM64, Key, 'SysVersion', V) then
    Result := ParseVersionPair(V, Major, Minor)
  else if RegQueryStringValue(HKLM, Key, 'SysVersion', V) then
    Result := ParseVersionPair(V, Major, Minor)
  else if RegQueryStringValue(HKCU, Key, 'SysVersion', V) then
    Result := ParseVersionPair(V, Major, Minor);
end;

function PythonSufficient(): Boolean;
var
  Res: Integer;
begin
  Result := False;
  { Probe the PATH interpreter through its exit code: python exits 0 when
    sys.version_info >= (3, 8) and 1 otherwise.  This needs no stdout
    capture (ExecWithOutput is unavailable in some builds) and the -c
    argument has no embedded double quotes, so Windows argument parsing
    cannot split it. }
  if ExecAsOriginalUser('python',
      '-c "import sys; raise SystemExit(0 if sys.version_info >= (3, 8) else 1)"',
      '', SW_HIDE, ewWaitUntilTerminated, Res) then
    Result := (Res = 0);
end;

function PythonDetected(): Boolean;
var
  Major, Minor: Integer;
begin
  { Check the PATH interpreter first - that is what run.bat actually
    launches - then fall back to a registered installation. }
  if PythonSufficient() then
    Result := True
  else if RegistryPythonVersion(Major, Minor) then
    Result := SufficientVersion(Major, Minor)
  else
    Result := False;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = wpReady then
  begin
    if not PythonDetected() then
      MsgBox('Python 3.8 or newer was not detected on this system.' + #13#10 +
             'HVSR Analyzer is written in pure Python and needs it to run.' + #13#10 + #13#10 +
             'Install Python from https://www.python.org/downloads/ ' +
             '(tick "Add python.exe to PATH") and then re-run this setup.',
             mbInformation, MB_OK);
  end;
end;
