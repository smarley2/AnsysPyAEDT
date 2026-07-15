from __future__ import annotations

import dataclasses

from inductor_designer.geometry.symmetry import (
    SymmetryPlan,
    SymmetryRefusal,
    propose_symmetry_plan,
)
from tests.unit.domain.test_project import make_winding


def trio(sector: float = 100.0) -> tuple[object, object, object]:
    return (
        make_winding(winding_id="w1", start_angle_deg=0.0, sector_deg=sector),
        make_winding(winding_id="w2", start_angle_deg=120.0, sector_deg=sector),
        make_winding(winding_id="w3", start_angle_deg=240.0, sector_deg=sector),
    )


def test_three_identical_windings_give_order_three() -> None:
    plan = propose_symmetry_plan(trio())
    assert isinstance(plan, SymmetryPlan)
    assert plan.multiplier == 3
    assert plan.sector_deg == 120.0
    cut0, cut1 = plan.cut_angles_deg
    assert cut0 == 350.0  # gap = 20 deg, start_0 = 0 -> cut at -10 -> 350
    assert cut1 == 110.0


def test_single_winding_refused() -> None:
    refusal = propose_symmetry_plan([make_winding(winding_id="w1")])
    assert isinstance(refusal, SymmetryRefusal)
    assert refusal.code == "single-winding"


def test_unequal_turns_refused() -> None:
    w1, w2, w3 = trio()
    w2 = dataclasses.replace(w2, turns=99)  # type: ignore[type-var]
    refusal = propose_symmetry_plan([w1, w2, w3])
    assert isinstance(refusal, SymmetryRefusal)
    assert refusal.code == "unequal-windings"


def test_unequal_spacing_refused() -> None:
    w1, w2, w3 = trio()
    w2 = dataclasses.replace(w2, start_angle_deg=100.0)  # type: ignore[type-var]
    refusal = propose_symmetry_plan([w1, w2, w3])
    assert isinstance(refusal, SymmetryRefusal)
    assert refusal.code == "unequal-spacing"


def test_unequal_excitation_refused() -> None:
    w1, w2, w3 = trio()
    w2 = dataclasses.replace(w2, ac_phase_deg=120.0)  # type: ignore[type-var]
    refusal = propose_symmetry_plan([w1, w2, w3])
    assert isinstance(refusal, SymmetryRefusal)
    assert refusal.code == "unequal-excitation"
