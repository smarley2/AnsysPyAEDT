"""A snapshot newer than the document is offered; recovery never overwrites disk."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

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
from inductor_designer.adapters.system.app_logging import LOGGER_NAME  # noqa: E402
from inductor_designer.ui.project_session import ProjectSession  # noqa: E402
from inductor_designer.ui.recovery_controller import RecoveryController  # noqa: E402
from tests.unit.domain.test_project import make_project  # noqa: E402

pytestmark = pytest.mark.ui

LATER = datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc)
# Fixed well before LATER, and set explicitly on the saved document below --
# the freshness check in RecoveryController compares `LATER` to the
# document's real filesystem mtime, which is "now" (whenever the test
# actually runs) unless pinned back, so leaving it to the OS clock would make
# this comparison depend on which side of `LATER` the test happens to run.
DOCUMENT_SAVED_AT = datetime(2026, 8, 1, 0, 0, 0, tzinfo=timezone.utc)


def _store(tmp_path: Path) -> RecoveryStore:
    return RecoveryStore(
        tmp_path / "recovery", ProjectRepository(SchemaRepository(Path("schemas")))
    )


def _saved_document(tmp_path: Path) -> Path:
    path = tmp_path / "boost.inductor.json"
    ProjectRepository(SchemaRepository(Path("schemas"))).save(make_project(), path)
    timestamp = DOCUMENT_SAVED_AT.timestamp()
    os.utime(path, (timestamp, timestamp))
    return path


def _corrupt_saved_at(store: RecoveryStore, document_path: Path | None, saved_at_utc: str) -> None:
    """Overwrite a freshly-written index's `savedAtUtc` with an arbitrary
    string, simulating an index left behind by another build or mangled out
    of band -- `RecoveryStore.read()` only validates that this field is a
    string at all, not that it is a well-formed, timezone-aware timestamp."""
    store.index_path.write_text(
        json.dumps(
            {
                "documentPath": None if document_path is None else str(document_path),
                "savedAtUtc": saved_at_utc,
            }
        ),
        encoding="utf-8",
    )


def test_no_snapshot_means_no_offer(tmp_path: Path) -> None:
    QGuiApplication.instance() or QGuiApplication([])
    session = ProjectSession(make_project())
    controller = RecoveryController(_store(tmp_path), session)

    assert controller.available is False
    assert controller.recover() is False


def test_a_newer_snapshot_is_offered_and_summarised(tmp_path: Path) -> None:
    QGuiApplication.instance() or QGuiApplication([])
    document = _saved_document(tmp_path)
    store = _store(tmp_path)
    store.write(replace(make_project(), description="unsaved"), document, now=LATER)
    session = ProjectSession(make_project(), document_path=document)
    controller = RecoveryController(store, session)

    assert controller.available is True
    # Local time, so the date must be derived rather than hardcoded: a UTC+12
    # or later machine renders LATER as the following day.
    assert LATER.astimezone().strftime("%Y-%m-%d") in controller.summary


def test_recover_loads_the_snapshot_dirty_without_touching_disk(
    tmp_path: Path,
) -> None:
    QGuiApplication.instance() or QGuiApplication([])
    document = _saved_document(tmp_path)
    on_disk = document.read_text(encoding="utf-8")
    store = _store(tmp_path)
    store.write(replace(make_project(), description="unsaved"), document, now=LATER)
    session = ProjectSession(make_project(), document_path=document)
    controller = RecoveryController(store, session)

    assert controller.recover() is True

    assert session.project.description == "unsaved"
    assert session.dirty is True
    assert document.read_text(encoding="utf-8") == on_disk
    assert controller.available is False


def test_discard_clears_the_snapshot_and_leaves_the_session_alone(
    tmp_path: Path,
) -> None:
    QGuiApplication.instance() or QGuiApplication([])
    document = _saved_document(tmp_path)
    store = _store(tmp_path)
    store.write(replace(make_project(), description="unsaved"), document, now=LATER)
    session = ProjectSession(make_project(), document_path=document)
    controller = RecoveryController(store, session)

    assert controller.discard() is True

    assert store.read() is None
    assert session.project.description == make_project().description
    assert session.dirty is False
    assert controller.available is False


def test_a_snapshot_older_than_the_document_is_not_offered(tmp_path: Path) -> None:
    QGuiApplication.instance() or QGuiApplication([])
    document = _saved_document(tmp_path)
    store = _store(tmp_path)
    store.write(
        replace(make_project(), description="stale"),
        document,
        now=datetime.fromtimestamp(document.stat().st_mtime, tz=timezone.utc)
        - timedelta(minutes=5),
    )
    session = ProjectSession(make_project(), document_path=document)

    assert RecoveryController(store, session).available is False


def test_a_snapshot_for_an_unsaved_project_is_always_offered(tmp_path: Path) -> None:
    QGuiApplication.instance() or QGuiApplication([])
    store = _store(tmp_path)
    store.write(replace(make_project(), description="unsaved"), None, now=LATER)
    session = ProjectSession(make_project())

    assert RecoveryController(store, session).available is True


def test_an_unreadable_snapshot_document_is_not_offered(tmp_path: Path) -> None:
    QGuiApplication.instance() or QGuiApplication([])
    store = _store(tmp_path)
    store.write(replace(make_project(), description="unsaved"), None, now=LATER)
    store.document_path.write_text("{}", encoding="utf-8")
    session = ProjectSession(make_project())
    controller = RecoveryController(store, session)

    assert controller.recover() is False
    assert "recover" in session.statusMessage.casefold()


def test_a_snapshot_for_a_different_document_is_not_offered(tmp_path: Path) -> None:
    """The recovery slot is global to the app-data directory, not per-project.

    A crash while editing project A must not get spliced into project B just
    because B happens to be the one opened next -- that would hand the user
    someone else's unsaved edits under B's name.
    """
    QGuiApplication.instance() or QGuiApplication([])
    document_a = _saved_document(tmp_path)
    document_b = tmp_path / "buck.inductor.json"
    ProjectRepository(SchemaRepository(Path("schemas"))).save(make_project(), document_b)
    store = _store(tmp_path)
    store.write(replace(make_project(), description="unsaved-a"), document_a, now=LATER)
    session = ProjectSession(make_project(), document_path=document_b)

    assert RecoveryController(store, session).available is False


def test_a_load_failure_is_logged_and_leaves_the_application_usable(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    QGuiApplication.instance() or QGuiApplication([])
    store = _store(tmp_path)
    store.write(replace(make_project(), description="unsaved"), None, now=LATER)
    store.document_path.write_text("{}", encoding="utf-8")
    session = ProjectSession(make_project())
    controller = RecoveryController(store, session)

    # `conftest.py`'s autouse `reset_recovery_logger_propagation` fixture
    # undoes `configure_application_logging`'s process-wide
    # `propagate = False` on this logger before every test, so caplog's
    # root-logger handler sees records here without being attached directly.
    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        result = controller.recover()

    assert result is False
    assert session.project.description == make_project().description
    assert session.dirty is False
    assert any(
        "recover" in record.message.casefold() for record in caplog.records
    )


def test_discard_then_a_second_launch_does_not_offer_again(tmp_path: Path) -> None:
    QGuiApplication.instance() or QGuiApplication([])
    document = _saved_document(tmp_path)
    store = _store(tmp_path)
    store.write(replace(make_project(), description="unsaved"), document, now=LATER)
    session = ProjectSession(make_project(), document_path=document)
    RecoveryController(store, session).discard()

    second_session = ProjectSession(make_project(), document_path=document)
    second_controller = RecoveryController(store, second_session)

    assert second_controller.available is False


def test_a_naive_datetime_index_is_treated_as_utc_and_does_not_crash(
    tmp_path: Path,
) -> None:
    """An index written by another build (or mangled out of band) can carry a
    timezone-naive `savedAtUtc`. Comparing that directly against the
    document's timezone-aware mtime used to raise `TypeError` out of
    `RecoveryController.__init__`, taking startup down with it -- the exact
    failure this task exists to prevent."""
    QGuiApplication.instance() or QGuiApplication([])
    document = _saved_document(tmp_path)
    store = _store(tmp_path)
    store.write(replace(make_project(), description="unsaved"), document, now=LATER)
    _corrupt_saved_at(store, document, "2026-08-18T12:00:00")
    session = ProjectSession(make_project(), document_path=document)

    controller = RecoveryController(store, session)

    assert controller.available is True


def test_a_naive_date_only_index_is_treated_as_utc_and_does_not_crash(
    tmp_path: Path,
) -> None:
    QGuiApplication.instance() or QGuiApplication([])
    document = _saved_document(tmp_path)
    store = _store(tmp_path)
    store.write(replace(make_project(), description="unsaved"), document, now=LATER)
    _corrupt_saved_at(store, document, "2026-08-18")
    session = ProjectSession(make_project(), document_path=document)

    controller = RecoveryController(store, session)

    assert controller.available is True


def test_an_unparseable_timestamp_index_is_not_offered_and_does_not_crash(
    tmp_path: Path,
) -> None:
    """Covers the `except ValueError: return None` branch directly: a
    mutant that replaces it with `return snapshot` would offer garbage."""
    QGuiApplication.instance() or QGuiApplication([])
    document = _saved_document(tmp_path)
    store = _store(tmp_path)
    store.write(replace(make_project(), description="unsaved"), document, now=LATER)
    _corrupt_saved_at(store, document, "not-a-date")
    session = ProjectSession(make_project(), document_path=document)

    controller = RecoveryController(store, session)

    assert controller.available is False


def test_a_snapshot_identical_to_the_document_after_edit_and_undo_is_not_offered(
    tmp_path: Path,
) -> None:
    """`undo()` autosaves too (see `ProjectSession.undo`), so editing and then
    undoing back to the last-saved state before a crash leaves a snapshot
    that is *newer* than the document but changes nothing in it. Offering
    that describes work that does not exist, and -- since `recover()` reports
    success -- tells the user it recovered something it did not."""
    QGuiApplication.instance() or QGuiApplication([])
    document = _saved_document(tmp_path)
    store = _store(tmp_path)
    session = ProjectSession(
        make_project(),
        document_path=document,
        autosave_callback=lambda project, path: store.write(project, path, now=LATER),
    )

    session.apply(replace(session.project, description="edited"))
    session.flushAutosave()
    session.undo()
    session.flushAutosave()

    assert RecoveryController(store, session).available is False


def test_an_unreadable_document_falls_through_to_still_offering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The byte-comparison guard must not turn "can't tell" into a crash: an
    `OSError` reading the document (locked, permissions, a race with another
    process) must fall through to still offering, not raise or silently
    withhold the one recovery that does exist."""
    QGuiApplication.instance() or QGuiApplication([])
    document = _saved_document(tmp_path)
    store = _store(tmp_path)
    store.write(replace(make_project(), description="unsaved"), document, now=LATER)
    session = ProjectSession(make_project(), document_path=document)

    real_read_bytes = Path.read_bytes

    def flaky_read_bytes(self: Path) -> bytes:
        if self == document:
            raise OSError("locked by another process")
        return real_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", flaky_read_bytes)

    assert RecoveryController(store, session).available is True


