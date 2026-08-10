"""Inductance, A_L, and stored energy from an operating-point excursion.

Every case builds `FieldStrengths` and `FluxDensities` directly. That keeps the
permeability rules testable without a B-H series, a material record, or a whole
`PreliminaryRequest`.
"""

from __future__ import annotations

import pytest

from inductor_designer.simulation.inductance_estimate import (
    AL_TOLERANCE_NOTE,
    INDUCTANCE_EXCLUSION_NOTE,
    STORED_ENERGY_INTEGRATED_NOTE,
    STORED_ENERGY_LINEAR_NOTE,
    STORED_ENERGY_ORIGIN_NOTE,
    ZERO_RIPPLE_NOTE,
    CoreInductance,
    core_inductance,
    stored_energy_j,
)
from inductor_designer.simulation.magnetic_estimate import (
    MU_0,
    FieldStrengths,
    FluxDensities,
)
from inductor_designer.simulation.preliminary_contracts import (
    CoreMagneticProperties,
    DiagnosticCode,
    PreliminaryValue,
    ResultState,
)
from tests.unit.simulation.test_magnetic_estimate import make_bh_series

# 100 A/m of ripple on a 200 A/m bias: the excursion runs 100 to 300 A/m.
BIASED_FIELDS = FieldStrengths(
    h_ac_peak_a_per_m=100.0,
    h_dc_a_per_m=200.0,
    h_min_a_per_m=100.0,
    h_max_a_per_m=300.0,
)
# 0.2 T of swing over that 200 A/m span, so the incremental slope is 1e-3 H/m.
BIASED_DENSITIES = FluxDensities(
    b_dc_t=0.4,
    b_min_t=0.3,
    b_max_t=0.5,
    b_ac_peak_t=0.1,
    b_peak_magnitude_t=0.5,
    notes=(),
)
# A_e / l_e = 1e-3 m, so A_L effective is 1e-3 H/m * 1e-3 m = 1 uH per turn
# squared. The catalog value is deliberately higher, giving a -20 % roll-off.
CORE = CoreMagneticProperties(
    path_length_m=0.1,
    volume_m3=1e-5,
    effective_area_m2=1e-4,
    al_value_nh=1250.0,
)


def test_permeability_is_the_incremental_slope_over_the_excursion() -> None:
    result = core_inductance(BIASED_FIELDS, BIASED_DENSITIES, CORE)

    assert isinstance(result, CoreInductance)
    assert result.mu_r_effective == pytest.approx(1e-3 / MU_0)
    assert ZERO_RIPPLE_NOTE not in result.notes
    assert INDUCTANCE_EXCLUSION_NOTE in result.notes


def test_al_effective_is_permeability_times_area_over_path_length() -> None:
    result = core_inductance(BIASED_FIELDS, BIASED_DENSITIES, CORE)

    assert isinstance(result, CoreInductance)
    assert result.al_effective_h == pytest.approx(1e-6)


def test_the_catalog_check_reports_the_roll_off_against_the_manufacturer_value() -> None:
    result = core_inductance(BIASED_FIELDS, BIASED_DENSITIES, CORE)

    assert isinstance(result, CoreInductance)
    assert result.catalog is not None
    assert result.catalog.al_catalog_h == pytest.approx(1.25e-6)
    assert result.catalog.al_deviation == pytest.approx(-0.2)
    # The reference permeability is derived from the catalog A_L, never read
    # from the material record, so the two reported numbers cannot disagree.
    assert result.catalog.mu_r_initial == pytest.approx(
        1.25e-6 * CORE.path_length_m / (MU_0 * CORE.effective_area_m2)
    )
    assert AL_TOLERANCE_NOTE in result.notes


def test_an_effective_factor_above_catalog_reports_a_positive_deviation() -> None:
    """Sign check: the deviation must not be reported as a magnitude."""
    core = CoreMagneticProperties(
        path_length_m=0.1, volume_m3=1e-5, effective_area_m2=1e-4, al_value_nh=800.0
    )

    result = core_inductance(BIASED_FIELDS, BIASED_DENSITIES, core)

    assert isinstance(result, CoreInductance)
    assert result.catalog is not None
    assert result.catalog.al_deviation == pytest.approx(0.25)


