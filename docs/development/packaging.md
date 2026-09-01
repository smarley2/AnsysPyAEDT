# Freezing the application (M10 Task 3)

- Milestone: M10, Windows release
- Plan: [2026-09-01 M10 Windows release](../superpowers/plans/2026-09-01-m10-windows-release.md), Task 3
- Produces: a one-folder PyInstaller bundle at `dist/inductor-designer/`. Task
  4 wraps this output in an Inno Setup installer -- what this task produces
  is what gets shipped, unmodified.

## Build it

```powershell
.venv\Scripts\python.exe -m pip install -e ".[ui,packaging]"
.venv\Scripts\python.exe packaging\build_frozen.py
```

One command. `packaging/build_frozen.py`:

1. Builds the catalog index (`tools.build_catalog`) into a temporary
   directory and checks it has at least one core in it.
2. Sets `INDUCTOR_DESIGNER_BUILD_CATALOG` to that generated file's path.
3. Runs PyInstaller against `packaging/inductor-designer.spec`, which reads
   that environment variable at Analysis time (a `.spec` file takes no
   command-line arguments of its own) and builds the bundle's `datas` from
   it via `resolve_datas()`.

**The catalog index is generated here, not copied.** `artifacts/` is
git-ignored, so `artifacts/catalog/catalog.sqlite` exists only where someone
has already run `tools.build_catalog` -- which is not guaranteed on a fresh
clone or a CI runner. Copying whatever happens to be on disk (or nothing)
would let a build silently ship an installer whose application starts and
shows an empty core list -- it looks like it worked, which is worse than a
build that refuses outright. So `build_catalog()` in `build_frozen.py`
raises `CatalogBuildError`, and `main()` turns that into a `SystemExit` with
the reason on the line, if the generated index has zero cores in it. Verified
directly: `tests/unit/tools/test_build_frozen.py::test_main_refuses_when_the_catalog_build_produces_no_index`
feeds it a catalog source tree with no `cores/*.yaml` files at all and
asserts PyInstaller is never invoked.

`packaging/` is a plain directory, not a Python package -- there is no
`__init__.py` in it. `packaging` is also the name of a direct PyPI
dependency of this project (`packaging>=24.2,<27` in `pyproject.toml`);
making this directory importable as `packaging.build_frozen` would risk
shadowing that dependency for anything else that imports `packaging` while
the repository root is on `sys.path` (which it is under pytest, since
`tests/__init__.py` makes `tests` a proper package and pytest's rootdir
insertion then puts the repo root at `sys.path[0]`). Run `build_frozen.py`
directly by path, as shown above; the test module loads it the same way,
via `importlib.util.spec_from_file_location`.

## What is excluded, and why

Every entry in `inductor-designer.spec`'s `excludes` list carries the reason
inline; summarized here:

- **`inductor_designer.mcp_server`, `mcp`** -- the 2026-09-01 release
  decision (see the M10 plan): MCP is not shipped in this version. The
  `inductor-designer-mcp` console script stays for source installs; nothing
  in the frozen product references it.
- **`pytest`, `hypothesis`, `mypy`, `ruff`** -- dev tooling, never imported by
  the shipped application.
