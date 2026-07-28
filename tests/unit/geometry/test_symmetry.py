from __future__ import annotations

import dataclasses

from inductor_designer.domain.project import WindingOperatingPoint
from inductor_designer.domain.winding import CurrentDirection, WindingDirection
from inductor_designer.geometry.symmetry import (
    SymmetryPlan,
    SymmetryRefusal,
    propose_symmetry_plan,
)
from tests.unit.domain.test_project import make_operating_point, make_winding


def trio(sector: float = 100.0) -> tuple[object, object, object]:
    return (
        make_winding(winding_id="w1", start_angle_deg=0.0, sector_deg=sector),
        make_winding(winding_id="w2", start_angle_deg=120.0, sector_deg=sector),
        make_winding(winding_id="w3", start_angle_deg=240.0, sector_deg=sector),
    )


def operating_trio() -> tuple[WindingOperatingPoint, ...]:
    return (
        WindingOperatingPoint("w1", 2.0, 0.0, 5.0, CurrentDirection.FORWARD),
        WindingOperatingPoint("w2", 2.0, 0.0, 5.0, CurrentDirection.FORWARD),
        WindingOperatingPoint("w3", 2.0, 0.0, 5.0, CurrentDirection.FORWARD),
    )


def test_three_identical_windings_give_order_three() -> None:
    plan = propose_symmetry_plan(trio(), operating_trio())
    assert isinstance(plan, SymmetryPlan)
    assert plan.multiplier == 3
    assert plan.sector_deg == 120.0
    cut0, cut1 = plan.cut_angles_deg
    assert cut0 == 350.0  # gap = 20 deg, start_0 = 0 -> cut at -10 -> 350
    assert cut1 == 110.0


def test_single_winding_refused() -> None:
    refusal = propose_symmetry_plan(
        [make_winding(winding_id="w1")], make_operating_point().windings
    )
    assert isinstance(refusal, SymmetryRefusal)
    assert refusal.code == "single-winding"


def test_unequal_turns_refused() -> None:
    w1, w2, w3 = trio()
    w2 = dataclasses.replace(w2, turns=99)  # type: ignore[type-var]
    refusal = propose_symmetry_plan([w1, w2, w3], operating_trio())
    assert isinstance(refusal, SymmetryRefusal)
    assert refusal.code == "unequal-windings"


def test_unequal_spacing_refused() -> None:
    w1, w2, w3 = trio()
    w2 = dataclasses.replace(w2, start_angle_deg=100.0)  # type: ignore[type-var]
    refusal = propose_symmetry_plan([w1, w2, w3], operating_trio())
    assert isinstance(refusal, SymmetryRefusal)
    assert refusal.code == "unequal-spacing"


def test_unequal_excitation_refused() -> None:
    w1, w2, w3 = trio()
    operating_points = list(operating_trio())
    operating_points[1] = dataclasses.replace(operating_points[1], ac_phase_deg=120.0)
    refusal = propose_symmetry_plan([w1, w2, w3], operating_points)
    assert isinstance(refusal, SymmetryRefusal)
    assert refusal.code == "unequal-excitation"


def test_unequal_winding_direction_refused_as_geometry() -> None:
    w1, w2, w3 = trio()
    w2 = dataclasses.replace(w2, winding_direction=WindingDirection.COUNTERCLOCKWISE)
    refusal = propose_symmetry_plan([w1, w2, w3], operating_trio())
    assert isinstance(refusal, SymmetryRefusal)
    assert refusal.code == "unequal-windings"


def test_unequal_current_direction_refused_as_excitation() -> None:
    operating_points = list(operating_trio())
    operating_points[1] = dataclasses.replace(
        operating_points[1], current_direction=CurrentDirection.REVERSE
    )
    refusal = propose_symmetry_plan(trio(), operating_points)
    assert isinstance(refusal, SymmetryRefusal)
    assert refusal.code == "unequal-excitation"
