from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from inductor_designer.adapters.pyaedt.maxwell2d import PyaedtMaxwell2dExporter
from inductor_designer.application.ports.maxwell2d_exporter import STAGE_NAMES_2D
from tests.contract.test_maxwell2d_exporter_contract import make_request
from tests.fakes.maxwell2d_app import FakeMaxwell2dApp, FakeMaxwell2dAppFactory
from tests.unit.simulation.test_maxwell_plan import make_approved_material_record
from tests.unit.simulation.test_plan_builder import make_definition
from tests.unit.simulation.test_plan_builder2d import build2d

pytestmark = pytest.mark.usefixtures("fake_maxwell_boundary")


def run(tmp_path: Path, app: FakeMaxwell2dApp) -> object:
    exporter = PyaedtMaxwell2dExporter(app_factory=FakeMaxwell2dAppFactory(app))
    return exporter.export(make_request(tmp_path))


def test_full_stage_sequence_and_release(tmp_path: Path) -> None:
    app = FakeMaxwell2dApp()
    result = run(tmp_path, app)
    assert tuple(stage.name for stage in result.stages) == STAGE_NAMES_2D
    assert result.succeeded(STAGE_NAMES_2D)
    assert app.released == [(True, True)]


def test_geometry_and_depth_calls(tmp_path: Path) -> None:
    app = FakeMaxwell2dApp()
    run(tmp_path, app)
    names = [name for name, _ in app.calls]
    depth_sets = [k for n, k in app.calls if n == "set.model_depth"]
    assert depth_sets and depth_sets[0]["value"].endswith("meter")
    assert names.index("set.model_depth") < names.index("create_setup")
    # core outer + bore + 8 conductors
    assert names.count("modeler.create_circle") == 2 + 8
    assert names.count("modeler.subtract") == 1
    coil_calls = [k for n, k in app.calls if n == "assign_coil"]
    assert len(coil_calls) == 8
    polarities = {k["polarity"] for k in coil_calls}
    assert polarities == {"Positive", "Negative"}
    winding_calls = [k for n, k in app.calls if n == "assign_winding"]
    assert len(winding_calls) == 1
    region_calls = [k for n, k in app.calls if n == "modeler.create_region"]
    assert region_calls == [{"pad_value": 100.0, "pad_type": "Percentage Offset"}]
    balloon_calls = [k for n, k in app.calls if n == "assign_balloon"]
    assert len(balloon_calls) == 1
    assert balloon_calls[0]["assignment"] == [
        "Region_edge1",
        "Region_edge2",
        "Region_edge3",
        "Region_edge4",
    ]
    assert balloon_calls[0]["boundary"] == "Balloon"


def test_nonzero_dc_current_never_reaches_the_generated_design(tmp_path: Path) -> None:
    # 2D runs AC-only (decision: Fabio Posser, 2026-08-07): the plan carries
    # the requested DC current for the record, but the adapter must never
    # forward it into `assign_winding` or set any DC-flavored property.
    app = FakeMaxwell2dApp()
    plan = build2d((make_definition(),))
    dc_plan = replace(
        plan,
        windings=tuple(replace(group, dc_current_a=5.0) for group in plan.windings),
    )
    request = replace(make_request(tmp_path), plan=dc_plan)
    exporter = PyaedtMaxwell2dExporter(app_factory=FakeMaxwell2dAppFactory(app))

    result = exporter.export(request)

    assert result.succeeded(STAGE_NAMES_2D)
    winding_calls = [k for n, k in app.calls if n == "assign_winding"]
    assert len(winding_calls) == 1
    assert set(winding_calls[0]) == {
        "assignment",
        "winding_type",
        "is_solid",
        "current",
        "phase",
        "name",
    }
    assert not any("dc" in key.lower() for key in winding_calls[0])


def test_nonlinear_material_and_steinmetz_calls_have_verified_shapes(tmp_path: Path) -> None:
    app = FakeMaxwell2dApp()
    request = replace(
        make_request(tmp_path),
        plan=build2d(
            (make_definition(),), material_record=make_approved_material_record()
        ),
    )
    exporter = PyaedtMaxwell2dExporter(app_factory=FakeMaxwell2dAppFactory(app))

    result = exporter.export(request)

    assert result.succeeded(STAGE_NAMES_2D)
    assert (
        "material.set.permeability",
        {
            "material": "Magnetics_Kool_Mu_60_r0123456789ab",
            "value": [[0.0, 0.0], [0.025132741, 100.0]],
        },
    ) in app.calls
    assert (
        "material.set_power_ferrite_coreloss",
        {
            "material": "Magnetics_Kool_Mu_60_r0123456789ab",
            "cm": 2.5,
            "x": 1.4,
            "y": 2.3,
        },
    ) in app.calls


