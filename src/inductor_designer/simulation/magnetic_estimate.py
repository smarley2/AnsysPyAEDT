"""Lumped effective-core magnetic estimate (specification section 6).

The result is a lumped effective-core value. It is not a local maximum, an
area-weighted mean, a leakage-field result, or a replacement for Maxwell/FEMM
field extraction.
"""

from __future__ import annotations

import cmath
import math
from collections.abc import Mapping
from dataclasses import dataclass

from inductor_designer.domain.project import MaterialRevisionSelection, OperatingPoint
from inductor_designer.domain.winding import (
    CurrentDirection,
    WindingDirection,
    mmf_sign,
)
from inductor_designer.materials.records import PointSeries, SeriesKind
from inductor_designer.simulation.interpolation import interpolate_within_range
from inductor_designer.simulation.preliminary_contracts import (
    DiagnosticCode,
    PreliminaryValue,
    unavailable,
)


@dataclass(frozen=True, slots=True)
class FieldStrengths:
    h_ac_peak_a_per_m: float
    h_dc_a_per_m: float
    h_min_a_per_m: float
    h_max_a_per_m: float


def _reference_direction(
    operating_point: OperatingPoint,
    turns_by_winding: Mapping[str, int],
    winding_direction_by_id: Mapping[str, WindingDirection] | None,
) -> WindingDirection:
    """The winding sense every other winding's sense is measured against.

    The absolute sign of the flux in a closed core is a choice of reference, not
    a physical fact -- only the signs BETWEEN windings are physical. Taking the
    first participating winding's sense as the reference keeps a single-winding
    design's flux positive under forward current, exactly as before cw/ccw
    entered this sum, while making a design that mixes cw and ccw agree with the
    coil polarity `winding_polarity` exports.
    """
    if winding_direction_by_id is None:
        return WindingDirection.COUNTERCLOCKWISE
    for winding in operating_point.windings:
        if winding.winding_id in turns_by_winding:
            return winding_direction_by_id.get(
                winding.winding_id, WindingDirection.COUNTERCLOCKWISE
            )
    return WindingDirection.COUNTERCLOCKWISE


def field_strengths(
    operating_point: OperatingPoint,
    turns_by_winding: Mapping[str, int],
    path_length_m: float,
    winding_direction_by_id: Mapping[str, WindingDirection] | None = None,
) -> FieldStrengths | PreliminaryValue:
    """Return field strengths, or the diagnostic explaining why they are absent.

    `winding_direction_by_id` carries each winding's cw/ccw sense. Omitting it
    treats every winding as wound the same way, which is right only for a
    single-winding design: two windings of opposite sense carrying forward
    current drive the core against each other, and the exported Maxwell coil
    polarity says so whether this sum is told about it or not.
    """
    if not math.isfinite(path_length_m):
        return unavailable(
            DiagnosticCode.FLUX_DENSITY_CORE_PATH_NOT_FINITE,
            "Core effective magnetic path length is not a finite number, so "
            "the core dimensions are out of range.",
        )
    if not path_length_m > 0.0:
        return unavailable(
            DiagnosticCode.FLUX_DENSITY_NON_POSITIVE_PATH_LENGTH,
            "Core effective magnetic path length must be positive; "
            f"got {path_length_m:g} m.",
        )

    reference = _reference_direction(
        operating_point, turns_by_winding, winding_direction_by_id
    )
    ac_phasor = 0j
    dc_ampere_turns = 0.0
    for winding in operating_point.windings:
        turns = turns_by_winding.get(winding.winding_id)
        if turns is None:
            continue
        sense = (
            reference
            if winding_direction_by_id is None
            else winding_direction_by_id.get(winding.winding_id, reference)
        )
        # Both factors are the same rule the exported coil polarity uses, so a
        # winding wound against the reference reverses, and dividing by the
        # reference's own sign keeps the first winding positive.
        sign = mmf_sign(sense, winding.current_direction) * mmf_sign(
            reference, CurrentDirection.FORWARD
        )
        ac_phasor += (
            sign
            * turns
            * math.sqrt(2.0)
            * winding.ac_rms_current_a
            * cmath.exp(1j * math.radians(winding.ac_phase_deg))
        )
        dc_ampere_turns += sign * turns * winding.dc_current_a

    h_ac_peak = abs(ac_phasor) / path_length_m
    h_dc = dc_ampere_turns / path_length_m
    if not all(math.isfinite(value) for value in (h_ac_peak, h_dc)):
        return unavailable(
            DiagnosticCode.FLUX_DENSITY_CORE_PATH_NOT_FINITE,
            "Core effective magnetic path length is too small for the winding "
            "ampere-turns, so the field strength overflows; the core dimensions "
            "are out of range.",
        )
    return FieldStrengths(
        h_ac_peak_a_per_m=h_ac_peak,
        h_dc_a_per_m=h_dc,
        h_min_a_per_m=h_dc - h_ac_peak,
        h_max_a_per_m=h_dc + h_ac_peak,
    )


