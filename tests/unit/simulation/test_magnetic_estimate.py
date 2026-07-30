from __future__ import annotations

import math

from inductor_designer.domain.project import (
    MaterialRevisionSelection,
    OperatingPoint,
    WindingOperatingPoint,
)
from inductor_designer.domain.winding import CurrentDirection
from inductor_designer.materials.identity import MaterialRef
from inductor_designer.materials.records import (
    CurveConditions,
    CurvePoint,
    MaterialRecord,
    MaterialStatus,
    PointSeries,
    SeriesKind,
    SourceKind,
    SourceProvenance,
)
from inductor_designer.simulation.magnetic_estimate import (
    FieldStrengths,
    FluxDensities,
    field_strengths,
    flux_densities,
)
from inductor_designer.simulation.preliminary_contracts import (
    DiagnosticCode,
    PreliminaryValue,
)

MU_0 = 4e-7 * math.pi


def make_operating_point(*windings: WindingOperatingPoint) -> OperatingPoint:
    return OperatingPoint(frequency_hz=100_000.0, windings=windings)


def make_winding(
    winding_id: str,
    *,
    ac_rms: float = 0.0,
    phase_deg: float = 0.0,
    dc: float = 0.0,
    direction: CurrentDirection = CurrentDirection.FORWARD,
) -> WindingOperatingPoint:
    return WindingOperatingPoint(
        winding_id=winding_id,
        ac_rms_current_a=ac_rms,
        ac_phase_deg=phase_deg,
        dc_current_a=dc,
        current_direction=direction,
    )


def test_single_winding_ac_peak_uses_sqrt_two_times_rms() -> None:
    result = field_strengths(
        make_operating_point(make_winding("w1", ac_rms=2.0)),
        {"w1": 10},
        path_length_m=0.1,
    )

    assert isinstance(result, FieldStrengths)
    # 10 turns * sqrt(2) * 2 A / 0.1 m
    assert result.h_ac_peak_a_per_m == 10 * math.sqrt(2) * 2.0 / 0.1
    assert result.h_dc_a_per_m == 0.0
    assert result.h_min_a_per_m == -result.h_ac_peak_a_per_m
    assert result.h_max_a_per_m == result.h_ac_peak_a_per_m


def test_in_phase_windings_add_and_reverse_direction_subtracts() -> None:
    same = field_strengths(
        make_operating_point(make_winding("w1", ac_rms=1.0), make_winding("w2", ac_rms=1.0)),
        {"w1": 10, "w2": 10},
        path_length_m=0.1,
    )
    opposed = field_strengths(
        make_operating_point(
            make_winding("w1", ac_rms=1.0),
            make_winding("w2", ac_rms=1.0, direction=CurrentDirection.REVERSE),
        ),
        {"w1": 10, "w2": 10},
        path_length_m=0.1,
    )

    assert isinstance(same, FieldStrengths)
    assert isinstance(opposed, FieldStrengths)
    assert math.isclose(same.h_ac_peak_a_per_m, 2 * 10 * math.sqrt(2) / 0.1)
    assert math.isclose(opposed.h_ac_peak_a_per_m, 0.0, abs_tol=1e-9)


def test_quadrature_phases_combine_as_phasors_not_magnitudes() -> None:
    result = field_strengths(
        make_operating_point(
            make_winding("w1", ac_rms=1.0, phase_deg=0.0),
            make_winding("w2", ac_rms=1.0, phase_deg=90.0),
        ),
        {"w1": 10, "w2": 10},
        path_length_m=0.1,
    )

    assert isinstance(result, FieldStrengths)
    single = 10 * math.sqrt(2) * 1.0 / 0.1
    assert math.isclose(result.h_ac_peak_a_per_m, single * math.sqrt(2))


def test_dc_ampere_turns_are_summed_separately_and_shift_the_window() -> None:
    result = field_strengths(
        make_operating_point(make_winding("w1", ac_rms=1.0, dc=5.0)),
        {"w1": 10},
        path_length_m=0.1,
    )

    assert isinstance(result, FieldStrengths)
    assert result.h_dc_a_per_m == 10 * 5.0 / 0.1
    assert math.isclose(
        result.h_min_a_per_m, result.h_dc_a_per_m - result.h_ac_peak_a_per_m
    )
    assert math.isclose(
        result.h_max_a_per_m, result.h_dc_a_per_m + result.h_ac_peak_a_per_m
    )


def test_reverse_direction_flips_the_dc_contribution() -> None:
    result = field_strengths(
        make_operating_point(
            make_winding("w1", dc=5.0, direction=CurrentDirection.REVERSE)
        ),
        {"w1": 10},
        path_length_m=0.1,
    )

    assert isinstance(result, FieldStrengths)
    assert result.h_dc_a_per_m == -10 * 5.0 / 0.1


