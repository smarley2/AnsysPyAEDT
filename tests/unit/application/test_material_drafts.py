from __future__ import annotations

from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import replace

import pytest

from inductor_designer.adapters.materials import (
    ImportedMaterialDraft,
    MaterialTemplateDownload,
    export_material_record_xlsx,
    import_material_file_as_draft,
    material_import_template,
)
from inductor_designer.application.services.material_drafts import (
    MaterialDraftSession,
    add_table_series,
    approve_material_session,
    clone_revision_as_draft,
    derive_workbook_draft,
    remove_series,
    replace_table_series,
    review_material_session,
    save_material_session,
    session_from_import,
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
from inductor_designer.materials.replay import reproduce_record
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


def _session_from_upload(
    filename: str,
    data: bytes,
    *,
    created_at: str = _CREATED_AT,
    notes: str = "",
) -> MaterialDraftSession:
    imported = import_material_file_as_draft(
        filename,
        data,
        created_at=created_at,
        notes=notes,
    )
    return session_from_import(imported.record, imported.source_files)


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
    filename = "shared.csv" if shared else "external.csv"
    source = SourceProvenance(
        kind=SourceKind.CSV,
        filename=filename,
        sha256=sha256_hex(data),
        url="https://example.com/source.csv",
        page=None,
        captured_at=_CREATED_AT,
        description="External source",
    )
    target = PointSeries(
        series_id="bh-first",
        kind=SeriesKind.BH_CURVE,
        x_unit="A/m",
        y_unit="T",
        conditions=CurveConditions(None, 25.0, None),
        points=(CurvePoint(0.0, 0.0), CurvePoint(100.0, 0.2)),
        source_filename=filename,
    )
    series = (target, replace(target, series_id="bh-second")) if shared else (target,)
    record = new_draft_record(
        MaterialRef("Example", "Ferrite", "External"),
        series=series,
        sources=(source,),
        created_at=_CREATED_AT,
    )
    return MaterialDraftSession(record, ((filename, data),), None)


def test_session_from_import_wraps_existing_import_result_exactly() -> None:
    _, imported = _uploaded_draft()

    session = session_from_import(imported.record, imported.source_files)

    assert session.record == imported.record
    assert session.source_files == imported.source_files
    assert session.base_revision_id is None


def test_session_from_import_rejects_non_draft_record() -> None:
    _, imported = _uploaded_draft()
    reviewed = review_material(imported.record, "reviewer@example.com")

    with pytest.raises(MaterialImportError, match="draft"):
        session_from_import(reviewed, imported.source_files)


def test_session_from_import_rejects_revision_mismatch() -> None:
    _, imported = _uploaded_draft()
    mismatched = replace(imported.record, revision_id="000000000000")

    with pytest.raises(MaterialImportError, match="revision"):
        session_from_import(mismatched, imported.source_files)


@pytest.mark.parametrize(
    ("source_files", "message"),
    [
        (lambda files: files[:-1], "filenames"),
        (lambda files: (*files, ("extra.csv", b"x,y\n")), "filenames"),
        (lambda files: tuple(reversed(files)), "order"),
        (
            lambda files: ((files[0][0], b"changed"), *files[1:]),
            "hash",
        ),
        (lambda files: (*files, files[0]), "filenames"),
    ],
)
def test_session_from_import_rejects_inconsistent_source_files(
    source_files: Callable[
        [tuple[tuple[str, bytes], ...]],
        tuple[tuple[str, bytes], ...],
    ],
    message: str,
) -> None:
    _, imported = _uploaded_draft()

    with pytest.raises(MaterialImportError, match=message):
        session_from_import(imported.record, source_files(imported.source_files))


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
        created_at="2026-07-20T08:00:00+00:00",
    )

    assert session.record.status is MaterialStatus.DRAFT
    assert session.record.reviewed_by is None
    assert session.record.approved_by is None
    assert session.record.created_at == "2026-07-20T08:00:00+00:00"
    assert session.record.revision_id == stored.revision_id
    assert session.source_files == imported.source_files
    assert session.base_revision_id == stored.revision_id
    assert repository.get(stored.ref, stored.revision_id) == base_before