MU_0 = 4e-7 * math.pi

_ODD_SYMMETRY_NOTE = (
    "negative field strength evaluated by odd symmetry of the first-quadrant "
    "B-H series"
)
_LINEAR_NOTE = (
    "linear permeability approximation; saturation and hysteresis are not modeled"
)


@dataclass(frozen=True, slots=True)
class FluxDensities:
    b_dc_t: float
    b_min_t: float
    b_max_t: float
    b_ac_peak_t: float
    b_peak_magnitude_t: float
    notes: tuple[str, ...]
    # The curve these came from, so a consumer needing the shape of B(H) and
    # not just its value at a few points -- stored energy integrates it -- does
    # not have to re-select a series and risk choosing a different one. None
    # means the linear-permeability branch below produced these values, and
    # there is no recorded curve to integrate.
    bh_series: PointSeries | None = None


def _interpolate(series: PointSeries, h: float) -> float | None:
    """Odd-symmetric linear interpolation; None when outside the recorded range."""
    magnitude = abs(h)
    value = interpolate_within_range([(point.x, point.y) for point in series.points], magnitude)
    if value is None:
        return None
    sign = 1.0 if h >= 0.0 else -1.0
    return sign * value


def _select_bh_series(
    selection: MaterialRevisionSelection, core_temperature_c: float
) -> tuple[PointSeries | None, tuple[PointSeries, ...]]:
    """Return the chosen series (if any) and the pin-filtered candidates.

    Returning the candidates lets the caller report only the temperatures the
    current `bh_series_id` pin can actually reach, instead of every recorded
    B-H series regardless of the pin.
    """
    candidates = tuple(
        series
        for series in selection.snapshot.series
        if series.kind is SeriesKind.BH_CURVE
        and (selection.bh_series_id is None or series.series_id == selection.bh_series_id)
    )
    for series in candidates:
        if series.conditions.temperature_c == core_temperature_c:
            return series, candidates
    return None, candidates


def flux_densities(
    selection: MaterialRevisionSelection,
    fields: FieldStrengths,
    core_temperature_c: float,
) -> FluxDensities | PreliminaryValue:
    """Map H to B using recorded B-H data, else a labelled linear approximation."""
    bh_series, candidates = _select_bh_series(selection, core_temperature_c)
    if bh_series is not None:
        mapped: list[float] = []
        for h in (fields.h_min_a_per_m, fields.h_dc_a_per_m, fields.h_max_a_per_m):
            value = _interpolate(bh_series, h)
            if value is None:
                if not bh_series.points:
                    return unavailable(
                        DiagnosticCode.FLUX_DENSITY_FIELD_OUTSIDE_BH_RANGE,
                        f"Series {bh_series.series_id} records no field-strength "
                        "points, so the requested field strength cannot be "
                        "bounded; extrapolation is not performed.",
                    )
                lowest = min(point.x for point in bh_series.points)
                largest = max(point.x for point in bh_series.points)
                return unavailable(
                    DiagnosticCode.FLUX_DENSITY_FIELD_OUTSIDE_BH_RANGE,
                    f"Field strength {h:g} A/m is outside the recorded range of "
                    f"series {bh_series.series_id} ({lowest:g} to {largest:g} A/m); "
                    "extrapolation is not performed.",
                )
            mapped.append(value)
        b_min, b_dc, b_max = mapped
        notes: tuple[str, ...] = ()
        if min(fields.h_min_a_per_m, fields.h_dc_a_per_m, fields.h_max_a_per_m) < 0.0:
            notes = (_ODD_SYMMETRY_NOTE,)
        return _assemble(b_dc, b_min, b_max, notes, bh_series)

    available = sorted(
        {
            series.conditions.temperature_c
            for series in candidates
            if series.conditions.temperature_c is not None
        }
    )
    if available:
        recorded = ", ".join(f"{value:g} C" for value in available)
        return unavailable(
            DiagnosticCode.FLUX_DENSITY_NO_BH_SERIES_FOR_TEMPERATURE,
            f"No B-H series recorded at {core_temperature_c:g} C; "
            f"available: {recorded}. Set the core temperature to a recorded "
            "value or import a series at the temperature you need.",
        )
    if candidates:
        # A B-H series exists (and, if a pin is set, matches it), but it
        # records no temperature at all: falling through to the linear-
        # permeability approximation below would label the result with a
        # message claiming there is no B-H series, which is false.
        return unavailable(
            DiagnosticCode.FLUX_DENSITY_NO_BH_SERIES_FOR_TEMPERATURE,
            "The selected B-H series records no temperature, so it cannot be "
            f"matched against the requested core temperature "
            f"({core_temperature_c:g} C).",
        )

    permeability = selection.snapshot.relative_permeability
    if permeability is not None and permeability > 0.0:
        factor = MU_0 * permeability
        return _assemble(
            factor * fields.h_dc_a_per_m,
            factor * fields.h_min_a_per_m,
            factor * fields.h_max_a_per_m,
            (_LINEAR_NOTE,),
        )

    return unavailable(
        DiagnosticCode.FLUX_DENSITY_NO_SUPPORTED_MODEL,
        "The selected material revision has no B-H series and no relative "
        "permeability, so flux density cannot be estimated.",
    )


