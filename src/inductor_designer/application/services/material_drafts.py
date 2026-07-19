from __future__ import annotations

from dataclasses import dataclass, replace

from inductor_designer.application.ports.material_repository import (
    MaterialLookupError,
    MaterialRepository,
)
from inductor_designer.application.services.material_import import (
    MaterialImportError,
    approve_material,
    import_curve_csv,
    new_draft_record,
    review_material,
)
from inductor_designer.domain.units import from_canonical
from inductor_designer.geometry.naming import sanitize_identifier
from inductor_designer.materials.calibration import ExtractionRecord, extract_points
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
from inductor_designer.materials.serde import canonicalize_points, revision_id_for, sha256_hex
from inductor_designer.materials.validation import validate_series


@dataclass(frozen=True, slots=True)
class MaterialDraftSession:
    record: MaterialRecord
    source_files: tuple[tuple[str, bytes], ...]
    base_revision_id: str | None


@dataclass(frozen=True, slots=True)
class ImageSeriesInput:
    ref: MaterialRef
    source_filename: str
    source_data: bytes
    source_url: str
    source_page: int | None
    captured_at: str
    source_description: str
    series_id: str
    kind: SeriesKind
    x_unit: str
    y_unit: str
    conditions: CurveConditions
    extraction: ExtractionRecord
    created_at: str
    notes: str = ""


def _image_series(
    *,
    series_id: str,
    kind: SeriesKind,
    x_unit: str,
    y_unit: str,
    conditions: CurveConditions,
    source_filename: str,
    extraction: ExtractionRecord,
) -> PointSeries:
    series = PointSeries(
        series_id=series_id,
        kind=kind,
        x_unit=x_unit,
        y_unit=y_unit,
        conditions=conditions,
        points=canonicalize_points(extract_points(extraction), x_unit, y_unit),
        source_filename=source_filename,
        extraction=extraction,
    )
    if messages := tuple(
        issue.message for issue in validate_series(series) if issue.code == "unit-family"
    ):
        raise MaterialImportError(messages)
    return series


def image_draft_session(input_data: ImageSeriesInput) -> MaterialDraftSession:
    provenance = SourceProvenance(
        kind=SourceKind.IMAGE,
        filename=input_data.source_filename,
        sha256=sha256_hex(input_data.source_data),
        url=input_data.source_url,
        page=input_data.source_page,
        captured_at=input_data.captured_at,
        description=input_data.source_description,
    )
    series = _image_series(
        series_id=input_data.series_id,
        kind=input_data.kind,
        x_unit=input_data.x_unit,
        y_unit=input_data.y_unit,
        conditions=input_data.conditions,
        source_filename=input_data.source_filename,
        extraction=input_data.extraction,
    )
    record = new_draft_record(
        input_data.ref,
        series=(series,),
        sources=(provenance,),
        created_at=input_data.created_at,
        notes=input_data.notes,
    )
    return MaterialDraftSession(
        record,
        ((input_data.source_filename, input_data.source_data),),
        None,
    )


def _image_target(
    session: MaterialDraftSession,
    series_id: str,
) -> PointSeries:
    if session.record.status is not MaterialStatus.DRAFT:
        raise MaterialImportError(("Image extraction can only be edited in a draft session.",))
    target = next((item for item in session.record.series if item.series_id == series_id), None)
    if target is None:
        raise MaterialImportError((f"Series '{series_id}' does not exist.",))
    provenance = next(
        (
            source
            for source in session.record.sources
            if source.filename == target.source_filename
        ),
        None,
    )
    if provenance is None or provenance.kind is not SourceKind.IMAGE:
        raise MaterialImportError((f"Series '{series_id}' is not backed by an image source.",))
    if not any(name == target.source_filename for name, _ in session.source_files):
        raise MaterialImportError((f"Series '{series_id}' source bytes do not exist.",))
    return target


def _require_draft(session: MaterialDraftSession, action: str) -> None:
    if session.record.status is not MaterialStatus.DRAFT:
        raise MaterialImportError((f"{action} can only be edited in a draft session.",))


def _new_series_id(session: MaterialDraftSession, series_id: str) -> str:
    if not series_id.strip():
        raise MaterialImportError(("Series ID must not be blank.",))
    if any(item.series_id == series_id for item in session.record.series):
        raise MaterialImportError((f"Series ID '{series_id}' already exists.",))
    sanitized_id = sanitize_identifier(series_id)
    if any(
        sanitize_identifier(item.series_id).casefold() == sanitized_id.casefold()
        for item in session.record.series
    ):
        raise MaterialImportError((f"Series ID '{series_id}' collides after sanitizing.",))
    return sanitized_id


