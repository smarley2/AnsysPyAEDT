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

  These excludes shrink the *binary and plugin* footprint for Qt libraries
  the app never touches; they do **not** shrink `PySide6/qml/`, which is the
  majority of `PySide6`'s ~384 MB in the bundle (see sizes below).
  `QQmlApplicationEngine` loads QML modules by string at runtime, so
  PyInstaller's hook bundles the entire Qt QML plugin tree rather than
  guessing which of it is reachable -- a known PyInstaller/PySide6
  limitation, not something `excludes` can address without risking exactly
  the breakage this section exists to avoid.

`pyaedt` and `pyfemm` are **not** excluded -- the frozen application talks to
a real installed AEDT/FEMM through them, and they are the largest
contributors to the bundle's size after PySide6.

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
on the development workstation (24 logical processors, Windows 11).

```text
dist/inductor-designer/                514 MB total
├── inductor-designer.exe              21 MB   (console subsystem; see below)
└── _internal/                         494 MB
    ├── PySide6/                       384 MB  (mostly PySide6/qml/, 23 top-level Qt QML modules -- see above)
    ├── numpy.libs/                     21 MB
    ├── matplotlib/                     15 MB
    ├── PIL/                            13 MB
    ├── grpc/                           11 MB  (pyaedt's gRPC transport)
    ├── cryptography/                  9.5 MB
    ├── numpy/                         6.1 MB
    ├── pydantic_core/                 5.1 MB
    ├── ansys_edb_core-*.dist-info/, pyaedt-*.dist-info/, pyfemm-*.dist-info/  -- pyaedt and pyfemm ship, deliberately (see above)
    ├── schemas/                              -- resource 1/4
    ├── compatibility/aedt-matrix.yml         -- resource 2/4
    ├── artifacts/catalog/catalog.sqlite      -- resource 3/4, GENERATED, never copied
    ├── materials-overlay/                    -- resource 4/4
    └── inductor_designer/ui/qml/             -- package data (Main.qml et al.), not one of the four resources
```

Confirmed absent: `inductor_designer/mcp_server`, and no `mcp*`, `pytest*`,
`hypothesis*`, `mypy*`, or `ruff*` directory anywhere under `_internal/`.

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

## Known limitation carried forward

`PySide6/qml/` dominates the bundle and is not reduced by the `excludes`
list (see above) -- this is inherent to using `QQmlApplicationEngine`, not a
gap in this task's exclusion list. Task 4 or a later pass could investigate
PyInstaller's `Tree`/QML-scanning options if bundle size becomes a shipping
concern; out of scope here.
