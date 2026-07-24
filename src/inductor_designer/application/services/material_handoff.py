from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace

from inductor_designer.application.ports.catalog import CatalogRepository
from inductor_designer.application.services.aedt_support import (
    SUPPORTED_AEDT_EDITION,
    SUPPORTED_AEDT_RELEASE,
)
from inductor_designer.application.services.catalog_revisions import select_core
from inductor_designer.application.services.material_selection import pin_material_revision
from inductor_designer.domain.aedt_target import ModelDimension
from inductor_designer.domain.project import InductorProject
from inductor_designer.materials.records import MaterialRecord, SeriesKind
from inductor_designer.materials.replay import reproduce_record


@dataclass(frozen=True, slots=True)
class MaterialHandoffPreparation:
    project: InductorProject
    record: MaterialRecord
    bh_series_id: str
    bh_point_count: int
    loss_frequencies_hz: tuple[float, ...]
    source_hashes: tuple[tuple[str, str], ...]


class MaterialHandoffError(ValueError):
    def __init__(self, issues: tuple[str, ...]) -> None:
        self.issues = issues
        super().__init__("; ".join(issues))


def prepare_material_handoff(
    project: InductorProject,
    catalog: CatalogRepository,
    record: MaterialRecord,
    sources: Mapping[str, bytes],
    *,
    core_part_number: str,
    bh_series_id: str,
) -> MaterialHandoffPreparation:
    issues = list(reproduce_record(record, sources).mismatches)
    if project.materials:
        issues.append(
            "Base validation project must not already contain material revisions."
        )
    core = catalog.get_core(core_part_number)
    if core is None:
        issues.append(f"Core not found in catalog: {core_part_number}")
    elif core.material != record.ref:
        issues.append(
            f"Material {record.ref!r} does not match core material {core.material!r}."
        )

    selected_bh = next(
        (
            series
            for series in record.series
            if series.series_id == bh_series_id
            and series.kind is SeriesKind.BH_CURVE
        ),
        None,
    )
    if selected_bh is None:
        issues.append(f"B-H series {bh_series_id!r} is missing or not a B-H curve.")

    loss_frequencies = tuple(
        sorted(
            {
                frequency
                for series in record.series
                if series.kind is SeriesKind.LOSS_TABLE
                if (frequency := series.conditions.frequency_hz) is not None
            }
        )
    )
    if len(loss_frequencies) < 2 or record.steinmetz is None:
        issues.append(
            "Material handoff requires at least two loss frequencies and "
            "a reproducible Steinmetz fit."
        )
    if issues:
        raise MaterialHandoffError(tuple(issues))

    assert selected_bh is not None
    selected = select_core(project, catalog, core_part_number)
    selected = pin_material_revision(
        selected,
        record,
        bh_series_id=bh_series_id,
    )
    selected = replace(
        selected,
        target_release=SUPPORTED_AEDT_RELEASE,
        target_edition=SUPPORTED_AEDT_EDITION,
        dimension_mode=ModelDimension.THREE_D,
    )
    return MaterialHandoffPreparation(
        project=selected,
        record=record,
        bh_series_id=bh_series_id,
        bh_point_count=len(selected_bh.points),
        loss_frequencies_hz=loss_frequencies,
        source_hashes=tuple(
            (source.filename, source.sha256) for source in record.sources
        ),
    )
