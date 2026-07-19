from __future__ import annotations

import base64
import os
from dataclasses import replace
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QSG_RHI_BACKEND", "software")

pytest.importorskip("PySide6")

from PySide6.QtCore import QUrl  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

from inductor_designer.adapters.materials import (  # noqa: E402
    export_material_record_xlsx,
    material_import_template,
)
from inductor_designer.application.services.material_drafts import (  # noqa: E402
    MaterialDraftSession,
    approve_material_session,
    review_material_session,
    save_material_session,
    session_from_upload,
)
from inductor_designer.domain.project import InductorProject  # noqa: E402
from inductor_designer.materials.records import SeriesKind  # noqa: E402
from inductor_designer.ui.main import create_engine  # noqa: E402
from inductor_designer.ui.material_source import render_material_source  # noqa: E402
from inductor_designer.ui.material_studio_controller import (  # noqa: E402
    MaterialStudioController,
)
from tests.fakes.material_repository import InMemoryMaterialRepository  # noqa: E402
from tests.unit.domain.test_project import make_project  # noqa: E402

_CREATED_AT = "2026-07-19T09:00:00+00:00"
_IMAGE = Path(__file__).parents[1] / "fixtures" / "materials" / "manual-bh.png"


def _file_url(path: Path) -> str:
    return QUrl.fromLocalFile(str(path)).toString()


def _approved_material(
    repository: InMemoryMaterialRepository,
) -> MaterialDraftSession:
    template = material_import_template("csv")
    draft = session_from_upload(template.filename, template.data, created_at=_CREATED_AT)
    save_material_session(repository, draft)
    reviewed = review_material_session(repository, draft, "reviewer@example.com")
    return approve_material_session(repository, reviewed, "approver@example.com")


def _controller(
    repository: InMemoryMaterialRepository,
    *,
    with_project: bool = True,
) -> tuple[MaterialStudioController, list[InductorProject]]:
    saved_projects = []
    controller = MaterialStudioController(
        repository,
        project=make_project() if with_project else None,
        project_save_callback=saved_projects.append if with_project else None,
        now=lambda: "2026-07-19T10:00:00+00:00",
    )
    return controller, saved_projects


@pytest.mark.ui
def test_library_refresh_and_latest_approved_are_advisory_only() -> None:
    repository = InMemoryMaterialRepository()
    approved = _approved_material(repository)

    controller, _ = _controller(repository)

    assert controller.materials == [
        {
            "manufacturer": approved.record.ref.manufacturer,
            "name": approved.record.ref.name,
            "grade": approved.record.ref.grade,
        }
    ]
    assert controller.revisions == []
    assert controller.selectedRevision == {}

    controller.selectMaterial(
        approved.record.ref.manufacturer,
        approved.record.ref.name,
        approved.record.ref.grade,
    )

    assert [item["revisionId"] for item in controller.revisions] == [
        approved.record.revision_id
    ]
    assert controller.revisions[0]["isLatestApproved"] is True
    assert controller.selectedRevision == {}
    assert controller.dirty is False


@pytest.mark.ui
def test_selected_revision_exposes_plain_details_and_action_flags() -> None:
    repository = InMemoryMaterialRepository()
    approved = _approved_material(repository)
    controller, _ = _controller(repository)
    controller.selectMaterial(
        approved.record.ref.manufacturer,
        approved.record.ref.name,
        approved.record.ref.grade,
    )

    controller.selectRevision(approved.record.revision_id)

    assert controller.selectedRevision["revisionId"] == approved.record.revision_id
    assert controller.selectedRevision["status"] == "approved"
    assert controller.selectedRevision["reviewedBy"] == "reviewer@example.com"
    assert controller.selectedRevision["approvedBy"] == "approver@example.com"
    assert all(isinstance(item, dict) for item in controller.series)
    assert all(isinstance(item, dict) for item in controller.points)
    assert all(isinstance(item, dict) for item in controller.issues)
    assert isinstance(controller.fit, dict)
    assert controller.canSave is False
    assert controller.canReview is False
    assert controller.canApprove is False
    assert controller.canUseInProject is True


