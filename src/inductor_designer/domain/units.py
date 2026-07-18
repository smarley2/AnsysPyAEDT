from __future__ import annotations

import math

_CONVERSIONS: dict[str, float] = {
    # length -> meters
    "m": 1.0,
    "mm": 1e-3,
    "cm": 1e-2,
    "um": 1e-6,
    # current -> amperes
    "A": 1.0,
    "mA": 1e-3,
    # frequency -> hertz
    "Hz": 1.0,
    "kHz": 1e3,
    "MHz": 1e6,
    # angle -> degrees (canonical angle unit is the degree)
    "deg": 1.0,
    # flux density -> tesla
    "T": 1.0,
    "mT": 1e-3,
    "G": 1e-4,
    "kG": 0.1,
    # magnetic field strength -> amperes per meter
    "A/m": 1.0,
    "kA/m": 1e3,
    "Oe": 79.57747154594767,
    # loss density -> watts per cubic meter
    "W/m3": 1.0,
    "kW/m3": 1e3,
    "mW/cm3": 1e3,
}


def to_canonical(value: float, unit: str) -> float:
    """Convert a value to the canonical unit of its dimension."""
    factor = _CONVERSIONS.get(unit)
    if factor is None:
        raise ValueError(f"Unknown unit: {unit!r}")
    if not math.isfinite(value):
        raise ValueError(f"Value must be finite, got {value!r}")
    return value * factor


def from_canonical(value: float, unit: str) -> float:
    """Convert a canonical value to a supported unit of its dimension."""
    factor = _CONVERSIONS.get(unit)
    if factor is None:
        raise ValueError(f"Unknown unit: {unit!r}")
    if not math.isfinite(value):
        raise ValueError(f"Value must be finite, got {value!r}")
    return value / factor


def awg_bare_diameter_m(gauge: int) -> float:
    """Bare copper diameter for an AWG gauge: d = 0.127 mm * 92**((36 - n) / 39)."""
    if type(gauge) is not int or not 1 <= gauge <= 40:
        raise ValueError(f"AWG gauge must be an integer in [1, 40], got {gauge!r}")
    return float(0.000127 * 92.0 ** ((36 - gauge) / 39))
