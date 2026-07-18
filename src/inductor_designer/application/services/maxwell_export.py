from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from inductor_designer.application.ports.catalog import CatalogRepository
from inductor_designer.application.ports.femm_solver import (
    FemmSolver,
    FemmSolveRequest,
    FemmSolveResult,
)
from inductor_designer.application.ports.maxwell2d_exporter import (
    Maxwell2dExporter,
    Maxwell2dExportRequest,
)
from inductor_designer.application.ports.maxwell_exporter import (
    Maxwell3dExporter,
    Maxwell3dExportRequest,
    MaxwellExportResult,
)
from inductor_designer.application.services.geometry_model import (
    GeometryModel,
    build_geometry_model,
)
from inductor_designer.domain.aedt_target import ModelDimension
from inductor_designer.domain.project import CatalogCoreSelection, InductorProject
from inductor_designer.geometry.naming import sanitize_identifier
from inductor_designer.materials.records import MaterialRecord
from inductor_designer.simulation.capabilities import (
    CapabilitySnapshot,
    DcBiasDecision,
    DcBiasStrategy,
    select_dc_bias_strategy,
)
from inductor_designer.simulation.femm_problem import FemmProblem, femm_problem_from_plan
from inductor_designer.simulation.maxwell2d_plan import Maxwell2dDesignPlan
from inductor_designer.simulation.maxwell_plan import Maxwell3dDesignPlan, PlanBuildError
from inductor_designer.simulation.plan_builder import build_maxwell3d_plan
from inductor_designer.simulation.plan_builder2d import build_maxwell2d_plan


class Backend2d(str, Enum):
    AEDT = "aedt"
    FEMM = "femm"


class MaxwellExportBlocked(ValueError):
    def __init__(self, issues: tuple[str, ...]) -> None:
        super().__init__("; ".join(issues))
        self.issues = issues


@dataclass(frozen=True, slots=True)
class MaxwellExportOutcome:
    plan: Maxwell3dDesignPlan | Maxwell2dDesignPlan
    result: MaxwellExportResult
    capabilities: CapabilitySnapshot
    decision: DcBiasDecision
    dimension: ModelDimension


def _validated_model(
    project: InductorProject,
    catalog: CatalogRepository,
    expected: ModelDimension,
) -> tuple[CatalogCoreSelection, GeometryModel]:
    if project.dimension_mode is not expected:
        raise MaxwellExportBlocked(
            (f"Project dimension mode must be {expected.value} for this export.",)
        )
    core_selection = project.core
    if not isinstance(core_selection, CatalogCoreSelection):
        raise MaxwellExportBlocked(
            ("Only catalog cores are supported; manual cores carry no material identity.",)
        )
    model = build_geometry_model(project, catalog)
    if model.collisions:
        raise MaxwellExportBlocked(tuple(issue.message for issue in model.collisions))
    return core_selection, model


def _selected_material(
    project: InductorProject, core_selection: CatalogCoreSelection
) -> MaterialRecord | None:
    matches = tuple(
        selection.snapshot
        for selection in project.materials
        if selection.ref == core_selection.snapshot.material
    )
    if len(matches) > 1:
        raise MaxwellExportBlocked(
            (
                "Project contains multiple material revisions for the selected core; "
                "pin exactly one revision before export.",
            )
        )
    return matches[0] if matches else None


