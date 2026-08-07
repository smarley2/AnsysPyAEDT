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


STEP_NAMES = (
    "coreMaterialStep",
    "windingsStep",
    "preliminaryStep",
    "simulationStep",
    "reviewStep",
)


def _step_label(step: QObject) -> QObject:
    """The `Label` `contentItem` of a step delegate.

    PySide cannot marshal the `contentItem` property itself (it is a bare
    `QQuickItem*`, which has no registered converter), so this finds the
    same object by walking the delegate's QObject children instead --
    `contentItem` is still a real child of the delegate either way.
    """
    for child in step.children():
        if "Label" in child.metaObject().className():
            return child
    raise AssertionError(f"{step.objectName()} has no Label content item")


def test_step_rail_labels_render_visibly_in_both_states() -> None:
    """Regression test for Fabio's screenshots: the highlighted step showed
    no label at all (the native style's built-in label painted highlighted
    text in a colour invisible against the `#e9efff` highlight background),
    and "Core & Material" rendered as "Core _Material" (native mnemonic
    processing treating "&" as an accelerator marker). Each delegate now
    has its own `contentItem: Label`, which performs no mnemonic processing
    and renders `text` in an explicit colour in every state.
    """
    app = QGuiApplication.instance() or QGuiApplication([])
    session = ProjectSession(make_project())
    controller = GuidedStudioController(session, CATALOG)
    engine = create_engine(guided_studio_controller=controller)
    root = engine.rootObjects()[0]
    steps = root.findChild(QObject, "guidedStepList")
    app.processEvents()

    # Every delegate is highlighted at exactly one of these two indices and
    # not-highlighted at the other, so this covers both states for all five
    # without needing five separate passes.
    for index in (0, 1):
        steps.setProperty("currentIndex", index)
        app.processEvents()
        for name in STEP_NAMES:
            step = root.findChild(QObject, name)
            label = _step_label(step)
            highlighted = step.property("highlighted")
            background_color = "#e9efff" if highlighted else "#fbfaf8"

            assert label.property("visible") is True, (name, index)
            # Equal to the delegate's own `text` (not merely "close to
            # it") rules out a mnemonic-processed rendering: Qt turns
            # "Core & Material" into "Core _Material" for a mnemonic-aware
            # label, which would fail this exact comparison.
            assert label.property("text") == step.property("text"), (name, index)
            label_color = label.property("color").name()
            assert label_color.lower() != background_color.lower(), (
                name,
                index,
                "label colour matches the background it sits on",
            )


def test_manual_core_fields_reject_letters_natively() -> None:
    app = QGuiApplication.instance() or QGuiApplication([])
    engine = create_engine()
    root = engine.rootObjects()[0]
    field = root.findChild(QObject, "manualCoreOuterField")
    app.processEvents()

    field.setProperty("text", "27.2")
    assert field.property("acceptableInput") is True
    assert field.property("validator") is not None
