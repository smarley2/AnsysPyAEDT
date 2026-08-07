"""Port for opening a generated solver project or its run folder (ADR 0007)."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class PathOpener(Protocol):
    """Implementations may raise `OSError` or `RuntimeError`; callers must
    handle both (e.g. `DesktopPathOpener` raises `RuntimeError` on any
    non-Windows platform, and `OSError` for a missing or unopenable path).
    """

    def open_path(self, path: Path) -> None: ...
