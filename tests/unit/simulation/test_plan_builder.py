from __future__ import annotations

from dataclasses import fields

import pytest

from inductor_designer.domain.project import MeshIntent, RequestedOutput, SimulationRecipe
from inductor_designer.domain.winding import (
    ConductorMode,
    CurrentDirection,
    WindingDefinition,
    WindingDirection,
)
from inductor_designer.geometry.core_solid import FinishedCore
from inductor_designer.geometry.packing import PackedWinding, WindingSpec, pack_winding
from inductor_designer.materials.records import MaterialRecord
from inductor_designer.simulation.capabilities import DcBiasDecision, DcBiasStrategy
from inductor_designer.simulation.maxwell_plan import (
    SOLUTION_TYPE_DC,
    GeometryOnlyMaxwell3dPlan,
    Maxwell3dDesignPlan,
    PlanBuildError,
    Polarity,
)
from inductor_designer.simulation.plan_builder import (
    build_geometry_only_maxwell3d_plan,
    build_maxwell3d_plan,
)
from inductor_designer.simulation.run_contracts import EffectiveWindingInput
from tests.unit.simulation.test_maxwell_plan import (
    make_approved_material_record,
    make_multi_bh_material_record,
)

CORE = FinishedCore(
    r_inner_m=0.00973,
    r_outer_m=0.01683,
    half_height_m=0.005715,
    corner_radius_m=0.0,
)
BARE = 0.001


def make_definition(**overrides: object) -> WindingDefinition:
    values: dict[str, object] = {
        "winding_id": "w1",
        "label": "Primary",
        "turns": 4,
        "conductor_name": "AWG 18",
        "mode": ConductorMode.SOLID,
        "start_angle_deg": 0.0,
        "sector_deg": 150.0,
        "min_spacing_m": 0.0002,
        "min_clearance_m": 0.001,
        "winding_direction": WindingDirection.COUNTERCLOCKWISE,
        "terminal_intent": "",
    }
    values.update(overrides)
    return WindingDefinition(**values)  # type: ignore[arg-type]


def make_effective(**overrides: object) -> EffectiveWindingInput:
    values: dict[str, object] = {
        "winding_id": "w1",
        "ac_rms_current_a": 2.0,
        "ac_peak_current_a": 2.8284271247461903,
        "phase_deg": 0.0,
        "dc_current_a": 0.0,
        "current_direction": CurrentDirection.FORWARD,
    }
    values.update(overrides)
    return EffectiveWindingInput(**values)  # type: ignore[arg-type]


def make_recipe(
    *requested_outputs: RequestedOutput,
    maximum_passes: int = 10,
    percent_error: float = 1.0,
) -> SimulationRecipe:
    return SimulationRecipe(
        mesh_intent=MeshIntent.STANDARD,
        maximum_passes=maximum_passes,
        percent_error=percent_error,
        requested_outputs=requested_outputs
        or (RequestedOutput.RESISTANCE, RequestedOutput.INDUCTANCE),
    )


def pack(definition: WindingDefinition) -> PackedWinding:
    return pack_winding(
        CORE,
        WindingSpec(
            winding_id=definition.winding_id,
            turns=definition.turns,
            insulated_diameter_m=0.0011,
            start_deg=definition.start_angle_deg,
            sector_deg=definition.sector_deg,
            min_spacing_m=definition.min_spacing_m,
            min_clearance_m=definition.min_clearance_m,
        ),
    )


def build(
    definitions: tuple[WindingDefinition, ...],
    effective_inputs: tuple[EffectiveWindingInput, ...] | None = None,
    dc_bias_decision: DcBiasDecision | None = None,
    material_record: MaterialRecord | None = None,
    *,
    frequency_hz: float = 100_000.0,
    recipe: SimulationRecipe | None = None,
) -> Maxwell3dDesignPlan:
    packings = tuple(pack(definition) for definition in definitions)
    effective = effective_inputs
    if effective is None:
        effective = tuple(
            make_effective(winding_id=definition.winding_id) for definition in definitions
        )
    return build_maxwell3d_plan(
        CORE,
        packings,
        definitions,
        effective,
        {definition.winding_id: BARE for definition in definitions},
        frequency_hz=frequency_hz,
        recipe=recipe or make_recipe(),
        dc_bias_decision=dc_bias_decision,
        material_record=material_record or make_approved_material_record(),
        material_bh_series_id=None,
    )


def test_plan_shape_and_names() -> None:
    plan = build((make_definition(),))
    assert plan.design_name == "Inductor3D"
    assert plan.solution_type == "EddyCurrent"
    assert plan.core.name == "Core"
    group = plan.windings[0]
    assert group.name == "w1"
    assert [turn.name for turn in group.turns] == [
        "w1_L01_T001",
        "w1_L01_T002",
        "w1_L01_T003",
        "w1_L01_T004",
    ]
    assert group.turns[0].terminal.name == "w1_L01_T001_Term"
    assert group.turns[0].bare_diameter_m == BARE
    assert len(group.turns[0].segments) == 8


def test_colliding_ids_stay_distinct() -> None:
    definitions = (
        make_definition(winding_id="w 1", start_angle_deg=0.0, sector_deg=100.0),
        make_definition(winding_id="w-1", start_angle_deg=180.0, sector_deg=100.0),
    )
    plan = build(
        definitions,
        (
            make_effective(winding_id="w 1"),
            make_effective(winding_id="w-1"),
        ),
    )
    assert [group.name for group in plan.windings] == ["w_1", "w_1_2"]


