from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum

from inductor_designer.materials.calibration import ExtractionRecord
from inductor_designer.materials.identity import MaterialRef


class MaterialStatus(str, Enum):
    DRAFT = "draft"
    REVIEWED = "reviewed"
    APPROVED = "approved"


class SourceKind(str, Enum):
    IMAGE = "image"
    CSV = "csv"


class SeriesKind(str, Enum):
    BH_CURVE = "bh-curve"
    LOSS_TABLE = "loss-table"


@dataclass(frozen=True, slots=True)
class SourceProvenance:
    kind: SourceKind
    filename: str
    sha256: str
    url: str
    page: int | None
    captured_at: str
    description: str

    def __post_init__(self) -> None:
        if len(self.sha256) != 64 or any(char not in "0123456789abcdef" for char in self.sha256):
            raise ValueError("sha256 must be 64 lowercase hexadecimal characters")


@dataclass(frozen=True, slots=True)
class CurveConditions:
    frequency_hz: float | None
    temperature_c: float | None
    dc_bias_a_per_m: float | None


@dataclass(frozen=True, slots=True)
class CurvePoint:
    x: float
    y: float


@dataclass(frozen=True, slots=True)
class PointSeries:
    series_id: str
    kind: SeriesKind
    x_unit: str
    y_unit: str
    conditions: CurveConditions
    points: tuple[CurvePoint, ...]
    source_filename: str
    extraction: ExtractionRecord | None


@dataclass(frozen=True, slots=True)
class SteinmetzFit:
    k: float
    alpha: float
    beta: float
    rms_relative_residual: float
    max_relative_residual: float


@dataclass(frozen=True, slots=True)
class MaterialRecord:
    ref: MaterialRef
    revision_id: str
    status: MaterialStatus
    created_at: str
    reviewed_by: str | None
    approved_by: str | None
    sources: tuple[SourceProvenance, ...]
    series: tuple[PointSeries, ...]
    relative_permeability: float | None
    steinmetz: SteinmetzFit | None
    notes: str

    def __post_init__(self) -> None:
        if self.status is MaterialStatus.REVIEWED and not self.reviewed_by:
            raise ValueError("reviewed material requires reviewed_by")
        if self.status is MaterialStatus.APPROVED and (
            not self.reviewed_by or not self.approved_by
        ):
            raise ValueError("approved material requires reviewed_by and approved_by")

        series_ids = [item.series_id for item in self.series]
        if len(series_ids) != len(set(series_ids)):
            raise ValueError("series_id values must be unique within a material record")

        source_filenames = {source.filename for source in self.sources}
        if any(item.source_filename not in source_filenames for item in self.series):
            raise ValueError("each series source_filename must name a provenance source")


def review_record(record: MaterialRecord, reviewer: str) -> MaterialRecord:
    if record.status is not MaterialStatus.DRAFT:
        raise ValueError("only a draft material record can be reviewed")
    return replace(record, status=MaterialStatus.REVIEWED, reviewed_by=reviewer)


def approve_record(record: MaterialRecord, approver: str) -> MaterialRecord:
    if record.status is not MaterialStatus.REVIEWED:
        raise ValueError("only a reviewed material record can be approved")
    return replace(record, status=MaterialStatus.APPROVED, approved_by=approver)
