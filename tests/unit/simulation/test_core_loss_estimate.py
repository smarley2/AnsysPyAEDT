from __future__ import annotations

import math
from dataclasses import replace

from inductor_designer.domain.project import MaterialRevisionSelection
from inductor_designer.materials.records import (
    CurveConditions,
    CurvePoint,
    PointSeries,
    SeriesKind,
    SteinmetzFit,
)
from inductor_designer.simulation.core_loss_estimate import core_loss_w
from inductor_designer.simulation.preliminary_contracts import (
    DiagnosticCode,
    ResultState,
)
from tests.unit.simulation.test_magnetic_estimate import make_material_selection


def replace_steinmetz(
    selection: MaterialRevisionSelection, fit: SteinmetzFit
) -> MaterialRevisionSelection:
    return replace(selection, snapshot=replace(selection.snapshot, steinmetz=fit))


def make_loss_series(
    series_id: str = "loss-100khz",
    frequency_hz: float | None = 100_000.0,
    temperature_c: float | None = 25.0,
    dc_bias_a_per_m: float | None = 0.0,
    points: tuple[tuple[float, float], ...] = ((0.05, 1000.0), (0.1, 4000.0)),
) -> PointSeries:
    return PointSeries(
        series_id=series_id,
        kind=SeriesKind.LOSS_TABLE,
        x_unit="T",
        y_unit="W/m3",
        conditions=CurveConditions(
            frequency_hz=frequency_hz,
            temperature_c=temperature_c,
            dc_bias_a_per_m=dc_bias_a_per_m,
        ),
        points=tuple(CurvePoint(b, loss) for b, loss in points),
        source_filename="loss.csv",
    )


def test_loss_table_is_preferred_and_interpolated_inside_its_range() -> None:
    result = core_loss_w(
        make_material_selection(series=(make_loss_series(),)),
        b_ac_peak_t=0.075,
        frequency_hz=100_000.0,
        core_temperature_c=25.0,
        h_dc_a_per_m=0.0,
        core_volume_m3=5.34e-6,
    )

    assert result.state is ResultState.ESTIMATED
    assert result.value is not None
    assert math.isclose(result.value, 2500.0 * 5.34e-6)


def test_flux_beyond_the_loss_table_range_is_not_extrapolated() -> None:
    result = core_loss_w(
        make_material_selection(series=(make_loss_series(),)),
        b_ac_peak_t=0.5,
        frequency_hz=100_000.0,
        core_temperature_c=25.0,
        h_dc_a_per_m=0.0,
        core_volume_m3=5.34e-6,
    )

    assert result.code == DiagnosticCode.CORE_LOSS_FLUX_OUTSIDE_LOSS_RANGE


def test_temperature_mismatch_names_the_recorded_temperatures() -> None:
    result = core_loss_w(
        make_material_selection(series=(make_loss_series(temperature_c=25.0),)),
        b_ac_peak_t=0.075,
        frequency_hz=100_000.0,
        core_temperature_c=80.0,
        h_dc_a_per_m=0.0,
        core_volume_m3=5.34e-6,
    )

    assert result.code == DiagnosticCode.CORE_LOSS_NO_LOSS_DATA_FOR_TEMPERATURE
    assert "25" in str(result.message)


def test_nonzero_dc_bias_without_supporting_data_is_unavailable() -> None:
    result = core_loss_w(
        make_material_selection(series=(make_loss_series(dc_bias_a_per_m=0.0),)),
        b_ac_peak_t=0.075,
        frequency_hz=100_000.0,
        core_temperature_c=25.0,
        h_dc_a_per_m=1800.0,
        core_volume_m3=5.34e-6,
    )

    assert result.code == DiagnosticCode.CORE_LOSS_NO_LOSS_DATA_FOR_DC_BIAS
    assert "1800" in str(result.message)


