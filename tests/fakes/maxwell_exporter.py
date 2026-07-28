from __future__ import annotations

from inductor_designer.application.ports.maxwell_exporter import (
    GEOMETRY_ONLY_STAGE_NAMES,
    STAGE_NAMES,
    Maxwell3dExportRequest,
    Maxwell3dExportResult,
    Maxwell3dGeometryOnlyRequest,
    StageRecord,
)


class RecordingMaxwell3dExporter:
    """Port fake: records requests, never launches AEDT."""

    def __init__(self) -> None:
        self.requests: list[Maxwell3dExportRequest] = []
        self.geometry_only_requests: list[Maxwell3dGeometryOnlyRequest] = []

    def export(self, request: Maxwell3dExportRequest) -> Maxwell3dExportResult:
        self.requests.append(request)
        return Maxwell3dExportResult(
            project_path=request.output_directory / f"{request.project_name}.aedt",
            design_name=request.plan.design_name,
            pyaedt_version="recording-fake",
            stages=tuple(
                StageRecord(name=name, succeeded=True, message="recorded")
                for name in STAGE_NAMES
            ),
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
