from __future__ import annotations

from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from inductor_designer.adapters.materials import (
    ImportedMaterialDraft,
    MaterialTemplateDownload,
    import_material_file_as_draft,
    material_import_template,
)
from inductor_designer.application.services.material_drafts import (
    ImageSeriesInput,
    MaterialDraftSession,
    add_image_series,
    add_table_series,
    approve_material_session,
    clone_revision_as_draft,
    image_draft_session,
    remove_series,
    replace_image_extraction,
    replace_image_series,
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
from inductor_designer.application.services.material_library import (
    list_material_revision_summaries,
)
from inductor_designer.materials.calibration import (
    AxisCalibration,
    AxisScale,
    CropRegion,
    ExtractionRecord,
    PixelPoint,
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
_MANUAL_IMAGE = Path(__file__).resolve().parents[2] / "fixtures/materials/manual-bh.png"


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
    created_at: str,
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


def _external_source_session(
    *,
    shared: bool,
    filename: str = "external.csv",
) -> MaterialDraftSession:
    data = b"x,y\n0.0,0.0\n100.0,0.2\n"
    source = SourceProvenance(
        kind=SourceKind.CSV,
        filename="shared.csv" if shared else filename,
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


def test_session_from_import_wraps_existing_import_result_exactly() -> None:
    template, imported = _uploaded_draft()

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


def test_unchanged_approved_clone_cannot_be_saved_or_overwrite_base() -> None:
    repository, approved, _ = _approved_repository()
    session = clone_revision_as_draft(
        repository,
        approved.ref,
        approved.revision_id,
        created_at="2026-07-20T08:00:00+00:00",
    )
    before = repository.get(approved.ref, approved.revision_id)

    with pytest.raises(MaterialImportError, match="edited"):
        save_material_session(repository, session)

    assert repository.get(approved.ref, approved.revision_id) == before
    with pytest.raises(ValueError, match="immutable"):
        repository.save(session.record, dict(session.source_files))
    assert repository.get(approved.ref, approved.revision_id) == before


def test_approved_edit_gets_fresh_timestamp_and_becomes_latest_suggestion() -> None:
    repository, approved, _ = _approved_repository()
    base_before = deepcopy(approved)
    derived_at = "2026-07-20T08:00:00+00:00"
    clone = clone_revision_as_draft(
        repository,
        approved.ref,
        approved.revision_id,
        created_at=derived_at,
    )

    edited = replace_table_series(
        clone,
        "bh-25c",
        series_id="bh-30c",
        kind=SeriesKind.BH_CURVE,
        x_unit="A/m",
        y_unit="T",
        conditions=CurveConditions(None, 30.0, None),
        points=(CurvePoint(0.0, 0.0), CurvePoint(125.0, 0.2)),
    )
    save_material_session(repository, edited)
    reviewed = review_material_session(repository, edited, "reviewer@example.com")
    derived = approve_material_session(repository, reviewed, "approver@example.com")

    summaries = list_material_revision_summaries(repository, approved.ref)
    assert clone.record.created_at == derived_at
    assert edited.record.created_at == derived_at
    assert derived.record.created_at == derived_at
    assert derived.record.revision_id != approved.revision_id
    assert summaries[0].revision_id == derived.record.revision_id
    assert summaries[0].is_latest_approved
    assert not summaries[1].is_latest_approved
    assert repository.get(approved.ref, approved.revision_id) == base_before


def test_replace_table_series_renames_generated_source_and_retains_upload() -> None:
    repository, approved, _ = _approved_repository()
    session = clone_revision_as_draft(
        repository,
        approved.ref,
        approved.revision_id,
        created_at="2026-07-20T08:00:00+00:00",
    )
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
    session = _session_from_upload(
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


def test_replace_table_series_preserves_vendor_source_with_generated_style_name() -> None:
    session = _external_source_session(
        shared=False,
        filename="series-bh_first.csv",
    )
    vendor_source = session.record.sources[0]
    vendor_file = session.source_files[0]

    edited = replace_table_series(
        session,
        "bh-first",
        series_id="bh-updated",
        kind=SeriesKind.BH_CURVE,
        x_unit="A/m",
        y_unit="T",
        conditions=CurveConditions(None, 30.0, None),
        points=(CurvePoint(0.0, 0.0), CurvePoint(125.0, 0.25)),
    )

    assert vendor_source in edited.record.sources
    assert vendor_file in edited.source_files
    assert edited.record.series[0].source_filename == "series-bh_updated.csv"


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
    draft = _session_from_upload(template.filename, template.data, created_at=_CREATED_AT)
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
    session = _session_from_upload(template.filename, template.data, created_at=_CREATED_AT)
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


def test_add_table_series_is_immutable_replayable_and_retains_lineage() -> None:
    template = material_import_template("csv")
    original = _session_from_upload(
        template.filename,
        template.data,
        created_at=_CREATED_AT,
    )
    before = deepcopy(original)

    added = add_table_series(
        original,
        series_id="bh extra",
        kind=SeriesKind.BH_CURVE,
        x_unit="A/m",
        y_unit="T",
        conditions=CurveConditions(None, 80.0, None),
        points=(CurvePoint(0.0, 0.0), CurvePoint(150.0, 0.25)),
        captured_at="2026-07-20T09:00:00+00:00",
    )

    assert original == before
    assert added.record.created_at == original.record.created_at
    assert added.base_revision_id == original.base_revision_id
    assert added.record.revision_id == revision_id_for(added.record)
    assert added.record.revision_id != original.record.revision_id
    assert added.record.series[-1].series_id == "bh extra"
    assert added.record.series[-1].source_filename == "series-bh_extra.csv"
    assert added.record.sources[:-1] == original.record.sources
    assert added.record.sources[-1] == SourceProvenance(
        kind=SourceKind.CSV,
        filename="series-bh_extra.csv",
        sha256=sha256_hex(b"x,y\n0.0,0.0\n150.0,0.25\n"),
        url="",
        page=None,
        captured_at="2026-07-20T09:00:00+00:00",
        description="Material Studio generated per-series CSV",
    )
    assert added.source_files[:-1] == original.source_files
    assert reproduce_record(added.record, dict(added.source_files)).matches


@pytest.mark.parametrize("series_id", ["bh-25c", "bh 25c"])
def test_add_table_series_rejects_exact_and_sanitized_id_collisions(
    series_id: str,
) -> None:
    template = material_import_template("csv")
    session = _session_from_upload(
        template.filename,
        template.data,
        created_at=_CREATED_AT,
    )

    with pytest.raises(MaterialImportError, match="already exists|collides"):
        add_table_series(
            session,
            series_id=series_id,
            kind=SeriesKind.BH_CURVE,
            x_unit="A/m",
            y_unit="T",
            conditions=CurveConditions(None, 25.0, None),
            points=(CurvePoint(0.0, 0.0), CurvePoint(100.0, 0.2)),
            captured_at=_CREATED_AT,
        )


def test_add_image_series_reuses_source_without_duplicating_provenance() -> None:
    source_data = _MANUAL_IMAGE.read_bytes()
    extraction = _linear_extraction(PixelPoint(10.0, 70.0), PixelPoint(110.0, 10.0))
    original = image_draft_session(
        ImageSeriesInput(
            ref=MaterialRef("Example", "Ferrite", "Image add"),
            source_filename="manual-bh.png",
            source_data=source_data,
            source_url="https://example.com/manual-bh.png",
            source_page=None,
            captured_at=_CREATED_AT,
            source_description="Synthetic manual curves",
            series_id="bh-25c",
            kind=SeriesKind.BH_CURVE,
            x_unit="A/m",
            y_unit="T",
            conditions=CurveConditions(None, 25.0, None),
            extraction=extraction,
            created_at=_CREATED_AT,
        )
    )

    added = add_image_series(
        original,
        source_filename="manual-bh.png",
        series_id="bh-100c",
        kind=SeriesKind.BH_CURVE,
        x_unit="A/m",
        y_unit="T",
        conditions=CurveConditions(None, 100.0, None),
        extraction=extraction,
    )

    assert tuple(item.series_id for item in added.record.series) == ("bh-25c", "bh-100c")
    assert added.record.sources == original.record.sources
    assert added.source_files == original.source_files
    assert added.record.revision_id == revision_id_for(added.record)
    assert reproduce_record(added.record, dict(added.source_files)).matches


def test_remove_series_drops_only_unreferenced_generated_source() -> None:
    template = material_import_template("csv")
    original = _session_from_upload(
        template.filename,
        template.data,
        created_at=_CREATED_AT,
    )

    removed = remove_series(original, "loss-100khz")

    assert original.record.steinmetz is not None
    assert removed.record.steinmetz is None
    assert tuple(item.series_id for item in removed.record.series) == (
        "bh-25c",
        "loss-200khz",
    )
    assert removed.record.sources[0] == original.record.sources[0]
    assert "material-import-template.csv" in dict(removed.source_files)
    assert "series-loss_100khz.csv" not in dict(removed.source_files)
    assert all(
        source.filename != "series-loss_100khz.csv"
        for source in removed.record.sources
    )
    assert removed.record.revision_id == revision_id_for(removed.record)
    assert reproduce_record(removed.record, dict(removed.source_files)).matches


def test_remove_series_preserves_vendor_csv_that_matches_generated_filename() -> None:
    vendor_data = b"x,y\n0.0,0.0\n100.0,0.2\n"
    sibling_data = b"x,y\n0.0,0.0\n200.0,0.3\n"
    vendor_source = SourceProvenance(
        kind=SourceKind.CSV,
        filename="series-vendor.csv",
        sha256=sha256_hex(vendor_data),
        url="https://vendor.example/material.csv",
        page=None,
        captured_at=_CREATED_AT,
        description="Vendor characterization data",
    )
    sibling_source = replace(
        vendor_source,
        filename="sibling.csv",
        sha256=sha256_hex(sibling_data),
    )
    target = PointSeries(
        series_id="vendor",
        kind=SeriesKind.BH_CURVE,
        x_unit="A/m",
        y_unit="T",
        conditions=CurveConditions(None, 25.0, None),
        points=(CurvePoint(0.0, 0.0), CurvePoint(100.0, 0.2)),
        source_filename=vendor_source.filename,
        extraction=None,
    )
    sibling = replace(
        target,
        series_id="sibling",
        points=(CurvePoint(0.0, 0.0), CurvePoint(200.0, 0.3)),
        source_filename=sibling_source.filename,
    )
    record = new_draft_record(
        MaterialRef("Vendor", "Ferrite", "CSV"),
        series=(target, sibling),
        sources=(vendor_source, sibling_source),
        created_at=_CREATED_AT,
    )
    session = MaterialDraftSession(
        record,
        ((vendor_source.filename, vendor_data), (sibling_source.filename, sibling_data)),
        None,
    )

    removed = remove_series(session, "vendor")

    assert vendor_source in removed.record.sources
    assert (vendor_source.filename, vendor_data) in removed.source_files


def test_remove_series_cleans_owned_generated_table_source() -> None:
    base = _external_source_session(shared=False)
    added = add_table_series(
        base,
        series_id="added",
        kind=SeriesKind.BH_CURVE,
        x_unit="A/m",
        y_unit="T",
        conditions=CurveConditions(None, 80.0, None),
        points=(CurvePoint(0.0, 0.0), CurvePoint(150.0, 0.25)),
        captured_at=_CREATED_AT,
    )

    removed = remove_series(added, "added")

    assert all(source.filename != "series-added.csv" for source in removed.record.sources)
    assert "series-added.csv" not in dict(removed.source_files)
    assert removed.record.sources == base.record.sources
    assert removed.source_files == base.source_files


def test_remove_series_retains_generated_source_still_used_by_sibling() -> None:
    template = material_import_template("csv")
    original = _session_from_upload(
        template.filename,
        template.data,
        created_at=_CREATED_AT,
    )
    target = original.record.series[0]
    sibling = replace(target, series_id="bh-shared")
    record = new_draft_record(
        original.record.ref,
        series=(*original.record.series, sibling),
        sources=original.record.sources,
        created_at=original.record.created_at,
    )
    session = MaterialDraftSession(record, original.source_files, None)

    removed = remove_series(session, target.series_id)

    assert "series-bh_25c.csv" in dict(removed.source_files)
    assert any(
        source.filename == "series-bh_25c.csv" for source in removed.record.sources
    )
    assert reproduce_record(removed.record, dict(removed.source_files)).matches


def test_remove_image_series_retains_original_source_as_supplemental_provenance() -> None:
    source_data = _MANUAL_IMAGE.read_bytes()
    extraction = _linear_extraction(PixelPoint(10.0, 70.0), PixelPoint(110.0, 10.0))
    image = image_draft_session(
        ImageSeriesInput(
            ref=MaterialRef("Example", "Ferrite", "Image removal"),
            source_filename="manual-bh.png",
            source_data=source_data,
            source_url="https://example.com/manual-bh.png",
            source_page=None,
            captured_at=_CREATED_AT,
            source_description="Synthetic manual curve",
            series_id="bh-image",
            kind=SeriesKind.BH_CURVE,
            x_unit="A/m",
            y_unit="T",
            conditions=CurveConditions(None, 100.0, None),
            extraction=extraction,
            created_at=_CREATED_AT,
        )
    )
    session = add_table_series(
        image,
        series_id="bh-table",
        kind=SeriesKind.BH_CURVE,
        x_unit="A/m",
        y_unit="T",
        conditions=CurveConditions(None, 25.0, None),
        points=(CurvePoint(0.0, 0.0), CurvePoint(100.0, 0.2)),
        captured_at=_CREATED_AT,
    )

    removed = remove_series(session, "bh-image")

    assert removed.record.sources == session.record.sources
    assert removed.source_files == session.source_files
    assert removed.base_revision_id == session.base_revision_id


def test_remove_series_rejects_missing_target_and_final_series() -> None:
    session = _external_source_session(shared=False)

    with pytest.raises(MaterialImportError, match="does not exist"):
        remove_series(session, "missing")
    with pytest.raises(MaterialImportError, match="final"):
        remove_series(session, "bh-first")


def test_save_review_and_approve_persist_each_immutable_session() -> None:
    template = material_import_template("csv")
    repository = InMemoryMaterialRepository()
    draft = _session_from_upload(template.filename, template.data, created_at=_CREATED_AT)

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
    draft = _session_from_upload(template.filename, template.data, created_at=_CREATED_AT)
    save_material_session(repository, draft)
    reviewed = review_material_session(repository, draft, "reviewer@example.com")

    with pytest.raises(MaterialImportError, match="current saved draft"):
        save_material_session(repository, draft)

    assert repository.get(reviewed.record.ref, reviewed.record.revision_id) == reviewed.record


@pytest.mark.parametrize("status", [MaterialStatus.REVIEWED, MaterialStatus.APPROVED])
def test_save_material_session_rejects_non_draft_status(status: MaterialStatus) -> None:
    template = material_import_template("csv")
    repository = InMemoryMaterialRepository()
    draft = _session_from_upload(template.filename, template.data, created_at=_CREATED_AT)
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
    session = _session_from_upload(template.filename, template.data, created_at=_CREATED_AT)

    with pytest.raises(MaterialImportError, match="saved draft"):
        review_material_session(repository, session, "reviewer@example.com")

    assert repository.list_revisions(session.record.ref) == ()
    assert session.record.status is MaterialStatus.DRAFT


def test_approval_requires_the_current_reviewed_revision_to_be_saved() -> None:
    template = material_import_template("csv")
    repository = InMemoryMaterialRepository()
    draft = _session_from_upload(template.filename, template.data, created_at=_CREATED_AT)
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
        _session_from_upload(template.filename, template.data, created_at=_CREATED_AT),
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
    draft = _session_from_upload(template.filename, template.data, created_at=_CREATED_AT)
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


def _linear_extraction(*points: PixelPoint) -> ExtractionRecord:
    return ExtractionRecord(
        crop=CropRegion(0, 0, 120, 80),
        x_axis=AxisCalibration(AxisScale.LINEAR, 10.0, 0.0, 110.0, 2.0),
        y_axis=AxisCalibration(AxisScale.LINEAR, 70.0, 0.0, 10.0, 2.0),
        pixel_points=points,
    )


def test_image_draft_canonicalizes_points_and_preserves_replayable_source() -> None:
    source_data = _MANUAL_IMAGE.read_bytes()
    extraction = _linear_extraction(PixelPoint(10.0, 70.0), PixelPoint(110.0, 10.0))
    input_data = ImageSeriesInput(
        ref=MaterialRef("Example", "Ferrite", "Manual"),
        source_filename="manual-bh.png",
        source_data=source_data,
        source_url="https://example.com/manual-bh.png",
        source_page=None,
        captured_at=_CREATED_AT,
        source_description="Synthetic manual B-H curve",
        series_id="bh-manual",
        kind=SeriesKind.BH_CURVE,
        x_unit="Oe",
        y_unit="kG",
        conditions=CurveConditions(None, 25.0, 0.0),
        extraction=extraction,
        created_at=_CREATED_AT,
        notes="Digitized manually",
    )

    session = image_draft_session(input_data)

    assert session.base_revision_id is None
    assert session.source_files == (("manual-bh.png", source_data),)
    assert session.record.sources == (
        SourceProvenance(
            kind=SourceKind.IMAGE,
            filename="manual-bh.png",
            sha256=sha256_hex(source_data),
            url="https://example.com/manual-bh.png",
            page=None,
            captured_at=_CREATED_AT,
            description="Synthetic manual B-H curve",
        ),
    )
    assert session.record.series == (
        PointSeries(
            series_id="bh-manual",
            kind=SeriesKind.BH_CURVE,
            x_unit="Oe",
            y_unit="kG",
            conditions=CurveConditions(None, 25.0, 0.0),
            points=(CurvePoint(0.0, 0.0), CurvePoint(159.154943092, 0.2)),
            source_filename="manual-bh.png",
            extraction=extraction,
        ),
    )
    assert session.record.revision_id == revision_id_for(session.record)
    assert reproduce_record(session.record, dict(session.source_files)).matches


def test_image_draft_supports_log_axes_and_preserves_pdf_page_metadata() -> None:
    source_data = b"synthetic two-page PDF source"
    extraction = ExtractionRecord(
        crop=CropRegion(0, 0, 100, 100),
        x_axis=AxisCalibration(AxisScale.LOG, 0.0, 0.1, 100.0, 1.0),
        y_axis=AxisCalibration(AxisScale.LOG, 100.0, 10.0, 0.0, 1000.0),
        pixel_points=(PixelPoint(50.0, 50.0),),
    )

    session = image_draft_session(
        ImageSeriesInput(
            ref=MaterialRef("Example", "Ferrite", "PDF"),
            source_filename="datasheet.pdf",
            source_data=source_data,
            source_url="https://example.com/datasheet.pdf",
            source_page=1,
            captured_at=_CREATED_AT,
            source_description="Synthetic PDF page",
            series_id="loss-log",
            kind=SeriesKind.LOSS_TABLE,
            x_unit="kG",
            y_unit="mW/cm3",
            conditions=CurveConditions(100_000.0, 100.0, None),
            extraction=extraction,
            created_at=_CREATED_AT,
        )
    )

    assert session.record.series[0].points == (CurvePoint(0.031622777, 100_000.0),)
    assert session.record.sources[0].page == 1
    assert session.record.sources[0].sha256 == sha256_hex(source_data)
    assert reproduce_record(session.record, dict(session.source_files)).matches


def test_replace_image_extraction_rebuilds_draft_and_retains_original_sources() -> None:
    source_data = _MANUAL_IMAGE.read_bytes()
    original_extraction = _linear_extraction(
        PixelPoint(10.0, 70.0), PixelPoint(110.0, 10.0)
    )
    session = image_draft_session(
        ImageSeriesInput(
            ref=MaterialRef("Example", "Ferrite", "Editable"),
            source_filename="manual-bh.png",
            source_data=source_data,
            source_url="https://example.com/manual-bh.png",
            source_page=None,
            captured_at=_CREATED_AT,
            source_description="Synthetic manual B-H curve",
            series_id="bh-manual",
            kind=SeriesKind.BH_CURVE,
            x_unit="Oe",
            y_unit="kG",
            conditions=CurveConditions(None, 25.0, 0.0),
            extraction=original_extraction,
            created_at=_CREATED_AT,
        )
    )
    before = deepcopy(session)
    moved_extraction = replace(
        original_extraction,
        pixel_points=(PixelPoint(10.0, 70.0), PixelPoint(100.0, 20.0)),
    )

    edited = replace_image_extraction(session, "bh-manual", moved_extraction)

    assert edited.record.series[0].extraction == moved_extraction
    assert edited.record.series[0].points == (
        CurvePoint(0.0, 0.0),
        CurvePoint(143.239448783, 0.166666667),
    )
    assert edited.record.revision_id == revision_id_for(edited.record)
    assert edited.record.revision_id != session.record.revision_id
    assert edited.record.sources == session.record.sources
    assert edited.source_files == session.source_files
    assert edited.base_revision_id == session.base_revision_id
    assert reproduce_record(edited.record, dict(edited.source_files)).matches
    assert session == before


def test_replace_image_series_changes_metadata_and_retains_sibling_and_sources() -> None:
    source_data = _MANUAL_IMAGE.read_bytes()
    extraction = _linear_extraction(PixelPoint(10.0, 70.0), PixelPoint(110.0, 10.0))
    session = image_draft_session(
        ImageSeriesInput(
            ref=MaterialRef("Example", "Ferrite", "Multi image"),
            source_filename="manual-bh.png",
            source_data=source_data,
            source_url="https://example.com/manual-bh.png",
            source_page=None,
            captured_at=_CREATED_AT,
            source_description="Synthetic manual curves",
            series_id="bh-manual",
            kind=SeriesKind.BH_CURVE,
            x_unit="A/m",
            y_unit="T",
            conditions=CurveConditions(None, 25.0, None),
            extraction=extraction,
            created_at=_CREATED_AT,
        )
    )
    target = session.record.series[0]
    sibling = replace(target, series_id="bh-sibling")
    record = new_draft_record(
        session.record.ref,
        series=(target, sibling),
        sources=session.record.sources,
        created_at=session.record.created_at,
    )
    session = MaterialDraftSession(record, session.source_files, None)
    before = deepcopy(session)

    edited = replace_image_series(
        session,
        "bh-manual",
        series_id="bh room",
        kind=SeriesKind.BH_CURVE,
        x_unit="Oe",
        y_unit="kG",
        conditions=CurveConditions(0.0, 30.0, 0.0),
        extraction=extraction,
    )

    replacement = next(item for item in edited.record.series if item.series_id == "bh room")
    assert replacement.extraction == extraction
    assert replacement.x_unit == "Oe"
    assert replacement.y_unit == "kG"
    assert replacement.conditions == CurveConditions(0.0, 30.0, 0.0)
    assert replacement.points == (CurvePoint(0.0, 0.0), CurvePoint(159.154943092, 0.2))
    assert edited.record.series[1] == sibling
    assert edited.record.sources == session.record.sources
    assert edited.source_files == session.source_files
    assert edited.record.revision_id == revision_id_for(edited.record)
    assert edited.record.revision_id != session.record.revision_id
    assert session == before


@pytest.mark.parametrize(
    ("target_series_id", "series_id", "message"),
    [
        ("missing", "replacement", "does not exist"),
        ("bh-manual", " ", "must not be blank"),
        ("bh-manual", "bh-sibling", "already exists"),
        ("bh-manual", "bh sibling", "collides"),
    ],
)
def test_replace_image_series_validates_target_and_replacement_id(
    target_series_id: str,
    series_id: str,
    message: str,
) -> None:
    source_data = _MANUAL_IMAGE.read_bytes()
    extraction = _linear_extraction(PixelPoint(10.0, 70.0), PixelPoint(110.0, 10.0))
    session = image_draft_session(
        ImageSeriesInput(
            ref=MaterialRef("Example", "Ferrite", "Validation"),
            source_filename="manual-bh.png",
            source_data=source_data,
            source_url="",
            source_page=None,
            captured_at=_CREATED_AT,
            source_description="Synthetic manual curve",
            series_id="bh-manual",
            kind=SeriesKind.BH_CURVE,
            x_unit="A/m",
            y_unit="T",
            conditions=CurveConditions(None, 25.0, None),
            extraction=extraction,
            created_at=_CREATED_AT,
        )
    )
    target = session.record.series[0]
    sibling = replace(target, series_id="bh-sibling")
    record = new_draft_record(
        session.record.ref,
        series=(target, sibling),
        sources=session.record.sources,
        created_at=session.record.created_at,
    )
    session = MaterialDraftSession(record, session.source_files, None)

    with pytest.raises(MaterialImportError, match=message):
        replace_image_series(
            session,
            target_series_id,
            series_id=series_id,
            kind=SeriesKind.BH_CURVE,
            x_unit="A/m",
            y_unit="T",
            conditions=CurveConditions(None, 25.0, None),
            extraction=extraction,
        )


@pytest.mark.parametrize("status", [MaterialStatus.REVIEWED, MaterialStatus.APPROVED])
def test_replace_image_extraction_requires_a_draft_session(status: MaterialStatus) -> None:
    source_data = _MANUAL_IMAGE.read_bytes()
    extraction = _linear_extraction(PixelPoint(10.0, 70.0), PixelPoint(110.0, 10.0))
    session = image_draft_session(
        ImageSeriesInput(
            ref=MaterialRef("Example", "Ferrite", "Lifecycle"),
            source_filename="manual-bh.png",
            source_data=source_data,
            source_url="",
            source_page=None,
            captured_at=_CREATED_AT,
            source_description="Synthetic manual B-H curve",
            series_id="bh-manual",
            kind=SeriesKind.BH_CURVE,
            x_unit="A/m",
            y_unit="T",
            conditions=CurveConditions(None, 25.0, None),
            extraction=extraction,
            created_at=_CREATED_AT,
        )
    )
    repository = InMemoryMaterialRepository()
    save_material_session(repository, session)
    session = review_material_session(repository, session, "reviewer@example.com")
    if status is MaterialStatus.APPROVED:
        session = approve_material_session(repository, session, "approver@example.com")

    with pytest.raises(MaterialImportError, match="draft"):
        replace_image_extraction(session, "bh-manual", extraction)

    assert session.record.status is status
