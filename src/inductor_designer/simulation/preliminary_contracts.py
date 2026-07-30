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
    FLUX_DENSITY_NO_BH_SERIES_FOR_TEMPERATURE = (
        "flux_density.no_bh_series_for_temperature"
    )
    FLUX_DENSITY_NO_SUPPORTED_MODEL = "flux_density.no_supported_model"
    FLUX_DENSITY_FIELD_OUTSIDE_BH_RANGE = "flux_density.field_outside_bh_range"
    FLUX_DENSITY_NON_POSITIVE_PATH_LENGTH = "flux_density.non_positive_path_length"

    CURRENT_DENSITY_NO_CONDUCTOR = "current_density.no_conductor"

    WIRE_LOSS_NO_GEOMETRY = "wire_loss.no_geometry"
    WIRE_LOSS_TEMPERATURE_OUT_OF_RANGE = "wire_loss.temperature_out_of_range"

    CORE_LOSS_NO_FLUX_DENSITY = "core_loss.no_flux_density"
    CORE_LOSS_NON_POSITIVE_FREQUENCY = "core_loss.non_positive_frequency"
    CORE_LOSS_NON_POSITIVE_VOLUME = "core_loss.non_positive_volume"
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
