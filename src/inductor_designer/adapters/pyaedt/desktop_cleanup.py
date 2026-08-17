"""Cleanup for AEDT desktops that outlive a failed launch.

Both adapters open a design with ``new_desktop=True`` and
``close_on_exit=False``, so the desktop process belongs to the run, not to the
interpreter. When the application object fails to initialise, nothing owns that
process: it keeps its gRPC port open, the next launch finds two sessions,
attaches to the wrong one and fails with a message about the desktop it never
opened. Verified on AEDT 2025.2, 2026-08-14.
"""

from __future__ import annotations


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
