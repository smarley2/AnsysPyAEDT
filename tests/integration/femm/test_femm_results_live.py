"""M8b live evidence: a FEMM solve produces a normalized scalar result set.

    set INDUCTOR_FEMM_LIVE=1
    .venv/Scripts/python.exe -m pytest -m femm -q

The assertions are about the contract, never about a physical value: every
requested scalar quantity is either available with a unit and a provenance, or
unavailable with a dotted reason.
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
from inductor_designer.domain.project import MaterialRevisionSelection
from inductor_designer.simulation.result_vocabulary import SCALAR_QUANTITIES
from inductor_designer.simulation.run_contracts import (
    ResultAvailability,
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


def test_a_femm_solve_produces_a_complete_normalized_result_set(
    tmp_path: Path,
) -> None:
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
                material.ref, material.revision_id, material, "bh"
            ),
        ),
        operating_point=replace(
            project.operating_point,
            windings=tuple(
                replace(winding, dc_current_a=0.0)
                for winding in project.operating_point.windings
            ),
        ),
        simulation_recipe=replace(
            project.simulation_recipe, requested_outputs=SCALAR_QUANTITIES
        ),
    )
    document_path = tmp_path / "results.inductor.json"
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
    assert manifest.results is not None

    requested = set(SCALAR_QUANTITIES)
    reported = {quantity.quantity for quantity in manifest.results.quantities}
    assert reported == requested, "every requested scalar quantity must be accounted for"

    for entry in manifest.results.quantities:
        if entry.availability is ResultAvailability.AVAILABLE:
            assert entry.unit and entry.provenance and entry.reason is None
        else:
            assert entry.value is None
            assert entry.reason is not None
            assert entry.reason.startswith(f"{entry.quantity.value}.")

    exported = result.location.results_directory / "results.json"
    assert exported.is_file()
    assert (result.location.results_directory / "results.csv").is_file()
    document = json.loads(exported.read_text(encoding="utf-8"))
    assert document["quantities"]