- **A block of PySide6 Qt submodules** (`QtWidgets`, `QtWebEngine*`,
  `QtMultimedia*`, `QtBluetooth`, `QtCharts`, `Qt3D*`, and about two dozen
  more) -- the application never imports them and the QML tree never
  `import`s them. Verified by exhaustive grep before excluding anything, not
  guessed:

  ```powershell
  # Every PySide6 submodule this application's Python code imports:
  grep -rhoE "from PySide6\.[A-Za-z0-9_.]+ import" src | sort -u
  # -> PySide6.QtCore, PySide6.QtGui, PySide6.QtQml, PySide6.QtQuick3D

  # Every Qt module the QML tree imports:
  grep -rhoE "^import [A-Za-z0-9_.]+" src/inductor_designer/ui/qml | sort -u
  # -> QtQml.Models, QtQuick, QtQuick.Controls, QtQuick.Dialogs,
  #    QtQuick.Layouts, QtQuick.Window, QtQuick3D, QtQuick3D.Helpers
  ```

  Everything excluded is outside both lists. `QtOpenGL` and `QtQuick` --
  needed transitively by `QtQuick3D`'s rendering pipeline -- are **not**
  excluded, and the build's own warning log (`build/inductor-designer/warn-
  inductor-designer.txt`) shows PyInstaller pulling them in as expected.
  Excluding a module either list actually uses is the classic way to
  produce a bundle that starts and renders nothing, so this list stops
  where the grep evidence stops -- and Task 3 Step 4 below is the empirical
  check that it actually still renders, not just a grep-based guess.

  These excludes only shrink the *Python binding* (`.pyd`) for each
  submodule -- they do **not**, by themselves, shrink the corresponding
  native Qt DLL or the `PySide6/qml/` tree; see "Reducing the QML and DLL
  footprint" below for the filter that does.

`pyaedt` (`ansys.aedt.core`) and `pyfemm` are **not** excluded -- the frozen
application talks to a real installed AEDT/FEMM through them. Neither ships a
directory under `_internal/`; both are pure Python and land inside the PYZ
archive, so their footprint doesn't show up in the top-level `_internal/`
size table at all (only their `*.dist-info/` metadata does). `pyaedt` does
ship one **data** dependency the spec must collect explicitly:
`ansys.aedt.core`'s 114 non-Python data files, 13.3 MB, via
`collect_data_files("ansys.aedt.core")` -- most importantly
`visualization/post/fields_calculator_files/expression_catalog.toml`, which
`PostProcessor3D`'s `FieldsCalculator` (`post_common_3d.py`,
`fields_calculator.py`) reads eagerly on every result read. Without it, every
result path in this application (`adapters/pyaedt/live_app.py`,
`maxwell3d.py`, `maxwell2d.py`) raises `TypeError` the moment a solve is
opened -- a frozen build could generate a solve but never read one back.
`femm` and `ansys.edb` ship zero data files each; nothing to collect for
those.

## Reducing the QML and DLL footprint

`excludes=` stops PyInstaller from including a submodule's Python binding,
but PySide6's own PyInstaller hook still copies the *entire*
`PySide6/qml/` tree, because `QQmlApplicationEngine` loads QML modules by
string at runtime and the hook can't tell which of them are reachable. That
QML tree then drags native Qt DLLs back in through plugin dependencies even
for modules whose Python binding was already excluded -- concretely,
`qml/QtWebEngine/qtwebenginequickplugin.dll` needs `Qt6WebEngineQuick.dll`,
which links `Qt6WebEngineCore.dll` (195 MB on its own). `excludes=` cannot
reach any of this; it only ever touches `.pyd` files.

The spec addresses this after `Analysis` runs, by filtering `a.binaries` and
`a.datas` before `COLLECT` (see `_keep_binary`/`_keep_data` in
`inductor-designer.spec`). Dropped, all confirmed unreferenced by the same
import-grep evidence above:

- **WebEngine** -- `Qt6WebEngineCore.dll`, `Qt6WebEngineQuick.dll`,
  `Qt6WebEngineQuickDelegatesQml.dll`, and `qml/QtWebEngine/`. Already
  non-functional in this bundle before the filter existed (no
  `QtWebEngineProcess.exe`, no `*.pak`, no `icudtl.dat` -- PyInstaller's
  hook never copies those), so this is pure payload, not a working feature
  being cut.
- **The native Qt6\*.dll for every other already-excluded PySide6 submodule**
  (`Qt6Widgets.dll`, the six `Qt63D*.dll`, `Qt6Charts.dll`,
  `Qt6DataVisualization.dll`, `Qt6Graphs.dll`, `Qt6Location.dll`,
  `Qt6Multimedia.dll`, `Qt6RemoteObjects.dll`, `Qt6SpatialAudio.dll`, and
  the rest -- plus `Qt6WebView.dll`/`Qt6WebViewQuick.dll`, unused and absent
  from both import greps above but never added to `excludes=`).
- **17 unused `qml/` module directories**: `Qt3D`, `Qt5Compat`, `QtCharts`,
  `QtDataVisualization`, `QtGraphs`, `QtLocation`, `QtMultimedia`,
  `QtPositioning`, `QtRemoteObjects`, `QtScxml`, `QtSensors`, `QtTest`,
  `QtTextToSpeech`, `QtWebChannel`, `QtWebEngine`, `QtWebSockets`,
  `QtWebView` -- these are what pull the DLLs above back in. What remains
  under `PySide6/qml/`: `Qt`, `QtCore`, `QtNetwork`, `QtQml`, `QtQuick`,
  `QtQuick3D`.
- **`PySide6/translations/`** -- the UI is English-only.

**Deliberately kept**: `opengl32sw.dll` (the software OpenGL fallback) --
it matters on RDP or a machine with no GPU driver, exactly where this
application gets used, so it stays regardless of size. `matplotlib` and
`PIL` are untouched too -- both are pulled in by `pyaedt`, not by this
application's own code, and neither was verified unused the way the Qt
modules above were.

This is the riskiest change in the freeze: over-pruning produces a bundle
that starts and renders nothing, silently. Task 3 Step 4 below is the
post-prune empirical check -- a real launch on the real sample project, not
a simulated one.

## One folder, not one file

`inductor-designer.spec` builds a `COLLECT`, not a single-file `EXE`. A
one-file build re-unpacks itself to a temp directory on every launch, which
costs real seconds for a PySide6 bundle this size and is a common antivirus
trigger. One folder also means `INDUCTOR_DESIGNER_RESOURCES` (the override
`adapters/system/resources.py` checks first) can point at a corrected
resource tree without a rebuild, and a support engineer can replace one file
under `_internal/` in place.

## Build output observed

Bundle built 2026-09-01, PyInstaller 6.22.2, PySide6 6.11.1, Python 3.13.14,
on the development workstation (24 logical processors, Windows 11). Measured
with a recursive byte count, not `du`/Explorer rounding.

**Before the QML/DLL prune** (`collect_data_files("ansys.aedt.core")`
already applied, `a.binaries`/`a.datas` filter not yet applied): 544.5 MB
(519.3 MiB) total, `PySide6/` 384 MB -- `PySide6/qml/` itself measured at
29 MB, and the single largest object in the whole bundle was
`Qt6WebEngineCore.dll` alone at 195.3 MB (38% of the bundle).

**After the prune** -- the state that ships:

```text
dist/inductor-designer/                297 MB total (296,534,641 bytes)
├── inductor-designer.exe              21 MB   (console subsystem; see below)
└── _internal/                         276 MB
    ├── PySide6/                       148 MB  (qml/ down to 6 modules: Qt, QtCore, QtNetwork, QtQml, QtQuick, QtQuick3D -- see above)
    ├── numpy.libs/                     21 MB
    ├── matplotlib/                     14 MB  (pulled in by pyaedt, not this app -- left alone)
    ├── PIL/                            13 MB  (pulled in by pyaedt, not this app -- left alone)
    ├── ansys/                          13 MB  (pyaedt's non-Python data files -- see above; NEW in this pass, was 0 MB)
    ├── grpc/                           11 MB  (pyaedt's gRPC transport)
    ├── cryptography/                  9.9 MB
    ├── numpy/                         6.3 MB
    ├── pydantic_core/                 5.3 MB
    ├── ansys_edb_core-*.dist-info/, pyaedt-*.dist-info/, pyfemm-*.dist-info/  -- metadata only; pyaedt/pyfemm code itself is pure Python, inside the PYZ
    ├── schemas/                              -- resource 1/4
    ├── compatibility/aedt-matrix.yml         -- resource 2/4
    ├── artifacts/catalog/catalog.sqlite      -- resource 3/4, GENERATED, never copied
    ├── materials-overlay/                    -- resource 4/4
    └── inductor_designer/ui/qml/             -- package data (Main.qml et al.), not one of the four resources
```

Net effect of the prune: 544.5 MB -> 296.5 MB, a cut of 248.0 MB (45.5%).
`PySide6/` alone: 384 MB -> 148 MB.

Confirmed absent: `inductor_designer/mcp_server`, and no `mcp*`, `pytest*`,
`hypothesis*`, `mypy*`, or `ruff*` directory anywhere under `_internal/`; no
`Qt6WebEngine*.dll`, no `PySide6/qml/QtWebEngine/`, no
`PySide6/translations/`.

### `--help`, from a working directory outside the checkout

```text
C:\Users\...\Temp> C:\Work\git\AnsysPyAEDT\dist\inductor-designer\inductor-designer.exe --help
usage: inductor-designer [-h] [--project PROJECT] [--catalog CATALOG]
                         [--matrix MATRIX]

options:
  -h, --help         show this help message and exit
  --project PROJECT
  --catalog CATALOG
  --matrix MATRIX
```

Exit code `0`. This alone already exercises `resources.resource_root()`'s
frozen branch, since `--catalog`/`--matrix` default to
`resources.catalog_index_path()` / `compatibility_matrix_path()`, computed
before argparse ever looks at `argv`.

Console, not windowed: `ui/main.py` writes refusal messages, `--project`
parse errors, and the project-lock refusal to stderr for a terminal or CI
launch, and the frozen build needs that to stay readable. Task 4's installer
can hide the console for the Start Menu shortcut if that turns out to matter
for the release's polish; nothing here forecloses it.

## Task 3 Step 4: launching on the real sample project, from outside the checkout

This section records the *original* Task 3 launch, against the bundle as it
existed before the fix wave below (no pyaedt data files, no QML/DLL prune).
See "Fix wave 1 re-verification" further down for the launch against the
bundle that actually ships.

This is the step that actually proves Task 1's resource seam was worth
building -- not a simulated `sys.frozen`, the real frozen artifact, launched
from a directory that has never seen the source tree:

```powershell
cd C:\Users\fpo01\AppData\Local\Temp\inductor-designer-launch-test
C:\Work\git\AnsysPyAEDT\dist\inductor-designer\inductor-designer.exe --project C:\Work\git\AnsysPyAEDT\artifacts\maxwell3d\2025.2-commercial\m7b.inductor.json
```

Observed directly, not inferred:

- stderr: `Loaded m7b.inductor.json: 6 winding(s); opening viewer.` -- the
  project, catalog, and compatibility matrix all resolved and parsed; the
  application did not hit `_refuse_if_resources_are_missing` or either of
  the per-flag `.is_file()` checks in `main()`.
- stderr also carried two benign QML warnings (`Shortcut: Only binding to
  one of multiple key bindings...`), sourced from
  `file:///C:/Work/git/AnsysPyAEDT/dist/inductor-designer/_internal/inductor_designer/ui/qml/Main.qml`
  -- confirming the QML package data landed at the path `qml_directory()`
  expects inside the frozen bundle, not just the four resource paths.
- A real, visible window opened on the development workstation's desktop
  (captured by screenshot, not assumed): "PyAEDT Inductor Designer",
  Guided Studio's Windings step, with a rendered 3D toroid-and-windings
  preview from `m7b.inductor.json` (6 windings, w1/w2 shown at 10 turns,
  AWG 18) -- direct visual proof that `QtQuick3D` renders correctly with
  the spec's Qt exclusions in place, not just that the process didn't crash.
- The application log at `%LOCALAPPDATA%\InductorDesigner\logs\
  inductor-designer.log` recorded `Application 0.1.0.dev0 starting.` and,
  from the earlier `--help` invocation and this one, `Detected AEDT 2025.2
  at [redacted-path] (via environment_variable).` and `Detected FEMM at
  [redacted-path] (via standard_location).` -- M10 Task 2's detection ran
  correctly from inside the frozen build too. This file already held
  earlier records from this machine's owner (the M9 acceptance walk); this
  session only appended to it, per instructions, and did not truncate or
  delete anything in it.
- Closed with `taskkill /IM inductor-designer.exe` (a graceful `WM_CLOSE`,
  the same signal a window's own close button sends) -- the process exited,
  and no `.lock` file was left behind next to `m7b.inductor.json`,
  confirming `session.release_lock` ran on `aboutToQuit` exactly as it does
  from source.

Not run in this pass: `--project` against a Generate/Solve action that
actually drives AEDT or FEMM. That is out of scope for Task 3 (freezing),
and this session must not start an AEDT session or run anything marked
`aedt`/`femm` per the house rules; whether PyAEDT behaves identically frozen
is called out as an open question for later verification in the M10 plan
itself.

## Fix wave 1 re-verification: the bundle that ships

After the pyaedt-data-files fix and the QML/DLL prune (see above), the
bundle was rebuilt and relaunched the same way, from the same kind of
directory outside the checkout, against the same sample project:

```powershell
cd C:\Users\fpo01\AppData\Local\Temp\inductor-designer-launch-test-2
C:\Work\git\AnsysPyAEDT\dist\inductor-designer\inductor-designer.exe --project C:\Work\git\AnsysPyAEDT\artifacts\maxwell3d\2025.2-commercial\m7b.inductor.json
```

Observed directly:

- stderr: the same `Loaded m7b.inductor.json: 6 winding(s); opening
  viewer.` line, followed by the same two benign QML `Shortcut` warnings
  from `Main.qml` seen in the original launch above -- no missing-module or
  missing-plugin error of any kind, which is the failure mode an
  over-aggressive prune would produce.
- The process stayed alive and its working set grew from 116 MB
  immediately after launch to 316 MB roughly eight seconds in -- consistent
  with the QML engine and `QtQuick3D` scene initializing, though not itself
  proof of what was drawn.
- The application log recorded a fresh `Application 0.1.0.dev0 starting.`
  plus `Detected AEDT 2025.2` / `Detected FEMM` entries at the time of this
  launch, appended after the existing entries from earlier sessions (none
  of which were touched or removed).
- Closed with `taskkill /IM inductor-designer.exe`: the process exited and
  no `.lock` file was left next to `m7b.inductor.json`, the same clean
  shutdown as the original launch.
- **Not confirmed in this session**: a visible window with the 3D preview
  rendered. The screenshot tool available in this session captured the
  operator's live desktop, which at the time was showing an unrelated
  video call with third-party screen content -- not the frozen
  application's window -- so no visual capture of this specific launch
  exists. The evidence above (clean stderr, no module/plugin errors, a
  live process with growing memory consistent with scene setup, a correct
  log trail, and a clean lock-released shutdown) is the same signature the
  original, visually-confirmed launch produced on every point it shares;
  the one thing it does not independently prove is that the window
  actually painted the toroid-and-windings preview rather than, say, a
  blank `QtQuick3D` surface. A future pass should re-run this launch with
  screen capture available and confirm the render directly.

Not run in this pass either: `--project` against a Generate/Solve action
that actually drives AEDT or FEMM -- same scope and house-rule limits as
the original Task 3 Step 4.

## Known limitations carried forward

- `PySide6/qml/` still ships the plugin trees for the six Qt modules this
  application actually uses (`Qt`, `QtCore`, `QtNetwork`, `QtQml`,
  `QtQuick`, `QtQuick3D`) -- 29 MB after the prune above. Shrinking that
  further would mean pruning within a module this application does use,
  which is a different and much riskier kind of cut than removing modules
  it doesn't; out of scope here.
- `matplotlib` (14 MB) and `PIL` (13 MB) are untouched. Both are pulled in
  by `pyaedt`, not by this application's own code, and neither has been
  verified unused the way the PySide6 modules above were -- removing them
  without that verification risks the same failure mode the QML/DLL prune
  was careful to avoid.

# Wrapping the bundle in an installer (M10 Task 4)

- Plan: [2026-09-01 M10 Windows release](../superpowers/plans/2026-09-01-m10-windows-release.md), Task 4
- Produces: an unsigned, per-user Inno Setup installer that wraps the Task 3
  bundle unmodified.

## Build it

Inno Setup 6 must already be installed on the build machine --
`packaging/build_frozen.py` never installs it for you; that would be a
machine-wide change no packaging script has the authority to make silently.
Get it from <https://jrsoftware.org/isdl.php>. The compiler is
`%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe` at its default install location;
set `INDUCTOR_DESIGNER_ISCC` to override that path.

```powershell
.venv\Scripts\python.exe packaging\build_frozen.py --installer
```

This runs the same catalog build and PyInstaller freeze as the plain command
(see above), then compiles `packaging/installer.iss` with `ISCC.exe`,
passing the running application's own version
(`inductor_designer.__about__.__version__`) in via `/DMyAppVersion` so the
installer can never disagree with the application's About box. Without
`--installer`, the build never looks for `ISCC.exe` at all -- a machine with
only PyInstaller installed can still produce the frozen bundle.

If `ISCC.exe` cannot be found, the build exits with a message naming the
paths it looked in and the download page; it does not attempt to install
Inno Setup, and it does not silently skip the installer step. Verified on
this development machine, which does not have Inno Setup installed:

```text
build_frozen: ISCC.exe (Inno Setup 6's command-line compiler) was not found.
Looked in: C:\Program Files (x86)\Inno Setup 6\ISCC.exe, C:\Program
Files\Inno Setup 6\ISCC.exe. Install Inno Setup 6 from
https://jrsoftware.org/isdl.php, or set INDUCTOR_DESIGNER_ISCC to an
existing ISCC.exe path. This build step never installs it for you.
```

The installer lands at
`dist\installer\inductor-designer-<version>-setup.exe` (`dist/` is
git-ignored, same as the bundle itself).

## What the installer does

`packaging/installer.iss`:

- **Per-user, no administrator required** (`PrivilegesRequired=lowest`,
  ruled by Fabio Posser 2026-09-01) -- an engineering workstation user who
  cannot elevate can still install. Installs to
  `%LOCALAPPDATA%\Programs\PyAEDT Inductor Designer` (Inno's `{userpf}`),
  not `%ProgramFiles%`.
- **Unsigned** for this release (ruled 2026-09-01) -- no signing
  configuration is present; Task 5's release notes carry the resulting
  SmartScreen warning.
- **Version and product name read from `__about__.py`** at build time (via
  `/DMyAppVersion`, above), not hard-coded in the `.iss`.
- Installs a Start Menu shortcut unconditionally, and offers a desktop
  shortcut as an unticked opt-in task.
- Ships the Task 3 bundle unmodified, nothing else -- in particular, no
  sample project (ruled 2026-09-01: nothing installed carries a design).

## Verifying the uninstaller leaves user data alone

**The thing that matters most about this installer.** `%LOCALAPPDATA%\
InductorDesigner` (`adapters/system/environment.py`'s
`application_data_directory()`) holds the user's crash-recovery snapshots
and the application log. The installer must never delete it: losing a
recovery snapshot during an uninstall would destroy unsaved work at the
worst possible moment, and the log is what a support engineer reads
afterwards. `installer.iss` has no `[UninstallDelete]` or `[Dirs]` entry
naming that path at all (see the comment block at the bottom of the
script), so the generated uninstaller has no instruction that could reach
it -- the application creates and writes that directory at runtime, the
installer never does.

A repeatable test, for whoever runs this before a release:

1. Note the directory's current contents, sizes, and modified times:
   `Get-ChildItem -Recurse "$env:LOCALAPPDATA\InductorDesigner" | Select-Object FullName, Length, LastWriteTime`.
2. Install the application into a throwaway per-user location and launch it
   at least once (so a recovery snapshot and a log entry are written).
3. Uninstall it (Settings > Apps, or the `unins000.exe` Inno Setup writes
   under the install directory).
4. Confirm two things:
   - The install directory (`%LOCALAPPDATA%\Programs\PyAEDT Inductor
     Designer`) and the Start Menu / desktop shortcuts are gone.
   - `%LOCALAPPDATA%\InductorDesigner` still exists, and every file already
     in it before the install -- by name, byte count, and modified time --
     is unchanged: `Get-ChildItem -Recurse "$env:LOCALAPPDATA\InductorDesigner" | Select-Object FullName, Length, LastWriteTime`
     again, and diff against step 1's output.

This is the same check M10 Task 4's implementation session ran against this
machine's own `%LOCALAPPDATA%\InductorDesigner\logs\inductor-designer.log`
(which already held real acceptance-walk records from this machine's owner
before this task started) -- see that task's report for the recorded
before/after mtime and byte count.