def test_steinmetz_fit_is_used_when_no_table_matches_the_frequency() -> None:
    # Two tables bound the requested frequency (25 kHz, 100 kHz) without either
    # matching it exactly, so order-1 (an exact-frequency table) cannot apply
    # and the Steinmetz fit's envelope must be used instead.
    selection = make_material_selection(
        series=(
            make_loss_series(series_id="loss-25khz", frequency_hz=25_000.0),
            make_loss_series(series_id="loss-100khz-b", frequency_hz=100_000.0),
        )
    )
    fitted = replace_steinmetz(selection, SteinmetzFit(2.0, 1.5, 2.0, 0.0, 0.0))

    result = core_loss_w(
        fitted,
        b_ac_peak_t=0.075,
        frequency_hz=50_000.0,
        core_temperature_c=25.0,
        h_dc_a_per_m=0.0,
        core_volume_m3=5.34e-6,
    )

    expected_volume = 2.0 * 50_000.0**1.5 * 0.075**2.0
    assert result.state is ResultState.ESTIMATED
    assert result.value is not None
    assert math.isclose(result.value, expected_volume * 5.34e-6)


def test_frequency_outside_the_fit_envelope_is_refused() -> None:
    selection = make_material_selection(series=(make_loss_series(frequency_hz=100_000.0),))
    fitted = replace_steinmetz(selection, SteinmetzFit(2.0, 1.5, 2.0, 0.0, 0.0))

    result = core_loss_w(
        fitted,
        b_ac_peak_t=0.075,
        frequency_hz=1_000_000.0,
        core_temperature_c=25.0,
        h_dc_a_per_m=0.0,
        core_volume_m3=5.34e-6,
    )

    assert result.code == DiagnosticCode.CORE_LOSS_FREQUENCY_OUTSIDE_FIT_ENVELOPE


def test_no_loss_model_at_all_is_unavailable() -> None:
    result = core_loss_w(
        make_material_selection(),
        b_ac_peak_t=0.075,
        frequency_hz=100_000.0,
        core_temperature_c=25.0,
        h_dc_a_per_m=0.0,
        core_volume_m3=5.34e-6,
    )

    assert result.code == DiagnosticCode.CORE_LOSS_NO_LOSS_MODEL


def test_non_positive_frequency_and_volume_are_refused() -> None:
    selection = make_material_selection(series=(make_loss_series(),))

    zero_frequency = core_loss_w(
        selection, 0.075, 0.0, 25.0, 0.0, 5.34e-6
    )
    zero_volume = core_loss_w(
        selection, 0.075, 100_000.0, 25.0, 0.0, 0.0
    )

    assert zero_frequency.code == DiagnosticCode.CORE_LOSS_NON_POSITIVE_FREQUENCY
    assert zero_volume.code == DiagnosticCode.CORE_LOSS_NON_POSITIVE_VOLUME


def test_non_finite_volume_is_a_diagnostic_not_a_crash() -> None:
    selection = make_material_selection(series=(make_loss_series(),))

    result = core_loss_w(
        selection, 0.075, 100_000.0, 25.0, 0.0, float("inf")
    )

    assert result.code == DiagnosticCode.CORE_LOSS_NON_FINITE_VOLUME


def test_flux_beyond_the_fit_envelope_is_not_extrapolated() -> None:
    # Same bounding-frequency setup as the Steinmetz-fit test above (25 kHz and
    # 100 kHz tables, request at 50 kHz so the fit branch is taken), but this
    # time the requested flux falls outside the recorded 0.05-0.1 T envelope.
    selection = make_material_selection(
        series=(
            make_loss_series(series_id="loss-25khz", frequency_hz=25_000.0),
            make_loss_series(series_id="loss-100khz-b", frequency_hz=100_000.0),
        )
    )
    fitted = replace_steinmetz(selection, SteinmetzFit(2.0, 1.5, 2.0, 0.0, 0.0))

    result = core_loss_w(
        fitted,
        b_ac_peak_t=0.5,
        frequency_hz=50_000.0,
        core_temperature_c=25.0,
        h_dc_a_per_m=0.0,
        core_volume_m3=5.34e-6,
    )

    assert result.code == DiagnosticCode.CORE_LOSS_FLUX_OUTSIDE_LOSS_RANGE


