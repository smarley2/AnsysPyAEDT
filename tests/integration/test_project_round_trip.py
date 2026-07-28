from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from inductor_designer.adapters.persistence.project_repository import ProjectRepository
from inductor_designer.adapters.persistence.schema_repository import SchemaRepository
from inductor_designer.application.services.maxwell_export import (
    RunOutcome,
    generate_run,
    run_manifest_json,
)
from inductor_designer.domain.aedt_target import AedtEdition, AedtRelease
from inductor_designer.domain.project import (
    InductorProject,
    MaterialRevisionSelection,
)
from inductor_designer.domain.validation import ValidationCategory, validate_project
from inductor_designer.domain.winding import CurrentDirection
from inductor_designer.simulation.capabilities import (
    CapabilityReviewStatus,
    CapabilitySnapshot,
)
from inductor_designer.simulation.femm_problem import FemmProblem
from inductor_designer.simulation.maxwell2d_plan import Maxwell2dDesignPlan
from inductor_designer.simulation.maxwell_plan import Maxwell3dDesignPlan
from inductor_designer.simulation.run_contracts import (
    RunBackend,
    RunMode,
    RunRequest,
)
from tests.fakes.femm_solver import RecordingFemmSolver
from tests.fakes.maxwell2d_exporter import RecordingMaxwell2dExporter
from tests.fakes.maxwell_exporter import RecordingMaxwell3dExporter
from tests.unit.application.test_geometry_model import CATALOG
from tests.unit.domain.test_project import make_project
from tests.unit.simulation.test_maxwell_plan import make_multi_bh_material_record

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIRECTORY = Path("outputs/m6")
GOLDEN_FILES = {
    RunBackend.MAXWELL_3D: "m6-maxwell3d-run-manifest.json",
    RunBackend.MAXWELL_2D: "m6-maxwell2d-run-manifest.json",
    RunBackend.FEMM: "m6-femm-run-manifest.json",
}
CAPABILITIES = CapabilitySnapshot(
    release=AedtRelease(2025, 2),
    edition=AedtEdition.COMMERCIAL,
    include_dc_fields_3d=True,
    discovered_limits=(),
    evidence_source="M6 acceptance test",
    review_status=CapabilityReviewStatus.REVIEWED,
)


def _acceptance_project() -> InductorProject:
    project = make_project()
    material = make_multi_bh_material_record()
    return replace(
        project,
        design=replace(
            project.design,
            core_material=MaterialRevisionSelection(
                ref=material.ref,
                revision_id=material.revision_id,
                snapshot=material,
                bh_series_id="bh-100c",
            ),
        ),
        operating_point=replace(
            project.operating_point,
            frequency_hz=125_000.0,
            winding_temperature_c=45.0,
            core_temperature_c=80.0,
            windings=(
                replace(
                    project.operating_point.windings[0],
                    ac_phase_deg=30.0,
                    dc_current_a=0.0,
                    current_direction=CurrentDirection.FORWARD,
                ),
            ),
        ),
    )


def _generate_all_backends(project: InductorProject) -> dict[RunBackend, RunOutcome]:
    maxwell3d = RecordingMaxwell3dExporter()
    maxwell2d = RecordingMaxwell2dExporter()
    femm = RecordingFemmSolver()
    outcomes = {
        backend: generate_run(
            project,
            RunRequest(backend, RunMode.GENERATE_ONLY),
            CATALOG,
            CAPABILITIES,
            OUTPUT_DIRECTORY,
            maxwell3d_exporter=maxwell3d,
            maxwell2d_exporter=maxwell2d,
            femm_solver=femm,
            run_id=f"m6-{backend.value}",
            application_version="0.6.0-test",
        )
        for backend in RunBackend
    }

    assert len(maxwell3d.requests) == 1
    assert maxwell3d.geometry_only_requests == []
    assert len(maxwell2d.requests) == 1
    assert len(femm.requests) == 1
    assert femm.requests[0].analyze is False
    return outcomes


def test_m6_project_round_trip_and_all_backend_manifests(tmp_path: Path) -> None:
    repository = ProjectRepository(SchemaRepository(ROOT / "schemas"))
    first_path = tmp_path / "first.inductor.json"
    second_path = tmp_path / "second.inductor.json"

    project = _acceptance_project()
    repository.save(project, first_path)
    loaded = repository.load(first_path)
    repository.save(loaded, second_path)

    assert loaded == project
    assert second_path.read_bytes() == first_path.read_bytes()
    document = json.loads(first_path.read_text(encoding="utf-8"))
    assert document["schemaVersion"] == 5
    assert set(document) == {
        "schemaVersion",
        "projectId",
        "metadata",
        "design",
        "operatingPoint",
        "simulationRecipe",
    }

    assert loaded.operating_point.frequency_hz == 125_000.0
    assert loaded.operating_point.winding_temperature_c == 45.0
    assert loaded.operating_point.core_temperature_c == 80.0
    operating_winding = loaded.operating_point.windings[0]
    assert operating_winding.ac_rms_current_a == 2.0
    assert operating_winding.ac_phase_deg == 30.0
    assert operating_winding.dc_current_a == 0.0
    assert operating_winding.current_direction is CurrentDirection.FORWARD

    material = loaded.design.core_material
    assert material is not None
    assert material.revision_id == "0123456789ab"
    assert material.bh_series_id == "bh-100c"
    assert any(series.series_id == "bh-100c" for series in material.snapshot.series)
    assert loaded.design.manual_material_compatibility_acknowledged is False
    assert not [
        issue
        for issue in validate_project(
            loaded,
            known_conductors=CATALOG.list_conductor_names(),
        )
        if issue.category is ValidationCategory.ERROR
    ]

    outcomes = _generate_all_backends(loaded)
    plans = {
        backend: outcome.planned_run.solver_plan
        for backend, outcome in outcomes.items()
    }
    assert isinstance(plans[RunBackend.MAXWELL_3D], Maxwell3dDesignPlan)
    assert isinstance(plans[RunBackend.MAXWELL_2D], Maxwell2dDesignPlan)
    assert isinstance(plans[RunBackend.FEMM], FemmProblem)

    effective_inputs = {
        outcome.planned_run.effective_inputs for outcome in outcomes.values()
    }
    assert len(effective_inputs) == 1
    effective = next(iter(effective_inputs))
    assert len(effective) == 1
    assert effective[0].winding_id == "w1"
    assert effective[0].ac_rms_current_a == 2.0
    assert effective[0].ac_peak_current_a == pytest.approx(2.8284271247461903)
    assert effective[0].phase_deg == 30.0
    assert effective[0].dc_current_a == 0.0
    assert effective[0].current_direction is CurrentDirection.FORWARD

    golden_directory = ROOT / "tests" / "golden"
    for backend, outcome in outcomes.items():
        assert outcome.manifest.windings == effective
        expected = (golden_directory / GOLDEN_FILES[backend]).read_text(
            encoding="utf-8"
        )
        assert run_manifest_json(outcome.manifest) == expected
