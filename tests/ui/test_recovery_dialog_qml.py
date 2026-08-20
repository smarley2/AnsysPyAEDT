"""`Main.qml`'s recovery dialog end to end: `Component.onCompleted` opens it
when a controller with an offer is passed to `create_engine`, and its
Recover button actually applies the snapshot through the real
`RecoveryController` -- not a mock standing in for the wiring. Closes the
Task 6 gap where `main.py`'s half of the deliverable (the `setContextProperty`
call, the controller construction, and `recoveryDialog.open()` itself) had
no test at all: each of those three lines could be deleted or replaced with
a no-op and every other UI test still passed.
"""

from __future__ import annotations

import os
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QSG_RHI_BACKEND", "software")

pytest.importorskip("PySide6")

from PySide6.QtCore import QMetaObject, QObject  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

from inductor_designer.adapters.persistence.project_repository import (  # noqa: E402
    ProjectRepository,
)
from inductor_designer.adapters.persistence.recovery_store import (  # noqa: E402
    RecoveryStore,
)
from inductor_designer.adapters.persistence.schema_repository import (  # noqa: E402
    SchemaRepository,
)
from inductor_designer.ui.main import create_engine  # noqa: E402
from inductor_designer.ui.project_session import ProjectSession  # noqa: E402
from inductor_designer.ui.recovery_controller import RecoveryController  # noqa: E402
from tests.unit.domain.test_project import make_project  # noqa: E402

pytestmark = pytest.mark.ui

LATER = datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc)
DOCUMENT_SAVED_AT = datetime(2026, 8, 1, 0, 0, 0, tzinfo=timezone.utc)

# `QQmlApplicationEngine` owns the root window it creates and has no parent
# of its own: once the Python wrapper for the engine (or a controller passed
# to it) is garbage collected, the window goes with it even though other
# variables still reference it. Pin everything here, same idiom as
# test_main_close_dialog.py and test_main_wiring.py.
_KEEPALIVE: list[object] = []


def _click(button: object) -> None:
    assert QMetaObject.invokeMethod(button, "clicked") is True


def _saved_document(tmp_path: Path) -> Path:
    path = tmp_path / "boost.inductor.json"
    ProjectRepository(SchemaRepository(Path("schemas"))).save(make_project(), path)
    timestamp = DOCUMENT_SAVED_AT.timestamp()
    os.utime(path, (timestamp, timestamp))
    return path


def _offered_controller_root(
    tmp_path: Path,
) -> tuple[object, RecoveryController, ProjectSession]:
    app = QGuiApplication.instance() or QGuiApplication([])
    document = _saved_document(tmp_path)
    store = RecoveryStore(
        tmp_path / "recovery", ProjectRepository(SchemaRepository(Path("schemas")))
    )
    store.write(replace(make_project(), description="recovered"), document, now=LATER)
    session = ProjectSession(make_project(), document_path=document)
    controller = RecoveryController(store, session)
    assert controller.available is True

    engine = create_engine(recovery_controller=controller)
    root = engine.rootObjects()[0]
    _KEEPALIVE.append((app, engine, *engine.rootObjects(), controller, session))
    app.processEvents()
    return root, controller, session


def test_the_dialog_opens_on_startup_when_a_recovery_offer_exists(tmp_path: Path) -> None:
    root, _controller, _session = _offered_controller_root(tmp_path)

    dialog = root.findChild(QObject, "recoveryDialog")
    assert dialog is not None
    assert dialog.property("visible") is True


def test_no_offer_leaves_the_dialog_closed() -> None:
    app = QGuiApplication.instance() or QGuiApplication([])
    engine = create_engine()
    root = engine.rootObjects()[0]
    _KEEPALIVE.append((app, engine, *engine.rootObjects()))
    app.processEvents()

    dialog = root.findChild(QObject, "recoveryDialog")
    assert dialog is not None
    assert dialog.property("visible") is False


def test_clicking_recover_applies_the_snapshot_and_closes_the_dialog(
    tmp_path: Path,
) -> None:
    root, _controller, session = _offered_controller_root(tmp_path)

    _click(root.findChild(QObject, "recoverButton"))
    QGuiApplication.instance().processEvents()

    assert session.project.description == "recovered"
    assert session.dirty is True
    assert root.findChild(QObject, "recoveryDialog").property("visible") is False


def test_clicking_discard_clears_the_offer_and_closes_the_dialog_without_changing_the_project(
    tmp_path: Path,
) -> None:
    root, _controller, session = _offered_controller_root(tmp_path)
    original_description = session.project.description

    _click(root.findChild(QObject, "discardRecoveryButton"))
    QGuiApplication.instance().processEvents()

    assert session.project.description == original_description
    assert session.dirty is False
    assert root.findChild(QObject, "recoveryDialog").property("visible") is False
