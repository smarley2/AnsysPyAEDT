from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from inductor_designer.geometry.core_solid import FinishedCore
from inductor_designer.geometry.packing import PackedWinding


@dataclass(frozen=True, slots=True)
class CollisionIssue:
    kind: str
    first_winding: str
    second_winding: str
    required_m: float
    actual_m: float
    message: str


def _worst_radius(core: FinishedCore, packing: PackedWinding) -> float:
    deepest = max(layer.radial_build_m for layer in packing.layers)
    return core.r_inner_m - deepest - packing.insulated_diameter_m / 2.0


def check_clearances(
    core: FinishedCore,
    packings: Sequence[PackedWinding],
    clearances: Mapping[str, float],
) -> tuple[CollisionIssue, ...]:
    windings = sorted(packings, key=lambda p: p.start_deg)
    if len(windings) < 2:
        return ()
    issues: list[CollisionIssue] = []
    for i, first in enumerate(windings):
        second = windings[(i + 1) % len(windings)]
        gap_deg = (second.start_deg - (first.start_deg + first.sector_deg)) % 360.0
        r_ref = min(_worst_radius(core, first), _worst_radius(core, second))
        actual = math.radians(gap_deg) * r_ref
        required = (
            max(clearances[first.winding_id], clearances[second.winding_id])
            + first.insulated_diameter_m / 2.0
            + second.insulated_diameter_m / 2.0
        )
        if actual < required:
            issues.append(
                CollisionIssue(
                    kind="clearance",
                    first_winding=first.winding_id,
                    second_winding=second.winding_id,
                    required_m=round(required, 9),
                    actual_m=round(actual, 9),
                    message=(
                        f"Windings {first.winding_id!r} and {second.winding_id!r} are "
                        f"{actual * 1000:.3f} mm apart at the bore; "
                        f"{required * 1000:.3f} mm required"
                    ),
                )
            )
    return tuple(issues)


def occupancy_summary(packings: Sequence[PackedWinding]) -> dict[str, float]:
    return {p.winding_id: round(p.sector_deg / 360.0, 9) for p in packings}