def test_flux_below_the_loss_table_range_is_not_extrapolated() -> None:
    result = core_loss_w(
        make_material_selection(series=(make_loss_series(),)),
        b_ac_peak_t=0.01,
        frequency_hz=100_000.0,
        core_temperature_c=25.0,
        h_dc_a_per_m=0.0,
        core_volume_m3=5.34e-6,
    )

    assert result.code == DiagnosticCode.CORE_LOSS_FLUX_OUTSIDE_LOSS_RANGE


def test_an_unbiased_loss_table_supports_a_zero_bias_request() -> None:
    """A recorded dc_bias_a_per_m of None is an ordinary unbiased datasheet
    curve -- it never recorded a bias field -- and must be usable for a
    zero-bias request, while still refusing a nonzero one.
    """
    unbiased = make_material_selection(
        series=(make_loss_series(dc_bias_a_per_m=None),)
    )

    zero_bias = core_loss_w(
        unbiased,
        b_ac_peak_t=0.075,
        frequency_hz=100_000.0,
        core_temperature_c=25.0,
        h_dc_a_per_m=0.0,
        core_volume_m3=5.34e-6,
    )
    nonzero_bias = core_loss_w(
        unbiased,
        b_ac_peak_t=0.075,
        frequency_hz=100_000.0,
        core_temperature_c=25.0,
        h_dc_a_per_m=1800.0,
        core_volume_m3=5.34e-6,
    )

    assert zero_bias.state is ResultState.ESTIMATED
    assert nonzero_bias.code == DiagnosticCode.CORE_LOSS_NO_LOSS_DATA_FOR_DC_BIAS


def test_dc_bias_mismatch_message_does_not_name_a_bias_from_another_temperature() -> None:
    """A series at 100 C happens to record a distinctive nonzero bias. A
    request at 25 C with no supporting bias data must not list that 100 C
    bias as though it were recorded at the requested temperature.
    """
    result = core_loss_w(
        make_material_selection(
            series=(
                make_loss_series(
                    series_id="loss-25c", temperature_c=25.0, dc_bias_a_per_m=0.0
                ),
                make_loss_series(
                    series_id="loss-100c", temperature_c=100.0, dc_bias_a_per_m=4200.0
                ),
            )
        ),
        b_ac_peak_t=0.075,
        frequency_hz=100_000.0,
        core_temperature_c=25.0,
        h_dc_a_per_m=1800.0,
        core_volume_m3=5.34e-6,
    )

    assert result.code == DiagnosticCode.CORE_LOSS_NO_LOSS_DATA_FOR_DC_BIAS
    assert "4200" not in str(result.message)


def test_steinmetz_fit_is_refused_when_any_source_series_mismatches_condition() -> None:
    """Two 25 C series (25 kHz and 100 kHz) genuinely bracket the requested
    50 kHz -- without the contamination guard, the fit's frequency envelope
    check alone would pass and the fit would be Estimated. A third series,
    recorded at 100 C, contaminates the pooled fit even though the request is
    at 25 C. Per specification section 8 step 2, the fit cannot be trusted
    unless every source series it pools matches the requested temperature and
    DC bias, so it must be refused rather than silently applied.

    This is the scenario that regressed silently once before: an earlier
    version of this test bracketed the frequency using only the contaminating
    series, so it was refused (for the wrong reason, frequency-envelope) even
    before the contamination guard existed, and never proved the guard did
    anything. Checked against commit f82c5cd (pre-guard): this rewritten
    scenario is Estimated there and refused with
    CORE_LOSS_FIT_SOURCES_MISMATCH_CONDITION here.
    """
    selection = make_material_selection(
        series=(
            make_loss_series(
                series_id="loss-25khz", frequency_hz=25_000.0, temperature_c=25.0
            ),
            make_loss_series(
                series_id="loss-100khz", frequency_hz=100_000.0, temperature_c=25.0
            ),
            make_loss_series(
                series_id="loss-100c", frequency_hz=100_000.0, temperature_c=100.0
            ),
        )
    )
    fitted = replace_steinmetz(selection, SteinmetzFit(2.0, 1.5, 2.0, 0.0, 0.0))

    result = core_loss_w(
        fitted,
        b_ac_peak_t=0.075,
        frequency_hz=50_000.0,
        core_temperature_c=25.0,
        h_dc_a_per_m=0.0,
        core_volume_m3=5.34e-6,
    )

    assert result.code == DiagnosticCode.CORE_LOSS_FIT_SOURCES_MISMATCH_CONDITION