def _assemble(
    b_dc: float,
    b_min: float,
    b_max: float,
    notes: tuple[str, ...],
    bh_series: PointSeries | None = None,
) -> FluxDensities:
    return FluxDensities(
        b_dc_t=b_dc,
        b_min_t=b_min,
        b_max_t=b_max,
        b_ac_peak_t=(b_max - b_min) / 2.0,
        b_peak_magnitude_t=max(abs(b_min), abs(b_max)),
        notes=notes,
        bh_series=bh_series,
    )


_GAP_LOADLINE_NOTE = (
    "gapped core: flux from the reluctance loadline "
    "NI = H*l_iron + (B/mu_0)*l_gap intersected with the recorded B-H curve, "
    "not from ampere-turns over a path length. Fringing is excluded, which "
    "understates reluctance and so overstates inductance, by more as the gap "
    "grows"
)
_GAP_BISECTION_STEPS = 80


def _solve_loadline(
    mmf: float,
    iron_length_m: float,
    gap_length_m: float,
    series: PointSeries,
) -> tuple[float, float] | None:
    """The (H_iron, B) pair on the curve that carries `mmf`, or None.

    Bisection, because the loadline is monotone: B(H) rises with H on a B-H
    curve, so `H*l_iron + B(H)/mu_0*l_gap` rises too, and the root is
    bracketed by zero and the ungapped field strength `mmf/l_iron` (a gap can
    only reduce the iron's share of the ampere-turns, never raise it).

    None means the curve does not reach the required flux density -- the same
    condition the ungapped path reports as a field strength outside the
    recorded range, and reported by the caller in the same way.
    """
    sign = 1.0 if mmf >= 0.0 else -1.0
    magnitude = abs(mmf)
    if magnitude == 0.0:
        return 0.0, 0.0
    if not series.points:
        return None
    ungapped_h = magnitude / iron_length_m
    if gap_length_m == 0.0:
        # No gap, no loadline: the whole MMF is in the iron. Answered here so
        # the gapped path is a strict generalisation of the ungapped one, and
        # so an out-of-range flux density is reported by the same rule rather
        # than by a bracket that happens to fail.
        b = _interpolate(series, ungapped_h)
        return None if b is None else (sign * ungapped_h, sign * b)
    # Bracket at the recorded curve's own top, not at the ungapped field
    # strength: with a gap the solution is far below `NI/l_iron`, and asking
    # the curve for a value at that point is what a gap makes unnecessary. A
    # gap of zero collapses the bracket back onto it.
    upper = min(ungapped_h, max(point.x for point in series.points))

    def excess(h: float) -> float | None:
        b = _interpolate(series, h)
        if b is None:
            return None
        return h * iron_length_m + b / MU_0 * gap_length_m - magnitude

    top = excess(upper)
    if top is None:
        return None
    if top <= 0.0:
        # Even at the top of the recorded curve the loadline cannot carry
        # this MMF, so the answer lies outside the data. For a zero gap this
        # is exactly the ungapped out-of-range case, and it is reported the
        # same way rather than extrapolated.
        if upper >= ungapped_h:
            return sign * upper, sign * (_interpolate(series, upper) or 0.0)
        return None
    low, high = 0.0, upper
    for _ in range(_GAP_BISECTION_STEPS):
        middle = (low + high) / 2.0
        value = excess(middle)
        if value is None:
            return None
        if value > 0.0:
            high = middle
        else:
            low = middle
    h_iron = (low + high) / 2.0
    b = _interpolate(series, h_iron)
    if b is None:
        return None
    return sign * h_iron, sign * b


