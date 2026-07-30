from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from inductor_designer.application.ports.femm_solver import (
    FemmSolveRequest,
    FemmSolveResult,
)
from inductor_designer.application.services.maxwell_export import MaxwellExportBlocked
from inductor_designer.application.services.project_run import (
    ProjectRunFailed,
    ProjectRunResult,
    start_project_run,
)
from inductor_designer.application.services.run_planning import RunPlanningError
from inductor_designer.domain.project import InductorProject
from inductor_designer.simulation.run_contracts import (
    RunBackend,
    RunMode,
    RunRequest,
    RunStatus,
)
from tests.fakes.femm_solver import RecordingFemmSolver
from tests.fakes.maxwell2d_exporter import RecordingMaxwell2dExporter
from tests.fakes.maxwell_exporter import RecordingMaxwell3dExporter
from tests.unit.application.test_geometry_model import CATALOG
from tests.unit.application.test_maxwell_export import CAPABILITIES, project_for_runs

MOMENT = datetime(2026, 7, 30, 10, 15, 0, tzinfo=timezone.utc)


def saved_project(tmp_path: Path) -> Path:
    path = tmp_path / "boost.inductor.json"
    path.write_text("{}", encoding="utf-8")
    return path


def run(
    tmp_path: Path,
    backend: RunBackend = RunBackend.FEMM,
    *,
    project: InductorProject | None = None,
    show_solver_window: bool = False,
) -> ProjectRunResult:
    return start_project_run(
        project_for_runs() if project is None else project,
        saved_project(tmp_path),
        RunRequest(backend, RunMode.GENERATE_ONLY),
        CATALOG,
        CAPABILITIES,
        maxwell3d_exporter=RecordingMaxwell3dExporter(),
        maxwell2d_exporter=RecordingMaxwell2dExporter(),
        femm_solver=RecordingFemmSolver(),
        application_version="0.7.0-test",
        show_solver_window=show_solver_window,
        now=MOMENT,
    )


def test_a_run_writes_its_manifest_into_its_own_directory(tmp_path: Path) -> None:
    result = run(tmp_path)

    assert result.location.directory == tmp_path.resolve() / "runs" / "20260730-101500-femm"
    assert result.manifest_path == result.location.manifest_path
    document = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert document["runId"] == "20260730-101500"
    assert document["status"] == RunStatus.SUCCEEDED.value


def test_manifest_artifact_paths_are_project_relative(tmp_path: Path) -> None:
    result = run(tmp_path)

    document = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert [artifact["path"] for artifact in document["artifacts"]] == [
        "runs/20260730-101500-femm/Boost_inductor_2d.fem"
    ]


def test_a_second_run_never_overwrites_the_first(tmp_path: Path) -> None:
    first = run(tmp_path)
    second = run(tmp_path)

    assert first.location.directory != second.location.directory
    assert first.manifest_path.is_file()
    assert second.manifest_path.is_file()
    assert second.location.run_id == "20260730-101500-2"


def test_the_results_directory_is_reserved_and_empty(tmp_path: Path) -> None:
    result = run(tmp_path)

    assert result.location.results_directory.is_dir()
    assert list(result.location.results_directory.iterdir()) == []


def test_a_failed_run_keeps_its_directory_and_manifest(tmp_path: Path) -> None:
    class FailingFemmSolver(RecordingFemmSolver):
        def solve(self, request: FemmSolveRequest) -> FemmSolveResult:
            raise RuntimeError("FEMM refused the problem")

    with pytest.raises(ProjectRunFailed) as failure:
        start_project_run(
            project_for_runs(),
            saved_project(tmp_path),
            RunRequest(RunBackend.FEMM, RunMode.GENERATE_ONLY),
            CATALOG,
            CAPABILITIES,
            maxwell3d_exporter=RecordingMaxwell3dExporter(),
            maxwell2d_exporter=RecordingMaxwell2dExporter(),
            femm_solver=FailingFemmSolver(),
            application_version="0.7.0-test",
            now=MOMENT,
        )

    error = failure.value
    assert error.manifest.status is RunStatus.FAILED
    document = json.loads(error.manifest_path.read_text(encoding="utf-8"))
    assert document["status"] == RunStatus.FAILED.value
    assert "FEMM refused the problem" in " ".join(document["diagnostics"])
    assert error.location.directory.is_dir()


def test_a_manifest_write_failure_does_not_mask_the_adapter_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FailingFemmSolver(RecordingFemmSolver):
        def solve(self, request: FemmSolveRequest) -> FemmSolveResult:
            raise RuntimeError("FEMM refused the problem")

    original_write_text = Path.write_text

    def _failing_write_text(self: Path, *args: object, **kwargs: object) -> int:
        if self.name == "run-manifest.json":
            raise OSError("simulated: disk full")
        return original_write_text(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "write_text", _failing_write_text)

    with pytest.raises(ProjectRunFailed) as failure:
        start_project_run(
            project_for_runs(),
            saved_project(tmp_path),
            RunRequest(RunBackend.FEMM, RunMode.GENERATE_ONLY),
            CATALOG,
            CAPABILITIES,
            maxwell3d_exporter=RecordingMaxwell3dExporter(),
            maxwell2d_exporter=RecordingMaxwell2dExporter(),
            femm_solver=FailingFemmSolver(),
            application_version="0.7.0-test",
            now=MOMENT,
        )

    error = failure.value
    assert error.manifest.status is RunStatus.FAILED
    assert "FEMM refused the problem" in " ".join(error.manifest.diagnostics)
    assert isinstance(error.__cause__, OSError)


def test_a_blocked_run_leaves_no_empty_directory_behind(tmp_path: Path) -> None:
    document_path = saved_project(tmp_path)

    with pytest.raises(MaxwellExportBlocked):
        start_project_run(
            project_for_runs(),
            document_path,
            RunRequest(RunBackend.FEMM, RunMode.GENERATE_AND_SOLVE),
            CATALOG,
            CAPABILITIES,
            maxwell3d_exporter=RecordingMaxwell3dExporter(),
            maxwell2d_exporter=RecordingMaxwell2dExporter(),
            femm_solver=RecordingFemmSolver(),
            application_version="0.7.0-test",
            now=MOMENT,
        )

    assert list((tmp_path / "runs").iterdir()) == []


def test_an_invalid_project_is_refused_without_creating_a_run(tmp_path: Path) -> None:
    project = project_for_runs()
    broken = replace(project, design=replace(project.design, windings=()))

    with pytest.raises(RunPlanningError):
        run(tmp_path, project=broken)

    assert list((tmp_path / "runs").iterdir()) == []


def test_an_unsaved_project_never_starts_a_run(tmp_path: Path) -> None:
    with pytest.raises(Exception, match="save the project"):
        start_project_run(
            project_for_runs(),
            tmp_path / "never-saved.inductor.json",
            RunRequest(RunBackend.FEMM, RunMode.GENERATE_ONLY),
            CATALOG,
            CAPABILITIES,
            maxwell3d_exporter=RecordingMaxwell3dExporter(),
            maxwell2d_exporter=RecordingMaxwell2dExporter(),
            femm_solver=RecordingFemmSolver(),
            application_version="0.7.0-test",
            now=MOMENT,
        )

    assert not (tmp_path / "runs").exists()
