from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path

import pytest

from inductor_designer.adapters.catalog.sqlite_repository import SqliteCatalogRepository
from inductor_designer.adapters.compatibility.matrix_repository import (
    MatrixCapabilityRepository,
)
from inductor_designer.adapters.persistence.project_repository import ProjectRepository
from inductor_designer.adapters.persistence.schema_repository import SchemaRepository
from inductor_designer.adapters.pyaedt.maxwell2d import PyaedtMaxwell2dExporter
from inductor_designer.application.services.maxwell_export import (
    export_maxwell2d,
    generation_manifest_json,
)
from inductor_designer.domain.aedt_target import ModelDimension
from inductor_designer.domain.project import CatalogCoreSelection
from inductor_designer.materials.records import SeriesKind
from tools.build_catalog import build

ROOT = Path(__file__).resolve().parents[3]

pytestmark = pytest.mark.aedt


def test_prepared_material_reaches_maxwell_2d_with_the_same_snapshot() -> None:
    """M5a proved the material reaches Maxwell 3D and FEMM but never Maxwell 2D.

    The 2D material stage is separate code from the 3D one, and 2D has its own
    AEDT quirks (region creation, balloon boundary), so identical source is not
    evidence that the nonlinear B-H curve and the core-loss model arrive intact.
    """
    project_value = os.environ.get("INDUCTOR_M5A_PROJECT")
    if not project_value:
        pytest.skip("Set INDUCTOR_M5A_PROJECT to run the M5a Maxwell 2D handoff test")
    artifact_root_value = os.environ.get("INDUCTOR_M5A_ARTIFACT_ROOT")
    if not artifact_root_value:
        pytest.fail("INDUCTOR_M5A_ARTIFACT_ROOT is required for M5a evidence")
    assert os.environ.get("INDUCTOR_AEDT_RELEASE") == "2025.2"
    assert os.environ.get("INDUCTOR_AEDT_EDITION") == "commercial"

    project_path = Path(project_value)
    assert project_path.is_file()
    repository = ProjectRepository(SchemaRepository(ROOT / "schemas"))
    project = replace(
        repository.load(project_path), dimension_mode=ModelDimension.TWO_D
    )
    assert isinstance(project.core, CatalogCoreSelection)
    selection = next(
        material
        for material in project.materials
        if material.ref == project.core.snapshot.material
    )
    bh_series = next(
        series
        for series in selection.snapshot.series
        if series.series_id == selection.bh_series_id
        and series.kind is SeriesKind.BH_CURVE
    )
    assert selection.snapshot.steinmetz is not None

    output = Path(artifact_root_value) / "aedt-2d"
    index = output / "catalog.sqlite"
    build(ROOT / "catalog", ROOT / "schemas" / "catalog", index)
    catalog = SqliteCatalogRepository(index)
    capabilities = MatrixCapabilityRepository(
        ROOT / "compatibility" / "aedt-matrix.yml"
    ).snapshot_for(project.target_release, project.target_edition)

    outcome = export_maxwell2d(
        project,
        catalog,
        PyaedtMaxwell2dExporter(),
        output,
        capabilities=capabilities,
    )
    manifest_path = output / "generation-manifest.json"
    manifest_path.write_text(generation_manifest_json(outcome), encoding="utf-8")

    failed = [stage for stage in outcome.result.stages if not stage.succeeded]
    assert outcome.result.succeeded(), failed
    assert outcome.result.project_path.is_file()
    stage_names = {stage.name for stage in outcome.result.stages}
    assert {"materials", "validate", "save"} <= stage_names

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["dimension"] == "2d"
    material = manifest["coreMaterial"]
    assert material["materialRevision"] == selection.revision_id
    assert material["bhSeriesId"] == selection.bh_series_id
    assert material["bhPointCount"] == len(bh_series.points)
    fit = selection.snapshot.steinmetz
    assert fit is not None
    assert material["steinmetz"] == {"k": fit.k, "alpha": fit.alpha, "beta": fit.beta}
