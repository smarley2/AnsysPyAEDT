from __future__ import annotations

import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.ui

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def catalog_index(tmp_path: Path) -> Path:
    from tools.build_catalog import build

    index = tmp_path / "catalog.sqlite"
    build(ROOT / "catalog", ROOT / "schemas" / "catalog", index)
    return index


def test_preview_entries_built_offscreen(catalog_index: Path) -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QGuiApplication

    from inductor_designer.adapters.catalog.sqlite_repository import SqliteCatalogRepository
    from inductor_designer.adapters.persistence.project_repository import ProjectRepository
    from inductor_designer.adapters.persistence.schema_repository import SchemaRepository
    from inductor_designer.application.services.geometry_model import build_geometry_model
    from inductor_designer.ui.preview_geometry import build_preview_entries

    app = QGuiApplication.instance() or QGuiApplication([])
    assert app is not None
    repo = ProjectRepository(SchemaRepository(ROOT / "schemas"))
    project = repo.load(ROOT / "tests" / "fixtures" / "sample_geometry_project.inductor.json")
    model = build_geometry_model(project, SqliteCatalogRepository(catalog_index))
    entries = build_preview_entries(model)
    assert len(entries) == 3  # core + 2 windings
    assert entries[0].opacity < 1.0
    assert entries[1].color != entries[2].color
    assert entries[1].geometry is not None
