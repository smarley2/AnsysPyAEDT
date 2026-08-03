"""Close the Task 16 CI gap: nothing called `main()` / `create_engine` with the
real wiring (five screen controllers, one shared `ProjectSession`, one shared
`SqliteCatalogRepository`, one shared `FileOverlayMaterialRepository`) --
every other UI test builds controllers itself against in-memory fakes. This
runs `main()` itself against a real project, catalog, and compatibility
matrix and confirms the wiring actually reached the QML layer, not just that
nothing raised.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QSG_RHI_BACKEND", "software")

pytest.importorskip("PySide6")

import PySide6.QtGui as QtGui  # noqa: E402
from PySide6.QtCore import QObject  # noqa: E402

import inductor_designer.ui.main as main_module  # noqa: E402
from inductor_designer.adapters.persistence.project_repository import (  # noqa: E402
    ProjectRepository,
)
from inductor_designer.adapters.persistence.schema_repository import (  # noqa: E402
    SchemaRepository,
)
from tests.unit.domain.test_project import make_project_with_material  # noqa: E402
from tools.build_catalog import build  # noqa: E402

pytestmark = pytest.mark.ui

ROOT = Path(__file__).resolve().parents[2]

CONTROLLER_CONTEXT_PROPERTIES = (
    "guidedStudioController",
    "coreMaterialController",
    "preliminaryController",
    "simulationController",
    "reviewController",
)
# objectName -> the QML `controller` property it must be bound to. A dropped
# or reordered controller still lets the panel *load* (its `controller`
# property just defaults to null), so the objectName resolving is not enough
# on its own -- the property value has to be checked too.
PANEL_OBJECT_NAMES = (
    "coreMaterialPanel",
    "windingsPanel",
    "preliminaryPage",
    "simulationPanel",
    "reviewPage",
)

# QQmlApplicationEngine owns the root window it creates, and the engine
# itself has no parent: once the Python wrapper for the engine is garbage
# collected, the root window (and everything under it) goes with it, even
# though other variables still reference the window. Pin the engine here for
# the rest of the test, same idiom as tests/ui/test_flow_screens_qml.py and
# tests/ui/test_winding_panel_qml.py.
_ENGINES: list[object] = []


def test_main_wires_all_five_controllers_and_shared_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    index = tmp_path / "catalog.sqlite"
    build(ROOT / "catalog", ROOT / "schemas" / "catalog", index)

    project_path = tmp_path / "walk.inductor.json"
    ProjectRepository(SchemaRepository(ROOT / "schemas")).save(
        make_project_with_material(), project_path
    )
    matrix_path = ROOT / "compatibility" / "aedt-matrix.yml"

    real_app_cls = QtGui.QGuiApplication
    # `main()` unconditionally constructs `QGuiApplication(sys.argv)`. Under
    # `pytest -m ui` an earlier test module has already created the
    # process-wide singleton, and Qt refuses to build a second one -- reuse
    # it if present, the same `.instance() or QGuiApplication([])` idiom the
    # other ui test modules use, just applied to main()'s own import.
    monkeypatch.setattr(
        QtGui,
        "QGuiApplication",
        lambda argv: real_app_cls.instance() or real_app_cls(argv),
    )
    # Never block on the real event loop.
    monkeypatch.setattr(real_app_cls, "exec", lambda self: 0)

    real_create_engine = main_module.create_engine

    def capturing_create_engine(*args: object, **kwargs: object) -> object:
        engine = real_create_engine(*args, **kwargs)
        # The controllers passed in are parent-less QObjects: `main()` holds
        # the only Python references to them, so once it returns they are
        # garbage collected and `contextProperty()` on the (still alive)
        # engine comes back null. Pin the controllers here too, not just the
        # engine and root window.
        _ENGINES.append((engine, *engine.rootObjects(), *args, *kwargs.values()))
        return engine

    monkeypatch.setattr(main_module, "create_engine", capturing_create_engine)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "inductor-designer",
            "--project",
            str(project_path),
            "--catalog",
            str(index),
            "--matrix",
            str(matrix_path),
        ],
    )

    result = main_module.main()

    assert result == 0
    engine, root, *_kept = _ENGINES[-1]

    context = engine.rootContext()
    for name in CONTROLLER_CONTEXT_PROPERTIES:
        assert context.contextProperty(name) is not None, name
    assert context.contextProperty("projectSession") is not None
    assert context.contextProperty("generationController") is not None
    assert context.contextProperty("materialStudioController") is not None

    for name in PANEL_OBJECT_NAMES:
        panel = root.findChild(QObject, name)
        assert panel is not None, name
        assert panel.property("controller") is not None, name
