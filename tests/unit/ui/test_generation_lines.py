from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from inductor_designer.domain.aedt_target import AedtEdition, AedtRelease, ModelDimension
from inductor_designer.simulation.capabilities import (
    CapabilityReviewStatus,
    CapabilitySnapshot,
)
from inductor_designer.ui.generation_lines import GenerationBackend, run_generation
from tests.fakes.femm_solver import RecordingFemmSolver
from tests.fakes.maxwell2d_exporter import RecordingMaxwell2dExporter
from tests.fakes.maxwell_exporter import RecordingMaxwell3dExporter
from tests.unit.application.test_geometry_model import CATALOG
from tests.unit.application.test_maxwell_export import three_d_project

SNAPSHOT = CapabilitySnapshot(
    release=AedtRelease(2025, 2),
    edition=AedtEdition.COMMERCIAL,
    include_dc_fields_3d=None,
    discovered_limits=(),
    evidence_source="test",
    review_status=CapabilityReviewStatus.REVIEWED,
)


def _exporters() -> dict[str, object]:
    return {
        "maxwell3d_exporter": RecordingMaxwell3dExporter(),
        "maxwell2d_exporter": RecordingMaxwell2dExporter(),
        "femm_solver": RecordingFemmSolver(),
    }


def test_maxwell3d_backend_reports_stage_lines(tmp_path: Path) -> None:
    lines = run_generation(
        GenerationBackend.MAXWELL_3D,
        three_d_project(),  # type: ignore[arg-type]
        CATALOG,
        SNAPSHOT,
        tmp_path,
        **_exporters(),  # type: ignore[arg-type]
    )
    assert lines[0] == "launch: ok - recorded"
    assert all(line.split(": ", 1)[1].startswith("ok") for line in lines)


def test_maxwell2d_backend_reports_stage_lines(tmp_path: Path) -> None:
    project = replace(three_d_project(), dimension_mode=ModelDimension.TWO_D)  # type: ignore[type-var]
    lines = run_generation(
        GenerationBackend.MAXWELL_2D,
        project,  # type: ignore[arg-type]
        CATALOG,
        SNAPSHOT,
        tmp_path,
        **_exporters(),  # type: ignore[arg-type]
    )
    assert lines
    assert lines[0].startswith("launch: ok")


def test_femm_backend_reports_fem_path_and_winding_results(tmp_path: Path) -> None:
    project = replace(three_d_project(), dimension_mode=ModelDimension.TWO_D)  # type: ignore[type-var]
    lines = run_generation(
        GenerationBackend.FEMM_2D,
        project,  # type: ignore[arg-type]
        CATALOG,
        SNAPSHOT,
        tmp_path,
        **_exporters(),  # type: ignore[arg-type]
    )
    assert lines[0].startswith("fem: ")
    assert lines[0].endswith(".fem")
    assert "w1: R=0.1 ohm  L=0.0001 H" in lines
    assert "w2: R=0.1 ohm  L=0.0001 H" in lines


def test_femm_backend_not_analyzed_reports_status(tmp_path: Path) -> None:
    # Build a project + call export_femm2d directly via run_generation is not
    # parameterized for analyze=False, so exercise the "not analyzed" branch
    # through a solver fake that returns no results.
    project = replace(three_d_project(), dimension_mode=ModelDimension.TWO_D)  # type: ignore[type-var]

    class NotAnalyzedFemmSolver(RecordingFemmSolver):
        def solve(self, request: object) -> object:  # type: ignore[override]
            result = super().solve(request)  # type: ignore[arg-type]
            return replace(result, analyzed=False, results=None)  # type: ignore[arg-type]

    exporters = _exporters()
    exporters["femm_solver"] = NotAnalyzedFemmSolver()
    lines = run_generation(
        GenerationBackend.FEMM_2D,
        project,  # type: ignore[arg-type]
        CATALOG,
        SNAPSHOT,
        tmp_path,
        **exporters,  # type: ignore[arg-type]
    )
    assert "w1: not analyzed" in lines
    assert "w2: not analyzed" in lines


def test_dimension_mismatch_is_blocked_not_raised(tmp_path: Path) -> None:
    lines = run_generation(
        GenerationBackend.MAXWELL_2D,
        three_d_project(),  # type: ignore[arg-type]
        CATALOG,
        SNAPSHOT,
        tmp_path,
        **_exporters(),  # type: ignore[arg-type]
    )
    assert len(lines) == 1
    assert lines[0].startswith("BLOCKED: ")
    assert "2d" in lines[0]


def test_exception_becomes_error_line(tmp_path: Path) -> None:
    class ExplodingExporter(RecordingMaxwell3dExporter):
        def export(self, request: object) -> object:  # type: ignore[override]
            raise RuntimeError("boom")

    exporters = _exporters()
    exporters["maxwell3d_exporter"] = ExplodingExporter()
    lines = run_generation(
        GenerationBackend.MAXWELL_3D,
        three_d_project(),  # type: ignore[arg-type]
        CATALOG,
        SNAPSHOT,
        tmp_path,
        **exporters,  # type: ignore[arg-type]
    )
    assert len(lines) == 1
    assert "boom" in lines[0]
