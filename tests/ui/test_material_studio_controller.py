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
from inductor_designer.application.services.material_selection import (  # noqa: E402
    pin_material_revision as authoritative_pin_material_revision,
)
from inductor_designer.domain.project import InductorProject  # noqa: E402
from inductor_designer.materials.identity import MaterialRef  # noqa: E402
from inductor_designer.materials.records import (  # noqa: E402
    MaterialRecord,
    MaterialStatus,
    SeriesKind,
)
from inductor_designer.ui import material_studio_controller as controller_module  # noqa: E402
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


def _create_image_draft(controller: MaterialStudioController) -> None:
    controller.importSourceImage(_file_url(_IMAGE), 0)
    controller.setCrop(0, 0, 120, 80)
    controller.setXAxis("linear", 10.0, 0.0, 110.0, 2.0)
    controller.setYAxis("linear", 70.0, 0.0, 10.0, 2.0)
    controller.setSeriesMetadata(
        "bh-manual",
        "bh-curve",
        "Oe",
        "kG",
        float("nan"),
        0.0,
        float("nan"),
    )
    controller.addPixelPoint(10.0, 70.0)
    controller.addPixelPoint(110.0, 10.0)
    controller.createImageDraft(
        "Example",
        "Ferrite",
        "Manual",
        "Synthetic manual B-H curve",
    )


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
def test_known_errors_are_logged_with_traceback(
    caplog: pytest.LogCaptureFixture,
) -> None:
    repository = InMemoryMaterialRepository()
    approved = _approved_material(repository)
    controller, _ = _controller(repository)
    controller.selectMaterial(
        approved.record.ref.manufacturer,
        approved.record.ref.name,
        approved.record.ref.grade,
    )
    caplog.set_level("ERROR", logger="inductor_designer.ui.material_studio_controller")

    controller.selectRevision("missing")

    assert "unknown material revision:" in controller.statusMessage
    assert any(
        record.exc_info is not None and "Material Studio action failed" in record.message
        for record in caplog.records
    )


@pytest.mark.ui
def test_qml_property_values_are_deep_copies() -> None:
    repository = InMemoryMaterialRepository()
    approved = _approved_material(repository)
    controller, _ = _controller(repository)
    controller.selectMaterial(
        approved.record.ref.manufacturer,
        approved.record.ref.name,
        approved.record.ref.grade,
    )
    controller.selectRevision(approved.record.revision_id)

    materials = controller.materials
    revisions = controller.revisions
    selected = controller.selectedRevision
    materials[0]["name"] = "mutated"
    revisions[0]["status"] = "mutated"
    selected["sources"][0]["filename"] = "mutated"

    assert controller.materials[0]["name"] == approved.record.ref.name
    assert controller.revisions[0]["status"] == "approved"
    assert controller.selectedRevision["sources"][0]["filename"] != "mutated"


@pytest.mark.ui
def test_downloads_require_local_destinations_and_use_exact_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
    expected_workbook = export_material_record_xlsx(approved.record)
    monkeypatch.setattr(
        controller_module,
        "export_material_record_xlsx",
        lambda _record: expected_workbook,
    )

    controller.exportSelectedWorkbook("")
    assert not workbook_target.exists()
    controller.exportSelectedWorkbook(_file_url(workbook_target))

    assert workbook_target.read_bytes() == expected_workbook.data


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
def test_new_record_clears_source_while_lifecycle_preserves_it(tmp_path: Path) -> None:
    repository = InMemoryMaterialRepository()
    approved = _approved_material(repository)
    controller, _ = _controller(repository)
    controller.selectMaterial(
        approved.record.ref.manufacturer,
        approved.record.ref.name,
        approved.record.ref.grade,
    )
    controller.selectRevision(approved.record.revision_id)
    controller.importSourceImage(_file_url(_IMAGE), 0)
    assert controller.source
    source_changes: list[None] = []
    controller.sourceChanged.connect(lambda: source_changes.append(None))
    template = material_import_template("csv")
    edited = tmp_path / template.filename
    edited.write_bytes(
        template.data.replace(
            b"Synthetic example data - replace before review",
            b"Source clearing lifecycle draft",
        )
    )

    controller.importTable(_file_url(edited))

    assert controller.source == {}
    assert source_changes == [None]

    controller.importSourceImage(_file_url(_IMAGE), 0)
    rendered_source = controller.source
    controller.saveDraft()
    controller.reviewDraft("reviewer-2@example.com")

    assert controller.source == rendered_source


