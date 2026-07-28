from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from inductor_designer.adapters.femm.solver import PyfemmSolver
from inductor_designer.adapters.persistence.project_repository import ProjectRepository
from inductor_designer.adapters.persistence.schema_repository import SchemaRepository
from inductor_designer.application.ports.femm_solver import FemmSolveRequest
from inductor_designer.application.services.maxwell_export import (
    RunOutcome,
    generate_run,
    run_manifest_json,
)
from inductor_designer.application.services.run_planning import (
    RunPlanningError,
    plan_run,
)
from inductor_designer.domain.aedt_target import AedtEdition, AedtRelease
from inductor_designer.domain.project import (
    InductorProject,
    ManualCoreSelection,
    MaterialRevisionSelection,
)
from inductor_designer.domain.validation import ValidationCategory, validate_project
from inductor_designer.domain.winding import CurrentDirection, WindingDirection
from inductor_designer.simulation.capabilities import (
    CapabilityReviewStatus,
    CapabilitySnapshot,
)
from inductor_designer.simulation.femm_problem import FemmProblem
from inductor_designer.simulation.maxwell2d_plan import Maxwell2dDesignPlan
from inductor_designer.simulation.maxwell_plan import Maxwell3dDesignPlan, Polarity
from inductor_designer.simulation.run_contracts import (
    RunBackend,
    RunMode,
    RunRequest,
)
from tests.fakes.femm_module import FakeFemmModule, FakeFemmModuleFactory
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


def _assert_native_plans_consume_operating_point_and_material(
    outcomes: dict[RunBackend, RunOutcome],
) -> None:
    maxwell3d = outcomes[RunBackend.MAXWELL_3D].planned_run.solver_plan
    maxwell2d = outcomes[RunBackend.MAXWELL_2D].planned_run.solver_plan
    femm = outcomes[RunBackend.FEMM].planned_run.solver_plan
    assert isinstance(maxwell3d, Maxwell3dDesignPlan)
    assert isinstance(maxwell2d, Maxwell2dDesignPlan)
    assert isinstance(femm, FemmProblem)

    maxwell3d_winding = maxwell3d.windings[0]
    assert maxwell3d.setup.frequency_hz == 125_000.0
    assert maxwell3d_winding.winding_id == "w1"
    assert maxwell3d_winding.current_peak_a == pytest.approx(2.8284271247461903)
    assert maxwell3d_winding.phase_deg == 30.0
    assert maxwell3d_winding.dc_current_a == 0.0
    assert tuple(
        turn.terminal.polarity for turn in maxwell3d_winding.turns
    ) == (Polarity.NEGATIVE,) * 20
    assert maxwell3d.core.material.name == "Magnetics_Kool_Mu_60_r0123456789ab"
    assert maxwell3d.core.material.material_revision == "0123456789ab"
    assert maxwell3d.core.material.bh_series_id == "bh-100c"
    assert maxwell3d.core.material.bh_curve == ((0.0, 0.0), (0.03, 120.0))

    maxwell2d_winding = maxwell2d.windings[0]
    assert maxwell2d.setup.frequency_hz == 125_000.0
    assert maxwell2d_winding.winding_id == "w1"
    assert maxwell2d_winding.current_peak_a == pytest.approx(2.8284271247461903)
    assert maxwell2d_winding.phase_deg == 30.0
    assert maxwell2d_winding.dc_current_a == 0.0
    assert tuple(
        conductor.polarity for conductor in maxwell2d_winding.conductors
    ) == (Polarity.NEGATIVE, Polarity.POSITIVE) * 20
    assert maxwell2d.core.material.name == "Magnetics_Kool_Mu_60_r0123456789ab"
    assert maxwell2d.core.material.material_revision == "0123456789ab"
    assert maxwell2d.core.material.bh_series_id == "bh-100c"
    assert maxwell2d.core.material.bh_curve == ((0.0, 0.0), (0.03, 120.0))

    assert femm.frequency_hz == 125_000.0
    assert len(femm.circuits) == 1
    assert femm.circuits[0].name == "w1"
    assert femm.circuits[0].current_peak_a == pytest.approx(2.8284271247461903)
    assert femm.circuits[0].phase_deg == 30.0
    assert tuple(conductor.turns for conductor in femm.conductors) == (-1, 1) * 20
    assert femm.core.material == "Magnetics_Kool_Mu_60_r0123456789ab"
    femm_core_material = next(
        material for material in femm.materials if material.name == femm.core.material
    )
    assert femm_core_material.bh_points == ((0.0, 0.0), (0.03, 120.0))


