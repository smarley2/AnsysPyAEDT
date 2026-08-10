from __future__ import annotations

from inductor_designer.domain.project import RequestedOutput
from inductor_designer.simulation.result_vocabulary import (
    DEVICE_SCOPE,
    SCALAR_QUANTITIES,
    convention_for,
    reason_code,
    unit_for,
    winding_scope,
)
from inductor_designer.simulation.run_contracts import CurrentConvention


def test_field_quantities_are_not_scalar_work() -> None:
    assert RequestedOutput.FLUX_DENSITY not in SCALAR_QUANTITIES
    assert RequestedOutput.CURRENT_DENSITY not in SCALAR_QUANTITIES
    assert RequestedOutput.RESISTANCE in SCALAR_QUANTITIES


def test_every_scalar_quantity_has_a_unit_and_a_convention() -> None:
    for quantity in SCALAR_QUANTITIES:
        assert unit_for(quantity).strip()
        assert isinstance(convention_for(quantity), CurrentConvention)


def test_units_are_si_and_exact() -> None:
    assert unit_for(RequestedOutput.RESISTANCE) == "ohm"
    assert unit_for(RequestedOutput.INDUCTANCE) == "H"
    assert unit_for(RequestedOutput.IMPEDANCE) == "ohm"
    assert unit_for(RequestedOutput.COPPER_LOSS) == "W"
    assert unit_for(RequestedOutput.CORE_LOSS) == "W"
    assert unit_for(RequestedOutput.TOTAL_LOSS) == "W"
    assert unit_for(RequestedOutput.MAGNETIC_ENERGY) == "J"
    assert unit_for(RequestedOutput.CONVERGENCE) == "percent"


def test_losses_are_reported_at_ac_rms_and_energy_at_ac_peak() -> None:
    """A loss is mean power over the cycle; stored energy is instantaneous."""
    assert convention_for(RequestedOutput.COPPER_LOSS) is CurrentConvention.AC_RMS
    assert convention_for(RequestedOutput.CORE_LOSS) is CurrentConvention.AC_RMS
    assert convention_for(RequestedOutput.TOTAL_LOSS) is CurrentConvention.AC_RMS
    assert convention_for(RequestedOutput.MAGNETIC_ENERGY) is CurrentConvention.AC_PEAK


def test_convergence_and_impedance_are_convention_free() -> None:
    assert convention_for(RequestedOutput.CONVERGENCE) is CurrentConvention.NOT_APPLICABLE
    assert convention_for(RequestedOutput.IMPEDANCE) is CurrentConvention.NOT_APPLICABLE


def test_scopes_and_reason_codes_are_stable_strings() -> None:
    assert winding_scope("w1") == "winding.w1"
    assert DEVICE_SCOPE == "device"
    assert reason_code(RequestedOutput.MATRICES, "not_exposed") == "matrices.not_exposed"
