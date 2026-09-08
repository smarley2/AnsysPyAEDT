"""The E-core reluctance network, reduced to two referred lengths.

Design: `docs/superpowers/specs/2026-09-04-m11a-gapped-e-core-design.md`.

An E core's sections have genuinely different areas, so one `l_e / A_e` would
bury that. The network separates exactly into an iron length and a gap length
referred to the centre-leg area, because every iron term carries `1/mu_r` and
no gap term does -- and the arithmetic is pinned here to numbers computed by
hand, so the implementation cannot quietly become its own reference.
"""

from __future__ import annotations

import pytest

from inductor_designer.geometry.ecore.body import FinishedECore
from inductor_designer.geometry.ecore.reluctance import referred_lengths
from inductor_designer.simulation.magnetic_estimate import MU_0

_DIMENSIONS = {
    "centre_leg_width_m": 0.0170,
    "depth_m": 0.0210,
    "window_width_m": 0.0092,
    "window_height_m": 0.0187,
    "outer_leg_width_m": 0.0085,
    "yoke_thickness_m": 0.0093,
}

# Hand-computed for the dimensions above:
#   A_c = 0.0170*0.0210 = 3.5700e-4   A_y = 0.0093*0.0210 = 1.9530e-4
#   A_o = 0.0085*0.0210 = 1.7850e-4   yoke_run = 0.0092 + 0.0085 + 0.00425
#                                              = 0.02195
#   centre iron = outer iron = 2*0.0187 = 0.0374
#
# ONE yoke run, not two: the flux splits at the yoke, so each yoke is two runs
# in parallel and two yokes in series contribute 2*(run/2) = one run. The first
# version of this file counted two and pinned 0.15504731182795703, which was
# 1.349x the true reluctance -- see `test_the_network_matches_a_brute_force_
# node_analysis`, which is the check that would have caught it.
#
#   iron_m = A_c*(0.0374/A_c + 0.02195/A_y + 0.0374/(2*A_o))
#          = 0.1149236559139785
_UNGAPPED_IRON_M = 0.1149236559139785
_AREA_M2 = 0.000357


def _core(**overrides: object) -> FinishedECore:
    values: dict[str, object] = dict(_DIMENSIONS)
    values.update(overrides)
    return FinishedECore(**values)  # type: ignore[arg-type]


def test_an_ungapped_pair_matches_the_hand_computed_iron_path() -> None:
    lengths = referred_lengths(_core())
    assert lengths.iron_m == pytest.approx(_UNGAPPED_IRON_M, rel=1e-12)
    assert lengths.gap_m == 0.0
    assert lengths.effective_area_m2 == pytest.approx(_AREA_M2, rel=1e-12)


def test_one_gap_moves_its_length_from_iron_to_gap() -> None:
    """The centre leg loses exactly the ground-away millimetre, and the gap
    term gains it -- referred to the same area, so the two are comparable."""
    lengths = referred_lengths(_core(gaps=(0.001,)))
    assert lengths.iron_m == pytest.approx(_UNGAPPED_IRON_M - 0.001, rel=1e-12)
    assert lengths.gap_m == pytest.approx(0.001, rel=1e-12)


def test_the_gap_term_rises_with_total_gap() -> None:
    gaps = [(), (0.0005,), (0.001,), (0.002,)]
    values = [referred_lengths(_core(gaps=g)).gap_m for g in gaps]
    assert values == sorted(values)
    assert values[0] == 0.0


def test_distributed_gaps_equal_one_gap_of_the_same_total() -> None:
    """This pins the fringing assumption rather than describing it. With
    fringing ignored, three 0.5 mm gaps and one 1.5 mm gap are the same
    reluctance -- so if anyone adds a fringing correction later, this test
    fails loudly instead of the published numbers changing quietly.

    Distributed gaps exist precisely because that equality is false in
    reality; M11b's solve is what shows the difference.
    """
    single = referred_lengths(_core(gaps=(0.0015,)))
    spread = referred_lengths(
        _core(gaps=(0.0005, 0.0005, 0.0005), gap_spacings_m=(0.004, 0.004))
    )
    assert spread.gap_m == pytest.approx(single.gap_m, rel=1e-12)
    assert spread.iron_m == pytest.approx(single.iron_m, rel=1e-12)


