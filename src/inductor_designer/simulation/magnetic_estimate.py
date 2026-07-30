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
from inductor_designer.domain.winding import CurrentDirection
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


def _sign(direction: CurrentDirection) -> float:
    return 1.0 if direction is CurrentDirection.FORWARD else -1.0


def field_strengths(
    operating_point: OperatingPoint,
    turns_by_winding: Mapping[str, int],
    path_length_m: float,
) -> FieldStrengths | PreliminaryValue:
    """Return field strengths, or the diagnostic explaining why they are absent."""
    if not path_length_m > 0.0:
        return unavailable(
            DiagnosticCode.FLUX_DENSITY_NON_POSITIVE_PATH_LENGTH,
            "Core effective magnetic path length must be positive; "
            f"got {path_length_m:g} m.",
        )

    ac_phasor = 0j
    dc_ampere_turns = 0.0
    for winding in operating_point.windings:
        turns = turns_by_winding.get(winding.winding_id)
        if turns is None:
            continue
        sign = _sign(winding.current_direction)
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
        return _assemble(b_dc, b_min, b_max, notes)

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
    b_dc: float, b_min: float, b_max: float, notes: tuple[str, ...]
) -> FluxDensities:
    return FluxDensities(
        b_dc_t=b_dc,
        b_min_t=b_min,
        b_max_t=b_max,
        b_ac_peak_t=(b_max - b_min) / 2.0,
        b_peak_magnitude_t=max(abs(b_min), abs(b_max)),
        notes=notes,
    )
