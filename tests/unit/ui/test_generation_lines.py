from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from inductor_designer.domain.aedt_target import AedtEdition, AedtRelease
from inductor_designer.simulation.capabilities import (
    CapabilityReviewStatus,
    CapabilitySnapshot,
)
from inductor_designer.simulation.run_contracts import RunStatus
from inductor_designer.ui.generation_lines import GenerationBackend, run_generation
from tests.fakes.femm_solver import RecordingFemmSolver
from tests.fakes.maxwell2d_exporter import RecordingMaxwell2dExporter
from tests.fakes.maxwell_exporter import RecordingMaxwell3dExporter
from tests.unit.application.test_geometry_model import CATALOG
from tests.unit.application.test_maxwell_export import project_for_runs

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
        project_for_runs(),
        CATALOG,
        SNAPSHOT,
        tmp_path,
        **_exporters(),  # type: ignore[arg-type]
    )
    assert lines[0] == "launch: ok - recorded"
    assert all(line.split(": ", 1)[1].startswith("ok") for line in lines)


def test_maxwell2d_backend_reports_stage_lines(tmp_path: Path) -> None:
    lines = run_generation(
        GenerationBackend.MAXWELL_2D,
        project_for_runs(),
        CATALOG,
        SNAPSHOT,
        tmp_path,
        **_exporters(),  # type: ignore[arg-type]
    )
    assert lines
    assert lines[0].startswith("launch: ok")


def test_femm_backend_reports_generate_only_status(tmp_path: Path) -> None:
    lines = run_generation(
        GenerationBackend.FEMM_2D,
        project_for_runs(),
        CATALOG,
        SNAPSHOT,
        tmp_path,
        **_exporters(),  # type: ignore[arg-type]
    )
    assert lines[0].startswith("fem: ")
    assert lines[0].endswith(".fem")
    assert "w1: not analyzed" in lines


def test_one_project_can_generate_every_backend(tmp_path: Path) -> None:
    project = project_for_runs()
    for backend in GenerationBackend:
        assert run_generation(
            backend,
            project,
            CATALOG,
            SNAPSHOT,
            tmp_path,
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
        CATALOG,
        SNAPSHOT,
        tmp_path,
        **exporters,  # type: ignore[arg-type]
    )
    assert len(result) == 1
    assert "boom" in result[0]
    manifest = result.failed_manifest
    assert manifest is not None
    assert manifest.status is RunStatus.FAILED
    assert manifest.diagnostics == ("RuntimeError: boom",)
    assert manifest.artifacts == ()
    with pytest.raises(FrozenInstanceError):
        manifest.status = RunStatus.SUCCEEDED  # type: ignore[misc]
