"""Cancellation bookkeeping shared by both Maxwell adapters."""

from __future__ import annotations

from inductor_designer.application.ports.maxwell_exporter import StageRecord
from inductor_designer.simulation.run_control import (
    ProgressSink,
    StagePhase,
    emit_stage_event,
)


def record_cancellation(
    stages: list[StageRecord],
    progress: ProgressSink | None,
    stage_name: str,
) -> None:
    """Close an interrupted run with evidence of where it stopped."""
    message = f"Run cancelled before stage {stage_name!r}."
    stages.append(StageRecord(name="cancelled", succeeded=False, message=message))
    emit_stage_event(progress, stage_name, StagePhase.CANCELLED, message)
