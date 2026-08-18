"""Cancellation and failure bookkeeping shared by both Maxwell adapters."""

from __future__ import annotations

import logging
from typing import Protocol

from inductor_designer.adapters.system.app_logging import LOGGER_NAME
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


class HasDesktopMessages(Protocol):
    def desktop_messages(self) -> tuple[str, ...]: ...


def log_desktop_messages(app: HasDesktopMessages, stage: str) -> None:
    """Record why AEDT failed, while the session that knows still exists.

    The channel dies with the session at `release_live_app`, so this must run
    from the stage-failure handler, before that release. A read that raises
    is logged and swallowed: the run still reports its own stage error, never
    this one.
    """
    logger = logging.getLogger(LOGGER_NAME)
    try:
        messages = app.desktop_messages()
    except Exception as error:  # noqa: BLE001 - capture never masks the real failure
        logger.warning("Could not read AEDT messages after %s failed: %s", stage, error)
        return
    for line in messages:
        logger.error("AEDT [%s]: %s", stage, line)
