from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import replace

import pytest

from inductor_designer.adapters.materials import (
    ImportedMaterialDraft,
    MaterialTemplateDownload,
    import_material_file_as_draft,
    material_import_template,
)
from inductor_designer.application.services.material_drafts import (
    MaterialDraftSession,
    approve_material_session,
    clone_revision_as_draft,
    replace_table_series,
    review_material_session,
    save_material_session,
    session_from_upload,
)
from inductor_designer.application.services.material_import import (
    MaterialImportError,
    approve_material,
    new_draft_record,
    review_material,
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
from inductor_designer.materials.serde import revision_id_for, sha256_hex
from tests.fakes.material_repository import InMemoryMaterialRepository

_CREATED_AT = "2026-07-19T08:00:00+00:00"


def _uploaded_draft() -> tuple[MaterialTemplateDownload, ImportedMaterialDraft]:
    template = material_import_template("csv")
    return template, import_material_file_as_draft(
        template.filename,
        template.data,
        created_at=_CREATED_AT,
        notes="Uploaded in Material Studio",
    )


def _approved_repository() -> tuple[
    InMemoryMaterialRepository,
    MaterialRecord,
    tuple[tuple[str, bytes], ...],
]:
    _, imported = _uploaded_draft()
    approved = approve_material(
        review_material(imported.record, "reviewer@example.com"),
        "approver@example.com",
    )
    repository = InMemoryMaterialRepository()
    repository.save(approved, dict(imported.source_files))
    return repository, approved, imported.source_files


def _external_source_session(*, shared: bool) -> MaterialDraftSession:
    data = b"x,y\n0.0,0.0\n100.0,0.2\n"
    source = SourceProvenance(
        kind=SourceKind.CSV,
        filename="shared.csv" if shared else "external.csv",
        sha256=sha256_hex(data),
        url="https://example.com/source.csv",
        page=None,
        captured_at=_CREATED_AT,
        description="External source",
    )
    conditions = CurveConditions(None, 25.0, None)
    points = (CurvePoint(0.0, 0.0), CurvePoint(100.0, 0.2))
    target = PointSeries(
        series_id="bh-first",
        kind=SeriesKind.BH_CURVE,
        x_unit="A/m",
        y_unit="T",
        conditions=conditions,
        points=points,
        source_filename=source.filename,
        extraction=None,
    )
    sibling = replace(target, series_id="bh-second")
    record = new_draft_record(
        MaterialRef("Example", "Ferrite", "External"),
        series=(target, sibling) if shared else (target,),
        sources=(source,),
        created_at=_CREATED_AT,
    )
    return MaterialDraftSession(record, ((source.filename, data),), None)


def test_session_from_upload_wraps_existing_import_result_exactly() -> None:
    template, imported = _uploaded_draft()

    session = session_from_upload(
        template.filename,
        template.data,
        created_at=_CREATED_AT,
        notes="Uploaded in Material Studio",
    )

    assert session.record == imported.record
    assert session.source_files == imported.source_files
    assert session.base_revision_id is None


@pytest.mark.parametrize("status", [MaterialStatus.REVIEWED, MaterialStatus.APPROVED])
def test_clone_revision_resets_lifecycle_and_retains_exact_sources(
    status: MaterialStatus,
) -> None:
    _, imported = _uploaded_draft()
    stored = review_material(imported.record, "reviewer@example.com")
    if status is MaterialStatus.APPROVED:
        stored = approve_material(stored, "approver@example.com")
    repository = InMemoryMaterialRepository()
    repository.save(stored, dict(imported.source_files))
    base_before = deepcopy(stored)

    session = clone_revision_as_draft(
        repository,
        stored.ref,
        stored.revision_id,
    )

    assert session.record.status is MaterialStatus.DRAFT
    assert session.record.reviewed_by is None
    assert session.record.approved_by is None
    assert session.record.revision_id == stored.revision_id
    assert session.source_files == imported.source_files
    assert session.base_revision_id == stored.revision_id
    assert repository.get(stored.ref, stored.revision_id) == base_before


def test_unchanged_approved_clone_cannot_be_saved_or_overwrite_base() -> None:
    repository, approved, _ = _approved_repository()
    session = clone_revision_as_draft(repository, approved.ref, approved.revision_id)
    before = repository.get(approved.ref, approved.revision_id)

    with pytest.raises(MaterialImportError, match="edited"):
        save_material_session(repository, session)

    assert repository.get(approved.ref, approved.revision_id) == before
    with pytest.raises(ValueError, match="immutable"):
        repository.save(session.record, dict(session.source_files))
    assert repository.get(approved.ref, approved.revision_id) == before


def test_replace_table_series_renames_generated_source_and_retains_upload() -> None:
    repository, approved, _ = _approved_repository()
    session = clone_revision_as_draft(repository, approved.ref, approved.revision_id)
    session_before = deepcopy(session)
    base_before = repository.get(approved.ref, approved.revision_id)
    upload_name = session.record.sources[0].filename
    upload_bytes = dict(session.source_files)[upload_name]
    old_source = next(
        series.source_filename
        for series in session.record.series
        if series.series_id == "bh-25c"
    )
    retained_provenance = {
        source.filename: source
        for source in session.record.sources
        if source.filename != old_source
    }
    retained_files = {
        name: data for name, data in session.source_files if name != old_source
    }
    points = (
        CurvePoint(0.0, 0.0),
        CurvePoint(79.577471546, 0.12),
    )

    edited = replace_table_series(
        session,
        "bh-25c",
        series_id="bh room",
        kind=SeriesKind.BH_CURVE,
        x_unit="Oe",
        y_unit="kG",
        conditions=CurveConditions(None, 30.0, None),
        points=points,
    )

    replacement = next(series for series in edited.record.series if series.series_id == "bh room")
    expected_bytes = b"x,y\n0.0,0.0\n1.0000000000006575,1.2\n"
    assert replacement.points == points
    assert replacement.source_filename == "series-bh_room.csv"
    assert dict(edited.source_files)[replacement.source_filename] == expected_bytes
    replacement_source = next(
        source for source in edited.record.sources if source.filename == replacement.source_filename
    )
    assert replacement_source.sha256 == sha256_hex(expected_bytes)
    assert old_source not in {source.filename for source in edited.record.sources}
    assert old_source not in dict(edited.source_files)
    assert {
        source.filename: source
        for source in edited.record.sources
        if source.filename != replacement.source_filename
    } == retained_provenance
    assert {
        name: data
        for name, data in edited.source_files
        if name != replacement.source_filename
    } == retained_files
    assert dict(edited.source_files)[upload_name] == upload_bytes
    assert edited.record.sources[0] == session.record.sources[0]
    assert edited.record.status is MaterialStatus.DRAFT
    assert edited.record.reviewed_by is None
    assert edited.record.approved_by is None
    assert edited.record.revision_id == revision_id_for(edited.record)
    assert edited.record.revision_id != approved.revision_id
    assert edited.base_revision_id == approved.revision_id
    assert session == session_before
    assert repository.get(approved.ref, approved.revision_id) == base_before

    saved = save_material_session(repository, edited)
    assert saved is edited
    assert repository.get(edited.record.ref, edited.record.revision_id) == edited.record
    assert repository.get(approved.ref, approved.revision_id) == base_before


def test_replace_loss_series_recomputes_fit_and_revision() -> None:
    _, imported = _uploaded_draft()
    session = session_from_upload(
        "material-import-template.csv",
        material_import_template("csv").data,
        created_at=_CREATED_AT,
        notes="Uploaded in Material Studio",
    )
    old_fit = session.record.steinmetz

    edited = replace_table_series(
        session,
        "loss-100khz",
        series_id="loss-100khz",
        kind=SeriesKind.LOSS_TABLE,
        x_unit="kG",
        y_unit="mW/cm3",
        conditions=CurveConditions(100_000.0, 25.0, 0.0),
        points=(CurvePoint(0.05, 120_000.0), CurvePoint(0.1, 300_000.0)),
    )

    assert imported.record.steinmetz == old_fit
    assert edited.record.steinmetz is not None
    assert edited.record.steinmetz != old_fit
    assert edited.record.revision_id != session.record.revision_id


def test_replace_table_series_retains_direct_external_source() -> None:
    session = _external_source_session(shared=False)
    source = session.record.sources[0]
    source_bytes = session.source_files[0][1]

    edited = replace_table_series(
        session,
        "bh-first",
        series_id="bh-edited",
        kind=SeriesKind.BH_CURVE,
        x_unit="A/m",
        y_unit="T",
        conditions=CurveConditions(None, 30.0, None),
        points=(CurvePoint(0.0, 0.0), CurvePoint(200.0, 0.3)),
    )

    assert source in edited.record.sources
    assert dict(edited.source_files)[source.filename] == source_bytes
    replacement = next(item for item in edited.record.series if item.series_id == "bh-edited")
    assert replacement.source_filename == "series-bh_edited.csv"
    assert replacement.source_filename in {item.filename for item in edited.record.sources}
    assert replacement.source_filename in dict(edited.source_files)


def test_replace_table_series_retains_source_shared_by_sibling() -> None:
    session = _external_source_session(shared=True)
    source = session.record.sources[0]
    source_bytes = session.source_files[0][1]

    edited = replace_table_series(
        session,
        "bh-first",
        series_id="bh-edited",
        kind=SeriesKind.BH_CURVE,
        x_unit="A/m",
        y_unit="T",
        conditions=CurveConditions(None, 30.0, None),
        points=(CurvePoint(0.0, 0.0), CurvePoint(200.0, 0.3)),
    )

    sibling = next(item for item in edited.record.series if item.series_id == "bh-second")
    replacement = next(item for item in edited.record.series if item.series_id == "bh-edited")
    assert sibling.source_filename == source.filename
    assert source in edited.record.sources
    assert dict(edited.source_files)[source.filename] == source_bytes
    assert replacement.source_filename == "series-bh_edited.csv"
    assert replacement.source_filename in {item.filename for item in edited.record.sources}
    assert replacement.source_filename in dict(edited.source_files)


@pytest.mark.parametrize("status", [MaterialStatus.REVIEWED, MaterialStatus.APPROVED])
def test_replace_table_series_requires_a_draft_session(status: MaterialStatus) -> None:
    template = material_import_template("csv")
    repository = InMemoryMaterialRepository()
    draft = session_from_upload(template.filename, template.data, created_at=_CREATED_AT)
    save_material_session(repository, draft)
    session = review_material_session(repository, draft, "reviewer@example.com")
    if status is MaterialStatus.APPROVED:
        session = approve_material_session(repository, session, "approver@example.com")
    stored_before = repository.get(session.record.ref, session.record.revision_id)

    with pytest.raises(MaterialImportError, match="draft"):
        replace_table_series(
            session,
            "bh-25c",
            series_id="bh-30c",
            kind=SeriesKind.BH_CURVE,
            x_unit="A/m",
            y_unit="T",
            conditions=CurveConditions(None, 30.0, None),
            points=(CurvePoint(0.0, 0.0), CurvePoint(100.0, 0.2)),
        )

    assert repository.get(session.record.ref, session.record.revision_id) == stored_before
    assert session.record.status is status


@pytest.mark.parametrize(
    ("target_series_id", "series_id", "message"),
    [
        ("missing", "replacement", "does not exist"),
        ("bh-25c", "loss-100khz", "already exists"),
        ("bh-25c", "loss 100khz", "collides"),
    ],
)
def test_replace_table_series_rejects_missing_target_or_id_collision(
    target_series_id: str,
    series_id: str,
    message: str,
) -> None:
    template = material_import_template("csv")
    session = session_from_upload(template.filename, template.data, created_at=_CREATED_AT)
    before = deepcopy(session)

    with pytest.raises(MaterialImportError, match=message):
        replace_table_series(
            session,
            target_series_id,
            series_id=series_id,
            kind=SeriesKind.BH_CURVE,
            x_unit="A/m",
            y_unit="T",
            conditions=CurveConditions(None, 25.0, None),
            points=(CurvePoint(0.0, 0.0), CurvePoint(100.0, 0.2)),
        )

    assert session == before


def test_save_review_and_approve_persist_each_immutable_session() -> None:
    template = material_import_template("csv")
    repository = InMemoryMaterialRepository()
    draft = session_from_upload(template.filename, template.data, created_at=_CREATED_AT)

    saved = save_material_session(repository, draft)
    assert save_material_session(repository, saved) is saved
    reviewed = review_material_session(repository, saved, "reviewer@example.com")
    approved = approve_material_session(repository, reviewed, "approver@example.com")

    assert saved is draft
    assert reviewed.record.status is MaterialStatus.REVIEWED
    assert reviewed.record.reviewed_by == "reviewer@example.com"
    assert approved.record.status is MaterialStatus.APPROVED
    assert approved.record.approved_by == "approver@example.com"
    assert approved.record.revision_id == draft.record.revision_id
    assert approved.source_files == draft.source_files
    assert approved.base_revision_id is None
    assert repository.get(approved.record.ref, approved.record.revision_id) == approved.record
    assert draft.record.status is MaterialStatus.DRAFT
    assert saved.record.status is MaterialStatus.DRAFT
    assert reviewed.record.approved_by is None


def test_stale_draft_save_cannot_revert_a_reviewed_revision() -> None:
    template = material_import_template("csv")
    repository = InMemoryMaterialRepository()
    draft = session_from_upload(template.filename, template.data, created_at=_CREATED_AT)
    save_material_session(repository, draft)
    reviewed = review_material_session(repository, draft, "reviewer@example.com")

    with pytest.raises(MaterialImportError, match="current saved draft"):
        save_material_session(repository, draft)

    assert repository.get(reviewed.record.ref, reviewed.record.revision_id) == reviewed.record


@pytest.mark.parametrize("status", [MaterialStatus.REVIEWED, MaterialStatus.APPROVED])
def test_save_material_session_rejects_non_draft_status(status: MaterialStatus) -> None:
    template = material_import_template("csv")
    repository = InMemoryMaterialRepository()
    draft = session_from_upload(template.filename, template.data, created_at=_CREATED_AT)
    save_material_session(repository, draft)
    session = review_material_session(repository, draft, "reviewer@example.com")
    if status is MaterialStatus.APPROVED:
        session = approve_material_session(repository, session, "approver@example.com")
    stored_before = repository.get(session.record.ref, session.record.revision_id)

    with pytest.raises(MaterialImportError, match="draft"):
        save_material_session(repository, session)

    assert repository.get(session.record.ref, session.record.revision_id) == stored_before


def test_review_requires_the_current_draft_to_be_saved() -> None:
    template = material_import_template("csv")
    repository = InMemoryMaterialRepository()
    session = session_from_upload(template.filename, template.data, created_at=_CREATED_AT)

    with pytest.raises(MaterialImportError, match="saved draft"):
        review_material_session(repository, session, "reviewer@example.com")

    assert repository.list_revisions(session.record.ref) == ()
    assert session.record.status is MaterialStatus.DRAFT


def test_approval_requires_the_current_reviewed_revision_to_be_saved() -> None:
    template = material_import_template("csv")
    repository = InMemoryMaterialRepository()
    draft = session_from_upload(template.filename, template.data, created_at=_CREATED_AT)
    save_material_session(repository, draft)
    transient_reviewed = replace(
        draft,
        record=review_material(draft.record, "reviewer@example.com"),
    )

    with pytest.raises(MaterialImportError, match="saved reviewed"):
        approve_material_session(repository, transient_reviewed, "approver@example.com")

    assert repository.get(draft.record.ref, draft.record.revision_id) == draft.record
    assert transient_reviewed.record.status is MaterialStatus.REVIEWED


@pytest.mark.parametrize("actor", ["", "   "])
def test_lifecycle_rejects_blank_actors_without_repository_changes(actor: str) -> None:
    template = material_import_template("csv")
    repository = InMemoryMaterialRepository()
    saved = save_material_session(
        repository,
        session_from_upload(template.filename, template.data, created_at=_CREATED_AT),
    )
    revisions_before = repository.list_revisions(saved.record.ref)
    stored_before = repository.get(saved.record.ref, saved.record.revision_id)

    with pytest.raises(MaterialImportError, match="Reviewer"):
        review_material_session(repository, saved, actor)

    reviewed = review_material_session(repository, saved, "reviewer@example.com")
    reviewed_before = repository.get(reviewed.record.ref, reviewed.record.revision_id)
    with pytest.raises(MaterialImportError, match="Approver"):
        approve_material_session(repository, reviewed, actor)

    assert repository.list_revisions(saved.record.ref) == revisions_before
    assert stored_before.status is MaterialStatus.DRAFT
    assert repository.get(reviewed.record.ref, reviewed.record.revision_id) == reviewed_before
    assert reviewed_before.status is MaterialStatus.REVIEWED
    assert saved.record.status is MaterialStatus.DRAFT
    assert reviewed.record.status is MaterialStatus.REVIEWED


class _RejectingSaveRepository(InMemoryMaterialRepository):
    reject_save = False

    def save(self, record: MaterialRecord, sources: Mapping[str, bytes]) -> None:
        if self.reject_save:
            raise RuntimeError("repository rejected save")
        super().save(record, sources)


def test_failed_save_review_and_approval_leave_session_and_repository_unchanged() -> None:
    template = material_import_template("csv")
    repository = _RejectingSaveRepository()
    draft = session_from_upload(template.filename, template.data, created_at=_CREATED_AT)
    draft_before = deepcopy(draft)
    repository.reject_save = True

    with pytest.raises(RuntimeError, match="rejected"):
        save_material_session(repository, draft)

    assert repository.list_revisions(draft.record.ref) == ()
    assert draft == draft_before

    repository.reject_save = False
    save_material_session(repository, draft)
    stored_draft = repository.get(draft.record.ref, draft.record.revision_id)
    repository.reject_save = True
    with pytest.raises(RuntimeError, match="rejected"):
        review_material_session(repository, draft, "reviewer@example.com")
    assert repository.get(draft.record.ref, draft.record.revision_id) == stored_draft
    assert draft == draft_before

    repository.reject_save = False
    reviewed = review_material_session(repository, draft, "reviewer@example.com")
    reviewed_before = deepcopy(reviewed)
    stored_reviewed = repository.get(reviewed.record.ref, reviewed.record.revision_id)
    repository.reject_save = True
    with pytest.raises(RuntimeError, match="rejected"):
        approve_material_session(repository, reviewed, "approver@example.com")
    assert repository.get(reviewed.record.ref, reviewed.record.revision_id) == stored_reviewed
    assert reviewed == reviewed_before
