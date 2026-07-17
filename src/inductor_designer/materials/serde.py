from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from typing import Any, cast

from inductor_designer.materials.calibration import (
    AxisCalibration,
    AxisScale,
    CropRegion,
    ExtractionRecord,
    PixelPoint,
)
from inductor_designer.materials.identity import MaterialRef
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


def _axis_to_json(axis: AxisCalibration) -> dict[str, object]:
    return {
        "scale": axis.scale.value,
        "pixelA": axis.pixel_a,
        "valueA": axis.value_a,
        "pixelB": axis.pixel_b,
        "valueB": axis.value_b,
    }


def _extraction_to_json(extraction: ExtractionRecord) -> dict[str, object]:
    return {
        "crop": {
            "left": extraction.crop.left,
            "top": extraction.crop.top,
            "width": extraction.crop.width,
            "height": extraction.crop.height,
        },
        "xAxis": _axis_to_json(extraction.x_axis),
        "yAxis": _axis_to_json(extraction.y_axis),
        "pixelPoints": [
            {"xPx": point.x_px, "yPx": point.y_px} for point in extraction.pixel_points
        ],
    }


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
                    "frequencyHz": series.conditions.frequency_hz,
                    "temperatureC": series.conditions.temperature_c,
                    "dcBiasAPerM": series.conditions.dc_bias_a_per_m,
                },
                "points": [{"x": point.x, "y": point.y} for point in series.points],
                "sourceFilename": series.source_filename,
                "extraction": (
                    _extraction_to_json(series.extraction)
                    if series.extraction is not None
                    else None
                ),
            }
            for series in record.series
        ],
        "relativePermeability": record.relative_permeability,
        "steinmetz": (
            {
                "k": record.steinmetz.k,
                "alpha": record.steinmetz.alpha,
                "beta": record.steinmetz.beta,
                "rmsRelativeResidual": record.steinmetz.rms_relative_residual,
                "maxRelativeResidual": record.steinmetz.max_relative_residual,
            }
            if record.steinmetz is not None
            else None
        ),
        "notes": record.notes,
    }
    if include_revision:
        document["revisionId"] = record.revision_id
    return document


def _mapping(value: object) -> Mapping[str, Any]:
    return cast("Mapping[str, Any]", value)


def _axis_from_json(document: Mapping[str, Any]) -> AxisCalibration:
    return AxisCalibration(
        scale=AxisScale(document["scale"]),
        pixel_a=document["pixelA"],
        value_a=document["valueA"],
        pixel_b=document["pixelB"],
        value_b=document["valueB"],
    )


def _extraction_from_json(document: Mapping[str, Any]) -> ExtractionRecord:
    crop = _mapping(document["crop"])
    return ExtractionRecord(
        crop=CropRegion(crop["left"], crop["top"], crop["width"], crop["height"]),
        x_axis=_axis_from_json(_mapping(document["xAxis"])),
        y_axis=_axis_from_json(_mapping(document["yAxis"])),
        pixel_points=tuple(
            PixelPoint(point["xPx"], point["yPx"])
            for item in document["pixelPoints"]
            if (point := _mapping(item))
        ),
    )


def material_record_from_json(document: Mapping[str, Any]) -> MaterialRecord:
    ref = _mapping(document["ref"])
    sources = tuple(
        SourceProvenance(
            kind=SourceKind(source["kind"]),
            filename=source["filename"],
            sha256=source["sha256"],
            url=source["url"],
            page=source["page"],
            captured_at=source["capturedAt"],
            description=source["description"],
        )
        for item in document["sources"]
        if (source := _mapping(item))
    )
    series_items = []
    for item in document["series"]:
        series = _mapping(item)
        conditions = _mapping(series["conditions"])
        extraction = series["extraction"]
        series_items.append(
            PointSeries(
                series_id=series["seriesId"],
                kind=SeriesKind(series["kind"]),
                x_unit=series["xUnit"],
                y_unit=series["yUnit"],
                conditions=CurveConditions(
                    conditions["frequencyHz"],
                    conditions["temperatureC"],
                    conditions["dcBiasAPerM"],
                ),
                points=tuple(
                    CurvePoint(point["x"], point["y"])
                    for point_item in series["points"]
                    if (point := _mapping(point_item))
                ),
                source_filename=series["sourceFilename"],
                extraction=(
                    _extraction_from_json(_mapping(extraction))
                    if extraction is not None
                    else None
                ),
            )
        )
    fit_data = document["steinmetz"]
    fit = _mapping(fit_data) if fit_data is not None else None
    return MaterialRecord(
        ref=MaterialRef(ref["manufacturer"], ref["name"], ref["grade"]),
        revision_id=document.get("revisionId", ""),
        status=MaterialStatus(document["status"]),
        created_at=document["createdAt"],
        reviewed_by=document["reviewedBy"],
        approved_by=document["approvedBy"],
        sources=sources,
        series=tuple(series_items),
        relative_permeability=document["relativePermeability"],
        steinmetz=(
            SteinmetzFit(
                k=fit["k"],
                alpha=fit["alpha"],
                beta=fit["beta"],
                rms_relative_residual=fit["rmsRelativeResidual"],
                max_relative_residual=fit["maxRelativeResidual"],
            )
            if fit is not None
            else None
        ),
        notes=document["notes"],
    )


def material_record_json(record: MaterialRecord) -> str:
    return json.dumps(material_record_to_json(record), indent=2, sort_keys=True) + "\n"


def revision_id_for(record: MaterialRecord) -> str:
    document = material_record_to_json(record)
    document["revisionId"] = ""
    for key in ("status", "reviewedBy", "approvedBy"):
        del document[key]
    canonical = json.dumps(document, indent=2, sort_keys=True) + "\n"
    return sha256_hex(canonical.encode("utf-8"))[:12]


def points_csv(series: PointSeries) -> str:
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