def export_maxwell3d(
    project: InductorProject,
    catalog: CatalogRepository,
    exporter: Maxwell3dExporter,
    output_directory: Path,
    *,
    capabilities: CapabilitySnapshot,
    non_graphical: bool = True,
) -> MaxwellExportOutcome:
    core_selection, model = _validated_model(project, catalog, ModelDimension.THREE_D)
    decision = select_dc_bias_strategy(capabilities, ModelDimension.THREE_D)
    try:
        plan = build_maxwell3d_plan(
            model.core,
            core_selection.snapshot,
            model.packings,
            project.windings,
            model.bare_diameter_m,
            dc_bias_decision=decision,
            material_record=_selected_material(project, core_selection),
        )
    except PlanBuildError as error:
        raise MaxwellExportBlocked(error.issues) from error
    request = Maxwell3dExportRequest(
        plan=plan,
        release=project.target_release,
        edition=project.target_edition,
        non_graphical=non_graphical,
        output_directory=output_directory,
        project_name=sanitize_identifier(project.name),
    )
    return MaxwellExportOutcome(
        plan=plan,
        result=exporter.export(request),
        capabilities=capabilities,
        decision=decision,
        dimension=ModelDimension.THREE_D,
    )


def export_maxwell2d(
    project: InductorProject,
    catalog: CatalogRepository,
    exporter: Maxwell2dExporter,
    output_directory: Path,
    *,
    capabilities: CapabilitySnapshot,
    non_graphical: bool = True,
) -> MaxwellExportOutcome:
    core_selection, model = _validated_model(project, catalog, ModelDimension.TWO_D)
    decision = select_dc_bias_strategy(capabilities, ModelDimension.TWO_D)
    try:
        plan = build_maxwell2d_plan(
            model.planar,
            core_selection.snapshot,
            project.windings,
            model.bare_diameter_m,
            dc_bias_decision=decision,
            material_record=_selected_material(project, core_selection),
        )
    except PlanBuildError as error:
        raise MaxwellExportBlocked(error.issues) from error
    request = Maxwell2dExportRequest(
        plan=plan,
        release=project.target_release,
        edition=project.target_edition,
        non_graphical=non_graphical,
        output_directory=output_directory,
        project_name=f"{sanitize_identifier(project.name)}_2d",
    )
    return MaxwellExportOutcome(
        plan=plan,
        result=exporter.export(request),
        capabilities=capabilities,
        decision=decision,
        dimension=ModelDimension.TWO_D,
    )


@dataclass(frozen=True, slots=True)
class FemmExportOutcome:
    plan: Maxwell2dDesignPlan
    problem: FemmProblem
    result: FemmSolveResult
    capabilities: CapabilitySnapshot
    decision: DcBiasDecision


def export_femm2d(
    project: InductorProject,
    catalog: CatalogRepository,
    solver: FemmSolver,
    output_directory: Path,
    *,
    capabilities: CapabilitySnapshot,
    analyze: bool = True,
) -> FemmExportOutcome:
    core_selection, model = _validated_model(project, catalog, ModelDimension.TWO_D)
    decision = select_dc_bias_strategy(capabilities, ModelDimension.TWO_D)
    try:
        plan = build_maxwell2d_plan(
            model.planar,
            core_selection.snapshot,
            project.windings,
            model.bare_diameter_m,
            dc_bias_decision=decision,
            material_record=_selected_material(project, core_selection),
        )
    except PlanBuildError as error:
        raise MaxwellExportBlocked(error.issues) from error
    problem = femm_problem_from_plan(plan)
    request = FemmSolveRequest(
        problem=problem,
        output_directory=output_directory,
        project_name=f"{sanitize_identifier(project.name)}_2d",
        analyze=analyze,
    )
    return FemmExportOutcome(
        plan=plan,
        problem=problem,
        result=solver.solve(request),
        capabilities=capabilities,
        decision=decision,
    )


def _winding_entries(plan: Maxwell3dDesignPlan | Maxwell2dDesignPlan) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for group in plan.windings:
        entry: dict[str, object] = {
            "name": group.name,
            "windingId": group.winding_id,
            "isSolid": group.is_solid,
            "currentPeakA": group.current_peak_a,
            "phaseDeg": group.phase_deg,
            "dcCurrentA": group.dc_current_a,
        }
        if isinstance(plan, Maxwell3dDesignPlan):
            entry["turnCount"] = len(group.turns)  # type: ignore[union-attr]
        else:
            entry["conductorCount"] = len(group.conductors)  # type: ignore[union-attr]
        entries.append(entry)
    return entries


