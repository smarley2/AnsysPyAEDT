from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from inductor_designer.application.ports.material_repository import MaterialRepository
from inductor_designer.materials.identity import MaterialRef
from inductor_designer.materials.records import MaterialRecord, MaterialStatus
from inductor_designer.materials.validation import IssueSeverity, validate_record


@dataclass(frozen=True, slots=True)
class MaterialRevisionSummary:
    ref: MaterialRef
    revision_id: str
    status: MaterialStatus
    created_at: str
    reviewed_by: str | None
    approved_by: str | None
    series_count: int
    validation_errors: int
    validation_warnings: int
    is_latest_approved: bool


def _summary(
    record: MaterialRecord,
    latest_approved: MaterialRecord | None,
) -> MaterialRevisionSummary:
    issues = validate_record(record)
    return MaterialRevisionSummary(
        ref=record.ref,
        revision_id=record.revision_id,
        status=record.status,
        created_at=record.created_at,
        reviewed_by=record.reviewed_by,
        approved_by=record.approved_by,
        series_count=len(record.series),
        validation_errors=sum(
            issue.severity is IssueSeverity.ERROR for issue in issues
        ),
        validation_warnings=sum(
            issue.severity is IssueSeverity.WARNING for issue in issues
        ),
        is_latest_approved=(
            latest_approved is not None
            and record.ref == latest_approved.ref
            and record.revision_id == latest_approved.revision_id
        ),
    )


def _summary_time_key(summary: MaterialRevisionSummary) -> tuple[float, str]:
    timestamp = datetime.fromisoformat(summary.created_at.replace("Z", "+00:00"))
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return (timestamp.timestamp(), summary.revision_id)


def list_material_revision_summaries(
    repository: MaterialRepository,
    ref: MaterialRef,
) -> tuple[MaterialRevisionSummary, ...]:
    latest = repository.latest_approved(ref)
    summaries = tuple(
        _summary(repository.get(ref, revision), latest)
        for revision in repository.list_revisions(ref)
    )
    return tuple(sorted(summaries, key=_summary_time_key, reverse=True))
