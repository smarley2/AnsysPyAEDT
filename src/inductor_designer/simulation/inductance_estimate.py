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
    "DC bias instead of the incremental slope. The secant runs above the "
    "incremental permeability under DC bias, so this inductance is optimistic"
)
STORED_ENERGY_NOTE = (
    "stored energy is the effective-core-volume estimate "
    "0.5 * B_peak * H_peak * V_e, which assumes a linear medium from the origin "
    "to the peak; for a saturating core it is an upper bound on the true "
    "integral of H dB, so this estimate is optimistic. It is NOT "
    "0.5 * L * I_peak^2 evaluated from the reported incremental inductance, "
    "which describes a different permeability and reads lower under DC bias. "
    "Energy stored in the winding window and in leakage paths is excluded"
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
    if not permeability > 0.0:
        # A recorded B-H series whose flux does not rise with field strength is
        # corrupt data: `materials/validation.py` reports it and material
        # selection blocks it, but a persisted project snapshot is never
        # revalidated on load. Reported blindly this becomes a negative
        # permeability, a negative A_L, and a negative inductance, every one of
        # them labelled Estimated.
        return unavailable(
            DiagnosticCode.INDUCTANCE_NON_POSITIVE_PERMEABILITY,
            "The recorded B-H excursion does not increase with field strength "
            f"({permeability:g} H/m), so permeability is not usable and "
            "inductance cannot be estimated.",
        )
    return permeability, notes


def _geometry_ratio(core: CoreMagneticProperties) -> float | PreliminaryValue:
    """`A_e / l_e`, guarded on both dimensions and on the ratio itself.

    `field_strengths` already refuses a non-positive or non-finite path length
    for every caller inside the estimator, but this module is importable on its
    own, and a ratio can overflow or underflow even when both dimensions pass
    their own checks.
    """
    for name, value in (
        ("effective area", core.effective_area_m2),
        ("magnetic path length", core.path_length_m),
    ):
        if not math.isfinite(value):
            return unavailable(
                DiagnosticCode.INDUCTANCE_NON_FINITE_GEOMETRY,
                f"Core {name} is not a finite number, so the core dimensions "
                "are out of range and the inductance factor cannot be "
                "estimated.",
            )
        if not value > 0.0:
            return unavailable(
                DiagnosticCode.INDUCTANCE_NON_POSITIVE_GEOMETRY,
                f"Core {name} must be positive; got {value:g}. The inductance "
                "factor cannot be estimated.",
            )
    ratio = core.effective_area_m2 / core.path_length_m
    if not math.isfinite(ratio):
        return unavailable(
            DiagnosticCode.INDUCTANCE_NON_FINITE_GEOMETRY,
            "The ratio of core effective area to magnetic path length "
            "overflows, so the core dimensions are out of range.",
        )
    if not ratio > 0.0:
        return unavailable(
            DiagnosticCode.INDUCTANCE_NON_POSITIVE_GEOMETRY,
            "The ratio of core effective area to magnetic path length "
            "underflows to zero, so the core dimensions are out of range.",
        )
    return ratio


def core_inductance(
    fields: FieldStrengths,
    densities: FluxDensities,
    core: CoreMagneticProperties,
) -> CoreInductance | PreliminaryValue:
    """The core-level inductance factor, or the diagnostic explaining its absence.

    `A_L` is a core property: every winding's inductance is `turns**2 * A_L`,
    which the caller applies.

    Every returned number is checked for finiteness, not just the intermediate
    permeability: `estimated()` rejects a non-finite value, so an unguarded
    overflow would reach the screen as "Preliminary estimate failed" rather
    than as a diagnosed row.
    """
    ratio = _geometry_ratio(core)
    if isinstance(ratio, PreliminaryValue):
        return ratio
    permeability = _absolute_permeability(fields, densities)
    if isinstance(permeability, PreliminaryValue):
        return permeability
    mu_abs, notes = permeability

    al_effective_h = mu_abs * ratio
    mu_r_effective = mu_abs / MU_0
    if not (math.isfinite(al_effective_h) and math.isfinite(mu_r_effective)):
        return unavailable(
            DiagnosticCode.INDUCTANCE_NOT_FINITE,
            "The inductance factor overflows for the recorded permeability and "
            "core dimensions, so it is not reported.",
        )
    notes = (INDUCTANCE_EXCLUSION_NOTE, *notes)

    catalog = _al_check(core.al_value_nh, al_effective_h, ratio)
    if catalog is None:
        return CoreInductance(
            mu_r_effective=mu_r_effective,
            al_effective_h=al_effective_h,
            catalog=None,
            notes=notes,
        )
    return CoreInductance(
        mu_r_effective=mu_r_effective,
        al_effective_h=al_effective_h,
        catalog=catalog,
        notes=(*notes, AL_TOLERANCE_NOTE),
    )


def _al_check(
    al_value_nh: float | None, al_effective_h: float, ratio: float
) -> AlCheck | None:
    """The catalog comparison, or None when there is no usable reference.

    None covers both a Manual core, which has no manufacturer value at all, and
    a recorded value that cannot be compared against: `CoreRecord` validates
    only `al_value_nh > 0`, and `inf > 0` is True, which would otherwise yield a
    plausible-looking "-100 %" deviation out of corrupt data. Garbage in the
    reference withdraws the check only -- the effective A_L does not depend on
    it and stays estimated.
    """
    if al_value_nh is None or not (al_value_nh > 0.0 and math.isfinite(al_value_nh)):
        return None
    al_catalog_h = al_value_nh * 1e-9
    mu_r_initial = al_catalog_h / (MU_0 * ratio)
    al_deviation = al_effective_h / al_catalog_h - 1.0
    if not all(math.isfinite(value) for value in (mu_r_initial, al_deviation)):
        return None
    return AlCheck(
        al_catalog_h=al_catalog_h,
        mu_r_initial=mu_r_initial,
        al_deviation=al_deviation,
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
    if not math.isfinite(core.volume_m3):
        return unavailable(
            DiagnosticCode.STORED_ENERGY_NON_FINITE_VOLUME,
            "Core effective volume is not a finite number, so the core "
            "dimensions are out of range and stored energy is not reported.",
        )
    if not core.volume_m3 > 0.0:
        return unavailable(
            DiagnosticCode.STORED_ENERGY_NON_POSITIVE_VOLUME,
            f"Core effective volume must be positive; got {core.volume_m3:g} "
            "m^3. Stored energy is not reported.",
        )
    h_peak_a_per_m = max(abs(fields.h_min_a_per_m), abs(fields.h_max_a_per_m))
    energy_j = 0.5 * densities.b_peak_magnitude_t * h_peak_a_per_m * core.volume_m3
    if not math.isfinite(energy_j):
        return unavailable(
            DiagnosticCode.STORED_ENERGY_NOT_FINITE,
            "The product of peak flux density, peak field strength, and core "
            "volume overflows, so stored energy is not reported.",
        )
    return estimated(energy_j, (STORED_ENERGY_NOTE,))
