"""Where a winding sits, per core family.

Design: `docs/superpowers/specs/2026-09-04-m11a-gapped-e-core-design.md`.

A toroid places turns by angle about its axis; an E core places them along a
leg inside a window. Neither set of numbers means anything in the other
geometry, so placement is a union rather than a shared pair of fields with a
family-dependent meaning -- an angle reinterpreted as a fraction of a window
is the kind of overloaded number that makes a design impossible to audit.
"""

from __future__ import annotations

import pytest

from inductor_designer.domain.winding import (
    LegPlacement,
    ToroidPlacement,
    WindingLeg,
    require_toroid_placement,
)
from tests.unit.domain.test_project import make_winding


def test_a_toroid_placement_keeps_the_two_angles_it_always_had() -> None:
    placement = ToroidPlacement(start_angle_deg=30.0, sector_deg=150.0)
    assert placement.start_angle_deg == 30.0
    assert placement.sector_deg == 150.0


@pytest.mark.parametrize("bad", [float("nan"), float("inf")])
def test_a_toroid_placement_refuses_a_non_finite_angle(bad: float) -> None:
    with pytest.raises(ValueError, match="finite"):
        ToroidPlacement(start_angle_deg=bad, sector_deg=90.0)


def test_a_leg_placement_carries_the_window_span_it_occupies() -> None:
    placement = LegPlacement(
        leg=WindingLeg.CENTRE, window_start_m=0.002, window_span_m=0.014
    )
    assert placement.leg is WindingLeg.CENTRE
    assert placement.window_span_m == 0.014


@pytest.mark.parametrize("span", [0.0, -0.001, float("nan")])
def test_a_leg_placement_refuses_a_span_that_is_not_a_positive_length(
    span: float,
) -> None:
    with pytest.raises(ValueError, match="window_span_m"):
        LegPlacement(leg=WindingLeg.CENTRE, window_start_m=0.0, window_span_m=span)


def test_a_leg_placement_refuses_a_negative_start() -> None:
    with pytest.raises(ValueError, match="window_start_m"):
        LegPlacement(leg=WindingLeg.CENTRE, window_start_m=-0.001, window_span_m=0.01)


def test_toroid_code_asks_for_a_toroid_placement_and_says_so_when_refused() -> None:
    """Every toroid geometry function states this assumption once, at its
    entry, rather than reaching through `.placement` and failing later with an
    attribute error nobody can read."""
    toroid = make_winding()
    assert toroid.placement.sector_deg == toroid.placement.sector_deg

    leg_wound = make_winding(
        placement=LegPlacement(
            leg=WindingLeg.CENTRE, window_start_m=0.0, window_span_m=0.01
        )
    )
    with pytest.raises(ValueError, match=leg_wound.winding_id):
        require_toroid_placement(leg_wound)
