from __future__ import annotations

import pytest

from inductor_designer.domain.project import RequestedOutput, SimulationRecipe
from inductor_designer.domain.winding import CurrentDirection, WindingDefinition
from inductor_designer.geometry.packing import WindingSpec, pack_winding
from inductor_designer.geometry.planar import PlanarModel, build_planar_model
from inductor_designer.materials.records import MaterialRecord
from inductor_designer.simulation.maxwell2d_plan import Maxwell2dDesignPlan
from inductor_designer.simulation.maxwell_plan import PlanBuildError, Polarity
from inductor_designer.simulation.plan_builder2d import build_maxwell2d_plan
from inductor_designer.simulation.run_contracts import EffectiveWindingInput
from tests.unit.simulation.test_maxwell_plan import (
    make_approved_material_record,
    make_multi_bh_material_record,
)
from tests.unit.simulation.test_plan_builder import (
    BARE,
    CORE,
    make_definition,
    make_effective,
    make_recipe,
)


def planar_for(definitions: tuple[WindingDefinition, ...]) -> PlanarModel:
    packings = tuple(
        pack_winding(
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
        for definition in definitions
    )
    return build_planar_model(
        CORE,
        packings,
        {definition.winding_id: BARE / 2.0 for definition in definitions},
    )


def build2d(
    definitions: tuple[WindingDefinition, ...],
    effective_inputs: tuple[EffectiveWindingInput, ...] | None = None,
    *,
    frequency_hz: float = 100_000.0,
    recipe: SimulationRecipe | None = None,
    material_record: MaterialRecord | None = None,
) -> Maxwell2dDesignPlan:
    effective = effective_inputs
    if effective is None:
        effective = tuple(
            make_effective(winding_id=definition.winding_id) for definition in definitions
        )
    return build_maxwell2d_plan(
        planar_for(definitions),
        definitions,
        effective,
        {definition.winding_id: BARE for definition in definitions},
        frequency_hz=frequency_hz,
        recipe=recipe or make_recipe(),
        material_record=material_record or make_approved_material_record(),
        material_bh_series_id=None,
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
    assert len(group.conductors) == 8
    assert group.conductors[0].name == "w1_C001"
    assert group.conductors[0].radius_m == BARE / 2.0


def test_return_conductor_polarity_inverts() -> None:
    plan = build2d((make_definition(),))
    polarities = {conductor.polarity for conductor in plan.windings[0].conductors}
    assert polarities == {Polarity.POSITIVE, Polarity.NEGATIVE}
    positives = [
        conductor
        for conductor in plan.windings[0].conductors
        if conductor.polarity is Polarity.POSITIVE
    ]
    negatives = [
        conductor
        for conductor in plan.windings[0].conductors
        if conductor.polarity is Polarity.NEGATIVE
    ]
    assert len(positives) == len(negatives) == 4


def test_effective_current_direction_controls_base_polarity() -> None:
    reverse = build2d(
        (make_definition(),),
        (make_effective(current_direction=CurrentDirection.REVERSE),),
    )
    assert reverse.windings[0].conductors[0].polarity is Polarity.NEGATIVE


def test_two_d_approximation_note_always_present() -> None:
    plan = build2d((make_definition(),))
    assert any("approximate" in note and "cross-section" in note for note in plan.notes)


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
        build2d((make_definition(),), effective_inputs)


def test_selected_bh_series_is_threaded_to_2d_plan() -> None:
    definitions = (make_definition(),)
    plan = build_maxwell2d_plan(
        planar_for(definitions),
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


def test_shared_frequency_recipe_and_requested_reports_are_mapped() -> None:
    plan = build2d(
        (make_definition(),),
        frequency_hz=80_000.0,
        recipe=make_recipe(
            RequestedOutput.RESISTANCE,
            maximum_passes=14,
            percent_error=0.5,
        ),
    )

    assert plan.setup.frequency_hz == 80_000.0
    assert plan.setup.maximum_passes == 14
    assert plan.setup.percent_error == 0.5
    assert [report.expression for report in plan.reports] == ["Matrix1.R(w1,w1)"]
