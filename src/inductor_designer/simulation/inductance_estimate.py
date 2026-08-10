"""Inductance, inductance factor, and stored energy at one operating point.

Every value here is a lumped effective-core estimate derived from the field
strengths and flux densities the magnetic estimate already produced. None of
them is a solver result, and none models fringing, leakage, or winding
capacitance.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from inductor_designer.simulation.magnetic_estimate import (
    MU_0,
    FieldStrengths,
    FluxDensities,
)
from inductor_designer.simulation.preliminary_contracts import (
    CoreMagneticProperties,
    DiagnosticCode,
    PreliminaryValue,
    estimated,
    unavailable,
)

INDUCTANCE_EXCLUSION_NOTE = (
    "incremental-permeability inductance estimate at the DC bias; excludes "
    "air-gap fringing, leakage inductance, and winding self-capacitance"
)
AL_TOLERANCE_NOTE = (
    "the catalog inductance factor is a low-signal value, so the reported "
    "deviation mixes DC-bias roll-off with catalog tolerance and cannot "
    "separate them"
)
ZERO_RIPPLE_NOTE = (
    "zero AC ripple: permeability evaluated as the secant B_dc / H_dc at the "
    "DC bias instead of the incremental slope"
)
STORED_ENERGY_NOTE = (
    "stored energy is the effective-core-volume estimate "
    "0.5 * B_peak * H_peak * V_e; energy stored in the winding window and in "
    "leakage paths is excluded"
)


@dataclass(frozen=True, slots=True)
class AlCheck:
    """The catalog reference and the deviation from it.

    These three travel together because they are either all available or all
    absent: without a manufacturer `A_L` there is no reference, no derived
    initial permeability, and no deviation.
    """

    al_catalog_h: float
    mu_r_initial: float
    al_deviation: float


@dataclass(frozen=True, slots=True)
class CoreInductance:
    mu_r_effective: float
    al_effective_h: float
    catalog: AlCheck | None
    notes: tuple[str, ...]


def _absolute_permeability(
    fields: FieldStrengths, densities: FluxDensities
) -> tuple[float, tuple[str, ...]] | PreliminaryValue:
    """dB/dH over the operating excursion, or the secant when there is no ripple.

    The incremental slope is what a converter sees at the bias point. With no
    AC ripple the excursion collapses to a point and the slope is 0/0, so the
    secant through the bias is used and labelled. With no excitation at all
    there is nothing to differentiate and nothing to draw a secant through.
    """
    span_a_per_m = fields.h_max_a_per_m - fields.h_min_a_per_m
    if span_a_per_m > 0.0:
        permeability = (densities.b_max_t - densities.b_min_t) / span_a_per_m
        notes: tuple[str, ...] = ()
    elif fields.h_dc_a_per_m != 0.0:
        permeability = densities.b_dc_t / fields.h_dc_a_per_m
        notes = (ZERO_RIPPLE_NOTE,)
    else:
        return unavailable(
            DiagnosticCode.INDUCTANCE_NO_EXCITATION,
            "The operating point carries neither AC nor DC ampere-turns, so "
            "permeability is undefined and inductance cannot be estimated. "
            "The material's initial permeability is not substituted.",
        )
    if not math.isfinite(permeability):
        return unavailable(
            DiagnosticCode.INDUCTANCE_NOT_FINITE,
            "The field excursion is too small for the flux swing, so the "
            "permeability slope overflows; inductance is not reported.",
        )
    return permeability, notes


def core_inductance(
    fields: FieldStrengths,
    densities: FluxDensities,
    core: CoreMagneticProperties,
) -> CoreInductance | PreliminaryValue:
    """The core-level inductance factor, or the diagnostic explaining its absence.

    `A_L` is a core property: every winding's inductance is `turns**2 * A_L`,
    which the caller applies. The path length needs no guard here -- flux
    densities exist only after `field_strengths` has already refused a
    non-positive or non-finite path length.
    """
    if not (core.effective_area_m2 > 0.0 and math.isfinite(core.effective_area_m2)):
        return unavailable(
            DiagnosticCode.INDUCTANCE_NON_POSITIVE_AREA,
            "Core effective area must be a positive finite number; "
            f"got {core.effective_area_m2:g} m^2. The core dimensions are out "
            "of range, so the inductance factor cannot be estimated.",
        )
    permeability = _absolute_permeability(fields, densities)
    if isinstance(permeability, PreliminaryValue):
        return permeability
    mu_abs, notes = permeability

    geometry_factor = core.effective_area_m2 / core.path_length_m
    al_effective_h = mu_abs * geometry_factor
    notes = (INDUCTANCE_EXCLUSION_NOTE, *notes)

    if core.al_value_nh is None:
        return CoreInductance(
            mu_r_effective=mu_abs / MU_0,
            al_effective_h=al_effective_h,
            catalog=None,
            notes=notes,
        )

    # `CoreRecord` validates `al_value_nh > 0`, and a Manual core reports None
    # above, so no reachable path divides by zero here.
    al_catalog_h = core.al_value_nh * 1e-9
    return CoreInductance(
        mu_r_effective=mu_abs / MU_0,
        al_effective_h=al_effective_h,
        catalog=AlCheck(
            al_catalog_h=al_catalog_h,
            mu_r_initial=al_catalog_h / (MU_0 * geometry_factor),
            al_deviation=al_effective_h / al_catalog_h - 1.0,
        ),
        notes=(*notes, AL_TOLERANCE_NOTE),
    )


def stored_energy_j(
    fields: FieldStrengths,
    densities: FluxDensities,
    core: CoreMagneticProperties,
) -> PreliminaryValue:
    """Peak energy stored in the effective core volume.

    Needs no permeability, so it stays available where inductance is refused
    for want of excitation: at zero excitation the stored energy really is
    zero. `B` and `H` are both taken at their peak magnitude so the two factors
    describe the same instant of the cycle.
    """
    if not (core.volume_m3 > 0.0 and math.isfinite(core.volume_m3)):
        return unavailable(
            DiagnosticCode.STORED_ENERGY_NON_POSITIVE_VOLUME,
            "Core effective volume must be a positive finite number; "
            f"got {core.volume_m3:g} m^3. Stored energy is not reported.",
        )
    h_peak_a_per_m = max(abs(fields.h_min_a_per_m), abs(fields.h_max_a_per_m))
    return estimated(
        0.5 * densities.b_peak_magnitude_t * h_peak_a_per_m * core.volume_m3,
        (STORED_ENERGY_NOTE,),
    )
