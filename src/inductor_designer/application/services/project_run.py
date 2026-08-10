"""The one entry point for a project-local run (ADR 0007).

Every caller — Qt UI, MCP server, CLI tool — routes through this service so a
run always lands in its own directory beside the saved project document and
always leaves a truthful ``run-manifest.json`` there, successful or not.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from inductor_designer.application.ports.catalog import CatalogRepository
from inductor_designer.application.ports.femm_solver import FemmSolver
from inductor_designer.application.ports.maxwell2d_exporter import Maxwell2dExporter
from inductor_designer.application.ports.maxwell_exporter import Maxwell3dExporter
from inductor_designer.application.services.maxwell_export import (
    RunCancelledDuringGeneration,
    RunGenerationFailed,
    RunOutcome,
    generate_run,
    run_manifest_json,
)
from inductor_designer.application.services.result_export import (
    RESULTS_CSV_ARTIFACT_KIND,
    RESULTS_JSON_ARTIFACT_KIND,
    write_result_files,
)
from inductor_designer.application.services.run_directory import (
    RunLocation,
    allocate_run_directory,
    artifact_path_for_manifest,
    discard_empty_run_directory,
)
from inductor_designer.application.services.solve_log import (
    SOLVE_LOG_ARTIFACT_KIND,
    RecordingProgressSink,
    write_solve_log,
)
from inductor_designer.domain.project import InductorProject
from inductor_designer.simulation.capabilities import CapabilitySnapshot
from inductor_designer.simulation.run_contracts import (
    ManifestArtifact,
    RunManifest,
    RunMode,
    RunRequest,
    RunStatus,
)
from inductor_designer.simulation.run_control import CancellationToken, ProgressSink


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


class ProjectRunCancelled(RuntimeError):
    """A run the user cancelled between stages; its evidence is on disk."""

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


def _write_running_marker(
    location: RunLocation, request: RunRequest, started_at: datetime
) -> None:
    """Durable status while the adapter works.

    This is a placeholder, not a Run Manifest: the real manifest needs the
    planned run, which only exists once planning has succeeded. It is
    overwritten by the real manifest when the run ends, so a document with
    ``"status": "running"`` means the process died mid-run.

    Best effort: the real manifest is the evidence that matters, so a write
    failure here must never replace the adapter's own diagnostics.
    """
    try:
        _write_running_document(location, request, started_at)
    except OSError:
        return


def _write_running_document(
    location: RunLocation, request: RunRequest, started_at: datetime
) -> None:
    location.manifest_path.write_text(
        json.dumps(
            {
                "runId": location.run_id,
                "backend": request.backend.value,
                "mode": request.mode.value,
                "status": RunStatus.RUNNING.value,
                "startedUtc": started_at.astimezone(timezone.utc).isoformat(),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _with_solve_log(
    location: RunLocation, manifest: RunManifest, sink: RecordingProgressSink
) -> RunManifest:
    """Write the stage log and the result files, and reference them all.

    The result files are written only when the run actually produced a result
    set, so an interrupted or failed solve leaves the stage log alone rather
    than an empty results.json that reads like evidence.
    """
    from dataclasses import replace

    artifacts: tuple[ManifestArtifact, ...] = (
        ManifestArtifact(
            kind=SOLVE_LOG_ARTIFACT_KIND,
            path=artifact_path_for_manifest(
                write_solve_log(location.results_directory, sink.events),
                location.project_directory,
            ),
        ),
    )
    if manifest.results is not None:
        json_path, csv_path = write_result_files(
            location.results_directory, manifest.results
        )
        artifacts += (
            ManifestArtifact(
                kind=RESULTS_JSON_ARTIFACT_KIND,
                path=artifact_path_for_manifest(
                    json_path, location.project_directory
                ),
            ),
            ManifestArtifact(
                kind=RESULTS_CSV_ARTIFACT_KIND,
                path=artifact_path_for_manifest(csv_path, location.project_directory),
            ),
        )
    return replace(manifest, artifacts=manifest.artifacts + artifacts)


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
    progress: ProgressSink | None = None,
    cancellation: CancellationToken | None = None,
) -> ProjectRunResult:
    """Run one backend into a new project-local run directory."""
    started_at = datetime.now(timezone.utc) if now is None else now
    location = allocate_run_directory(project_document_path, request.backend, now=now)
    solve = request.mode is RunMode.GENERATE_AND_SOLVE
    sink = RecordingProgressSink(progress)
    _write_running_marker(location, request, started_at)
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
            progress=sink,
            cancellation=cancellation,
        )
    except RunCancelledDuringGeneration as interrupted:
        manifest = (
            _with_solve_log(location, interrupted.manifest, sink)
            if solve
            else interrupted.manifest
        )
        try:
            manifest_path = _write_manifest(location, manifest)
        except OSError as write_error:
            raise ProjectRunCancelled(
                location, manifest, location.manifest_path
            ) from write_error
        raise ProjectRunCancelled(location, manifest, manifest_path) from interrupted
    except RunGenerationFailed as failed:
        manifest = (
            _with_solve_log(location, failed.manifest, sink) if solve else failed.manifest
        )
        try:
            manifest_path = _write_manifest(location, manifest)
        except OSError as write_error:
            # The adapter's diagnostics are the real failure; a write error on
            # top of that must not replace them, only ride along as the cause.
            raise ProjectRunFailed(
                location, manifest, location.manifest_path
            ) from write_error
        raise ProjectRunFailed(location, manifest, manifest_path) from failed
    except Exception:
        # Blocked or invalid before any adapter wrote: leave no empty directory.
        location.manifest_path.unlink(missing_ok=True)
        discard_empty_run_directory(location)
        raise
    manifest = _with_solve_log(location, outcome.manifest, sink) if solve else outcome.manifest
    return ProjectRunResult(
        location=location,
        outcome=RunOutcome(
            planned_run=outcome.planned_run,
            adapter_result=outcome.adapter_result,
            manifest=manifest,
        ),
        manifest_path=_write_manifest(location, manifest),
    )