def test_a_relative_and_an_absolute_spelling_of_the_same_document_still_match(
    tmp_path: Path,
) -> None:
    """`main.py` passes `args.project` unresolved, so a launch with a
    relative path and a launch with an absolute one must still recognise the
    same document -- otherwise a valid offer is silently withheld."""
    QGuiApplication.instance() or QGuiApplication([])
    document = _saved_document(tmp_path)
    store = _store(tmp_path)
    store.write(replace(make_project(), description="unsaved"), document, now=LATER)
    # Same file, spelled differently: resolving must collapse the `..` back
    # to the same path `document` already is.
    respelled = tmp_path / "elsewhere" / ".." / document.name
    session = ProjectSession(make_project(), document_path=respelled)

    assert RecoveryController(store, session).available is True


def test_an_unrenderable_timestamp_still_describes_the_snapshot(tmp_path: Path) -> None:
    """A year-9999 or pre-epoch stamp is offerable but not locally renderable.

    `astimezone()` raises OSError on Windows outside the range the platform can
    represent, and the summary caught nothing: the dialog opened with an EMPTY
    message, asking the user to choose Recover or Discard with nothing to go on.
    """
    QGuiApplication.instance() or QGuiApplication([])
    document = _saved_document(tmp_path)
    store = _store(tmp_path)
    store.write(replace(make_project(), description="unsaved"), document, now=LATER)
    _corrupt_saved_at(store, document, "9999-12-31T23:59:59+00:00")
    controller = RecoveryController(store, ProjectSession(make_project(), document_path=document))

    assert controller.available is True
    assert "9999-12-31" in controller.summary


def test_a_failing_discard_still_dismisses_the_offer(tmp_path: Path) -> None:
    """`clear()` unlinks two files and raises on Windows when either is locked.

    Unguarded, the exception escaped into the dialog's `onClicked` handler so
    `close()` never ran -- a modal with NoAutoClose and no Cancel button, whose
    only remaining exit was to press Recover.
    """
    QGuiApplication.instance() or QGuiApplication([])
    document = _saved_document(tmp_path)
    store = _store(tmp_path)
    store.write(replace(make_project(), description="unsaved"), document, now=LATER)
    controller = RecoveryController(store, ProjectSession(make_project(), document_path=document))

    def refuse() -> None:
        raise PermissionError("locked by antivirus")

    store.clear = refuse  # type: ignore[method-assign]

    assert controller.discard() is True
    assert controller.available is False
