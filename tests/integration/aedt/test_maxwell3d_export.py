from __future__ import annotations

import os
from pathlib import Path

import pytest

from inductor_designer.adapters.catalog.sqlite_repository import SqliteCatalogRepository
from inductor_designer.adapters.compatibility.matrix_repository import (
    MatrixCapabilityRepository,
)
from inductor_designer.adapters.pyaedt.maxwell3d import PyaedtMaxwell3dExporter
from inductor_designer.application.ports.maxwell_exporter import STAGE_NAMES
from inductor_designer.application.services.aedt_support import (
    SUPPORTED_AEDT_EDITION,
    SUPPORTED_AEDT_RELEASE,
)
from inductor_designer.application.services.maxwell_export import generate_run
from inductor_designer.simulation.run_contracts import RunBackend, RunMode, RunRequest
from tests.fakes.femm_solver import RecordingFemmSolver
from tests.fakes.maxwell2d_exporter import RecordingMaxwell2dExporter
from tests.unit.application.test_maxwell_export import project_for_runs
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
    project = project_for_runs()
    matrix_path = ROOT / "compatibility" / "aedt-matrix.yml"
    capabilities = MatrixCapabilityRepository(matrix_path).snapshot_for(
        SUPPORTED_AEDT_RELEASE,
        SUPPORTED_AEDT_EDITION,
    )

    outcome = generate_run(
        project,
        RunRequest(RunBackend.MAXWELL_3D, RunMode.GENERATE_ONLY),
        catalog,
        capabilities,
        tmp_path / "out",
        maxwell3d_exporter=PyaedtMaxwell3dExporter(),
        maxwell2d_exporter=RecordingMaxwell2dExporter(),
        femm_solver=RecordingFemmSolver(),
        run_id="live-maxwell-3d",
        application_version="live-test",
    )

    result = outcome.adapter_result
    failed = [stage for stage in result.stages if not stage.succeeded]
    assert result.succeeded(STAGE_NAMES), failed
    assert result.project_path.exists()