@pytest.mark.ui
def test_image_edit_state_builds_draft_and_invalid_axis_keeps_last_valid_session() -> None:
    controller, _ = _controller(InMemoryMaterialRepository())

    _create_image_draft(controller)

    assert controller.selectedRevision["manufacturer"] == "Example"
    assert controller.selectedRevision["createdAt"] == "2026-07-19T10:00:00+00:00"
    assert controller.series == [
        {
            "seriesId": "bh-manual",
            "kind": "bh-curve",
            "xUnit": "Oe",
            "yUnit": "kG",
            "frequencyHz": None,
            "temperatureC": 0.0,
            "dcBiasAPerM": None,
            "pointCount": 2,
            "imageBacked": True,
        }
    ]
    assert controller.points == [
        {"seriesId": "bh-manual", "index": 0, "x": 0.0, "y": 0.0},
        {
            "seriesId": "bh-manual",
            "index": 1,
            "x": pytest.approx(159.154943092),
            "y": 0.2,
        },
    ]
    assert controller.imageEditing["pixelPoints"] == [
        {"xPx": 10.0, "yPx": 70.0},
        {"xPx": 110.0, "yPx": 10.0},
    ]
    assert controller.canSave is True
    last_valid_revision = controller.selectedRevision["revisionId"]

    controller.setXAxis("log", 10.0, 0.0, 110.0, 2.0)
    controller.movePixelPoint(1, 100.0, 20.0)

    assert controller.imageEditing["xAxis"]["scale"] == "log"
    assert controller.imageEditing["xAxis"]["valueA"] == 0.0
    assert controller.imageEditing["pixelPoints"][1] == {"xPx": 100.0, "yPx": 20.0}
    assert controller.selectedRevision["revisionId"] == last_valid_revision
    assert "logarithmic axis values must be positive" in controller.statusMessage
    assert controller.canSave is False
    controller.saveDraft()
    assert controller.dirty is True
    assert controller.selectedRevision["revisionId"] == last_valid_revision
    assert controller.statusMessage == "Resolve the invalid image edit before saving."

    controller.setXAxis("linear", 10.0, 0.0, 110.0, 2.0)

    assert controller.selectedRevision["revisionId"] != last_valid_revision
    assert controller.points[1]["x"] == pytest.approx(143.239448783)
    assert controller.points[1]["y"] == pytest.approx(0.166666667)
    assert controller.statusMessage == "Image extraction updated."
    assert controller.canSave is True


@pytest.mark.ui
def test_image_metadata_and_canonical_point_edits_use_authoritative_replacements() -> None:
    controller, _ = _controller(InMemoryMaterialRepository())
    _create_image_draft(controller)

    controller.setSeriesMetadata(
        "bh room",
        "bh-curve",
        "A/m",
        "T",
        0.0,
        30.0,
        0.0,
    )

    assert controller.series[0]["seriesId"] == "bh room"
    assert controller.series[0]["imageBacked"] is True
    assert controller.series[0]["frequencyHz"] == 0.0
    assert controller.series[0]["temperatureC"] == 30.0
    assert controller.series[0]["dcBiasAPerM"] == 0.0
    assert controller.imageEditing["metadata"]["seriesId"] == "bh room"

    controller.setCanonicalPoint("bh room", 1, 200.0, 0.3)

    assert controller.series[0]["imageBacked"] is False
    assert controller.points[1] == {
        "seriesId": "bh room",
        "index": 1,
        "x": 200.0,
        "y": 0.3,
    }
    assert [source["kind"] for source in controller.selectedRevision["sources"]] == [
        "image",
        "csv",
    ]
    assert controller.statusMessage == (
        "Numeric editing converted the image-backed series to a direct table edit; "
        "the original image/PDF remains as supplemental provenance."
    )


@pytest.mark.ui
def test_table_metadata_edit_treats_only_nan_as_an_absent_condition(tmp_path: Path) -> None:
    controller, _ = _controller(InMemoryMaterialRepository())
    template = material_import_template("csv")
    source = tmp_path / template.filename
    source.write_bytes(template.data)
    controller.importTable(_file_url(source))

    controller.setSeriesMetadata(
        "bh-25c",
        "bh-curve",
        "A/m",
        "T",
        float("nan"),
        0.0,
        0.0,
    )

    bh = next(item for item in controller.series if item["seriesId"] == "bh-25c")
    assert bh["frequencyHz"] is None
    assert bh["temperatureC"] == 0.0
    assert bh["dcBiasAPerM"] == 0.0
    assert bh["imageBacked"] is False
    assert controller.dirty is True


@pytest.mark.ui
def test_table_point_delete_edit_uses_authoritative_table_replacement(
    tmp_path: Path,
) -> None:
    controller, _ = _controller(InMemoryMaterialRepository())
    template = material_import_template("csv")
    source = tmp_path / template.filename
    source.write_bytes(template.data)
    controller.importTable(_file_url(source))
    before = [item for item in controller.points if item["seriesId"] == "bh-25c"]

    controller.deletePoint(1)

    after = [item for item in controller.points if item["seriesId"] == "bh-25c"]
    assert len(after) == len(before) - 1
    assert controller.statusMessage == "Canonical point deleted."
    assert controller.dirty is True


