from __future__ import annotations

from collections.abc import Sequence
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

from inductor_designer.application.ports.maxwell_exporter import StageRecord
from inductor_designer.application.services.maxwell_export import (
    MaxwellExportBlocked,
    export_femm2d,
    export_maxwell2d,
    export_maxwell3d,
)

if TYPE_CHECKING:
    from inductor_designer.application.ports.catalog import CatalogRepository
    from inductor_designer.application.ports.femm_solver import FemmSolver
    from inductor_designer.application.ports.maxwell2d_exporter import Maxwell2dExporter
    from inductor_designer.application.ports.maxwell_exporter import Maxwell3dExporter
    from inductor_designer.domain.project import InductorProject
    from inductor_designer.simulation.capabilities import CapabilitySnapshot


class GenerationBackend(str, Enum):
    MAXWELL_3D = "Maxwell 3D"
    MAXWELL_2D = "Maxwell 2D (Ansys)"
    FEMM_2D = "FEMM 2D"


def _stage_lines(stages: Sequence[StageRecord]) -> tuple[str, ...]:
    return tuple(
        f"{stage.name}: {'ok' if stage.succeeded else 'FAILED'} - {stage.message}"
        for stage in stages
    )


def run_generation(
    backend: GenerationBackend,
    project: InductorProject,
    catalog: CatalogRepository,
    capabilities: CapabilitySnapshot,
    output_directory: Path,
    *,
    maxwell3d_exporter: Maxwell3dExporter,
    maxwell2d_exporter: Maxwell2dExporter,
    femm_solver: FemmSolver,
) -> tuple[str, ...]:
    """Run one generation backend and return display lines. Never raises."""
    try:
        if backend is GenerationBackend.MAXWELL_3D:
            outcome = export_maxwell3d(
                project, catalog, maxwell3d_exporter, output_directory, capabilities=capabilities
            )
            return _stage_lines(outcome.result.stages)
        if backend is GenerationBackend.MAXWELL_2D:
            outcome = export_maxwell2d(
                project, catalog, maxwell2d_exporter, output_directory, capabilities=capabilities
            )
            return _stage_lines(outcome.result.stages)
        femm_outcome = export_femm2d(
            project, catalog, femm_solver, output_directory, capabilities=capabilities
        )
        lines = [f"fem: {femm_outcome.result.fem_path}"]
        results = femm_outcome.result.results
        for winding in femm_outcome.plan.windings:
            winding_result = results.get(winding.name) if results is not None else None
            if winding_result is None:
                lines.append(f"{winding.name}: not analyzed")
            else:
                lines.append(
                    f"{winding.name}: R={winding_result.resistance_ohm:g} ohm  "
                    f"L={winding_result.inductance_h:g} H"
                )
        return tuple(lines)
    except MaxwellExportBlocked as error:
        return tuple(f"BLOCKED: {issue}" for issue in error.issues)
    except Exception as error:  # noqa: BLE001 - the UI must never crash from generation
        return (f"Generation failed: {error}",)
