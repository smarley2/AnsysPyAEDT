from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QSG_RHI_BACKEND", "software")

pytest.importorskip("PySide6")

from PySide6.QtCore import QObject  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtQml import QQmlEngine, QQmlExpression  # noqa: E402

from inductor_designer.ui.guided_studio_controller import (  # noqa: E402
    GuidedStudioController,
)
from inductor_designer.ui.main import create_engine  # noqa: E402
from inductor_designer.ui.project_session import ProjectSession  # noqa: E402
from tests.unit.application.test_geometry_model import CATALOG  # noqa: E402
from tests.unit.domain.test_project import make_project  # noqa: E402

pytestmark = pytest.mark.ui

# The engine owns the root window; a collected engine takes every findChild
# target with it. See tests/ui/test_winding_panel_qml.py for the full note.
_ENGINES: list[object] = []
_CONTROLLERS: list[object] = []


def open_preview() -> tuple[QGuiApplication, QObject]:
    app = QGuiApplication.instance() or QGuiApplication([])
    session = ProjectSession(make_project())
    controller = GuidedStudioController(session, CATALOG)
    engine = create_engine(guided_studio_controller=controller)
    _ENGINES.append(engine)
    _CONTROLLERS.append(controller)
    app.processEvents()
    return app, engine.rootObjects()[0]


def test_the_preview_pane_exposes_the_toggle_the_checkbox_and_the_canvas() -> None:
    _app, root = open_preview()

    for name in (
        "previewMode3DButton",
        "previewMode2DButton",
        "showCutPlaneCheck",
        "cutPlaneView",
        "cutPlaneCanvas",
        "cutPlaneNote",
        "cutPlaneModel",
    ):
        assert root.findChild(QObject, name) is not None, name


def test_the_two_d_view_is_hidden_until_the_toggle_selects_it() -> None:
    app, root = open_preview()
    view = root.findChild(QObject, "cutPlaneView")

    assert view.property("visible") is False

    root.findChild(QObject, "previewMode2DButton").setProperty("checked", True)
    app.processEvents()

    assert view.property("visible") is True


def test_selecting_two_d_also_shows_the_plane_in_the_three_d_scene() -> None:
    app, root = open_preview()

    root.findChild(QObject, "previewMode2DButton").setProperty("checked", True)
    app.processEvents()

    assert root.findChild(QObject, "showCutPlaneCheck").property("checked") is True
    assert root.findChild(QObject, "cutPlaneModel").property("visible") is True


def test_the_note_reaches_qml_from_the_controller() -> None:
    _app, root = open_preview()

    note = root.findChild(QObject, "cutPlaneNote").property("text")

    assert "Model depth" in note


def _evaluate(view: QObject, expression: str) -> object:
    """Evaluate `expression` as QML sees it, not as Python sees it."""
    query = QQmlExpression(QQmlEngine.contextForObject(view), view, expression)
    # PySide6 returns (value, valueIsUndefined), not the bare value.
    value, is_undefined = query.evaluate()
    assert not query.hasError(), query.error().toString()
    assert not is_undefined, f"{expression} evaluated to undefined"
    return value


def test_the_conductors_reach_qml_as_an_array_the_paint_loop_can_walk() -> None:
    """A Python tuple crosses into QML as an opaque object whose `.length` is
    `undefined`, so the `for` loop in `CutPlaneView.onPaint` runs zero times and
    every conductor glyph silently disappears while the core annulus still
    draws. Nothing else in the suite notices, because the objects all exist and
    no error is ever raised. Asserted through the QML engine rather than on the
    Python dict, because the defect only exists on the far side of the marshal.

    `Array.isArray` is deliberately not asserted: a marshalled sequence is a
    QVariantList, which reports false there even when it works -- the already
    working `previewEntries` does too. The paint loop needs `.length` and
    indexing, so that is what is pinned.
    """
    _app, root = open_preview()
    view = root.findChild(QObject, "cutPlaneView")

    assert _evaluate(view, "drawing.circles.length") > 0
    assert _evaluate(view, "typeof drawing.circles[0].radius_mm") == "number"
    assert _evaluate(view, "typeof drawing.circles[0].into_plane") == "boolean"
    assert _evaluate(view, "typeof drawing.circles[0].color") == "string"
