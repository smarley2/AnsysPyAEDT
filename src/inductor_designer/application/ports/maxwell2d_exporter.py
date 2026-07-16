from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from inductor_designer.application.ports.maxwell_exporter import MaxwellExportResult
from inductor_designer.domain.aedt_target import AedtEdition, AedtRelease
from inductor_designer.simulation.maxwell2d_plan import Maxwell2dDesignPlan

STAGE_NAMES_2D: tuple[str, ...] = (
    "launch",
    "units",
    "materials",
    "core",
    "conductors",
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
class Maxwell2dExportRequest:
    plan: Maxwell2dDesignPlan
    release: AedtRelease
    edition: AedtEdition
    non_graphical: bool
    output_directory: Path
    project_name: str


class Maxwell2dExporter(Protocol):
    def export(self, request: Maxwell2dExportRequest) -> MaxwellExportResult: ...