def test_gapping_the_outer_legs_adds_the_stack_referred_through_two_legs() -> None:
    """The shim build gaps all three legs. The two outer legs are in
    parallel, so their gap contributes half its referred length -- and the
    same iron leaves the outer branch.
    """
    centre_only = referred_lengths(_core(gaps=(0.001,)))
    all_legs = referred_lengths(_core(gaps=(0.001,), outer_legs_gapped=True))

    added = _AREA_M2 * (0.001 / (0.0085 * 0.0210)) / 2.0
    assert all_legs.gap_m == pytest.approx(centre_only.gap_m + added, rel=1e-12)
    # Hand-computed: iron_m falls by the same referred amount.
    assert all_legs.iron_m == pytest.approx(centre_only.iron_m - added, rel=1e-12)


def test_the_iron_volume_counts_every_section_once() -> None:
    """Core loss is per unit volume, so this is the number that scales it."""
    lengths = referred_lengths(_core(gaps=(0.001,)))
    # A_c*(2D - g) + 2*(A*H*C) + 2*(G*C*2D), hand-computed:
    assert lengths.iron_volume_m3 == pytest.approx(4.6814040000000006e-05, rel=1e-12)


def test_the_referred_form_reproduces_a_plain_reluctance_for_a_uniform_core() -> None:
    """A sanity check on the referral itself: make every section the same
    area, and the iron length must collapse to the plain centreline loop --
    centre leg, two yoke runs, one outer leg -- with no area weighting left.
    """
    uniform = FinishedECore(
        centre_leg_width_m=0.0100,
        depth_m=0.0100,
        # A_y = H*C and A_o = G*C both equal A_c = F*C when H = G = F.
        window_width_m=0.0050,
        window_height_m=0.0200,
        outer_leg_width_m=0.0100,
        yoke_thickness_m=0.0100,
    )
    lengths = referred_lengths(uniform)
    yoke_run = 0.0050 + 0.0100 / 2.0 + 0.0100 / 2.0
    # One yoke run (two runs per yoke in parallel, two yokes in series), and
    # the outer branch is two legs in parallel, so it contributes half.
    expected = 2 * 0.0200 + yoke_run + (2 * 0.0200) / 2.0
    assert lengths.iron_m == pytest.approx(expected, rel=1e-12)


def test_the_network_matches_a_brute_force_node_analysis() -> None:
    """The referred form against the network written out branch by branch.

    This is the test the first version of this file did not have, and its
    absence is why a doubled yoke term shipped: every other test here compares
    the implementation against the same expression evaluated by hand, so an
    error in the expression itself was invisible. This one builds the network
    independently -- centre-leg branch in series with two side branches in
    parallel, each side branch being top yoke run, outer leg, bottom yoke run
    -- and compares reluctances.
    """
    mu_r = 2000.0
    core = _core()
    area_c = 0.0170 * 0.0210
    area_y = 0.0093 * 0.0210
    area_o = 0.0085 * 0.0210
    yoke_run = 0.0092 + 0.0170 / 2.0 + 0.0085 / 2.0
    leg = 2 * 0.0187

    def reluctance(length: float, area: float) -> float:
        return length / (mu_r * MU_0 * area)

    side = reluctance(yoke_run, area_y) * 2.0 + reluctance(leg, area_o)
    brute = reluctance(leg, area_c) + side / 2.0

    lengths = referred_lengths(core)
    referred = lengths.iron_m / (mu_r * MU_0 * lengths.effective_area_m2)
    assert referred == pytest.approx(brute, rel=1e-12)


def test_the_referred_length_is_shorter_than_the_all_series_sum() -> None:
    """A guard against the specific error this file shipped once.

    Counting the yoke twice -- treating each yoke as one series run rather
    than two parallel ones -- inflates the referred length. So does dropping
    the outer branch's halving. Both make the result approach the naive "every
    section in series at its own area" sum, which is a strict upper bound on
    any network with a parallel branch in it. The bound is crude, and it is
    exactly the class of mistake that got here.

    No datasheet numbers: a manufacturer's measured `l_e` includes corner
    effects this centreline model has no term for, and encoding dimensions
    from a datasheet nobody in this repository has read would be the invented
    physical assumption `AGENTS.md` forbids. The brute-force node analysis
    above is the rigorous check; during review a real E42/21/15 was compared
    by hand and the corrected model landed within 1 mm of its published 97 mm.
    """
    core = _core()
    area_c = core.centre_leg_area_m2
    all_series = area_c * (
        core.centre_leg_length_m / area_c
        + 2.0 * core.yoke_run_m / core.yoke_area_m2
        + core.centre_leg_length_m / core.outer_leg_area_m2
    )
    assert referred_lengths(core).iron_m < all_series
    # And by a wide margin, not a rounding: the parallel branches halve two of
    # the three terms.
    assert referred_lengths(core).iron_m < 0.75 * all_series
