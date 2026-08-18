from __future__ import annotations

import logging
import os
from dataclasses import replace
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtGui import QGuiApplication  # noqa: E402

from inductor_designer.adapters.system.app_logging import LOGGER_NAME  # noqa: E402
from inductor_designer.domain.project import InductorProject  # noqa: E402
from inductor_designer.ui.project_session import ProjectSession  # noqa: E402
from tests.unit.domain.test_project import make_project  # noqa: E402

pytestmark = pytest.mark.ui


def _session(
    calls: list[tuple[InductorProject, Path | None]], **kwargs: object
) -> ProjectSession:
    QGuiApplication.instance() or QGuiApplication([])
    return ProjectSession(
        make_project(),
        autosave_callback=lambda project, path: calls.append((project, path)),
        **kwargs,  # type: ignore[arg-type]
    )


def test_an_edit_autosaves_the_edited_project() -> None:
    calls: list[tuple[InductorProject, Path | None]] = []
    session = _session(calls)
    session.apply(replace(session.project, description="edited"))

    session.flushAutosave()

    assert [project.description for project, _ in calls] == ["edited"]


def test_autosave_does_not_clear_dirty_so_generate_stays_gated() -> None:
    calls: list[tuple[InductorProject, Path | None]] = []
    session = _session(calls)
    session.apply(replace(session.project, description="edited"))

    session.flushAutosave()

    assert session.dirty is True


def test_autosave_never_writes_the_project_document(tmp_path: Path) -> None:
    document = tmp_path / "boost.inductor.json"
    document.write_text("{}", encoding="utf-8")
    calls: list[tuple[InductorProject, Path | None]] = []
    session = _session(calls, document_path=document)
    session.apply(replace(session.project, description="edited"))

    session.flushAutosave()

    assert document.read_text(encoding="utf-8") == "{}"
    assert calls[0][1] == document


def test_undo_autosaves_the_restored_project() -> None:
    calls: list[tuple[InductorProject, Path | None]] = []
    session = _session(calls)
    session.apply(replace(session.project, description="edited"))
    session.flushAutosave()
    calls.clear()

    session.undo()
    session.flushAutosave()

    assert [project.description for project, _ in calls] == [
        make_project().description
    ]


def test_an_autosave_failure_is_reported_and_does_not_raise() -> None:
    QGuiApplication.instance() or QGuiApplication([])

    def explode(project: InductorProject, path: Path | None) -> None:
        raise OSError("disk full")

    session = ProjectSession(make_project(), autosave_callback=explode)
    session.apply(replace(session.project, description="edited"))

    session.flushAutosave()

    assert "autosave" in session.statusMessage.casefold()
    assert session.project.description == "edited"


def test_flush_without_a_pending_edit_writes_nothing() -> None:
    calls: list[tuple[InductorProject, Path | None]] = []
    session = _session(calls)

    session.flushAutosave()

    assert calls == []


def test_two_rapid_edits_produce_one_write_carrying_the_second_edit() -> None:
    """The debounce must coalesce to the LAST edit, not fire once per edit."""
    calls: list[tuple[InductorProject, Path | None]] = []
    session = _session(calls)

    session.apply(replace(session.project, description="first"))
    session.apply(replace(session.project, description="second"))

    session.flushAutosave()

    assert [project.description for project, _ in calls] == ["second"]


def test_an_autosave_oserror_leaves_project_dirty_and_undo_history_untouched(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A disk-full or permission error during autosave must not lose work.

    The in-memory project, the dirty flag and the undo stack all describe the
    edit the user made -- autosave failing is purely a recovery-copy problem,
    and must not unwind any of them.
    """

    def explode(project: InductorProject, path: Path | None) -> None:
        raise OSError("disk full")

    session = ProjectSession(make_project(), autosave_callback=explode)
    session.apply(replace(session.project, description="edited"))

    # caplog's handler lives on the root logger; attach it to this logger
    # directly too, because an earlier test in the same xdist worker may have
    # called `configure_application_logging`, which sets
    # `propagate = False` on it for the rest of the process.
    logger = logging.getLogger(LOGGER_NAME)
    logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
            session.flushAutosave()
    finally:
        logger.removeHandler(caplog.handler)

    assert session.project.description == "edited"
    assert session.dirty is True
    assert session.canUndo is True
    assert session.undo() is True
    assert session.project.description == make_project().description
    assert any("autosave" in record.message.casefold() for record in caplog.records)
