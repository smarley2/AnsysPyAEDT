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
from inductor_designer.simulation.maxwell2d_plan import Maxwell2dDesignPlan
from inductor_designer.simulation.run_contracts import RunBackend, RunMode, RunRequest
from tests.fakes.femm_solver import RecordingFemmSolver
from tests.fakes.maxwell_exporter import RecordingMaxwell3dExporter
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
    loaded = repository.load(project_path)
    # This test isolates material transfer. M6 blocks nonzero DC for Maxwell 2D.
    project = replace(
        loaded,
        operating_point=replace(
            loaded.operating_point,
            windings=tuple(
                replace(winding, dc_current_a=0.0)
                for winding in loaded.operating_point.windings
            ),
        ),
    )
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

    output = Path(artifact_root_value) / "aedt-2d"
    index = output / "catalog.sqlite"
    build(ROOT / "catalog", ROOT / "schemas" / "catalog", index)
    catalog = SqliteCatalogRepository(index)
    capabilities = MatrixCapabilityRepository(
        ROOT / "compatibility" / "aedt-matrix.yml"
    ).snapshot_for(SUPPORTED_AEDT_RELEASE, SUPPORTED_AEDT_EDITION)

    outcome = generate_run(
        project,
        RunRequest(RunBackend.MAXWELL_2D, RunMode.GENERATE_ONLY),
        catalog,
        capabilities,
        output,
        maxwell3d_exporter=RecordingMaxwell3dExporter(),
        maxwell2d_exporter=PyaedtMaxwell2dExporter(),
        femm_solver=RecordingFemmSolver(),
        run_id="m5a-live-maxwell-2d",
        application_version="m5a-live-test",
    )
    manifest_path = output / "run-manifest.json"
    manifest_path.write_text(run_manifest_json(outcome.manifest), encoding="utf-8")

    result = outcome.adapter_result
    failed = [stage for stage in result.stages if not stage.succeeded]
    assert result.succeeded(), failed
    assert result.project_path.is_file()
    stage_names = {stage.name for stage in result.stages}
    assert {"materials", "validate", "save"} <= stage_names

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["backend"] == "maxwell-2d"
    material = manifest["material"]
    assert material["revisionId"] == selection.revision_id
    assert material["bhSeriesId"] == selection.bh_series_id
    plan = outcome.planned_run.solver_plan
    assert isinstance(plan, Maxwell2dDesignPlan)
    assert len(plan.core.material.bh_curve) == len(bh_series.points)
    fit = selection.snapshot.steinmetz
    assert fit is not None
    assert plan.core.material.steinmetz == fit
