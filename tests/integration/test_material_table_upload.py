from __future__ import annotations

import io
from copy import deepcopy
from pathlib import Path

from openpyxl import load_workbook

from inductor_designer.adapters.materials import (
    FileOverlayMaterialRepository,
    export_material_record_xlsx,
    import_material_file,
    import_material_file_as_draft,
    material_import_template,
)
from inductor_designer.application.services.material_import import (
    approve_material,
    new_draft_record,
    review_material,
)
from inductor_designer.materials.records import CurvePoint, MaterialRecord, MaterialStatus
from inductor_designer.materials.replay import reproduce_record


def _approve_template(
    file_format: str, overlay: Path
) -> tuple[MaterialRecord, FileOverlayMaterialRepository]:
    download = material_import_template(file_format)
    imported = import_material_file(download.filename, download.data)
    draft = new_draft_record(
        imported.ref,
        series=imported.series,
        sources=imported.sources,
        created_at="2026-07-18T12:00:00+00:00",
        notes="Synthetic template end-to-end proof.",
    )
    approved = approve_material(
        review_material(draft, "reviewer@example.com"),
        "approver@example.com",
    )
    repository = FileOverlayMaterialRepository(overlay)
    repository.save(approved, dict(imported.source_files))

    fresh = FileOverlayMaterialRepository(overlay)
    loaded = fresh.get(approved.ref, approved.revision_id)
    assert reproduce_record(
        loaded, fresh.source_bytes(loaded.ref, loaded.revision_id)
    ).matches
    return loaded, fresh


def test_template_upload_export_and_edit_reproduce_end_to_end(tmp_path: Path) -> None:
    csv_approved, _ = _approve_template("csv", tmp_path / "csv-overlay")
    xlsx_approved, repository = _approve_template("xlsx", tmp_path / "xlsx-overlay")
    assert csv_approved.series == xlsx_approved.series

    base_before_edit = deepcopy(xlsx_approved)
    exported = export_material_record_xlsx(xlsx_approved)
    workbook = load_workbook(io.BytesIO(exported.data))
    workbook["Loss Curves"]["H2"] = 110.0
    stream = io.BytesIO()
    workbook.save(stream)

    edited = import_material_file_as_draft(
        exported.filename,
        stream.getvalue(),
        created_at="2026-07-18T13:00:00+00:00",
        notes="Edited exported workbook.",
    )
    assert edited.record.status is MaterialStatus.DRAFT
    assert edited.record.revision_id != xlsx_approved.revision_id
    base_loss = next(
        series for series in xlsx_approved.series if series.series_id == "loss-100khz"
    )
    edited_loss = next(
        series for series in edited.record.series if series.series_id == "loss-100khz"
    )
    assert edited_loss.points[0] == CurvePoint(0.05, 110_000.0)
    assert edited_loss.points[0] != base_loss.points[0]
    assert xlsx_approved == base_before_edit

    edited_approved = approve_material(
        review_material(edited.record, "reviewer@example.com"),
        "approver@example.com",
    )
    repository.save(edited_approved, dict(edited.source_files))
    fresh = FileOverlayMaterialRepository(tmp_path / "xlsx-overlay")
    reloaded = fresh.get(edited_approved.ref, edited_approved.revision_id)
    assert reproduce_record(
        reloaded, fresh.source_bytes(reloaded.ref, reloaded.revision_id)
    ).matches
    reloaded_loss = next(
        series for series in reloaded.series if series.series_id == "loss-100khz"
    )
    assert reloaded_loss.points[0] == CurvePoint(0.05, 110_000.0)
    assert fresh.get(xlsx_approved.ref, xlsx_approved.revision_id) == base_before_edit
