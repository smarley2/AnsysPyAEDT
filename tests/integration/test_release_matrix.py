from __future__ import annotations

from pathlib import Path

from inductor_designer.adapters.compatibility.matrix_repository import (
    MatrixCapabilityRepository,
)
from inductor_designer.application.services.maxwell_export import RunOutcome, generate_run
from inductor_designer.domain.aedt_target import AedtEdition, AedtRelease
from inductor_designer.simulation.capabilities import DcBiasStrategy
from inductor_designer.simulation.maxwell_plan import Maxwell3dDesignPlan
from inductor_designer.simulation.run_contracts import (
    DimensionalRepresentation,
    RunBackend,
    RunMode,
    RunRequest,
    RunStatus,
)
from tests.fakes.femm_solver import RecordingFemmSolver
from tests.fakes.maxwell2d_exporter import RecordingMaxwell2dExporter
from tests.fakes.maxwell_exporter import RecordingMaxwell3dExporter
from tests.unit.application.test_geometry_model import CATALOG
from tests.unit.application.test_maxwell_export import project_for_runs

ROOT = Path(__file__).resolve().parents[2]
REAL_MATRIX = ROOT / "compatibility" / "aedt-matrix.yml"

SYNTHETIC = """\
schemaVersion: 1
rows:
  - release: "2025.2"
    edition: commercial
    status: passed
    includeDcFields3d: true
    discoveredLimits: []
    evidenceReviewedAt: "2026-07-17T00:00:00Z"
    evidenceReviewedBy: fabio
"""


def generate(matrix: Path, backend: RunBackend, tmp_path: Path) -> RunOutcome:
    capabilities = MatrixCapabilityRepository(matrix).snapshot_for(
        AedtRelease(2025, 2),
        AedtEdition.COMMERCIAL,
    )
    return generate_run(
        project_for_runs(),
        RunRequest(backend, RunMode.GENERATE_ONLY),
        CATALOG,
        capabilities,
        tmp_path,
        maxwell3d_exporter=RecordingMaxwell3dExporter(),
        maxwell2d_exporter=RecordingMaxwell2dExporter(),
        femm_solver=RecordingFemmSolver(),
        run_id=f"release-matrix-{backend.value}",
        application_version="release-matrix-test",
    )


def test_real_matrix_2025_2_identifies_native(tmp_path: Path) -> None:
    outcome = generate(REAL_MATRIX, RunBackend.MAXWELL_3D, tmp_path)
    plan = outcome.planned_run.solver_plan
    assert isinstance(plan, Maxwell3dDesignPlan)
    assert plan.dc_bias is not None
    assert plan.dc_bias.strategy is DcBiasStrategy.NATIVE_INCLUDE_DC_FIELDS
    assert plan.dc_bias.approximate is False
    assert outcome.manifest.status is RunStatus.SUCCEEDED


def test_synthetic_native_row_identifies_native(tmp_path: Path) -> None:
    matrix = tmp_path / "m.yml"
    matrix.write_text(SYNTHETIC, encoding="utf-8")
    outcome = generate(matrix, RunBackend.MAXWELL_3D, tmp_path)
    plan = outcome.planned_run.solver_plan
    assert isinstance(plan, Maxwell3dDesignPlan)
    assert plan.dc_bias is not None
    assert plan.dc_bias.strategy is DcBiasStrategy.NATIVE_INCLUDE_DC_FIELDS


def test_two_d_manifest_is_marked_approximate_model(tmp_path: Path) -> None:
    matrix = tmp_path / "m.yml"
    matrix.write_text(SYNTHETIC, encoding="utf-8")
    outcome = generate(matrix, RunBackend.MAXWELL_2D, tmp_path)
    assert outcome.manifest.status is RunStatus.SUCCEEDED
    assert outcome.manifest.dimensional_representation is (
        DimensionalRepresentation.EQUIVALENT_CROSS_SECTION
    )
    assert any("approximate" in warning for warning in outcome.manifest.warnings)
