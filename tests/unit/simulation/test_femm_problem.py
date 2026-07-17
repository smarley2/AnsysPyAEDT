from __future__ import annotations

from inductor_designer.simulation.femm_problem import (
    COPPER_CONDUCTIVITY_MS_PER_M,
    femm_problem_from_plan,
)
from inductor_designer.simulation.maxwell_plan import Polarity
from tests.unit.simulation.test_plan_builder import make_definition
from tests.unit.simulation.test_plan_builder2d import build2d


def test_problem_maps_plan_essentials() -> None:
    plan = build2d((make_definition(),))
    problem = femm_problem_from_plan(plan)  # type: ignore[arg-type]
    assert problem.frequency_hz == 100_000.0
    assert problem.depth_m == plan.model_depth_m
    assert problem.core.r_inner_m == plan.core.r_inner_m
    assert problem.core.material == plan.core.material.name
    assert [c.name for c in problem.circuits] == ["w1"]
    assert problem.circuits[0].current_peak_a == 2.0
    assert len(problem.conductors) == 8


def test_polarity_becomes_signed_turns() -> None:
    plan = build2d((make_definition(),))
    problem = femm_problem_from_plan(plan)  # type: ignore[arg-type]
    signs = {conductor.turns for conductor in problem.conductors}
    assert signs == {1, -1}
    positives = [c for c in problem.conductors if c.turns == 1]
    assert len(positives) == 4
    for conductor, plan_conductor in zip(
        problem.conductors, plan.windings[0].conductors, strict=True
    ):
        expected = 1 if plan_conductor.polarity is Polarity.POSITIVE else -1
        assert conductor.turns == expected


def test_solid_winding_gets_conductive_copper() -> None:
    plan = build2d((make_definition(),))  # SOLID mode default
    problem = femm_problem_from_plan(plan)  # type: ignore[arg-type]
    materials = {m.name: m for m in problem.materials}
    assert problem.conductors[0].material == "Copper_solid"
    assert materials["Copper_solid"].conductivity_ms_per_m == COPPER_CONDUCTIVITY_MS_PER_M
    assert materials["Air"].relative_permeability == 1.0
