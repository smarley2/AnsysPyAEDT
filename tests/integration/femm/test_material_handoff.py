from __future__ import annotations

import importlib.util
import json
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
from inductor_designer.application.services.maxwell_export import (
    export_femm2d,
    femm_manifest_json,
)
from inductor_designer.domain.aedt_target import ModelDimension
from inductor_designer.domain.project import CatalogCoreSelection
from tools.build_catalog import build
from tools.femm_material_evidence import read_material_bh_points

ROOT = Path(__file__).resolve().parents[3]

pytestmark = pytest.mark.femm


def test_prepared_material_reaches_femm_with_exact_bh_points() -> None:
    project_value = os.environ.get("INDUCTOR_M5A_PROJECT")
    if not project_value:
        pytest.skip("Set INDUCTOR_M5A_PROJECT to run the M5a FEMM handoff test")
    if os.environ.get("INDUCTOR_FEMM_LIVE") != "1":
        pytest.skip("Set INDUCTOR_FEMM_LIVE=1 to run the M5a FEMM handoff test")
    if importlib.util.find_spec("femm") is None:
        pytest.fail("INDUCTOR_FEMM_LIVE=1 requires the femm package")
    artifact_root_value = os.environ.get("INDUCTOR_M5A_ARTIFACT_ROOT")
    if not artifact_root_value:
        pytest.fail("INDUCTOR_M5A_ARTIFACT_ROOT is required for M5a evidence")

    project_path = Path(project_value)
    assert project_path.is_file()
    repository = ProjectRepository(SchemaRepository(ROOT / "schemas"))
    project = replace(
        repository.load(project_path),
        dimension_mode=ModelDimension.TWO_D,
    )
    assert isinstance(project.core, CatalogCoreSelection)

    femm_output = Path(artifact_root_value) / "femm"
    index = femm_output / "catalog.sqlite"
    build(ROOT / "catalog", ROOT / "schemas" / "catalog", index)
    catalog = SqliteCatalogRepository(index)
    capabilities = MatrixCapabilityRepository(
        ROOT / "compatibility" / "aedt-matrix.yml"
    ).snapshot_for(project.target_release, project.target_edition)

    outcome = export_femm2d(
        project,
        catalog,
        PyfemmSolver(),
        femm_output,
        capabilities=capabilities,
        analyze=False,
    )
    manifest_path = femm_output / "femm-manifest.json"
    manifest_path.write_text(femm_manifest_json(outcome), encoding="utf-8")

    assert outcome.result.fem_path.is_file()
    assert outcome.result.analyzed is False
    expected_points = outcome.plan.core.material.bh_curve
    actual_points = read_material_bh_points(
        outcome.result.fem_path,
        outcome.plan.core.material.name,
    )
    assert expected_points
    assert len(actual_points) == len(expected_points)
    for actual, expected in zip(actual_points, expected_points, strict=True):
        assert actual == pytest.approx(expected)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    material = manifest["coreMaterial"]
    selection = next(
        item
        for item in project.materials
        if item.ref == project.core.snapshot.material
    )
    assert material["materialRevision"] == selection.revision_id
    assert material["bhSeriesId"] == selection.bh_series_id
