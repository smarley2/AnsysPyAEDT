from __future__ import annotations

import os
from copy import deepcopy
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QSG_RHI_BACKEND", "software")

pytest.importorskip("PySide6")

from PySide6.QtCore import QUrl  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

from inductor_designer.adapters.materials import (  # noqa: E402
    import_material_file_as_draft,
    import_material_file_as_imported,
    material_import_template,
)
from inductor_designer.application.services.material_drafts import (  # noqa: E402
    MaterialDraftSession,
    approve_material_session,
    review_material_session,
    save_material_session,
    session_from_import,
)
from inductor_designer.domain.project import InductorProject  # noqa: E402
from inductor_designer.ui.material_studio_controller import (  # noqa: E402
    MaterialStudioController,
)
from tests.fakes.material_repository import InMemoryMaterialRepository  # noqa: E402
from tests.unit.domain.test_project import make_project  # noqa: E402

_APP = QGuiApplication.instance() or QGuiApplication([])
_CREATED_AT = "2026-07-19T09:00:00+00:00"


def _file_url(path: Path) -> str:
    return QUrl.fromLocalFile(str(path)).toString()


def _approved_material(
    repository: InMemoryMaterialRepository,
) -> MaterialDraftSession:
    template = material_import_template("csv")
    imported = import_material_file_as_draft(
        template.filename, template.data, created_at=_CREATED_AT
    )
    draft = session_from_import(imported.record, imported.source_files)
    save_material_session(repository, draft)
    reviewed = review_material_session(repository, draft, "reviewer@example.com")
    return approve_material_session(repository, reviewed, "approver@example.com")


def _controller(
    repository: InMemoryMaterialRepository,
    *,
    with_project: bool = True,
) -> tuple[MaterialStudioController, list[InductorProject]]:
    saved_projects: list[InductorProject] = []
    controller = MaterialStudioController(
        repository,
        project=make_project() if with_project else None,
        project_save_callback=saved_projects.append if with_project else None,
        now=lambda: "2026-07-19T10:00:00+00:00",
    )
    return controller, saved_projects


@pytest.mark.ui
def test_library_refresh_and_revision_selection_expose_table_provenance() -> None:
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
    assert controller.selectMaterial(
        approved.record.ref.manufacturer,
        approved.record.ref.name,
        approved.record.ref.grade,
    )
    assert controller.selectedRevision["revisionId"] == approved.record.revision_id
    assert controller.selectedRevision["status"] == "approved"
    assert controller.selectedRevision["seriesCount"] == len(approved.record.series)
    assert controller.tableEditing["metadata"]["seriesId"] == "bh-25c"
    assert isinstance(controller.sourcePoints, list)
    assert all(item["sourceKind"] in ("csv", "spreadsheet") for item in controller.series)
    assert all("imageBacked" not in item for item in controller.series)


@pytest.mark.ui
def test_import_table_persists_imported_revision_without_dirty_editor_state(
    tmp_path: Path,
) -> None:
    repository = InMemoryMaterialRepository()
    controller, _ = _controller(repository, with_project=False)
    template = material_import_template("csv")
    source_path = tmp_path / template.filename
    source_path.write_bytes(template.data)

    controller.importTable(_file_url(source_path))

    assert controller.selectedRevision["status"] == "imported"
    assert controller.dirty is False
    assert controller.canSave is False
    assert repository.list_revisions(controller._selected_ref) == (  # type: ignore[arg-type]
        controller.selectedRevision["revisionId"],
    )


@pytest.mark.ui
def test_curve_points_are_exposed_in_retained_spreadsheet_units(
    tmp_path: Path,
) -> None:
    repository = InMemoryMaterialRepository()
    controller, _ = _controller(repository, with_project=False)
    template = material_import_template("csv")
    source_path = tmp_path / template.filename
    source_path.write_bytes(template.data)

    controller.importTable(_file_url(source_path))

    assert controller.tableEditing["metadata"]["xUnit"] == "Oe"
    assert controller.tableEditing["metadata"]["yUnit"] == "kG"
    assert controller.points[-1]["x"] == pytest.approx(2.0)
    assert controller.points[-1]["y"] == pytest.approx(1.6)