def test_workbook_draft_retains_base_evidence_and_replays() -> None:
    repository, approved, source_files = _approved_repository()
    base_session = MaterialDraftSession(approved, source_files, None)
    exported = export_material_record_xlsx(approved)
    imported = import_material_file_as_draft(
        exported.filename,
        exported.data,
        created_at="2026-07-20T08:00:00+00:00",
    )

    derived = derive_workbook_draft(
        base_session,
        imported.record,
        imported.source_files,
    )

    assert derived.base_revision_id == approved.revision_id
    assert derived.record.sources[: len(approved.sources)] == approved.sources
    assert len(derived.record.sources) == len(
        set(source.filename for source in derived.record.sources)
    )
    assert all(
        item.source_filename not in {source.filename for source in approved.sources}
        for item in derived.record.series
    )
    assert reproduce_record(derived.record, dict(derived.source_files)).matches
    assert repository.get(approved.ref, approved.revision_id) == approved


def test_replace_table_series_renames_generated_source_and_retains_upload() -> None:
    repository, approved, _ = _approved_repository()
    session = clone_revision_as_draft(
        repository,
        approved.ref,
        approved.revision_id,
        created_at="2026-07-20T08:00:00+00:00",
    )
    old_source = session.record.series[0].source_filename
    points = (CurvePoint(0.0, 0.0), CurvePoint(79.577471546, 0.12))

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

    replacement = next(item for item in edited.record.series if item.series_id == "bh room")
    assert replacement.points == points
    assert replacement.source_filename == "series-bh_room.csv"
    assert dict(edited.source_files)[replacement.source_filename].startswith(b"x,y\n")
    assert old_source not in {source.filename for source in edited.record.sources}
    assert "material-import-template.csv" in {
        source.filename for source in edited.record.sources
    }
    assert edited.record.revision_id == revision_id_for(edited.record)
    assert edited.base_revision_id == approved.revision_id
    assert repository.get(approved.ref, approved.revision_id) == approved


def test_replace_table_series_rejects_duplicate_or_invalid_ids() -> None:
    _, imported = _uploaded_draft()
    session = session_from_import(imported.record, imported.source_files)

    for series_id, message in (
        (" ", "blank"),
        ("loss-100khz", "already exists"),
        ("loss 100khz", "collides"),
    ):
        with pytest.raises(MaterialImportError, match=message):
            replace_table_series(
                session,
                "bh-25c",
                series_id=series_id,
                kind=SeriesKind.BH_CURVE,
                x_unit="A/m",
                y_unit="T",
                conditions=CurveConditions(None, 25.0, None),
                points=(CurvePoint(0.0, 0.0), CurvePoint(100.0, 0.2)),
            )


def test_replace_table_series_retains_shared_external_source() -> None:
    session = _external_source_session(shared=True)
    edited = replace_table_series(
        session,
        "bh-first",
        series_id="bh-edited",
        kind=SeriesKind.BH_CURVE,
        x_unit="A/m",
        y_unit="T",
        conditions=CurveConditions(None, 30.0, None),
        points=(CurvePoint(0.0, 0.0), CurvePoint(100.0, 0.3)),
    )

    assert edited.record.series[1].source_filename == "shared.csv"
    assert edited.record.sources[0].filename == "shared.csv"
    assert dict(edited.source_files)["shared.csv"] == session.source_files[0][1]


def test_add_and_remove_table_series_manage_generated_sources() -> None:
    _, imported = _uploaded_draft()
    session = session_from_import(imported.record, imported.source_files)
    added = add_table_series(
        session,
        series_id="bh extra",
        kind=SeriesKind.BH_CURVE,
        x_unit="A/m",
        y_unit="T",
        conditions=CurveConditions(None, 80.0, None),
        points=(CurvePoint(0.0, 0.0), CurvePoint(150.0, 0.25)),
        captured_at="2026-07-20T09:00:00+00:00",
    )

    added_source = added.record.series[-1].source_filename
    assert added_source == "series-bh_extra.csv"
    assert added_source in dict(added.source_files)

    removed = remove_series(added, "bh extra")

    assert removed.record.series == session.record.series
    assert removed.record.sources == session.record.sources
    assert removed.source_files == session.source_files


