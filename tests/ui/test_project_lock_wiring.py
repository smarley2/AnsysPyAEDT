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
import subprocess
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
from inductor_designer.ui.guided_studio_controller import (  # noqa: E402
    GuidedStudioController,
)
from inductor_designer.ui.main import create_engine  # noqa: E402
from inductor_designer.ui.project_session import ProjectSession  # noqa: E402
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
    """A lock file recording a pid that is guaranteed not running, written
    by hand rather than through `ProjectLock` -- as if left by a previous
    build's crashed process."""
    completed = subprocess.Popen([sys.executable, "-c", "pass"])
    completed.wait()
    _lock_path(document_path).write_text(
        json.dumps(
            {
                "pid": completed.pid,
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
    session = ProjectSession(
        make_project(),
        document_path,
        open_callback=_repository().load,
        lock=lock,
    )
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
