"""Engineering-unit rows for the Preliminary screen (specification section 4.3).

The estimator reports SI. Every conversion the user sees happens here, once, in
pure functions with no Qt import, so the numbers can be checked against a
datasheet in a plain unit test. QML renders these dicts and computes nothing.
"""

from __future__ import annotations

from dataclasses import dataclass

from inductor_designer.simulation.preliminary import PreliminaryResult
from inductor_designer.simulation.preliminary_contracts import (
    PreliminaryValue,
    ResultState,
)


@dataclass(frozen=True, slots=True)
class DisplayUnit:
    suffix: str
    scale: float
    decimals: int


MILLITESLA = DisplayUnit("mT", 1000.0, 3)
AMPERE_PER_SQUARE_MILLIMETRE = DisplayUnit("A/mm²", 1e-6, 3)
MILLIOHM = DisplayUnit("mΩ", 1000.0, 4)
MILLIMETRE = DisplayUnit("mm", 1000.0, 2)
SQUARE_MILLIMETRE = DisplayUnit("mm²", 1e6, 4)
WATT = DisplayUnit("W", 1.0, 4)

_STATE_TEXT = {
    ResultState.UNAVAILABLE: "Unavailable",
    ResultState.INVALID: "Invalid",
}


def cell(value: PreliminaryValue, unit: DisplayUnit) -> dict[str, object]:
    """One displayed quantity: its state, its text, and why if it has no number."""
    if value.state is ResultState.ESTIMATED and value.value is not None:
        text = f"{value.value * unit.scale:.{unit.decimals}f} {unit.suffix}"
    else:
        text = _STATE_TEXT[value.state]
    return {
        "state": value.state.value,
        "text": text,
        "code": value.code or "",
        "message": value.message or "",
        "notes": list(value.notes),
    }


def _labelled(
    label: str, value: PreliminaryValue, unit: DisplayUnit
) -> dict[str, object]:
    return {"label": label, **cell(value, unit)}


def core_rows(result: PreliminaryResult) -> list[dict[str, object]]:
    core = result.core
    return [
        _labelled("DC flux density", core.b_dc, MILLITESLA),
        _labelled("AC flux-density swing", core.b_ac_peak, MILLITESLA),
        _labelled("Minimum flux density", core.b_min, MILLITESLA),
        _labelled("Maximum flux density", core.b_max, MILLITESLA),
        _labelled("Peak flux-density magnitude", core.b_peak_magnitude, MILLITESLA),
        _labelled("Core loss", core.core_loss, WATT),
    ]


def winding_rows(result: PreliminaryResult) -> list[dict[str, object]]:
    return [
        {
            "windingId": row.winding_id,
            "conductorArea": cell(row.conductor_area, SQUARE_MILLIMETRE),
            "jAcRms": cell(row.j_ac_rms, AMPERE_PER_SQUARE_MILLIMETRE),
            "jAcPeak": cell(row.j_ac_peak, AMPERE_PER_SQUARE_MILLIMETRE),
            "jDc": cell(row.j_dc, AMPERE_PER_SQUARE_MILLIMETRE),
            "wireLength": cell(row.wire_length, MILLIMETRE),
            "resistance": cell(row.resistance, MILLIOHM),
            "wireLoss": cell(row.wire_loss, WATT),
        }
        for row in result.windings
    ]


def total_rows(result: PreliminaryResult) -> list[dict[str, object]]:
    totals = result.totals
    return [
        _labelled("Total wire loss", totals.total_wire_loss, WATT),
        _labelled("Core loss", totals.core_loss, WATT),
        _labelled("Total preliminary loss", totals.total_loss, WATT),
    ]
