from __future__ import annotations

from dataclasses import dataclass

from inductor_designer.application.ports.catalog import CatalogRepository
from inductor_designer.application.services.geometry_model import (
    GeometryModelError,
    build_geometry_model,
)
from inductor_designer.domain.aedt_target import ModelDimension
from inductor_designer.domain.project import (
    CatalogCoreSelection,
    InductorProject,
    ManualCoreSelection,
)
from inductor_designer.domain.validation import (
    ValidationCategory,
    validate_project,
)
from inductor_designer.simulation.capabilities import (
    CapabilitySnapshot,
    DcBiasStrategy,
    select_dc_bias_strategy,
)
from inductor_designer.simulation.femm_problem import (
    FemmProblem,
    femm_problem_from_plan,
)
from inductor_designer.simulation.maxwell2d_plan import Maxwell2dDesignPlan
from inductor_designer.simulation.maxwell_plan import (
    GeometryOnlyMaxwell3dPlan,
    Maxwell3dDesignPlan,
    PlanBuildError,
)
from inductor_designer.simulation.plan_builder import (
    build_geometry_only_maxwell3d_plan,
    build_maxwell3d_plan,
)
from inductor_designer.simulation.plan_builder2d import build_maxwell2d_plan
from inductor_designer.simulation.run_contracts import (
    EffectiveWindingInput,
    RunBackend,
    RunMode,
    RunRequest,
    effective_winding_inputs,
)

_GEOMETRY_ONLY_WARNING = (
    "Core material is unresolved. This confirmed Maxwell 3D Generate Only run "
    "creates geometry only; it has no material assignments, excitations, setup, "
    "mesh, reports, or solve-ready claim."
)


class RunPlanningError(ValueError):
    def __init__(self, issues: tuple[str, ...]) -> None:
        self.issues = issues
        super().__init__("; ".join(issues))


@dataclass(frozen=True, slots=True)
class SolveReadyRunPlan:
    request: RunRequest
    effective_inputs: tuple[EffectiveWindingInput, ...]
    solver_plan: Maxwell3dDesignPlan | Maxwell2dDesignPlan | FemmProblem
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GeometryOnlyRunPlan:
    request: RunRequest
    effective_inputs: tuple[EffectiveWindingInput, ...]
    solver_plan: GeometryOnlyMaxwell3dPlan
    warnings: tuple[str, ...]


PlannedRun = SolveReadyRunPlan | GeometryOnlyRunPlan


def plan_run(
    project: InductorProject,
    request: RunRequest,
    catalog: CatalogRepository,
    capabilities: CapabilitySnapshot,
) -> PlannedRun:
    validation_issues = validate_project(
        project,
        known_conductors=catalog.list_conductor_names(),
    )
    errors = tuple(
        f"{issue.code}: {issue.message}"
        for issue in validation_issues
        if issue.category is ValidationCategory.ERROR
    )
    if errors:
        raise RunPlanningError(errors)

    core = project.design.core
    if core is None:
        raise RunPlanningError(("Project has no core selection; run planning needs one.",))
    if not project.design.windings:
        raise RunPlanningError(("Project has no windings; run planning needs at least one.",))

    try:
        model = build_geometry_model(project, catalog)
    except GeometryModelError as error:
        raise RunPlanningError(error.issues) from error
    if model.collisions:
        raise RunPlanningError(tuple(issue.message for issue in model.collisions))

    material = project.design.core_material
    geometry_only = (
        material is None
        and request.backend is RunBackend.MAXWELL_3D
        and request.mode is RunMode.GENERATE_ONLY
        and request.confirm_geometry_only
    )
    if material is None and not geometry_only:
        raise RunPlanningError(
            (
                "Core material is unresolved; only a confirmed Maxwell 3D "
                "Generate Only Geometry-Only run is allowed.",
            )
        )

    if material is not None:
        if (
            isinstance(core, CatalogCoreSelection)
            and material.ref != core.snapshot.material
        ):
            raise RunPlanningError(
                ("Material record identity does not match the selected core.",)
            )
        if (
            isinstance(core, ManualCoreSelection)
            and not project.design.manual_material_compatibility_acknowledged
        ):
            raise RunPlanningError(
                (
                    "Manual core and material selections require compatibility "
                    "acknowledgment.",
                )
            )
    dimension = (
        ModelDimension.THREE_D
        if request.backend is RunBackend.MAXWELL_3D
        else ModelDimension.TWO_D
    )
    dc_bias_decision = select_dc_bias_strategy(capabilities, dimension)
    dc_requested = any(
        item.dc_current_a != 0.0 for item in project.operating_point.windings
    )
    if dc_requested and dc_bias_decision.strategy is DcBiasStrategy.BLOCKED:
        raise RunPlanningError((dc_bias_decision.reason,))

    effective_inputs = effective_winding_inputs(project.operating_point)
    try:
        if geometry_only:
            return GeometryOnlyRunPlan(
                request=request,
                effective_inputs=effective_inputs,
                solver_plan=build_geometry_only_maxwell3d_plan(
                    model.core,
                    model.packings,
                    project.design.windings,
                    model.bare_diameter_m,
                ),
                warnings=(_GEOMETRY_ONLY_WARNING,),
            )

        assert material is not None
        if request.backend is RunBackend.MAXWELL_3D:
            solver_plan: Maxwell3dDesignPlan | Maxwell2dDesignPlan | FemmProblem = (
                build_maxwell3d_plan(
                    model.core,
                    model.packings,
                    project.design.windings,
                    effective_inputs,
                    model.bare_diameter_m,
                    frequency_hz=project.operating_point.frequency_hz,
                    recipe=project.simulation_recipe,
                    dc_bias_decision=dc_bias_decision,
                    material_record=material.snapshot,
                    material_bh_series_id=material.bh_series_id,
                )
            )
        else:
            maxwell2d_plan = build_maxwell2d_plan(
                model.planar,
                project.design.windings,
                effective_inputs,
                model.bare_diameter_m,
                frequency_hz=project.operating_point.frequency_hz,
                recipe=project.simulation_recipe,
                dc_bias_decision=dc_bias_decision,
                material_record=material.snapshot,
                material_bh_series_id=material.bh_series_id,
            )
            solver_plan = (
                femm_problem_from_plan(maxwell2d_plan)
                if request.backend is RunBackend.FEMM
                else maxwell2d_plan
            )
    except PlanBuildError as error:
        raise RunPlanningError(error.issues) from error

    warnings = (
        solver_plan.notes
        if isinstance(solver_plan, (Maxwell3dDesignPlan, Maxwell2dDesignPlan))
        else maxwell2d_plan.notes
    )
    return SolveReadyRunPlan(
        request=request,
        effective_inputs=effective_inputs,
        solver_plan=solver_plan,
        warnings=warnings,
    )
