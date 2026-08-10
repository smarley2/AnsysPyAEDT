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
    STORED_ENERGY_NOTE,
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


@pytest.mark.parametrize("area", [0.0, -1e-4, float("inf"), float("nan")])
def test_an_unusable_area_refuses_al_instead_of_dividing(area: float) -> None:
    core = CoreMagneticProperties(
        path_length_m=0.1, volume_m3=1e-5, effective_area_m2=area, al_value_nh=1250.0
    )

    result = core_inductance(BIASED_FIELDS, BIASED_DENSITIES, core)

    assert isinstance(result, PreliminaryValue)
    assert result.code == DiagnosticCode.INDUCTANCE_NON_POSITIVE_AREA


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
    result = stored_energy_j(BIASED_FIELDS, BIASED_DENSITIES, CORE)

    assert result.state is ResultState.ESTIMATED
    # 0.5 * 0.5 T * 300 A/m * 1e-5 m^3
    assert result.value == pytest.approx(7.5e-4)
    assert STORED_ENERGY_NOTE in result.notes


def test_stored_energy_uses_the_larger_field_magnitude_of_the_excursion() -> None:
    """A bias smaller than the ripple drives the field negative; the peak is
    then |H_min|, and pairing it with |B| keeps both factors at one instant.
    """
    fields = FieldStrengths(
        h_ac_peak_a_per_m=300.0,
        h_dc_a_per_m=100.0,
        h_min_a_per_m=-200.0,
        h_max_a_per_m=400.0,
    )
    densities = FluxDensities(
        b_dc_t=0.2,
        b_min_t=-0.4,
        b_max_t=0.5,
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


@pytest.mark.parametrize("volume", [0.0, -1e-5, float("inf"), float("nan")])
def test_an_unusable_volume_refuses_stored_energy(volume: float) -> None:
    core = CoreMagneticProperties(
        path_length_m=0.1,
        volume_m3=volume,
        effective_area_m2=1e-4,
        al_value_nh=1250.0,
    )

    result = stored_energy_j(BIASED_FIELDS, BIASED_DENSITIES, core)

    assert result.state is ResultState.UNAVAILABLE
    assert result.code == DiagnosticCode.STORED_ENERGY_NON_POSITIVE_VOLUME
