from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from inductor_designer.domain.project import (
    MeshIntent,
    OperatingPoint,
    RequestedOutput,
)
from inductor_designer.domain.winding import CurrentDirection
from inductor_designer.materials.identity import MaterialRef


class RunBackend(str, Enum):
    MAXWELL_3D = "maxwell-3d"
    MAXWELL_2D = "maxwell-2d"
    FEMM = "femm"


class RunMode(str, Enum):
    GENERATE_ONLY = "generate-only"
    GENERATE_AND_SOLVE = "generate-and-solve"


class RunStatus(str, Enum):
    PLANNED = "planned"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StageStatus(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class DimensionalRepresentation(str, Enum):
    THREE_DIMENSIONAL = "three-dimensional"
    EQUIVALENT_CROSS_SECTION = "equivalent-cross-section"


@dataclass(frozen=True, slots=True)
class RunRequest:
    backend: RunBackend
    mode: RunMode
    confirm_geometry_only: bool = False


@dataclass(frozen=True, slots=True)
class EffectiveWindingInput:
    winding_id: str
    ac_rms_current_a: float
    ac_peak_current_a: float
    phase_deg: float
    dc_current_a: float
    current_direction: CurrentDirection


def effective_winding_inputs(
    operating_point: OperatingPoint,
) -> tuple[EffectiveWindingInput, ...]:
    return tuple(
        EffectiveWindingInput(
            winding_id=item.winding_id,
            ac_rms_current_a=item.ac_rms_current_a,
            ac_peak_current_a=item.ac_rms_current_a * math.sqrt(2.0),
            phase_deg=item.ac_phase_deg,
            dc_current_a=item.dc_current_a,
            current_direction=item.current_direction,
        )
        for item in operating_point.windings
    )


@dataclass(frozen=True, slots=True)
class ManifestMaterialState:
    resolved: bool
    ref: MaterialRef | None
    revision_id: str | None
    bh_series_id: str | None
    manual_compatibility_acknowledged: bool


@dataclass(frozen=True, slots=True)
class ManifestStage:
    name: str
    status: StageStatus
    diagnostic: str


@dataclass(frozen=True, slots=True)
class ManifestArtifact:
    kind: str
    path: str


class ResultAvailability(str, Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


class CurrentConvention(str, Enum):
    NOT_APPLICABLE = "not-applicable"
    AC_RMS = "ac-rms"
    AC_PEAK = "ac-peak"
    DC = "dc"
    COMBINED = "combined"


ResultQuantity = RequestedOutput


@dataclass(frozen=True, slots=True)
class ComplexValue:
    real: float
    imaginary: float


@dataclass(frozen=True, slots=True)
class MatrixValue:
    row_labels: tuple[str, ...]
    column_labels: tuple[str, ...]
    values: tuple[tuple[float | ComplexValue, ...], ...]


NormalizedValue = float | ComplexValue | MatrixValue


@dataclass(frozen=True, slots=True)
class NormalizedQuantity:
    quantity: ResultQuantity
    scope: str
    availability: ResultAvailability
    value: NormalizedValue | None
    unit: str | None
    current_convention: CurrentConvention
    approximation: str | None
    reason: str | None
    provenance: str | None

    def __post_init__(self) -> None:
        if self.availability is ResultAvailability.AVAILABLE:
            if (
                self.value is None
                or self.unit is None
                or not self.unit.strip()
                or self.provenance is None
                or not self.provenance.strip()
                or self.reason is not None
            ):
                raise ValueError(
                    "available result requires value, unit, and provenance without reason"
                )
        elif self.value is not None or self.reason is None or not self.reason.strip():
            raise ValueError("unavailable result requires no value and a nonblank reason")


@dataclass(frozen=True, slots=True)
class NormalizedResultSet:
    run_id: str
    backend: RunBackend
    quantities: tuple[NormalizedQuantity, ...]


@dataclass(frozen=True, slots=True)
class RunManifest:
    run_id: str
    project_id: str
    project_schema_version: int
    backend: RunBackend
    mode: RunMode
    dimensional_representation: DimensionalRepresentation
    frequency_hz: float
    winding_temperature_c: float
    core_temperature_c: float
    windings: tuple[EffectiveWindingInput, ...]
    material: ManifestMaterialState
    mesh_intent: MeshIntent
    maximum_passes: int
    percent_error: float
    requested_outputs: tuple[RequestedOutput, ...]
    geometry_only: bool
    application_version: str
    solver_version: str | None
    adapter_version: str | None
    warnings: tuple[str, ...]
    stages: tuple[ManifestStage, ...]
    status: RunStatus
    diagnostics: tuple[str, ...]
    artifacts: tuple[ManifestArtifact, ...]
    results: NormalizedResultSet | None

    def __post_init__(self) -> None:
        if self.geometry_only and (
            self.backend is not RunBackend.MAXWELL_3D
            or self.mode is not RunMode.GENERATE_ONLY
            or self.material.resolved
            or self.results is not None
        ):
            raise ValueError(
                "Geometry-Only manifest requires unresolved Maxwell 3D Generate Only "
                "without results"
            )
        if self.status is RunStatus.SUCCEEDED and not self.artifacts:
            raise ValueError("succeeded manifest requires at least one artifact")
        if self.results is not None and self.results.backend is not self.backend:
            raise ValueError("result backend must match manifest backend")
