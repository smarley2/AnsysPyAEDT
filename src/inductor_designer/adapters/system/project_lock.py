"""An advisory lock on the project document a window has open on disk.

Two windows opened on the same `*.inductor.json` file both save to it, so the
last writer silently wins -- and a second window's startup reconcile
(`run_recovery.reconcile_unfinished_runs`) can rewrite the first window's
live "running" manifest to "interrupted" mid-run. This lock is what refuses
the second window before either of those can happen.

THE RULE THAT GOVERNS THIS: a stale lock must never block the application.
The ordinary aftermath of the crash this whole area exists to survive is a
lock file whose owner is dead -- not the rare case. A recovery path that
refuses to start because of it is worse than no recovery at all (the same
shape as the malformed-recovery-index defect this milestone already fixed
once), so every unreadable or dead-owner lock is *taken*, never treated as a
reason to stop. Only a lock whose recorded owner is actually alive -- on
this host, or on any other host, since liveness cannot be probed remotely --
is a reason to refuse.
"""

from __future__ import annotations

import ctypes
import enum
import json
import logging
import os
import platform
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from inductor_designer.adapters.system.app_logging import LOGGER_NAME

_logger = logging.getLogger(LOGGER_NAME)

# Same convention AEDT itself uses (`<project>.aedt` -> `<project>.aedt.lock`),
# so the git-ignore rule sits right beside `*.aedt.lock` too.
_LOCK_SUFFIX = ".lock"


class LockOutcome(enum.Enum):
    ACQUIRED = "acquired"
    TAKEN_FROM_STALE = "taken_from_stale"
    HELD_BY_LIVE_PROCESS = "held_by_live_process"


@dataclass(frozen=True, slots=True)
class LockHolder:
    """Who a refused lock says is holding the document."""

    pid: int
    host: str
    started_at_utc: str
    same_host: bool


def _hostname() -> str:
    return platform.node()


def _pid_alive_windows(pid: int) -> bool:
    # PROCESS_QUERY_LIMITED_INFORMATION: the narrowest access right that
    # still lets us learn the process exists, so this never needs privileges
    # beyond what any user process already has.
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    # A denied handle still means "exists but is not ours" -- e.g. another
    # user's session on the same host (RDP/Citrix/fast user switching), or
    # one window elevated and the other not. Reading ERROR_ACCESS_DENIED as
    # "dead" is how a live owner's lock got stolen out from under it; only
    # an OpenProcess failure for any OTHER reason (pid does not exist) means
    # dead, matching the POSIX branch's PermissionError == alive rule below.
    ERROR_ACCESS_DENIED = 5
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if handle:
        kernel32.CloseHandle(handle)
        return True
    return ctypes.get_last_error() == ERROR_ACCESS_DENIED


def _pid_alive(pid: int) -> bool:
    if platform.system() == "Windows":
        return _pid_alive_windows(pid)
    # POSIX: `os.kill(pid, 0)` sends no signal, just checks the pid exists.
    # `PermissionError` means it exists but belongs to another user -- still
    # alive. This branch only runs on the non-Windows CI runner (ADR 0004:
    # Windows is the product platform); ctypes.windll does not exist there.
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


@dataclass(frozen=True, slots=True)
class _LockRecord:
    pid: int
    host: str
    started_at_utc: str


def _read_lock(path: Path) -> _LockRecord | None:
    """The lock's recorded pid/host/start time, or `None` for anything that
    is not a trustworthy record -- missing, unreadable, not JSON, not an
    object, or missing a field. Every one of those must be treated as stale
    rather than raised, per the module docstring's rule."""
    try:
        raw = path.read_text(encoding="utf-8")
        loaded = json.loads(raw)
    except (OSError, ValueError):
        return None
    if not isinstance(loaded, dict):
        return None
    pid = loaded.get("pid")
    host = loaded.get("host")
    started = loaded.get("startedAtUtc")
    # `bool` is a subclass of `int`, so `isinstance(pid, int)` alone lets
    # `{"pid": true}` through as pid 1. The upper bound keeps an
    # out-of-range pid (e.g. 10**12) from reaching `OpenProcess`/`os.kill`,
    # where it raises instead of returning -- the same "must never block
    # startup" shape as the malformed-recovery-index defect. The lower
    # bound excludes 0, which `os.kill(0, 0)` reads as "this process's own
    # group" on POSIX -- always alive, never a real pid.
    if (
        not isinstance(pid, int)
        or isinstance(pid, bool)
        or not 0 < pid < 2**32
        or not isinstance(host, str)
        or not isinstance(started, str)
    ):
        return None
    return _LockRecord(pid=pid, host=host, started_at_utc=started)


def _write_lock_atomic(path: Path, pid: int, host: str, started_at_utc: str) -> None:
    """Same mkstemp-then-`os.replace` shape as `ProjectRepository.save` and
    `RecoveryStore._write_atomic`, so a crash mid-write can never leave a
    torn lock file behind."""
    text = (
        json.dumps({"pid": pid, "host": host, "startedAtUtc": started_at_utc}, indent=2) + "\n"
    )
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
            descriptor = -1
            stream.write(text)
            stream.flush()
        os.replace(temporary_path, path)
    finally:
        if descriptor != -1:
            os.close(descriptor)
        temporary_path.unlink(missing_ok=True)


class ProjectLock:
    """An advisory, per-document lock file: `<document>.lock`.

    `acquire()` never raises and never refuses on a dead or unreadable owner
    -- only on a recorded owner that is actually alive. `release()` removes
    the file only if it still records this process's own pid and host, so a
    lock this process no longer owns (stolen back after going stale, or
    never actually acquired) is left untouched.
    """

    def __init__(self, document_path: Path) -> None:
        self._document_path = document_path
        self.path = document_path.with_name(document_path.name + _LOCK_SUFFIX)
        self.holder: LockHolder | None = None

    def acquire(self) -> LockOutcome:
        taken_from_stale = False
        if self.path.is_file():
            record = _read_lock(self.path)
            if record is None:
                taken_from_stale = True
                _logger.info(
                    "Clearing an unreadable project lock at %s; taking it rather than "
                    "blocking startup.",
                    self.path,
                )
            elif record.host != _hostname():
                self.holder = LockHolder(
                    pid=record.pid,
                    host=record.host,
                    started_at_utc=record.started_at_utc,
                    same_host=False,
                )
                return LockOutcome.HELD_BY_LIVE_PROCESS
            elif _pid_alive(record.pid):
                self.holder = LockHolder(
                    pid=record.pid,
                    host=record.host,
                    started_at_utc=record.started_at_utc,
                    same_host=True,
                )
                return LockOutcome.HELD_BY_LIVE_PROCESS
            else:
                taken_from_stale = True
                _logger.info(
                    "Clearing a stale project lock at %s: pid %s is no longer running.",
                    self.path,
                    record.pid,
                )
        self.holder = None
        _write_lock_atomic(
            self.path,
            os.getpid(),
            _hostname(),
            datetime.now(timezone.utc).isoformat(),
        )
        return LockOutcome.TAKEN_FROM_STALE if taken_from_stale else LockOutcome.ACQUIRED

    def release(self) -> None:
        """Remove the lock file only if it still records this process's own
        pid and host -- releasing a lock this process does not own would
        hand the document to a third window while the real owner still holds
        it."""
        record = _read_lock(self.path)
        if record is None:
            return
        if record.pid == os.getpid() and record.host == _hostname():
            self.path.unlink(missing_ok=True)