def test_non_positive_path_length_is_a_diagnostic_not_a_crash() -> None:
    result = field_strengths(
        make_operating_point(make_winding("w1", ac_rms=1.0)),
        {"w1": 10},
        path_length_m=0.0,
    )

    assert isinstance(result, PreliminaryValue)
    assert result.code == DiagnosticCode.FLUX_DENSITY_NON_POSITIVE_PATH_LENGTH


def test_a_winding_without_a_turn_count_contributes_nothing() -> None:
    result = field_strengths(
        make_operating_point(make_winding("w1", ac_rms=1.0), make_winding("w2", ac_rms=1.0)),
        {"w1": 10},
        path_length_m=0.1,
    )

    assert isinstance(result, FieldStrengths)
    assert math.isclose(result.h_ac_peak_a_per_m, 10 * math.sqrt(2) / 0.1)


def make_bh_series(
    series_id: str = "bh-25c",
    temperature_c: float | None = 25.0,
    points: tuple[tuple[float, float], ...] = ((0.0, 0.0), (100.0, 0.5), (200.0, 0.8)),
) -> PointSeries:
    return PointSeries(
        series_id=series_id,
        kind=SeriesKind.BH_CURVE,
        x_unit="A/m",
        y_unit="T",
        conditions=CurveConditions(
            frequency_hz=None, temperature_c=temperature_c, dc_bias_a_per_m=None
        ),
        points=tuple(CurvePoint(h, b) for h, b in points),
        source_filename="bh.csv",
    )


def make_material_selection(
    *,
    series: tuple[PointSeries, ...] = (),
    relative_permeability: float | None = None,
    bh_series_id: str | None = None,
) -> MaterialRevisionSelection:
    ref = MaterialRef("Magnetics", "High Flux", "60")
    record = MaterialRecord(
        ref=ref,
        revision_id="0123456789ab",
        status=MaterialStatus.IMPORTED,
        created_at="2026-07-29T00:00:00+00:00",
        reviewed_by=None,
        approved_by=None,
        sources=(
            SourceProvenance(
                kind=SourceKind.CSV,
                filename="bh.csv",
                sha256="0" * 64,
                url="",
                page=None,
                captured_at="2026-07-29T00:00:00",
                description="test",
            ),
            SourceProvenance(
                kind=SourceKind.CSV,
                filename="loss.csv",
                sha256="0" * 64,
                url="",
                page=None,
                captured_at="2026-07-29T00:00:00",
                description="test",
            ),
        ),
        series=series,
        relative_permeability=relative_permeability,
        mass_density_kg_per_m3=8176.0,
        steinmetz=None,
        notes="",
    )
    return MaterialRevisionSelection(
        ref=ref,
        revision_id="0123456789ab",
        snapshot=record,
        bh_series_id=bh_series_id,
    )


def make_field_strengths(h_dc: float, h_ac_peak: float) -> FieldStrengths:
    return FieldStrengths(
        h_ac_peak_a_per_m=h_ac_peak,
        h_dc_a_per_m=h_dc,
        h_min_a_per_m=h_dc - h_ac_peak,
        h_max_a_per_m=h_dc + h_ac_peak,
    )


def test_bh_series_interpolates_linearly_inside_the_recorded_range() -> None:
    result = flux_densities(
        make_material_selection(series=(make_bh_series(),), bh_series_id="bh-25c"),
        make_field_strengths(h_dc=50.0, h_ac_peak=0.0),
        core_temperature_c=25.0,
    )

    assert isinstance(result, FluxDensities)
    assert math.isclose(result.b_dc_t, 0.25)


def test_negative_field_uses_reported_odd_symmetry() -> None:
    result = flux_densities(
        make_material_selection(series=(make_bh_series(),), bh_series_id="bh-25c"),
        make_field_strengths(h_dc=0.0, h_ac_peak=100.0),
        core_temperature_c=25.0,
    )

    assert isinstance(result, FluxDensities)
    assert math.isclose(result.b_min_t, -0.5)
    assert math.isclose(result.b_max_t, 0.5)
    assert math.isclose(result.b_ac_peak_t, 0.5)
    assert math.isclose(result.b_peak_magnitude_t, 0.5)
    assert any("odd symmetry" in note for note in result.notes)


def test_field_beyond_the_recorded_range_is_not_extrapolated() -> None:
    result = flux_densities(
        make_material_selection(series=(make_bh_series(),), bh_series_id="bh-25c"),
        make_field_strengths(h_dc=0.0, h_ac_peak=250.0),
        core_temperature_c=25.0,
    )

    assert isinstance(result, PreliminaryValue)
    assert result.code == DiagnosticCode.FLUX_DENSITY_FIELD_OUTSIDE_BH_RANGE
    assert "200" in str(result.message)


