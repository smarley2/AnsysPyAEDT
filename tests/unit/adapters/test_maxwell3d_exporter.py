from __future__ import annotations

from pathlib import Path

import pytest

from inductor_designer.adapters.pyaedt.maxwell3d import PyaedtMaxwell3dExporter
from inductor_designer.application.ports.maxwell_exporter import (
    STAGE_NAMES,
    Maxwell3dExportRequest,
)
from inductor_designer.domain.aedt_target import AedtEdition, AedtRelease
from inductor_designer.simulation.capabilities import DcBiasDecision, DcBiasStrategy
from tests.fakes.maxwell3d_app import FakeMaxwell3dApp, FakeMaxwell3dAppFactory
from tests.unit.simulation.test_plan_builder import build, make_definition

pytestmark = pytest.mark.usefixtures("fake_maxwell_boundary")


def make_request(tmp_path: Path) -> Maxwell3dExportRequest:
    return Maxwell3dExportRequest(
        plan=build((make_definition(),)),  # type: ignore[arg-type]
        release=AedtRelease(2025, 2),
        edition=AedtEdition.COMMERCIAL,
        non_graphical=True,
        output_directory=tmp_path / "out",
        project_name="Boost_inductor",
    )


def run(tmp_path: Path, app: FakeMaxwell3dApp) -> object:
    exporter = PyaedtMaxwell3dExporter(app_factory=FakeMaxwell3dAppFactory(app))
    return exporter.export(make_request(tmp_path))


def test_successful_export_runs_every_stage_in_order(tmp_path: Path) -> None:
    app = FakeMaxwell3dApp()
    result = run(tmp_path, app)
    assert tuple(stage.name for stage in result.stages) == STAGE_NAMES  # type: ignore[attr-defined]
    assert result.succeeded()  # type: ignore[attr-defined]
    assert app.released == [(True, True)]


def test_geometry_calls_are_made(tmp_path: Path) -> None:
    app = FakeMaxwell3dApp()
    run(tmp_path, app)
    names = [name for name, _ in app.calls]
    # units, then 1 core polyline + sweep + material, then 4 turn polylines
    assert ("modeler.set.model_units", {"value": "meter"}) in app.calls
    assert names.count("modeler.create_polyline") == 1 + 4
    assert names.count("modeler.sweep_around_axis") == 1
    assert names.count("modeler.create_circle") == 4
    assert names.count("modeler.rotate") == 4
    polyline_kwargs = [k for n, k in app.calls if n == "modeler.create_polyline"]
    turn_kwargs = polyline_kwargs[1]
    assert turn_kwargs["xsection_type"] == "Circle"
    assert turn_kwargs["material"] == "copper"


def test_failing_stage_truncates_and_still_releases(tmp_path: Path) -> None:
    app = FakeMaxwell3dApp(raise_on="assign_matrix")
    result = run(tmp_path, app)
    assert not result.succeeded()  # type: ignore[attr-defined]
    assert result.stages[-2].name == "matrix"  # type: ignore[attr-defined]
    assert result.stages[-2].succeeded is False  # type: ignore[attr-defined]
    assert "boom" in result.stages[-2].message  # type: ignore[attr-defined]
    assert result.stages[-1].name == "save"  # type: ignore[attr-defined]
    assert result.stages[-1].succeeded is True  # type: ignore[attr-defined]
    saves = [k for n, k in app.calls if n == "save_project"]
    assert len(saves) == 1
    assert app.released == [(True, True)]


def test_falsy_region_return_fails_stage_and_still_saves(tmp_path: Path) -> None:
    app = FakeMaxwell3dApp(falsy_on="create_air_region")
    result = run(tmp_path, app)
    assert not result.succeeded()  # type: ignore[attr-defined]
    assert result.stages[-2].name == "region"  # type: ignore[attr-defined]
    assert result.stages[-2].succeeded is False  # type: ignore[attr-defined]
    assert result.stages[-1].name == "save"  # type: ignore[attr-defined]
    assert result.stages[-1].succeeded is True  # type: ignore[attr-defined]
    saves = [k for n, k in app.calls if n == "save_project"]
    assert len(saves) == 1
    assert app.released == [(True, True)]


def test_excitations_group_coils_into_windings(tmp_path: Path) -> None:
    app = FakeMaxwell3dApp()
    run(tmp_path, app)
    coil_calls = [k for n, k in app.calls if n == "assign_coil"]
    assert len(coil_calls) == 4
    assert coil_calls[0]["polarity"] == "Positive"
    assert coil_calls[0]["conductors_number"] == 1
    winding_calls = [k for n, k in app.calls if n == "assign_winding"]
    assert len(winding_calls) == 1
    assert winding_calls[0]["winding_type"] == "Current"
    assert winding_calls[0]["is_solid"] is True
    assert winding_calls[0]["current"] == 2.0
    group_calls = [k for n, k in app.calls if n == "add_winding_coils"]
    assert group_calls[0]["assignment"] == "w1"
    assert len(group_calls[0]["coils"]) == 4


