from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, overload

from inductor_designer import __version__
from inductor_designer.application.ports.femm_solver import FemmSolveResult
from inductor_designer.application.ports.maxwell_exporter import (
    MaxwellExportResult,
    StageRecord,
)
from inductor_designer.application.services.maxwell_export import MaxwellExportBlocked
from inductor_designer.application.services.project_run import (
    ProjectRunFailed,
    start_project_run,
)
from inductor_designer.application.services.run_directory import RunDirectoryError
from inductor_designer.application.services.run_planning import RunPlanningError
from inductor_designer.simulation.run_contracts import (
    RunBackend,
    RunManifest,
    RunMode,
    RunRequest,
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


_RUN_BACKENDS = {
    GenerationBackend.MAXWELL_3D: RunBackend.MAXWELL_3D,
    GenerationBackend.MAXWELL_2D: RunBackend.MAXWELL_2D,
    GenerationBackend.FEMM_2D: RunBackend.FEMM,
}


def run_backend_for(backend: GenerationBackend) -> RunBackend:
    """The run-contract backend behind a UI backend label."""
    return _RUN_BACKENDS[backend]


@dataclass(frozen=True, slots=True)
class GenerationResult(Sequence[str]):
    """UI display lines with optional immutable failed-run evidence."""

    lines: tuple[str, ...]
    failed_manifest: RunManifest | None = None
    run_directory: Path | None = None
    generated_file: Path | None = None

    @overload
    def __getitem__(self, index: int) -> str: ...

    @overload
    def __getitem__(self, index: slice) -> tuple[str, ...]: ...

    def __getitem__(self, index: int | slice) -> str | tuple[str, ...]:
        return self.lines[index]

    def __len__(self) -> int:
        return len(self.lines)


def _stage_lines(stages: Sequence[StageRecord]) -> tuple[str, ...]:
    return tuple(
        f"{stage.name}: {'ok' if stage.succeeded else 'FAILED'} - {stage.message}"
        for stage in stages
    )


def run_generation(
    backend: GenerationBackend,
    project: InductorProject,
    project_document_path: Path,
    catalog: CatalogRepository,
    capabilities: CapabilitySnapshot,
    *,
    maxwell3d_exporter: Maxwell3dExporter,
    maxwell2d_exporter: Maxwell2dExporter,
    femm_solver: FemmSolver,
    show_solver_window: bool = False,
) -> GenerationResult:
    """Run one backend into the project's run directory. Never raises."""
    try:
        result = start_project_run(
            project,
            project_document_path,
            RunRequest(_RUN_BACKENDS[backend], RunMode.GENERATE_ONLY),
            catalog,
            capabilities,
            maxwell3d_exporter=maxwell3d_exporter,
            maxwell2d_exporter=maxwell2d_exporter,
            femm_solver=femm_solver,
            application_version=__version__,
            show_solver_window=show_solver_window,
        )
        adapter_result = result.outcome.adapter_result
        lines: list[str] = []
        generated_file: Path | None = None
        if isinstance(adapter_result, MaxwellExportResult):
            generated_file = adapter_result.project_path
            lines.extend(_stage_lines(adapter_result.stages))
        elif isinstance(adapter_result, FemmSolveResult):
            generated_file = adapter_result.fem_path
            lines.append(f"fem: {adapter_result.fem_path}")
            for winding in result.outcome.manifest.windings:
                winding_result = (
                    adapter_result.results.get(winding.winding_id)
                    if adapter_result.results is not None
                    else None
                )
                if winding_result is None:
                    lines.append(f"{winding.winding_id}: not analyzed")
                else:
                    lines.append(
                        f"{winding.winding_id}: R={winding_result.resistance_ohm:g} ohm  "
                        f"L={winding_result.inductance_h:g} H"
                    )
        else:
            raise TypeError("Run generation returned an unknown adapter result.")
        lines.append(f"run folder: {result.location.directory}")
        return GenerationResult(
            tuple(lines),
            run_directory=result.location.directory,
            generated_file=generated_file,
        )
    except ProjectRunFailed as error:
        return GenerationResult(
            tuple(
                f"Generation failed: {diagnostic}"
                for diagnostic in error.manifest.diagnostics
            )
            + (f"run folder: {error.location.directory}",),
            failed_manifest=error.manifest,
            run_directory=error.location.directory,
        )
    except (MaxwellExportBlocked, RunPlanningError) as error:
        return GenerationResult(tuple(f"BLOCKED: {issue}" for issue in error.issues))
    except RunDirectoryError as error:
        return GenerationResult((f"BLOCKED: {error}",))
    except Exception as error:  # noqa: BLE001 - the UI must never crash from generation
        return GenerationResult((f"Generation failed: {error}",))
