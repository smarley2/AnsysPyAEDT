from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from inductor_designer.materials.calibration import extract_points
from inductor_designer.materials.fitting import LossSample, MaterialFitError, fit_steinmetz
from inductor_designer.materials.records import (
    CurvePoint,
    MaterialRecord,
    PointSeries,
    SeriesKind,
    SourceKind,
)
from inductor_designer.materials.serde import (
    canonicalize_points,
    parse_points_csv,
    revision_id_for,
    sha256_hex,
)


@dataclass(frozen=True, slots=True)
class ReproductionReport:
    matches: bool
    mismatches: tuple[str, ...]


def _loss_samples(
    series: tuple[PointSeries, ...], reproduced: Mapping[str, tuple[CurvePoint, ...]]
) -> tuple[LossSample, ...]:
    return tuple(
        LossSample(frequency, point.x, point.y)
        for item in series
        if item.kind is SeriesKind.LOSS_TABLE
        if (frequency := item.conditions.frequency_hz) is not None and frequency > 0
        for point in reproduced[item.series_id]
        if point.x > 0 and point.y > 0
    )


def reproduce_record(
    record: MaterialRecord, sources: Mapping[str, bytes]
) -> ReproductionReport:
    """Rebuild a material record and report every independent divergence."""
    mismatches: list[str] = []
    unavailable_sources: set[str] = set()
    provenance_by_filename = {source.filename: source for source in record.sources}

    for provenance in record.sources:
        data = sources.get(provenance.filename)
        if data is None:
            mismatches.append(f"source '{provenance.filename}' is missing")
            if provenance.kind is SourceKind.CSV:
                unavailable_sources.add(provenance.filename)
        elif sha256_hex(data) != provenance.sha256:
            mismatches.append(f"source '{provenance.filename}' SHA-256 mismatch")
            if provenance.kind is SourceKind.CSV:
                unavailable_sources.add(provenance.filename)

    reproduced: dict[str, tuple[CurvePoint, ...]] = {}
    failed_loss_reconstruction = False
    for series in record.series:
        provenance = provenance_by_filename[series.source_filename]
        if series.source_filename in unavailable_sources:
            failed_loss_reconstruction |= series.kind is SeriesKind.LOSS_TABLE
            continue
        try:
            if provenance.kind is SourceKind.CSV:
                raw_points = parse_points_csv(sources[series.source_filename].decode("utf-8"))
            elif series.extraction is not None:
                raw_points = extract_points(series.extraction)
            else:
                mismatches.append(f"series '{series.series_id}' extraction is missing")
                failed_loss_reconstruction |= series.kind is SeriesKind.LOSS_TABLE
                continue
            points = canonicalize_points(raw_points, series.x_unit, series.y_unit)
        except (UnicodeError, ValueError) as error:
            mismatches.append(f"series '{series.series_id}' reconstruction failed: {error}")
            failed_loss_reconstruction |= series.kind is SeriesKind.LOSS_TABLE
            continue
        reproduced[series.series_id] = points
        if points != series.points:
            mismatches.append(f"series '{series.series_id}' points mismatch")

    if record.steinmetz is not None and not failed_loss_reconstruction:
        try:
            reproduced_fit = fit_steinmetz(_loss_samples(record.series, reproduced))
        except MaterialFitError:
            mismatches.append("Steinmetz fit could not be reproduced")
        else:
            if reproduced_fit != record.steinmetz:
                mismatches.append("Steinmetz fit mismatch")

    if revision_id_for(record) != record.revision_id:
        mismatches.append("revision ID mismatch")

    return ReproductionReport(matches=not mismatches, mismatches=tuple(mismatches))
