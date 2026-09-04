"""The E-core reluctance network, reduced to two lengths.

Design: ``docs/superpowers/specs/2026-09-04-m11a-gapped-e-core-design.md``.

An E core's sections have genuinely different cross-sections -- centre leg,
two yokes, two outer legs in parallel -- so collapsing them into a single
``l_e / A_e`` would bury that in one number nobody could check. The network
is summed section by section here instead.

It then separates **exactly** into two lengths, both referred to the
centre-leg area: every iron term carries ``1/mu_r`` and no gap term does, and
the parallel outer branch is a linear factor of one half, so

    R_total = iron_m/(mu_r*mu_0*A_c) + gap_m/(mu_0*A_c)

with no approximation. That is why the preliminary estimate needs one extra
term rather than a second magnetic model: ``gap_m`` is zero for every core
that has no gap, which is every core the application handled before M11a.

Fringing is deliberately not modelled. See the spec, and the note the
estimate already carries: ignoring it understates reluctance and therefore
overstates inductance, by more as the gap grows.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from inductor_designer.geometry.ecore.body import FinishedECore


@dataclass(frozen=True, slots=True)
class ReferredLengths:
    """The network, as the two lengths and the area they are referred to.

    ``iron_m`` and ``gap_m`` are both referred to ``effective_area_m2``, so
    they are directly comparable: a 1 mm gap in the centre leg contributes
    exactly 1 mm of ``gap_m``, while the same gap in the two parallel outer
    legs contributes half its length scaled by the area ratio.
    """

    iron_m: float
    gap_m: float
    effective_area_m2: float
    iron_volume_m3: float


def referred_lengths(core: FinishedECore) -> ReferredLengths:
    """Sum the network for one E+E pair."""
    area = core.centre_leg_area_m2
    yoke_area = core.yoke_area_m2
    outer_area = core.outer_leg_area_m2

    gap_total = core.total_gap_m
    outer_gap_total = gap_total if core.outer_legs_gapped else 0.0
    centre_iron = core.centre_leg_length_m - gap_total
    outer_iron = core.centre_leg_length_m - outer_gap_total

    # Series along the loop: centre leg, both yokes, then the outer legs --
    # two of them in parallel, hence the halved term.
    iron_m = area * (
        centre_iron / area
        + 2.0 * core.yoke_run_m / yoke_area
        + outer_iron / (2.0 * outer_area)
    )
    gap_m = area * (gap_total / area + outer_gap_total / (2.0 * outer_area))

    iron_volume_m3 = (
        area * centre_iron
        + 2.0 * (core.overall_width_m * core.yoke_thickness_m * core.depth_m)
        + 2.0 * (outer_area * outer_iron)
    )
    return ReferredLengths(
        iron_m=iron_m,
        gap_m=gap_m,
        effective_area_m2=area,
        iron_volume_m3=iron_volume_m3,
    )
