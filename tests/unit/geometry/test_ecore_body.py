"""The gapped E+E core body.

Design: `docs/superpowers/specs/2026-09-04-m11a-gapped-e-core-design.md`.

Six independent dimensions, and the two derived ones are never entered twice
-- the same rule the toroid's four dimensions follow, for the same reason: a
core whose overall width disagrees with its legs is a core nobody can build.
"""

from __future__ import annotations

import pytest

from inductor_designer.geometry.ecore.body import FinishedECore
from inductor_designer.geometry.toroid.core_solid import CoreGeometryError

# A plausible ferrite E core pair, in metres: E55/28/21-ish proportions.
_DIMENSIONS = {
    "centre_leg_width_m": 0.0170,
    "depth_m": 0.0210,
    "window_width_m": 0.0092,
    "window_height_m": 0.0187,
    "outer_leg_width_m": 0.0085,
    "yoke_thickness_m": 0.0093,
}


def _core(**overrides: object) -> FinishedECore:
    values: dict[str, object] = dict(_DIMENSIONS)
    values.update(overrides)
    return FinishedECore(**values)  # type: ignore[arg-type]


def test_the_derived_dimensions_follow_from_the_six_independent_ones() -> None:
    core = _core()
    # A = F + 2E + 2G
    assert core.overall_width_m == pytest.approx(0.0170 + 2 * 0.0092 + 2 * 0.0085)
    # B = 2(D + H)
    assert core.overall_height_m == pytest.approx(2 * (0.0187 + 0.0093))
    # The centre leg spans both halves' windows.
    assert core.centre_leg_length_m == pytest.approx(2 * 0.0187)


def test_a_pair_with_no_gaps_is_legal() -> None:
    """An ungapped E+E pair is a real build -- a transformer core, or an
    inductor whose gap has not been chosen yet."""
    core = _core()
    assert core.gaps == ()
    assert core.gap_spacings_m == ()
    assert core.total_gap_m == 0.0
    assert core.outer_legs_gapped is False


def test_the_gap_stack_is_kept_in_the_order_it_was_given() -> None:
    """Distributed gaps are not interchangeable with one gap of the same total
    once fringing is modelled, so the individual lengths are kept rather than
    summed away at construction."""
    core = _core(gaps=(0.0005, 0.0005, 0.0005), gap_spacings_m=(0.004, 0.004))
    assert core.gaps == (0.0005, 0.0005, 0.0005)
    assert core.total_gap_m == pytest.approx(0.0015)


@pytest.mark.parametrize("field", sorted(_DIMENSIONS))
@pytest.mark.parametrize("bad", [0.0, -0.001, float("nan"), float("inf")])
def test_a_dimension_that_is_not_a_positive_number_is_refused(
    field: str, bad: float
) -> None:
    with pytest.raises(CoreGeometryError, match=field):
        _core(**{field: bad})


@pytest.mark.parametrize("bad", [-0.001, float("nan"), float("inf")])
def test_a_gap_that_is_not_a_finite_positive_length_is_refused(bad: float) -> None:
    with pytest.raises(CoreGeometryError, match="gap"):
        _core(gaps=(bad,))


def test_a_gap_stack_longer_than_the_centre_leg_is_refused() -> None:
    """Grinding away more than the leg is not a gap, it is two separate
    cores. The refusal names the total so the user can see by how much."""
    # Two 20 mm gaps and the 1 mm segment between them, in a 37.4 mm leg.
    with pytest.raises(CoreGeometryError, match="0.0410"):
        _core(gaps=(0.02, 0.02), gap_spacings_m=(0.001,))


def test_the_segments_between_gaps_count_against_the_leg_too() -> None:
    """Spacings are core, so gaps plus spacings must still fit."""
    with pytest.raises(CoreGeometryError, match="centre leg"):
        _core(gaps=(0.001, 0.001), gap_spacings_m=(0.040,))


def test_the_spacings_must_separate_the_gaps_they_are_given_for() -> None:
    """N gaps have N-1 segments between them; any other count is a
    description of nothing."""
    with pytest.raises(CoreGeometryError, match="spacing"):
        _core(gaps=(0.001, 0.001, 0.001), gap_spacings_m=(0.004,))


def test_a_single_gap_needs_no_spacing() -> None:
    core = _core(gaps=(0.001,))
    assert core.gap_spacings_m == ()
    assert core.total_gap_m == pytest.approx(0.001)