@pytest.mark.parametrize(
    ("current", "direction", "expected"),
    (
        (
            CurrentDirection.FORWARD,
            WindingDirection.COUNTERCLOCKWISE,
            Polarity.POSITIVE,
        ),
        (CurrentDirection.FORWARD, WindingDirection.CLOCKWISE, Polarity.NEGATIVE),
        (
            CurrentDirection.REVERSE,
            WindingDirection.COUNTERCLOCKWISE,
            Polarity.NEGATIVE,
        ),
        (CurrentDirection.REVERSE, WindingDirection.CLOCKWISE, Polarity.POSITIVE),
    ),
)
def test_polarity_uses_effective_current_direction(
    current: CurrentDirection,
    direction: WindingDirection,
    expected: Polarity,
) -> None:
    plan = build(
        (make_definition(winding_direction=direction),),
        (make_effective(current_direction=current),),
    )
    assert plan.windings[0].turns[0].terminal.polarity is expected


@pytest.mark.parametrize(
    ("effective_inputs", "message"),
    (
        ((), "Missing effective winding inputs"),
        (
            (make_effective(), make_effective(ac_peak_current_a=3.0)),
            "Duplicate effective winding ids",
        ),
        (
            (make_effective(), make_effective(winding_id="unknown")),
            "Unknown effective winding ids",
        ),
    ),
)
def test_invalid_effective_winding_ids_are_refused(
    effective_inputs: tuple[EffectiveWindingInput, ...],
    message: str,
) -> None:
    with pytest.raises(PlanBuildError, match=message):
        build((make_definition(),), effective_inputs)


NATIVE = DcBiasDecision(DcBiasStrategy.NATIVE_INCLUDE_DC_FIELDS, False, "native ok")
BLOCKED = DcBiasDecision(DcBiasStrategy.BLOCKED, False, "unreviewed")


def test_native_decision_lands_in_plan_and_notes() -> None:
    plan = build(
        (make_definition(),),
        (make_effective(dc_current_a=5.0),),
        dc_bias_decision=NATIVE,
    )
    assert plan.dc_bias is NATIVE
    assert plan.solution_type == SOLUTION_TYPE_DC
    assert any("AC Magnetic with DC" in note for note in plan.notes)
    assert not any("linear" in note for note in plan.notes)


def test_native_decision_without_dc_current_keeps_eddy_current_solution() -> None:
    plan = build((make_definition(),), dc_bias_decision=NATIVE)
    assert plan.solution_type == "EddyCurrent"


def test_blocked_decision_keeps_eddy_current_and_records_reason() -> None:
    plan = build(
        (make_definition(),),
        (make_effective(dc_current_a=5.0),),
        dc_bias_decision=BLOCKED,
    )

    assert plan.solution_type == "EddyCurrent"
    assert any("unreviewed" in note for note in plan.notes)
    assert not any("Magnetostatic" in note for note in plan.notes)


def test_zero_dc_current_emits_no_dc_notes() -> None:
    plan = build((make_definition(),), dc_bias_decision=NATIVE)
    assert not any("DC" in note for note in plan.notes)


def test_selected_bh_series_is_threaded_to_3d_plan() -> None:
    definitions = (make_definition(),)
    plan = build_maxwell3d_plan(
        CORE,
        tuple(pack(definition) for definition in definitions),
        definitions,
        (make_effective(),),
        {"w1": BARE},
        frequency_hz=100_000.0,
        recipe=make_recipe(),
        material_record=make_multi_bh_material_record(),
        material_bh_series_id="bh-100c",
    )

    assert plan.core.material.bh_curve == ((0.0, 0.0), (0.03, 120.0))
    assert plan.core.material.bh_series_id == "bh-100c"


def test_setup_mesh_and_requested_reports() -> None:
    plan = build(
        (make_definition(),),
        frequency_hz=80_000.0,
        recipe=make_recipe(
            RequestedOutput.INDUCTANCE,
            maximum_passes=14,
            percent_error=0.5,
        ),
    )
    assert plan.setup.frequency_hz == 80_000.0
    assert plan.setup.maximum_passes == 14
    assert plan.setup.percent_error == 0.5
    assert plan.mesh.conductor_max_length_m == round(1.5 * BARE, 9)
    assert plan.mesh.core_max_length_m == round(min(0.0071, 0.01143) / 3.0, 9)
    assert [report.expression for report in plan.reports] == ["Matrix1.L(w1,w1)"]


def test_geometry_only_plan_carries_paths_and_diameters_only() -> None:
    definition = make_definition()
    solve_ready = build((definition,))
    geometry_only = build_geometry_only_maxwell3d_plan(
        CORE,
        (pack(definition),),
        (definition,),
        {"w1": BARE},
    )

    assert geometry_only.core_profile == solve_ready.core.profile
    assert geometry_only.windings[0].turns[0].segments == (
        solve_ready.windings[0].turns[0].segments
    )
    assert geometry_only.windings[0].turns[0].bare_diameter_m == BARE
    assert {field.name for field in fields(GeometryOnlyMaxwell3dPlan)} == {
        "design_name",
        "core_name",
        "core_profile",
        "windings",
        "notes",
    }
    assert {field.name for field in fields(type(geometry_only.windings[0]))} == {
        "name",
        "winding_id",
        "turns",
    }
    assert {field.name for field in fields(type(geometry_only.windings[0].turns[0]))} == {
        "name",
        "segments",
        "bare_diameter_m",
    }