def _dc_bias_block(
    plan: Maxwell3dDesignPlan | Maxwell2dDesignPlan, decision: DcBiasDecision
) -> dict[str, object]:
    dc_requested = any(group.dc_current_a != 0.0 for group in plan.windings)
    applied = (
        {group.name: group.dc_current_a for group in plan.windings if group.dc_current_a != 0.0}
        if dc_requested and decision.strategy is DcBiasStrategy.NATIVE_INCLUDE_DC_FIELDS
        else None
    )
    return {
        "strategy": decision.strategy.value,
        "approximate": decision.approximate,
        "reason": decision.reason,
        "appliedCurrentsA": applied,
    }


def _capabilities_block(capabilities: CapabilitySnapshot) -> dict[str, object]:
    return {
        "release": str(capabilities.release),
        "edition": capabilities.edition.value,
        "includeDcFields3d": capabilities.include_dc_fields_3d,
        "reviewStatus": capabilities.review_status.value,
        "evidenceSource": capabilities.evidence_source,
    }


def _core_material_block(plan: Maxwell3dDesignPlan | Maxwell2dDesignPlan) -> dict[str, object]:
    steinmetz = plan.core.material.steinmetz
    return {
        "name": plan.core.material.name,
        "relativePermeability": plan.core.material.relative_permeability,
        "conductivitySPerM": plan.core.material.conductivity_s_per_m,
        "draft": plan.core.material.draft,
        "bhPointCount": len(plan.core.material.bh_curve),
        "steinmetz": (
            None
            if steinmetz is None
            else {"k": steinmetz.k, "alpha": steinmetz.alpha, "beta": steinmetz.beta}
        ),
        "materialRevision": plan.core.material.material_revision,
    }


def generation_manifest_json(outcome: MaxwellExportOutcome) -> str:
    plan = outcome.plan
    result = outcome.result
    decision = outcome.decision
    capabilities = outcome.capabilities
    payload: dict[str, object] = {
        "schemaVersion": 2,
        "backend": Backend2d.AEDT.value,
        "dimension": outcome.dimension.value,
        "designName": result.design_name,
        "projectPath": str(result.project_path),
        "pyaedtVersion": result.pyaedt_version,
        "succeeded": result.succeeded(),
        "solutionType": plan.solution_type,
        "frequencyHz": plan.setup.frequency_hz,
        "dcBias": _dc_bias_block(plan, decision),
        "capabilities": _capabilities_block(capabilities),
        "coreMaterial": _core_material_block(plan),
        "windings": _winding_entries(plan),
        "notes": list(plan.notes),
        "stages": [
            {"name": stage.name, "succeeded": stage.succeeded, "message": stage.message}
            for stage in result.stages
        ],
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def femm_manifest_json(outcome: FemmExportOutcome) -> str:
    plan = outcome.plan
    result = outcome.result
    femm_results: dict[str, object] | None
    if result.results is None:
        femm_results = None
    else:
        femm_results = {
            name: {
                "resistanceOhm": winding.resistance_ohm,
                "inductanceH": winding.inductance_h,
                "currentA": list(winding.current_a),
                "voltageV": list(winding.voltage_v),
                "fluxLinkageWb": list(winding.flux_linkage_wb),
            }
            for name, winding in result.results.items()
        }
    payload: dict[str, object] = {
        "schemaVersion": 2,
        "backend": Backend2d.FEMM.value,
        "dimension": "2d",
        "designName": plan.design_name,
        "femPath": str(result.fem_path),
        "analyzed": result.analyzed,
        "dcBias": _dc_bias_block(plan, outcome.decision),
        "capabilities": _capabilities_block(outcome.capabilities),
        "coreMaterial": _core_material_block(plan),
        "windings": _winding_entries(plan),
        "notes": list(plan.notes),
        "femmResults": femm_results,
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"
