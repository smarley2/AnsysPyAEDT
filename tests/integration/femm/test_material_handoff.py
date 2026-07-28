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
from inductor_designer.application.services.aedt_support import (
    SUPPORTED_AEDT_EDITION,
    SUPPORTED_AEDT_RELEASE,
)
from inductor_designer.application.services.maxwell_export import (
    generate_run,
    run_manifest_json,
)
from inductor_designer.domain.project import CatalogCoreSelection
from inductor_designer.simulation.femm_problem import FemmProblem
from inductor_designer.simulation.run_contracts import RunBackend, RunMode, RunRequest
from tests.fakes.maxwell2d_exporter import RecordingMaxwell2dExporter
from tests.fakes.maxwell_exporter import RecordingMaxwell3dExporter
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
    loaded = repository.load(project_path)
    # This test isolates material transfer. M6 blocks nonzero DC for FEMM.
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

    femm_output = Path(artifact_root_value) / "femm"
    index = femm_output / "catalog.sqlite"
    build(ROOT / "catalog", ROOT / "schemas" / "catalog", index)
    catalog = SqliteCatalogRepository(index)
    capabilities = MatrixCapabilityRepository(
        ROOT / "compatibility" / "aedt-matrix.yml"
    ).snapshot_for(SUPPORTED_AEDT_RELEASE, SUPPORTED_AEDT_EDITION)

    outcome = generate_run(
        project,
        RunRequest(RunBackend.FEMM, RunMode.GENERATE_ONLY),
        catalog,
        capabilities,
        femm_output,
        maxwell3d_exporter=RecordingMaxwell3dExporter(),
        maxwell2d_exporter=RecordingMaxwell2dExporter(),
        femm_solver=PyfemmSolver(),
        run_id="m5a-live-femm",
        application_version="m5a-live-test",
    )
    manifest_path = femm_output / "run-manifest.json"
    manifest_path.write_text(run_manifest_json(outcome.manifest), encoding="utf-8")

    result = outcome.adapter_result
    assert result.fem_path.is_file()
    assert result.analyzed is False
    problem = outcome.planned_run.solver_plan
    assert isinstance(problem, FemmProblem)
    material_name = problem.core.material
    expected_points = next(
        material.bh_points
        for material in problem.materials
        if material.name == material_name
    )
    actual_points = read_material_bh_points(
        result.fem_path,
        material_name,
    )
    assert expected_points
    assert len(actual_points) == len(expected_points)
    for actual, expected in zip(actual_points, expected_points, strict=True):
        assert actual == pytest.approx(expected)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    material = manifest["material"]
    selection = project.design.core_material
    assert selection is not None
    assert material["revisionId"] == selection.revision_id
    assert material["bhSeriesId"] == selection.bh_series_id