@pytest.mark.ui
def test_replace_selected_material_replaces_unpinned_imported_revision(tmp_path: Path) -> None:
    repository = InMemoryMaterialRepository()
    controller, _ = _controller(repository, with_project=False)
    template = material_import_template("csv")
    first_path = tmp_path / "first.csv"
    second_path = tmp_path / "second.csv"
    first_path.write_bytes(template.data)
    second_path.write_bytes(
        template.data.replace(b"UTC 2026-07-18 12:00:00", b"UTC 2026-07-23 12:00:00")
    )

    controller.importTable(_file_url(first_path))
    old_revision = str(controller.selectedRevision["revisionId"])
    controller.replaceSelectedMaterial(_file_url(second_path))

    new_revision = str(controller.selectedRevision["revisionId"])
    assert new_revision != old_revision
    assert controller.selectedRevision["status"] == "imported"
    assert len(repository.list_revisions(controller._selected_ref)) == 1  # type: ignore[arg-type]
    with pytest.raises(KeyError):
        repository.get(controller._selected_ref, old_revision)  # type: ignore[arg-type]


@pytest.mark.ui
def test_replace_selected_material_rejects_identity_mismatch(tmp_path: Path) -> None:
    repository = InMemoryMaterialRepository()
    controller, _ = _controller(repository, with_project=False)
    template = material_import_template("csv")
    first_path = tmp_path / "first.csv"
    other_path = tmp_path / "other.csv"
    first_path.write_bytes(template.data)
    other_path.write_bytes(template.data.replace(b"Synthetic Ferrite", b"Other Ferrite"))

    controller.importTable(_file_url(first_path))
    old_revision = str(controller.selectedRevision["revisionId"])
    controller.replaceSelectedMaterial(_file_url(other_path))

    assert "identity" in controller.statusMessage
    assert controller.selectedRevision["revisionId"] == old_revision
    assert len(repository.list_revisions(controller._selected_ref)) == 1  # type: ignore[arg-type]


@pytest.mark.ui
def test_delete_selected_material_is_blocked_when_project_pins_revision(
    tmp_path: Path,
) -> None:
    repository = InMemoryMaterialRepository()
    controller, saved_projects = _controller(repository, with_project=True)
    template = material_import_template("csv")
    source_path = tmp_path / template.filename
    source_path.write_bytes(template.data)

    controller.importTable(_file_url(source_path))
    controller.useInProject("bh-25c")
    controller.deleteSelectedMaterial()

    assert saved_projects
    assert "pinned" in controller.statusMessage
    assert controller.materials


@pytest.mark.ui
def test_imported_material_does_not_allow_direct_point_mutation(tmp_path: Path) -> None:
    repository = InMemoryMaterialRepository()
    controller, _ = _controller(repository, with_project=False)
    template = material_import_template("csv")
    source_path = tmp_path / template.filename
    source_path.write_bytes(template.data)

    controller.importTable(_file_url(source_path))
    revision = str(controller.selectedRevision["revisionId"])
    assert controller.setCanonicalPoint("bh-25c", 1, 90.0, 0.09) is False

    assert controller.selectedRevision["revisionId"] == revision
    assert controller.dirty is False


@pytest.mark.ui
def test_import_table_is_immediately_persisted_and_has_no_lifecycle_actions(
    tmp_path: Path,
) -> None:
    repository = InMemoryMaterialRepository()
    controller, _ = _controller(repository, with_project=False)
    template = material_import_template("csv")
    source_path = tmp_path / template.filename
    source_path.write_bytes(template.data)

    controller.importTable(_file_url(source_path))
    assert controller.selectedRevision["status"] == "imported"
    assert controller.canSave is False
    assert controller.canReview is False
    assert controller.canApprove is False
    assert controller.dirty is False