def test_zero_ripple_falls_back_to_the_secant_at_the_bias_and_says_so() -> None:
    fields = FieldStrengths(
        h_ac_peak_a_per_m=0.0,
        h_dc_a_per_m=200.0,
        h_min_a_per_m=200.0,
        h_max_a_per_m=200.0,
    )
    densities = FluxDensities(
        b_dc_t=0.4,
        b_min_t=0.4,
        b_max_t=0.4,
        b_ac_peak_t=0.0,
        b_peak_magnitude_t=0.4,
        notes=(),
    )

    result = core_inductance(fields, densities, CORE)

    assert isinstance(result, CoreInductance)
    assert result.mu_r_effective == pytest.approx((0.4 / 200.0) / MU_0)
    assert ZERO_RIPPLE_NOTE in result.notes


def test_no_excitation_at_all_leaves_permeability_undefined() -> None:
    """No substituted initial permeability, no zero, no default."""
    fields = FieldStrengths(
        h_ac_peak_a_per_m=0.0,
        h_dc_a_per_m=0.0,
        h_min_a_per_m=0.0,
        h_max_a_per_m=0.0,
    )
    densities = FluxDensities(
        b_dc_t=0.0,
        b_min_t=0.0,
        b_max_t=0.0,
        b_ac_peak_t=0.0,
        b_peak_magnitude_t=0.0,
        notes=(),
    )

    result = core_inductance(fields, densities, CORE)

    assert isinstance(result, PreliminaryValue)
    assert result.state is ResultState.UNAVAILABLE
    assert result.code == DiagnosticCode.INDUCTANCE_NO_EXCITATION


def test_a_manual_core_has_no_reference_to_check_against() -> None:
    core = CoreMagneticProperties(
        path_length_m=0.1, volume_m3=1e-5, effective_area_m2=1e-4, al_value_nh=None
    )

    result = core_inductance(BIASED_FIELDS, BIASED_DENSITIES, core)

    assert isinstance(result, CoreInductance)
    assert result.catalog is None
    assert result.al_effective_h == pytest.approx(1e-6)
    assert AL_TOLERANCE_NOTE not in result.notes


def test_a_decreasing_excursion_is_refused_not_reported_as_negative() -> None:
    """A B-H series whose flux falls with rising field is corrupt data.

    `materials/validation.py` flags it and core-material selection blocks it,
    but the estimator reads a persisted project snapshot that is never
    revalidated. Without this guard the screen reports a negative permeability,
    a negative A_L and a negative inductance, all labelled Estimated.
    """
    densities = FluxDensities(
        b_dc_t=0.4,
        b_min_t=0.5,
        b_max_t=0.3,
        b_ac_peak_t=0.1,
        b_peak_magnitude_t=0.5,
        notes=(),
    )

    result = core_inductance(BIASED_FIELDS, densities, CORE)

    assert isinstance(result, PreliminaryValue)
    assert result.code == DiagnosticCode.INDUCTANCE_NON_POSITIVE_PERMEABILITY


@pytest.mark.parametrize("area", [0.0, -1e-4])
def test_a_non_positive_area_refuses_al_instead_of_dividing(area: float) -> None:
    core = CoreMagneticProperties(
        path_length_m=0.1, volume_m3=1e-5, effective_area_m2=area, al_value_nh=1250.0
    )

    result = core_inductance(BIASED_FIELDS, BIASED_DENSITIES, core)

    assert isinstance(result, PreliminaryValue)
    assert result.code == DiagnosticCode.INDUCTANCE_NON_POSITIVE_GEOMETRY


@pytest.mark.parametrize("area", [float("inf"), float("nan")])
def test_a_non_finite_area_refuses_al_instead_of_dividing(area: float) -> None:
    core = CoreMagneticProperties(
        path_length_m=0.1, volume_m3=1e-5, effective_area_m2=area, al_value_nh=1250.0
    )

    result = core_inductance(BIASED_FIELDS, BIASED_DENSITIES, core)

    assert isinstance(result, PreliminaryValue)
    assert result.code == DiagnosticCode.INDUCTANCE_NON_FINITE_GEOMETRY


