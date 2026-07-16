from __future__ import annotations

import os
from pathlib import Path

import pytest

from inductor_designer.adapters.catalog.sqlite_repository import SqliteCatalogRepository
from inductor_designer.adapters.persistence.project_repository import ProjectRepository
from inductor_designer.adapters.persistence.schema_repository import SchemaRepository
from inductor_designer.adapters.pyaedt.maxwell3d import PyaedtMaxwell3dExporter
from inductor_designer.application.services.maxwell_export import export_maxwell3d
from tools.build_catalog import build

ROOT = Path(__file__).resolve().parents[3]

pytestmark = pytest.mark.aedt


def test_generated_project_is_ready_to_solve(tmp_path: Path) -> None:
    release = os.environ.get("INDUCTOR_AEDT_RELEASE")
    edition = os.environ.get("INDUCTOR_AEDT_EDITION")
    if not release or not edition:
        pytest.skip("Set INDUCTOR_AEDT_RELEASE and INDUCTOR_AEDT_EDITION to run AEDT tests")

    index = tmp_path / "catalog.sqlite"
    build(ROOT / "catalog", ROOT / "schemas" / "catalog", index)
    catalog = SqliteCatalogRepository(index)
    repository = ProjectRepository(SchemaRepository(ROOT / "schemas"))
    project = repository.load(ROOT / "tests" / "fixtures" / "sample_geometry_project.inductor.json")

    outcome = export_maxwell3d(project, catalog, PyaedtMaxwell3dExporter(), tmp_path / "out")

    failed = [stage for stage in outcome.result.stages if not stage.succeeded]
    assert outcome.result.succeeded(), failed
    assert outcome.result.project_path.exists()
