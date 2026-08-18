from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtGui import QGuiApplication  # noqa: E402

from inductor_designer.ui.guided_studio_controller import (  # noqa: E402
    GuidedStudioController,
)
from inductor_designer.ui.project_session import UNDO_DEPTH, ProjectSession  # noqa: E402
from tests.unit.application.test_geometry_model import CATALOG  # noqa: E402
from tests.unit.domain.test_project import make_project  # noqa: E402

pytestmark = pytest.mark.ui


def _session(**kwargs: object) -> ProjectSession:
    QGuiApplication.instance() or QGuiApplication([])
    return ProjectSession(make_project(), **kwargs)  # type: ignore[arg-type]


def test_a_fresh_session_can_neither_undo_nor_redo() -> None:
    session = _session()
    assert session.canUndo is False
    assert session.canRedo is False
    assert session.undo() is False
    assert session.redo() is False


def test_undo_restores_the_previous_project_and_enables_redo() -> None:
    session = _session()
    session.apply(replace(session.project, description="first"))
    session.apply(replace(session.project, description="second"))

    assert session.undo() is True
    assert session.project.description == "first"
    assert session.canRedo is True
    assert session.redo() is True
    assert session.project.description == "second"


def test_undo_emits_project_changed_so_every_screen_refreshes() -> None:
    session = _session()
    session.apply(replace(session.project, description="edited"))
    changes: list[int] = []
    session.projectChanged.connect(lambda: changes.append(1))

    session.undo()

    assert changes == [1]


def test_a_new_edit_after_undo_clears_the_redo_history() -> None:
    session = _session()
    session.apply(replace(session.project, description="first"))
    session.undo()
    session.apply(replace(session.project, description="other"))

    assert session.canRedo is False


def test_undo_back_to_the_saved_project_clears_dirty(tmp_path: Path) -> None:
    path = tmp_path / "boost.inductor.json"
    path.write_text("{}", encoding="utf-8")
    session = _session(document_path=path, save_callback=lambda project: None)
    session.saveProject()
    session.apply(replace(session.project, description="edited"))
    assert session.dirty is True

    session.undo()

    assert session.dirty is False


def test_undo_history_is_bounded(tmp_path: Path) -> None:
    session = _session()
    for index in range(UNDO_DEPTH + 10):
        session.apply(replace(session.project, description=f"edit {index}"))

    undone = 0
    while session.undo():
        undone += 1

    assert undone == UNDO_DEPTH


def test_opening_a_project_clears_the_history(tmp_path: Path) -> None:
    opened = replace(make_project(), description="from disk")
    session = _session(open_callback=lambda path: opened)
    session.apply(replace(session.project, description="edited"))

    from PySide6.QtCore import QUrl

    assert session.openProject(QUrl.fromLocalFile(str(tmp_path / "other.json"))) is True
    assert session.canUndo is False
    assert session.canRedo is False


def test_an_edit_that_fails_validation_does_not_push_a_history_entry() -> None:
    """Architecture rule 12: a failed edit preserves the last valid project.

    `GuidedStudioController.setOperatingPointField` validates before ever
    calling `session.apply(...)` -- a bad value raises inside the controller
    and `apply()` is never reached. If a future change moved validation
    inside `apply()` (or dropped it) and let a rejected project through, this
    would fail by finding `session.canUndo` true with only one, unrejected,
    edit behind it.
    """
    session = _session()
    controller = GuidedStudioController(session, CATALOG)
    original = session.project

    accepted = controller.setOperatingPointField("frequencyHz", "not-a-number")

    assert accepted is False
    assert session.canUndo is False
    assert session.project == original
