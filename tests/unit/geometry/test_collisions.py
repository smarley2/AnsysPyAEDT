from __future__ import annotations

from inductor_designer.geometry.collisions import check_clearances, occupancy_summary
from inductor_designer.geometry.core_solid import FinishedCore
from inductor_designer.geometry.packing import WindingSpec, pack_winding

CORE = FinishedCore(r_inner_m=0.00973, r_outer_m=0.01683, half_height_m=0.005715,
                    corner_radius_m=0.0)
D = 0.001118


def packed(winding_id: str, start: float, sector: float, turns: int = 8) -> object:
    return pack_winding(
        CORE,
        WindingSpec(winding_id, turns, D, start, sector, 0.0001, 0.001),
    )


def test_well_separated_windings_have_no_issues() -> None:
    packings = [packed("w1", 0.0, 150.0), packed("w2", 180.0, 150.0)]
    issues = check_clearances(CORE, packings, {"w1": 0.001, "w2": 0.001})
    assert issues == ()


def test_tight_gap_reports_clearance_violation() -> None:
    packings = [packed("w1", 0.0, 179.0), packed("w2", 180.0, 179.0)]
    issues = check_clearances(CORE, packings, {"w1": 0.004, "w2": 0.004})
    assert len(issues) == 2  # both gaps (179->180 and 359->360) violate
    issue = issues[0]
    assert issue.kind == "clearance"
    assert issue.actual_m < issue.required_m


def test_single_winding_no_issues() -> None:
    assert check_clearances(CORE, [packed("w1", 0.0, 300.0)], {"w1": 0.001}) == ()


def test_occupancy() -> None:
    packings = [packed("w1", 0.0, 90.0), packed("w2", 180.0, 45.0)]
    summary = occupancy_summary(packings)
    assert summary == {"w1": 0.25, "w2": 0.125}
