from __future__ import annotations

import math

import pytest

from inductor_designer.domain.units import awg_bare_diameter_m, to_canonical


@pytest.mark.parametrize(
    ("value", "unit", "expected"),
    [
        (1.0, "m", 1.0),
        (25.4, "mm", 0.0254),
        (2.0, "cm", 0.02),
        (500.0, "um", 0.0005),
        (1.5, "A", 1.5),
        (250.0, "mA", 0.25),
        (100.0, "kHz", 100_000.0),
        (1.0, "MHz", 1_000_000.0),
        (90.0, "deg", 90.0),
    ],
)
def test_to_canonical(value: float, unit: str, expected: float) -> None:
    assert to_canonical(value, unit) == pytest.approx(expected)


def test_to_canonical_rejects_unknown_unit() -> None:
    with pytest.raises(ValueError, match="Unknown unit"):
        to_canonical(1.0, "furlong")


def test_to_canonical_rejects_non_finite() -> None:
    with pytest.raises(ValueError, match="finite"):
        to_canonical(math.nan, "mm")


def test_awg_formula() -> None:
    assert awg_bare_diameter_m(36) == pytest.approx(0.000127, rel=1e-6)
    assert awg_bare_diameter_m(18) == pytest.approx(0.00102362, rel=1e-3)


def test_awg_rejects_out_of_range() -> None:
    with pytest.raises(ValueError, match="AWG gauge"):
        awg_bare_diameter_m(0)
    with pytest.raises(ValueError, match="AWG gauge"):
        awg_bare_diameter_m(41)
