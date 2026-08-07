"""Closing the main window must not silently discard an unsaved project.

Before this fix, `Main.qml`'s `onClosing` only guarded
`materialStudioController.dirty`; a dirty `ProjectSession` (winding, core,
material-pin, or simulation edits) was discarded with no warning. These
tests exercise the real QML wiring end to end: `root.close()` reaches
`onClosing`, which delegates to the testable `requestApplicationClose()`
function, which opens `unsavedProjectDialog` and its Save / Discard / Cancel
buttons.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QSG_RHI_BACKEND", "software")

pytest.importorskip("PySide6")

from PySide6.QtCore import QMetaObject, QObject  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

from inductor_designer.ui.guided_studio_controller import (  # noqa: E402
    GuidedStudioController,
)
from inductor_designer.ui.main import create_engine  # noqa: E402
from inductor_designer.ui.material_studio_controller import (  # noqa: E402
    MaterialStudioController,
)
from inductor_designer.ui.project_session import ProjectSession  # noqa: E402
from tests.fakes.material_repository import InMemoryMaterialRepository  # noqa: E402
from tests.unit.application.test_geometry_model import CATALOG  # noqa: E402
from tests.unit.domain.test_project import make_project  # noqa: E402

pytestmark = pytest.mark.ui

# `QQmlApplicationEngine` owns the root window it creates, and a `QObject`
# passed to `create_engine` is garbage collected the moment nothing else in
# Python still references it. Pin both the engine and the controllers for the
# lifetime of each test, same idiom as test_winding_panel_qml.py and
# test_main_wiring.py.
_KEEPALIVE: list[object] = []


def _click(button: object) -> None:
    assert QMetaObject.invokeMethod(button, "clicked") is True


def _dirty_session_root() -> tuple[object, ProjectSession, object]:
    app = QGuiApplication.instance() or QGuiApplication([])
    session = ProjectSession(make_project(), Path("boost.inductor.json"), lambda _: None)
    controller = GuidedStudioController(session, CATALOG)
    assert controller.setWindingField("w1", "turns", "24") is True
    assert session.dirty is True
    engine = create_engine(guided_studio_controller=controller)
    root = engine.rootObjects()[0]
    _KEEPALIVE.append((app, engine, *engine.rootObjects(), controller, session))
    app.processEvents()
    return root, session, controller


def test_closing_a_dirty_session_stays_open_and_shows_the_dialog() -> None:
    root, session, _controller = _dirty_session_root()

    assert root.property("visible") is True
    root.close()
    QGuiApplication.instance().processEvents()

    assert root.property("visible") is True
    dialog = root.findChild(QObject, "unsavedProjectDialog")
    assert dialog is not None
    assert dialog.property("visible") is True
    assert session.dirty is True


def test_requestApplicationClose_itself_refuses_to_close_and_opens_the_dialog() -> None:
    """The testable function `onClosing` delegates to, called directly."""
    root, _session, _controller = _dirty_session_root()

    assert QMetaObject.invokeMethod(root, "requestApplicationClose") is True
    QGuiApplication.instance().processEvents()

    assert root.findChild(QObject, "unsavedProjectDialog").property("visible") is True
    assert root.property("visible") is True


def test_save_saves_the_session_and_then_closes() -> None:
    app = QGuiApplication.instance() or QGuiApplication([])
    saved: list[object] = []
    session = ProjectSession(make_project(), Path("boost.inductor.json"), saved.append)
    controller = GuidedStudioController(session, CATALOG)
    assert controller.setWindingField("w1", "turns", "24") is True
    engine = create_engine(guided_studio_controller=controller)
    root = engine.rootObjects()[0]
    _KEEPALIVE.append((app, engine, *engine.rootObjects(), controller, session))
    app.processEvents()

    root.close()
    app.processEvents()
    _click(root.findChild(QObject, "unsavedProjectSaveButton"))
    app.processEvents()

    assert saved and saved[0].design.windings[0].turns == 24
    assert session.dirty is False
    assert root.property("visible") is False


def test_a_failed_save_leaves_the_window_and_dialog_open() -> None:
    # No save callback: `session.saveProject()` fails and reports it in the
    # status bar instead of raising, so the dialog must not close the window
    # out from under that message.
    app = QGuiApplication.instance() or QGuiApplication([])
    session = ProjectSession(make_project())  # no document path, no save callback
    controller = GuidedStudioController(session, CATALOG)
    assert controller.setWindingField("w1", "turns", "24") is True
    engine = create_engine(guided_studio_controller=controller)
    root = engine.rootObjects()[0]
    _KEEPALIVE.append((app, engine, *engine.rootObjects(), controller, session))
    app.processEvents()

    root.close()
    QGuiApplication.instance().processEvents()
    _click(root.findChild(QObject, "unsavedProjectSaveButton"))
    QGuiApplication.instance().processEvents()

    assert session.dirty is True
    assert root.property("visible") is True
    assert root.findChild(QObject, "unsavedProjectDialog").property("visible") is True
    assert "Unable to save" in controller.statusMessage


def test_discard_closes_the_window_without_saving() -> None:
    root, session, _controller = _dirty_session_root()

    root.close()
    QGuiApplication.instance().processEvents()
    _click(root.findChild(QObject, "unsavedProjectDiscardButton"))
    QGuiApplication.instance().processEvents()

    assert root.property("visible") is False
    # Discarded, not saved: the session is still dirty, the edit was never
    # persisted.
    assert session.dirty is True


def test_cancel_keeps_the_window_open() -> None:
    root, session, _controller = _dirty_session_root()

    root.close()
    QGuiApplication.instance().processEvents()
    _click(root.findChild(QObject, "unsavedProjectCancelButton"))
    QGuiApplication.instance().processEvents()

    assert root.property("visible") is True
    assert root.findChild(QObject, "unsavedProjectDialog").property("visible") is False
    assert session.dirty is True


def test_a_dirty_material_draft_still_takes_precedence_over_the_project_guard() -> None:
    """Material Studio drafts were already protected; the new project guard
    must not shadow that existing behaviour."""
    app = QGuiApplication.instance() or QGuiApplication([])
    session = ProjectSession(make_project(), Path("boost.inductor.json"), lambda _: None)
    guided_controller = GuidedStudioController(session, CATALOG)
    assert guided_controller.setWindingField("w1", "turns", "24") is True

    material_controller = MaterialStudioController(
        InMemoryMaterialRepository(), now=lambda: "2026-07-19T10:00:00+00:00"
    )
    # `invalidateEditorInput` marks the draft dirty unconditionally, without
    # needing a real import round-trip -- the only property this test needs
    # from Material Studio is `dirty is True`.
    material_controller.invalidateEditorInput("group", "test")
    assert material_controller.dirty is True

    engine = create_engine(
        guided_studio_controller=guided_controller,
        material_studio_controller=material_controller,
    )
    root = engine.rootObjects()[0]
    _KEEPALIVE.append(
        (app, engine, *engine.rootObjects(), guided_controller, material_controller, session)
    )
    app.processEvents()

    root.close()
    app.processEvents()

    assert root.property("visible") is True
    assert root.findChild(QObject, "unsavedProjectDialog").property("visible") is False
    material_window = root.findChild(QObject, "materialStudioWindow")
    assert material_window.property("visible") is True
    assert (
        material_window.findChild(QObject, "dirtyMaterialTransactionDialog").property(
            "visible"
        )
        is True
    )