def test_falsy_steinmetz_setter_fails_material_stage(tmp_path: Path) -> None:
    app = FakeMaxwell2dApp(coreloss_result=False)
    request = replace(
        make_request(tmp_path),
        plan=build2d(
            (make_definition(),), material_record=make_approved_material_record()
        ),
    )
    exporter = PyaedtMaxwell2dExporter(app_factory=FakeMaxwell2dAppFactory(app))

    result = exporter.export(request)

    assert not result.succeeded(STAGE_NAMES_2D)
    material_stage = next(stage for stage in result.stages if stage.name == "materials")
    assert material_stage.succeeded is False
    assert "core-loss" in material_stage.message


def test_failing_stage_truncates_and_releases(tmp_path: Path) -> None:
    app = FakeMaxwell2dApp(raise_on="assign_matrix")
    result = run(tmp_path, app)
    assert not result.succeeded(STAGE_NAMES_2D)
    assert result.stages[-2].name == "matrix"
    assert result.stages[-2].succeeded is False
    assert "boom" in result.stages[-2].message
    assert result.stages[-1].name == "save"
    assert result.stages[-1].succeeded is True
    saves = [k for n, k in app.calls if n == "save_project"]
    assert len(saves) == 1
    assert app.released == [(True, True)]


def test_falsy_region_return_fails_stage_and_still_saves(tmp_path: Path) -> None:
    app = FakeMaxwell2dApp(falsy_on="create_region")
    result = run(tmp_path, app)
    assert not result.succeeded(STAGE_NAMES_2D)
    assert result.stages[-2].name == "region"
    assert result.stages[-2].succeeded is False
    assert result.stages[-1].name == "save"
    assert result.stages[-1].succeeded is True
    saves = [k for n, k in app.calls if n == "save_project"]
    assert len(saves) == 1
    assert app.released == [(True, True)]


def test_falsy_balloon_return_fails_stage_and_still_saves(tmp_path: Path) -> None:
    app = FakeMaxwell2dApp(falsy_on="assign_balloon")
    result = run(tmp_path, app)
    assert not result.succeeded(STAGE_NAMES_2D)
    assert result.stages[-2].name == "region"
    assert result.stages[-2].succeeded is False
    assert "assign_balloon" in result.stages[-2].message
    assert result.stages[-1].name == "save"
    assert result.stages[-1].succeeded is True
    saves = [k for n, k in app.calls if n == "save_project"]
    assert len(saves) == 1
    assert app.released == [(True, True)]


def test_initial_mesh_uses_the_slider_only(tmp_path: Path) -> None:
    """Maxwell 2D offers neither the TAU mesher nor the curvilinear switch, so the
    3D workaround for the DC-bias mapping failure cannot be applied here."""
    app = FakeMaxwell2dApp()
    result = run(tmp_path, app)
    assert result.succeeded(STAGE_NAMES_2D)  # type: ignore[attr-defined]

    initial_mesh = [k for n, k in app.calls if n == "mesh.assign_initial_mesh_from_slider"]
    assert len(initial_mesh) == 1
    assert initial_mesh[0] == {"level": 6}


def test_model_units_switch_to_mm_after_mesh_ops(tmp_path: Path) -> None:
    """TAU's 2D surface mesher fails at meter model units once a feature (the
    conductor-to-core clearance) drops to tens of microns; see GitHub issue #14.
    All geometry and mesh lengths must already be set (in meter units) before
    the switch, so this must land after 'CoreLength', not before."""
    app = FakeMaxwell2dApp()
    result = run(tmp_path, app)
    assert result.succeeded(STAGE_NAMES_2D)  # type: ignore[attr-defined]

    names = [name for name, _ in app.calls]
    unit_sets = [k["value"] for n, k in app.calls if n == "modeler.set.model_units"]
    assert unit_sets == ["meter", "mm"]
    length_mesh_positions = [i for i, n in enumerate(names) if n == "mesh.assign_length_mesh"]
    mm_position = names.index("modeler.set.model_units", length_mesh_positions[0] + 1)
    assert max(length_mesh_positions) < mm_position < names.index("create_setup")


def test_setup_requires_at_least_three_passes(tmp_path: Path) -> None:
    """A single converged pass is not enough evidence that the 2D solve has
    settled; Maxwell 2D has none of the DC-bias mesh-mapping fragility that
    keeps Maxwell 3D pinned to one adaptive pass (see
    docs/development/dc-bias-solve-limitation.md), so raising the floor here
    carries no regression risk for 3D."""
    app = FakeMaxwell2dApp()
    result = run(tmp_path, app)
    assert result.succeeded(STAGE_NAMES_2D)  # type: ignore[attr-defined]

    setup_updates = [k for n, k in app.calls if n == "setup.update"]
    assert setup_updates[0]["props"]["MinimumPasses"] == 3
