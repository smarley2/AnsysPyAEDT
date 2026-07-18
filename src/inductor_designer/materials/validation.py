from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from inductor_designer.materials.fitting import MU0
from inductor_designer.materials.records import (
    MaterialRecord,
    PointSeries,
    SeriesKind,
    SourceKind,
)

_B_UNITS = frozenset({"T", "mT", "G", "kG"})
_H_UNITS = frozenset({"A/m", "kA/m", "Oe"})
_LOSS_UNITS = frozenset({"W/m3", "kW/m3", "mW/cm3"})


class IssueSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True, slots=True)
class MaterialIssue:
    code: str
    severity: IssueSeverity
    message: str


def _error(code: str, message: str) -> MaterialIssue:
    return MaterialIssue(code, IssueSeverity.ERROR, message)


def validate_series(series: PointSeries) -> tuple[MaterialIssue, ...]:
    """Return deterministic unit and physics issues for one point series."""
    issues: list[MaterialIssue] = []
    if series.kind is SeriesKind.BH_CURVE:
        if series.x_unit not in _H_UNITS or series.y_unit not in _B_UNITS:
            issues.append(_error("unit-family", "B-H series units must describe H and B"))
        if any(not 0.0 <= point.y <= 5.0 for point in series.points):
            issues.append(_error("range-b", "flux density must be between 0 and 5 T"))
        if any(not 0.0 <= point.x <= 10_000_000.0 for point in series.points):
            issues.append(_error("range-h", "field strength must be between 0 and 1e7 A/m"))

        pairs = tuple(zip(series.points, series.points[1:], strict=False))
        field_strengths = tuple(point.x for point in series.points)
        if len(field_strengths) != len(set(field_strengths)):
            issues.append(_error("duplicate-h", "B-H series must not contain duplicate H values"))
        if any(current.x > following.x for current, following in pairs):
            issues.append(_error("monotonic-h", "H values must be strictly increasing"))
        if any(current.y >= following.y for current, following in pairs):
            issues.append(_error("monotonic-b", "B values must be strictly increasing"))
        if not series.points or (series.points[0].x, series.points[0].y) != (0.0, 0.0):
            issues.append(_error("origin", "B-H series must start at (0, 0)"))
        if any(
            (following.y - current.y) / (following.x - current.x) < MU0
            for current, following in pairs
            if following.x > current.x
        ):
            issues.append(
                MaterialIssue(
                    "slope-below-mu0",
                    IssueSeverity.WARNING,
                    "B-H slope is below vacuum permeability",
                )
            )
    else:
        if series.x_unit not in _B_UNITS or series.y_unit not in _LOSS_UNITS:
            issues.append(
                _error("unit-family", "loss series units must describe B and loss density")
            )
        if any(not 0.0 <= point.x <= 5.0 for point in series.points):
            issues.append(_error("range-b", "flux density must be between 0 and 5 T"))
        if any(not point.y > 0.0 for point in series.points):
            issues.append(_error("loss-positive", "loss density must be positive"))
        if (
            series.conditions.frequency_hz is None
            or series.conditions.frequency_hz <= 0.0
        ):
            issues.append(
                _error(
                    "loss-frequency-missing",
                    "loss series requires a positive frequency condition",
                )
            )
    return tuple(issues)


def validate_record(record: MaterialRecord) -> tuple[MaterialIssue, ...]:
    """Return series and record-level material validation issues."""
    issues = [issue for series in record.series for issue in validate_series(series)]
    source_kinds = {source.filename: source.kind for source in record.sources}
    for series in record.series:
        source_kind = source_kinds[series.source_filename]
        if source_kind is SourceKind.IMAGE and series.extraction is None:
            issues.append(
                _error(
                    "image-extraction-missing",
                    "image-backed series requires extraction metadata",
                )
            )
        elif source_kind is SourceKind.CSV and series.extraction is not None:
            issues.append(
                _error(
                    "csv-extraction-present",
                    "CSV-backed series must not include extraction metadata",
                )
            )
        elif source_kind is SourceKind.SPREADSHEET:
            issues.append(
                _error(
                    "spreadsheet-series-source",
                    "spreadsheet provenance cannot directly back a point series",
                )
            )
    if record.relative_permeability is not None and not 1.0 <= record.relative_permeability <= 1e6:
        issues.append(
            _error("permeability-range", "relative permeability must be between 1 and 1e6")
        )
    if not record.series and record.relative_permeability is None:
        issues.append(
            _error("empty-record", "material record requires series data or permeability")
        )
    if record.steinmetz is not None and not any(
        series.kind is SeriesKind.LOSS_TABLE for series in record.series
    ):
        issues.append(_error("fit-without-data", "Steinmetz fit requires loss series data"))
    return tuple(issues)
