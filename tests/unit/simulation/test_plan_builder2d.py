from __future__ import annotations

import pytest

from inductor_designer.geometry.packing import WindingSpec, pack_winding
from inductor_designer.geometry.planar import build_planar_model
from inductor_designer.simulation.maxwell_plan import PlanBuildError, Polarity
from inductor_designer.simulation.plan_builder2d import build_maxwell2d_plan
from tests.unit.simulation.test_maxwell_plan import make_core_record
from tests.unit.simulation.test_plan_builder import BARE, CORE, make_definition


def planar_for(definitions: tuple[object, ...]) -> object:
    packings = tuple(
        pack_winding(
            CORE,
            WindingSpec(
                winding_id=d.winding_id,
                turns=d.turns,
                insulated_diameter_m=0.0011,
                start_deg=d.start_angle_deg,
                sector_deg=d.sector_deg,
                min_spacing_m=d.min_spacing_m,
                min_clearance_m=d.min_clearance_m,
            ),
        )
        for d in definitions
    )
    return build_planar_model(CORE, packings, {d.winding_id: BARE / 2.0 for d in definitions})


def build2d(definitions: tuple[object, ...], **kwargs: object) -> object:
    return build_maxwell2d_plan(
        planar_for(definitions),
        make_core_record(),
        definitions,
        {d.winding_id: BARE for d in definitions},
        **kwargs,
    )


def test_plan_shape_names_and_depth() -> None:
    plan = build2d((make_definition(),))
    assert plan.design_name == "Inductor2D"
    assert plan.solution_type == "EddyCurrent"
    assert plan.model_depth_m == round(2.0 * CORE.half_height_m, 9)
    assert plan.core.r_inner_m == CORE.r_inner_m
    assert plan.core.r_outer_m == CORE.r_outer_m
    group = plan.windings[0]
    assert group.name == "w1"
    # 4 turns -> 8 conductors (go/return pairs)
    assert len(group.conductors) == 8
    assert group.conductors[0].name == "w1_C001"
    assert group.conductors[0].radius_m == BARE / 2.0


def test_return_conductor_polarity_inverts() -> None:
    plan = build2d((make_definition(),))  # FORWARD + CCW -> base Positive
    polarities = {c.polarity for c in plan.windings[0].conductors}
    assert polarities == {Polarity.POSITIVE, Polarity.NEGATIVE}
    positives = [c for c in plan.windings[0].conductors if c.polarity is Polarity.POSITIVE]
    negatives = [c for c in plan.windings[0].conductors if c.polarity is Polarity.NEGATIVE]
    assert len(positives) == len(negatives) == 4


def test_two_d_approximation_note_always_present() -> None:
    plan = build2d((make_definition(dc_current_a=0.0),))
    assert any("approximate" in note and "cross-section" in note for note in plan.notes)


def test_mixed_frequencies_refused() -> None:
    with pytest.raises(PlanBuildError, match="frequency"):
        build2d(
            (
                make_definition(winding_id="w1", sector_deg=100.0),
                make_definition(
                    winding_id="w2", start_angle_deg=180.0, sector_deg=100.0,
                    frequency_hz=50_000.0,
                ),
            )
        )
