"""M9 follow-up Task 2: the advisory project lock, wired end to end.

`tests/unit/adapters/system/test_project_lock.py` covers `ProjectLock`
itself. These tests exercise the real QML wiring (`ProjectSession.openProject`
refusing a locked target, `main()` refusing a locked launch target, and a
clean exit releasing the lock) the way `test_app_menu.py` and
`test_main_wiring.py` exercise the rest of `main()`.
"""

from __future__ import annotations

import json
import os
import platform
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QSG_RHI_BACKEND", "software")

pytest.importorskip("PySide6")

import PySide6.QtGui as QtGui  # noqa: E402
from PySide6.QtCore import QMetaObject, QObject, QUrl  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

import inductor_designer.ui.main as main_module  # noqa: E402
from inductor_designer.adapters.persistence.project_repository import (  # noqa: E402
    ProjectRepository,
)
from inductor_designer.adapters.persistence.schema_repository import (  # noqa: E402
    SchemaRepository,
)
from inductor_designer.adapters.system.project_lock import (  # noqa: E402
    LockOutcome,
    ProjectLock,
)
from inductor_designer.domain.project import InductorProject  # noqa: E402
from inductor_designer.ui.guided_studio_controller import (  # noqa: E402
    GuidedStudioController,
)
from inductor_designer.ui.main import create_engine  # noqa: E402
from inductor_designer.ui.project_session import ProjectSession  # noqa: E402
from tests.unit.adapters.system.test_project_lock import (  # noqa: E402
    _a_pid_that_is_not_running,
)
from tests.unit.application.test_geometry_model import CATALOG  # noqa: E402
from tests.unit.domain.test_project import make_project  # noqa: E402
from tools.build_catalog import build  # noqa: E402

pytestmark = pytest.mark.ui

ROOT = Path(__file__).resolve().parents[2]

# Same lifetime idiom as test_app_menu.py / test_main_wiring.py: a QObject
# with no surviving Python reference is garbage collected out from under
# `setContextProperty`, taking the engine's window with it.
_KEEPALIVE: list[object] = []


def _lock_path(document_path: Path) -> Path:
    return document_path.with_name(document_path.name + ".lock")


