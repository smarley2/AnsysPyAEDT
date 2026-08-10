"""Stage progress and cancellation helpers shared by both Maxwell adapters."""

from __future__ import annotations

from inductor_designer.application.ports.maxwell_exporter import StageRecord
from inductor_designer.simulation.run_control import (
    CancellationToken,
    ProgressSink,
    StageEvent,
    StagePhase,
)


def emit(
    progress: ProgressSink | None,
    stage_name: str,
    phase: StagePhase,
    message: str | None,
) -> None:
    if progress is not None:
        progress.emit(StageEvent(stage_name=stage_name, phase=phase, message=message))


def cancelled(token: CancellationToken | None) -> bool:
    return token is not None and token.cancelled


def record_cancellation(
    stages: list[StageRecord],
    progress: ProgressSink | None,
    stage_name: str,
) -> None:
    """Close an interrupted run with evidence of where it stopped."""
    message = f"Run cancelled before stage {stage_name!r}."
    stages.append(StageRecord(name="cancelled", succeeded=False, message=message))
    emit(progress, stage_name, StagePhase.CANCELLED, message)
