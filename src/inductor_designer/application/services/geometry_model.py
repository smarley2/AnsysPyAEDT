from __future__ import annotations

from dataclasses import dataclass

from inductor_designer.application.ports.catalog import CatalogRepository
from inductor_designer.domain.catalog_records import ConductorRecord
from inductor_designer.domain.project import InductorProject, ManualECoreSelection
from inductor_designer.domain.validation import ValidationCategory, validate_project
from inductor_designer.domain.winding import (
    CurrentDirection,
    LegPlacement,
    WindingDirection,
    require_toroid_placement,
)
from inductor_designer.geometry.ecore.body import FinishedECore
from inductor_designer.geometry.ecore.packing import (
    LegPackingError,
    LegWindingSpec,
    PackedLegWinding,
    pack_leg_winding,
)
from inductor_designer.geometry.toroid.collisions import CollisionIssue, check_clearances
from inductor_designer.geometry.toroid.core_solid import (
    CoreGeometryError,
    FinishedCore,
    resolve_finished_core,
    resolve_magnetic_core,
)
from inductor_designer.geometry.toroid.packing import (
    PackedWinding,
    PackingError,
    WindingSpec,
    pack_winding,
)
from inductor_designer.geometry.toroid.planar import PlanarModel, build_planar_model
from inductor_designer.geometry.toroid.symmetry import (
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
    # `core` is the coated envelope every winding is placed against;
    # `magnetic_core` is the ferrite body a solver meshes. They differ by the
    # coating and the catalog tolerance band, which is a quarter of the
    # cross-section on a small powder toroid.
    core: FinishedCore
    magnetic_core: FinishedCore
    packings: tuple[PackedWinding, ...]
    collisions: tuple[CollisionIssue, ...]
    symmetry: SymmetryPlan | SymmetryRefusal
    planar: PlanarModel
    insulated_diameter_m: dict[str, float]
    bare_diameter_m: dict[str, float]
    # The wound sense per winding. Geometry does not otherwise care -- packing
    # and clearance are the same either way -- but the preview draws the lean
    # it implies, so the choice is visible before a solve.
    winding_direction: dict[str, WindingDirection]
    # The excitation's direction, for the same reason: the preview's arrow shows
    # where the current goes, which is the product of the two choices.
    current_direction: dict[str, CurrentDirection]


def insulated_diameter(record: ConductorRecord) -> float:
    value = record.grade2_diameter_m or record.grade1_diameter_m
    if value is None:
        raise GeometryModelError(
            (f"Conductor {record.name!r} has no insulated diameter; packing needs one.",)
        )
    return value


def build_geometry_model(project: InductorProject, catalog: CatalogRepository) -> GeometryModel:
    try:
        known_conductors = catalog.list_conductor_names()
    except Exception as error:  # noqa: BLE001 - any repository failure is a geometry input failure
        raise GeometryModelError(
            (f"Catalog is unavailable, so geometry cannot be validated: {error}",)
        ) from error
    validation = validate_project(project, known_conductors=known_conductors)
    errors = tuple(
        f"{issue.code}: {issue.message}"
        for issue in validation
        if issue.category is ValidationCategory.ERROR
    )
    if errors:
        raise GeometryModelError(errors)
    if project.design.core is None:
        raise GeometryModelError(("Project has no core selection; geometry needs one.",))
    if isinstance(project.design.core, ManualECoreSelection):
        # Both builders are legitimate and the project decides which applies.
        # Refusing by name keeps `geometry/toroid/` from learning what a leg
        # is, which is this milestone's rule, and tells the caller where to
        # go instead of returning a model shaped for the wrong family.
        raise GeometryModelError(
            (
                "This project uses an E core, not a toroid: build its geometry "
                "with build_ecore_geometry_model.",
            )
        )
    try:
        core = resolve_finished_core(project.design.core)
        magnetic_core = resolve_magnetic_core(project.design.core)
    except CoreGeometryError as error:
        raise GeometryModelError((str(error),)) from error

    packings: list[PackedWinding] = []
    clearances: dict[str, float] = {}
    insulated: dict[str, float] = {}
    bare: dict[str, float] = {}
    senses: dict[str, WindingDirection] = {}
    for winding in project.design.windings:
        try:
            record = catalog.get_conductor(winding.conductor_name)
        except Exception as error:  # noqa: BLE001 - any repository failure is a geometry input failure
            raise GeometryModelError(
                (f"Catalog is unavailable, so geometry cannot be validated: {error}",)
            ) from error
        assert record is not None  # validation already checked membership
        d_ins = insulated_diameter(record)
        insulated[winding.winding_id] = d_ins
        bare[winding.winding_id] = record.bare_diameter_m
        clearances[winding.winding_id] = winding.min_clearance_m
        senses[winding.winding_id] = winding.winding_direction
        spec = WindingSpec(
            winding_id=winding.winding_id,
            turns=winding.turns,
            insulated_diameter_m=d_ins,
            start_deg=require_toroid_placement(winding).start_angle_deg,
            sector_deg=require_toroid_placement(winding).sector_deg,
            min_spacing_m=winding.min_spacing_m,
            min_clearance_m=winding.min_clearance_m,
        )
        try:
            packings.append(pack_winding(core, spec))
        except PackingError as error:
            raise GeometryModelError((str(error),)) from error

    # Validation already pairs every winding with one excitation, so a missing
    # entry here is impossible rather than defaulted.
    currents = {
        point.winding_id: point.current_direction
        for point in project.operating_point.windings
    }
    collisions = check_clearances(core, packings, clearances)
    symmetry = propose_symmetry_plan(project.design.windings, project.operating_point.windings)
    planar = build_planar_model(
        core, magnetic_core, packings, {w: b / 2.0 for w, b in bare.items()}
    )
    return GeometryModel(
        core=core,
        magnetic_core=magnetic_core,
        packings=tuple(packings),
        collisions=collisions,
        symmetry=symmetry,
        planar=planar,
        insulated_diameter_m=insulated,
        bare_diameter_m=bare,
        winding_direction=senses,
        current_direction=currents,
    )


@dataclass(frozen=True, slots=True)
class ECoreGeometryModel:
    """The E-core family's geometry model.

    A sibling of `GeometryModel` rather than a widening of it: the toroid's
    packings are angular and this family's are axial, so one type carrying
    both would leave every consumer asking which half is populated -- the
    universal monolith this milestone rules out. Consumers that only ever
    meant the toroid keep their exact type and are untouched.
    """

    body: FinishedECore
    packings: tuple[PackedLegWinding, ...]
    insulated_diameter_m: dict[str, float]
    bare_diameter_m: dict[str, float]
    winding_direction: dict[str, WindingDirection]
    current_direction: dict[str, CurrentDirection]


def build_ecore_geometry_model(
    project: InductorProject, catalog: CatalogRepository
) -> ECoreGeometryModel:
    """Resolve an E-core project's body and wind its centre leg."""
    core = project.design.core
    if not isinstance(core, ManualECoreSelection):
        raise GeometryModelError(
            ("This project does not use an E core, so it has no E-core geometry.",)
        )
    known_conductors = catalog.list_conductor_names()
    validation = validate_project(project, known_conductors=known_conductors)
    errors = tuple(
        f"{issue.code}: {issue.message}"
        for issue in validation
        if issue.category is ValidationCategory.ERROR
    )
    if errors:
        raise GeometryModelError(errors)

    try:
        body = FinishedECore(
            centre_leg_width_m=core.centre_leg_width_m,
            depth_m=core.depth_m,
            window_width_m=core.window_width_m,
            window_height_m=core.window_height_m,
            outer_leg_width_m=core.outer_leg_width_m,
            yoke_thickness_m=core.yoke_thickness_m,
            gaps=core.gaps_m,
            gap_spacings_m=core.gap_spacings_m,
            outer_legs_gapped=core.outer_legs_gapped,
        )
    except CoreGeometryError as error:
        raise GeometryModelError((str(error),)) from error

    leg_length_m = body.centre_leg_length_m
    claimed: list[tuple[str, float, float]] = []
    for winding in project.design.windings:
        placement = winding.placement
        if not isinstance(placement, LegPlacement):
            continue
        end = placement.window_start_m + placement.window_span_m
        if end > leg_length_m:
            raise GeometryModelError(
                (
                    f"Winding {winding.winding_id} runs to "
                    f"{end * 1000.0:.1f} mm along a centre leg only "
                    f"{leg_length_m * 1000.0:.1f} mm long.",
                )
            )
        for other_id, other_start, other_end in claimed:
            # The window analogue of the toroid's sector-overlap rule, which
            # `domain/validation._sectors_overlap` cannot express for a leg:
            # two windings sharing a span would pack to identical stations and
            # occupy the same copper.
            if placement.window_start_m < other_end and other_start < end:
                raise GeometryModelError(
                    (
                        f"Windings {other_id} and {winding.winding_id} claim "
                        "the same span of the winding window.",
                    )
                )
        claimed.append((winding.winding_id, placement.window_start_m, end))

    packings: list[PackedLegWinding] = []
    insulated: dict[str, float] = {}
    bare: dict[str, float] = {}
    senses: dict[str, WindingDirection] = {}
    for winding in project.design.windings:
        placement = winding.placement
        if not isinstance(placement, LegPlacement):
            raise GeometryModelError(
                (
                    f"Winding {winding.winding_id} is placed around a toroid, "
                    "not on a leg, so this E core cannot carry it.",
                )
            )
        record = catalog.get_conductor(winding.conductor_name)
        assert record is not None  # validation already checked membership
        d_ins = insulated_diameter(record)
        insulated[winding.winding_id] = d_ins
        bare[winding.winding_id] = record.bare_diameter_m
        senses[winding.winding_id] = winding.winding_direction
        try:
            packings.append(
                pack_leg_winding(
                    body,
                    LegWindingSpec(
                        winding_id=winding.winding_id,
                        turns=winding.turns,
                        insulated_diameter_m=d_ins,
                        window_start_m=placement.window_start_m,
                        window_span_m=placement.window_span_m,
                        min_spacing_m=winding.min_spacing_m,
                        min_clearance_m=winding.min_clearance_m,
                    ),
                )
            )
        except LegPackingError as error:
            raise GeometryModelError((str(error),)) from error

    currents = {
        point.winding_id: point.current_direction
        for point in project.operating_point.windings
    }
    return ECoreGeometryModel(
        body=body,
        packings=tuple(packings),
        insulated_diameter_m=insulated,
        bare_diameter_m=bare,
        winding_direction=senses,
        current_direction=currents,
    )
