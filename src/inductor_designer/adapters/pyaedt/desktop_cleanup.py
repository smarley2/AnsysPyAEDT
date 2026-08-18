"""Cleanup for AEDT desktops that outlive a failed launch.

Both adapters open a design with ``new_desktop=True`` and
``close_on_exit=False``, so the desktop process belongs to the run, not to the
interpreter. When the application object fails to initialise, nothing owns that
process: it keeps its gRPC port open, the next launch finds two sessions,
attaches to the wrong one and fails with a message about the desktop it never
opened. Verified on AEDT 2025.2, 2026-08-14.
"""

from __future__ import annotations

import os
import signal
from typing import Any, Protocol


class ReleasableApp(Protocol):
    """The slice of a PyAEDT application `release_live_app` needs."""

    def release_desktop(self, close_projects: bool, close_desktop: bool) -> Any: ...


def _desktop_process_id(app: ReleasableApp) -> int | None:
    """The AEDT process behind this application, if PyAEDT will say."""
    desktop = getattr(app, "desktop_class", None)
    for holder in (desktop, app):
        process_id = getattr(holder, "aedt_process_id", None)
        if isinstance(process_id, int) and process_id > 0:
            return process_id
    return None


def _still_running(process_id: int) -> bool:
    try:
        os.kill(process_id, 0)
    except OSError:
        return False
    return True


def release_live_app(app: ReleasableApp) -> str | None:
    """Release one application's desktop; return a diagnostic if it resisted.

    An `electronics_desktop` seat is held until the process exits, out of a pool
    shared with other users, so this does three things in order of preference.

    A release that raises must not propagate out of a `finally` block and leave
    the seat taken -- it also masks whatever failure put us in that block -- so
    anything that goes wrong falls through to `release_orphaned_desktops`.

    A release that *succeeds* is still not proof the seat came back: the runs on
    2026-08-17 called this, PyAEDT reported the desktop released, and two
    headless `ansysedt.exe` processes stayed up holding their seats until they
    were killed by hand. The launch asks for `close_on_exit=False`, so nothing
    else will ever close them. When PyAEDT names the process and it is still
    alive after the release, it is terminated here.
    """
    process_id = _desktop_process_id(app)
    try:
        app.release_desktop(close_projects=True, close_desktop=True)
    except Exception as error:  # noqa: BLE001 - the seat matters more than the error
        released = release_orphaned_desktops()
        return (
            f"release_desktop failed ({type(error).__name__}: {error}); "
            f"released {released} registered session(s) instead."
        )
    if process_id is None or not _still_running(process_id):
        return None
    try:
        os.kill(process_id, signal.SIGTERM)
    except OSError as error:
        return (
            f"AEDT process {process_id} survived release_desktop and could not "
            f"be terminated ({error}); its licence seat is still held."
        )
    return f"AEDT process {process_id} survived release_desktop and was terminated."


def release_orphaned_desktops() -> int:
    """Release every desktop session PyAEDT still holds; return how many.

    Best effort by construction: it runs on a path that is already failing, and
    a cleanup that raises would replace the real diagnostic with its own.
    """
    try:
        from ansys.aedt.core.internal.desktop_sessions import _desktop_sessions
    except Exception:  # noqa: BLE001 - no registry means nothing to release
        return 0
    released = 0
    for session in list(_desktop_sessions.values()):
        try:
            session.release_desktop(close_projects=True, close_on_exit=True)
            released += 1
        except Exception:  # noqa: BLE001 - one stuck session must not stop the rest
            continue
    return released
