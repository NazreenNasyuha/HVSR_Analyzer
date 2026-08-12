; ============================================================================
;  HVSR Analyzer - Inno Setup installer script
; ============================================================================
;  Build the installer:
;    1. Build the standalone app first (bundles a private Python runtime +
;       tkinter, so end users do NOT need Python installed):
;           pip install pyinstaller
;           python scripts/build_exe.py
;       Output:  dist\HVSR_Analyzer\
;    2. Compile this script with Inno Setup 6 (free) from
;       https://jrsoftware.org/isinfo.php - open it in Inno Setup and press
;       Compile, or run:
;           ISCC.exe HVSR_Analyzer_Setup.iss
;    3. The single-file setup  Output\HVSR_Analyzer_Setup.exe  is produced.
;
;  The application is pure Python (standard library only) packaged by
;  PyInstaller: the setup ships the exe together with its own private
;  Python runtime, so no Python installation is required on the target
;  machine.
; ============================================================================

#define MyAppName "HVSR Analyzer"
#define MyAppVersion "1.1.0"
#define MyAppPublisher "NazreenNasyuha"
#define MyAppExeName "HVSR_Analyzer\HVSR_Analyzer.exe"
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
; Tell Explorer to refresh its icon/association cache after install/uninstall.
ChangesAssociations=yes
LicenseFile=..\LICENSE
VersionInfoVersion=1.1.0.0
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
; The PyInstaller bundle: the app exe plus its private Python runtime,
; tkinter and standard library.  No Python installation is needed on the
; target machine.  Build it first with  python scripts/build_exe.py
Source: "..\dist\HVSR_Analyzer\*"; DestDir: "{app}\HVSR_Analyzer"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\README.md";             DestDir: "{app}";      Flags: ignoreversion
Source: "..\CHANGELOG.md";          DestDir: "{app}";      Flags: ignoreversion
Source: "..\docs\TUTORIAL.md";       DestDir: "{app}\docs";  Flags: ignoreversion
Source: "..\docs\screenshots\*";    DestDir: "{app}\docs\screenshots";  Flags: ignoreversion
Source: "..\examples\example.eqd";        DestDir: "{app}\examples";  Flags: ignoreversion
Source: "..\examples\example_Z.mseed";     DestDir: "{app}\examples";  Flags: ignoreversion
Source: "..\examples\example_N.mseed";     DestDir: "{app}\examples";  Flags: ignoreversion
Source: "..\examples\example_E.mseed";     DestDir: "{app}\examples";  Flags: ignoreversion
Source: "..\examples\example.sg2";        DestDir: "{app}\examples";  Flags: ignoreversion
Source: "..\examples\README.md";    DestDir: "{app}\examples";  Flags: ignoreversion
Source: "..\LICENSE";               DestDir: "{app}";      Flags: ignoreversion
Source: "HVSR_Analyzer.ico";        DestDir: "{app}";      Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}";        Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\HVSR_Analyzer.ico"; WorkingDir: "{app}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"; IconFilename: "{app}\HVSR_Analyzer.ico"
Name: "{autodesktop}\{#MyAppName}";  Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\HVSR_Analyzer.ico"; WorkingDir: "{app}"; Tasks: desktopicon

[InstallDelete]
; Remove files shipped by pre-1.1.0 installers that the packaged build no
; longer needs (the PyInstaller bundle replaces the loose sources, tests and
; the run.bat launcher).  Without this, upgrading from 1.0.0 leaves stale
; files behind.
Type: filesandordirs; Name: "{app}\src"
Type: filesandordirs; Name: "{app}\tests"
Type: filesandordirs; Name: "{app}\run.bat"

[Registry]
; Per-user file associations (written to HKCU\Software\Classes, removed on
; uninstall).  Double-clicking a recording opens HVSR Analyzer with that
; file pre-loaded (see the command-line handling in hvsr_gui.main()).
; The extensions are niche seismic formats, so claiming them is safe.
; (uninsdeletekey removes the whole per-user <ext> key on uninstall - the
; formats are effectively app-owned, so no realistic collision.)
Root: HKCR; Subkey: "HVSR_Analyzer\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\HVSR_Analyzer\HVSR_Analyzer.exe,0"; Flags: uninsdeletekey
Root: HKCR; Subkey: "HVSR_Analyzer\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\HVSR_Analyzer\HVSR_Analyzer.exe"" ""%1"""; Flags: uninsdeletekey
Root: HKCR; Subkey: ".eqd";      ValueType: string; ValueName: ""; ValueData: "HVSR_Analyzer"; Flags: uninsdeletekey
Root: HKCR; Subkey: ".sg2";      ValueType: string; ValueName: ""; ValueData: "HVSR_Analyzer"; Flags: uninsdeletekey
Root: HKCR; Subkey: ".mseed";    ValueType: string; ValueName: ""; ValueData: "HVSR_Analyzer"; Flags: uninsdeletekey
Root: HKCR; Subkey: ".miniseed"; ValueType: string; ValueName: ""; ValueData: "HVSR_Analyzer"; Flags: uninsdeletekey

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Remove the whole PyInstaller bundle folder: the recursed files are normally
; deleted by the uninstaller from its log, but the onedir bundle is large and
; a clean uninstall must never leave it (or any runtime data) behind.
; With no output folder chosen the frozen app auto-creates HVSR_Results next
; to the exe, i.e. inside this folder too (see hvsr_gui._out_dir).
Type: filesandordirs; Name: "{app}\HVSR_Analyzer"
Type: dirifempty;     Name: "{app}"
