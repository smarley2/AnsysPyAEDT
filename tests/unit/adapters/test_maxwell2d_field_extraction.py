from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from inductor_designer.adapters.pyaedt.maxwell2d import PyaedtMaxwell2dExporter
from inductor_designer.application.ports.maxwell_exporter import MaxwellExportResult
from tests.contract.test_maxwell2d_exporter_contract import make_request
from tests.fakes.maxwell2d_app import FakeMaxwell2dApp, FakeMaxwell2dAppFactory

pytestmark = pytest.mark.usefixtures("fake_maxwell_boundary")


def export(
    tmp_path: Path, app: FakeMaxwell2dApp, **overrides: object
) -> MaxwellExportResult:
    request = replace(make_request(tmp_path), **overrides)  # type: ignore[arg-type]
    return PyaedtMaxwell2dExporter(app_factory=FakeMaxwell2dAppFactory(app)).export(
        request
    )


def test_2d_integrates_the_evaluated_regions_directly(tmp_path: Path) -> None:
    raw = export(tmp_path, FakeMaxwell2dApp(), solve=True).raw_results

    assert raw is not None
    assert [section.scope for section in raw.flux_density_sections] == ["core.region"]
    assert raw.current_density_sections
    assert all(
        section.scope.endswith(".region")
        for section in raw.current_density_sections
    )


def test_2d_creates_no_section_sheets(tmp_path: Path) -> None:
    app = FakeMaxwell2dApp()

    export(tmp_path, app, solve=True)

    assert app.created_sheets == [], "2D evaluates the region, never a cut plane"


def test_the_core_region_area_is_the_annulus(tmp_path: Path) -> None:
    import math

    request = make_request(tmp_path)
    raw = export(tmp_path, FakeMaxwell2dApp(), solve=True).raw_results

    assert raw is not None
    expected = math.pi * (
        request.plan.core.r_outer_m**2 - request.plan.core.r_inner_m**2
    )
    assert raw.flux_density_sections[0].area_m2 == pytest.approx(expected)


def test_a_failed_region_read_is_recorded_not_raised(tmp_path: Path) -> None:
    app = FakeMaxwell2dApp()
    app.fail_field_value_for = "Core"

    raw = export(tmp_path, app, solve=True).raw_results

    assert raw is not None
    assert raw.flux_density_sections[0].mean is None
    assert raw.flux_density_sections[0].diagnostic


def test_a_generate_only_2d_run_reports_no_field_sections(tmp_path: Path) -> None:
    assert export(tmp_path, FakeMaxwell2dApp()).raw_results is None
