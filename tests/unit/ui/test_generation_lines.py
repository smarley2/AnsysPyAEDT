from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from inductor_designer.simulation.run_contracts import RunStatus
from inductor_designer.ui.generation_lines import GenerationBackend, run_generation
from tests.fakes.femm_solver import RecordingFemmSolver
from tests.fakes.maxwell2d_exporter import RecordingMaxwell2dExporter
from tests.fakes.maxwell_exporter import RecordingMaxwell3dExporter
from tests.unit.application.test_geometry_model import CATALOG
from tests.unit.application.test_maxwell_export import CAPABILITIES, project_for_runs


def _saved_document(tmp_path: Path) -> Path:
    document = tmp_path / "boost.inductor.json"
    document.write_text("{}", encoding="utf-8")
    return document


def _exporters() -> dict[str, object]:
    return {
        "maxwell3d_exporter": RecordingMaxwell3dExporter(),
        "maxwell2d_exporter": RecordingMaxwell2dExporter(),
        "femm_solver": RecordingFemmSolver(),
    }


def test_maxwell3d_backend_reports_stage_lines(tmp_path: Path) -> None:
    lines = run_generation(
        GenerationBackend.MAXWELL_3D,
        project_for_runs(),
        _saved_document(tmp_path),
        CATALOG,
        CAPABILITIES,
        **_exporters(),  # type: ignore[arg-type]
    )
    assert lines[0] == "launch: ok - recorded"
    assert all(line.split(": ", 1)[1].startswith("ok") for line in lines[:-1])


def test_maxwell2d_backend_reports_stage_lines(tmp_path: Path) -> None:
    lines = run_generation(
        GenerationBackend.MAXWELL_2D,
        project_for_runs(),
        _saved_document(tmp_path),
        CATALOG,
        CAPABILITIES,
        **_exporters(),  # type: ignore[arg-type]
    )
    assert lines
    assert lines[0].startswith("launch: ok")


def test_femm_backend_reports_generate_only_status(tmp_path: Path) -> None:
    lines = run_generation(
        GenerationBackend.FEMM_2D,
        project_for_runs(),
        _saved_document(tmp_path),
        CATALOG,
        CAPABILITIES,
        **_exporters(),  # type: ignore[arg-type]
    )
    assert lines[0].startswith("fem: ")
    assert lines[0].endswith(".fem")
    assert "w1: not analyzed" in lines


def test_one_project_can_generate_every_backend(tmp_path: Path) -> None:
    project = project_for_runs()
    document = _saved_document(tmp_path)
    for backend in GenerationBackend:
        assert run_generation(
            backend,
            project,
            document,
            CATALOG,
            CAPABILITIES,
            **_exporters(),  # type: ignore[arg-type]
        )[0]


def test_exception_becomes_error_line(tmp_path: Path) -> None:
    class ExplodingExporter(RecordingMaxwell3dExporter):
        def export(self, request: object) -> object:  # type: ignore[override]
            raise RuntimeError("boom")

    exporters = _exporters()
    exporters["maxwell3d_exporter"] = ExplodingExporter()
    result = run_generation(
        GenerationBackend.MAXWELL_3D,
        project_for_runs(),
        _saved_document(tmp_path),
        CATALOG,
        CAPABILITIES,
        **exporters,  # type: ignore[arg-type]
    )
    assert len(result) == 2
    assert "boom" in result[0]
    manifest = result.failed_manifest
    assert manifest is not None
    assert manifest.status is RunStatus.FAILED
    assert manifest.diagnostics == ("RuntimeError: boom",)
    assert manifest.artifacts == ()
    with pytest.raises(FrozenInstanceError):
        manifest.status = RunStatus.SUCCEEDED  # type: ignore[misc]


def test_generation_writes_into_the_project_run_directory(tmp_path: Path) -> None:
    document = tmp_path / "boost.inductor.json"
    document.write_text("{}", encoding="utf-8")

    result = run_generation(
        GenerationBackend.FEMM_2D,
        project_for_runs(),
        document,
        CATALOG,
        CAPABILITIES,
        maxwell3d_exporter=RecordingMaxwell3dExporter(),
        maxwell2d_exporter=RecordingMaxwell2dExporter(),
        femm_solver=RecordingFemmSolver(),
    )

    assert result.run_directory is not None
    assert result.run_directory.parent == tmp_path.resolve() / "runs"
    assert (result.run_directory / "run-manifest.json").is_file()
    assert result.generated_file is not None
    assert result.generated_file.suffix == ".fem"
    assert any("run folder" in line for line in result.lines)


def test_a_visible_run_is_requested_only_when_asked(tmp_path: Path) -> None:
    document = tmp_path / "boost.inductor.json"
    document.write_text("{}", encoding="utf-8")
    femm = RecordingFemmSolver()

    run_generation(
        GenerationBackend.FEMM_2D,
        project_for_runs(),
        document,
        CATALOG,
        CAPABILITIES,
        maxwell3d_exporter=RecordingMaxwell3dExporter(),
        maxwell2d_exporter=RecordingMaxwell2dExporter(),
        femm_solver=femm,
        show_solver_window=True,
    )

    assert femm.requests[0].show_window is True


def test_an_unsaved_project_reports_a_blocked_run(tmp_path: Path) -> None:
    result = run_generation(
        GenerationBackend.FEMM_2D,
        project_for_runs(),
        tmp_path / "never-saved.inductor.json",
        CATALOG,
        CAPABILITIES,
        maxwell3d_exporter=RecordingMaxwell3dExporter(),
        maxwell2d_exporter=RecordingMaxwell2dExporter(),
        femm_solver=RecordingFemmSolver(),
    )

    assert result.run_directory is None
    assert any("save the project" in line for line in result.lines)
