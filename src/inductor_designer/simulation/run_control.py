"""Cooperative cancellation and stage progress, free of Qt and solver imports.

A run is cancelled only between stages: a PyAEDT or pyFEMM call already in
flight is never interrupted, because a half-executed solver call cannot be
described truthfully in a manifest.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class RunCancelled(RuntimeError):
    """Raised at a stage boundary after the user cancelled the run."""

    def __init__(self, stage_name: str | None = None) -> None:
        self.stage_name = stage_name
        super().__init__(
            f"Run cancelled before stage {stage_name!r}."
            if stage_name
            else "Run cancelled."
        )


class CancellationToken:
    """Thread-safe one-way flag; the UI thread cancels, the worker observes."""

    def __init__(self) -> None:
        self._event = threading.Event()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> None:
        self._event.set()

    def raise_if_cancelled(self, stage_name: str | None = None) -> None:
        if self._event.is_set():
            raise RunCancelled(stage_name)


class StagePhase(str, Enum):
    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class StageEvent:
    stage_name: str
    phase: StagePhase
    message: str | None


class ProgressSink(Protocol):
    def emit(self, event: StageEvent) -> None: ...
