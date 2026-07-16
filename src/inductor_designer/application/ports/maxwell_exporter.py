from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from inductor_designer.domain.aedt_target import AedtEdition, AedtRelease
from inductor_designer.simulation.maxwell_plan import Maxwell3dDesignPlan

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


@dataclass(frozen=True, slots=True)
class Maxwell3dExportRequest:
    plan: Maxwell3dDesignPlan
    release: AedtRelease
    edition: AedtEdition
    non_graphical: bool
    output_directory: Path
    project_name: str


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

    def succeeded(self) -> bool:
        """A partial design is never successful (design spec §12).

        Success = every recorded stage succeeded and the run reached "save".
        Stage counts differ between the 3D and 2D exporters.
        """
        return (
            bool(self.stages)
            and all(stage.succeeded for stage in self.stages)
            and self.stages[-1].name == "save"
        )


MaxwellExportResult = Maxwell3dExportResult


class Maxwell3dExporter(Protocol):
    def export(self, request: Maxwell3dExportRequest) -> Maxwell3dExportResult: ...
