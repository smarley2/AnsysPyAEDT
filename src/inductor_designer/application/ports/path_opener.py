"""Port for opening a generated solver project or its run folder (ADR 0007)."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class PathOpener(Protocol):
    def open_path(self, path: Path) -> None: ...