def test_eddy_region_mesh_setup_matrix_reports(tmp_path: Path) -> None:
    app = FakeMaxwell3dApp()
    result = run(tmp_path, app)
    assert result.succeeded()  # type: ignore[attr-defined]
    names = [name for name, _ in app.calls]
    eddy = [k for n, k in app.calls if n == "eddy_effects_on"]
    assert eddy[0]["enable_eddy_effects"] is True
    assert "modeler.create_air_region" in names
    mesh_calls = [k for n, k in app.calls if n == "mesh.assign_length_mesh"]
    assert len(mesh_calls) == 2
    setup_updates = [k for n, k in app.calls if n == "setup.update"]
    assert setup_updates[0]["props"]["Frequency"] == "100000Hz"
    assert setup_updates[0]["props"]["MaximumPasses"] == 10
    matrix = [k for n, k in app.calls if n == "assign_matrix"]
    assert matrix[0]["assignment"] is not None  # schema object passed positionally
    reports = [k for n, k in app.calls if n == "post.create_report"]
    assert len(reports) == 2
    assert ("validate_simple", {}) in app.calls
    saves = [k for n, k in app.calls if n == "save_project"]
    assert saves[0]["path"].endswith("Boost_inductor.aedt")


def native_request(tmp_path: Path) -> Maxwell3dExportRequest:
    from dataclasses import replace

    base = make_request(tmp_path)
    decision = DcBiasDecision(DcBiasStrategy.NATIVE_INCLUDE_DC_FIELDS, False, "native ok")
    windings = tuple(replace(g, dc_current_a=5.0) for g in base.plan.windings)
    return replace(base, plan=replace(base.plan, windings=windings, dc_bias=decision))


def test_native_dc_sets_setup_flag_and_winding_dc(tmp_path: Path) -> None:
    app = FakeMaxwell3dApp()
    exporter = PyaedtMaxwell3dExporter(app_factory=FakeMaxwell3dAppFactory(app))
    result = exporter.export(native_request(tmp_path))
    assert result.succeeded()
    setup_updates = [k for n, k in app.calls if n == "setup.update"]
    assert setup_updates[0]["props"]["IncludeDcFields"] is True
    dc_sets = [k for n, k in app.calls if n == "winding.set_prop"]
    assert dc_sets == [{"name": "w1", "key": "DCValue", "value": "5A"}]
    winding_updates = [k for n, k in app.calls if n == "winding.update"]
    assert len(winding_updates) == 1


def test_no_dc_flag_without_native_decision(tmp_path: Path) -> None:
    app = FakeMaxwell3dApp()
    exporter = PyaedtMaxwell3dExporter(app_factory=FakeMaxwell3dAppFactory(app))
    exporter.export(make_request(tmp_path))
    setup_updates = [k for n, k in app.calls if n == "setup.update"]
    assert "IncludeDcFields" not in setup_updates[0]["props"]
    assert not [k for n, k in app.calls if n == "winding.set_prop"]


def test_native_dc_only_applies_to_nonzero_windings(tmp_path: Path) -> None:
    from dataclasses import replace

    plan = build(
        (
            make_definition(winding_id="w1", sector_deg=100.0, dc_current_a=5.0),
            make_definition(
                winding_id="w2", start_angle_deg=180.0, sector_deg=100.0, dc_current_a=0.0
            ),
        ),
        dc_bias_decision=DcBiasDecision(
            DcBiasStrategy.NATIVE_INCLUDE_DC_FIELDS, False, "native ok"
        ),
    )
    request = replace(make_request(tmp_path), plan=plan)
    app = FakeMaxwell3dApp()
    exporter = PyaedtMaxwell3dExporter(app_factory=FakeMaxwell3dAppFactory(app))
    result = exporter.export(request)
    assert result.succeeded()
    dc_sets = [k for n, k in app.calls if n == "winding.set_prop"]
    assert dc_sets == [{"name": "w1", "key": "DCValue", "value": "5A"}]
    winding_updates = [k for n, k in app.calls if n == "winding.update"]
    assert len(winding_updates) == 1
    winding_assigns = [k for n, k in app.calls if n == "assign_winding"]
    assert len(winding_assigns) == 2
