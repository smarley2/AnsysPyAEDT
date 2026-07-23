from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

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
    approve_record,
    review_record,
)


def _source(filename: str = "curve.csv") -> SourceProvenance:
    return SourceProvenance(
        kind=SourceKind.CSV,
        filename=filename,
        sha256="a" * 64,
        url="https://example.com/curve.csv",
        page=None,
        captured_at="2026-07-17T12:00:00+00:00",
        description="Example curve",
    )


def _series(
    series_id: str = "bh_25c", source_filename: str = "curve.csv"
) -> PointSeries:
    return PointSeries(
        series_id=series_id,
        kind=SeriesKind.BH_CURVE,
        x_unit="Oe",
        y_unit="G",
        conditions=CurveConditions(
            frequency_hz=None,
            temperature_c=25.0,
            dc_bias_a_per_m=None,
        ),
        points=(CurvePoint(0.0, 0.0), CurvePoint(79.577471546, 0.1)),
        source_filename=source_filename,
    )


def _record(
    *,
    revision_id: str = "0123456789ab",
    status: MaterialStatus = MaterialStatus.DRAFT,
    reviewed_by: str | None = None,
    approved_by: str | None = None,
    sources: tuple[SourceProvenance, ...] | None = None,
    series: tuple[PointSeries, ...] | None = None,
) -> MaterialRecord:
    return MaterialRecord(
        ref=MaterialRef("Magnetics", "Kool Mu", "60"),
        revision_id=revision_id,
        status=status,
        created_at="2026-07-17T12:00:00+00:00",
        reviewed_by=reviewed_by,
        approved_by=approved_by,
        sources=(_source(),) if sources is None else sources,
        series=(_series(),) if series is None else series,
        relative_permeability=60.0,
        steinmetz=None,
        notes="",
    )


def test_review_and_approve_record_preserve_revision_id() -> None:
    draft = _record()

    reviewed = review_record(draft, "reviewer@example.com")
    approved = approve_record(reviewed, "approver@example.com")

    assert draft.status is MaterialStatus.DRAFT
    assert reviewed.status is MaterialStatus.REVIEWED
    assert reviewed.reviewed_by == "reviewer@example.com"
    assert reviewed.revision_id == draft.revision_id
    assert approved.status is MaterialStatus.APPROVED
    assert approved.reviewed_by == "reviewer@example.com"
    assert approved.approved_by == "approver@example.com"
    assert approved.revision_id == draft.revision_id
    with pytest.raises(FrozenInstanceError):
        approved.notes = "changed"  # type: ignore[misc]


@pytest.mark.parametrize("status", [MaterialStatus.REVIEWED, MaterialStatus.APPROVED])
def test_review_record_rejects_non_draft(status: MaterialStatus) -> None:
    record = _record(
        status=status,
        reviewed_by="reviewer@example.com",
        approved_by="approver@example.com" if status is MaterialStatus.APPROVED else None,
    )

    with pytest.raises(ValueError, match="draft"):
        review_record(record, "another-reviewer@example.com")


@pytest.mark.parametrize("status", [MaterialStatus.DRAFT, MaterialStatus.APPROVED])
def test_approve_record_rejects_non_reviewed(status: MaterialStatus) -> None:
    record = _record(
        status=status,
        reviewed_by="reviewer@example.com" if status is MaterialStatus.APPROVED else None,
        approved_by="approver@example.com" if status is MaterialStatus.APPROVED else None,
    )

    with pytest.raises(ValueError, match="reviewed"):
        approve_record(record, "another-approver@example.com")


def test_source_provenance_rejects_invalid_sha256() -> None:
    with pytest.raises(ValueError, match="sha256"):
        SourceProvenance(
            kind=SourceKind.CSV,
            sha256="A" * 64,
            filename="curve.csv",
            url="https://example.com/curve.csv",
            page=None,
            captured_at="2026-07-17T12:00:00+00:00",
            description="Example table",
        )


def test_material_record_canonicalizes_all_nested_floats_in_memory() -> None:
    series = PointSeries(
        series_id="loss",
        kind=SeriesKind.LOSS_TABLE,
        x_unit="T",
        y_unit="W/m3",
        conditions=CurveConditions(10_000.0000000004, 25.0000000004, 0.0000000004),
        points=(CurvePoint(0.1000000004, 1000.0000000004),),
        source_filename="curve.csv",
    )
    record = _record(
        series=(series,),
    )
    record = MaterialRecord(
        ref=record.ref,
        revision_id=record.revision_id,
        status=record.status,
        created_at=record.created_at,
        reviewed_by=record.reviewed_by,
        approved_by=record.approved_by,
        sources=record.sources,
        series=record.series,
        relative_permeability=60.0000000004,
        steinmetz=SteinmetzFit(
            2.5000000004,
            1.4000000004,
            2.3000000004,
            0.0100000004,
            0.0200000004,
        ),
        notes=record.notes,
    )

    assert record.relative_permeability == 60.0
    assert record.steinmetz == SteinmetzFit(2.5, 1.4, 2.3, 0.01, 0.02)
    assert record.series[0].conditions == CurveConditions(10_000.0, 25.0, 0.0)
    assert record.series[0].points == (CurvePoint(0.1, 1000.0),)


@pytest.mark.parametrize(
    ("status", "reviewed_by", "approved_by"),
    [
        (MaterialStatus.REVIEWED, None, None),
        (MaterialStatus.APPROVED, None, "approver@example.com"),
        (MaterialStatus.APPROVED, "reviewer@example.com", None),
    ],
)
def test_record_requires_attribution_for_status(
    status: MaterialStatus, reviewed_by: str | None, approved_by: str | None
) -> None:
    with pytest.raises(ValueError, match="requires"):
        _record(status=status, reviewed_by=reviewed_by, approved_by=approved_by)


def test_record_rejects_duplicate_series_ids() -> None:
    with pytest.raises(ValueError, match="series_id"):
        _record(series=(_series(), _series()))


def test_record_rejects_dangling_source_link() -> None:
    with pytest.raises(ValueError, match="source_filename"):
        _record(series=(_series(source_filename="missing.csv"),))


def test_record_allows_supplemental_spreadsheet_provenance() -> None:
    spreadsheet = SourceProvenance(
        kind=SourceKind.SPREADSHEET,
        filename="material.xlsx",
        sha256="b" * 64,
        url="https://example.com/material.xlsx",
        page=7,
        captured_at="2026-07-18T12:00:00+00:00",
        description="Original workbook",
    )

    record = _record(sources=(spreadsheet, _source()))

    assert record.sources[0].kind is SourceKind.SPREADSHEET


def test_record_allows_empty_revision_only_for_transient_draft_or_imported() -> None:
    assert _record(revision_id="").revision_id == ""
    assert _record(revision_id="", status=MaterialStatus.IMPORTED).revision_id == ""

    with pytest.raises(ValueError, match="revision_id"):
        _record(
            revision_id="",
            status=MaterialStatus.REVIEWED,
            reviewed_by="reviewer@example.com",
        )


@pytest.mark.parametrize("revision_id", ["short", "0123456789AB", "0123456789ag"])
def test_record_requires_twelve_lowercase_hex_revision(revision_id: str) -> None:
    with pytest.raises(ValueError, match="revision_id"):
        _record(revision_id=revision_id)
