from __future__ import annotations

from inductor_designer.application.ports.maxwell2d_exporter import (
    STAGE_NAMES_2D,
    Maxwell2dExportRequest,
)
from inductor_designer.application.ports.maxwell_exporter import (
    MaxwellExportResult,
    StageRecord,
)


class RecordingMaxwell2dExporter:
    """Port fake: records requests, never launches AEDT."""

    def __init__(self) -> None:
        self.requests: list[Maxwell2dExportRequest] = []

    def export(self, request: Maxwell2dExportRequest) -> MaxwellExportResult:
        self.requests.append(request)
        return MaxwellExportResult(
            project_path=request.output_directory / f"{request.project_name}.aedt",
            design_name=request.plan.design_name,
            pyaedt_version="recording-fake",
            stages=tuple(
                StageRecord(name=name, succeeded=True, message="recorded")
                for name in STAGE_NAMES_2D
            ),
        )