def _rebuild_session(
    session: MaterialDraftSession,
    *,
    series: tuple[PointSeries, ...],
    sources: tuple[SourceProvenance, ...],
    source_files: tuple[tuple[str, bytes], ...],
) -> MaterialDraftSession:
    draft = new_draft_record(
        session.record.ref,
        series=series,
        sources=sources,
        created_at=session.record.created_at,
        relative_permeability=session.record.relative_permeability,
        notes=session.record.notes,
    )
    return MaterialDraftSession(draft, source_files, session.base_revision_id)


def add_table_series(
    session: MaterialDraftSession,
    *,
    series_id: str,
    kind: SeriesKind,
    x_unit: str,
    y_unit: str,
    conditions: CurveConditions,
    points: tuple[CurvePoint, ...],
    captured_at: str,
) -> MaterialDraftSession:
    """Add a direct-edit series while retaining all existing source evidence."""
    _require_draft(session, "Table series")
    sanitized_id = _new_series_id(session, series_id)
    source_filename = f"series-{sanitized_id}.csv"
    if any(
        sanitize_identifier(source.filename).casefold()
        == sanitize_identifier(source_filename).casefold()
        for source in session.record.sources
    ):
        raise MaterialImportError(
            (f"Generated source filename '{source_filename}' collides with retained provenance.",)
        )
    raw_rows = tuple(
        (from_canonical(point.x, x_unit), from_canonical(point.y, y_unit))
        for point in points
    )
    source_text = "x,y\n" + "".join(f"{x!r},{y!r}\n" for x, y in raw_rows)
    source_bytes = source_text.encode()
    provenance = SourceProvenance(
        kind=SourceKind.CSV,
        filename=source_filename,
        sha256=sha256_hex(source_bytes),
        url="",
        page=None,
        captured_at=captured_at,
        description="Material Studio direct table series",
    )
    added = import_curve_csv(
        source_text,
        series_id=series_id,
        kind=kind,
        x_unit=x_unit,
        y_unit=y_unit,
        conditions=conditions,
        source=provenance,
    )
    return _rebuild_session(
        session,
        series=(*session.record.series, added),
        sources=(*session.record.sources, provenance),
        source_files=(*session.source_files, (source_filename, source_bytes)),
    )


def add_image_series(
    session: MaterialDraftSession,
    *,
    source_filename: str,
    series_id: str,
    kind: SeriesKind,
    x_unit: str,
    y_unit: str,
    conditions: CurveConditions,
    extraction: ExtractionRecord,
) -> MaterialDraftSession:
    """Add another manually digitized series from an existing image/PDF source."""
    _require_draft(session, "Image series")
    _new_series_id(session, series_id)
    provenance = next(
        (source for source in session.record.sources if source.filename == source_filename),
        None,
    )
    if provenance is None or provenance.kind is not SourceKind.IMAGE:
        raise MaterialImportError((f"Image source '{source_filename}' does not exist.",))
    if not any(name == source_filename for name, _ in session.source_files):
        raise MaterialImportError((f"Image source '{source_filename}' bytes do not exist.",))
    added = _image_series(
        series_id=series_id,
        kind=kind,
        x_unit=x_unit,
        y_unit=y_unit,
        conditions=conditions,
        source_filename=source_filename,
        extraction=extraction,
    )
    return _rebuild_session(
        session,
        series=(*session.record.series, added),
        sources=session.record.sources,
        source_files=session.source_files,
    )


def remove_series(
    session: MaterialDraftSession,
    series_id: str,
) -> MaterialDraftSession:
    """Remove one series and only its unreferenced generated CSV artifact."""
    _require_draft(session, "Material series")
    target = next(
        (item for item in session.record.series if item.series_id == series_id),
        None,
    )
    if target is None:
        raise MaterialImportError((f"Series '{series_id}' does not exist.",))
    if len(session.record.series) == 1:
        raise MaterialImportError(("Cannot remove the final material series.",))
    retained_series = tuple(
        item for item in session.record.series if item.series_id != series_id
    )
    provenance = next(
        (
            source
            for source in session.record.sources
            if source.filename == target.source_filename
        ),
        None,
    )
    generated_filename = f"series-{sanitize_identifier(series_id)}.csv"
    remove_generated_source = (
        provenance is not None
        and provenance.kind is SourceKind.CSV
        and target.source_filename == generated_filename
        and not any(
            item.source_filename == target.source_filename for item in retained_series
        )
    )
    sources = tuple(
        source
        for source in session.record.sources
        if not remove_generated_source or source.filename != target.source_filename
    )
    source_files = tuple(
        (name, data)
        for name, data in session.source_files
        if not remove_generated_source or name != target.source_filename
    )
    return _rebuild_session(
        session,
        series=retained_series,
        sources=sources,
        source_files=source_files,
    )


