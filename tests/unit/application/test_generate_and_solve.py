from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from inductor_designer.application.ports.femm_solver import (
    FemmSolveRequest,
    FemmSolveResult,
)
from inductor_designer.application.services.maxwell_export import (
    RunCancelledDuringGeneration,
    RunGenerationFailed,
    generate_run,
)
from inductor_designer.application.services.project_run import (
    ProjectRunCancelled,
    ProjectRunResult,
    start_project_run,
)
from inductor_designer.simulation.run_contracts import (
    RunBackend,
    RunMode,
    RunRequest,
    RunStatus,
)
from inductor_designer.simulation.run_control import CancellationToken, StageEvent
from tests.fakes.femm_solver import RecordingFemmSolver
from tests.fakes.maxwell2d_exporter import RecordingMaxwell2dExporter
from tests.fakes.maxwell_exporter import RecordingMaxwell3dExporter
from tests.unit.application.test_geometry_model import CATALOG
from tests.unit.application.test_maxwell_export import CAPABILITIES, project_for_runs
from tests.unit.application.test_project_run import MOMENT, saved_project


class RecordingSink:
    def __init__(self) -> None:
        self.events: list[StageEvent] = []

    def emit(self, event: StageEvent) -> None:
        self.events.append(event)


def solve_run(
    tmp_path: Path,
    backend: RunBackend = RunBackend.MAXWELL_3D,
    **overrides: object,
) -> ProjectRunResult:
    return start_project_run(
        project_for_runs(),
        saved_project(tmp_path),
        RunRequest(backend, RunMode.GENERATE_AND_SOLVE),
        CATALOG,
        CAPABILITIES,
        maxwell3d_exporter=overrides.pop(
            "maxwell3d_exporter", RecordingMaxwell3dExporter()
        ),  # type: ignore[arg-type]
        maxwell2d_exporter=overrides.pop(
            "maxwell2d_exporter", RecordingMaxwell2dExporter()
        ),  # type: ignore[arg-type]
        femm_solver=overrides.pop("femm_solver", RecordingFemmSolver()),  # type: ignore[arg-type]
        application_version="0.7.0-test",
        now=MOMENT,
        **overrides,  # type: ignore[arg-type]
    )


def test_generate_and_solve_is_no_longer_blocked(tmp_path: Path) -> None:
    exporter = RecordingMaxwell3dExporter()

    result = solve_run(tmp_path, maxwell3d_exporter=exporter)

    assert exporter.requests[0].solve is True
    assert result.outcome.manifest.mode is RunMode.GENERATE_AND_SOLVE
    assert result.outcome.manifest.status is RunStatus.SUCCEEDED
    assert any(stage.name == "analyze" for stage in result.outcome.manifest.stages)


def test_femm_solve_mode_asks_the_adapter_to_analyze(tmp_path: Path) -> None:
    solver = RecordingFemmSolver()

    result = solve_run(tmp_path, RunBackend.FEMM, femm_solver=solver)

    assert solver.requests[0].analyze is True
    assert result.outcome.manifest.status is RunStatus.SUCCEEDED
    assert [stage.name for stage in result.outcome.manifest.stages] == [
        "generate",
        "analyze",
    ]


def test_maxwell2d_solve_mode_reaches_analyze(tmp_path: Path) -> None:
    exporter = RecordingMaxwell2dExporter()

    result = solve_run(tmp_path, RunBackend.MAXWELL_2D, maxwell2d_exporter=exporter)

    assert exporter.requests[0].solve is True
    assert result.outcome.manifest.stages[-1].name == "analyze"


def test_solve_mode_manifest_carries_no_results_in_m8a(tmp_path: Path) -> None:
    result = solve_run(tmp_path)

    assert result.outcome.manifest.results is None
    document = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert document["results"] is None


def test_generate_only_still_never_asks_for_a_solve(tmp_path: Path) -> None:
    exporter = RecordingMaxwell3dExporter()

    start_project_run(
        project_for_runs(),
        saved_project(tmp_path),
        RunRequest(RunBackend.MAXWELL_3D, RunMode.GENERATE_ONLY),
        CATALOG,
        CAPABILITIES,
        maxwell3d_exporter=exporter,
        maxwell2d_exporter=RecordingMaxwell2dExporter(),
        femm_solver=RecordingFemmSolver(),
        application_version="0.7.0-test",
        now=MOMENT,
    )

    assert exporter.requests[0].solve is False
    assert "analyze" not in [stage.name for stage in exporter.requests[0].plan.reports]


