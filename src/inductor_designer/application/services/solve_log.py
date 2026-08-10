"""The human-readable stage log for one solve run, written into ``results/``.

M8a writes nothing else into ``results/``: normalized result artifacts belong
to M8b and M8c.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from inductor_designer.simulation.run_control import ProgressSink, StageEvent

SOLVE_LOG_FILENAME = "solve-log.txt"
SOLVE_LOG_ARTIFACT_KIND = "solve-log"


class RecordingProgressSink:
    """Collects every stage event, forwarding to the caller's sink if any."""

    def __init__(self, downstream: ProgressSink | None = None) -> None:
        self.events: list[StageEvent] = []
        self._downstream = downstream

    def emit(self, event: StageEvent) -> None:
        self.events.append(event)
        if self._downstream is not None:
            self._downstream.emit(event)


def solve_log_text(events: Sequence[StageEvent]) -> str:
    return "".join(
        f"{event.stage_name}\t{event.phase.value}\t{event.message or ''}\n"
        for event in events
    )


def write_solve_log(results_directory: Path, events: Sequence[StageEvent]) -> Path:
    results_directory.mkdir(parents=True, exist_ok=True)
    path = results_directory / SOLVE_LOG_FILENAME
    path.write_text(solve_log_text(events), encoding="utf-8")
    return path
