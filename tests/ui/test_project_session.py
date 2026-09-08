from __future__ import annotations

import json
import logging
import os
from dataclasses import replace
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtCore import QUrl  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

from inductor_designer.adapters.persistence.project_repository import (  # noqa: E402
    ProjectRepository,
)
from inductor_designer.adapters.persistence.recovery_store import RecoveryStore  # noqa: E402
from inductor_designer.adapters.persistence.schema_repository import (  # noqa: E402
    SchemaRepository,
)
from inductor_designer.adapters.system.app_logging import LOGGER_NAME  # noqa: E402
from inductor_designer.domain.project import InductorProject  # noqa: E402
from inductor_designer.simulation.run_contracts import RunStatus  # noqa: E402
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
        recovery_cleanup=lambda _path: calls.append(1),
    )
    session.apply(replace(session.project, description="edited"))

    assert session.saveProject() is True

    assert calls == [1]


def test_saving_as_clears_the_old_documents_recovery_snapshot(tmp_path: Path) -> None:
    """Before per-document recovery slots, one global slot meant Save As's
    single `recovery_store.clear()` call always removed the live snapshot, so
    asserting "the cleanup callback fired" was equivalent to "the snapshot is
    gone". It no longer is: `ProjectSession.saveProjectAs` moves
    `self._document_path` to the NEW document BEFORE calling
    `recovery_cleanup`, so a cleanup that re-derives the slot from the
    session's *current* path at call time (as `main.py` used to) clears the
    new document's empty slot and leaves the OLD document's snapshot
    orphaned on disk -- offered back on a later relaunch of the original
    file. This drives a REAL `RecoveryStore` and wires the callbacks the way
    `main.py` does: tracking the path each autosave actually wrote under,
    rather than reading the session's current path at cleanup time."""
    QGuiApplication.instance() or QGuiApplication([])
    store = RecoveryStore(
        tmp_path / "recovery", ProjectRepository(SchemaRepository(Path("schemas")))
    )
    original_path = tmp_path / "boost.inductor.json"
    target_path = tmp_path / "renamed.inductor.json"
    def autosave(project: InductorProject, document_path: Path | None) -> None:
        store.write(project, document_path)

    session = ProjectSession(
        make_project(),
        document_path=original_path,
        save_callback=lambda project: None,
        autosave_callback=autosave,
        recovery_cleanup=store.clear,
    )
    session.apply(replace(session.project, description="edited"))
    session.flushAutosave()
    assert store.read(original_path) is not None

    assert session.saveProjectAs(QUrl.fromLocalFile(str(target_path))) is True

    assert store.read(original_path) is None
    assert store.read(target_path) is None


def test_an_open_moves_the_tracked_slot_so_a_later_save_spares_the_old_snapshot(
    tmp_path: Path,
) -> None:
    """An Open keeps the previous document's snapshot -- on purpose, since
    cancelling a pending autosave is not the same as discarding the work. But
    the slot the cleanup targets has to follow the Open, or the first Save,
    Save As or quit-time Discard made in the NEW document clears the slot the
    OLD document's snapshot lives in, and that work is gone with nothing on
    screen to say so. Tracking the last autosave's path alone is not enough:
    it still points at the old document after an Open, which is how the first
    fix for the Save As orphan introduced this second, opposite defect."""
    QGuiApplication.instance() or QGuiApplication([])
    store = RecoveryStore(
        tmp_path / "recovery", ProjectRepository(SchemaRepository(Path("schemas")))
    )
    first_path = tmp_path / "first.inductor.json"
    second_path = tmp_path / "second.inductor.json"
    def autosave(project: InductorProject, document_path: Path | None) -> None:
        store.write(project, document_path)

    def open_document(path: Path) -> InductorProject:
        return replace(make_project(), description="from disk")

    session = ProjectSession(
        make_project(),
        document_path=first_path,
        save_callback=lambda project: None,
        open_callback=open_document,
        autosave_callback=autosave,
        recovery_cleanup=store.clear,
    )
    session.apply(replace(session.project, description="unsaved work in first"))
    session.flushAutosave()
    assert store.read(first_path) is not None

    assert session.openProject(QUrl.fromLocalFile(str(second_path))) is True
    assert session.saveProject() is True

    # The Save happened in the second document, so only its slot may be
    # touched; the first document's unsaved work must still be recoverable.
    recovered = store.read(first_path)
    assert recovered is not None
    assert store.load_project(recovered).description == "unsaved work in first"


