from __future__ import annotations

from collections.abc import Sequence
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from inductor_designer import __version__
from inductor_designer.application.ports.femm_solver import FemmSolveResult
from inductor_designer.application.ports.maxwell_exporter import (
    MaxwellExportResult,
    StageRecord,
)
from inductor_designer.application.services.maxwell_export import (
    MaxwellExportBlocked,
    generate_run,
)
from inductor_designer.application.services.run_planning import RunPlanningError
from inductor_designer.simulation.run_contracts import RunBackend, RunMode, RunRequest

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


_RUN_BACKENDS = {
    GenerationBackend.MAXWELL_3D: RunBackend.MAXWELL_3D,
    GenerationBackend.MAXWELL_2D: RunBackend.MAXWELL_2D,
    GenerationBackend.FEMM_2D: RunBackend.FEMM,
}


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
        outcome = generate_run(
            project,
            RunRequest(_RUN_BACKENDS[backend], RunMode.GENERATE_ONLY),
            catalog,
            capabilities,
            output_directory,
            maxwell3d_exporter=maxwell3d_exporter,
            maxwell2d_exporter=maxwell2d_exporter,
            femm_solver=femm_solver,
            run_id=str(uuid4()),
            application_version=__version__,
        )
        result = outcome.adapter_result
        if isinstance(result, MaxwellExportResult):
            return _stage_lines(result.stages)
        if not isinstance(result, FemmSolveResult):
            raise TypeError("Run generation returned an unknown adapter result.")
        lines = [f"fem: {result.fem_path}"]
        for winding in outcome.manifest.windings:
            winding_result = (
                result.results.get(winding.winding_id)
                if result.results is not None
                else None
            )
            if winding_result is None:
                lines.append(f"{winding.winding_id}: not analyzed")
            else:
                lines.append(
                    f"{winding.winding_id}: R={winding_result.resistance_ohm:g} ohm  "
                    f"L={winding_result.inductance_h:g} H"
                )
        return tuple(lines)
    except (MaxwellExportBlocked, RunPlanningError) as error:
        return tuple(f"BLOCKED: {issue}" for issue in error.issues)
    except Exception as error:  # noqa: BLE001 - the UI must never crash from generation
        return (f"Generation failed: {error}",)
