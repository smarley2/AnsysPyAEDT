"""Per-winding preliminary estimates (specification section 7).

Current density is uniform over the copper area. Skin and proximity
redistribution are excluded.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from inductor_designer.simulation.preliminary_contracts import (
    DiagnosticCode,
    PreliminaryValue,
    unavailable,
)


@dataclass(frozen=True, slots=True)
class CurrentDensities:
    j_ac_rms_a_per_m2: float
    j_ac_peak_a_per_m2: float
    j_dc_a_per_m2: float


def conductor_area_m2(bare_diameter_m: float) -> float:
    if not bare_diameter_m > 0.0:
        raise ValueError("bare conductor diameter must be positive")
    return math.pi * bare_diameter_m**2 / 4.0


def current_densities(
    area_m2: float, ac_rms_current_a: float, dc_current_a: float
) -> CurrentDensities:
    j_ac_rms = ac_rms_current_a / area_m2
    return CurrentDensities(
        j_ac_rms_a_per_m2=j_ac_rms,
        j_ac_peak_a_per_m2=math.sqrt(2.0) * j_ac_rms,
        j_dc_a_per_m2=dc_current_a / area_m2,
    )


# Annealed 100% IACS copper, from the US National Bureau of Standards copper
# measurements: https://nvlpubs.nist.gov/nistpubs/bulletin/07/nbsbulletinv7n1p71_A2b.pdf
# The range is the validated linear range, not a convenience clamp: outside it
# resistance and loss are reported unavailable rather than extrapolated.
COPPER_RHO_20_OHM_M = 1.7241e-8
COPPER_ALPHA_20_PER_C = 0.00393
COPPER_MIN_TEMPERATURE_C = 10.0
COPPER_MAX_TEMPERATURE_C = 100.0

WIRE_LOSS_EXCLUSION_NOTE = (
    "DC-resistance wire-loss estimate; excludes skin effect, proximity effect, "
    "eddy-current loss, terminal loss, connector loss, and temperature rise"
)
LEAD_EXCLUSION_NOTE = (
    "wire length is the modeled closed-loop turn length; connectors, external "
    "leads, and terminals are excluded"
)


@dataclass(frozen=True, slots=True)
class WireLoss:
    resistance_ohm: float
    loss_w: float
    notes: tuple[str, ...]


def wire_resistance_and_loss(
    area_m2: float,
    wire_length_m: float,
    winding_temperature_c: float,
    ac_rms_current_a: float,
    dc_current_a: float,
) -> WireLoss | PreliminaryValue:
    if not wire_length_m > 0.0:
        return unavailable(
            DiagnosticCode.WIRE_LOSS_NO_GEOMETRY,
            "Winding geometry produced no modeled wire length, so resistance "
            "and wire loss cannot be estimated.",
        )
    if not (
        COPPER_MIN_TEMPERATURE_C <= winding_temperature_c <= COPPER_MAX_TEMPERATURE_C
    ):
        return unavailable(
            DiagnosticCode.WIRE_LOSS_TEMPERATURE_OUT_OF_RANGE,
            f"Winding temperature {winding_temperature_c:g} C is outside the "
            f"validated copper range {COPPER_MIN_TEMPERATURE_C:g} C through "
            f"{COPPER_MAX_TEMPERATURE_C:g} C; resistance is not extrapolated.",
        )

    rho = COPPER_RHO_20_OHM_M * (
        1.0 + COPPER_ALPHA_20_PER_C * (winding_temperature_c - 20.0)
    )
    resistance = rho * wire_length_m / area_m2
    return WireLoss(
        resistance_ohm=resistance,
        loss_w=resistance * (ac_rms_current_a**2 + dc_current_a**2),
        notes=(WIRE_LOSS_EXCLUSION_NOTE, LEAD_EXCLUSION_NOTE),
    )
