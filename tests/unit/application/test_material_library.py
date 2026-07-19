from __future__ import annotations

from inductor_designer.application.services.material_library import (
    MaterialRevisionSummary,
    list_material_revision_summaries,
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
)
from inductor_designer.materials.serde import sha256_hex
from tests.fakes.material_repository import InMemoryMaterialRepository

_REF = MaterialRef("ACME", "Ferrite", "N87")
_SOURCE = b"h,b\n0,0\n100,0.2\n"


def _record(
    revision_id: str,
    status: MaterialStatus,
    created_at: str,
    *,
    warning: bool = False,
) -> MaterialRecord:
    reviewed_by = "reviewer@example.com" if status is not MaterialStatus.DRAFT else None
    approved_by = "approver@example.com" if status is MaterialStatus.APPROVED else None
    final_point = CurvePoint(1_000_000.0, 0.2) if warning else CurvePoint(100.0, 0.2)
    return MaterialRecord(
        ref=_REF,
        revision_id=revision_id,
        status=status,
        created_at=created_at,
        reviewed_by=reviewed_by,
        approved_by=approved_by,
        sources=(
            SourceProvenance(
                kind=SourceKind.CSV,
                filename="bh-source.csv",
                sha256=sha256_hex(_SOURCE),
                url="https://example.com/bh.csv",
                page=None,
                captured_at="2026-07-17T07:00:00+00:00",
                description="B-H source points",
            ),
        ),
        series=(
            PointSeries(
                series_id="bh-room-temperature",
                kind=SeriesKind.BH_CURVE,
                x_unit="A/m",
                y_unit="T",
                conditions=CurveConditions(None, 25.0, None),
                points=(CurvePoint(0.0, 0.0), final_point),
                source_filename="bh-source.csv",
                extraction=None,
            ),
        ),
        relative_permeability=1600.0,
        steinmetz=None,
        notes="Library fixture",
    )


def test_list_material_revision_summaries_is_newest_first_and_read_only() -> None:
    repository = InMemoryMaterialRepository()
    draft = _record("aaaaaaaaaaaa", MaterialStatus.DRAFT, "2026-07-17T10:00:00+02:00")
    reviewed = _record(
        "bbbbbbbbbbbb",
        MaterialStatus.REVIEWED,
        "2026-07-17T08:30:00+00:00",
    )
    approved = _record(
        "cccccccccccc",
        MaterialStatus.APPROVED,
        "2026-07-17T08:00:00+00:00",
        warning=True,
    )
    for record in (draft, reviewed, approved):
        repository.save(record, {"bh-source.csv": _SOURCE})
    revisions_before = repository.list_revisions(_REF)
    records_before = tuple(repository.get(_REF, revision) for revision in revisions_before)

    summaries = list_material_revision_summaries(repository, _REF)

    assert summaries == (
        MaterialRevisionSummary(
            ref=_REF,
            revision_id=reviewed.revision_id,
            status=MaterialStatus.REVIEWED,
            created_at=reviewed.created_at,
            reviewed_by="reviewer@example.com",
            approved_by=None,
            series_count=1,
            validation_errors=0,
            validation_warnings=0,
            is_latest_approved=False,
        ),
        MaterialRevisionSummary(
            ref=_REF,
            revision_id=approved.revision_id,
            status=MaterialStatus.APPROVED,
            created_at=approved.created_at,
            reviewed_by="reviewer@example.com",
            approved_by="approver@example.com",
            series_count=1,
            validation_errors=0,
            validation_warnings=1,
            is_latest_approved=True,
        ),
        MaterialRevisionSummary(
            ref=_REF,
            revision_id=draft.revision_id,
            status=MaterialStatus.DRAFT,
            created_at=draft.created_at,
            reviewed_by=None,
            approved_by=None,
            series_count=1,
            validation_errors=0,
            validation_warnings=0,
            is_latest_approved=False,
        ),
    )
    assert sum(summary.is_latest_approved for summary in summaries) == 1
    assert repository.list_revisions(_REF) == revisions_before
    assert tuple(repository.get(_REF, revision) for revision in revisions_before) == records_before
    assert repository.latest_approved(_REF) == approved