def test_generate_only_femm_still_rejects_analyzed_evidence(tmp_path: Path) -> None:
    class AlwaysAnalyzingFemmSolver(RecordingFemmSolver):
        def solve(self, request: FemmSolveRequest) -> FemmSolveResult:
            return replace(super().solve(request), analyzed=True)

    with pytest.raises(RunGenerationFailed) as failure:
        generate_run(
            project_for_runs(),
            RunRequest(RunBackend.FEMM, RunMode.GENERATE_ONLY),
            CATALOG,
            CAPABILITIES,
            tmp_path,
            maxwell3d_exporter=RecordingMaxwell3dExporter(),
            maxwell2d_exporter=RecordingMaxwell2dExporter(),
            femm_solver=AlwaysAnalyzingFemmSolver(),
            run_id="20260810-120002",
            application_version="0.7.0-test",
        )

    assert failure.value.manifest.status is RunStatus.FAILED
    assert "nonconforming" in failure.value.manifest.diagnostics[0]


def test_a_cancelled_maxwell_run_reports_cancelled_not_failed(tmp_path: Path) -> None:
    token = CancellationToken()
    exporter = RecordingMaxwell3dExporter()
    exporter.on_stage["mesh"] = token.cancel

    with pytest.raises(ProjectRunCancelled) as cancelled:
        solve_run(tmp_path, maxwell3d_exporter=exporter, cancellation=token)

    manifest = cancelled.value.manifest
    assert manifest.status is RunStatus.CANCELLED
    assert manifest.results is None
    assert [stage.name for stage in manifest.stages][-1] == "cancelled"
    document = json.loads(cancelled.value.manifest_path.read_text(encoding="utf-8"))
    assert document["status"] == "cancelled"


def test_a_cancelled_femm_run_reports_cancelled(tmp_path: Path) -> None:
    token = CancellationToken()
    token.cancel()

    with pytest.raises(ProjectRunCancelled) as cancelled:
        solve_run(tmp_path, RunBackend.FEMM, cancellation=token)

    assert cancelled.value.manifest.status is RunStatus.CANCELLED


def test_generate_run_raises_the_cancellation_error_directly(tmp_path: Path) -> None:
    token = CancellationToken()
    token.cancel()

    with pytest.raises(RunCancelledDuringGeneration) as cancelled:
        generate_run(
            project_for_runs(),
            RunRequest(RunBackend.MAXWELL_3D, RunMode.GENERATE_AND_SOLVE),
            CATALOG,
            CAPABILITIES,
            tmp_path,
            maxwell3d_exporter=RecordingMaxwell3dExporter(),
            maxwell2d_exporter=RecordingMaxwell2dExporter(),
            femm_solver=RecordingFemmSolver(),
            run_id="20260810-120003",
            application_version="0.7.0-test",
            cancellation=token,
        )

    assert cancelled.value.manifest.status is RunStatus.CANCELLED


def test_a_running_manifest_exists_while_the_adapter_works(tmp_path: Path) -> None:
    seen: list[str] = []
    exporter = RecordingMaxwell3dExporter()

    def peek() -> None:
        manifest = next((tmp_path / "runs").glob("*/run-manifest.json"))
        seen.append(json.loads(manifest.read_text(encoding="utf-8"))["status"])

    exporter.on_stage["launch"] = peek

    result = solve_run(tmp_path, maxwell3d_exporter=exporter)

    assert seen == [RunStatus.RUNNING.value]
    document = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert document["status"] == RunStatus.SUCCEEDED.value


def test_the_solve_log_lands_in_the_reserved_results_directory(
    tmp_path: Path,
) -> None:
    result = solve_run(tmp_path)

    log_path = result.location.results_directory / "solve-log.txt"
    assert log_path.is_file()
    text = log_path.read_text(encoding="utf-8")
    assert "analyze" in text
    document = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert any(artifact["kind"] == "solve-log" for artifact in document["artifacts"])


def test_a_caller_supplied_progress_sink_sees_every_event(tmp_path: Path) -> None:
    sink = RecordingSink()

    solve_run(tmp_path, progress=sink)

    assert [event.stage_name for event in sink.events][0] == "launch"
    assert any(event.stage_name == "analyze" for event in sink.events)
