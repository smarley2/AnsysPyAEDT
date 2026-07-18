from __future__ import annotations

import math


def canonical_float(value: float) -> float:
    """Round valid material data while leaving invalid values for boundary validation."""
    return round(value, 9) if math.isfinite(value) else value