def test_a_failing_recovery_cleanup_does_not_fail_a_successful_save(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """`RecoveryStore.clear()` is `unlink(missing_ok=True)` twice, which can
    raise `PermissionError` on Windows when the snapshot is locked (antivirus,
    a sync client). That must not turn a save the user's file actually
    received into a reported failure."""
    QGuiApplication.instance() or QGuiApplication([])

    def explode_cleanup(_path: Path | None) -> None:
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


def _running_manifest(document_path: Path) -> Path:
    manifest_path = (
        document_path.parent / "runs" / "20260818-101500-maxwell-3d" / "run-manifest.json"
    )
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        json.dumps(
            {
                "runId": "20260818-101500",
                "backend": "maxwell-3d",
                "mode": "generate-and-solve",
                "status": RunStatus.RUNNING.value,
                "startedUtc": "2026-08-18T10:15:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    return manifest_path


def test_opening_a_project_while_a_run_is_busy_skips_reconciliation(
    tmp_path: Path,
) -> None:
    """Reproduces the race a reviewer demonstrated: reconciling on Open can
    catch a run between its own manifest write and this one, permanently
    overwriting a real "succeeded" record with "interrupted". The
    `is_run_busy` check is what closes that window -- without it, this test's
    manifest would be rewritten to `interrupted` by the `openProject` call
    below."""
    QGuiApplication.instance() or QGuiApplication([])
    document_path = tmp_path / "boost.inductor.json"
    document_path.write_text("{}", encoding="utf-8")
    manifest_path = _running_manifest(document_path)
    before = manifest_path.read_text(encoding="utf-8")

    session = ProjectSession(
        make_project(),
        open_callback=lambda path: make_project(),
        is_run_busy=lambda: True,
    )

    assert session.openProject(QUrl.fromLocalFile(str(document_path))) is True
    assert manifest_path.read_text(encoding="utf-8") == before


def test_opening_a_project_while_idle_still_reconciles(tmp_path: Path) -> None:
    """The other half of the guard: with no run in flight, Open must keep
    reconciling a stale "running" marker exactly as before."""
    QGuiApplication.instance() or QGuiApplication([])
    document_path = tmp_path / "boost.inductor.json"
    document_path.write_text("{}", encoding="utf-8")
    manifest_path = _running_manifest(document_path)

    session = ProjectSession(
        make_project(),
        open_callback=lambda path: make_project(),
        is_run_busy=lambda: False,
    )

    assert session.openProject(QUrl.fromLocalFile(str(document_path))) is True
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert document["status"] == RunStatus.INTERRUPTED.value


def test_new_project_replaces_the_document_with_a_blank_unsaved_one(
    tmp_path: Path,
) -> None:
    """File > New has to leave the session in the state a launch with no
    `--project` produces -- including NOT dirty. `dirty` is a comparison
    against the saved project, so a blank project adopted without also being
    adopted as its own saved state would make the Exit guard nag about
    unsaved changes the user never made.
    """
    QGuiApplication.instance() or QGuiApplication([])
    document = tmp_path / "boost.inductor.json"
    document.write_text("{}", encoding="utf-8")
    session = ProjectSession(make_project(), document)
    session.apply(replace(session.project, description="edited"))
    assert session.canUndo is True
    assert session.dirty is True

    assert session.newProject() is True

    assert session.document_path is None
    assert session.documentPath == ""
    assert session.project.design.core is None
    assert session.project.design.windings[0].turns == 1
    # An Open is not an edit and neither is a New: the previous document's
    # history must not be able to overwrite this one.
    assert session.canUndo is False
    assert session.canRedo is False
    assert session.dirty is False


def test_new_project_releases_the_previous_document_lock(tmp_path: Path) -> None:
    """The previous document would stay claimed otherwise: a second window
    could not open the file this session no longer holds."""
    from inductor_designer.adapters.system.project_lock import LockOutcome, ProjectLock

    QGuiApplication.instance() or QGuiApplication([])
    document = tmp_path / "boost.inductor.json"
    document.write_text("{}", encoding="utf-8")
    lock = ProjectLock(document)
    assert lock.acquire() is LockOutcome.ACQUIRED
    session = ProjectSession(make_project(), document, lock=lock)

    assert session.newProject() is True

    second = ProjectLock(document)
    assert second.acquire() is LockOutcome.ACQUIRED
    second.release()
