from __future__ import annotations

from collections.abc import Callable

from inductor_designer.application.ports.maxwell_exporter import (
    GEOMETRY_ONLY_STAGE_NAMES,
    SOLVE_STAGE_NAMES,
    STAGE_NAMES,
    Maxwell3dExportRequest,
    Maxwell3dExportResult,
    Maxwell3dGeometryOnlyRequest,
    StageRecord,
)
from inductor_designer.simulation.run_control import (
    StagePhase,
    emit_stage_event,
    is_cancelled,
)


class RecordingMaxwell3dExporter:
    """Port fake: records requests, never launches AEDT.

    It reproduces the real adapter's observable contract: the stage sequence
    depends on ``solve``, every stage reports progress, and a cancelled token
    stops the sequence and appends a ``cancelled`` stage.
    """

    def __init__(self) -> None:
        self.requests: list[Maxwell3dExportRequest] = []
        self.geometry_only_requests: list[Maxwell3dGeometryOnlyRequest] = []
        # Runs when the named stage is about to execute; lets a test cancel.
        self.on_stage: dict[str, Callable[[], None]] = {}

    def export(self, request: Maxwell3dExportRequest) -> Maxwell3dExportResult:
        self.requests.append(request)
        names = SOLVE_STAGE_NAMES if request.solve else STAGE_NAMES
        return Maxwell3dExportResult(
            project_path=request.output_directory / f"{request.project_name}.aedt",
            design_name=request.plan.design_name,
            pyaedt_version="recording-fake",
            stages=self._run_stages(request, names),
        )

    def export_geometry_only(
        self, request: Maxwell3dGeometryOnlyRequest
    ) -> Maxwell3dExportResult:
        self.geometry_only_requests.append(request)
        return Maxwell3dExportResult(
            project_path=request.output_directory / f"{request.project_name}.aedt",
            design_name=request.design_name,
            pyaedt_version="recording-fake",
            stages=tuple(
                StageRecord(name=name, succeeded=True, message="recorded")
                for name in GEOMETRY_ONLY_STAGE_NAMES
            ),
        )

    def _run_stages(
        self, request: Maxwell3dExportRequest, names: tuple[str, ...]
    ) -> tuple[StageRecord, ...]:
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
            emit_stage_event(
                request.progress, name, StagePhase.SUCCEEDED, "recorded"
            )
        return tuple(stages)
