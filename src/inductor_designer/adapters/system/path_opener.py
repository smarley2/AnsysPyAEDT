"""Hand a file or folder to the Windows shell (ADR 0004, ADR 0007).

The generated solver project is an independent, user-owned output: opening it
never imports, synchronizes, or compares anything back into the project
document.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from pathlib import Path


def _shell_launcher() -> Callable[[str], None]:
    if sys.platform != "win32":
        raise RuntimeError(
            "Opening a path from the application is supported on Windows only."
        )
    return os.startfile


class DesktopPathOpener:
    """Port adapter; `launcher` is injectable so tests never touch the shell."""

    def __init__(self, launcher: Callable[[str], None] | None = None) -> None:
        self._launcher = launcher

    def open_path(self, path: Path) -> None:
        if not path.exists():
            raise FileNotFoundError(f"Cannot open {path}: it does not exist.")
        launcher = self._launcher if self._launcher is not None else _shell_launcher()
        launcher(str(path))
