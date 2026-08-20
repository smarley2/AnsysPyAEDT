from __future__ import annotations

import logging
import os
from dataclasses import replace
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtCore import QUrl  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

from inductor_designer.adapters.system.app_logging import LOGGER_NAME  # noqa: E402
from inductor_designer.domain.project import InductorProject  # noqa: E402
from inductor_designer.ui.project_session import ProjectSession  # noqa: E402
from tests.unit.domain.test_project import make_project  # noqa: E402

pytestmark = pytest.mark.ui


def test_session_starts_clean_and_publishes_edits() -> None:
    QGuiApplication.instance() or QGuiApplication([])
    session = ProjectSession(make_project())
    changes: list[int] = []
    session.projectChanged.connect(lambda: changes.append(1))

    assert session.dirty is False
    assert session.documentPath == ""

    session.apply(replace(session.project, description="edited"))

    assert session.project.description == "edited"
    assert session.dirty is True
    assert changes == [1]


def test_saving_persists_once_and_clears_dirty(tmp_path: Path) -> None:
    QGuiApplication.instance() or QGuiApplication([])
    saved: list[InductorProject] = []
    session = ProjectSession(
        make_project(),
        document_path=tmp_path / "boost.inductor.json",
        save_callback=saved.append,
    )
    session.apply(replace(session.project, description="edited"))

    assert session.saveProject() is True

    assert [item.description for item in saved] == ["edited"]
    assert session.dirty is False
    assert session.statusMessage == "Saved"
    assert session.documentPath == str(tmp_path / "boost.inductor.json")


def test_a_failed_save_keeps_the_session_dirty() -> None:
    QGuiApplication.instance() or QGuiApplication([])

    def explode(project: InductorProject) -> None:
        raise OSError("disk full")

    session = ProjectSession(
        make_project(), Path("boost.inductor.json"), save_callback=explode
    )
    session.apply(replace(session.project, description="edited"))

    assert session.saveProject() is False

    assert session.dirty is True
    assert "disk full" in session.statusMessage


def test_a_session_without_a_document_path_cannot_save() -> None:
    QGuiApplication.instance() or QGuiApplication([])
    session = ProjectSession(make_project())

    assert session.saveProject() is False
    assert "no project document" in session.statusMessage.casefold()


def test_saving_clears_the_recovery_snapshot(tmp_path: Path) -> None:
    QGuiApplication.instance() or QGuiApplication([])
    calls: list[int] = []
    session = ProjectSession(
        make_project(),
        document_path=tmp_path / "boost.inductor.json",
        save_callback=lambda project: None,
        recovery_cleanup=lambda: calls.append(1),
    )
    session.apply(replace(session.project, description="edited"))

    assert session.saveProject() is True

    assert calls == [1]


def test_saving_as_clears_the_recovery_snapshot(tmp_path: Path) -> None:
    QGuiApplication.instance() or QGuiApplication([])
    calls: list[int] = []
    session = ProjectSession(
        make_project(),
        save_callback=lambda project: None,
        recovery_cleanup=lambda: calls.append(1),
    )
    session.apply(replace(session.project, description="edited"))

    assert (
        session.saveProjectAs(
            QUrl.fromLocalFile(str(tmp_path / "boost.inductor.json"))
        )
        is True
    )

    assert calls == [1]


def test_a_failing_recovery_cleanup_does_not_fail_a_successful_save(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """`RecoveryStore.clear()` is `unlink(missing_ok=True)` twice, which can
    raise `PermissionError` on Windows when the snapshot is locked (antivirus,
    a sync client). That must not turn a save the user's file actually
    received into a reported failure."""
    QGuiApplication.instance() or QGuiApplication([])

    def explode_cleanup() -> None:
        raise PermissionError("locked by antivirus")

    session = ProjectSession(
        make_project(),
        document_path=tmp_path / "boost.inductor.json",
        save_callback=lambda project: None,
        recovery_cleanup=explode_cleanup,
    )
    session.apply(replace(session.project, description="edited"))

    # `conftest.py`'s autouse `reset_recovery_logger_propagation` fixture
    # undoes `configure_application_logging`'s process-wide
    # `propagate = False` on this logger before every test, so caplog's
    # root-logger handler sees records here without being attached directly.
    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        result = session.saveProject()

    assert result is True
    assert session.dirty is False
    assert session.statusMessage == "Saved"
    assert any(
        "recovery snapshot" in record.message.casefold() for record in caplog.records
    )
