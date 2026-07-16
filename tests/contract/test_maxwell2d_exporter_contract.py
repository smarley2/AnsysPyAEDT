from __future__ import annotations

from pathlib import Path

from inductor_designer.application.ports.maxwell2d_exporter import (
    STAGE_NAMES_2D,
    Maxwell2dExportRequest,
)
from inductor_designer.domain.aedt_target import AedtEdition, AedtRelease
from tests.fakes.maxwell2d_exporter import RecordingMaxwell2dExporter
from tests.unit.simulation.test_plan_builder import make_definition
from tests.unit.simulation.test_plan_builder2d import build2d


def make_request(tmp_path: Path) -> Maxwell2dExportRequest:
    return Maxwell2dExportRequest(
        plan=build2d((make_definition(),)),  # type: ignore[arg-type]
        release=AedtRelease(2025, 2),
        edition=AedtEdition.COMMERCIAL,
        non_graphical=True,
        output_directory=tmp_path,
        project_name="Boost_inductor_2d",
    )


def test_fake_records_and_reports_full_stage_sequence(tmp_path: Path) -> None:
    exporter = RecordingMaxwell2dExporter()
    request = make_request(tmp_path)
    result = exporter.export(request)
    assert exporter.requests == [request]
    assert tuple(stage.name for stage in result.stages) == STAGE_NAMES_2D
    assert result.succeeded()
    assert result.project_path == tmp_path / "Boost_inductor_2d.aedt"
    assert result.design_name == "Inductor2D"
