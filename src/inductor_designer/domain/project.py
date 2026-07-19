from __future__ import annotations

from dataclasses import dataclass

from inductor_designer.domain.aedt_target import AedtEdition, AedtRelease, ModelDimension
from inductor_designer.domain.catalog_records import CoreRecord
from inductor_designer.domain.winding import WindingDefinition
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


CoreSelection = CatalogCoreSelection | ManualCoreSelection


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
class InductorProject:
    project_id: str
    name: str
    description: str
    target_release: AedtRelease
    target_edition: AedtEdition
    dimension_mode: ModelDimension
    core: CoreSelection | None
    windings: tuple[WindingDefinition, ...]
    materials: tuple[MaterialRevisionSelection, ...] = ()

    def __post_init__(self) -> None:
        if not self.project_id.strip():
            raise ValueError("InductorProject project_id cannot be blank")
        if not self.name.strip():
            raise ValueError("InductorProject name cannot be blank")