@pytest.mark.ui
def test_series_selector_changes_the_active_editor_without_marking_dirty(
    tmp_path: Path,
) -> None:
    controller, _ = _controller(InMemoryMaterialRepository())
    template = material_import_template("csv")
    source = tmp_path / template.filename
    source.write_bytes(template.data)
    controller.importTable(_file_url(source))
    controller.saveDraft()

    controller.selectSeries("loss-100khz")

    assert controller.imageEditing["metadata"]["seriesId"] == "loss-100khz"
    assert controller.imageEditing["metadata"]["kind"] == "loss-table"
    assert controller.dirty is False

    before = controller.imageEditing
    controller.selectSeries("missing")
    assert controller.imageEditing == before
    assert controller.statusMessage == "Series 'missing' does not exist."


@pytest.mark.ui
def test_discard_edit_restores_last_saved_session_and_loaded_source() -> None:
    repository = InMemoryMaterialRepository()
    approved = _approved_material(repository)
    controller, _ = _controller(repository)
    controller.selectMaterial(
        approved.record.ref.manufacturer,
        approved.record.ref.name,
        approved.record.ref.grade,
    )
    controller.selectRevision(approved.record.revision_id)
    selected_before = controller.selectedRevision

    controller.importSourceImage(_file_url(_IMAGE), 0)

    assert controller.dirty is True
    assert controller.source
    assert controller.discardChanges() is True
    assert controller.dirty is False
    assert controller.source == {}
    assert controller.selectedRevision == selected_before
    assert controller.statusMessage == "Unsaved changes discarded."

    _create_image_draft(controller)
    controller.saveDraft()
    saved_revision = controller.selectedRevision["revisionId"]
    saved_points = controller.points
    controller.setCanonicalPoint("bh-manual", 1, 200.0, 0.3)

    assert controller.dirty is True
    assert controller.discardChanges() is True
    assert controller.dirty is False
    assert controller.selectedRevision["revisionId"] == saved_revision
    assert controller.points == saved_points


class _PostPersistenceListingFailureRepository(InMemoryMaterialRepository):
    fail_listing = False

    def list_materials(self) -> tuple[MaterialRef, ...]:
        if self.fail_listing:
            raise ValueError("post-persistence listing unavailable")
        return super().list_materials()


@pytest.mark.ui
def test_lifecycle_success_is_committed_before_refresh_warning(tmp_path: Path) -> None:
    repository = _PostPersistenceListingFailureRepository()
    _approved_material(repository)
    controller, _ = _controller(repository)
    template = material_import_template("csv")
    edited = tmp_path / template.filename
    edited.write_bytes(
        template.data.replace(
            b"Synthetic example data - replace before review",
            b"Post-persistence refresh draft",
        )
    )
    controller.importTable(_file_url(edited))
    controller.saveDraft()
    ref = MaterialRef(
        controller.selectedRevision["manufacturer"],
        controller.selectedRevision["name"],
        controller.selectedRevision["grade"],
    )
    revision_id = controller.selectedRevision["revisionId"]
    repository.fail_listing = True

    controller.reviewDraft("reviewer-2@example.com")

    assert repository.get(ref, revision_id).status is MaterialStatus.REVIEWED
    assert controller.selectedRevision["status"] == "reviewed"
    assert controller.selectedRevision["reviewedBy"] == "reviewer-2@example.com"
    assert controller.canApprove is True
    assert "reviewed" in controller.statusMessage
    assert "refresh failed" in controller.statusMessage


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
@pytest.mark.parametrize(
    ("requested_id", "expected_id"),
    [("   ", None), ("  bh-25c  ", "bh-25c")],
)
def test_bh_selection_is_normalized_then_forwarded_to_authoritative_service(
    monkeypatch: pytest.MonkeyPatch,
    requested_id: str,
    expected_id: str | None,
) -> None:
    repository = InMemoryMaterialRepository()
    approved = _approved_material(repository)
    controller, saved_projects = _controller(repository)
    controller.selectMaterial(
        approved.record.ref.manufacturer,
        approved.record.ref.name,
        approved.record.ref.grade,
    )
    controller.selectRevision(approved.record.revision_id)
    forwarded: list[str | None] = []

    def recording_pin(
        project: InductorProject,
        record: MaterialRecord,
        *,
        bh_series_id: str | None,
    ) -> InductorProject:
        forwarded.append(bh_series_id)
        return authoritative_pin_material_revision(
            project,
            record,
            bh_series_id=bh_series_id,
        )

    monkeypatch.setattr(controller_module, "pin_material_revision", recording_pin)

    controller.useInProject(requested_id)

    assert forwarded == [expected_id]
    assert len(saved_projects) == 1
    assert saved_projects[0].materials[0].bh_series_id == expected_id


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