@pytest.mark.ui
def test_import_save_review_and_approve_refresh_state(tmp_path: Path) -> None:
    repository = InMemoryMaterialRepository()
    approved = _approved_material(repository)
    controller, _ = _controller(repository)
    template = material_import_template("csv")
    edited_bytes = template.data.replace(
        b"Synthetic example data - replace before review",
        b"Controller lifecycle draft",
    )
    source = tmp_path / template.filename
    source.write_bytes(edited_bytes)

    controller.importTable(_file_url(source))

    draft_id = controller.selectedRevision["revisionId"]
    assert draft_id != approved.record.revision_id
    assert controller.selectedRevision["status"] == "draft"
    assert controller.dirty is True
    assert controller.canSave is True
    assert controller.canReview is False
    assert controller.canApprove is False

    controller.saveDraft()

    assert controller.dirty is False
    assert controller.canSave is False
    assert controller.canReview is True
    assert {item["revisionId"] for item in controller.revisions} == {
        approved.record.revision_id,
        draft_id,
    }

    selected_before = dict(controller.selectedRevision)
    revisions_before = list(controller.revisions)
    controller.reviewDraft("  ")
    assert controller.selectedRevision == selected_before
    assert controller.revisions == revisions_before
    assert controller.statusMessage == "Reviewer must not be blank."

    controller.reviewDraft("reviewer-2@example.com")

    assert controller.selectedRevision["status"] == "reviewed"
    assert controller.selectedRevision["reviewedBy"] == "reviewer-2@example.com"
    assert controller.canReview is False
    assert controller.canApprove is True

    selected_before = dict(controller.selectedRevision)
    controller.approveRevision("")
    assert controller.selectedRevision == selected_before
    assert controller.statusMessage == "Approver must not be blank."

    controller.approveRevision("approver-2@example.com")

    assert controller.selectedRevision["status"] == "approved"
    assert controller.selectedRevision["approvedBy"] == "approver-2@example.com"
    assert controller.canApprove is False
    assert controller.canUseInProject is True
    approved_summary = next(
        item for item in controller.revisions if item["revisionId"] == draft_id
    )
    assert approved_summary["isLatestApproved"] is True


@pytest.mark.ui
def test_known_selection_error_keeps_prior_selection() -> None:
    repository = InMemoryMaterialRepository()
    approved = _approved_material(repository)
    controller, _ = _controller(repository)
    controller.selectMaterial(
        approved.record.ref.manufacturer,
        approved.record.ref.name,
        approved.record.ref.grade,
    )
    controller.selectRevision(approved.record.revision_id)
    before = dict(controller.selectedRevision)

    controller.selectRevision("missing")

    assert controller.selectedRevision == before
    assert "unknown material revision:" in controller.statusMessage


@pytest.mark.ui
def test_downloads_require_local_destinations_and_use_exact_bytes(tmp_path: Path) -> None:
    repository = InMemoryMaterialRepository()
    approved = _approved_material(repository)
    controller, _ = _controller(repository)

    controller.downloadTemplate("csv", "")
    assert list(tmp_path.iterdir()) == []

    template_target = tmp_path / "template.csv"
    controller.downloadTemplate("csv", _file_url(template_target))
    assert template_target.read_bytes() == material_import_template("csv").data

    controller.selectMaterial(
        approved.record.ref.manufacturer,
        approved.record.ref.name,
        approved.record.ref.grade,
    )
    controller.selectRevision(approved.record.revision_id)
    workbook_target = tmp_path / "selected.xlsx"

    controller.exportSelectedWorkbook("")
    assert not workbook_target.exists()
    controller.exportSelectedWorkbook(_file_url(workbook_target))

    assert workbook_target.read_bytes() == export_material_record_xlsx(
        approved.record
    ).data