def test_temperature_mismatch_names_the_available_temperatures() -> None:
    result = flux_densities(
        make_material_selection(
            series=(make_bh_series(temperature_c=25.0),), bh_series_id="bh-25c"
        ),
        make_field_strengths(h_dc=50.0, h_ac_peak=0.0),
        core_temperature_c=80.0,
    )

    assert isinstance(result, PreliminaryValue)
    assert result.code == DiagnosticCode.FLUX_DENSITY_NO_BH_SERIES_FOR_TEMPERATURE
    assert "80" in str(result.message)
    assert "25" in str(result.message)


def test_linear_permeability_fallback_is_labelled() -> None:
    result = flux_densities(
        make_material_selection(relative_permeability=60.0),
        make_field_strengths(h_dc=1000.0, h_ac_peak=0.0),
        core_temperature_c=25.0,
    )

    assert isinstance(result, FluxDensities)
    assert math.isclose(result.b_dc_t, MU_0 * 60.0 * 1000.0)
    assert any("linear permeability approximation" in note for note in result.notes)


def test_field_below_the_recorded_range_is_not_extrapolated() -> None:
    """A B-H series that does not start at the origin (bypassing the domain
    validator that normally forces this) must refuse a field below its lowest
    recorded point rather than silently clamping to that point's B value.

    The refusal message must state the series' actual lower bound (100 A/m),
    not a hardcoded 0 -- a message reading "50 A/m is outside the recorded
    range (0 to 200 A/m)" would claim 50 is both outside and inside the
    stated range at once.
    """
    result = flux_densities(
        make_material_selection(
            series=(make_bh_series(points=((100.0, 0.5), (200.0, 0.8))),),
            bh_series_id="bh-25c",
        ),
        make_field_strengths(h_dc=50.0, h_ac_peak=0.0),
        core_temperature_c=25.0,
    )

    assert isinstance(result, PreliminaryValue)
    assert result.code == DiagnosticCode.FLUX_DENSITY_FIELD_OUTSIDE_BH_RANGE
    assert "(100 to 200 A/m)" in str(result.message)


def test_bh_series_with_no_points_is_a_diagnostic_not_a_crash() -> None:
    """A pinned, temperature-matched B-H series that records no points at all
    must not raise when min()/max() would otherwise be called on an empty
    sequence.
    """
    result = flux_densities(
        make_material_selection(
            series=(make_bh_series(points=()),), bh_series_id="bh-25c"
        ),
        make_field_strengths(h_dc=50.0, h_ac_peak=0.0),
        core_temperature_c=25.0,
    )

    assert isinstance(result, PreliminaryValue)
    assert result.code == DiagnosticCode.FLUX_DENSITY_FIELD_OUTSIDE_BH_RANGE
    assert "no field-strength points" in str(result.message)


def test_pinned_series_mismatch_names_only_temperatures_the_pin_can_reach() -> None:
    """A series matching the requested temperature exists, but it is not the
    pinned series, so the pin cannot reach it. The mismatch message must not
    offer that unreachable temperature as though the pin could satisfy it.
    """
    result = flux_densities(
        make_material_selection(
            series=(
                make_bh_series(series_id="bh-pin", temperature_c=100.0),
                make_bh_series(series_id="bh-other", temperature_c=45.0),
            ),
            bh_series_id="bh-pin",
        ),
        make_field_strengths(h_dc=50.0, h_ac_peak=0.0),
        core_temperature_c=45.0,
    )

    assert isinstance(result, PreliminaryValue)
    assert result.code == DiagnosticCode.FLUX_DENSITY_NO_BH_SERIES_FOR_TEMPERATURE
    available_text = str(result.message).split("available:", 1)[1]
    assert "45" not in available_text
    assert "100" in available_text


def test_pinned_series_with_no_temperature_refuses_rather_than_falling_back() -> None:
    """The pinned B-H series records no temperature at all, so it can never
    be matched against a requested core temperature. Falling through to the
    linear-permeability approximation would attach a note claiming the
    revision "has no B-H series", which is false -- one exists but cannot be
    matched. This must refuse with FLUX_DENSITY_NO_BH_SERIES_FOR_TEMPERATURE
    instead.
    """
    result = flux_densities(
        make_material_selection(
            series=(make_bh_series(series_id="bh-pin", temperature_c=None),),
            bh_series_id="bh-pin",
            relative_permeability=60.0,
        ),
        make_field_strengths(h_dc=50.0, h_ac_peak=0.0),
        core_temperature_c=25.0,
    )

    assert isinstance(result, PreliminaryValue)
    assert result.code == DiagnosticCode.FLUX_DENSITY_NO_BH_SERIES_FOR_TEMPERATURE
    assert "no temperature" in str(result.message).lower()


def test_no_model_at_all_is_unavailable() -> None:
    result = flux_densities(
        make_material_selection(),
        make_field_strengths(h_dc=1000.0, h_ac_peak=0.0),
        core_temperature_c=25.0,
    )

    assert isinstance(result, PreliminaryValue)
    assert result.code == DiagnosticCode.FLUX_DENSITY_NO_SUPPORTED_MODEL
