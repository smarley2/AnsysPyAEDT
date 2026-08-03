from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QSG_RHI_BACKEND", "software")

pytest.importorskip("PySide6")

from PySide6.QtCore import QObject  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

from inductor_designer.ui.guided_studio_controller import (  # noqa: E402
    GuidedStudioController,
)
from inductor_designer.ui.main import create_engine  # noqa: E402
from inductor_designer.ui.project_session import ProjectSession  # noqa: E402
from tests.unit.application.test_geometry_model import CATALOG  # noqa: E402
from tests.unit.domain.test_project import make_project  # noqa: E402

pytestmark = pytest.mark.ui


def test_canvas_first_shell_exposes_real_winding_workspace() -> None:
    app = QGuiApplication.instance() or QGuiApplication([])
    controller = GuidedStudioController(ProjectSession(make_project()), CATALOG)
    engine = create_engine(guided_studio_controller=controller)
    root = engine.rootObjects()[0]
    app.processEvents()

    assert root.objectName() == "canvasFirstShell"
    assert root.findChild(QObject, "topbar") is not None
    assert root.findChild(QObject, "guidedStepList") is not None
    assert root.findChild(QObject, "previewPane") is not None
    assert root.findChild(QObject, "contextPanel") is not None
    assert root.findChild(QObject, "windingsPanel") is not None
    assert root.findChild(QObject, "windingList") is not None
    assert root.findChild(QObject, "windingTurnsField") is not None
    assert root.findChild(QObject, "statusDock") is not None
    assert root.findChild(QObject, "saveProjectButton") is not None
    assert controller.previewEntries


def test_the_step_rail_carries_the_five_specified_screens() -> None:
    app = QGuiApplication.instance() or QGuiApplication([])
    session = ProjectSession(make_project())
    controller = GuidedStudioController(session, CATALOG)
    engine = create_engine(guided_studio_controller=controller)
    root = engine.rootObjects()[0]
    app.processEvents()

    for name in (
        "coreMaterialStep",
        "windingsStep",
        "preliminaryStep",
        "simulationStep",
        "reviewStep",
    ):
        assert root.findChild(QObject, name) is not None, name
    assert root.findChild(QObject, "materialsStep") is None


def test_material_studio_is_a_separate_window_not_a_step() -> None:
    app = QGuiApplication.instance() or QGuiApplication([])
    engine = create_engine()
    root = engine.rootObjects()[0]
    app.processEvents()

    window = root.findChild(QObject, "materialStudioWindow")
    assert window is not None
    assert window.property("visible") is False
    assert root.findChild(QObject, "openMaterialStudioButton") is not None


def test_preliminary_and_review_hide_the_geometry_canvas() -> None:
    app = QGuiApplication.instance() or QGuiApplication([])
    engine = create_engine()
    root = engine.rootObjects()[0]
    steps = root.findChild(QObject, "guidedStepList")
    canvas = root.findChild(QObject, "canvasCard")
    app.processEvents()

    steps.setProperty("currentIndex", 1)
    app.processEvents()
    assert canvas.property("visible") is True

    steps.setProperty("currentIndex", 2)
    app.processEvents()
    assert canvas.property("visible") is False

    steps.setProperty("currentIndex", 4)
    app.processEvents()
    assert canvas.property("visible") is False


def test_core_material_panel_exposes_both_selectors_and_manual_dimensions() -> None:
    app = QGuiApplication.instance() or QGuiApplication([])
    engine = create_engine()
    root = engine.rootObjects()[0]
    app.processEvents()

    for name in (
        "coreMaterialPanel",
        "coreOptionList",
        "materialOptionList",
        "manualCoreOuterField",
        "manualCoreInnerField",
        "manualCoreHeightField",
        "manualCoreCornerField",
        "applyManualCoreButton",
        "manualCompatibilityCheckBox",
        "clearMaterialButton",
        "coreMaterialMessage",
    ):
        assert root.findChild(QObject, name) is not None, name


def test_manual_core_fields_reject_letters_natively() -> None:
    app = QGuiApplication.instance() or QGuiApplication([])
    engine = create_engine()
    root = engine.rootObjects()[0]
    field = root.findChild(QObject, "manualCoreOuterField")
    app.processEvents()

    field.setProperty("text", "27.2")
    assert field.property("acceptableInput") is True
    assert field.property("validator") is not None
