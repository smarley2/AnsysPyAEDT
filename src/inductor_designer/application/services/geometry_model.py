from __future__ import annotations

from dataclasses import dataclass

from inductor_designer.application.ports.catalog import CatalogRepository
from inductor_designer.domain.catalog_records import ConductorRecord
from inductor_designer.domain.project import InductorProject
from inductor_designer.domain.validation import ValidationCategory, validate_project
from inductor_designer.geometry.collisions import CollisionIssue, check_clearances
from inductor_designer.geometry.core_solid import (
    CoreGeometryError,
    FinishedCore,
    resolve_finished_core,
)
from inductor_designer.geometry.packing import (
    PackedWinding,
    PackingError,
    WindingSpec,
    pack_winding,
)
from inductor_designer.geometry.planar import PlanarModel, build_planar_model
from inductor_designer.geometry.symmetry import (
    SymmetryPlan,
    SymmetryRefusal,
    propose_symmetry_plan,
)


class GeometryModelError(ValueError):
    def __init__(self, issues: tuple[str, ...]) -> None:
        super().__init__("; ".join(issues))
        self.issues = issues


@dataclass(frozen=True, slots=True)
class GeometryModel:
    core: FinishedCore
    packings: tuple[PackedWinding, ...]
    collisions: tuple[CollisionIssue, ...]
    symmetry: SymmetryPlan | SymmetryRefusal
    planar: PlanarModel
    insulated_diameter_m: dict[str, float]
    bare_diameter_m: dict[str, float]


def insulated_diameter(record: ConductorRecord) -> float:
    value = record.grade2_diameter_m or record.grade1_diameter_m
    if value is None:
        raise GeometryModelError(
            (f"Conductor {record.name!r} has no insulated diameter; packing needs one.",)
        )
    return value


def build_geometry_model(project: InductorProject, catalog: CatalogRepository) -> GeometryModel:
    validation = validate_project(project, known_conductors=catalog.list_conductor_names())
    errors = tuple(
        f"{issue.code}: {issue.message}"
        for issue in validation
        if issue.category is ValidationCategory.ERROR
    )
    if errors:
        raise GeometryModelError(errors)
    if project.core is None:
        raise GeometryModelError(("Project has no core selection; geometry needs one.",))
    try:
        core = resolve_finished_core(project.core)
    except CoreGeometryError as error:
        raise GeometryModelError((str(error),)) from error

    packings: list[PackedWinding] = []
    clearances: dict[str, float] = {}
    insulated: dict[str, float] = {}
    bare: dict[str, float] = {}
    for winding in project.windings:
        record = catalog.get_conductor(winding.conductor_name)
        assert record is not None  # validation already checked membership
        d_ins = insulated_diameter(record)
        insulated[winding.winding_id] = d_ins
        bare[winding.winding_id] = record.bare_diameter_m
        clearances[winding.winding_id] = winding.min_clearance_m
        spec = WindingSpec(
            winding_id=winding.winding_id,
            turns=winding.turns,
            insulated_diameter_m=d_ins,
            start_deg=winding.start_angle_deg,
            sector_deg=winding.sector_deg,
            min_spacing_m=winding.min_spacing_m,
            min_clearance_m=winding.min_clearance_m,
        )
        try:
            packings.append(pack_winding(core, spec))
        except PackingError as error:
            raise GeometryModelError((str(error),)) from error

    collisions = check_clearances(core, packings, clearances)
    symmetry = propose_symmetry_plan(project.windings)
    planar = build_planar_model(core, packings, {w: b / 2.0 for w, b in bare.items()})
    return GeometryModel(
        core=core,
        packings=tuple(packings),
        collisions=collisions,
        symmetry=symmetry,
        planar=planar,
        insulated_diameter_m=insulated,
        bare_diameter_m=bare,
    )
