from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

from inductor_designer.adapters.catalog.sqlite_repository import SqliteCatalogRepository
from inductor_designer.adapters.compatibility.matrix_repository import (
    MatrixCapabilityRepository,
)
from inductor_designer.adapters.femm.solver import PyfemmSolver
from inductor_designer.application.services.aedt_support import (
    SUPPORTED_AEDT_EDITION,
    SUPPORTED_AEDT_RELEASE,
)
from inductor_designer.application.services.maxwell_export import generate_run
from inductor_designer.simulation.femm_problem import FemmProblem
from inductor_designer.simulation.run_contracts import RunBackend, RunMode, RunRequest
from tests.fakes.maxwell2d_exporter import RecordingMaxwell2dExporter
from tests.fakes.maxwell_exporter import RecordingMaxwell3dExporter
from tests.unit.application.test_maxwell_export import project_for_runs
from tools.build_catalog import build

ROOT = Path(__file__).resolve().parents[3]

pytestmark = pytest.mark.femm


def test_femm_solves_sample_project(tmp_path: Path) -> None:
    if importlib.util.find_spec("femm") is None or os.environ.get("INDUCTOR_FEMM_LIVE") != "1":
        pytest.skip("Set INDUCTOR_FEMM_LIVE=1 with the femm package installed to run FEMM tests")

    index = tmp_path / "catalog.sqlite"
    build(ROOT / "catalog", ROOT / "schemas" / "catalog", index)
    catalog = SqliteCatalogRepository(index)
    project = project_for_runs()
    capabilities = MatrixCapabilityRepository(
        ROOT / "compatibility" / "aedt-matrix.yml"
    ).snapshot_for(SUPPORTED_AEDT_RELEASE, SUPPORTED_AEDT_EDITION)

    outcome = generate_run(
        project,
        RunRequest(RunBackend.FEMM, RunMode.GENERATE_ONLY),
        catalog,
        capabilities,
        tmp_path / "out",
        maxwell3d_exporter=RecordingMaxwell3dExporter(),
        maxwell2d_exporter=RecordingMaxwell2dExporter(),
        femm_solver=PyfemmSolver(),
        run_id="live-femm",
        application_version="live-test",
    )

    result = outcome.adapter_result
    assert result.fem_path.exists()
    assert result.analyzed is False
    assert result.results is None

    fem_text = result.fem_path.read_text(encoding="utf-8", errors="ignore")
    assert "w1" in fem_text
    problem = outcome.planned_run.solver_plan
    assert isinstance(problem, FemmProblem)
    depth_m = problem.depth_m
    depth_candidates = {f"{depth_m:g}", f"{depth_m}", f"{depth_m:.6g}", f"{depth_m:.4f}"}
    assert any(candidate in fem_text for candidate in depth_candidates)
