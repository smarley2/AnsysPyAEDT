from __future__ import annotations

from dataclasses import replace

from inductor_designer.materials.fitting import LossSample, MaterialFitError, fit_steinmetz
from inductor_designer.materials.identity import MaterialRef
from inductor_designer.materials.records import (
    CurveConditions,
    MaterialRecord,
    MaterialStatus,
    PointSeries,
    SeriesKind,
    SourceProvenance,
    SteinmetzFit,
    approve_record,
    review_record,
)
from inductor_designer.materials.serde import (
    canonicalize_points,
    parse_points_csv,
    revision_id_for,
)
from inductor_designer.materials.validation import (
    IssueSeverity,
    MaterialIssue,
    validate_record,
    validate_series,
)

GENERATED_SERIES_SOURCE_DESCRIPTION = "Material Studio generated per-series CSV"


class MaterialImportError(ValueError):
    def __init__(self, issues: tuple[str, ...]) -> None:
        self.issues = issues
        super().__init__("; ".join(issues))


def _error_messages(issues: tuple[MaterialIssue, ...]) -> tuple[str, ...]:
    return tuple(issue.message for issue in issues if issue.severity is IssueSeverity.ERROR)


def import_curve_csv(
    text: str,
    *,
    series_id: str,
    kind: SeriesKind,
    x_unit: str,
    y_unit: str,
    conditions: CurveConditions,
    source: SourceProvenance,
) -> PointSeries:
    points = canonicalize_points(parse_points_csv(text), x_unit, y_unit)
    series = PointSeries(
        series_id=series_id,
        kind=kind,
        x_unit=x_unit,
        y_unit=y_unit,
        conditions=conditions,
        points=points,
        source_filename=source.filename,
    )
    unit_issues = tuple(issue for issue in validate_series(series) if issue.code == "unit-family")
    if messages := _error_messages(unit_issues):
        raise MaterialImportError(messages)
    return series


def _fit_loss_series(series: tuple[PointSeries, ...]) -> SteinmetzFit | None:
    samples = tuple(
        LossSample(frequency, point.x, point.y)
        for item in series
        if item.kind is SeriesKind.LOSS_TABLE
        if (frequency := item.conditions.frequency_hz) is not None and frequency > 0
        for point in item.points
        if point.x > 0 and point.y > 0
    )
    if (
        len(samples) >= 3
        and len({sample.frequency_hz for sample in samples}) >= 2
        and len({sample.flux_density_t for sample in samples}) >= 2
    ):
        try:
            return fit_steinmetz(samples)
        except MaterialFitError:
            return None
    return None


def new_draft_record(
    ref: MaterialRef,
    *,
    series: tuple[PointSeries, ...],
    sources: tuple[SourceProvenance, ...],
    created_at: str,
    relative_permeability: float | None = None,
    fit_steinmetz_from_losses: bool = True,
    notes: str = "",
) -> MaterialRecord:
    record = MaterialRecord(
        ref=ref,
        revision_id="",
        status=MaterialStatus.DRAFT,
        created_at=created_at,
        reviewed_by=None,
        approved_by=None,
        sources=sources,
        series=series,
        relative_permeability=relative_permeability,
        steinmetz=_fit_loss_series(series) if fit_steinmetz_from_losses else None,
        notes=notes,
    )
    return replace(record, revision_id=revision_id_for(record))


def _validate_transition(record: MaterialRecord) -> None:
    if messages := _error_messages(validate_record(record)):
        raise MaterialImportError(messages)


def review_material(record: MaterialRecord, reviewer: str) -> MaterialRecord:
    _validate_transition(record)
    return review_record(record, reviewer)


def approve_material(record: MaterialRecord, approver: str) -> MaterialRecord:
    _validate_transition(record)
    return approve_record(record, approver)
