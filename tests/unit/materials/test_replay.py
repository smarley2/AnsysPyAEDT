from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from inductor_designer.adapters.materials.overlay_repository import (
    FileOverlayMaterialRepository,
)
from inductor_designer.application.services.material_import import (
    import_curve_csv,
    new_draft_record,
)
from inductor_designer.materials.identity import MaterialRef
from inductor_designer.materials.records import (
    CurveConditions,
    CurvePoint,
    MaterialRecord,
    SeriesKind,
    SourceKind,
    SourceProvenance,
)
from inductor_designer.materials.replay import reproduce_record
from inductor_designer.materials.serde import revision_id_for, sha256_hex


def _source(filename: str, data: bytes) -> SourceProvenance:
    return SourceProvenance(
        kind=SourceKind.CSV,
        filename=filename,
        sha256=sha256_hex(data),
        url=f"https://example.com/{filename}",
        page=None,
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
        "bh.csv": b"x,y\n0,0\n1,0.001\n2,0.002\n",
    }
    loss_sources = tuple(
        _source(filename, source_bytes[filename])
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
    bh_source = _source("bh.csv", source_bytes["bh.csv"])
    bh_series = import_curve_csv(
        source_bytes["bh.csv"].decode("utf-8"),
        series_id="bh-table",
        kind=SeriesKind.BH_CURVE,
        x_unit="A/m",
        y_unit="T",
        conditions=CurveConditions(None, 25.0, None),
        source=bh_source,
    )
    record = new_draft_record(
        MaterialRef("Example", "Ferrite", "F1"),
        series=(*loss_series, bh_series),
        sources=(*loss_sources, bh_source),
        created_at="2026-07-17T12:00:00+00:00",
    )
    return record, source_bytes


def _with_current_revision(record: MaterialRecord) -> MaterialRecord:
    return replace(record, revision_id=revision_id_for(record))


def test_reproduce_record_matches_csv_material_tables() -> None:
    record, sources = _record_fixture()

    report = reproduce_record(record, sources)

    assert report.matches
    assert report.mismatches == ()


def test_save_load_replay_matches_noncanonical_nested_values(tmp_path: Path) -> None:
    record, sources = _record_fixture()
    record = replace(
        record,
        relative_permeability=60.0000000004,
        series=(
            replace(
                record.series[0],
                conditions=CurveConditions(10_000.0, 25.0000000004, 0.0000000004),
            ),
            *record.series[1:],
        ),
    )
    record = _with_current_revision(record)
    repository = FileOverlayMaterialRepository(tmp_path / "overlay")

    repository.save(record, sources)
    loaded = repository.get(record.ref, record.revision_id)

    assert loaded == record
    assert reproduce_record(
        loaded, repository.source_bytes(loaded.ref, loaded.revision_id)
    ).matches


def test_source_tamper_reports_only_hash_mismatch() -> None:
    record, sources = _record_fixture()
    sources["loss-10000.csv"] += b"!"

    report = reproduce_record(record, sources)

    assert report.mismatches == ("source 'loss-10000.csv' SHA-256 mismatch",)


def test_stored_point_tamper_reports_only_series_mismatch() -> None:
    record, sources = _record_fixture()
    bh = record.series[-1]
    tampered = _with_current_revision(
        replace(
            record,
            series=(
                *record.series[:-1],
                replace(bh, points=(*bh.points[:-1], CurvePoint(bh.points[-1].x, 0.11))),
            ),
        )
    )

    report = reproduce_record(tampered, sources)

    assert report.mismatches == ("series 'bh-table' points mismatch",)


def test_stored_fit_tamper_reports_only_fit_mismatch() -> None:
    record, sources = _record_fixture()
    assert record.steinmetz is not None
    tampered = _with_current_revision(
        replace(record, steinmetz=replace(record.steinmetz, k=record.steinmetz.k + 0.1))
    )

    report = reproduce_record(tampered, sources)

    assert report.mismatches == ("Steinmetz fit mismatch",)


def test_revision_tamper_reports_only_revision_mismatch() -> None:
    record, sources = _record_fixture()

    report = reproduce_record(replace(record, revision_id="0" * 12), sources)

    assert report.mismatches == ("revision ID mismatch",)


def test_independent_divergences_are_all_reported_in_check_order() -> None:
    record, sources = _record_fixture()
    bh = record.series[-1]
    assert record.steinmetz is not None
    tampered = replace(
        record,
        revision_id="0" * 12,
        series=(
            *record.series[:-1],
            replace(bh, points=(*bh.points[:-1], CurvePoint(bh.points[-1].x, 0.11))),
        ),
        steinmetz=replace(record.steinmetz, k=record.steinmetz.k + 0.1),
    )
    sources["bh.csv"] += b"!"

    report = reproduce_record(tampered, sources)

    assert report.mismatches == (
        "source 'bh.csv' SHA-256 mismatch",
        "Steinmetz fit mismatch",
        "revision ID mismatch",
    )
    assert not report.matches


def test_missing_source_does_not_duplicate_series_noise() -> None:
    record, sources = _record_fixture()
    del sources["loss-10000.csv"]

    report = reproduce_record(record, sources)

    assert report.mismatches == ("source 'loss-10000.csv' is missing",)


def test_spreadsheet_provenance_cannot_directly_back_a_series() -> None:
    record, sources = _record_fixture()
    bh = record.series[-1]
    spreadsheet = replace(
        next(source for source in record.sources if source.filename == "bh.csv"),
        kind=SourceKind.SPREADSHEET,
        filename="material.xlsx",
    )
    tampered = _with_current_revision(
        replace(
            record,
            sources=(*record.sources[:-1], spreadsheet),
            series=(*record.series[:-1], replace(bh, source_filename="material.xlsx")),
        )
    )
    sources["material.xlsx"] = sources.pop("bh.csv")

    report = reproduce_record(tampered, sources)

    assert report.mismatches == (
        "series 'bh-table' must be backed by a CSV source",
    )
