from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from inductor_designer.application.ports.maxwell_exporter import (
    STAGE_NAMES,
    Maxwell3dExportRequest,
)
from inductor_designer.domain.aedt_target import AedtEdition, AedtRelease
from tests.fakes.maxwell_exporter import RecordingMaxwell3dExporter
from tests.unit.simulation.test_plan_builder import build, make_definition


def make_request(tmp_path: Path) -> Maxwell3dExportRequest:
    return Maxwell3dExportRequest(
        plan=build((make_definition(),)),  # type: ignore[arg-type]
        release=AedtRelease(2025, 2),
        edition=AedtEdition.COMMERCIAL,
        non_graphical=True,
        output_directory=tmp_path,
        project_name="Boost_inductor",
    )


def test_fake_records_request_and_reports_full_stage_sequence(tmp_path: Path) -> None:
    exporter = RecordingMaxwell3dExporter()
    request = make_request(tmp_path)
    result = exporter.export(request)
    assert exporter.requests == [request]
    assert tuple(stage.name for stage in result.stages) == STAGE_NAMES
    assert result.succeeded()
    assert result.project_path == tmp_path / "Boost_inductor.aedt"
    assert result.design_name == "Inductor3D"


def test_result_not_succeeded_when_stages_incomplete(tmp_path: Path) -> None:
    exporter = RecordingMaxwell3dExporter()
    full = exporter.export(make_request(tmp_path))
    truncated = replace(full, stages=full.stages[:3])
    assert not truncated.succeeded()
