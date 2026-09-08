from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from inductor_designer.domain.winding import (
    CurrentDirection,
    WindingDefinition,
    mmf_sign,
)
from inductor_designer.geometry.naming import sanitize_identifier
from inductor_designer.geometry.primitives import PathSegment
from inductor_designer.geometry.toroid.terminals import TerminalDisk
from inductor_designer.materials.fitting import MaterialFitError, mean_relative_permeability
from inductor_designer.materials.identity import MaterialRef
from inductor_designer.materials.records import (
    MaterialRecord,
    MaterialStatus,
    SeriesKind,
    SteinmetzFit,
)
from inductor_designer.materials.validation import IssueSeverity, validate_record
from inductor_designer.simulation.capabilities import DcBiasDecision, DcBiasStrategy
from inductor_designer.simulation.sections import ConductorSection, CoreSection

SOLUTION_TYPE = "EddyCurrent"
SOLUTION_TYPE_DC = "AC Magnetic with DC"
DESIGN_NAME = "Inductor3D"
SETUP_NAME = "Setup1"
MATRIX_NAME = "Matrix1"
COPPER_MATERIAL = "copper"

# AEDT surface-approximation slider position for the initial mesh, shared by the
# 2D and 3D adapters. 6 is the value verified live on AEDT 2025 R2.
INITIAL_MESH_SLIDER_LEVEL = 6
REGION_PADDING_PERCENT = 100.0


class PlanBuildError(ValueError):
    def __init__(self, issues: tuple[str, ...]) -> None:
        super().__init__("; ".join(issues))
        self.issues = issues


class Polarity(str, Enum):
    POSITIVE = "Positive"
    NEGATIVE = "Negative"


def winding_polarity(
    definition: WindingDefinition,
    current_direction: CurrentDirection,
) -> Polarity:
    """Sign of a winding's go leg for the given current direction.

    Shared by the Maxwell 3D and Maxwell 2D plan builders and by the 2D cut
    plane preview, so the drawn polarity and the exported polarity cannot
    disagree. The sign itself comes from `domain.winding.mmf_sign`, which the
    preliminary estimate reads too.
    """
    positive = mmf_sign(definition.winding_direction, current_direction) > 0.0
    return Polarity.POSITIVE if positive else Polarity.NEGATIVE


def invert_polarity(polarity: Polarity) -> Polarity:
    return Polarity.NEGATIVE if polarity is Polarity.POSITIVE else Polarity.POSITIVE


@dataclass(frozen=True, slots=True)
class MaterialSpec:
    """Solver-independent magnetic material properties."""

    name: str
    relative_permeability: float
    conductivity_s_per_m: float
    draft: bool
    mass_density_kg_per_m3: float | None = None
    # (B in tesla, H in A/m) per point -- FEMM's own `mi_addbhpoint(name, b, h)`
    # argument order, which is the reverse of the recorded series (x = H,
    # y = B) and the reverse of what AEDT stores. The Maxwell adapters must
    # swap it back; PyAEDT's `set_non_linear` docstring example passes
    # [[b, h]] pairs, which writes B into AEDT's H column.
    bh_curve: tuple[tuple[float, float], ...] = ()
    steinmetz: SteinmetzFit | None = None
    material_revision: str | None = None
    bh_series_id: str | None = None


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
    # Finished dimensions, so a section sheet can span the cross section
    # without the adapter re-deriving them from the profile.
    r_inner_m: float = 0.0
    r_outer_m: float = 0.0
    half_height_m: float = 0.0


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
    # Representative cross sections (2026-08-10 design). Chosen by pure
    # selection so the adapter evaluates a section list it did not pick.
    core_sections: tuple[CoreSection, ...] = ()
    conductor_sections: tuple[ConductorSection, ...] = ()


@dataclass(frozen=True, slots=True)
class GeometryOnlyTurnPlan:
    name: str
    segments: tuple[PathSegment, ...]
    bare_diameter_m: float


@dataclass(frozen=True, slots=True)
class GeometryOnlyWindingPlan:
    name: str
    winding_id: str
    turns: tuple[GeometryOnlyTurnPlan, ...]


@dataclass(frozen=True, slots=True)
class GeometryOnlyMaxwell3dPlan:
    design_name: str
    core_name: str
    core_profile: tuple[PathSegment, ...]
    windings: tuple[GeometryOnlyWindingPlan, ...]
    notes: tuple[str, ...]


def material_spec_from_material_record(
    expected_ref: MaterialRef | None,
    material: MaterialRecord,
    *,
    bh_series_id: str | None = None,
) -> MaterialSpec:
    """Build solver material data from an imported or approved project snapshot."""
    if material.status not in (MaterialStatus.IMPORTED, MaterialStatus.APPROVED):
        raise PlanBuildError(("Only imported or approved material records can be exported.",))
    if expected_ref is not None and material.ref != expected_ref:
        raise PlanBuildError(("Material record identity does not match the selected core.",))
    errors = tuple(
        issue.message
        for issue in validate_record(material)
        if issue.severity is IssueSeverity.ERROR
    )
    if errors:
        raise PlanBuildError(errors)

    bh_series = tuple(
        series for series in material.series if series.kind is SeriesKind.BH_CURVE
    )
    if bh_series_id is None:
        if len(bh_series) > 1:
            raise PlanBuildError(
                (
                    "Material revision has multiple B-H series; provide an explicit "
                    "bh_series_id before export.",
                )
            )
        selected_bh = bh_series[0] if bh_series else None
    else:
        selected_bh = next(
            (series for series in material.series if series.series_id == bh_series_id), None
        )
        if selected_bh is None:
            raise PlanBuildError((f"Selected unknown B-H series {bh_series_id!r}.",))
        if selected_bh.kind is not SeriesKind.BH_CURVE:
            raise PlanBuildError(
                (f"Selected series {bh_series_id!r} does not name a B-H series.",)
            )
    bh_points = (
        tuple((point.x, point.y) for point in selected_bh.points)
        if selected_bh is not None
        else ()
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
        mass_density_kg_per_m3=material.mass_density_kg_per_m3,
        bh_curve=tuple(
            (flux_density, field_strength) for field_strength, flux_density in bh_points
        ),
        steinmetz=material.steinmetz,
        material_revision=material.revision_id,
        bh_series_id=bh_series_id,
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
    if decision.strategy is DcBiasStrategy.AC_ONLY_DC_IGNORED:
        return (f"DC bias ignored; this is an AC-only result: {decision.reason}",)
    return (f"DC operating currents are recorded but not applied: {decision.reason}",)
