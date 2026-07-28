from __future__ import annotations

import math
from dataclasses import replace

import pytest

import inductor_designer.application.services.run_planning as run_planning
from inductor_designer.application.services import (
    GeometryOnlyRunPlan,
    RunPlanningError,
    SolveReadyRunPlan,
    plan_run,
)
from inductor_designer.domain.aedt_target import AedtEdition, AedtRelease
from inductor_designer.domain.project import (
    CatalogCoreSelection,
    InductorProject,
    ManualCoreSelection,
    MaterialRevisionSelection,
    OperatingPoint,
)
from inductor_designer.simulation.capabilities import (
    CapabilityReviewStatus,
    CapabilitySnapshot,
)
from inductor_designer.simulation.femm_problem import FemmProblem
from inductor_designer.simulation.maxwell2d_plan import Maxwell2dDesignPlan
from inductor_designer.simulation.maxwell_plan import (
    GeometryOnlyMaxwell3dPlan,
    Maxwell3dDesignPlan,
)
from inductor_designer.simulation.run_contracts import (
    EffectiveWindingInput,
    RunBackend,
    RunMode,
    RunRequest,
)
from tests.unit.application.test_geometry_model import CATALOG
from tests.unit.domain.test_project import make_operating_point, make_project
from tests.unit.simulation.test_maxwell_plan import make_approved_material_record


def capability_snapshot(
    *,
    include_dc_fields_3d: bool | None = True,
    review_status: CapabilityReviewStatus = CapabilityReviewStatus.REVIEWED,
) -> CapabilitySnapshot:
    return CapabilitySnapshot(
        release=AedtRelease(2025, 2),
        edition=AedtEdition.COMMERCIAL,
        include_dc_fields_3d=include_dc_fields_3d,
        discovered_limits=(),
        evidence_source="Task 6 test",
        review_status=review_status,
    )


def project_with_material(
    *,
    dc_current_a: float = 0.0,
) -> InductorProject:
    material = make_approved_material_record()
    project = make_project()
    selection = MaterialRevisionSelection(
        ref=material.ref,
        revision_id=material.revision_id,
        snapshot=material,
        bh_series_id="bh",
    )
    return replace(
        project,
        design=replace(project.design, core_material=selection),
        operating_point=make_operating_point(
            replace(
                project.operating_point.windings[0],
                dc_current_a=dc_current_a,
            )
        ),
    )


@pytest.mark.parametrize(
    ("backend", "solver_plan_type"),
    [
        (RunBackend.MAXWELL_3D, Maxwell3dDesignPlan),
        (RunBackend.MAXWELL_2D, Maxwell2dDesignPlan),
        (RunBackend.FEMM, FemmProblem),
    ],
)
def test_resolved_generate_only_matrix_builds_solve_ready_plan(
    backend: RunBackend,
    solver_plan_type: type[Maxwell3dDesignPlan | Maxwell2dDesignPlan | FemmProblem],
) -> None:
    planned = plan_run(
        project_with_material(),
        RunRequest(backend, RunMode.GENERATE_ONLY),
        CATALOG,
        capability_snapshot(),
    )

    assert isinstance(planned, SolveReadyRunPlan)
    assert isinstance(planned.solver_plan, solver_plan_type)


def test_all_backends_receive_identical_effective_inputs() -> None:
    project = project_with_material()

    plan3d = plan_run(
        project,
        RunRequest(RunBackend.MAXWELL_3D, RunMode.GENERATE_ONLY),
        CATALOG,
        capability_snapshot(),
    )
    plan2d = plan_run(
        project,
        RunRequest(RunBackend.MAXWELL_2D, RunMode.GENERATE_ONLY),
        CATALOG,
        capability_snapshot(),
    )
    femm = plan_run(
        project,
        RunRequest(RunBackend.FEMM, RunMode.GENERATE_ONLY),
        CATALOG,
        capability_snapshot(),
    )

    assert plan3d.effective_inputs == plan2d.effective_inputs == femm.effective_inputs
    assert plan3d.effective_inputs[0].ac_rms_current_a == 2.0
    assert plan3d.effective_inputs[0].ac_peak_current_a == pytest.approx(
        2.0 * math.sqrt(2.0)
    )


