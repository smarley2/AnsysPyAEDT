"""Core-loss estimate (specification section 8).

No temperature correction, DC-bias correction, waveform correction, frequency
extrapolation, flux-density extrapolation, or material substitution is invented.
"""

from __future__ import annotations

from math import isfinite

from inductor_designer.domain.project import MaterialRevisionSelection
from inductor_designer.materials.records import PointSeries, SeriesKind
from inductor_designer.simulation.interpolation import interpolate_within_range
from inductor_designer.simulation.preliminary_contracts import (
    DiagnosticCode,
    PreliminaryValue,
    estimated,
    unavailable,
)

_STEINMETZ_NOTE = (
    "Steinmetz fit evaluated inside its source-data envelope; no temperature, "
    "DC-bias, or waveform correction is applied"
)
_TABLE_NOTE = "interpolated from a recorded loss table at the requested condition"
# Decision: Fabio Posser, 2026-08-03 (see spec section 8 amendment). Manufacturer
# loss curves are almost always published at zero DC bias only; refusing every
# biased operating point left core loss blank for most real designs.
_ZERO_BIAS_APPROXIMATION_NOTE = (
    "core loss evaluated from zero-DC-bias loss data; DC premagnetization "
    "increases loss for a given AC flux swing and is not modeled, so this "
    "estimate is optimistic"
)


def _loss_series(selection: MaterialRevisionSelection) -> tuple[PointSeries, ...]:
    return tuple(
        series
        for series in selection.snapshot.series
        if series.kind is SeriesKind.LOSS_TABLE
    )


def _is_zero_bias(series: PointSeries) -> bool:
    recorded_bias = series.conditions.dc_bias_a_per_m
    return recorded_bias is None or recorded_bias == 0.0


def _bias_characterized_at_temperature(
    series: tuple[PointSeries, ...], core_temperature_c: float
) -> bool:
    """True when the material has at least one loss series, recorded at the
    requested temperature, with a nonzero DC bias.

    That is the only case with real bias-dependent loss data, so it is the
    only case where the strict exact-bias-match rule applies. Otherwise only
    zero-bias data exists at this temperature, and it is used to approximate
    any requested bias (specification section 8 amendment, 2026-08-03).
    """
    return any(
        item.conditions.temperature_c == core_temperature_c and not _is_zero_bias(item)
        for item in series
    )


def _supports_condition(
    series: PointSeries,
    core_temperature_c: float,
    h_dc_a_per_m: float,
    bias_characterized: bool,
) -> bool:
    if series.conditions.temperature_c != core_temperature_c:
        return False
    if _is_zero_bias(series):
        if bias_characterized:
            # This material does have bias-dependent data at this
            # temperature, just not from this particular (zero-bias) series,
            # so the strict rule applies: it supports only a zero-bias
            # request.
            return h_dc_a_per_m == 0.0
        # No bias-dependent data exists for this material at this
        # temperature at all, so the zero-bias curve is the best available
        # data and is used to approximate any requested bias.
        return True
    return series.conditions.dc_bias_a_per_m == h_dc_a_per_m


def _interpolate_loss(series: PointSeries, b_ac_peak_t: float) -> float | None:
    return interpolate_within_range(
        [(point.x, point.y) for point in series.points], b_ac_peak_t
    )


