from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from inductor_designer.materials.identity import MaterialRef


class ReviewStatus(str, Enum):
    DRAFT = "draft"
    REVIEWED = "reviewed"


class CoreFamily(str, Enum):
    POWDER_TOROID = "powder-toroid"
    FERRITE_TOROID = "ferrite-toroid"


class ConductorStandard(str, Enum):
    AWG = "awg"
    IEC_60317 = "iec-60317"


@dataclass(frozen=True, slots=True)
class Dimension:
    """A nominal dimension in meters with optional tolerance bounds."""

    nominal_m: float
    min_m: float | None
    max_m: float | None

    def __post_init__(self) -> None:
        if not self.nominal_m > 0:
            raise ValueError(f"Dimension nominal_m must be positive, got {self.nominal_m!r}")
        low = self.min_m if self.min_m is not None else self.nominal_m
        high = self.max_m if self.max_m is not None else self.nominal_m
        if not low <= self.nominal_m <= high:
            raise ValueError("Dimension requires min_m <= nominal_m <= max_m")


@dataclass(frozen=True, slots=True)
class CoreRecord:
    manufacturer: str
    family: CoreFamily
    part_number: str
    material: MaterialRef
    coating: str
    catalog_revision: str
    source_url: str
    source_page: int
    outer_diameter: Dimension
    inner_diameter: Dimension
    height: Dimension
    effective_area_m2: float
    path_length_m: float
    volume_m3: float
    al_value_nh: float
    review_status: ReviewStatus
    reviewed_by: str | None

    def __post_init__(self) -> None:
        for field_name in ("manufacturer", "part_number", "catalog_revision", "source_url"):
            if not getattr(self, field_name).strip():
                raise ValueError(f"CoreRecord {field_name} cannot be blank")
        if self.source_page < 1:
            raise ValueError(f"CoreRecord source_page must be >= 1, got {self.source_page!r}")
        if self.inner_diameter.nominal_m >= self.outer_diameter.nominal_m:
            raise ValueError("CoreRecord inner_diameter must be smaller than outer_diameter")
        for field_name in ("effective_area_m2", "path_length_m", "volume_m3", "al_value_nh"):
            if not getattr(self, field_name) > 0:
                raise ValueError(f"CoreRecord {field_name} must be positive")


@dataclass(frozen=True, slots=True)
class ConductorRecord:
    name: str
    standard: ConductorStandard
    bare_diameter_m: float
    grade1_diameter_m: float | None
    grade2_diameter_m: float | None
    source: str
    catalog_revision: str
    review_status: ReviewStatus
    reviewed_by: str | None

    def __post_init__(self) -> None:
        for field_name in ("name", "source", "catalog_revision"):
            if not getattr(self, field_name).strip():
                raise ValueError(f"ConductorRecord {field_name} cannot be blank")
        if not self.bare_diameter_m > 0:
            raise ValueError("ConductorRecord bare_diameter_m must be positive")
        for field_name in ("grade1_diameter_m", "grade2_diameter_m"):
            value: float | None = getattr(self, field_name)
            if value is not None and value <= self.bare_diameter_m:
                raise ValueError(
                    f"ConductorRecord {field_name} must exceed bare_diameter_m when present"
                )
