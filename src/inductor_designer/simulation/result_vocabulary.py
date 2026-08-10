"""Units, scopes and conventions for the scalar Normalized Result Set.

One table, so a unit or a convention is never decided at a call site. Field
quantities are absent on purpose: they belong to M8c and the representative
cross sections design.
"""

from __future__ import annotations

from inductor_designer.domain.project import RequestedOutput
from inductor_designer.simulation.run_contracts import CurrentConvention

DEVICE_SCOPE = "device"

SCALAR_QUANTITIES: tuple[RequestedOutput, ...] = (
    RequestedOutput.RESISTANCE,
    RequestedOutput.INDUCTANCE,
    RequestedOutput.IMPEDANCE,
    RequestedOutput.MATRICES,
    RequestedOutput.COPPER_LOSS,
    RequestedOutput.CORE_LOSS,
    RequestedOutput.TOTAL_LOSS,
    RequestedOutput.MAGNETIC_ENERGY,
    RequestedOutput.CONVERGENCE,
)

# The field half, owned by M8c: reported per section, never per device.
FIELD_QUANTITIES: tuple[RequestedOutput, ...] = (
    RequestedOutput.FLUX_DENSITY,
    RequestedOutput.CURRENT_DENSITY,
)

# Quantities reported once per winding rather than once per device.
PER_WINDING_QUANTITIES: tuple[RequestedOutput, ...] = (
    RequestedOutput.RESISTANCE,
    RequestedOutput.INDUCTANCE,
    RequestedOutput.IMPEDANCE,
)

_UNITS: dict[RequestedOutput, str] = {
    RequestedOutput.RESISTANCE: "ohm",
    RequestedOutput.INDUCTANCE: "H",
    RequestedOutput.IMPEDANCE: "ohm",
    RequestedOutput.MATRICES: "ohm and H",
    RequestedOutput.COPPER_LOSS: "W",
    RequestedOutput.CORE_LOSS: "W",
    RequestedOutput.TOTAL_LOSS: "W",
    RequestedOutput.MAGNETIC_ENERGY: "J",
    RequestedOutput.CONVERGENCE: "percent",
    RequestedOutput.FLUX_DENSITY: "T",
    RequestedOutput.CURRENT_DENSITY: "A/m^2",
}

# A loss is the mean power over one cycle, so it belongs to the RMS current
# convention even though the solver is excited at peak (ADR 0006). Stored
# magnetic energy is an instantaneous peak-excitation quantity. Resistance,
# inductance and impedance are properties of the structure, not of a current
# amplitude, so they carry no convention.
_CONVENTIONS: dict[RequestedOutput, CurrentConvention] = {
    RequestedOutput.RESISTANCE: CurrentConvention.NOT_APPLICABLE,
    RequestedOutput.INDUCTANCE: CurrentConvention.NOT_APPLICABLE,
    RequestedOutput.IMPEDANCE: CurrentConvention.NOT_APPLICABLE,
    RequestedOutput.MATRICES: CurrentConvention.NOT_APPLICABLE,
    RequestedOutput.COPPER_LOSS: CurrentConvention.AC_RMS,
    RequestedOutput.CORE_LOSS: CurrentConvention.AC_RMS,
    RequestedOutput.TOTAL_LOSS: CurrentConvention.AC_RMS,
    RequestedOutput.MAGNETIC_ENERGY: CurrentConvention.AC_PEAK,
    RequestedOutput.CONVERGENCE: CurrentConvention.NOT_APPLICABLE,
    # A field value follows the excitation, which is peak (ADR 0006). A
    # DC-biased run overrides this to COMBINED at normalization time.
    RequestedOutput.FLUX_DENSITY: CurrentConvention.AC_PEAK,
    RequestedOutput.CURRENT_DENSITY: CurrentConvention.AC_PEAK,
}

NOT_EXPOSED = "not_exposed"
NOT_REPORTED = "not_reported"
NOT_SOLVED = "not_solved"


def unit_for(quantity: RequestedOutput) -> str:
    return _UNITS[quantity]


def convention_for(quantity: RequestedOutput) -> CurrentConvention:
    return _CONVENTIONS[quantity]


def winding_scope(winding_id: str) -> str:
    return f"winding.{winding_id}"


def core_section_scope(section_id: str) -> str:
    return f"core.section.{section_id}"


def conductor_section_scope(winding_id: str, section_id: str) -> str:
    return f"winding.{winding_id}.section.{section_id}"


def reason_code(quantity: RequestedOutput, reason: str) -> str:
    return f"{quantity.value}.{reason}"
