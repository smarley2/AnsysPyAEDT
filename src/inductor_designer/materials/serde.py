from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable, Mapping
from typing import Any

from inductor_designer.domain.units import to_canonical
from inductor_designer.materials.identity import MaterialRef
from inductor_designer.materials.numerics import canonical_float
from inductor_designer.materials.records import (
    CurveConditions,
    CurvePoint,
    MaterialRecord,
    MaterialStatus,
    PointSeries,
    SeriesKind,
    SourceKind,
    SourceProvenance,
    SteinmetzFit,
)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_float(value: float | None) -> float | None:
    return canonical_float(value) if value is not None else None


def canonicalize_points(
    points: Iterable[tuple[float, float]], x_unit: str, y_unit: str
) -> tuple[CurvePoint, ...]:
    """Convert raw-unit points to sorted, nine-decimal canonical points."""
    return tuple(
        sorted(
            (
                CurvePoint(
                    round(to_canonical(x, x_unit), 9),
                    round(to_canonical(y, y_unit), 9),
                )
                for x, y in points
            ),
            key=lambda point: point.x,
        )
    )


def _reject_non_finite(value: object, path: str = "record") -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{path} must contain only finite numeric values")
    if isinstance(value, Mapping):
        for key, item in value.items():
            _reject_non_finite(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_non_finite(item, f"{path}[{index}]")


def material_record_to_json(
    record: MaterialRecord, *, include_revision: bool = True
) -> dict[str, object]:
    document: dict[str, object] = {
        "ref": {
            "manufacturer": record.ref.manufacturer,
            "name": record.ref.name,
            "grade": record.ref.grade,
        },
        "status": record.status.value,
        "createdAt": record.created_at,
        "reviewedBy": record.reviewed_by,
        "approvedBy": record.approved_by,
        "sources": [
            {
                "kind": source.kind.value,
                "filename": source.filename,
                "sha256": source.sha256,
                "url": source.url,
                "page": source.page,
                "capturedAt": source.captured_at,
                "description": source.description,
            }
            for source in record.sources
        ],
        "series": [
            {
                "seriesId": series.series_id,
                "kind": series.kind.value,
                "xUnit": series.x_unit,
                "yUnit": series.y_unit,
                "conditions": {
                    "frequencyHz": _canonical_float(series.conditions.frequency_hz),
                    "temperatureC": _canonical_float(series.conditions.temperature_c),
                    "dcBiasAPerM": _canonical_float(series.conditions.dc_bias_a_per_m),
                },
                "points": [
                    {
                        "x": _canonical_float(point.x),
                        "y": _canonical_float(point.y),
                    }
                    for point in series.points
                ],
                "sourceFilename": series.source_filename,
            }
            for series in record.series
        ],
        "relativePermeability": _canonical_float(record.relative_permeability),
        "steinmetz": (
            {
                "k": _canonical_float(record.steinmetz.k),
                "alpha": _canonical_float(record.steinmetz.alpha),
                "beta": _canonical_float(record.steinmetz.beta),
                "rmsRelativeResidual": _canonical_float(
                    record.steinmetz.rms_relative_residual
                ),
                "maxRelativeResidual": _canonical_float(
                    record.steinmetz.max_relative_residual
                ),
            }
            if record.steinmetz is not None
            else None
        ),
        "notes": record.notes,
    }
    if include_revision:
        document["revisionId"] = record.revision_id
    _reject_non_finite(document)
    return document


def _value(document: Mapping[str, Any], key: str, path: str) -> object:
    try:
        return document[key]
    except KeyError as error:
        raise ValueError(f"{path}.{key} is required") from error


def _mapping(value: object, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{path} must be an object")
    return value


def _list(document: Mapping[str, Any], key: str, path: str) -> list[object]:
    value = _value(document, key, path)
    if not isinstance(value, list):
        raise ValueError(f"{path}.{key} must be an array")
    return value


def _string(document: Mapping[str, Any], key: str, path: str) -> str:
    value = _value(document, key, path)
    if not isinstance(value, str):
        raise ValueError(f"{path}.{key} must be a string")
    return value


def _optional_string(document: Mapping[str, Any], key: str, path: str) -> str | None:
    value = _value(document, key, path)
    if value is not None and not isinstance(value, str):
        raise ValueError(f"{path}.{key} must be a string or null")
    return value


def _number(document: Mapping[str, Any], key: str, path: str) -> float:
    value = _value(document, key, path)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{path}.{key} must be a number")
    if not math.isfinite(value):
        raise ValueError(f"{path}.{key} must be finite")
    return float(value)


def _optional_number(document: Mapping[str, Any], key: str, path: str) -> float | None:
    if _value(document, key, path) is None:
        return None
    return _number(document, key, path)


def _integer(document: Mapping[str, Any], key: str, path: str) -> int:
    value = _value(document, key, path)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{path}.{key} must be an integer")
    return value


def _optional_integer(document: Mapping[str, Any], key: str, path: str) -> int | None:
    if _value(document, key, path) is None:
        return None
    return _integer(document, key, path)


def material_record_from_json(document: Mapping[str, Any]) -> MaterialRecord:
    ref = _mapping(_value(document, "ref", "record"), "record.ref")
    sources = []
    for index, item in enumerate(_list(document, "sources", "record")):
        path = f"record.sources[{index}]"
        source = _mapping(item, path)
        sources.append(
            SourceProvenance(
                kind=SourceKind(_string(source, "kind", path)),
                filename=_string(source, "filename", path),
                sha256=_string(source, "sha256", path),
                url=_string(source, "url", path),
                page=_optional_integer(source, "page", path),
                captured_at=_string(source, "capturedAt", path),
                description=_string(source, "description", path),
            )
        )
    series_items = []
    for index, item in enumerate(_list(document, "series", "record")):
        path = f"record.series[{index}]"
        series = _mapping(item, path)
        if "extraction" in series:
            raise ValueError(f"{path}.extraction is not supported; import a CSV or spreadsheet")
        conditions_path = f"{path}.conditions"
        conditions = _mapping(_value(series, "conditions", path), conditions_path)
        points = []
        for point_index, point_item in enumerate(_list(series, "points", path)):
            point_path = f"{path}.points[{point_index}]"
            point = _mapping(point_item, point_path)
            points.append(
                CurvePoint(_number(point, "x", point_path), _number(point, "y", point_path))
            )
        series_items.append(
            PointSeries(
                series_id=_string(series, "seriesId", path),
                kind=SeriesKind(_string(series, "kind", path)),
                x_unit=_string(series, "xUnit", path),
                y_unit=_string(series, "yUnit", path),
                conditions=CurveConditions(
                    _optional_number(conditions, "frequencyHz", conditions_path),
                    _optional_number(conditions, "temperatureC", conditions_path),
                    _optional_number(conditions, "dcBiasAPerM", conditions_path),
                ),
                points=tuple(points),
                source_filename=_string(series, "sourceFilename", path),
            )
        )
    fit_data = _value(document, "steinmetz", "record")
    fit = _mapping(fit_data, "record.steinmetz") if fit_data is not None else None
    revision = document.get("revisionId", "")
    if not isinstance(revision, str):
        raise ValueError("record.revisionId must be a string")
    return MaterialRecord(
        ref=MaterialRef(
            _string(ref, "manufacturer", "record.ref"),
            _string(ref, "name", "record.ref"),
            _string(ref, "grade", "record.ref"),
        ),
        revision_id=revision,
        status=MaterialStatus(_string(document, "status", "record")),
        created_at=_string(document, "createdAt", "record"),
        reviewed_by=_optional_string(document, "reviewedBy", "record"),
        approved_by=_optional_string(document, "approvedBy", "record"),
        sources=tuple(sources),
        series=tuple(series_items),
        relative_permeability=_optional_number(document, "relativePermeability", "record"),
        steinmetz=(
            SteinmetzFit(
                k=_number(fit, "k", "record.steinmetz"),
                alpha=_number(fit, "alpha", "record.steinmetz"),
                beta=_number(fit, "beta", "record.steinmetz"),
                rms_relative_residual=_number(
                    fit, "rmsRelativeResidual", "record.steinmetz"
                ),
                max_relative_residual=_number(
                    fit, "maxRelativeResidual", "record.steinmetz"
                ),
            )
            if fit is not None
            else None
        ),
        notes=_string(document, "notes", "record"),
    )


def material_record_json(record: MaterialRecord) -> str:
    return (
        json.dumps(material_record_to_json(record), allow_nan=False, indent=2, sort_keys=True)
        + "\n"
    )


def revision_id_for(record: MaterialRecord) -> str:
    document = material_record_to_json(record)
    document["revisionId"] = ""
    for key in ("status", "reviewedBy", "approvedBy"):
        del document[key]
    canonical = json.dumps(document, allow_nan=False, indent=2, sort_keys=True) + "\n"
    return sha256_hex(canonical.encode("utf-8"))[:12]


def points_csv(series: PointSeries) -> str:
    for point in series.points:
        if not math.isfinite(point.x) or not math.isfinite(point.y):
            raise ValueError("CSV points must contain only finite values")
    rows = (f"{repr(round(point.x, 9))},{repr(round(point.y, 9))}" for point in series.points)
    return "x,y\n" + "".join(f"{row}\n" for row in rows)


def parse_points_csv(text: str) -> tuple[tuple[float, float], ...]:
    lines = text.splitlines()
    if len(lines) < 2 or lines[0] != "x,y" or any(not line for line in lines[1:]):
        raise ValueError("CSV must contain an x,y header and at least one data row")
    points = []
    for row_number, line in enumerate(lines[1:], start=2):
        columns = line.split(",")
        if len(columns) != 2:
            raise ValueError(f"CSV row {row_number} must contain exactly two columns")
        try:
            point = (float(columns[0]), float(columns[1]))
        except ValueError as error:
            raise ValueError(f"CSV row {row_number} contains a non-numeric value") from error
        if not all(math.isfinite(value) for value in point):
            raise ValueError(f"CSV row {row_number} contains a non-finite value")
        points.append(point)
    return tuple(points)
