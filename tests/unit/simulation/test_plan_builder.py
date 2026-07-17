from __future__ import annotations

import pytest

from inductor_designer.domain.winding import (
    ConductorMode,
    CurrentDirection,
    WindingDefinition,
    WindingDirection,
)
from inductor_designer.geometry.core_solid import FinishedCore
from inductor_designer.geometry.packing import WindingSpec, pack_winding
from inductor_designer.simulation.capabilities import DcBiasDecision, DcBiasStrategy
from inductor_designer.simulation.maxwell_plan import (
    SOLUTION_TYPE_DC,
    PlanBuildError,
    Polarity,
)
from inductor_designer.simulation.plan_builder import build_maxwell3d_plan
from tests.unit.simulation.test_maxwell_plan import make_core_record

CORE = FinishedCore(
    r_inner_m=0.00973, r_outer_m=0.01683, half_height_m=0.005715, corner_radius_m=0.0
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
        "current_direction": CurrentDirection.FORWARD,
        "terminal_intent": "",
        "ac_magnitude_a": 2.0,
        "ac_phase_deg": 0.0,
        "frequency_hz": 100_000.0,
        "dc_current_a": 0.0,
    }
    values.update(overrides)
    return WindingDefinition(**values)  # type: ignore[arg-type]


def pack(definition: WindingDefinition) -> object:
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
    dc_bias_decision: DcBiasDecision | None = None,
) -> object:
    packings = tuple(pack(d) for d in definitions)
    return build_maxwell3d_plan(
        CORE,
        make_core_record(),
        packings,
        definitions,
        {d.winding_id: BARE for d in definitions},
        dc_bias_decision=dc_bias_decision,
    )


def test_plan_shape_and_names() -> None:
    plan = build((make_definition(),))
    assert plan.design_name == "Inductor3D"
    assert plan.solution_type == "EddyCurrent"
    assert plan.core.name == "Core"
    group = plan.windings[0]
    assert group.name == "w1"
    assert [t.name for t in group.turns] == [
        "w1_L01_T001", "w1_L01_T002", "w1_L01_T003", "w1_L01_T004",
    ]
    assert group.turns[0].terminal.name == "w1_L01_T001_Term"
    assert group.turns[0].bare_diameter_m == BARE
    assert len(group.turns[0].segments) == 8


def test_colliding_ids_stay_distinct() -> None:
    plan = build(
        (
            make_definition(winding_id="w 1", start_angle_deg=0.0, sector_deg=100.0),
            make_definition(winding_id="w-1", start_angle_deg=180.0, sector_deg=100.0),
        )
    )
    assert [g.name for g in plan.windings] == ["w_1", "w_1_2"]


def test_polarity_convention() -> None:
    cases = [
        (CurrentDirection.FORWARD, WindingDirection.COUNTERCLOCKWISE, Polarity.POSITIVE),
        (CurrentDirection.FORWARD, WindingDirection.CLOCKWISE, Polarity.NEGATIVE),
        (CurrentDirection.REVERSE, WindingDirection.COUNTERCLOCKWISE, Polarity.NEGATIVE),
        (CurrentDirection.REVERSE, WindingDirection.CLOCKWISE, Polarity.POSITIVE),
    ]
    for current, direction, expected in cases:
        plan = build((make_definition(current_direction=current, winding_direction=direction),))
        assert plan.windings[0].turns[0].terminal.polarity is expected, (current, direction)


def test_mixed_frequencies_refused() -> None:
    with pytest.raises(PlanBuildError, match="frequency"):
        build(
            (
                make_definition(winding_id="w1", sector_deg=100.0),
                make_definition(
                    winding_id="w2", start_angle_deg=180.0, sector_deg=100.0,
                    frequency_hz=50_000.0,
                ),
            )
        )


NATIVE = DcBiasDecision(DcBiasStrategy.NATIVE_INCLUDE_DC_FIELDS, False, "native ok")
FALLBACK = DcBiasDecision(
    DcBiasStrategy.MAGNETOSTATIC_INCREMENTAL_FALLBACK, True, "2024 R2 fallback"
)
BLOCKED = DcBiasDecision(DcBiasStrategy.BLOCKED, False, "unreviewed")


def test_native_decision_lands_in_plan_and_notes() -> None:
    plan = build((make_definition(dc_current_a=5.0),), dc_bias_decision=NATIVE)
    assert plan.dc_bias is NATIVE
    assert plan.solution_type == SOLUTION_TYPE_DC
    assert any("AC Magnetic with DC" in note for note in plan.notes)
    assert any("linear" in note for note in plan.notes)


def test_native_decision_without_dc_current_keeps_eddy_current_solution() -> None:
    plan = build((make_definition(dc_current_a=0.0),), dc_bias_decision=NATIVE)
    assert plan.solution_type == "EddyCurrent"


def test_fallback_decision_keeps_eddy_current_solution() -> None:
    plan = build((make_definition(dc_current_a=5.0),), dc_bias_decision=FALLBACK)
    assert plan.solution_type == "EddyCurrent"


def test_fallback_decision_notes_deferral() -> None:
    plan = build((make_definition(dc_current_a=5.0),), dc_bias_decision=FALLBACK)
    assert any("deferred" in note and "2024 R2" in note for note in plan.notes)


def test_blocked_decision_notes_reason() -> None:
    plan = build((make_definition(dc_current_a=5.0),), dc_bias_decision=BLOCKED)
    assert any("unreviewed" in note for note in plan.notes)


def test_zero_dc_current_emits_no_dc_notes() -> None:
    plan = build((make_definition(dc_current_a=0.0),), dc_bias_decision=NATIVE)
    assert not any("DC" in note for note in plan.notes)


def test_setup_mesh_reports_and_notes() -> None:
    plan = build((make_definition(dc_current_a=5.0),))
    assert plan.setup.frequency_hz == 100_000.0
    assert plan.mesh.conductor_max_length_m == round(1.5 * BARE, 9)
    assert plan.mesh.core_max_length_m == round(min(0.0071, 0.01143) / 3.0, 9)
    assert [r.expression for r in plan.reports] == ["Matrix1.R(w1,w1)", "Matrix1.L(w1,w1)"]
    assert any("no capability decision" in note for note in plan.notes)
