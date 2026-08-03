"""Bidirectional core/material selection (specification section 4.1).

Each side filters the other. When a new choice makes the existing paired
selection incompatible, the incompatible side is cleared and the caller is told
why. Nothing is ever substituted: the user picks the replacement.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum

from inductor_designer.application.ports.catalog import CatalogRepository
from inductor_designer.application.ports.material_repository import MaterialRepository
from inductor_designer.application.services.catalog_revisions import select_core
from inductor_designer.application.services.material_selection import (
    pin_material_revision,
)
from inductor_designer.domain.catalog_records import CoreFamily
from inductor_designer.domain.project import (
    CatalogCoreSelection,
    InductorProject,
    ManualCoreSelection,
)
from inductor_designer.materials.identity import MaterialRef
from inductor_designer.materials.records import (
    MaterialRecord,
    MaterialStatus,
    SeriesKind,
)
from inductor_designer.materials.validation import IssueSeverity, validate_record

_SELECTABLE_STATUSES = (MaterialStatus.IMPORTED, MaterialStatus.APPROVED)


class ClearedSelection(str, Enum):
    CORE = "core"
    MATERIAL = "material"


@dataclass(frozen=True, slots=True)
class CoreOption:
    part_number: str
    manufacturer: str
    family: CoreFamily
    material_ref: MaterialRef
    outer_diameter_m: float
    inner_diameter_m: float
    height_m: float


@dataclass(frozen=True, slots=True)
class MaterialOption:
    ref: MaterialRef
    revision_id: str
    status: MaterialStatus
    created_at: str
    bh_series_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SelectionOutcome:
    project: InductorProject
    cleared: ClearedSelection | None
    message: str


def required_material_ref(project: InductorProject) -> MaterialRef | None:
    """The material identity a catalog core demands; None for Manual or no core."""
    core = project.design.core
    return core.snapshot.material if isinstance(core, CatalogCoreSelection) else None


def core_options(
    catalog: CatalogRepository, material_ref: MaterialRef | None
) -> tuple[CoreOption, ...]:
    return tuple(
        CoreOption(
            part_number=record.part_number,
            manufacturer=record.manufacturer,
            family=record.family,
            material_ref=record.material,
            outer_diameter_m=record.outer_diameter.nominal_m,
            inner_diameter_m=record.inner_diameter.nominal_m,
            height_m=record.height.nominal_m,
        )
        for record in catalog.list_cores()
        if material_ref is None or record.material == material_ref
    )


def _is_selectable(record: MaterialRecord) -> bool:
    if record.status not in _SELECTABLE_STATUSES:
        return False
    return not any(
        issue.severity is IssueSeverity.ERROR for issue in validate_record(record)
    )


def material_options(
    repository: MaterialRepository, material_ref: MaterialRef | None
) -> tuple[MaterialOption, ...]:
    options: list[MaterialOption] = []
    for ref in repository.list_materials():
        if material_ref is not None and ref != material_ref:
            continue
        for revision_id in repository.list_revisions(ref):
            record = repository.get(ref, revision_id)
            if not _is_selectable(record):
                continue
            options.append(
                MaterialOption(
                    ref=ref,
                    revision_id=revision_id,
                    status=record.status,
                    created_at=record.created_at,
                    bh_series_ids=tuple(
                        series.series_id
                        for series in record.series
                        if series.kind is SeriesKind.BH_CURVE
                    ),
                )
            )
    return tuple(options)


def apply_catalog_core(
    project: InductorProject, catalog: CatalogRepository, part_number: str
) -> SelectionOutcome:
    """Select a catalog core, clearing a material it cannot carry."""
    selected = select_core(project, catalog, part_number)
    core = selected.design.core
    assert isinstance(core, CatalogCoreSelection)
    # A catalog core declares its own material identity, so a Manual-core
    # compatibility acknowledgment can never apply to it. Dropping it here
    # covers the compatible case too: switching Manual -> Catalog must not
    # leave a stale acknowledgment on a design that never needed one, or the
    # run manifest reports an assumption the user never made.
    selected = replace(
        selected,
        design=replace(
            selected.design, manual_material_compatibility_acknowledged=False
        ),
    )
    material = selected.design.core_material
    if material is not None and material.ref != core.snapshot.material:
        cleared = replace(
            selected,
            design=replace(selected.design, core_material=None),
        )
        return SelectionOutcome(
            project=cleared,
            cleared=ClearedSelection.MATERIAL,
            message=(
                f"Core {part_number} requires material "
                f"{core.snapshot.material.manufacturer} "
                f"{core.snapshot.material.name} {core.snapshot.material.grade}, so the "
                f"pinned {material.ref.manufacturer} {material.ref.name} "
                f"{material.ref.grade} revision {material.revision_id} was cleared. "
                "Select a compatible material revision."
            ),
        )
    return SelectionOutcome(
        project=selected,
        cleared=None,
        message=f"Selected catalog core {part_number}.",
    )


def apply_manual_core(
    project: InductorProject,
    *,
    outer_diameter_m: float,
    inner_diameter_m: float,
    height_m: float,
    corner_radius_m: float,
) -> SelectionOutcome:
    """A Manual core carries no material identity, so nothing is ever cleared.

    New dimensions are new geometry, so any recorded compatibility attestation
    is dropped: the user attested to the pair they saw, and every consumer of
    the project -- exports, run manifests, other screens -- reads that flag.
    """
    core = ManualCoreSelection(
        outer_diameter_m=outer_diameter_m,
        inner_diameter_m=inner_diameter_m,
        height_m=height_m,
        corner_radius_m=corner_radius_m,
    )
    reconfirm = (
        " Confirm material compatibility again for the new dimensions."
        if project.design.manual_material_compatibility_acknowledged
        else ""
    )
    return SelectionOutcome(
        project=replace(
            project,
            design=replace(
                project.design,
                core=core,
                manual_material_compatibility_acknowledged=False,
            ),
        ),
        cleared=None,
        message=f"Applied manual core dimensions.{reconfirm}",
    )


def apply_material_revision(
    project: InductorProject,
    repository: MaterialRepository,
    ref: MaterialRef,
    revision_id: str,
    *,
    bh_series_id: str | None = None,
    acknowledge_manual_compatibility: bool = False,
) -> SelectionOutcome:
    """Pin an exact revision, clearing a catalog core it does not belong to.

    `pin_material_revision` refuses a mismatched catalog core outright; clearing
    the core first is what turns that refusal into the visible, unresolved state
    the specification asks for.
    """
    record = repository.get(ref, revision_id)
    core = project.design.core
    cleared: ClearedSelection | None = None
    message_prefix = ""
    target = project
    if isinstance(core, CatalogCoreSelection) and core.snapshot.material != ref:
        target = replace(project, design=replace(project.design, core=None))
        cleared = ClearedSelection.CORE
        message_prefix = (
            f"Catalog core {core.part_number} requires material "
            f"{core.snapshot.material.manufacturer} {core.snapshot.material.name} "
            f"{core.snapshot.material.grade}, so it was cleared. Select a core that "
            "uses the pinned material. "
        )
    pinned = pin_material_revision(
        target,
        record,
        bh_series_id=bh_series_id,
        manual_compatibility_acknowledged=(
            acknowledge_manual_compatibility
            if isinstance(target.design.core, ManualCoreSelection)
            else False
        ),
    )
    return SelectionOutcome(
        project=pinned,
        cleared=cleared,
        message=(
            f"{message_prefix}Pinned {ref.manufacturer} {ref.name} {ref.grade} "
            f"revision {revision_id}."
        ),
    )


def clear_material_selection(project: InductorProject) -> SelectionOutcome:
    """Unpin the material revision, leaving the core alone.

    Clearing carries no compatibility rule, but it still happens here so the
    controller never mutates project state itself.
    """
    if project.design.core_material is None:
        return SelectionOutcome(project, None, "No material revision is pinned.")
    return SelectionOutcome(
        project=replace(
            project,
            design=replace(
                project.design,
                core_material=None,
                manual_material_compatibility_acknowledged=False,
            ),
        ),
        cleared=ClearedSelection.MATERIAL,
        message="Cleared the pinned material revision.",
    )


def revalidate_pinned_material(
    project: InductorProject, repository: MaterialRepository
) -> SelectionOutcome:
    """Re-check the pinned revision after the material library changed.

    Called when the Material Studio window closes. An exact revision that still
    exists and is still selectable survives untouched; anything else becomes
    unresolved with a message that names it.
    """
    material = project.design.core_material
    if material is None:
        return SelectionOutcome(project, None, "No material revision is pinned.")
    still_present = material.revision_id in repository.list_revisions(material.ref)
    if still_present and _is_selectable(
        repository.get(material.ref, material.revision_id)
    ):
        return SelectionOutcome(
            project,
            None,
            f"Pinned revision {material.revision_id} is unchanged.",
        )
    reason = (
        "no longer exists in the material library"
        if not still_present
        else "is no longer selectable"
    )
    return SelectionOutcome(
        project=replace(
            project,
            design=replace(
                project.design,
                core_material=None,
                manual_material_compatibility_acknowledged=False,
            ),
        ),
        cleared=ClearedSelection.MATERIAL,
        message=(
            f"Pinned {material.ref.manufacturer} {material.ref.name} "
            f"{material.ref.grade} revision {material.revision_id} {reason}, so the "
            "material selection was cleared. Select a revision that exists."
        ),
    )
