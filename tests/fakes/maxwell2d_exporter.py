from __future__ import annotations

from collections.abc import Callable

from inductor_designer.application.ports.maxwell2d_exporter import (
    SOLVE_STAGE_NAMES_2D,
    STAGE_NAMES_2D,
    Maxwell2dExportRequest,
)
from inductor_designer.application.ports.maxwell_exporter import (
    MaxwellExportResult,
    StageRecord,
)
from inductor_designer.simulation.run_control import (
    StagePhase,
    emit_stage_event,
    is_cancelled,
)


class RecordingMaxwell2dExporter:
    """Port fake: records requests, never launches AEDT."""

    def __init__(self) -> None:
        self.requests: list[Maxwell2dExportRequest] = []
        # Runs when the named stage is about to execute; lets a test cancel.
        self.on_stage: dict[str, Callable[[], None]] = {}

    def export(self, request: Maxwell2dExportRequest) -> MaxwellExportResult:
        self.requests.append(request)
        names = SOLVE_STAGE_NAMES_2D if request.solve else STAGE_NAMES_2D
        stages: list[StageRecord] = []
        for name in names:
            callback = self.on_stage.get(name)
            if callback is not None:
                callback()
            if is_cancelled(request.cancellation):
                message = f"Run cancelled before stage {name!r}."
                stages.append(
                    StageRecord(name="cancelled", succeeded=False, message=message)
                )
                emit_stage_event(
                    request.progress, name, StagePhase.CANCELLED, message
                )
                break
            emit_stage_event(request.progress, name, StagePhase.STARTED, None)
            stages.append(StageRecord(name=name, succeeded=True, message="recorded"))
            emit_stage_event(request.progress, name, StagePhase.SUCCEEDED, "recorded")
        return MaxwellExportResult(
            project_path=request.output_directory / f"{request.project_name}.aedt",
            design_name=request.plan.design_name,
            pyaedt_version="recording-fake",
            stages=tuple(stages),
        )
