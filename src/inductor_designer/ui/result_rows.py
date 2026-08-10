"""Engineering-unit rows for the Review results section.

The result set stores SI. Every conversion the user sees happens here, once,
in pure functions with no Qt import - the same rule `preliminary_rows.py`
follows, and it reuses that module's display units so the two sections read
alike. An unavailable quantity renders its reason, never a blank.
"""

from __future__ import annotations

from inductor_designer.domain.project import RequestedOutput
from inductor_designer.simulation.run_contracts import (
    ComplexValue,
    MatrixValue,
    NormalizedQuantity,
    NormalizedResultSet,
    ResultAvailability,
)
from inductor_designer.ui.preliminary_rows import (
    MICROHENRY,
    MILLIJOULE,
    MILLIOHM,
    WATT,
    DisplayUnit,
)

PERCENT_POINTS = DisplayUnit("%", 1.0, 3)

_UNITS: dict[RequestedOutput, DisplayUnit] = {
    RequestedOutput.RESISTANCE: MILLIOHM,
    RequestedOutput.INDUCTANCE: MICROHENRY,
    RequestedOutput.IMPEDANCE: MILLIOHM,
    RequestedOutput.COPPER_LOSS: WATT,
    RequestedOutput.CORE_LOSS: WATT,
    RequestedOutput.TOTAL_LOSS: WATT,
    RequestedOutput.MAGNETIC_ENERGY: MILLIJOULE,
    RequestedOutput.CONVERGENCE: PERCENT_POINTS,
}

_LABELS: dict[RequestedOutput, str] = {
    RequestedOutput.RESISTANCE: "Resistance",
    RequestedOutput.INDUCTANCE: "Inductance",
    RequestedOutput.IMPEDANCE: "Impedance",
    RequestedOutput.MATRICES: "Matrix",
    RequestedOutput.COPPER_LOSS: "Copper loss",
    RequestedOutput.CORE_LOSS: "Core loss",
    RequestedOutput.TOTAL_LOSS: "Total loss",
    RequestedOutput.MAGNETIC_ENERGY: "Magnetic energy",
    RequestedOutput.CONVERGENCE: "Convergence",
}


def _scope_suffix(scope: str) -> str:
    if scope.startswith("winding."):
        return f" ({scope.removeprefix('winding.')})"
    if scope.startswith("device."):
        return f" ({scope.removeprefix('device.')})"
    return ""


def label_for(quantity: NormalizedQuantity) -> str:
    return f"{_LABELS[quantity.quantity]}{_scope_suffix(quantity.scope)}"


def _number(value: float, unit: DisplayUnit) -> str:
    return f"{value * unit.scale:.{unit.decimals}f} {unit.suffix}".rstrip()


def text_for(quantity: NormalizedQuantity) -> str:
    """The displayed value, or the reason the backend could not report one."""
    if quantity.availability is ResultAvailability.UNAVAILABLE:
        return quantity.reason or "Unavailable"
    value = quantity.value
    unit = _UNITS.get(quantity.quantity)
    if isinstance(value, MatrixValue):
        return f"{len(value.row_labels)}x{len(value.column_labels)}, see results.json"
    if unit is None or value is None:
        return "Unavailable"
    if isinstance(value, ComplexValue):
        return f"{_number(value.real, unit)} + j{_number(value.imaginary, unit)}"
    text = _number(value, unit)
    if quantity.approximation:
        return f"{text} — {quantity.approximation}"
    return text


def result_rows(results: NormalizedResultSet) -> list[dict[str, str]]:
    return [
        {"label": label_for(quantity), "text": text_for(quantity)}
        for quantity in results.quantities
    ]
