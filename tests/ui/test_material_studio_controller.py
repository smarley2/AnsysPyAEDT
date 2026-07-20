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
    assert controller.selectRevision(approved.record.revision_id)
    assert controller.selectedRevision["status"] == "approved"
    assert controller.tableEditing["metadata"]["seriesId"] == "bh-25c"
    assert isinstance(controller.sourcePoints, list)
    assert all(item["sourceKind"] in ("csv", "spreadsheet") for item in controller.series)
    assert all("imageBacked" not in item for item in controller.series)


@pytest.mark.ui
def test_import_table_save_review_and_approve_refresh_state(tmp_path: Path) -> None:
    repository = InMemoryMaterialRepository()
    controller, _ = _controller(repository, with_project=False)
    template = material_import_template("csv")
    source_path = tmp_path / template.filename
    source_path.write_bytes(template.data)

    controller.importTable(_file_url(source_path))
    assert controller.selectedRevision["status"] == "draft"
    assert controller.canSave
    controller.saveDraft()
    controller.reviewDraft("reviewer@example.com")
    controller.approveRevision("approver@example.com")

    assert controller.selectedRevision["status"] == "approved"
    assert controller.canSave is False
    assert controller.statusMessage == "Material revision approved."


@pytest.mark.ui
def test_canonical_point_edit_clones_approved_revision_as_table_draft() -> None:
    repository = InMemoryMaterialRepository()
    approved = _approved_material(repository)
    controller, _ = _controller(repository)
    controller.selectMaterial("Example Magnetics", "Synthetic Ferrite", "F1")
    controller.selectRevision(approved.record.revision_id)
    original = deepcopy(approved.record)

    assert controller.setCanonicalPoint("bh-25c", 1, 90.0, 0.09)

    assert controller.selectedRevision["status"] == "draft"
    assert controller.dirty
    assert controller.statusMessage == "Canonical point updated."
    assert repository.get(original.ref, original.revision_id) == original
    assert controller.tableEditing["metadata"]["seriesId"] == "bh-25c"


@pytest.mark.ui
def test_metadata_edit_add_and_remove_series_use_only_numeric_table_operations(
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
    assert controller.tableEditing["metadata"]["seriesId"] == "bh-renamed"
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
    )
    assert any(item["seriesId"] == "extra-bh" for item in controller.series)
    assert controller.removeSeries("extra-bh")
    assert not any(item["seriesId"] == "extra-bh" for item in controller.series)


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
def test_approved_bh_series_can_be_pinned_to_project() -> None:
    repository = InMemoryMaterialRepository()
    approved = _approved_material(repository)
    controller, saved_projects = _controller(repository)
    controller.selectMaterial("Example Magnetics", "Synthetic Ferrite", "F1")
    controller.selectRevision(approved.record.revision_id)

    controller.useInProject("bh-25c")

    assert len(saved_projects) == 1
    assert saved_projects[0].materials[0].bh_series_id == "bh-25c"
