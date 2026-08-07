from __future__ import annotations

import pytest

from inductor_designer.simulation.preliminary_contracts import (
    CoreMagneticProperties,
    DiagnosticCode,
    PreliminaryValue,
    ResultState,
    estimated,
    invalid,
    unavailable,
)


def test_estimated_value_carries_a_number_and_no_diagnostic() -> None:
    value = estimated(1.25, notes=("linear permeability approximation",))

    assert value.state is ResultState.ESTIMATED
    assert value.value == 1.25
    assert value.code is None
    assert value.message is None
    assert value.notes == ("linear permeability approximation",)


def test_unavailable_value_carries_a_code_and_message_but_no_number() -> None:
    value = unavailable(
        DiagnosticCode.CORE_LOSS_NO_LOSS_DATA_FOR_DC_BIAS,
        "No loss data recorded at 1800 A/m DC bias; recorded bias: 0 A/m.",
    )

    assert value.state is ResultState.UNAVAILABLE
    assert value.value is None
    assert value.code == "core_loss.no_loss_data_for_dc_bias"
    assert "1800 A/m" in str(value.message)


def test_invalid_value_is_distinct_from_unavailable() -> None:
    value = invalid(
        DiagnosticCode.WIRE_LOSS_TEMPERATURE_OUT_OF_RANGE,
        "Winding temperature 150 C is outside 10 C through 100 C.",
    )

    assert value.state is ResultState.INVALID
    assert value.value is None


def test_estimated_requires_a_finite_number() -> None:
    with pytest.raises(ValueError, match="finite"):
        estimated(float("nan"))


def test_a_diagnostic_state_requires_both_code_and_message() -> None:
    with pytest.raises(ValueError, match="code and message"):
        PreliminaryValue(state=ResultState.UNAVAILABLE, value=None, code=None, message=None)


def test_every_diagnostic_code_is_a_dotted_lowercase_string() -> None:
    codes = [
        getattr(DiagnosticCode, name)
        for name in dir(DiagnosticCode)
        if name.isupper()
    ]

    assert codes, "DiagnosticCode must define codes"
    for code in codes:
        assert code == code.lower(), code
        quantity, _, reason = code.partition(".")
        assert quantity and reason, code
        assert " " not in code, code
    assert len(set(codes)) == len(codes), "diagnostic codes must be unique"


def test_core_magnetic_properties_allow_every_number_including_non_finite() -> None:
    """Bad geometry is a diagnosed condition, never a constructor error.

    `flux_density.non_positive_path_length`, `flux_density.core_path_not_finite`,
    `core_loss.non_positive_volume`, and `core_loss.non_finite_volume` all report
    these, so raising here would replace a user-facing diagnostic with a crash
    inside the Preliminary controller's constructor.
    """
    zero = CoreMagneticProperties(path_length_m=0.0, volume_m3=0.0)
    overflowed = CoreMagneticProperties(
        path_length_m=float("inf"), volume_m3=float("inf")
    )

    assert zero.path_length_m == 0.0
    assert zero.notes == ()
    assert overflowed.volume_m3 == float("inf")
