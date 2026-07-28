from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from inductor_designer.domain.aedt_target import AedtEdition, AedtRelease
from inductor_designer.simulation.maxwell_plan import (
    GeometryOnlyMaxwell3dPlan,
    Maxwell3dDesignPlan,
)

STAGE_NAMES: tuple[str, ...] = (
    "launch",
    "units",
    "materials",
    "core",
    "windings",
    "terminals",
    "excitations",
    "eddy",
    "region",
    "mesh",
    "setup",
    "matrix",
    "reports",
    "validate",
    "save",
)

GEOMETRY_ONLY_STAGE_NAMES: tuple[str, ...] = (
    "launch",
    "units",
    "core",
    "windings",
    "save",
)


@dataclass(frozen=True, slots=True)
class Maxwell3dExportRequest:
    plan: Maxwell3dDesignPlan
    release: AedtRelease
    edition: AedtEdition
    non_graphical: bool
    output_directory: Path
    project_name: str


@dataclass(frozen=True, slots=True)
class Maxwell3dGeometryOnlyRequest:
    plan: GeometryOnlyMaxwell3dPlan
    release: AedtRelease
    edition: AedtEdition
    non_graphical: bool
    output_directory: Path
    project_name: str
    design_name: str = "Inductor3D_GeometryOnly"


@dataclass(frozen=True, slots=True)
class StageRecord:
    name: str
    succeeded: bool
    message: str


@dataclass(frozen=True, slots=True)
class Maxwell3dExportResult:
    project_path: Path
    design_name: str
    pyaedt_version: str
    stages: tuple[StageRecord, ...]

    def succeeded(self, expected_stage_names: tuple[str, ...]) -> bool:
        """A partial design is never successful (design spec §12).

        Success requires the operation's exact typed stage sequence and every
        stage succeeding.
        """
        return (
            tuple(stage.name for stage in self.stages) == expected_stage_names
            and all(stage.succeeded for stage in self.stages)
        )


MaxwellExportResult = Maxwell3dExportResult


class Maxwell3dExporter(Protocol):
    def export(self, request: Maxwell3dExportRequest) -> Maxwell3dExportResult: ...

    def export_geometry_only(
        self, request: Maxwell3dGeometryOnlyRequest
    ) -> Maxwell3dExportResult: ...