@pytest.mark.parametrize("path_length", [0.0, -0.1])
def test_a_non_positive_path_length_refuses_al_instead_of_dividing(
    path_length: float,
) -> None:
    """`field_strengths` refuses this first for every caller inside the
    estimator, but this module is importable on its own and must not raise
    ZeroDivisionError to prove a point about call order.
    """
    core = CoreMagneticProperties(
        path_length_m=path_length,
        volume_m3=1e-5,
        effective_area_m2=1e-4,
        al_value_nh=1250.0,
    )

    result = core_inductance(BIASED_FIELDS, BIASED_DENSITIES, core)

    assert isinstance(result, PreliminaryValue)
    assert result.code == DiagnosticCode.INDUCTANCE_NON_POSITIVE_GEOMETRY


def test_an_underflowing_geometry_ratio_is_refused_not_reported_as_zero() -> None:
    """Both dimensions pass their own guards, but their ratio underflows."""
    core = CoreMagneticProperties(
        path_length_m=1e300,
        volume_m3=1e-5,
        effective_area_m2=1e-300,
        al_value_nh=1250.0,
    )

    result = core_inductance(BIASED_FIELDS, BIASED_DENSITIES, core)

    assert isinstance(result, PreliminaryValue)
    assert result.code == DiagnosticCode.INDUCTANCE_NON_POSITIVE_GEOMETRY


def test_an_overflowing_geometry_ratio_is_refused_not_reported() -> None:
    core = CoreMagneticProperties(
        path_length_m=1e-3,
        volume_m3=1e-5,
        effective_area_m2=1e308,
        al_value_nh=1250.0,
    )

    result = core_inductance(BIASED_FIELDS, BIASED_DENSITIES, core)

    assert isinstance(result, PreliminaryValue)
    assert result.code == DiagnosticCode.INDUCTANCE_NON_FINITE_GEOMETRY


def test_an_overflowing_inductance_factor_is_refused_not_reported() -> None:
    """`estimated()` rejects a non-finite number, so an unguarded overflow here
    would surface as "Preliminary estimate failed" instead of a diagnosed row.
    """
    densities = FluxDensities(
        b_dc_t=0.0,
        b_min_t=0.0,
        b_max_t=1e308,
        b_ac_peak_t=5e307,
        b_peak_magnitude_t=1e308,
        notes=(),
    )
    fields = FieldStrengths(
        h_ac_peak_a_per_m=0.5,
        h_dc_a_per_m=0.5,
        h_min_a_per_m=0.0,
        h_max_a_per_m=1.0,
    )
    core = CoreMagneticProperties(
        path_length_m=0.1, volume_m3=1e-5, effective_area_m2=1.0, al_value_nh=1250.0
    )

    result = core_inductance(fields, densities, core)

    assert isinstance(result, PreliminaryValue)
    assert result.code == DiagnosticCode.INDUCTANCE_NOT_FINITE


def test_an_unusable_catalog_al_refuses_the_check_but_keeps_the_inductance() -> None:
    """`CoreRecord` only checks `al_value_nh > 0`, and `inf > 0` is True.

    Reported blindly, an infinite catalog value gives a plausible-looking
    "-100 %" deviation. The effective A_L is unaffected by garbage in the
    reference, so only the check is withdrawn.
    """
    core = CoreMagneticProperties(
        path_length_m=0.1,
        volume_m3=1e-5,
        effective_area_m2=1e-4,
        al_value_nh=float("inf"),
    )

    result = core_inductance(BIASED_FIELDS, BIASED_DENSITIES, core)

    assert isinstance(result, CoreInductance)
    assert result.catalog is None
    assert result.al_effective_h == pytest.approx(1e-6)


def test_the_two_reported_permeabilities_agree_with_the_reported_deviation() -> None:
    """Design section 3.3: the reference permeability is derived from the
    catalog A_L precisely so the two rows cannot contradict each other. This
    pins that relation, which a factor slip in either one would break.
    """
    result = core_inductance(BIASED_FIELDS, BIASED_DENSITIES, CORE)

    assert isinstance(result, CoreInductance)
    assert result.catalog is not None
    assert result.mu_r_effective / result.catalog.mu_r_initial == pytest.approx(
        1.0 + result.catalog.al_deviation
    )