def gapped_fields_and_flux(
    selection: MaterialRevisionSelection,
    ungapped: FieldStrengths,
    iron_length_m: float,
    gap_length_m: float,
    effective_area_m2: float,
    core_temperature_c: float,
) -> tuple[FieldStrengths, FluxDensities] | PreliminaryValue:
    """Field strength and flux density for a gapped core, solved together.

    The ungapped pipeline computes H from geometry and then B from the
    material, in that order. A gap breaks the ordering: the iron's share of
    the ampere-turns depends on the flux density, which depends on the
    material -- so both are solved at once here, against the same recorded
    B-H curve the ungapped path uses.

    `ungapped` carries the ampere-turns: `field_strengths` already applied the
    winding-sense rule to produce it, and `H * iron_length_m` recovers the MMF
    exactly. Recovering it rather than re-deriving it keeps one implementation
    of that sign rule, which matters more here than the last float bit.
    """
    if not math.isfinite(gap_length_m) or gap_length_m < 0.0:
        return unavailable(
            DiagnosticCode.FLUX_DENSITY_CORE_PATH_NOT_FINITE,
            "Core gap length is not a finite, non-negative number, so the "
            "gapped flux cannot be solved.",
        )
    if not math.isfinite(effective_area_m2) or effective_area_m2 <= 0.0:
        return unavailable(
            DiagnosticCode.FLUX_DENSITY_CORE_PATH_NOT_FINITE,
            "Core effective area must be a positive number to solve a gapped "
            f"core; got {effective_area_m2:g} m^2.",
        )
    series, _candidates = _select_bh_series(selection, core_temperature_c)
    if series is None:
        # No recorded curve: the linear branch of `flux_densities` owns that
        # case, and it has no loadline to solve against.
        return unavailable(
            DiagnosticCode.FLUX_DENSITY_NO_BH_SERIES_FOR_TEMPERATURE,
            "A gapped core needs a recorded B-H series to solve its "
            "reluctance loadline; none of the pinned revision's series "
            "applies at this temperature.",
        )

    solved: list[tuple[float, float]] = []
    for h in (ungapped.h_min_a_per_m, ungapped.h_dc_a_per_m, ungapped.h_max_a_per_m):
        pair = _solve_loadline(h * iron_length_m, iron_length_m, gap_length_m, series)
        if pair is None:
            lowest = min(point.x for point in series.points) if series.points else 0.0
            largest = max(point.x for point in series.points) if series.points else 0.0
            return unavailable(
                DiagnosticCode.FLUX_DENSITY_FIELD_OUTSIDE_BH_RANGE,
                f"Solving the gap loadline needs a point outside the recorded "
                f"range of series {series.series_id} ({lowest:g} to "
                f"{largest:g} A/m); extrapolation is not performed.",
            )
        solved.append(pair)

    (h_min, b_min), (h_dc, b_dc), (h_max, b_max) = solved
    fields = FieldStrengths(
        h_ac_peak_a_per_m=(h_max - h_min) / 2.0,
        h_dc_a_per_m=h_dc,
        h_min_a_per_m=h_min,
        h_max_a_per_m=h_max,
    )
    notes: tuple[str, ...] = (_GAP_LOADLINE_NOTE,)
    if min(h_min, h_dc, h_max) < 0.0:
        notes = (*notes, _ODD_SYMMETRY_NOTE)
    return fields, _assemble(b_dc, b_min, b_max, notes, series)