def replace_image_series(
    session: MaterialDraftSession,
    target_series_id: str,
    *,
    series_id: str,
    kind: SeriesKind,
    x_unit: str,
    y_unit: str,
    conditions: CurveConditions,
    extraction: ExtractionRecord,
) -> MaterialDraftSession:
    target = _image_target(session, target_series_id)
    if not series_id.strip():
        raise MaterialImportError(("Replacement series ID must not be blank.",))
    other_series = tuple(
        item for item in session.record.series if item.series_id != target_series_id
    )
    if any(item.series_id == series_id for item in other_series):
        raise MaterialImportError((f"Series ID '{series_id}' already exists.",))
    sanitized_id = sanitize_identifier(series_id)
    if any(
        sanitize_identifier(item.series_id).casefold() == sanitized_id.casefold()
        for item in other_series
    ):
        raise MaterialImportError(
            (f"Series ID '{series_id}' collides after sanitizing.",)
        )

    replacement = _image_series(
        series_id=series_id,
        kind=kind,
        x_unit=x_unit,
        y_unit=y_unit,
        conditions=conditions,
        source_filename=target.source_filename,
        extraction=extraction,
    )
    series = tuple(
        replacement if item.series_id == target_series_id else item
        for item in session.record.series
    )
    draft = new_draft_record(
        session.record.ref,
        series=series,
        sources=session.record.sources,
        created_at=session.record.created_at,
        relative_permeability=session.record.relative_permeability,
        notes=session.record.notes,
    )
    return MaterialDraftSession(draft, session.source_files, session.base_revision_id)


def replace_image_extraction(
    session: MaterialDraftSession,
    series_id: str,
    extraction: ExtractionRecord,
) -> MaterialDraftSession:
    target = _image_target(session, series_id)
    return replace_image_series(
        session,
        series_id,
        series_id=target.series_id,
        kind=target.kind,
        x_unit=target.x_unit,
        y_unit=target.y_unit,
        conditions=target.conditions,
        extraction=extraction,
    )


def session_from_import(
    record: MaterialRecord,
    source_files: tuple[tuple[str, bytes], ...],
) -> MaterialDraftSession:
    """Wrap format-neutral imported material data in a draft session."""
    return MaterialDraftSession(record, source_files, None)


def clone_revision_as_draft(
    repository: MaterialRepository,
    ref: MaterialRef,
    revision_id: str,
    *,
    created_at: str,
) -> MaterialDraftSession:
    stored = repository.get(ref, revision_id)
    draft = replace(
        stored,
        status=MaterialStatus.DRAFT,
        created_at=created_at,
        reviewed_by=None,
        approved_by=None,
    )
    return MaterialDraftSession(
        draft,
        tuple(repository.source_bytes(ref, revision_id).items()),
        revision_id,
    )


