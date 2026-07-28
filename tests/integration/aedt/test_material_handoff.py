from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from inductor_designer.adapters.catalog.sqlite_repository import SqliteCatalogRepository
from inductor_designer.adapters.compatibility.matrix_repository import (
    MatrixCapabilityRepository,
)
from inductor_designer.adapters.persistence.project_repository import ProjectRepository
from inductor_designer.adapters.persistence.schema_repository import SchemaRepository
from inductor_designer.adapters.pyaedt.maxwell3d import PyaedtMaxwell3dExporter
from inductor_designer.application.ports.maxwell_exporter import STAGE_NAMES
from inductor_designer.application.services.aedt_support import (
    SUPPORTED_AEDT_EDITION,
    SUPPORTED_AEDT_RELEASE,
)
from inductor_designer.application.services.maxwell_export import (
    generate_run,
    run_manifest_json,
)
from inductor_designer.domain.project import CatalogCoreSelection
from inductor_designer.materials.records import SeriesKind
from inductor_designer.simulation.maxwell_plan import Maxwell3dDesignPlan
from inductor_designer.simulation.run_contracts import RunBackend, RunMode, RunRequest
from tests.fakes.femm_solver import RecordingFemmSolver
from tests.fakes.maxwell2d_exporter import RecordingMaxwell2dExporter
from tools.build_catalog import build

ROOT = Path(__file__).resolve().parents[3]

pytestmark = pytest.mark.aedt


def test_prepared_material_reaches_aedt_and_manifest_preserves_snapshot() -> None:
    project_value = os.environ.get("INDUCTOR_M5A_PROJECT")
    if not project_value:
        pytest.skip("Set INDUCTOR_M5A_PROJECT to run the M5a AEDT handoff test")
    artifact_root_value = os.environ.get("INDUCTOR_M5A_ARTIFACT_ROOT")
    if not artifact_root_value:
        pytest.fail("INDUCTOR_M5A_ARTIFACT_ROOT is required for M5a evidence")
    assert os.environ.get("INDUCTOR_AEDT_RELEASE") == "2025.2"
    assert os.environ.get("INDUCTOR_AEDT_EDITION") == "commercial"

    project_path = Path(project_value)
    assert project_path.is_file()
    repository = ProjectRepository(SchemaRepository(ROOT / "schemas"))
    project = repository.load(project_path)
    assert isinstance(project.design.core, CatalogCoreSelection)
    selection = project.design.core_material
    assert selection is not None
    assert selection.ref == project.design.core.snapshot.material
    bh_series = next(
        series
        for series in selection.snapshot.series
        if series.series_id == selection.bh_series_id
        and series.kind is SeriesKind.BH_CURVE
    )
    assert selection.snapshot.steinmetz is not None

    aedt_output = Path(artifact_root_value) / "aedt"
    index = aedt_output / "catalog.sqlite"
    build(ROOT / "catalog", ROOT / "schemas" / "catalog", index)
    catalog = SqliteCatalogRepository(index)
    capabilities = MatrixCapabilityRepository(
        ROOT / "compatibility" / "aedt-matrix.yml"
    ).snapshot_for(SUPPORTED_AEDT_RELEASE, SUPPORTED_AEDT_EDITION)

    outcome = generate_run(
        project,
        RunRequest(RunBackend.MAXWELL_3D, RunMode.GENERATE_ONLY),
        catalog,
        capabilities,
        aedt_output,
        maxwell3d_exporter=PyaedtMaxwell3dExporter(),
        maxwell2d_exporter=RecordingMaxwell2dExporter(),
        femm_solver=RecordingFemmSolver(),
        run_id="m5a-live-maxwell-3d",
        application_version="m5a-live-test",
    )
    manifest_path = aedt_output / "run-manifest.json"
    manifest_path.write_text(run_manifest_json(outcome.manifest), encoding="utf-8")

    result = outcome.adapter_result
    failed = [stage for stage in result.stages if not stage.succeeded]
    assert result.succeeded(STAGE_NAMES), failed
    assert result.project_path.is_file()
    stage_names = {stage.name for stage in result.stages}
    assert {"materials", "validate", "save"} <= stage_names

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    material = manifest["material"]
    assert material["revisionId"] == selection.revision_id
    assert material["bhSeriesId"] == selection.bh_series_id
    plan = outcome.planned_run.solver_plan
    assert isinstance(plan, Maxwell3dDesignPlan)
    assert len(plan.core.material.bh_curve) == len(bh_series.points)
    fit = selection.snapshot.steinmetz
    assert fit is not None
    assert plan.core.material.steinmetz == fit