@pytest.mark.ui
def test_table_and_workbook_uploads_read_before_replacing_state(tmp_path: Path) -> None:
    repository = InMemoryMaterialRepository()
    approved = _approved_material(repository)
    controller, _ = _controller(repository)
    controller.selectMaterial(
        approved.record.ref.manufacturer,
        approved.record.ref.name,
        approved.record.ref.grade,
    )
    controller.selectRevision(approved.record.revision_id)
    selected_before = dict(controller.selectedRevision)

    controller.importTable("")
    controller.importTable("https://example.com/material.csv")
    controller.importEditedWorkbook(_file_url(tmp_path / "missing.xlsx"))

    assert controller.selectedRevision == selected_before
    assert controller.dirty is False

    workbook = tmp_path / "edited.xlsx"
    workbook.write_bytes(export_material_record_xlsx(approved.record).data)
    controller.importEditedWorkbook(_file_url(workbook))

    assert controller.selectedRevision["status"] == "draft"
    assert controller.selectedRevision["revisionId"] != approved.record.revision_id
    assert controller.dirty is True
    assert controller.canSave is True


@pytest.mark.ui
def test_image_import_exposes_rendered_png_and_preserves_selection_on_error() -> None:
    repository = InMemoryMaterialRepository()
    approved = _approved_material(repository)
    controller, _ = _controller(repository)
    controller.selectMaterial(
        approved.record.ref.manufacturer,
        approved.record.ref.name,
        approved.record.ref.grade,
    )
    controller.selectRevision(approved.record.revision_id)
    source_bytes = _IMAGE.read_bytes()
    rendered = render_material_source(_IMAGE.name, source_bytes)

    controller.importSourceImage(_file_url(_IMAGE), 0)

    assert controller.source == {
        "dataUrl": "data:image/png;base64,"
        + base64.b64encode(rendered.png_data).decode("ascii"),
        "filename": _IMAGE.name,
        "width": rendered.width_px,
        "height": rendered.height_px,
        "pageCount": 1,
        "pageIndex": 0,
    }
    source_before = dict(controller.source)
    selected_before = dict(controller.selectedRevision)

    controller.importSourceImage("", 0)
    controller.importSourceImage("https://example.com/manual-bh.png", 0)

    assert controller.source == source_before
    assert controller.selectedRevision == selected_before


@pytest.mark.ui
def test_project_use_requires_explicit_multi_bh_id_and_saves_once() -> None:
    repository = InMemoryMaterialRepository()
    approved = _approved_material(repository)
    bh = next(item for item in approved.record.series if item.kind is SeriesKind.BH_CURVE)
    multi = replace(
        approved.record,
        revision_id="ffffffffffff",
        series=(*approved.record.series, replace(bh, series_id="bh-100c")),
    )
    repository.save(multi, dict(approved.source_files))
    controller, saved_projects = _controller(repository)
    controller.selectMaterial(
        multi.ref.manufacturer,
        multi.ref.name,
        multi.ref.grade,
    )
    controller.selectRevision(multi.revision_id)

    controller.useInProject("")

    assert saved_projects == []
    assert "multiple B-H series" in controller.statusMessage

    controller.useInProject("bh-100c")

    assert len(saved_projects) == 1
    assert saved_projects[0].materials[0].revision_id == multi.revision_id
    assert saved_projects[0].materials[0].bh_series_id == "bh-100c"


@pytest.mark.ui
def test_library_controller_without_project_cannot_pin() -> None:
    repository = InMemoryMaterialRepository()
    approved = _approved_material(repository)
    controller, saved_projects = _controller(repository, with_project=False)
    controller.selectMaterial(
        approved.record.ref.manufacturer,
        approved.record.ref.name,
        approved.record.ref.grade,
    )
    controller.selectRevision(approved.record.revision_id)

    assert controller.canUseInProject is False
    controller.useInProject("")
    assert saved_projects == []
    assert controller.statusMessage == "No project is loaded."


@pytest.mark.ui
def test_create_engine_injects_material_studio_controller() -> None:
    app = QGuiApplication.instance() or QGuiApplication([])
    controller, _ = _controller(InMemoryMaterialRepository(), with_project=False)

    engine = create_engine(material_studio_controller=controller)

    assert app is not None
    assert engine.rootContext().contextProperty("materialStudioController") is controller
    assert len(engine.rootObjects()) == 1
