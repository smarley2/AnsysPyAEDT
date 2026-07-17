from __future__ import annotations

import importlib.util
import os
from dataclasses import replace
from pathlib import Path

import pytest

from inductor_designer.adapters.catalog.sqlite_repository import SqliteCatalogRepository
from inductor_designer.adapters.compatibility.matrix_repository import (
    MatrixCapabilityRepository,
)
from inductor_designer.adapters.femm.solver import PyfemmSolver
from inductor_designer.adapters.persistence.project_repository import ProjectRepository
from inductor_designer.adapters.persistence.schema_repository import SchemaRepository
from inductor_designer.application.services.maxwell_export import export_femm2d
from inductor_designer.domain.aedt_target import ModelDimension
from tools.build_catalog import build

ROOT = Path(__file__).resolve().parents[3]

pytestmark = pytest.mark.femm


def test_femm_solves_sample_project(tmp_path: Path) -> None:
    if importlib.util.find_spec("femm") is None or os.environ.get("INDUCTOR_FEMM_LIVE") != "1":
        pytest.skip("Set INDUCTOR_FEMM_LIVE=1 with the femm package installed to run FEMM tests")

    index = tmp_path / "catalog.sqlite"
    build(ROOT / "catalog", ROOT / "schemas" / "catalog", index)
    catalog = SqliteCatalogRepository(index)
    repository = ProjectRepository(SchemaRepository(ROOT / "schemas"))
    project = replace(
        repository.load(ROOT / "tests" / "fixtures" / "sample_geometry_project.inductor.json"),
        dimension_mode=ModelDimension.TWO_D,
    )
    capabilities = MatrixCapabilityRepository(
        ROOT / "compatibility" / "aedt-matrix.yml"
    ).snapshot_for(project.target_release, project.target_edition)

    outcome = export_femm2d(
        project, catalog, PyfemmSolver(), tmp_path / "out", capabilities=capabilities
    )

    result = outcome.result
    assert result.fem_path.exists()
    assert result.analyzed
    assert result.results is not None
    assert set(result.results) == {"w1", "w2"}
    for winding in result.results.values():
        assert winding.resistance_ohm > 0
        assert winding.inductance_h > 0

    fem_text = result.fem_path.read_text(encoding="utf-8", errors="ignore")
    assert "w1" in fem_text
    assert "w2" in fem_text
    depth_m = outcome.problem.depth_m
    depth_candidates = {f"{depth_m:g}", f"{depth_m}", f"{depth_m:.6g}", f"{depth_m:.4f}"}
    assert any(candidate in fem_text for candidate in depth_candidates)