def core_loss_w(
    selection: MaterialRevisionSelection,
    b_ac_peak_t: float,
    frequency_hz: float,
    core_temperature_c: float,
    h_dc_a_per_m: float,
    core_volume_m3: float,
) -> PreliminaryValue:
    if not frequency_hz > 0.0:
        return unavailable(
            DiagnosticCode.CORE_LOSS_NON_POSITIVE_FREQUENCY,
            f"Core loss requires a positive frequency; got {frequency_hz:g} Hz.",
        )
    if not isfinite(core_volume_m3):
        return unavailable(
            DiagnosticCode.CORE_LOSS_NON_FINITE_VOLUME,
            "Core volume is not a finite number, so the core dimensions are "
            "out of range.",
        )
    if not core_volume_m3 > 0.0:
        return unavailable(
            DiagnosticCode.CORE_LOSS_NON_POSITIVE_VOLUME,
            f"Core loss requires a positive core volume; got {core_volume_m3:g} m3.",
        )

    series = _loss_series(selection)
    if not series:
        return unavailable(
            DiagnosticCode.CORE_LOSS_NO_LOSS_MODEL,
            "The selected material revision has no loss table and no Steinmetz "
            "fit, so core loss cannot be estimated.",
        )

    bias_characterized = _bias_characterized_at_temperature(series, core_temperature_c)
    supported = [
        item
        for item in series
        if _supports_condition(item, core_temperature_c, h_dc_a_per_m, bias_characterized)
    ]
    if not supported:
        temperatures = sorted(
            {
                item.conditions.temperature_c
                for item in series
                if item.conditions.temperature_c is not None
            }
        )
        if core_temperature_c not in temperatures:
            recorded = (
                ", ".join(f"{value:g} C" for value in temperatures)
                if temperatures
                else "none recorded"
            )
            return unavailable(
                DiagnosticCode.CORE_LOSS_NO_LOSS_DATA_FOR_TEMPERATURE,
                f"No loss data recorded at {core_temperature_c:g} C; "
                f"available: {recorded}.",
            )
        # Unlike temperature, H_DC is not a value the user sets directly: it
        # follows from the winding DC currents, turns, and core path length.
        # Naming a recorded bias from a *different* temperature would also be
        # meaningless, so only biases recorded at the requested temperature
        # are pooled here.
        biases = sorted(
            {
                0.0
                if item.conditions.dc_bias_a_per_m is None
                else item.conditions.dc_bias_a_per_m
                for item in series
                if item.conditions.temperature_c == core_temperature_c
            }
        )
        recorded_bias = (
            ", ".join(f"{value:g} A/m" for value in biases)
            if biases
            else "none recorded"
        )
        return unavailable(
            DiagnosticCode.CORE_LOSS_NO_LOSS_DATA_FOR_DC_BIAS,
            f"DC bias {h_dc_a_per_m:g} A/m follows from the winding DC "
            "currents, turns, and core path length; loss data at that bias "
            f"is not recorded (recorded bias: {recorded_bias}).",
        )

    exact = [
        item for item in supported if item.conditions.frequency_hz == frequency_hz
    ]
    if exact:
        if not exact[0].points:
            return unavailable(
                DiagnosticCode.CORE_LOSS_FLUX_OUTSIDE_LOSS_RANGE,
                f"Series {exact[0].series_id} records no flux-density points, "
                "so the requested flux density cannot be bounded; "
                "extrapolation is not performed.",
            )
        volumetric = _interpolate_loss(exact[0], b_ac_peak_t)
        if volumetric is None:
            lowest = min(point.x for point in exact[0].points)
            highest = max(point.x for point in exact[0].points)
            return unavailable(
                DiagnosticCode.CORE_LOSS_FLUX_OUTSIDE_LOSS_RANGE,
                f"AC flux density {b_ac_peak_t:g} T is outside the recorded "
                f"range of series {exact[0].series_id} ({lowest:g} to "
                f"{highest:g} T); extrapolation is not performed.",
            )
        notes: tuple[str, ...] = (_TABLE_NOTE,)
        if not bias_characterized and h_dc_a_per_m != 0.0:
            notes = notes + (_ZERO_BIAS_APPROXIMATION_NOTE,)
        return estimated(volumetric * core_volume_m3, notes=notes)

    fit = selection.snapshot.steinmetz
    if fit is None:
        return unavailable(
            DiagnosticCode.CORE_LOSS_NO_LOSS_MODEL,
            f"No loss table recorded at {frequency_hz:g} Hz and no Steinmetz "
            "fit is stored on the selected revision.",
        )

    # The stored fit pools every recorded loss series regardless of condition
    # (specification section 8 step 2), so it can only be trusted when EVERY
    # series on the record -- not just the ones already known to match --
    # supports the requested temperature and DC bias. Otherwise a request at
    # this condition could be silently answered by a fit contaminated with
    # data recorded at another temperature or bias.
    if any(
        not _supports_condition(item, core_temperature_c, h_dc_a_per_m, bias_characterized)
        for item in series
    ):
        return unavailable(
            DiagnosticCode.CORE_LOSS_FIT_SOURCES_MISMATCH_CONDITION,
            "The stored Steinmetz fit pools all recorded loss series and "
            "cannot be used unless every one of them matches the requested "
            f"condition ({core_temperature_c:g} C, {h_dc_a_per_m:g} A/m DC "
            "bias); at least one recorded series was measured at a "
            "different condition, so the fit is refused.",
        )

    frequencies = [
        item.conditions.frequency_hz
        for item in supported
        if item.conditions.frequency_hz is not None
    ]
    if not frequencies or not min(frequencies) <= frequency_hz <= max(frequencies):
        envelope = (
            f"{min(frequencies):g} to {max(frequencies):g} Hz"
            if frequencies
            else "unknown"
        )
        return unavailable(
            DiagnosticCode.CORE_LOSS_FREQUENCY_OUTSIDE_FIT_ENVELOPE,
            f"Frequency {frequency_hz:g} Hz is outside the fit's source-data "
            f"envelope ({envelope}); the fit is not extrapolated.",
        )

    flux_values = [point.x for item in supported for point in item.points]
    if not flux_values:
        # No source series recorded any flux-density points at all, so there
        # is no envelope to check against: this must refuse, not silently
        # skip the check and let any flux density through unbounded.
        return unavailable(
            DiagnosticCode.CORE_LOSS_FLUX_OUTSIDE_LOSS_RANGE,
            "The fit's source series record no flux-density points, so the "
            "requested flux density cannot be bounded; extrapolation is not "
            "performed.",
        )
    if not min(flux_values) <= b_ac_peak_t <= max(flux_values):
        return unavailable(
            DiagnosticCode.CORE_LOSS_FLUX_OUTSIDE_LOSS_RANGE,
            f"AC flux density {b_ac_peak_t:g} T is outside the fit's source-data "
            f"range ({min(flux_values):g} to {max(flux_values):g} T).",
        )

    volumetric = fit.k * frequency_hz**fit.alpha * b_ac_peak_t**fit.beta
    fit_notes: tuple[str, ...] = (_STEINMETZ_NOTE,)
    if not bias_characterized and h_dc_a_per_m != 0.0:
        fit_notes = fit_notes + (_ZERO_BIAS_APPROXIMATION_NOTE,)
    return estimated(volumetric * core_volume_m3, notes=fit_notes)
