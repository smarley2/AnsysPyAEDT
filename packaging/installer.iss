; Inno Setup script for PyAEDT Inductor Designer (M10 Task 4).
;
; Compiled by `packaging/build_frozen.py --installer`, never run through
; ISCC.exe by hand for a release build -- that script passes the running
; application's own version (`inductor_designer.__about__.__version__`) in
; via /DMyAppVersion, so this script and the About box can never disagree.
; The #ifndef fallback below only exists so a developer can compile this
; script directly (`ISCC installer.iss`) to sanity-check it while editing,
; without also needing a live Python environment on the compiling machine.
#ifndef MyAppVersion
  #define MyAppVersion "0.0.0-dev"
#endif

#define MyAppName "PyAEDT Inductor Designer"
#define MyAppPublisher "PyAEDT Inductor Designer contributors"
#define MyAppExeName "inductor-designer.exe"

; The bundle `packaging/build_frozen.py` produces -- see docs/development/
; packaging.md. Task 4 wraps this output unmodified; it is not rebuilt here.
#define BundleDir SourcePath + "..\dist\inductor-designer"

[Setup]
; Fixed so upgrade/uninstall recognise the same product across versions.
; Generated once for this application; never regenerate it for a new
; release, only for a genuinely different product.
AppId={{2E66D529-8CBF-4DF2-938B-44DAFBD7B1FF}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
VersionInfoVersion={#MyAppVersion}

; Ruled by Fabio Posser, 2026-09-01: per-user install, no administrator
; required. An engineering workstation user who cannot elevate must still be
; able to install. {userpf} is the per-user equivalent of "Program Files"
; (%LOCALAPPDATA%\Programs) -- it needs no elevation to write to, unlike
; {commonpf} / {autopf} in admin mode.
PrivilegesRequired=lowest
DefaultDirName={userpf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}

; Ruled by Fabio Posser, 2026-09-01: unsigned for this release. Task 5's
; release notes carry the resulting SmartScreen warning; no signing
; configuration is added here.

OutputDir={#SourcePath}..\dist\installer
OutputBaseFilename=inductor-designer-{#MyAppVersion}-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
DisableWelcomePage=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
; Start Menu shortcut is unconditional (below); desktop is opt-in and
; unticked by default -- Fabio Posser's ruling, 2026-09-01.
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
; The frozen one-folder bundle, unmodified -- Task 3's output is what ships.
; No sample project is included anywhere in this section (ruled 2026-09-01:
; nothing installed carries a design).
Source: "{#BundleDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

; --------------------------------------------------------------------------
; Deliberately absent: any [UninstallDelete] entry, and any [Dirs] entry,
; naming %LOCALAPPDATA%\InductorDesigner (or any path under it).
;
; That directory (adapters/system/environment.py:
; application_data_directory()) holds the user's crash-recovery snapshots
; and the application log -- the application creates and writes it at
; runtime, this installer never does. Standard installer practice removes
; application data on uninstall; this one deliberately does not, because
; deleting a recovery snapshot during an uninstall would destroy unsaved
; work at the worst possible moment, and the log is what a support engineer
; reads afterwards. Inno Setup's generated uninstaller only removes what
; [Files]/[Icons]/[Dirs] told it to install -- since nothing in this script
; ever names %LOCALAPPDATA%\InductorDesigner, the uninstaller has no path to
; it at all. Verified in docs/development/packaging.md's "Verifying the
; uninstaller leaves user data alone" section: install, run once so the
; directory exists with real content, uninstall, confirm the directory and
; every file in it (including a pre-existing log) are untouched by mtime and
; byte count.
; --------------------------------------------------------------------------
