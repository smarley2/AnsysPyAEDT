from __future__ import annotations

import logging
import os
import time
from dataclasses import replace
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtCore import QUrl  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

from inductor_designer.adapters.system.app_logging import (  # noqa: E402
    LOGGER_NAME,
    configure_application_logging,
)
from inductor_designer.application.services.redaction import RedactionContext  # noqa: E402
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

    # `conftest.py`'s autouse `reset_recovery_logger_propagation` fixture
    # undoes `configure_application_logging`'s process-wide
    # `propagate = False` on this logger before every test, so caplog's
    # root-logger handler sees records here without being attached directly.
    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        session.flushAutosave()

    assert session.project.description == "edited"
    assert session.dirty is True
    assert session.canUndo is True
    assert session.undo() is True
    assert session.project.description == make_project().description
    assert any("autosave" in record.message.casefold() for record in caplog.records)


def test_opening_a_document_within_the_debounce_window_cancels_the_pending_autosave(
    tmp_path: Path,
) -> None:
    """Edit A, then Open B before the debounce timer fires: A's pending
    snapshot write must be cancelled, not carried out on B's behalf. Without
    cancelling it, the still-running timer would fire after Open and hand the
    autosave callback the freshly opened (clean, on-disk) project -- silently
    overwriting the one snapshot actually worth keeping."""
    calls: list[tuple[InductorProject, Path | None]] = []
    cleanups: list[int] = []
    opened = replace(make_project(), description="from disk")
    session = _session(
        calls,
        open_callback=lambda path: opened,
        recovery_cleanup=lambda: cleanups.append(1),
    )
    session.apply(replace(session.project, description="edited A"))

    # An absolute path under `tmp_path`, not a bare relative name: `openProject`
    # acquires a real `ProjectLock` for whatever path it is given, which
    # creates a `<path>.lock` file beside it -- a relative path here wrote
    # that lock into the repository's working directory instead of this
    # test's own sandbox.
    other_path = tmp_path / "other.inductor.json"
    assert session.openProject(QUrl.fromLocalFile(str(other_path))) is True

    session.flushAutosave()

    assert calls == []
    # Cancelling is not the same as discarding. A's snapshot is the one worth
    # keeping, so Open must leave it on disk: clearing it here would pass the
    # assertion above while destroying the very recovery this task exists for.
    assert cleanups == []


def test_flushing_stops_the_timer_and_a_second_flush_writes_nothing() -> None:
    calls: list[tuple[InductorProject, Path | None]] = []
    session = _session(calls)
    session.apply(replace(session.project, description="edited"))
    assert session._autosave_timer.isActive() is True

    session.flushAutosave()
    session.flushAutosave()

    assert session._autosave_timer.isActive() is False
    assert len(calls) == 1


def test_the_debounce_timer_itself_triggers_the_autosave() -> None:
    """The only thing wired to `flushAutosave` in production is the QTimer's
    own `timeout` signal (see `ProjectSession.__init__`). Every other test in
    this file calls `flushAutosave()` directly, so deleting that `connect`
    call would leave them all green while autosave never fired in the shipped
    app. This test never calls `flushAutosave()` itself -- only a real timer
    firing on a real event loop can make it pass."""
    app = QGuiApplication.instance() or QGuiApplication([])
    calls: list[tuple[InductorProject, Path | None]] = []
    session = ProjectSession(
        make_project(),
        autosave_callback=lambda project, path: calls.append((project, path)),
        debounce_ms=20,
    )
    session.apply(replace(session.project, description="edited"))

    deadline = time.monotonic() + 5.0
    while not calls and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)

    assert [project.description for project, _ in calls] == ["edited"]


def test_an_autosave_failure_warning_is_redacted_on_disk(tmp_path: Path) -> None:
    """The `OSError` text logged on autosave failure can carry the recovery
    snapshot's absolute path, which contains the user's login name. The
    redacting formatter is supposed to catch this like any other log line --
    this proves it actually does, by inspecting the bytes written to disk."""
    log_path = configure_application_logging(
        tmp_path / "logs", RedactionContext(user_names=("jane.doe",))
    )

    def explode(project: InductorProject, path: Path | None) -> None:
        raise OSError(r"cannot write C:\Users\jane.doe\recovery.inductor.json")

    session = ProjectSession(make_project(), autosave_callback=explode)
    session.apply(replace(session.project, description="edited"))

    session.flushAutosave()
    logging.getLogger(LOGGER_NAME).handlers[0].flush()

    written = log_path.read_bytes()
    assert b"jane.doe" not in written
    assert b"Users" not in written
