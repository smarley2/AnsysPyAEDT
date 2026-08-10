"""M8a live evidence: Maxwell 3D and Maxwell 2D actually solve.

Run on the Windows workstation with AEDT 2025 R2 Commercial installed:

    set INDUCTOR_AEDT_RELEASE=2025.2
    set INDUCTOR_AEDT_EDITION=commercial
    .venv/Scripts/python.exe -m pytest -m aedt -q
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from inductor_designer.adapters.catalog.sqlite_repository import SqliteCatalogRepository
from inductor_designer.adapters.compatibility.matrix_repository import (
    MatrixCapabilityRepository,
)
from inductor_designer.adapters.pyaedt.maxwell2d import PyaedtMaxwell2dExporter
from inductor_designer.adapters.pyaedt.maxwell3d import PyaedtMaxwell3dExporter
from inductor_designer.application.services.aedt_support import (
    SUPPORTED_AEDT_EDITION,
    SUPPORTED_AEDT_RELEASE,
)
from inductor_designer.application.services.project_run import start_project_run
from inductor_designer.application.services.solve_log import SOLVE_LOG_FILENAME
from inductor_designer.simulation.run_contracts import (
    RunBackend,
    RunMode,
    RunRequest,
    RunStatus,
)
from tests.fakes.femm_solver import RecordingFemmSolver
from tests.fakes.maxwell2d_exporter import RecordingMaxwell2dExporter
from tests.fakes.maxwell_exporter import RecordingMaxwell3dExporter
from tests.unit.application.test_maxwell_export import project_for_runs
from tools.build_catalog import build

ROOT = Path(__file__).resolve().parents[3]

pytestmark = pytest.mark.aedt


def _saved_project(tmp_path: Path) -> Path:
    path = tmp_path / "solve.inductor.json"
    path.write_text("{}", encoding="utf-8")
    return path


@pytest.mark.parametrize(
    "backend", (RunBackend.MAXWELL_3D, RunBackend.MAXWELL_2D)
)
def test_generate_and_solve_completes_and_records_its_stages(
    tmp_path: Path, backend: RunBackend
) -> None:
    release = os.environ.get("INDUCTOR_AEDT_RELEASE")
    edition = os.environ.get("INDUCTOR_AEDT_EDITION")
    if not release or not edition:
        pytest.skip("Set INDUCTOR_AEDT_RELEASE and INDUCTOR_AEDT_EDITION to run AEDT tests")

    index = tmp_path / "catalog.sqlite"
    build(ROOT / "catalog", ROOT / "schemas" / "catalog", index)
    catalog = SqliteCatalogRepository(index)
    capabilities = MatrixCapabilityRepository(
        ROOT / "compatibility" / "aedt-matrix.yml"
    ).snapshot_for(SUPPORTED_AEDT_RELEASE, SUPPORTED_AEDT_EDITION)

    result = start_project_run(
        project_for_runs(),
        _saved_project(tmp_path),
        RunRequest(backend, RunMode.GENERATE_AND_SOLVE),
        catalog,
        capabilities,
        maxwell3d_exporter=(
            PyaedtMaxwell3dExporter()
            if backend is RunBackend.MAXWELL_3D
            else RecordingMaxwell3dExporter()
        ),
        maxwell2d_exporter=(
            PyaedtMaxwell2dExporter()
            if backend is RunBackend.MAXWELL_2D
            else RecordingMaxwell2dExporter()
        ),
        femm_solver=RecordingFemmSolver(),
        application_version="live-test",
    )

    manifest = result.outcome.manifest
    failed = [stage for stage in manifest.stages if stage.status.value != "succeeded"]
    assert manifest.status is RunStatus.SUCCEEDED, failed
    assert manifest.stages[-1].name == "analyze"
    assert manifest.results is None, "M8a normalizes nothing; M8b owns results"

    log = result.location.results_directory / SOLVE_LOG_FILENAME
    assert log.is_file()
    assert "analyze" in log.read_text(encoding="utf-8")

    document = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert document["status"] == "succeeded"
    assert document["mode"] == "generate-and-solve"
    assert any(artifact["kind"] == "solve-log" for artifact in document["artifacts"])