def test_remove_series_rejects_missing_target_and_final_series() -> None:
    session = _external_source_session(shared=False)

    with pytest.raises(MaterialImportError, match="does not exist"):
        remove_series(session, "missing")
    with pytest.raises(MaterialImportError, match="final"):
        remove_series(session, "bh-first")


def test_save_review_and_approve_persist_each_immutable_session() -> None:
    template = material_import_template("csv")
    repository = InMemoryMaterialRepository()
    draft = _session_from_upload(template.filename, template.data)

    saved = save_material_session(repository, draft)
    assert save_material_session(repository, saved) is saved
    reviewed = review_material_session(repository, saved, "reviewer@example.com")
    approved = approve_material_session(repository, reviewed, "approver@example.com")

    assert saved is draft
    assert reviewed.record.status is MaterialStatus.REVIEWED
    assert approved.record.status is MaterialStatus.APPROVED
    assert approved.record.revision_id == draft.record.revision_id
    assert repository.get(approved.record.ref, approved.record.revision_id) == approved.record


def test_stale_draft_save_cannot_revert_a_reviewed_revision() -> None:
    template = material_import_template("csv")
    repository = InMemoryMaterialRepository()
    draft = _session_from_upload(template.filename, template.data)
    save_material_session(repository, draft)
    reviewed = review_material_session(repository, draft, "reviewer@example.com")

    with pytest.raises(MaterialImportError, match="current saved draft"):
        save_material_session(repository, draft)

    assert repository.get(reviewed.record.ref, reviewed.record.revision_id) == reviewed.record


@pytest.mark.parametrize("status", [MaterialStatus.REVIEWED, MaterialStatus.APPROVED])
def test_save_material_session_rejects_non_draft_status(status: MaterialStatus) -> None:
    template = material_import_template("csv")
    repository = InMemoryMaterialRepository()
    draft = _session_from_upload(template.filename, template.data)
    save_material_session(repository, draft)
    session = review_material_session(repository, draft, "reviewer@example.com")
    if status is MaterialStatus.APPROVED:
        session = approve_material_session(repository, session, "approver@example.com")
    stored_before = repository.get(session.record.ref, session.record.revision_id)

    with pytest.raises(MaterialImportError, match="draft"):
        save_material_session(repository, session)

    assert repository.get(session.record.ref, session.record.revision_id) == stored_before


def test_lifecycle_rejects_blank_actors_without_mutating_state() -> None:
    repository = InMemoryMaterialRepository()
    _, imported = _uploaded_draft()
    draft = session_from_import(imported.record, imported.source_files)
    save_material_session(repository, draft)

    with pytest.raises(MaterialImportError, match="Reviewer"):
        review_material_session(repository, draft, " ")

    assert repository.get(draft.record.ref, draft.record.revision_id) == draft.record


class _RejectingSaveRepository(InMemoryMaterialRepository):
    reject_save = False

    def save(self, record: MaterialRecord, sources: Mapping[str, bytes]) -> None:
        if self.reject_save:
            raise RuntimeError("repository rejected save")
        super().save(record, sources)


def test_failed_save_review_and_approval_leave_session_and_repository_unchanged() -> None:
    template = material_import_template("csv")
    repository = _RejectingSaveRepository()
    draft = _session_from_upload(template.filename, template.data)
    draft_before = deepcopy(draft)
    repository.reject_save = True

    with pytest.raises(RuntimeError, match="rejected"):
        save_material_session(repository, draft)

    assert repository.list_revisions(draft.record.ref) == ()
    assert draft == draft_before
