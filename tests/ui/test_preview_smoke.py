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


def test_flipping_a_winding_sense_changes_what_the_preview_draws(
    catalog_index: Path,
) -> None:
    """The sense has to reach the mesh, not just the project: the drawn turns
    were sense-blind, so cw and ccw rendered identically."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from dataclasses import replace

    from PySide6.QtGui import QGuiApplication

    from inductor_designer.adapters.catalog.sqlite_repository import SqliteCatalogRepository
    from inductor_designer.adapters.persistence.project_repository import ProjectRepository
    from inductor_designer.adapters.persistence.schema_repository import SchemaRepository
    from inductor_designer.application.services.geometry_model import (
        GeometryModel,
        build_geometry_model,
    )
    from inductor_designer.domain.winding import WindingDirection
    from inductor_designer.geometry.tessellation import tessellate_winding

    app = QGuiApplication.instance() or QGuiApplication([])
    assert app is not None
    repo = ProjectRepository(SchemaRepository(ROOT / "schemas"))
    project = repo.load(ROOT / "tests" / "fixtures" / "sample_geometry_project.inductor.json")
    catalog = SqliteCatalogRepository(catalog_index)

    def model_with(sense: WindingDirection) -> GeometryModel:
        design = project.design
        flipped = replace(
            project,
            design=replace(
                design,
                windings=(
                    replace(design.windings[0], winding_direction=sense),
                    *design.windings[1:],
                ),
            ),
        )
        return build_geometry_model(flipped, catalog)

    cw = model_with(WindingDirection.CLOCKWISE)
    ccw = model_with(WindingDirection.COUNTERCLOCKWISE)
    first = min(cw.packings, key=lambda p: p.winding_id)

    assert cw.winding_direction[first.winding_id] is WindingDirection.CLOCKWISE
    drawn = [
        tessellate_winding(
            model.core, first, model.winding_direction[first.winding_id]
        ).positions
        for model in (cw, ccw)
    ]
    assert drawn[0] != drawn[1]
