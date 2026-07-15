from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from inductor_designer.domain.winding import WindingDefinition

_ANGLE_TOL_DEG = 1e-6


@dataclass(frozen=True, slots=True)
class SymmetryPlan:
    multiplier: int
    sector_deg: float
    cut_angles_deg: tuple[float, float]


@dataclass(frozen=True, slots=True)
class SymmetryRefusal:
    code: str
    message: str


def _geometry_key(w: WindingDefinition) -> tuple[object, ...]:
    return (
        w.turns,
        w.conductor_name,
        w.mode,
        w.sector_deg,
        w.min_spacing_m,
        w.min_clearance_m,
        w.winding_direction,
        w.current_direction,
    )


def _excitation_key(w: WindingDefinition) -> tuple[float, float, float, float]:
    return (w.ac_magnitude_a, w.ac_phase_deg, w.frequency_hz, w.dc_current_a)


def propose_symmetry_plan(
    windings: Sequence[WindingDefinition],
) -> SymmetryPlan | SymmetryRefusal:
    m = len(windings)
    if m < 2:
        return SymmetryRefusal(
            "single-winding", "Rotational symmetry needs at least two identical windings."
        )
    first = windings[0]
    if any(_geometry_key(w) != _geometry_key(first) for w in windings[1:]):
        return SymmetryRefusal(
            "unequal-windings",
            "Windings differ in turns, conductor, mode, sector, spacing, or direction.",
        )
    if any(_excitation_key(w) != _excitation_key(first) for w in windings[1:]):
        return SymmetryRefusal(
            "unequal-excitation", "Windings differ in AC/DC excitation values."
        )
    starts = sorted(w.start_angle_deg for w in windings)
    pitch = 360.0 / m
    if any(
        abs((starts[i] - starts[0]) - i * pitch) > _ANGLE_TOL_DEG for i in range(m)
    ):
        return SymmetryRefusal(
            "unequal-spacing", f"Winding start angles are not spaced by {pitch} degrees."
        )
    gap = pitch - first.sector_deg
    cut0 = (starts[0] - gap / 2.0) % 360.0
    cut1 = (cut0 + pitch) % 360.0
    return SymmetryPlan(
        multiplier=m,
        sector_deg=round(pitch, 9),
        cut_angles_deg=(round(cut0, 9), round(cut1, 9)),
    )
