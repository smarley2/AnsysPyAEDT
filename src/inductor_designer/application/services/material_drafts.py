from __future__ import annotations

from dataclasses import dataclass, replace

from inductor_designer.adapters.materials import import_material_file_as_draft
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
from inductor_designer.materials.identity import MaterialRef
from inductor_designer.materials.records import (
    CurveConditions,
    CurvePoint,
    MaterialRecord,
    MaterialStatus,
    SeriesKind,
    SourceKind,
)
from inductor_designer.materials.serde import revision_id_for, sha256_hex


@dataclass(frozen=True, slots=True)
class MaterialDraftSession:
    record: MaterialRecord
    source_files: tuple[tuple[str, bytes], ...]
    base_revision_id: str | None


def session_from_upload(
    filename: str,
    data: bytes,
    *,
    created_at: str,
    notes: str = "",
) -> MaterialDraftSession:
    imported = import_material_file_as_draft(
        filename,
        data,
        created_at=created_at,
        notes=notes,
    )
    return MaterialDraftSession(imported.record, imported.source_files, None)


def clone_revision_as_draft(
    repository: MaterialRepository,
    ref: MaterialRef,
    revision_id: str,
) -> MaterialDraftSession:
    stored = repository.get(ref, revision_id)
    draft = replace(
        stored,
        status=MaterialStatus.DRAFT,
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
    computed_revision = revision_id_for(session.record)
    if session.record.revision_id != computed_revision:
        raise MaterialImportError(("Material revision ID does not match its content.",))
    if session.base_revision_id == computed_revision:
        raise MaterialImportError(
            ("Cloned material revision must be edited before it can be saved.",)
        )


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
