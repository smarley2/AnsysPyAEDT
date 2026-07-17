from __future__ import annotations

from dataclasses import replace

from inductor_designer.application.services.material_import import (
    import_curve_csv,
    new_draft_record,
)
from inductor_designer.materials.calibration import (
    AxisCalibration,
    AxisScale,
    CropRegion,
    ExtractionRecord,
    PixelPoint,
    extract_points,
)
from inductor_designer.materials.identity import MaterialRef
from inductor_designer.materials.records import (
    CurveConditions,
    CurvePoint,
    MaterialRecord,
    PointSeries,
    SeriesKind,
    SourceKind,
    SourceProvenance,
)
from inductor_designer.materials.replay import reproduce_record
from inductor_designer.materials.serde import canonicalize_points, revision_id_for, sha256_hex


def _source(kind: SourceKind, filename: str, data: bytes) -> SourceProvenance:
    return SourceProvenance(
        kind=kind,
        filename=filename,
        sha256=sha256_hex(data),
        url=f"https://example.com/{filename}",
        page=1 if kind is SourceKind.IMAGE else None,
        captured_at="2026-07-17T12:00:00+00:00",
        description="Replay fixture",
    )


def _record_fixture() -> tuple[MaterialRecord, dict[str, bytes]]:
    source_bytes = {
        "loss-10000.csv": (
            b"x,y\n0.05,10933.62073943279\n0.1,53845.43935696282\n"
        ),
        "loss-50000.csv": (
            b"x,y\n0.05,104083.5487608821\n0.1,512636.1476004878\n"
        ),
        "bh.png": b"synthetic image bytes",
    }
    loss_sources = tuple(
        _source(SourceKind.CSV, filename, source_bytes[filename])
        for filename in ("loss-10000.csv", "loss-50000.csv")
    )
    loss_series = tuple(
        import_curve_csv(
            source_bytes[source.filename].decode("utf-8"),
            series_id=f"loss-{frequency}",
            kind=SeriesKind.LOSS_TABLE,
            x_unit="T",
            y_unit="W/m3",
            conditions=CurveConditions(float(frequency), 25.0, None),
            source=source,
        )
        for frequency, source in zip((10_000, 50_000), loss_sources, strict=True)
    )
    image_source = _source(SourceKind.IMAGE, "bh.png", source_bytes["bh.png"])
    extraction = ExtractionRecord(
        crop=CropRegion(0, 0, 100, 100),
        x_axis=AxisCalibration(AxisScale.LINEAR, 0.0, 0.0, 100.0, 2.0),
        y_axis=AxisCalibration(AxisScale.LINEAR, 100.0, 0.0, 0.0, 0.2),
        pixel_points=(PixelPoint(0.0, 100.0), PixelPoint(50.0, 50.0)),
    )
    image_series = PointSeries(
        series_id="bh-image",
        kind=SeriesKind.BH_CURVE,
        x_unit="Oe",
        y_unit="T",
        conditions=CurveConditions(None, 25.0, None),
        points=canonicalize_points(extract_points(extraction), "Oe", "T"),
        source_filename=image_source.filename,
        extraction=extraction,
    )
    record = new_draft_record(
        MaterialRef("Example", "Ferrite", "F1"),
        series=(*loss_series, image_series),
        sources=(*loss_sources, image_source),
        created_at="2026-07-17T12:00:00+00:00",
    )
    return record, source_bytes


def _with_current_revision(record: MaterialRecord) -> MaterialRecord:
    return replace(record, revision_id=revision_id_for(record))


def test_reproduce_record_matches_task_8_csv_and_image_paths() -> None:
    record, sources = _record_fixture()

    assert reproduce_record(record, sources).matches
    assert reproduce_record(record, sources).mismatches == ()


def test_source_tamper_reports_only_hash_mismatch() -> None:
    record, sources = _record_fixture()
    sources["loss-10000.csv"] += b"!"

    report = reproduce_record(record, sources)

    assert report.mismatches == ("source 'loss-10000.csv' SHA-256 mismatch",)


def test_stored_point_tamper_reports_only_series_mismatch() -> None:
    record, sources = _record_fixture()
    image = record.series[-1]
    tampered = replace(
        record,
        series=(
            *record.series[:-1],
            replace(image, points=(*image.points[:-1], CurvePoint(image.points[-1].x, 0.11))),
        ),
    )
    tampered = _with_current_revision(tampered)

    report = reproduce_record(tampered, sources)

    assert report.mismatches == ("series 'bh-image' points mismatch",)


def test_stored_fit_tamper_reports_only_fit_mismatch() -> None:
    record, sources = _record_fixture()
    assert record.steinmetz is not None
    tampered = replace(record, steinmetz=replace(record.steinmetz, k=record.steinmetz.k + 0.1))
    tampered = _with_current_revision(tampered)

    report = reproduce_record(tampered, sources)

    assert report.mismatches == ("Steinmetz fit mismatch",)


def test_revision_tamper_reports_only_revision_mismatch() -> None:
    record, sources = _record_fixture()

    report = reproduce_record(replace(record, revision_id="0" * 12), sources)

    assert report.mismatches == ("revision ID mismatch",)


def test_independent_divergences_are_all_reported_in_check_order() -> None:
    record, sources = _record_fixture()
    image = record.series[-1]
    assert record.steinmetz is not None
    tampered = replace(
        record,
        revision_id="0" * 12,
        series=(
            *record.series[:-1],
            replace(image, points=(*image.points[:-1], CurvePoint(image.points[-1].x, 0.11))),
        ),
        steinmetz=replace(record.steinmetz, k=record.steinmetz.k + 0.1),
    )
    sources["bh.png"] += b"!"

    report = reproduce_record(tampered, sources)

    assert report.mismatches == (
        "source 'bh.png' SHA-256 mismatch",
        "series 'bh-image' points mismatch",
        "Steinmetz fit mismatch",
        "revision ID mismatch",
    )
    assert not report.matches


def test_missing_source_does_not_duplicate_series_noise() -> None:
    record, sources = _record_fixture()
    del sources["loss-10000.csv"]

    report = reproduce_record(record, sources)

    assert report.mismatches == ("source 'loss-10000.csv' is missing",)


def test_missing_image_does_not_prevent_independent_extraction_check() -> None:
    record, sources = _record_fixture()
    image = record.series[-1]
    tampered = replace(
        record,
        series=(
            *record.series[:-1],
            replace(image, points=(*image.points[:-1], CurvePoint(image.points[-1].x, 0.11))),
        ),
    )
    tampered = _with_current_revision(tampered)
    del sources["bh.png"]

    report = reproduce_record(tampered, sources)

    assert report.mismatches == (
        "source 'bh.png' is missing",
        "series 'bh-image' points mismatch",
    )