def _assert_femm_adapter_applies_peak_phasor(
    outcome: RunOutcome,
    tmp_path: Path,
) -> None:
    problem = outcome.planned_run.solver_plan
    assert isinstance(problem, FemmProblem)
    module = FakeFemmModule()
    PyfemmSolver(module_factory=FakeFemmModuleFactory(module)).solve(
        FemmSolveRequest(
            problem=problem,
            output_directory=tmp_path,
            project_name="m6-femm-phase-acceptance",
            analyze=False,
        )
    )

    calls = [args for name, args in module.calls if name == "mi_addcircprop"]
    assert len(calls) == 1
    assert calls[0][0] == "w1"
    assert calls[0][1] == pytest.approx(
        complex(2.449489742783178, 1.414213562373095)
    )
    assert calls[0][2] == 1


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
    design_winding = loaded.design.windings[0]
    assert operating_winding.ac_rms_current_a == 2.0
    assert operating_winding.ac_phase_deg == 30.0
    assert operating_winding.dc_current_a == 0.0
    assert operating_winding.current_direction is CurrentDirection.FORWARD
    assert design_winding.winding_direction is WindingDirection.CLOCKWISE

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
    _assert_native_plans_consume_operating_point_and_material(outcomes)
    _assert_femm_adapter_applies_peak_phasor(
        outcomes[RunBackend.FEMM],
        tmp_path,
    )

    project_with_femm_dc = replace(
        loaded,
        operating_point=replace(
            loaded.operating_point,
            windings=(replace(operating_winding, dc_current_a=1.0),),
        ),
    )
    # FEMM uses the 2D capability policy and has no native DC source field:
    # exact zero reaches FemmProblem above, while nonzero DC is rejected here.
    with pytest.raises(RunPlanningError, match="Maxwell 2D DC-bias generation is blocked"):
        plan_run(
            project_with_femm_dc,
            RunRequest(RunBackend.FEMM, RunMode.GENERATE_ONLY),
            CATALOG,
            CAPABILITIES,
        )

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


def test_manual_core_material_acknowledgment_round_trips_and_validates(
    tmp_path: Path,
) -> None:
    repository = ProjectRepository(SchemaRepository(ROOT / "schemas"))
    first_path = tmp_path / "manual-first.inductor.json"
    second_path = tmp_path / "manual-second.inductor.json"
    project = _acceptance_project()
    manual_core = ManualCoreSelection(
        outer_diameter_m=0.0274,
        inner_diameter_m=0.0144,
        height_m=0.0112,
        corner_radius_m=0.0005,
    )
    project = replace(
        project,
        design=replace(
            project.design,
            core=manual_core,
            manual_material_compatibility_acknowledged=True,
        ),
    )

    repository.save(project, first_path)
    loaded = repository.load(first_path)
    repository.save(loaded, second_path)

    assert loaded == project
    assert loaded.design.core == manual_core
    assert loaded.design.core_material == project.design.core_material
    assert loaded.design.manual_material_compatibility_acknowledged is True
    assert second_path.read_bytes() == first_path.read_bytes()
    document = json.loads(first_path.read_text(encoding="utf-8"))
    assert document["design"]["core"] == {
        "kind": "manual",
        "outerDiameterM": 0.0274,
        "innerDiameterM": 0.0144,
        "heightM": 0.0112,
        "cornerRadiusM": 0.0005,
    }
    assert document["design"]["manualMaterialCompatibilityAcknowledged"] is True

    issues = validate_project(
        loaded,
        known_conductors=CATALOG.list_conductor_names(),
    )
    assert not [issue for issue in issues if issue.category is ValidationCategory.ERROR]
    issue_codes = {issue.code for issue in issues}
    assert issue_codes.isdisjoint(
        {
            "core-material.manual-unacknowledged",
            "core-material.acknowledgment-unused",
        }
    )
