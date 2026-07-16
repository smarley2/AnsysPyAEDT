from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from inductor_designer.application.ports.catalog import CatalogRepository
from inductor_designer.application.ports.maxwell_exporter import (
    Maxwell3dExporter,
    Maxwell3dExportRequest,
    Maxwell3dExportResult,
)
from inductor_designer.application.services.geometry_model import build_geometry_model
from inductor_designer.domain.aedt_target import ModelDimension
from inductor_designer.domain.project import CatalogCoreSelection, InductorProject
from inductor_designer.geometry.naming import sanitize_identifier
from inductor_designer.simulation.maxwell_plan import Maxwell3dDesignPlan, PlanBuildError
from inductor_designer.simulation.plan_builder import build_maxwell3d_plan


class MaxwellExportBlocked(ValueError):
    def __init__(self, issues: tuple[str, ...]) -> None:
        super().__init__("; ".join(issues))
        self.issues = issues


@dataclass(frozen=True, slots=True)
class MaxwellExportOutcome:
    plan: Maxwell3dDesignPlan
    result: Maxwell3dExportResult


def export_maxwell3d(
    project: InductorProject,
    catalog: CatalogRepository,
    exporter: Maxwell3dExporter,
    output_directory: Path,
    *,
    non_graphical: bool = True,
) -> MaxwellExportOutcome:
    if project.dimension_mode is not ModelDimension.THREE_D:
        raise MaxwellExportBlocked(
            ("Project dimension mode must be 3d for Maxwell 3D export.",)
        )
    core_selection = project.core
    if not isinstance(core_selection, CatalogCoreSelection):
        raise MaxwellExportBlocked(
            ("Milestone 3 exports catalog cores only; manual cores carry no material identity.",)
        )
    model = build_geometry_model(project, catalog)
    if model.collisions:
        raise MaxwellExportBlocked(tuple(issue.message for issue in model.collisions))
    try:
        plan = build_maxwell3d_plan(
            model.core,
            core_selection.snapshot,
            model.packings,
            project.windings,
            model.bare_diameter_m,
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
    return MaxwellExportOutcome(plan=plan, result=exporter.export(request))


def generation_manifest_json(outcome: MaxwellExportOutcome) -> str:
    plan = outcome.plan
    result = outcome.result
    payload: dict[str, object] = {
        "schemaVersion": 1,
        "designName": result.design_name,
        "projectPath": str(result.project_path),
        "pyaedtVersion": result.pyaedt_version,
        "succeeded": result.succeeded(),
        "solutionType": plan.solution_type,
        "frequencyHz": plan.setup.frequency_hz,
        "coreMaterial": {
            "name": plan.core.material.name,
            "relativePermeability": plan.core.material.relative_permeability,
            "conductivitySPerM": plan.core.material.conductivity_s_per_m,
            "draft": plan.core.material.draft,
        },
        "windings": [
            {
                "name": group.name,
                "windingId": group.winding_id,
                "isSolid": group.is_solid,
                "currentPeakA": group.current_peak_a,
                "phaseDeg": group.phase_deg,
                "dcCurrentA": group.dc_current_a,
                "turnCount": len(group.turns),
            }
            for group in plan.windings
        ],
        "notes": list(plan.notes),
        "stages": [
            {"name": stage.name, "succeeded": stage.succeeded, "message": stage.message}
            for stage in result.stages
        ],
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"