def _write_dead_lock(document_path: Path) -> None:
    """A lock file recording a pid that is not running, written by hand rather
    than through `ProjectLock` -- as if left by a previous build's crashed
    process.

    The pid comes from `_a_pid_that_is_not_running`, which verifies deadness
    against the lock's own check. It used to be a spawned-and-exited process's
    pid, which read as *alive* while `Popen` still held a handle to it and made
    this test fail intermittently under `pytest -n 8`; that helper's docstring
    has the detail.
    """
    _lock_path(document_path).write_text(
        json.dumps(
            {
                "pid": _a_pid_that_is_not_running(),
                "host": platform.node(),
                "startedAtUtc": "2026-01-01T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )


def _accept_file_dialog(dialog: QObject, path: Path) -> None:
    """Same technique as test_app_menu.py's `_accept_file_dialog`: emitting
    the signal directly, because the offscreen platform's non-native
    `FileDialog.accept()` resets `selectedFile` as part of closing."""
    assert dialog.setProperty("selectedFile", QUrl.fromLocalFile(str(path))) is True
    assert QMetaObject.invokeMethod(dialog, "accepted") is True


def _repository() -> ProjectRepository:
    return ProjectRepository(SchemaRepository(ROOT / "schemas"))


def _loaded_root(document_path: Path) -> tuple[object, ProjectSession, object]:
    """A window already open on `document_path`, its lock already held --
    the state `main.py` leaves a launched window in."""
    app = QGuiApplication.instance() or QGuiApplication([])
    lock = ProjectLock(document_path)
    assert lock.acquire() is LockOutcome.ACQUIRED
    repository = _repository()
    session = ProjectSession(
        make_project(),
        document_path,
        open_callback=repository.load,
        lock=lock,
    )

    # Same shape as `main.py`'s `save_project`: always writes to the
    # session's *current* document path, not the one it was built with, so
    # Save As (which moves that path before saving) writes to the new one.
    def _save(updated_project: InductorProject) -> None:
        assert session.document_path is not None
        repository.save(updated_project, session.document_path)

    session.set_save_callback(_save)

    controller = GuidedStudioController(session, CATALOG)
    engine = create_engine(guided_studio_controller=controller, project_session=session)
    root = engine.rootObjects()[0]
    _KEEPALIVE.append((app, engine, *engine.rootObjects(), controller, session))
    app.processEvents()
    return root, session, controller


def test_opening_a_project_locked_by_a_live_process_refuses_and_leaves_the_current_one_open(
    tmp_path: Path,
) -> None:
    repository = _repository()
    path_a = tmp_path / "a.inductor.json"
    path_b = tmp_path / "b.inductor.json"
    repository.save(make_project(), path_a)
    repository.save(make_project(), path_b)

    # A second window already holds b's lock.
    other_window_lock = ProjectLock(path_b)
    assert other_window_lock.acquire() is LockOutcome.ACQUIRED

    root, session, guided = _loaded_root(path_a)

    open_dialog = root.findChild(QObject, "openProjectDialog")
    _accept_file_dialog(open_dialog, path_b)
    QGuiApplication.instance().processEvents()

    # Refused: still a, and b's lock (someone else's) is untouched.
    assert session.documentPath == str(path_a)
    assert "already open" in guided.statusMessage
    assert path_b.name in guided.statusMessage
    assert json.loads(_lock_path(path_b).read_text(encoding="utf-8"))["pid"] == os.getpid()

    session.release_lock()
    other_window_lock.release()


def test_opening_a_project_with_a_stale_lock_succeeds_and_swaps_the_lock(
    tmp_path: Path,
) -> None:
    repository = _repository()
    path_a = tmp_path / "a.inductor.json"
    path_b = tmp_path / "b.inductor.json"
    repository.save(make_project(), path_a)
    repository.save(make_project(), path_b)
    _write_dead_lock(path_b)

    root, session, _guided = _loaded_root(path_a)
    assert _lock_path(path_a).is_file()

    open_dialog = root.findChild(QObject, "openProjectDialog")
    _accept_file_dialog(open_dialog, path_b)
    QGuiApplication.instance().processEvents()

    assert session.documentPath == str(path_b)
    # The previous document's lock is released only once the swap succeeds.
    assert not _lock_path(path_a).is_file()
    assert json.loads(_lock_path(path_b).read_text(encoding="utf-8"))["pid"] == os.getpid()

    session.release_lock()


def test_save_as_moves_the_lock_to_the_new_document(tmp_path: Path) -> None:
    """Important 3: a Save As that does not move the lock strands the old
    document locked (a second window is wrongly refused there) and leaves
    the newly edited document unlocked (a second window can open it right
    out from under this one)."""
    repository = _repository()
    path_a = tmp_path / "a.inductor.json"
    path_b = tmp_path / "b.inductor.json"
    repository.save(make_project(), path_a)

    root, session, _guided = _loaded_root(path_a)
    assert _lock_path(path_a).is_file()

    save_as_dialog = root.findChild(QObject, "saveProjectAsDialog")
    _accept_file_dialog(save_as_dialog, path_b)
    QGuiApplication.instance().processEvents()

    assert session.documentPath == str(path_b)
    # The old document's lock is gone -- a second window can now open it.
    assert not _lock_path(path_a).is_file()
    assert ProjectLock(path_a).acquire() is LockOutcome.ACQUIRED
    # The new document's lock is held by this process -- a second window
    # opening it is refused, not silently sharing the file.
    assert json.loads(_lock_path(path_b).read_text(encoding="utf-8"))["pid"] == os.getpid()
    assert ProjectLock(path_b).acquire() is LockOutcome.HELD_BY_LIVE_PROCESS

    session.release_lock()
    # The session's lock tracking followed the document, not just the lock
    # file on disk: exit releases b, not a stale reference to a's already-
    # gone lock.
    assert not _lock_path(path_b).is_file()


def test_opening_the_already_open_document_reloads_instead_of_refusing(
    tmp_path: Path,
) -> None:
    """Important 4: there is no Revert menu item, so File > Open on the
    document already open here -- reachable from the unsaved-changes
    guard's Discard button -- is the only way to reload from disk. Routing
    it through the lock like any other target refuses it, blaming this
    window's own pid."""
    repository = _repository()
    path_a = tmp_path / "a.inductor.json"
    repository.save(make_project(), path_a)

    root, session, guided = _loaded_root(path_a)
    lock_record_before = json.loads(_lock_path(path_a).read_text(encoding="utf-8"))

    open_dialog = root.findChild(QObject, "openProjectDialog")
    _accept_file_dialog(open_dialog, path_a)
    QGuiApplication.instance().processEvents()

    assert session.documentPath == str(path_a)
    assert "already open" not in guided.statusMessage
    assert "Reloaded" in guided.statusMessage
    # The lock this window already held is untouched, not re-acquired.
    assert json.loads(_lock_path(path_a).read_text(encoding="utf-8")) == lock_record_before

    session.release_lock()


def test_a_locked_launch_target_is_refused_before_any_window_is_created(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    index = tmp_path / "catalog.sqlite"
    build(ROOT / "catalog", ROOT / "schemas" / "catalog", index)
    project_path = tmp_path / "locked.inductor.json"
    _repository().save(make_project(), project_path)
    matrix_path = ROOT / "compatibility" / "aedt-matrix.yml"

    other_window_lock = ProjectLock(project_path)
    assert other_window_lock.acquire() is LockOutcome.ACQUIRED
    try:
        real_app_cls = QtGui.QGuiApplication
        monkeypatch.setattr(
            QtGui,
            "QGuiApplication",
            lambda argv: real_app_cls.instance() or real_app_cls(argv),
        )
        monkeypatch.setattr(real_app_cls, "exec", lambda self: 0)

        def _must_not_be_called(*_args: object, **_kwargs: object) -> object:
            raise AssertionError("create_engine must not run for a refused launch")

        monkeypatch.setattr(main_module, "create_engine", _must_not_be_called)
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "inductor-designer",
                "--project",
                str(project_path),
                "--catalog",
                str(index),
                "--matrix",
                str(matrix_path),
            ],
        )

        result = main_module.main()

        assert result == 5
        # Refused before touching anything: the other window's lock stands.
        record = json.loads(other_window_lock.path.read_text(encoding="utf-8"))
        assert record["pid"] == os.getpid()
    finally:
        other_window_lock.release()


def test_a_clean_exit_releases_the_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    index = tmp_path / "catalog.sqlite"
    build(ROOT / "catalog", ROOT / "schemas" / "catalog", index)
    project_path = tmp_path / "walk.inductor.json"
    _repository().save(make_project(), project_path)
    matrix_path = ROOT / "compatibility" / "aedt-matrix.yml"
    lock_path = _lock_path(project_path)

    real_app_cls = QtGui.QGuiApplication
    monkeypatch.setattr(
        QtGui,
        "QGuiApplication",
        lambda argv: real_app_cls.instance() or real_app_cls(argv),
    )
    monkeypatch.setattr(real_app_cls, "exec", lambda self: 0)

    real_create_engine = main_module.create_engine

    def capturing_create_engine(*args: object, **kwargs: object) -> object:
        engine = real_create_engine(*args, **kwargs)
        _KEEPALIVE.append((engine, *engine.rootObjects(), *args, *kwargs.values()))
        return engine

    monkeypatch.setattr(main_module, "create_engine", capturing_create_engine)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "inductor-designer",
            "--project",
            str(project_path),
            "--catalog",
            str(index),
            "--matrix",
            str(matrix_path),
        ],
    )

    result = main_module.main()

    assert result == 0
    assert lock_path.is_file()

    # `main()` connected `session.release_lock` to `aboutToQuit` before
    # returning; `exec()` itself is stubbed out above (never blocks), so a
    # normal quit is simulated by emitting the same signal a real
    # `window.close()` / Exit would eventually trigger.
    QGuiApplication.instance().aboutToQuit.emit()

    assert not lock_path.is_file()


def test_a_refused_launch_shows_the_reason_in_a_window() -> None:
    """A refusal printed only to stderr is invisible from a desktop shortcut.

    The click produced no window and no reason, which reads as a crash rather
    than as "your other window already has this project". The refusal now also
    renders on screen, and the message has to carry the pid so the user can
    find the window holding it.
    """
    QGuiApplication.instance() or QGuiApplication([])

    engine = main_module.show_launch_refusal(
        "boost.inductor.json is already open in another window (process 4242)."
    )

    roots = engine.rootObjects()
    assert roots, "the refusal window failed to load"
    window = roots[0]
    assert window.property("visible") is True
    message = window.findChild(QObject, "launchRefusedMessage")
    assert "process 4242" in message.property("text")
    assert window.findChild(QObject, "launchRefusedCloseButton") is not None
    _KEEPALIVE.append(engine)