def test_bias_mismatch_names_zero_when_recorded_bias_is_none() -> None:
    """An unbiased 25 C table recorded no dc_bias_a_per_m at all, which
    _supports_condition treats as a measurement at zero bias. The mismatch
    enumeration must coerce the same way instead of reporting it as
    unrecorded -- naming "none recorded" for the very table just treated as
    zero-bias data would contradict that support rule.
    """
    result = core_loss_w(
        make_material_selection(
            series=(make_loss_series(temperature_c=25.0, dc_bias_a_per_m=None),)
        ),
        b_ac_peak_t=0.075,
        frequency_hz=100_000.0,
        core_temperature_c=25.0,
        h_dc_a_per_m=1234.0,
        core_volume_m3=5.34e-6,
    )

    assert result.code == DiagnosticCode.CORE_LOSS_NO_LOSS_DATA_FOR_DC_BIAS
    assert "recorded bias: 0 A/m" in str(result.message)
    assert "none recorded" not in str(result.message)


def test_an_exact_frequency_series_with_no_points_does_not_crash() -> None:
    """A loss table that matches the requested condition and frequency
    exactly, but records no flux-density points, must return a diagnostic
    instead of raising when min()/max() would otherwise be called on an
    empty sequence. validate_series does not require loss points, so a
    record like this can pass validation and reach here.
    """
    result = core_loss_w(
        make_material_selection(series=(make_loss_series(points=()),)),
        b_ac_peak_t=0.075,
        frequency_hz=100_000.0,
        core_temperature_c=25.0,
        h_dc_a_per_m=0.0,
        core_volume_m3=5.34e-6,
    )

    assert result.code == DiagnosticCode.CORE_LOSS_FLUX_OUTSIDE_LOSS_RANGE
    assert "no flux-density points" in str(result.message)


def test_a_supported_series_with_no_points_cannot_skip_the_flux_envelope_check() -> None:
    """Both source series bound the requested frequency but record no
    flux-density points at all. Without a guard, an empty flux envelope is
    silently skipped, letting any flux density through unbounded.
    """
    selection = make_material_selection(
        series=(
            make_loss_series(series_id="loss-25khz", frequency_hz=25_000.0, points=()),
            make_loss_series(series_id="loss-100khz", frequency_hz=100_000.0, points=()),
        )
    )
    fitted = replace_steinmetz(selection, SteinmetzFit(2.0, 1.5, 2.0, 0.0, 0.0))

    result = core_loss_w(
        fitted,
        b_ac_peak_t=0.075,
        frequency_hz=50_000.0,
        core_temperature_c=25.0,
        h_dc_a_per_m=0.0,
        core_volume_m3=5.34e-6,
    )

    assert result.code == DiagnosticCode.CORE_LOSS_FLUX_OUTSIDE_LOSS_RANGE


def test_loss_table_wins_over_a_present_steinmetz_fit_with_a_different_answer() -> None:
    # A Steinmetz fit is attached alongside an exact-frequency loss table. The
    # fit's parameters are chosen so its prediction is wildly different from
    # the table's interpolated value, so if the code ever consulted the fit
    # first this assertion (not just the diagnostic) would catch it.
    selection = make_material_selection(series=(make_loss_series(),))
    fitted = replace_steinmetz(selection, SteinmetzFit(1.0, 2.0, 3.0, 0.0, 0.0))

    result = core_loss_w(
        fitted,
        b_ac_peak_t=0.075,
        frequency_hz=100_000.0,
        core_temperature_c=25.0,
        h_dc_a_per_m=0.0,
        core_volume_m3=5.34e-6,
    )

    fit_volumetric = 1.0 * 100_000.0**2.0 * 0.075**3.0
    assert result.state is ResultState.ESTIMATED
    assert result.value is not None
    assert math.isclose(result.value, 2500.0 * 5.34e-6)
    assert not math.isclose(result.value, fit_volumetric * 5.34e-6)
