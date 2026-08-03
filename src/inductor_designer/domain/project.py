from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite

from inductor_designer.domain.catalog_records import CoreRecord
from inductor_designer.domain.winding import CurrentDirection, WindingDefinition
from inductor_designer.materials.identity import MaterialRef
from inductor_designer.materials.records import MaterialRecord, SeriesKind


@dataclass(frozen=True, slots=True)
class CoreOverride:
    field: str
    value: float
    reason: str


@dataclass(frozen=True, slots=True)
class CatalogCoreSelection:
    part_number: str
    snapshot: CoreRecord
    overrides: tuple[CoreOverride, ...]

    def __post_init__(self) -> None:
        if self.part_number != self.snapshot.part_number:
            raise ValueError(
                "CatalogCoreSelection part_number must match snapshot.part_number"
            )


@dataclass(frozen=True, slots=True)
class ManualCoreSelection:
    outer_diameter_m: float
    inner_diameter_m: float
    height_m: float
    corner_radius_m: float

    def __post_init__(self) -> None:
        # Finiteness only: ordering and positivity are reported as diagnostics by
        # `_validate_core` and `resolve_finished_core`. NaN is what those checks
        # cannot see, because every comparison against it is False.
        for name, value in (
            ("outer_diameter_m", self.outer_diameter_m),
            ("inner_diameter_m", self.inner_diameter_m),
            ("height_m", self.height_m),
            ("corner_radius_m", self.corner_radius_m),
        ):
            if not isfinite(value):
                raise ValueError(f"ManualCoreSelection {name} must be finite")


CoreSelection = CatalogCoreSelection | ManualCoreSelection


class MeshIntent(str, Enum):
    STANDARD = "standard"


class RequestedOutput(str, Enum):
    RESISTANCE = "resistance"
    INDUCTANCE = "inductance"
    IMPEDANCE = "impedance"
    MATRICES = "matrices"
    COPPER_LOSS = "copper-loss"
    CORE_LOSS = "core-loss"
    TOTAL_LOSS = "total-loss"
    MAGNETIC_ENERGY = "magnetic-energy"
    CONVERGENCE = "convergence"
    FLUX_DENSITY = "flux-density"
    CURRENT_DENSITY = "current-density"


@dataclass(frozen=True, slots=True)
class MaterialRevisionSelection:
    ref: MaterialRef
    revision_id: str
    snapshot: MaterialRecord
    bh_series_id: str | None = None

    def __post_init__(self) -> None:
        if not self.revision_id.strip():
            raise ValueError("MaterialRevisionSelection revision_id cannot be blank")
        if self.ref != self.snapshot.ref:
            raise ValueError("MaterialRevisionSelection ref must match snapshot.ref")
        if self.revision_id != self.snapshot.revision_id:
            raise ValueError(
                "MaterialRevisionSelection revision_id must match snapshot.revision_id"
            )
        if self.bh_series_id is None:
            return
        if not self.bh_series_id.strip():
            raise ValueError("MaterialRevisionSelection bh_series_id cannot be blank")
        selected = next(
            (series for series in self.snapshot.series if series.series_id == self.bh_series_id),
            None,
        )
        if selected is None:
            raise ValueError(
                "MaterialRevisionSelection bh_series_id must name a series in snapshot"
            )
        if selected.kind is not SeriesKind.BH_CURVE:
            raise ValueError(
                "MaterialRevisionSelection bh_series_id must name a B-H curve"
            )


@dataclass(frozen=True, slots=True)
class Design:
    core: CoreSelection | None
    windings: tuple[WindingDefinition, ...]
    core_material: MaterialRevisionSelection | None
    manual_material_compatibility_acknowledged: bool


@dataclass(frozen=True, slots=True)
class WindingOperatingPoint:
    winding_id: str
    ac_rms_current_a: float
    ac_phase_deg: float
    dc_current_a: float
    current_direction: CurrentDirection

    def __post_init__(self) -> None:
        if not self.winding_id.strip():
            raise ValueError("WindingOperatingPoint winding_id cannot be blank")
        for field, value in (
            ("ac_rms_current_a", self.ac_rms_current_a),
            ("ac_phase_deg", self.ac_phase_deg),
            ("dc_current_a", self.dc_current_a),
        ):
            if not isfinite(value):
                raise ValueError(f"WindingOperatingPoint {field} must be finite")
        if self.ac_rms_current_a < 0:
            raise ValueError("WindingOperatingPoint ac_rms_current_a cannot be negative")
        if self.dc_current_a < 0:
            raise ValueError("WindingOperatingPoint dc_current_a cannot be negative")


@dataclass(frozen=True, slots=True)
class OperatingPoint:
    frequency_hz: float
    winding_temperature_c: float = 20.0
    core_temperature_c: float = 25.0
    windings: tuple[WindingOperatingPoint, ...] = ()

    def __post_init__(self) -> None:
        for field, value in (
            ("frequency_hz", self.frequency_hz),
            ("winding_temperature_c", self.winding_temperature_c),
            ("core_temperature_c", self.core_temperature_c),
        ):
            if not isfinite(value):
                raise ValueError(f"OperatingPoint {field} must be finite")
        if self.frequency_hz <= 0:
            raise ValueError("OperatingPoint frequency_hz must be positive")


@dataclass(frozen=True, slots=True)
class SimulationRecipe:
    mesh_intent: MeshIntent
    maximum_passes: int
    percent_error: float
    requested_outputs: tuple[RequestedOutput, ...]

    def __post_init__(self) -> None:
        if not isfinite(self.maximum_passes):
            raise ValueError("SimulationRecipe maximum_passes must be finite")
        if self.maximum_passes <= 0:
            raise ValueError("SimulationRecipe maximum_passes must be positive")
        if not isfinite(self.percent_error):
            raise ValueError("SimulationRecipe percent_error must be finite")
        if self.percent_error <= 0:
            raise ValueError("SimulationRecipe percent_error must be positive")


@dataclass(frozen=True, slots=True)
class InductorProject:
    project_id: str
    name: str
    description: str
    design: Design
    operating_point: OperatingPoint
    simulation_recipe: SimulationRecipe

    def __post_init__(self) -> None:
        if not self.project_id.strip():
            raise ValueError("InductorProject project_id cannot be blank")
        if not self.name.strip():
            raise ValueError("InductorProject name cannot be blank")
