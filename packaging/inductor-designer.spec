# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the one-folder frozen build.

Built by `packaging/build_frozen.py`, never invoked directly with
`pyinstaller packaging/inductor-designer.spec` -- the catalog index this
spec ships only exists because that script already built it into a
temporary directory and set `INDUCTOR_DESIGNER_BUILD_CATALOG` before
importing PyInstaller (see that module's docstring). `SPECPATH` is a name
PyInstaller injects into this file's namespace at exec time; it is not
undefined despite no import providing it.
"""

import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

sys.path.insert(0, SPECPATH)
from build_frozen import CATALOG_ENV_VAR, REPO_ROOT, resolve_datas  # noqa: E402

_catalog_path = os.environ.get(CATALOG_ENV_VAR)
if not _catalog_path:
    raise SystemExit(
        f"{CATALOG_ENV_VAR} is not set -- run "
        "`.venv\\Scripts\\python.exe packaging\\build_frozen.py`, "
        "not PyInstaller directly. The catalog index this spec ships has no "
        "other source; see build_frozen.py's module docstring."
    )

block_cipher = None

a = Analysis(
    [str(Path(SPECPATH) / "_entry_point.py")],
    pathex=[str(REPO_ROOT / "src")],
    binaries=[],
    # pyaedt (`ansys.aedt.core`) is imported eagerly by PostProcessor3D's
    # FieldsCalculator, which reads
    # `visualization/post/fields_calculator_files/expression_catalog.toml`
    # off disk on every result read (post_common_3d.py, fields_calculator.py)
    # -- none of pyaedt's 114 non-Python data files are on `sys.path`'s Python
    # scan, so without this every result path (live_app.py, maxwell3d.py,
    # maxwell2d.py) raises. `femm` and `ansys.edb` ship zero data files each
    # -- nothing to collect for those.
    datas=resolve_datas(REPO_ROOT, Path(_catalog_path)) + collect_data_files("ansys.aedt.core"),
    hiddenimports=[],
    hookspath=[],
    excludes=[
        # 2026-09-01 release decision (docs/superpowers/plans/2026-09-01-m10-
        # windows-release.md): MCP is not shipped in this version. The
        # `inductor-designer-mcp` console script stays for source installs;
        # nothing in the frozen product references it.
        "inductor_designer.mcp_server",
        "mcp",
        # Dev tooling: exercises this application's own test/lint/type-check
        # suite and is never imported by the shipped application itself.
        "pytest",
        "hypothesis",
        "mypy",
        "ruff",
        # PySide6 Qt modules this application never imports and its QML
        # tree never `import`s. Verified by grepping every `.py` file under
        # `src/` for `from PySide6.Qt* import` (QtCore, QtGui, QtQml,
        # QtQuick3D only) and every `.qml` file under `src/inductor_designer
        # /ui/qml` for `import Qt*` (QtQuick, QtQuick.Controls, QtQuick.
        # Dialogs, QtQuick.Layouts, QtQuick.Window, QtQml.Models, QtQuick3D,
        # QtQuick3D.Helpers only) -- see docs/development/packaging.md for
        # the exact commands. Excluding a module either list actually uses
        # produces a bundle that starts and renders nothing, so this list
        # stops at what neither list names; the frozen launch in Task 3
        # Step 4 confirms the app still renders with these excluded.
        "PySide6.QtWidgets",
        "PySide6.QtPrintSupport",
        "PySide6.QtOpenGLWidgets",
        "PySide6.QtQuickWidgets",
        "PySide6.QtSvgWidgets",
        "PySide6.QtXml",
        "PySide6.QtAxContainer",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebEngineQuick",
        "PySide6.QtWebChannel",
        "PySide6.QtWebSockets",
        "PySide6.QtMultimedia",
        "PySide6.QtMultimediaWidgets",
        "PySide6.QtSpatialAudio",
        "PySide6.QtBluetooth",
        "PySide6.QtNfc",
        "PySide6.QtSensors",
        "PySide6.QtPositioning",
        "PySide6.QtLocation",
        "PySide6.QtSerialPort",
        "PySide6.QtSerialBus",
        "PySide6.QtCharts",
        "PySide6.QtDataVisualization",
        "PySide6.QtGraphs",
        "PySide6.QtGraphsWidgets",
        "PySide6.QtPdf",
        "PySide6.QtPdfWidgets",
        "PySide6.QtHelp",
        "PySide6.QtDesigner",
        "PySide6.QtUiTools",
        "PySide6.QtTest",
        "PySide6.QtSql",
        "PySide6.QtRemoteObjects",
        "PySide6.QtScxml",
        "PySide6.QtStateMachine",
        "PySide6.QtTextToSpeech",
        "PySide6.QtHttpServer",
        "PySide6.QtNetworkAuth",
        "PySide6.QtDBus",
        "PySide6.Qt3DAnimation",
        "PySide6.Qt3DCore",
        "PySide6.Qt3DExtras",
        "PySide6.Qt3DInput",
        "PySide6.Qt3DLogic",
        "PySide6.Qt3DRender",
    ],
    noarchive=False,
)

# `excludes=` above only drops each PySide6 submodule's Python binding
# (.pyd); PyInstaller's PySide6 hook still copies the whole `PySide6/qml/`
# tree for `QQmlApplicationEngine`'s string-based module loading, and a
# handful of that tree's plugin DLLs (chiefly `qml/QtWebEngine/
# qtwebenginequickplugin.dll`, which needs `Qt6WebEngineQuick.dll`, which
# links `Qt6WebEngineCore.dll`) drag the corresponding native Qt6*.dll
# libraries back in even though nothing importable ever loads them. This
# filters `a.binaries`/`a.datas` after Analysis to actually drop that dead
# weight: 195+ MB of WebEngine (already non-functional here -- no
# `QtWebEngineProcess.exe`, no `*.pak`, no `icudtl.dat`), the native Qt6*.dll
# for every other excluded module above (plus QtWebView, unused and absent
# from both import greps in docs/development/packaging.md but never added to
# `excludes=`), the qml/ module directories those DLLs belong to, and the
# English-only app's unused translations/. `opengl32sw.dll` is deliberately
# NOT touched -- the software OpenGL fallback matters on RDP or a GPU-driver-
# less machine, exactly where this application gets used.
_DROP_BINARY_NAMES = frozenset(
    {
        "Qt6WebEngineCore.dll",
        "Qt6WebEngineQuick.dll",
        "Qt6WebEngineQuickDelegatesQml.dll",
        "Qt6Widgets.dll",
        "Qt6OpenGLWidgets.dll",
        "Qt6WebChannel.dll",
        "Qt6WebSockets.dll",
        "Qt6WebView.dll",
        "Qt6WebViewQuick.dll",
        "Qt6Multimedia.dll",
        "Qt6SpatialAudio.dll",
        "Qt6Sensors.dll",
        "Qt6Positioning.dll",
        "Qt6Location.dll",
        "Qt6Charts.dll",
        "Qt6DataVisualization.dll",
        "Qt6Graphs.dll",
        "Qt6Pdf.dll",
        "Qt6Test.dll",
        "Qt6Sql.dll",
        "Qt6RemoteObjects.dll",
        "Qt6Scxml.dll",
        "Qt6StateMachine.dll",
        "Qt6TextToSpeech.dll",
        "Qt63DAnimation.dll",
        "Qt63DCore.dll",
        "Qt63DExtras.dll",
        "Qt63DInput.dll",
        "Qt63DLogic.dll",
        "Qt63DRender.dll",
    }
)

_DROP_QML_MODULES = frozenset(
    {
        "Qt3D",
        "Qt5Compat",
        "QtCharts",
        "QtDataVisualization",
        "QtGraphs",
        "QtLocation",
        "QtMultimedia",
        "QtPositioning",
        "QtRemoteObjects",
        "QtScxml",
        "QtSensors",
        "QtTest",
        "QtTextToSpeech",
        "QtWebChannel",
        "QtWebEngine",
        "QtWebSockets",
        "QtWebView",
    }
)


def _dest_parts(dest_name: str) -> tuple[str, ...]:
    return Path(dest_name.replace("\\", "/")).parts


def _keep_binary(entry: tuple[str, str, str]) -> bool:
    parts = _dest_parts(entry[0])
    if not parts or parts[0] != "PySide6":
        return True
    if parts[-1] in _DROP_BINARY_NAMES:
        return False
    if len(parts) >= 3 and parts[1] == "qml" and parts[2] in _DROP_QML_MODULES:
        return False
    return True


def _keep_data(entry: tuple[str, str, str]) -> bool:
    parts = _dest_parts(entry[0])
    if not parts or parts[0] != "PySide6":
        return True
    if len(parts) >= 3 and parts[1] == "qml" and parts[2] in _DROP_QML_MODULES:
        return False
    if len(parts) >= 2 and parts[1] == "translations":
        return False
    return True


a.binaries = [entry for entry in a.binaries if _keep_binary(entry)]
a.datas = [entry for entry in a.datas if _keep_data(entry)]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="inductor-designer",
    debug=False,
    strip=False,
    upx=False,
    # A console, not a windowed subsystem: `--help`, `--project` parse
    # errors, and the project-lock and resources refusals all print to
    # stderr for a terminal or CI launch (see ui/main.py), and the frozen
    # build must keep that readable. The Start Menu shortcut Task 4 builds
    # can still hide the window if that turns out to matter for the
    # installer's polish; nothing here forecloses that.
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="inductor-designer",
)
