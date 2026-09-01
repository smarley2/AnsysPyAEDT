"""M9 follow-up Task 2: an advisory lock on the open project document.

Two windows on one project both save to the same file, so the last writer
silently wins, and window B's startup reconcile rewrites window A's live
`running` manifest to `interrupted` with `results: null`. `ProjectLock` is
what refuses the second window before either of those can happen -- except
when the recorded owner is dead, which is the *ordinary* aftermath of the
crash this whole area exists to survive, and must never block startup.
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
from pathlib import Path

from inductor_designer.adapters.system.project_lock import LockOutcome, ProjectLock


def _document(tmp_path: Path) -> Path:
    return tmp_path / "boost.inductor.json"


def _lock_path(document: Path) -> Path:
    return document.with_name(document.name + ".lock")


def _write_lock(
    tmp_path: Path,
    *,
    pid: int,
    host: str | None = None,
    started_at_utc: str = "2026-09-01T00:00:00+00:00",
) -> Path:
    """Write a lock file by hand, as if left by another build/process --
    not through `ProjectLock` itself, so a test can plant exactly the record
    it wants to probe."""
    document = _document(tmp_path)
    path = _lock_path(document)
    path.write_text(
        json.dumps(
            {
                "pid": pid,
                "host": host if host is not None else platform.node(),
                "startedAtUtc": started_at_utc,
            }
        ),
        encoding="utf-8",
    )
    return document


def _a_pid_that_is_not_running() -> int:
    """Spawn a trivial subprocess, let it exit, and hand back its pid. The
    pid is guaranteed free at the moment this returns (barring the
    documented pid-reuse risk, which is rare enough on a test's timescale to
    accept -- the same risk the brief calls out for production)."""
    completed = subprocess.Popen([sys.executable, "-c", "pass"])
    completed.wait()
    return completed.pid


def test_a_free_document_is_acquired(tmp_path: Path) -> None:
    document = _document(tmp_path)
    lock = ProjectLock(document)

    assert lock.acquire() is LockOutcome.ACQUIRED
    assert lock.path == _lock_path(document)
    assert lock.path.is_file()
    record = json.loads(lock.path.read_text(encoding="utf-8"))
    assert record["pid"] == os.getpid()
    assert record["host"] == platform.node()


def test_a_lock_held_by_this_live_process_is_refused(tmp_path: Path) -> None:
    """Two windows on one project: both save to the same file, so the last
    writer silently wins, and window B's startup reconcile rewrites window
    A's live `running` manifest."""
    document = _document(tmp_path)
    first_window = ProjectLock(document)
    assert first_window.acquire() is LockOutcome.ACQUIRED

    second_window = ProjectLock(document)
    outcome = second_window.acquire()

    assert outcome is LockOutcome.HELD_BY_LIVE_PROCESS
    assert second_window.holder is not None
    assert second_window.holder.pid == os.getpid()
    assert second_window.holder.same_host is True
    # Refused: the first window's lock file must be untouched.
    assert json.loads(first_window.path.read_text(encoding="utf-8"))["pid"] == os.getpid()


def test_a_stale_lock_is_taken_rather_than_blocking(tmp_path: Path) -> None:
    """The rule Task 6 established: a recovery path that refuses to start is
    worse than no recovery. A dead owner's lock is the ORDINARY state after
    the crash this area exists to survive, so it must never wedge the
    application."""
    document = _write_lock(tmp_path, pid=_a_pid_that_is_not_running())

    assert ProjectLock(document).acquire() is LockOutcome.TAKEN_FROM_STALE


def test_a_lock_from_another_host_is_refused_distinctly(tmp_path: Path) -> None:
    """Liveness cannot be probed across hosts, so it is treated as live --
    but the message has to differ, because the remedy is on another
    machine."""
    document = _write_lock(tmp_path, pid=os.getpid(), host="a-different-machine")

    lock = ProjectLock(document)
    outcome = lock.acquire()

    assert outcome is LockOutcome.HELD_BY_LIVE_PROCESS
    assert lock.holder is not None
    assert lock.holder.same_host is False
    assert lock.holder.host == "a-different-machine"


def test_a_malformed_lock_file_does_not_block(tmp_path: Path) -> None:
    """Same reasoning as the naive-timestamp defect in M9 Task 6: an
    unparseable file left by another build must not prevent startup."""
    document = _document(tmp_path)
    _lock_path(document).write_text("not json at all {{{", encoding="utf-8")

    assert ProjectLock(document).acquire() is LockOutcome.TAKEN_FROM_STALE


def test_releasing_removes_only_our_own_lock(tmp_path: Path) -> None:
    """Releasing a lock this process does not own would hand the document to
    a third window while the real owner is still editing."""
    document = _document(tmp_path)
    lock = ProjectLock(document)
    assert lock.acquire() is LockOutcome.ACQUIRED

    # Simulate another window stealing the (by-then-stale) lock back after
    # we acquired it -- the file on disk no longer agrees with what we
    # think we own.
    lock.path.write_text(
        json.dumps({"pid": 999999, "host": "someone-elses-window", "startedAtUtc": "x"}),
        encoding="utf-8",
    )

    lock.release()

    assert lock.path.is_file()
    assert json.loads(lock.path.read_text(encoding="utf-8"))["pid"] == 999999