@pytest.mark.ui
def test_approved_material_revision_is_read_only_in_material_studio() -> None:
    repository = InMemoryMaterialRepository()
    approved = _approved_material(repository)
    controller, _ = _controller(repository)
    controller.selectMaterial("Example Magnetics", "Synthetic Ferrite", "F1")
    controller.selectRevision(approved.record.revision_id)
    original = deepcopy(approved.record)

    assert controller.setCanonicalPoint("bh-25c", 1, 90.0, 0.09) is False

    assert controller.selectedRevision["status"] == "approved"
    assert controller.dirty is False
    assert "read-only" in controller.statusMessage
    assert repository.get(original.ref, original.revision_id) == original
    assert controller.tableEditing["metadata"]["seriesId"] == "bh-25c"


@pytest.mark.ui
def test_imported_material_rejects_series_metadata_and_series_editing(
    tmp_path: Path,
) -> None:
    repository = InMemoryMaterialRepository()
    controller, _ = _controller(repository, with_project=False)
    template = material_import_template("csv")
    source_path = tmp_path / template.filename
    source_path.write_bytes(template.data)
    controller.importTable(_file_url(source_path))

    controller.setSeriesMetadata(
        "bh-renamed",
        "bh-curve",
        "A/m",
        "T",
        float("nan"),
        30.0,
        float("nan"),
    )
    assert controller.tableEditing["metadata"]["seriesId"] == "bh-25c"
    assert controller.series[0]["sourceKind"] == "csv"

    assert controller.addTableSeries(
        "extra-bh",
        "bh-curve",
        "A/m",
        "T",
        float("nan"),
        40.0,
        float("nan"),
        [{"x": 0.0, "y": 0.0}, {"x": 100.0, "y": 0.2}],
    ) is False
    assert not any(item["seriesId"] == "extra-bh" for item in controller.series)
    assert controller.removeSeries("extra-bh") is False
    assert controller.dirty is False


@pytest.mark.ui
def test_table_template_actions_accept_local_csv_and_reject_non_file_urls(
    tmp_path: Path,
) -> None:
    repository = InMemoryMaterialRepository()
    controller, _ = _controller(repository, with_project=False)
    destination = tmp_path / "template.csv"

    controller.downloadTemplate("csv", _file_url(destination))
    assert destination.read_text(encoding="utf-8").startswith("manufacturer,")

    controller.importTable("https://example.com/material.csv")
    assert "local file URL" in controller.statusMessage
    assert not hasattr(controller, "importSourceImage")


@pytest.mark.ui
def test_exported_material_workbook_round_trips_all_series(tmp_path: Path) -> None:
    repository = InMemoryMaterialRepository()
    controller, _ = _controller(repository, with_project=False)
    template = material_import_template("xlsx")
    source = tmp_path / template.filename
    source.write_bytes(template.data)
    controller.importTable(_file_url(source))
    expected_ids = [item["seriesId"] for item in controller.series]
    destination = tmp_path / "downloaded-material.xlsx"

    controller.exportSelectedWorkbook(_file_url(destination))
    imported = import_material_file_as_imported(
        destination.name,
        destination.read_bytes(),
        created_at="2026-07-23T12:00:00+00:00",
    )

    assert [item.series_id for item in imported.record.series] == expected_ids


@pytest.mark.ui
def test_approved_bh_series_can_be_pinned_to_project() -> None:
    repository = InMemoryMaterialRepository()
    approved = _approved_material(repository)
    controller, saved_projects = _controller(repository)
    controller.selectMaterial("Example Magnetics", "Synthetic Ferrite", "F1")
    controller.selectRevision(approved.record.revision_id)

    controller.useInProject("bh-25c")

    assert len(saved_projects) == 1
    assert saved_projects[0].materials[0].bh_series_id == "bh-25c"
