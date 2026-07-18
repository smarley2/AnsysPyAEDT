from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from inductor_designer.domain.catalog_records import CoreFamily, CoreRecord, ReviewStatus
from inductor_designer.geometry.naming import sanitize_identifier
from inductor_designer.geometry.primitives import PathSegment
from inductor_designer.geometry.terminals import TerminalDisk
from inductor_designer.materials.fitting import MaterialFitError, mean_relative_permeability
from inductor_designer.materials.records import (
    MaterialRecord,
    MaterialStatus,
    SeriesKind,
    SteinmetzFit,
)
from inductor_designer.simulation.capabilities import DcBiasDecision, DcBiasStrategy

SOLUTION_TYPE = "EddyCurrent"
SOLUTION_TYPE_DC = "AC Magnetic with DC"
DESIGN_NAME = "Inductor3D"
SETUP_NAME = "Setup1"
MATRIX_NAME = "Matrix1"
COPPER_MATERIAL = "copper"
REGION_PADDING_PERCENT = 100.0


class PlanBuildError(ValueError):
    def __init__(self, issues: tuple[str, ...]) -> None:
        super().__init__("; ".join(issues))
        self.issues = issues


class Polarity(str, Enum):
    POSITIVE = "Positive"
    NEGATIVE = "Negative"


@dataclass(frozen=True, slots=True)
class MaterialSpec:
    """Solver-independent magnetic material properties."""

    name: str
    relative_permeability: float
    conductivity_s_per_m: float
    draft: bool
    bh_curve: tuple[tuple[float, float], ...] = ()
    steinmetz: SteinmetzFit | None = None
    material_revision: str | None = None


@dataclass(frozen=True, slots=True)
class TerminalPlan:
    name: str
    disk: TerminalDisk
    polarity: Polarity


@dataclass(frozen=True, slots=True)
class TurnPlan:
    name: str
    segments: tuple[PathSegment, ...]
    bare_diameter_m: float
    terminal: TerminalPlan


@dataclass(frozen=True, slots=True)
class WindingGroupPlan:
    name: str
    winding_id: str
    is_solid: bool
    current_peak_a: float
    phase_deg: float
    dc_current_a: float
    turns: tuple[TurnPlan, ...]


@dataclass(frozen=True, slots=True)
class CorePlan:
    name: str
    profile: tuple[PathSegment, ...]
    material: MaterialSpec


@dataclass(frozen=True, slots=True)
class RegionPlan:
    padding_percent: float


@dataclass(frozen=True, slots=True)
class MeshPlan:
    conductor_max_length_m: float
    core_max_length_m: float


@dataclass(frozen=True, slots=True)
class SetupPlan:
    name: str
    frequency_hz: float
    maximum_passes: int
    percent_error: float


@dataclass(frozen=True, slots=True)
class ReportPlan:
    name: str
    expression: str


@dataclass(frozen=True, slots=True)
class Maxwell3dDesignPlan:
    design_name: str
    solution_type: str
    core: CorePlan
    windings: tuple[WindingGroupPlan, ...]
    region: RegionPlan
    mesh: MeshPlan
    setup: SetupPlan
    matrix_name: str
    reports: tuple[ReportPlan, ...]
    notes: tuple[str, ...]
    dc_bias: DcBiasDecision | None = None


def core_material_spec(record: CoreRecord) -> MaterialSpec:
    """Milestone 3 material model: powder grade = linear relative permeability.

    Real property data (B-H curves, core loss) arrives with Material Studio in
    Milestone 5; ferrites stay unsupported until then.
    """
    if record.family is not CoreFamily.POWDER_TOROID:
        raise PlanBuildError(
            (
                f"Core family {record.family.value!r} has no Milestone 3 material model; "
                "only powder toroids export.",
            )
        )
    try:
        mu = float(record.material.grade)
    except ValueError as error:
        raise PlanBuildError(
            (f"Powder grade {record.material.grade!r} is not a numeric permeability.",)
        ) from error
    if mu <= 0.0:
        raise PlanBuildError((f"Powder grade {record.material.grade!r} must be positive.",))
    name = sanitize_identifier(
        f"{record.material.manufacturer}_{record.material.name}_{record.material.grade}"
    )
    return MaterialSpec(
        name=name,
        relative_permeability=mu,
        conductivity_s_per_m=0.0,
        draft=record.review_status is not ReviewStatus.REVIEWED,
    )


def material_spec_from_material_record(
    core_record: CoreRecord, material: MaterialRecord
) -> MaterialSpec:
    """Build solver material data from an approved project snapshot."""
    if material.status is not MaterialStatus.APPROVED:
        raise PlanBuildError(("Only approved material records can be exported.",))
    if material.ref != core_record.material:
        raise PlanBuildError(("Material record identity does not match the selected core.",))

    bh_series = tuple(
        series for series in material.series if series.kind is SeriesKind.BH_CURVE
    )
    if len(bh_series) > 1:
        raise PlanBuildError(
            ("Approved material has multiple B-H series; select one condition before export.",)
        )
    bh_points = (
        tuple((point.x, point.y) for point in bh_series[0].points) if bh_series else ()
    )
    if material.relative_permeability is not None:
        relative_permeability = material.relative_permeability
    else:
        try:
            relative_permeability = mean_relative_permeability(bh_points)
        except MaterialFitError as error:
            raise PlanBuildError(
                ("Approved material requires scalar permeability or usable B-H points.",)
            ) from error

    name = sanitize_identifier(
        f"{material.ref.manufacturer}_{material.ref.name}_{material.ref.grade}"
        f"_r{material.revision_id}"
    )
    return MaterialSpec(
        name=name,
        relative_permeability=relative_permeability,
        conductivity_s_per_m=0.0,
        draft=False,
        bh_curve=tuple(
            (flux_density, field_strength) for field_strength, flux_density in bh_points
        ),
        steinmetz=material.steinmetz,
        material_revision=material.revision_id,
    )


def dc_bias_notes(
    decision: DcBiasDecision | None,
    dc_requested: bool,
    *,
    nonlinear_material: bool = False,
) -> tuple[str, ...]:
    """Human-visible DC-bias treatment notes for plans and manifests."""
    if not dc_requested:
        return ()
    if decision is None:
        return ("DC operating currents are recorded but not applied; no capability decision.",)
    if decision.strategy is DcBiasStrategy.NATIVE_INCLUDE_DC_FIELDS:
        notes = [
            "DC operating point applied natively via the AC Magnetic with DC solution type."
        ]
        if not nonlinear_material:
            notes.append(
                "Core material is linear until Milestone 5; DC bias has no incremental "
                "effect on a linear material."
            )
        return tuple(notes)
    if decision.strategy is DcBiasStrategy.MAGNETOSTATIC_INCREMENTAL_FALLBACK:
        return (
            "DC operating currents are recorded but not applied; the 2024 R2 "
            "Magnetostatic fallback is deferred until a 2024 R2 installation exists.",
        )
    return (f"DC operating currents are recorded but not applied: {decision.reason}",)
