from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from enum import Enum

from inductor_designer.application.ports.catalog import CatalogRepository
from inductor_designer.domain.catalog_records import CoreRecord
from inductor_designer.domain.project import CatalogCoreSelection, InductorProject


class SnapshotStatus(str, Enum):
    UNCHANGED = "unchanged"
    CHANGED = "changed"
    MISSING = "missing"


@dataclass(frozen=True, slots=True)
class FieldChange:
    field: str
    old: object
    new: object


@dataclass(frozen=True, slots=True)
class CatalogComparison:
    part_number: str
    status: SnapshotStatus
    changes: tuple[FieldChange, ...]


def select_core(
    project: InductorProject, repository: CatalogRepository, part_number: str
) -> InductorProject:
    record = repository.get_core(part_number)
    if record is None:
        raise LookupError(f"Core not found in catalog: {part_number}")
    selection = CatalogCoreSelection(part_number=part_number, snapshot=record, overrides=())
    return dataclasses.replace(project, core=selection)


def _diff(snapshot: CoreRecord, current: CoreRecord) -> tuple[FieldChange, ...]:
    changes: list[FieldChange] = []
    for field in dataclasses.fields(CoreRecord):
        old = getattr(snapshot, field.name)
        new = getattr(current, field.name)
        if old != new:
            changes.append(FieldChange(field.name, old, new))
    return tuple(changes)


def compare_core_snapshot(
    project: InductorProject, repository: CatalogRepository
) -> CatalogComparison | None:
    core = project.core
    if not isinstance(core, CatalogCoreSelection):
        return None
    current = repository.get_core(core.part_number)
    if current is None:
        return CatalogComparison(core.part_number, SnapshotStatus.MISSING, ())
    changes = _diff(core.snapshot, current)
    status = SnapshotStatus.CHANGED if changes else SnapshotStatus.UNCHANGED
    return CatalogComparison(core.part_number, status, changes)


def adopt_core_revision(
    project: InductorProject, repository: CatalogRepository
) -> InductorProject:
    core = project.core
    if not isinstance(core, CatalogCoreSelection):
        raise LookupError("Project has no catalog core selection to update")
    current = repository.get_core(core.part_number)
    if current is None:
        raise LookupError(f"Core no longer exists in catalog: {core.part_number}")
    updated = dataclasses.replace(core, snapshot=current)
    return dataclasses.replace(project, core=updated)