def test_generation_permitted_validation_warnings_are_preserved_deterministically() -> None:
    project = project_with_material()
    project = replace(
        project,
        design=replace(
            project.design,
            manual_material_compatibility_acknowledged=True,
        ),
    )

    planned = plan_run(
        project,
        RunRequest(RunBackend.MAXWELL_3D, RunMode.GENERATE_ONLY),
        CATALOG,
        capability_snapshot(),
    )

    assert planned.warnings == (
        "core.snapshot.draft: Catalog record 0077071A7 is a draft pending review.",
    )
    assert not any(
        "core-material.acknowledgment-unused" in warning
        for warning in planned.warnings
    )


def test_confirmed_unresolved_maxwell3d_generate_only_builds_geometry_only_plan() -> None:
    planned = plan_run(
        replace(
            make_project(),
            operating_point=make_operating_point(
                replace(make_project().operating_point.windings[0], dc_current_a=0.0)
            ),
        ),
        RunRequest(
            RunBackend.MAXWELL_3D,
            RunMode.GENERATE_ONLY,
            confirm_geometry_only=True,
        ),
        CATALOG,
        capability_snapshot(),
    )

    assert isinstance(planned, GeometryOnlyRunPlan)
    assert isinstance(planned.solver_plan, GeometryOnlyMaxwell3dPlan)
    assert planned.warnings == (
        "core.snapshot.draft: Catalog record 0077071A7 is a draft pending review.",
        "Core material is unresolved. This confirmed Maxwell 3D Generate Only run "
        "creates geometry only; it has no material assignments, excitations, setup, "
        "mesh, reports, or solve-ready claim.",
    )


@pytest.mark.parametrize("include_dc_fields_3d", [False, None])
def test_confirmed_geometry_only_records_nonzero_dc_without_capability_gate(
    include_dc_fields_3d: bool | None,
) -> None:
    planned = plan_run(
        make_project(),
        RunRequest(
            RunBackend.MAXWELL_3D,
            RunMode.GENERATE_ONLY,
            confirm_geometry_only=True,
        ),
        CATALOG,
        capability_snapshot(include_dc_fields_3d=include_dc_fields_3d),
    )

    assert isinstance(planned, GeometryOnlyRunPlan)
    assert planned.effective_inputs[0].dc_current_a == 5.0


@pytest.mark.parametrize(
    ("backend", "mode", "confirmation"),
    [
        (RunBackend.MAXWELL_3D, RunMode.GENERATE_ONLY, False),
        (RunBackend.MAXWELL_3D, RunMode.GENERATE_AND_SOLVE, True),
        (RunBackend.MAXWELL_2D, RunMode.GENERATE_ONLY, False),
        (RunBackend.MAXWELL_2D, RunMode.GENERATE_ONLY, True),
        (RunBackend.MAXWELL_2D, RunMode.GENERATE_AND_SOLVE, False),
        (RunBackend.MAXWELL_2D, RunMode.GENERATE_AND_SOLVE, True),
        (RunBackend.FEMM, RunMode.GENERATE_ONLY, False),
        (RunBackend.FEMM, RunMode.GENERATE_ONLY, True),
        (RunBackend.FEMM, RunMode.GENERATE_AND_SOLVE, False),
        (RunBackend.FEMM, RunMode.GENERATE_AND_SOLVE, True),
    ],
)
def test_unresolved_material_matrix_blocks_every_other_operation(
    backend: RunBackend,
    mode: RunMode,
    confirmation: bool,
) -> None:
    project = make_project()
    project = replace(
        project,
        operating_point=make_operating_point(
            replace(project.operating_point.windings[0], dc_current_a=0.0)
        ),
    )

    with pytest.raises(RunPlanningError, match="unresolved"):
        plan_run(
            project,
            RunRequest(backend, mode, confirm_geometry_only=confirmation),
            CATALOG,
            capability_snapshot(),
        )


