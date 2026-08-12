from __future__ import annotations

import pytest

from inductor_designer.domain.winding import (
    CurrentDirection,
    WindingDirection,
)
from inductor_designer.simulation.maxwell_plan import (
    Polarity,
    invert_polarity,
    winding_polarity,
)
from tests.unit.domain.test_project import make_winding


@pytest.mark.parametrize(
    ("winding_direction", "current_direction", "expected"),
    [
        (WindingDirection.COUNTERCLOCKWISE, CurrentDirection.FORWARD, Polarity.POSITIVE),
        (WindingDirection.COUNTERCLOCKWISE, CurrentDirection.REVERSE, Polarity.NEGATIVE),
        (WindingDirection.CLOCKWISE, CurrentDirection.FORWARD, Polarity.NEGATIVE),
        (WindingDirection.CLOCKWISE, CurrentDirection.REVERSE, Polarity.POSITIVE),
    ],
)
def test_winding_polarity_covers_every_direction_pair(
    winding_direction: WindingDirection,
    current_direction: CurrentDirection,
    expected: Polarity,
) -> None:
    from dataclasses import replace

    definition = replace(make_winding(), winding_direction=winding_direction)

    assert winding_polarity(definition, current_direction) is expected


def test_invert_polarity_swaps_both_values() -> None:
    assert invert_polarity(Polarity.POSITIVE) is Polarity.NEGATIVE
    assert invert_polarity(Polarity.NEGATIVE) is Polarity.POSITIVE