def test_an_overflowing_slope_is_refused_not_reported() -> None:
    """A denormal field span with a finite flux swing overflows the slope.

    `PreliminaryValue` rejects a non-finite estimate, so without this guard the
    Preliminary screen would report "estimate failed" instead of a diagnosed
    row.
    """
    fields = FieldStrengths(
        h_ac_peak_a_per_m=5e-324,
        h_dc_a_per_m=0.0,
        h_min_a_per_m=0.0,
        h_max_a_per_m=5e-324,
    )

    result = core_inductance(fields, BIASED_DENSITIES, CORE)

    assert isinstance(result, PreliminaryValue)
    assert result.code == DiagnosticCode.INDUCTANCE_NOT_FINITE


def test_stored_energy_pairs_peak_flux_with_peak_field_over_the_volume() -> None:
    """With no recorded curve the permeability model is linear, and 0.5*B*H*V is
    that model's exact energy -- and exactly 0.5*L*I_peak^2 for the same model.
    """
    result = stored_energy_j(BIASED_FIELDS, BIASED_DENSITIES, CORE)

    assert result.state is ResultState.ESTIMATED
    # 0.5 * 0.5 T * 300 A/m * 1e-5 m^3
    assert result.value == pytest.approx(7.5e-4)
    assert STORED_ENERGY_LINEAR_NOTE in result.notes


def _densities(
    b_peak_t: float, points: tuple[tuple[float, float], ...]
) -> FluxDensities:
    """Flux densities carrying a recorded B-H curve, peaking at `b_peak_t`."""
    return FluxDensities(
        b_dc_t=b_peak_t,
        b_min_t=0.0,
        b_max_t=b_peak_t,
        b_ac_peak_t=b_peak_t / 2.0,
        b_peak_magnitude_t=b_peak_t,
        notes=(),
        bh_series=make_bh_series(points=points),
    )


def test_stored_energy_integrates_the_recorded_curve_when_one_is_available() -> None:
    """Energy density is the area to the LEFT of the B-H curve, integral H dB.

    Curve (0,0) -> (100 A/m, 0.5 T) -> (200 A/m, 0.8 T), taken to 0.8 T:
    (0+100)/2 * 0.5 = 25, plus (100+200)/2 * 0.3 = 45, so 70 J/m^3.
    """
    fields = FieldStrengths(
        h_ac_peak_a_per_m=100.0,
        h_dc_a_per_m=100.0,
        h_min_a_per_m=0.0,
        h_max_a_per_m=200.0,
    )

    densities = _densities(0.8, ((0.0, 0.0), (100.0, 0.5), (200.0, 0.8)))

    result = stored_energy_j(fields, densities, CORE)

    assert result.state is ResultState.ESTIMATED
    assert result.value == pytest.approx(70.0 * CORE.volume_m3)
    assert STORED_ENERGY_INTEGRATED_NOTE in result.notes
    assert STORED_ENERGY_LINEAR_NOTE not in result.notes


def test_the_integral_is_below_the_linear_form_it_replaces() -> None:
    """The saturating curve is the whole point: 0.5*B*H over-counts by 14 % here,
    and the gap widens with bias. Same inputs, both formulas, one assertion.
    """
    fields = FieldStrengths(
        h_ac_peak_a_per_m=100.0,
        h_dc_a_per_m=100.0,
        h_min_a_per_m=0.0,
        h_max_a_per_m=200.0,
    )
    densities = _densities(0.8, ((0.0, 0.0), (100.0, 0.5), (200.0, 0.8)))

    integrated = stored_energy_j(fields, densities, CORE).value
    linear_form = 0.5 * 0.8 * 200.0 * CORE.volume_m3

    assert integrated is not None
    assert integrated < linear_form
    assert integrated == pytest.approx(70.0 / 80.0 * linear_form)


def test_a_straight_curve_integrates_to_exactly_the_linear_form() -> None:
    """Sanity check on the integrator: for B = mu*H the two must coincide."""
    fields = FieldStrengths(
        h_ac_peak_a_per_m=50.0,
        h_dc_a_per_m=50.0,
        h_min_a_per_m=0.0,
        h_max_a_per_m=100.0,
    )

    result = stored_energy_j(fields, _densities(0.6, ((0.0, 0.0), (100.0, 0.6))), CORE)

    assert result.value == pytest.approx(0.5 * 0.6 * 100.0 * CORE.volume_m3)


