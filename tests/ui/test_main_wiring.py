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
from inductor_designer.adapters.system import resources  # noqa: E402
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
    "recoveryController",
    "diagnosticsController",
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


def test_the_startup_log_tells_an_absent_aedt_from_an_unsupported_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two conditions, two remedies, so they must not read alike.

    "No AEDT here" means install it; "AEDT 2024 R2 is here" means install the
    supported release beside it. A log line carrying neither code sends the user
    down the wrong path, which is what advice codes exist to prevent everywhere
    else in this application. The log is also what the diagnostic bundle
    carries, so it is the durable record for a machine support cannot reach.
    """
    import logging

    from inductor_designer.adapters.system import app_logging, installations
    from inductor_designer.application.services.redaction import RedactionContext
    from inductor_designer.domain.aedt_target import AedtRelease
    from inductor_designer.simulation.failure_advice import AdviceCode

    log_path = app_logging.configure_application_logging(
        tmp_path / "logs", RedactionContext()
    )
    logger = logging.getLogger(app_logging.LOGGER_NAME)

    monkeypatch.setattr(installations, "detect_aedt", lambda: None)
    monkeypatch.setattr(installations, "detect_femm", lambda: None)
    monkeypatch.setattr(installations, "detect_unsupported_aedt", lambda: None)
    assert main_module.log_detected_installations(logger) == (None, None)

    unsupported = installations.UnsupportedAedtInstallation(
        release=AedtRelease(2024, 2),
        install_root=tmp_path / "v242" / "AnsysEM",
        route=installations.DetectionRoute.REGISTRY,
    )
    monkeypatch.setattr(installations, "detect_unsupported_aedt", lambda: unsupported)
    assert main_module.log_detected_installations(logger) == (None, unsupported)

    for handler in logger.handlers:
        handler.flush()
    written = log_path.read_text(encoding="utf-8")

    assert AdviceCode.INSTALLATION_AEDT_MISSING in written
    assert AdviceCode.INSTALLATION_AEDT_UNSUPPORTED_RELEASE in written
    # The install root is an absolute path, so it must not survive verbatim.
    assert str(tmp_path) not in written


def test_main_refuses_before_any_window_when_a_shipped_resource_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Task 1's Step 5: the seam's defect surfaces here, on the real `main()`
    startup path, not only inside `resources.py`'s own unit tests. An empty
    override directory stands in for a broken install -- every one of the
    four resources is absent."""
    empty_resource_root = tmp_path / "broken-install"
    empty_resource_root.mkdir()
    monkeypatch.setenv(resources.OVERRIDE_VARIABLE, str(empty_resource_root))

    real_app_cls = QtGui.QGuiApplication
    monkeypatch.setattr(
        QtGui,
        "QGuiApplication",
        lambda argv: real_app_cls.instance() or real_app_cls(argv),
    )
    monkeypatch.setattr(real_app_cls, "exec", lambda self: 0)

    def _must_not_be_called(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("create_engine must not run for a refused launch")

    monkeypatch.setattr(main_module, "create_engine", _must_not_be_called)
    monkeypatch.setattr(sys, "argv", ["inductor-designer"])

    result = main_module.main()

    assert result == 6
    stderr = capsys.readouterr().err
    assert "resources.missing" in stderr
    assert "schemas directory" in stderr
    assert "catalog index" in stderr
    assert "compatibility matrix" in stderr
    assert "material overlay directory" in stderr
    assert str(empty_resource_root) in stderr

    # Important 3: a Start Menu launch has no console, so the redacting log
    # file `configure_application_logging` writes (LOCALAPPDATA redirected
    # into `tmp_path` by the autouse fixture above) is the only durable
    # record -- it must carry the same named list, at error level, not just
    # a count. `caplog` cannot see this: `configure_application_logging`
    # strips every existing handler off this named logger (including one
    # `caplog.at_level(logger=...)` would attach) before this line runs, and
    # sets `propagate = False` before the refusal log call, so a root-level
    # `caplog` handler never sees it either.
    from inductor_designer.adapters.system.app_logging import APP_LOG_FILENAME
    from inductor_designer.adapters.system.environment import log_directory

    log_text = (log_directory() / APP_LOG_FILENAME).read_text(encoding="utf-8")
    refusal_lines = [line for line in log_text.splitlines() if "Launch refused" in line]
    assert len(refusal_lines) == 1
    refusal_line = refusal_lines[0]
    assert "\tERROR\t" in refusal_line
    assert "schemas directory" in refusal_line
    assert "catalog index" in refusal_line
    assert "compatibility matrix" in refusal_line
    assert "material overlay directory" in refusal_line


def test_main_launches_when_a_valid_catalog_flag_supersedes_a_resource_root_lacking_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Important 1: someone debugging with a hand-built catalog passes
    `--catalog` pointing at a real index while the resource root itself (an
    override, here, standing in for an otherwise-incomplete install) has
    none. That is exactly the case the flag exists for -- it must supersede
    the resource, not get refused for the very thing it fixes."""
    partial_resource_root = tmp_path / "partial-install"
    (partial_resource_root / "schemas").mkdir(parents=True)
    (partial_resource_root / "compatibility").mkdir(parents=True)
    (partial_resource_root / "compatibility" / "aedt-matrix.yml").write_text(
        (ROOT / "compatibility" / "aedt-matrix.yml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (partial_resource_root / "materials-overlay").mkdir(parents=True)
    # No artifacts/catalog/catalog.sqlite: the resource root's own catalog is
    # missing on purpose -- the thing the `--catalog` flag below must cover.
    monkeypatch.setenv(resources.OVERRIDE_VARIABLE, str(partial_resource_root))

    hand_built_catalog = tmp_path / "hand-built-catalog.sqlite"
    build(ROOT / "catalog", ROOT / "schemas" / "catalog", hand_built_catalog)

    real_app_cls = QtGui.QGuiApplication
    monkeypatch.setattr(
        QtGui,
        "QGuiApplication",
        lambda argv: real_app_cls.instance() or real_app_cls(argv),
    )
    monkeypatch.setattr(real_app_cls, "exec", lambda self: 0)

    real_create_engine = main_module.create_engine

    def capturing_create_engine(*args: object, **kwargs: object) -> object:
        engine = real_create_engine(*args, **kwargs)
        _ENGINES.append((engine, *engine.rootObjects(), *args, *kwargs.values()))
        return engine

    monkeypatch.setattr(main_module, "create_engine", capturing_create_engine)
    monkeypatch.setattr(
        sys,
        "argv",
        ["inductor-designer", "--catalog", str(hand_built_catalog)],
    )

    result = main_module.main()

    assert result == 0
    assert _ENGINES, "create_engine must have run: the launch must not be refused"
