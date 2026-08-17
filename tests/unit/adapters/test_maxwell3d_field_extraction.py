from __future__ import annotations

import re
from pathlib import Path

import pytest

from inductor_designer.adapters.pyaedt.maxwell3d import PyaedtMaxwell3dExporter
from inductor_designer.application.ports.maxwell_exporter import (
    Maxwell3dExportRequest,
    Maxwell3dExportResult,
)
from inductor_designer.domain.aedt_target import AedtEdition, AedtRelease
from tests.fakes.maxwell3d_app import FakeMaxwell3dApp, FakeMaxwell3dAppFactory
from tests.unit.simulation.test_plan_builder import build, make_definition

pytestmark = pytest.mark.usefixtures("fake_maxwell_boundary")


def export(
    tmp_path: Path, app: FakeMaxwell3dApp, **overrides: object
) -> Maxwell3dExportResult:
    base: dict[str, object] = {
        "plan": build((make_definition(),)),
        "release": AedtRelease(2025, 2),
        "edition": AedtEdition.COMMERCIAL,
        "non_graphical": True,
        "output_directory": tmp_path / "out",
        "project_name": "Field_case",
        "solve": True,
    }
    base.update(overrides)
    return PyaedtMaxwell3dExporter(app_factory=FakeMaxwell3dAppFactory(app)).export(
        Maxwell3dExportRequest(**base)  # type: ignore[arg-type]
    )


def test_a_solved_run_reports_one_section_per_selected_plane(tmp_path: Path) -> None:
    app = FakeMaxwell3dApp()

    result = export(tmp_path, app)

    raw = result.raw_results
    assert raw is not None
    assert raw.flux_density_sections
    assert len(raw.flux_density_sections) == len(
        build((make_definition(),)).core_sections
    )
    assert all(section.area_m2 > 0.0 for section in raw.flux_density_sections)


def test_every_section_sheet_is_created_non_model(tmp_path: Path) -> None:
    app = FakeMaxwell3dApp()

    export(tmp_path, app)

    assert app.created_sheets
    assert all(sheet.non_model for sheet in app.created_sheets)


def test_core_sections_use_rectangles_and_conductor_sections_use_discs(
    tmp_path: Path,
) -> None:
    app = FakeMaxwell3dApp()

    export(tmp_path, app)

    kinds = {sheet.kind for sheet in app.created_sheets}
    assert kinds == {"rectangle", "disc"}


def test_conductor_sections_report_current_density(tmp_path: Path) -> None:
    raw = export(tmp_path, FakeMaxwell3dApp()).raw_results

    assert raw is not None
    assert raw.current_density_sections
    assert all(
        section.scope.startswith("winding.")
        for section in raw.current_density_sections
    )


def test_the_mean_is_the_integral_divided_by_the_section_area(
    tmp_path: Path,
) -> None:
    raw = export(tmp_path, FakeMaxwell3dApp()).raw_results

    assert raw is not None
    section = raw.flux_density_sections[0]
    assert section.mean == pytest.approx(1e-5 / section.area_m2)
    assert section.maximum == pytest.approx(0.42)


def test_one_failed_section_never_loses_the_others(tmp_path: Path) -> None:
    app = FakeMaxwell3dApp()
    app.fail_field_value_for = "core_00"

    raw = export(tmp_path, app).raw_results

    assert raw is not None
    failed = [s for s in raw.flux_density_sections if s.diagnostic]
    healthy = [s for s in raw.flux_density_sections if s.mean is not None]
    assert len(failed) == 1
    assert healthy


def test_a_generate_only_run_creates_no_sheets(tmp_path: Path) -> None:
    app = FakeMaxwell3dApp()

    export(tmp_path, app, solve=False)

    assert app.created_sheets == []


def test_the_sheets_exist_before_the_solve_starts(tmp_path: Path) -> None:
    """Adding geometry to a solved design invalidates the solution the sheets
    exist to be read against, so they are created before the solve. Being
    non-model, they are excluded from the mesh and change nothing about it.
    """
    app = FakeMaxwell3dApp()
    sheet_counts: list[int] = []
    app.on_call["analyze_setup"] = lambda: sheet_counts.append(len(app.created_sheets))

    result = export(tmp_path, app)

    assert result.raw_results is not None
    assert sheet_counts and sheet_counts[0] == len(app.created_sheets)
    assert sheet_counts[0] > 0


def test_a_sheet_failure_is_diagnosed_without_failing_the_run(tmp_path: Path) -> None:
    """Sheets serve field extraction only, so losing them costs the fields and
    nothing else: the solve and its scalar results still stand."""
    app = FakeMaxwell3dApp(raise_on="create_section_rectangle")

    result = export(tmp_path, app)

    sections = next(stage for stage in result.stages if stage.name == "sections")
    assert sections.succeeded
    assert "No field section sheets" in sections.message
    raw = result.raw_results
    assert raw is not None
    assert raw.flux_density_sections == ()
    assert any("create_section_rectangle" in item for item in raw.diagnostics)
    assert raw.windings


def test_sheet_names_carry_nothing_aedt_refuses_in_an_object_name(
    tmp_path: Path,
) -> None:
    """Section ids read `core.00.span-start`, and AEDT rejects a hyphen in an
    object name: `CreateRectangle` failed and took the design handle with it, so
    the next stage died on `'NoneType' object has no attribute 'InsertSetup'`.
    Replacing only the dots left the hyphen in place.
    """
    app = FakeMaxwell3dApp()

    export(tmp_path, app)

    assert app.created_sheets
    for sheet in app.created_sheets:
        assert sheet.name.startswith("Sec_")
        assert re.fullmatch(r"[A-Za-z0-9_]+", sheet.name), sheet.name