def test_the_integral_stops_partway_through_the_bracketing_segment() -> None:
    """Peak 0.65 T sits halfway up the second segment, where H is 150 A/m:
    25 + (100+150)/2 * 0.15 = 43.75 J/m^3.
    """
    fields = FieldStrengths(
        h_ac_peak_a_per_m=75.0,
        h_dc_a_per_m=75.0,
        h_min_a_per_m=0.0,
        h_max_a_per_m=150.0,
    )

    densities = _densities(0.65, ((0.0, 0.0), (100.0, 0.5), (200.0, 0.8)))

    result = stored_energy_j(fields, densities, CORE)

    assert result.value == pytest.approx(43.75 * CORE.volume_m3)


def test_a_curve_not_recorded_from_the_origin_says_it_assumed_one() -> None:
    """Anhysteretic B-H data usually starts at the origin; when it does not, the
    first segment has to come from somewhere, and the assumption is stated.
    """
    fields = FieldStrengths(
        h_ac_peak_a_per_m=50.0,
        h_dc_a_per_m=50.0,
        h_min_a_per_m=0.0,
        h_max_a_per_m=100.0,
    )

    result = stored_energy_j(fields, _densities(0.5, ((50.0, 0.3), (100.0, 0.5))), CORE)

    # (0+50)/2 * 0.3 = 7.5, plus (50+100)/2 * 0.2 = 15
    assert result.value == pytest.approx(22.5 * CORE.volume_m3)
    assert STORED_ENERGY_ORIGIN_NOTE in result.notes


def test_a_peak_above_the_recorded_curve_is_refused_not_extrapolated() -> None:
    fields = FieldStrengths(
        h_ac_peak_a_per_m=100.0,
        h_dc_a_per_m=100.0,
        h_min_a_per_m=0.0,
        h_max_a_per_m=200.0,
    )

    result = stored_energy_j(fields, _densities(0.95, ((0.0, 0.0), (200.0, 0.8))), CORE)

    assert result.state is ResultState.UNAVAILABLE
    assert result.code == DiagnosticCode.STORED_ENERGY_FLUX_OUTSIDE_BH_RANGE


def test_a_curve_that_doubles_back_below_the_peak_is_refused() -> None:
    """A B that falls with rising H makes the area to the left of the curve
    ambiguous, and the same corrupt data already refuses permeability.
    """
    fields = FieldStrengths(
        h_ac_peak_a_per_m=100.0,
        h_dc_a_per_m=100.0,
        h_min_a_per_m=0.0,
        h_max_a_per_m=200.0,
    )

    result = stored_energy_j(
        fields,
        _densities(0.9, ((0.0, 0.0), (100.0, 0.8), (150.0, 0.6), (200.0, 0.9))),
        CORE,
    )

    assert result.state is ResultState.UNAVAILABLE
    assert result.code == DiagnosticCode.STORED_ENERGY_NON_MONOTONIC_BH


def test_a_curve_that_doubles_back_above_the_peak_still_integrates() -> None:
    """Only the path actually walked has to be well behaved. Refusing because of
    a defect the integral never reaches would withhold a sound number.
    """
    fields = FieldStrengths(
        h_ac_peak_a_per_m=100.0,
        h_dc_a_per_m=100.0,
        h_min_a_per_m=0.0,
        h_max_a_per_m=200.0,
    )

    result = stored_energy_j(
        fields, _densities(0.7, ((0.0, 0.0), (100.0, 0.8), (200.0, 0.6))), CORE
    )

    assert result.state is ResultState.ESTIMATED
    # The peak sits at 7/8 of the first segment, where H is 87.5 A/m:
    # (0 + 87.5) / 2 * 0.7 = 30.625 J/m^3.
    assert result.value == pytest.approx(30.625 * CORE.volume_m3)


