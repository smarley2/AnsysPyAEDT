"""Result states and stable diagnostic codes for preliminary estimates.

Every quantity is reported independently: a missing loss curve makes core loss
unavailable without disturbing flux density, current density, or wire loss.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import isfinite


class ResultState(str, Enum):
    """Exactly the three states specification section 4.3 allows."""

    ESTIMATED = "estimated"
    UNAVAILABLE = "unavailable"
    INVALID = "invalid"


class DiagnosticCode:
    """Stable `<quantity>.<reason>` codes.

    These strings appear in the UI, in logs, and in M7b run manifests. Never
    reuse or repurpose one: add a new code instead.
    """

    FLUX_DENSITY_NO_CORE_SELECTED = "flux_density.no_core_selected"
    FLUX_DENSITY_NO_MATERIAL_SELECTED = "flux_density.no_material_selected"
    FLUX_DENSITY_MANUAL_COMPATIBILITY_UNACKNOWLEDGED = (
        "flux_density.manual_compatibility_unacknowledged"
    )
    FLUX_DENSITY_NO_BH_SERIES_FOR_TEMPERATURE = (
        "flux_density.no_bh_series_for_temperature"
    )
    FLUX_DENSITY_NO_SUPPORTED_MODEL = "flux_density.no_supported_model"
    FLUX_DENSITY_FIELD_OUTSIDE_BH_RANGE = "flux_density.field_outside_bh_range"
    FLUX_DENSITY_NON_POSITIVE_PATH_LENGTH = "flux_density.non_positive_path_length"
    FLUX_DENSITY_CORE_PATH_NOT_FINITE = "flux_density.core_path_not_finite"

    CURRENT_DENSITY_NO_CONDUCTOR = "current_density.no_conductor"

    INDUCTANCE_NO_FLUX_DENSITY = "inductance.no_flux_density"
    INDUCTANCE_NO_EXCITATION = "inductance.no_excitation"
    INDUCTANCE_NON_POSITIVE_PERMEABILITY = "inductance.non_positive_permeability"
    INDUCTANCE_NON_POSITIVE_GEOMETRY = "inductance.non_positive_geometry"
    INDUCTANCE_NON_FINITE_GEOMETRY = "inductance.non_finite_geometry"
    INDUCTANCE_NOT_FINITE = "inductance.not_finite"

    # The mode a pair's mutual subtracts from is leakage inductance alone, and
    # the lumped effective-core model has no leakage path to compute it from.
    COUPLING_NO_LEAKAGE_PATH = "coupling.no_leakage_path"

    AL_CHECK_NO_CATALOG_AL = "al_check.no_catalog_al"
    AL_CHECK_NOT_FINITE = "al_check.not_finite"

    STORED_ENERGY_NO_FLUX_DENSITY = "stored_energy.no_flux_density"
    STORED_ENERGY_NON_POSITIVE_VOLUME = "stored_energy.non_positive_volume"
    STORED_ENERGY_NON_FINITE_VOLUME = "stored_energy.non_finite_volume"
    STORED_ENERGY_NOT_FINITE = "stored_energy.not_finite"
    STORED_ENERGY_FLUX_OUTSIDE_BH_RANGE = "stored_energy.flux_outside_bh_range"
    STORED_ENERGY_NON_MONOTONIC_BH = "stored_energy.non_monotonic_bh"

    # The effective-geometry echo is reported independently of flux density, so
    # it needs its own reasons rather than borrowing the flux-density or
    # core-loss ones.
    CORE_GEOMETRY_NON_POSITIVE = "core_geometry.non_positive"
    CORE_GEOMETRY_NOT_FINITE = "core_geometry.not_finite"
    CORE_GEOMETRY_NO_CORE_SELECTED = "core_geometry.no_core_selected"

    WIRE_LOSS_NO_GEOMETRY = "wire_loss.no_geometry"
    WIRE_LOSS_TEMPERATURE_OUT_OF_RANGE = "wire_loss.temperature_out_of_range"

    CORE_LOSS_NO_FLUX_DENSITY = "core_loss.no_flux_density"
    CORE_LOSS_NON_POSITIVE_FREQUENCY = "core_loss.non_positive_frequency"
    CORE_LOSS_NON_POSITIVE_VOLUME = "core_loss.non_positive_volume"
    CORE_LOSS_NON_FINITE_VOLUME = "core_loss.non_finite_volume"
    CORE_LOSS_NO_LOSS_DATA_FOR_TEMPERATURE = "core_loss.no_loss_data_for_temperature"
    CORE_LOSS_NO_LOSS_DATA_FOR_DC_BIAS = "core_loss.no_loss_data_for_dc_bias"
    CORE_LOSS_FLUX_OUTSIDE_LOSS_RANGE = "core_loss.flux_outside_loss_range"
    CORE_LOSS_FREQUENCY_OUTSIDE_FIT_ENVELOPE = (
        "core_loss.frequency_outside_fit_envelope"
    )
    CORE_LOSS_NO_LOSS_MODEL = "core_loss.no_loss_model"
    CORE_LOSS_FIT_SOURCES_MISMATCH_CONDITION = (
        "core_loss.fit_sources_mismatch_condition"
    )

    TOTAL_LOSS_INCOMPLETE = "total_loss.incomplete"


@dataclass(frozen=True, slots=True)
class CoreMagneticProperties:
    """The core properties the estimator reads, and how they were obtained.

    A catalog core supplies the manufacturer's effective values. A Manual core
    has no record, so the caller computes them from the entered dimensions and
    says so in `notes`. Keeping this separate from `CoreRecord` means no caller
    ever has to fabricate manufacturer provenance to get an estimate.

    `al_value_nh` is None exactly when the core has no manufacturer inductance
    factor, which is the Manual-core case. Neither it nor the effective area
    has a default: a default would let a caller silently omit the area and get
    an Unavailable A_L instead of a construction error.
    """

    path_length_m: float
    volume_m3: float
    effective_area_m2: float
    al_value_nh: float | None
    #: The gap in the flux path, referred to `effective_area_m2`, or 0.0 for
    #: an ungapped core -- which is every core this application handled before
    #: the E-core family. It defaults to zero so no existing caller changes
    #: and no existing number moves; a non-zero value switches the estimate
    #: from `H = NI/l` to the loadline `NI = H*l_iron + (B/mu_0)*l_gap`,
    #: because with a gap most of the ampere-turns drop across it.
    gap_length_m: float = 0.0
    notes: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class PreliminaryValue:
    """One reported quantity in exactly one state."""

    state: ResultState
    value: float | None
    code: str | None = None
    message: str | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.state is ResultState.ESTIMATED:
            if self.value is None or not isfinite(self.value):
                raise ValueError("an estimated value must be a finite number")
            if self.code is not None or self.message is not None:
                raise ValueError("an estimated value carries no diagnostic")
            return
        if self.value is not None:
            raise ValueError(f"a {self.state.value} value carries no number")
        if not self.code or not self.message:
            raise ValueError(
                f"a {self.state.value} value requires both code and message"
            )


def estimated(value: float, notes: tuple[str, ...] = ()) -> PreliminaryValue:
    return PreliminaryValue(state=ResultState.ESTIMATED, value=value, notes=notes)


def unavailable(code: str, message: str) -> PreliminaryValue:
    return PreliminaryValue(
        state=ResultState.UNAVAILABLE, value=None, code=code, message=message
    )


def invalid(code: str, message: str) -> PreliminaryValue:
    return PreliminaryValue(
        state=ResultState.INVALID, value=None, code=code, message=message
    )
