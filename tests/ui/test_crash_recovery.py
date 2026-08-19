"""A snapshot newer than the document is offered; recovery never overwrites disk."""

from __future__ import annotations

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
    assert "2026-08-18" in controller.summary


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

    # `configure_application_logging` (run by any earlier test that calls
    # `main()`, e.g. test_main_wiring.py) sets `propagate = False` on this
    # named logger so it never doubles up into the root logger in production.
    # caplog's handler lives on the root logger, so it must be attached here
    # directly or a run of the full suite silently stops capturing anything
    # this logger emits -- a single-file run would never catch that.
    app_logger = logging.getLogger(LOGGER_NAME)
    app_logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
            result = controller.recover()
    finally:
        app_logger.removeHandler(caplog.handler)

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
