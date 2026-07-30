"""The one entry point for a project-local run (ADR 0007).

Every caller — Qt UI, MCP server, CLI tool — routes through this service so a
run always lands in its own directory beside the saved project document and
always leaves a truthful ``run-manifest.json`` there, successful or not.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from inductor_designer.application.ports.catalog import CatalogRepository
from inductor_designer.application.ports.femm_solver import FemmSolver
from inductor_designer.application.ports.maxwell2d_exporter import Maxwell2dExporter
from inductor_designer.application.ports.maxwell_exporter import Maxwell3dExporter
from inductor_designer.application.services.maxwell_export import (
    RunGenerationFailed,
    RunOutcome,
    generate_run,
    run_manifest_json,
)
from inductor_designer.application.services.run_directory import (
    RunLocation,
    allocate_run_directory,
    discard_empty_run_directory,
)
from inductor_designer.domain.project import InductorProject
from inductor_designer.simulation.capabilities import CapabilitySnapshot
from inductor_designer.simulation.run_contracts import RunManifest, RunRequest


@dataclass(frozen=True, slots=True)
class ProjectRunResult:
    location: RunLocation
    outcome: RunOutcome
    manifest_path: Path


class ProjectRunFailed(RuntimeError):
    """A run that reached an adapter and failed; its evidence is on disk."""

    def __init__(
        self,
        location: RunLocation,
        manifest: RunManifest,
        manifest_path: Path,
    ) -> None:
        self.location = location
        self.manifest = manifest
        self.manifest_path = manifest_path
        super().__init__("; ".join(manifest.diagnostics))


def _write_manifest(location: RunLocation, manifest: RunManifest) -> Path:
    location.manifest_path.write_text(run_manifest_json(manifest), encoding="utf-8")
    return location.manifest_path


def start_project_run(
    project: InductorProject,
    project_document_path: Path,
    request: RunRequest,
    catalog: CatalogRepository,
    capabilities: CapabilitySnapshot,
    *,
    maxwell3d_exporter: Maxwell3dExporter,
    maxwell2d_exporter: Maxwell2dExporter,
    femm_solver: FemmSolver,
    application_version: str,
    show_solver_window: bool = False,
    now: datetime | None = None,
) -> ProjectRunResult:
    """Run one backend into a new project-local run directory."""
    location = allocate_run_directory(project_document_path, request.backend, now=now)
    try:
        outcome = generate_run(
            project,
            request,
            catalog,
            capabilities,
            location.directory,
            maxwell3d_exporter=maxwell3d_exporter,
            maxwell2d_exporter=maxwell2d_exporter,
            femm_solver=femm_solver,
            run_id=location.run_id,
            application_version=application_version,
            show_solver_window=show_solver_window,
            artifact_base_directory=location.project_directory,
        )
    except RunGenerationFailed as failed:
        try:
            manifest_path = _write_manifest(location, failed.manifest)
        except OSError as write_error:
            # The adapter's diagnostics are the real failure; a write error on
            # top of that must not replace them, only ride along as the cause.
            raise ProjectRunFailed(
                location, failed.manifest, location.manifest_path
            ) from write_error
        raise ProjectRunFailed(location, failed.manifest, manifest_path) from failed
    except Exception:
        # Blocked or invalid before any adapter wrote: leave no empty directory.
        discard_empty_run_directory(location)
        raise
    return ProjectRunResult(
        location=location,
        outcome=outcome,
        manifest_path=_write_manifest(location, outcome.manifest),
    )