def test_stored_energy_uses_the_larger_field_magnitude_of_the_excursion() -> None:
    """A reverse-direction bias smaller than the ripple puts the peak field at
    |H_min|, so an implementation that reads `h_max` alone is off by a factor of
    two here. `h_min` is deliberately the larger magnitude.
    """
    fields = FieldStrengths(
        h_ac_peak_a_per_m=300.0,
        h_dc_a_per_m=-100.0,
        h_min_a_per_m=-400.0,
        h_max_a_per_m=200.0,
    )
    densities = FluxDensities(
        b_dc_t=-0.2,
        b_min_t=-0.5,
        b_max_t=0.4,
        b_ac_peak_t=0.45,
        b_peak_magnitude_t=0.5,
        notes=(),
    )

    result = stored_energy_j(fields, densities, CORE)

    assert result.value == pytest.approx(0.5 * 0.5 * 400.0 * 1e-5)


def test_zero_excitation_still_stores_zero_energy() -> None:
    """Energy needs no permeability, so it survives what inductance refuses."""
    fields = FieldStrengths(
        h_ac_peak_a_per_m=0.0,
        h_dc_a_per_m=0.0,
        h_min_a_per_m=0.0,
        h_max_a_per_m=0.0,
    )
    densities = FluxDensities(
        b_dc_t=0.0,
        b_min_t=0.0,
        b_max_t=0.0,
        b_ac_peak_t=0.0,
        b_peak_magnitude_t=0.0,
        notes=(),
    )

    result = stored_energy_j(fields, densities, CORE)

    assert result.state is ResultState.ESTIMATED
    assert result.value == 0.0


@pytest.mark.parametrize(
    ("volume", "code"),
    [
        (0.0, DiagnosticCode.STORED_ENERGY_NON_POSITIVE_VOLUME),
        (-1e-5, DiagnosticCode.STORED_ENERGY_NON_POSITIVE_VOLUME),
        (float("inf"), DiagnosticCode.STORED_ENERGY_NON_FINITE_VOLUME),
        (float("nan"), DiagnosticCode.STORED_ENERGY_NON_FINITE_VOLUME),
    ],
)
def test_an_unusable_volume_refuses_stored_energy(volume: float, code: str) -> None:
    """Non-positive and non-finite are separate reasons, as they already are for
    `core_loss.*` and `core_geometry.*`: one stable code cannot mean two things
    when it is triaged from a run manifest.
    """
    core = CoreMagneticProperties(
        path_length_m=0.1,
        volume_m3=volume,
        effective_area_m2=1e-4,
        al_value_nh=1250.0,
    )

    result = stored_energy_j(BIASED_FIELDS, BIASED_DENSITIES, core)

    assert result.state is ResultState.UNAVAILABLE
    assert result.code == code


def test_an_overflowing_energy_product_is_refused_not_reported() -> None:
    densities = FluxDensities(
        b_dc_t=0.0,
        b_min_t=0.0,
        b_max_t=1e308,
        b_ac_peak_t=5e307,
        b_peak_magnitude_t=1e308,
        notes=(),
    )
    fields = FieldStrengths(
        h_ac_peak_a_per_m=1e10,
        h_dc_a_per_m=0.0,
        h_min_a_per_m=-1e10,
        h_max_a_per_m=1e10,
    )

    result = stored_energy_j(fields, densities, CORE)

    assert result.state is ResultState.UNAVAILABLE
    assert result.code == DiagnosticCode.STORED_ENERGY_NOT_FINITE


def test_each_stored_energy_note_names_the_model_it_came_from() -> None:
    """Two branches, two honest statements. The integral is the real stored
    energy of the recorded curve; the linear form is exact for the linear
    permeability model that produced it -- and for that model it also equals
    0.5 * L * I_peak^2, so neither note claims to be optimistic.
    """
    assert "integral of H dB" in STORED_ENERGY_INTEGRATED_NOTE
    assert "recorded B-H" in STORED_ENERGY_INTEGRATED_NOTE
    assert "linear-permeability" in STORED_ENERGY_LINEAR_NOTE
    assert "exact" in STORED_ENERGY_LINEAR_NOTE


def test_the_zero_ripple_note_discloses_the_direction_of_its_error() -> None:
    """`core_loss_estimate` sets the convention: a substitution that biases the
    result states which way it biases it.
    """
    assert "optimistic" in ZERO_RIPPLE_NOTE