@pytest.mark.parametrize("backend", tuple(RunBackend))
@pytest.mark.parametrize("mode", tuple(RunMode))
@pytest.mark.parametrize("confirmation", [False, True])
def test_manual_material_without_acknowledgment_blocks_every_operation(
    backend: RunBackend,
    mode: RunMode,
    confirmation: bool,
) -> None:
    project = project_with_material()
    project = replace(
        project,
        design=replace(
            project.design,
            core=ManualCoreSelection(0.0269, 0.0147, 0.0112, 0.0),
            manual_material_compatibility_acknowledged=False,
        ),
    )

    with pytest.raises(RunPlanningError, match="compatibility acknowledgment"):
        plan_run(
            project,
            RunRequest(backend, mode, confirm_geometry_only=confirmation),
            CATALOG,
            capability_snapshot(),
        )


@pytest.mark.parametrize("backend", [RunBackend.MAXWELL_2D, RunBackend.FEMM])
def test_nonzero_dc_blocks_equivalent_cross_section_backends(
    backend: RunBackend,
) -> None:
    with pytest.raises(RunPlanningError, match="DC-bias"):
        plan_run(
            project_with_material(dc_current_a=5.0),
            RunRequest(backend, RunMode.GENERATE_ONLY),
            CATALOG,
            capability_snapshot(),
        )


def test_reviewed_native_dc_capability_permits_maxwell3d() -> None:
    planned = plan_run(
        project_with_material(dc_current_a=5.0),
        RunRequest(RunBackend.MAXWELL_3D, RunMode.GENERATE_ONLY),
        CATALOG,
        capability_snapshot(),
    )

    assert isinstance(planned, SolveReadyRunPlan)
    assert isinstance(planned.solver_plan, Maxwell3dDesignPlan)
    assert planned.solver_plan.windings[0].dc_current_a == 5.0


@pytest.mark.parametrize(
    ("include_dc_fields_3d", "review_status"),
    [
        (True, CapabilityReviewStatus.UNREVIEWED),
        (None, CapabilityReviewStatus.REVIEWED),
        (False, CapabilityReviewStatus.REVIEWED),
    ],
)
def test_unreviewed_or_unavailable_native_dc_capability_blocks_maxwell3d(
    include_dc_fields_3d: bool | None,
    review_status: CapabilityReviewStatus,
) -> None:
    with pytest.raises(RunPlanningError):
        plan_run(
            project_with_material(dc_current_a=5.0),
            RunRequest(RunBackend.MAXWELL_3D, RunMode.GENERATE_ONLY),
            CATALOG,
            capability_snapshot(
                include_dc_fields_3d=include_dc_fields_3d,
                review_status=review_status,
            ),
        )


def test_catalog_material_identity_is_rechecked_before_solver_plan() -> None:
    project = project_with_material()
    material = project.design.core_material
    assert material is not None
    assert isinstance(project.design.core, CatalogCoreSelection)
    mismatched = replace(
        material,
        ref=replace(material.ref, grade="26"),
        snapshot=replace(
            material.snapshot,
            ref=replace(material.snapshot.ref, grade="26"),
        ),
    )
    project = replace(
        project,
        design=replace(project.design, core_material=mismatched),
    )

    with pytest.raises(RunPlanningError, match="does not match"):
        plan_run(
            project,
            RunRequest(RunBackend.MAXWELL_3D, RunMode.GENERATE_ONLY),
            CATALOG,
            capability_snapshot(),
        )


def test_effective_winding_inputs_is_called_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_effective_winding_inputs = run_planning.effective_winding_inputs
    calls = 0

    def recording_effective_winding_inputs(
        operating_point: OperatingPoint,
    ) -> tuple[EffectiveWindingInput, ...]:
        nonlocal calls
        calls += 1
        return real_effective_winding_inputs(operating_point)

    monkeypatch.setattr(
        run_planning,
        "effective_winding_inputs",
        recording_effective_winding_inputs,
    )

    plan_run(
        project_with_material(),
        RunRequest(RunBackend.MAXWELL_3D, RunMode.GENERATE_ONLY),
        CATALOG,
        capability_snapshot(),
    )

    assert calls == 1