def replace_table_series(
    session: MaterialDraftSession,
    target_series_id: str,
    *,
    series_id: str,
    kind: SeriesKind,
    x_unit: str,
    y_unit: str,
    conditions: CurveConditions,
    points: tuple[CurvePoint, ...],
) -> MaterialDraftSession:
    if session.record.status is not MaterialStatus.DRAFT:
        raise MaterialImportError(("Table series can only be edited in a draft session.",))
    target = next(
        (item for item in session.record.series if item.series_id == target_series_id),
        None,
    )
    if target is None:
        raise MaterialImportError((f"Series '{target_series_id}' does not exist.",))
    if not series_id.strip():
        raise MaterialImportError(("Replacement series ID must not be blank.",))

    other_series = tuple(
        item for item in session.record.series if item.series_id != target_series_id
    )
    if any(item.series_id == series_id for item in other_series):
        raise MaterialImportError((f"Series ID '{series_id}' already exists.",))
    sanitized_id = sanitize_identifier(series_id)
    if any(
        sanitize_identifier(item.series_id).casefold() == sanitized_id.casefold()
        for item in other_series
    ):
        raise MaterialImportError(
            (f"Series ID '{series_id}' collides after sanitizing.",)
        )

    old_provenance = next(
        (
            source
            for source in session.record.sources
            if source.filename == target.source_filename
        ),
        None,
    )
    if old_provenance is None:
        raise MaterialImportError(
            (f"Series '{target_series_id}' source provenance does not exist.",)
        )
    if not any(name == target.source_filename for name, _ in session.source_files):
        raise MaterialImportError(
            (f"Series '{target_series_id}' source bytes do not exist.",)
        )

    disposable_filename = f"series-{sanitize_identifier(target_series_id)}.csv"
    disposable_source = (
        target.source_filename == disposable_filename
        and old_provenance.kind is SourceKind.CSV
        and not any(
            item.source_filename == target.source_filename for item in other_series
        )
    )
    source_filename = f"series-{sanitized_id}.csv"
    retained_sources = tuple(
        source
        for source in session.record.sources
        if not disposable_source or source.filename != target.source_filename
    )
    if any(
        sanitize_identifier(source.filename).casefold()
        == sanitize_identifier(source_filename).casefold()
        for source in retained_sources
    ):
        raise MaterialImportError(
            (f"Generated source filename '{source_filename}' collides with retained provenance.",)
        )

    raw_rows = tuple(
        (from_canonical(point.x, x_unit), from_canonical(point.y, y_unit))
        for point in points
    )
    source_text = "x,y\n" + "".join(f"{x!r},{y!r}\n" for x, y in raw_rows)
    source_bytes = source_text.encode()
    provenance = replace(
        old_provenance,
        kind=SourceKind.CSV,
        filename=source_filename,
        sha256=sha256_hex(source_bytes),
    )
    replacement = import_curve_csv(
        source_text,
        series_id=series_id,
        kind=kind,
        x_unit=x_unit,
        y_unit=y_unit,
        conditions=conditions,
        source=provenance,
    )

    series = tuple(
        replacement if item.series_id == target_series_id else item
        for item in session.record.series
    )
    if disposable_source:
        sources = tuple(
            provenance if source.filename == target.source_filename else source
            for source in session.record.sources
        )
        files = tuple(
            (source_filename, source_bytes)
            if name == target.source_filename
            else (name, data)
            for name, data in session.source_files
        )
    else:
        sources = (*session.record.sources, provenance)
        files = (*session.source_files, (source_filename, source_bytes))

    draft = new_draft_record(
        session.record.ref,
        series=series,
        sources=sources,
        created_at=session.record.created_at,
        relative_permeability=session.record.relative_permeability,
        notes=session.record.notes,
    )
    return MaterialDraftSession(draft, files, session.base_revision_id)


def save_material_session(
    repository: MaterialRepository,
    session: MaterialDraftSession,
) -> MaterialDraftSession:
    if session.record.status is not MaterialStatus.DRAFT:
        raise MaterialImportError(("Only draft material sessions can be saved.",))
    _require_distinct_valid_revision(session)
    try:
        stored = repository.get(session.record.ref, session.record.revision_id)
    except MaterialLookupError:
        pass
    else:
        if stored != session.record:
            raise MaterialImportError(
                ("Material must be the current saved draft before it can be saved.",)
            )
    repository.save(session.record, dict(session.source_files))
    return session


def _require_distinct_valid_revision(session: MaterialDraftSession) -> None:
    if session.base_revision_id == session.record.revision_id:
        raise MaterialImportError(
            ("Cloned material revision must be edited before it can be saved.",)
        )
    computed_revision = revision_id_for(session.record)
    if session.record.revision_id != computed_revision:
        raise MaterialImportError(("Material revision ID does not match its content.",))


def _require_actor(actor: str, role: str) -> None:
    if not actor.strip():
        raise MaterialImportError((f"{role} must not be blank.",))


def _require_stored_session(
    repository: MaterialRepository,
    session: MaterialDraftSession,
    status: MaterialStatus,
) -> None:
    _require_distinct_valid_revision(session)
    try:
        stored = repository.get(session.record.ref, session.record.revision_id)
    except MaterialLookupError as error:
        raise MaterialImportError(
            (f"Material must be a saved {status.value} before this transition.",)
        ) from error
    if stored != session.record or stored.status is not status:
        raise MaterialImportError(
            (f"Material must be the current saved {status.value} before this transition.",)
        )


def review_material_session(
    repository: MaterialRepository,
    session: MaterialDraftSession,
    reviewer: str,
) -> MaterialDraftSession:
    _require_actor(reviewer, "Reviewer")
    _require_stored_session(repository, session, MaterialStatus.DRAFT)
    reviewed = review_material(session.record, reviewer)
    repository.save(reviewed, dict(session.source_files))
    return replace(session, record=reviewed)


def approve_material_session(
    repository: MaterialRepository,
    session: MaterialDraftSession,
    approver: str,
) -> MaterialDraftSession:
    _require_actor(approver, "Approver")
    _require_stored_session(repository, session, MaterialStatus.REVIEWED)
    approved = approve_material(session.record, approver)
    repository.save(approved, dict(session.source_files))
    return replace(session, record=approved)
