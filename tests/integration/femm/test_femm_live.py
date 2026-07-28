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
from inductor_designer.application.services.maxwell_export import generate_run
from inductor_designer.domain.project import MaterialRevisionSelection
from inductor_designer.simulation.femm_problem import FemmProblem
from inductor_designer.simulation.run_contracts import (
    ManifestArtifact,
    RunBackend,
    RunMode,
    RunRequest,
)
from tests.fakes.maxwell2d_exporter import RecordingMaxwell2dExporter
from tests.fakes.maxwell_exporter import RecordingMaxwell3dExporter
from tests.unit.simulation.test_maxwell_plan import make_approved_material_record
from tools.build_catalog import build

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "tests" / "fixtures" / "sample_geometry_project.inductor.json"

pytestmark = pytest.mark.femm


def test_femm_generate_only_writes_resolved_two_winding_project(
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
    assert tuple(winding.winding_id for winding in project.design.windings) == (
        "w1",
        "w2",
    )
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
    assert tuple(winding.winding_id for winding in outcome.manifest.windings) == (
        "w1",
        "w2",
    )
    assert outcome.manifest.artifacts == (
        ManifestArtifact("femm-project", result.fem_path.as_posix()),
    )

    fem_text = result.fem_path.read_text(encoding="utf-8", errors="ignore")
    assert "w1" in fem_text
    assert "w2" in fem_text
    problem = outcome.planned_run.solver_plan
    assert isinstance(problem, FemmProblem)
    assert tuple(circuit.name for circuit in problem.circuits) == ("w1", "w2")
    depth_m = problem.depth_m
    depth_candidates = {f"{depth_m:g}", f"{depth_m}", f"{depth_m:.6g}", f"{depth_m:.4f}"}
    assert any(candidate in fem_text for candidate in depth_candidates)
