from __future__ import annotations

import math

import pytest

from inductor_designer.simulation.preliminary_contracts import (
    DiagnosticCode,
    PreliminaryValue,
)
from inductor_designer.simulation.winding_estimate import (
    COPPER_ALPHA_20_PER_C,
    COPPER_RHO_20_OHM_M,
    CurrentDensities,
    WireLoss,
    conductor_area_m2,
    current_densities,
    wire_resistance_and_loss,
)


def test_conductor_area_is_the_bare_circle_area() -> None:
    assert math.isclose(conductor_area_m2(0.001), math.pi * 0.001**2 / 4.0)


def test_current_densities_use_the_copper_area() -> None:
    area = conductor_area_m2(0.001)

    result = current_densities(area, ac_rms_current_a=2.0, dc_current_a=5.0)

    assert isinstance(result, CurrentDensities)
    assert math.isclose(result.j_ac_rms_a_per_m2, 2.0 / area)
    assert math.isclose(result.j_ac_peak_a_per_m2, math.sqrt(2.0) * 2.0 / area)
    assert math.isclose(result.j_dc_a_per_m2, 5.0 / area)


def test_zero_currents_give_zero_densities_not_a_diagnostic() -> None:
    result = current_densities(conductor_area_m2(0.001), 0.0, 0.0)

    assert result.j_ac_rms_a_per_m2 == 0.0
    assert result.j_dc_a_per_m2 == 0.0


def test_non_positive_diameter_is_rejected_at_the_boundary() -> None:
    with pytest.raises(ValueError, match="positive"):
        conductor_area_m2(0.0)


def test_copper_constants_match_the_specification_exactly() -> None:
    assert COPPER_RHO_20_OHM_M == 1.7241e-8
    assert COPPER_ALPHA_20_PER_C == 0.00393


def test_resistance_at_twenty_degrees_uses_rho_twenty_directly() -> None:
    area = conductor_area_m2(0.001)

    result = wire_resistance_and_loss(area, 2.0, 20.0, 1.0, 0.0)

    assert isinstance(result, WireLoss)
    assert math.isclose(result.resistance_ohm, COPPER_RHO_20_OHM_M * 2.0 / area)


def test_resistance_rises_linearly_with_winding_temperature() -> None:
    area = conductor_area_m2(0.001)

    result = wire_resistance_and_loss(area, 2.0, 100.0, 1.0, 0.0)

    expected_rho = COPPER_RHO_20_OHM_M * (1.0 + COPPER_ALPHA_20_PER_C * 80.0)
    assert isinstance(result, WireLoss)
    assert math.isclose(result.resistance_ohm, expected_rho * 2.0 / area)


def test_loss_sums_ac_rms_and_dc_contributions() -> None:
    area = conductor_area_m2(0.001)

    result = wire_resistance_and_loss(area, 2.0, 20.0, 3.0, 4.0)

    assert isinstance(result, WireLoss)
    assert math.isclose(result.loss_w, result.resistance_ohm * (9.0 + 16.0))


def test_loss_reports_its_exclusions() -> None:
    result = wire_resistance_and_loss(conductor_area_m2(0.001), 2.0, 20.0, 1.0, 0.0)

    assert isinstance(result, WireLoss)
    joined = " ".join(result.notes)
    assert "DC-resistance wire-loss estimate" in joined
    assert "connector" in joined
    assert "lead" in joined


@pytest.mark.parametrize("temperature", [9.9, 100.1, -40.0, 150.0])
def test_temperature_outside_the_validated_range_is_not_extrapolated(
    temperature: float,
) -> None:
    result = wire_resistance_and_loss(
        conductor_area_m2(0.001), 2.0, temperature, 1.0, 0.0
    )

    assert isinstance(result, PreliminaryValue)
    assert result.code == DiagnosticCode.WIRE_LOSS_TEMPERATURE_OUT_OF_RANGE
    assert "10" in str(result.message)
    assert "100" in str(result.message)


@pytest.mark.parametrize("temperature", [10.0, 100.0])
def test_the_validated_range_is_inclusive(temperature: float) -> None:
    result = wire_resistance_and_loss(
        conductor_area_m2(0.001), 2.0, temperature, 1.0, 0.0
    )

    assert isinstance(result, WireLoss)


def test_missing_wire_length_is_a_geometry_diagnostic() -> None:
    result = wire_resistance_and_loss(conductor_area_m2(0.001), 0.0, 20.0, 1.0, 0.0)

    assert isinstance(result, PreliminaryValue)
    assert result.code == DiagnosticCode.WIRE_LOSS_NO_GEOMETRY
