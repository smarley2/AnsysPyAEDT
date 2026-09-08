"""M8a live evidence: FEMM actually analyzes when the run mode asks for it.

Run on the Windows workstation with FEMM 4.2 and pyfemm installed:

    set INDUCTOR_FEMM_LIVE=1
    .venv/Scripts/python.exe -m pytest -m femm -q
"""

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
from inductor_designer.adapters.persistence.project_repository import project_from_document
from inductor_designer.application.services.aedt_support import (
    SUPPORTED_AEDT_EDITION,
    SUPPORTED_AEDT_RELEASE,
)
from inductor_designer.application.services.project_run import start_project_run
from inductor_designer.application.services.solve_log import SOLVE_LOG_FILENAME
from inductor_designer.domain.project import MaterialRevisionSelection
from inductor_designer.simulation.run_contracts import (
    RunBackend,
    RunMode,
    RunRequest,
    RunStatus,
)
from tests.fakes.maxwell2d_exporter import RecordingMaxwell2dExporter
from tests.fakes.maxwell_exporter import RecordingMaxwell3dExporter
from tests.unit.simulation.test_maxwell_plan import make_approved_material_record
from tools.build_catalog import build

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "tests" / "fixtures" / "sample_geometry_project.inductor.json"

pytestmark = pytest.mark.femm


def test_generate_and_solve_analyzes_and_logs_its_stages(tmp_path: Path) -> None:
    if importlib.util.find_spec("femm") is None or os.environ.get("INDUCTOR_FEMM_LIVE") != "1":
        pytest.skip("Set INDUCTOR_FEMM_LIVE=1 with the femm package installed to run FEMM tests")

    index = tmp_path / "catalog.sqlite"
    build(ROOT / "catalog", ROOT / "schemas" / "catalog", index)
    catalog = SqliteCatalogRepository(index)
    project = project_from_document(json.loads(FIXTURE.read_text(encoding="utf-8")))
    material = make_approved_material_record()
    project = replace(
        project,
        design=replace(
            project.design,
            core_material=MaterialRevisionSelection(
                material.ref,
                material.revision_id,
                material,
                "bh",
            ),
        ),
        operating_point=replace(
            project.operating_point,
            windings=tuple(
                replace(winding, dc_current_a=0.0)
                for winding in project.operating_point.windings
            ),
        ),
    )
    document_path = tmp_path / "solve.inductor.json"
    document_path.write_text("{}", encoding="utf-8")
    capabilities = MatrixCapabilityRepository(
        ROOT / "compatibility" / "aedt-matrix.yml"
    ).snapshot_for(SUPPORTED_AEDT_RELEASE, SUPPORTED_AEDT_EDITION)

    result = start_project_run(
        project,
        document_path,
        RunRequest(RunBackend.FEMM, RunMode.GENERATE_AND_SOLVE),
        catalog,
        capabilities,
        maxwell3d_exporter=RecordingMaxwell3dExporter(),
        maxwell2d_exporter=RecordingMaxwell2dExporter(),
        femm_solver=PyfemmSolver(),
        application_version="live-test",
    )

    manifest = result.outcome.manifest
    assert manifest.status is RunStatus.SUCCEEDED
    assert [stage.name for stage in manifest.stages] == ["generate", "analyze"]
    # M8a left `results` None; M8b made a solved run carry its normalized set,
    # and this assertion still demanded the M8a shape until 2026-08-18. Live
    # tests sit behind the `femm` marker, so the normal gate never ran it and
    # nothing noticed. Assert the M8b contract instead of the absence.
    assert manifest.results is not None
    assert manifest.results.backend is RunBackend.FEMM
    assert {entry.quantity for entry in manifest.results.quantities} == set(
        project.simulation_recipe.requested_outputs
    )

    log = result.location.results_directory / SOLVE_LOG_FILENAME
    assert log.is_file()
    assert "analyze" in log.read_text(encoding="utf-8")

    document = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert document["mode"] == "generate-and-solve"
    assert document["status"] == "succeeded"
