from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from inductor_designer.application.ports.catalog import CatalogRepository
from inductor_designer.application.ports.femm_solver import (
    FemmSolver,
    FemmSolveRequest,
    FemmSolveResult,
)
from inductor_designer.application.ports.maxwell2d_exporter import (
    STAGE_NAMES_2D,
    Maxwell2dExporter,
    Maxwell2dExportRequest,
)
from inductor_designer.application.ports.maxwell_exporter import (
    GEOMETRY_ONLY_STAGE_NAMES,
    STAGE_NAMES,
    Maxwell3dExporter,
    Maxwell3dExportRequest,
    Maxwell3dGeometryOnlyRequest,
    MaxwellExportResult,
)
from inductor_designer.application.services.aedt_support import (
    SUPPORTED_AEDT_EDITION,
    SUPPORTED_AEDT_RELEASE,
    aedt_support_issues,
)
from inductor_designer.application.services.run_planning import (
    GeometryOnlyRunPlan,
    PlannedRun,
    SolveReadyRunPlan,
    plan_run,
)
from inductor_designer.domain.project import InductorProject
from inductor_designer.geometry.naming import sanitize_identifier
from inductor_designer.simulation.capabilities import CapabilitySnapshot
from inductor_designer.simulation.femm_problem import FemmProblem
from inductor_designer.simulation.maxwell2d_plan import Maxwell2dDesignPlan
from inductor_designer.simulation.maxwell_plan import Maxwell3dDesignPlan
from inductor_designer.simulation.run_contracts import (
    ComplexValue,
    DimensionalRepresentation,
    ManifestArtifact,
    ManifestMaterialState,
    ManifestStage,
    MatrixValue,
    NormalizedQuantity,
    NormalizedResultSet,
    NormalizedValue,
    RunBackend,
    RunManifest,
    RunMode,
    RunRequest,
    RunStatus,
    StageStatus,
)

_PROJECT_SCHEMA_VERSION = 5
_GENERATE_AND_SOLVE_BLOCK = (
    "Generate and Solve execution belongs to M8; M6 only validates its Run Request."
)


class MaxwellExportBlocked(ValueError):
    def __init__(self, issues: tuple[str, ...]) -> None:
        self.issues = issues
        super().__init__("; ".join(issues))


AdapterResult = MaxwellExportResult | FemmSolveResult


@dataclass(frozen=True, slots=True)
class RunOutcome:
    planned_run: PlannedRun
    adapter_result: AdapterResult
    manifest: RunManifest


class RunGenerationFailed(RuntimeError):
    def __init__(
        self,
        planned_run: PlannedRun,
        manifest: RunManifest,
    ) -> None:
        self.planned_run = planned_run
        self.manifest = manifest
        super().__init__("; ".join(manifest.diagnostics))


class _AdapterDispatchError(Exception):
    def __init__(self, error: Exception) -> None:
        self.error = error
        super().__init__(str(error))


def _project_name(project: InductorProject) -> str:
    return sanitize_identifier(project.name)


def _export_maxwell3d_plan(
    project: InductorProject,
    planned_run: SolveReadyRunPlan | GeometryOnlyRunPlan,
    exporter: Maxwell3dExporter,
    output_directory: Path,
    *,
    non_graphical: bool,
) -> MaxwellExportResult:
    if isinstance(planned_run, GeometryOnlyRunPlan):
        geometry_request = Maxwell3dGeometryOnlyRequest(
            plan=planned_run.solver_plan,
            release=SUPPORTED_AEDT_RELEASE,
            edition=SUPPORTED_AEDT_EDITION,
            non_graphical=non_graphical,
            output_directory=output_directory,
            project_name=_project_name(project),
        )
        try:
            return exporter.export_geometry_only(geometry_request)
        except Exception as error:
            raise _AdapterDispatchError(error) from error
    plan = planned_run.solver_plan
    if not isinstance(plan, Maxwell3dDesignPlan):
        raise TypeError("Maxwell 3D run planning returned a non-Maxwell 3D plan.")
    export_request = Maxwell3dExportRequest(
        plan=plan,
        release=SUPPORTED_AEDT_RELEASE,
        edition=SUPPORTED_AEDT_EDITION,
        non_graphical=non_graphical,
        output_directory=output_directory,
        project_name=_project_name(project),
    )
    try:
        return exporter.export(export_request)
    except Exception as error:
        raise _AdapterDispatchError(error) from error


def _export_maxwell2d_plan(
    project: InductorProject,
    planned_run: SolveReadyRunPlan,
    exporter: Maxwell2dExporter,
    output_directory: Path,
    *,
    non_graphical: bool,
) -> MaxwellExportResult:
    plan = planned_run.solver_plan
    if not isinstance(plan, Maxwell2dDesignPlan):
        raise TypeError("Maxwell 2D run planning returned a non-Maxwell 2D plan.")
    request = Maxwell2dExportRequest(
        plan=plan,
        release=SUPPORTED_AEDT_RELEASE,
        edition=SUPPORTED_AEDT_EDITION,
        non_graphical=non_graphical,
        output_directory=output_directory,
        project_name=f"{_project_name(project)}_2d",
    )
    try:
        return exporter.export(request)
    except Exception as error:
        raise _AdapterDispatchError(error) from error


def _export_femm_plan(
    project: InductorProject,
    planned_run: SolveReadyRunPlan,
    solver: FemmSolver,
    output_directory: Path,
) -> FemmSolveResult:
    problem = planned_run.solver_plan
    if not isinstance(problem, FemmProblem):
        raise TypeError("FEMM run planning returned a non-FEMM problem.")
    request = FemmSolveRequest(
        problem=problem,
        output_directory=output_directory,
        project_name=f"{_project_name(project)}_2d",
        analyze=False,
    )
    try:
        return solver.solve(request)
    except Exception as error:
        raise _AdapterDispatchError(error) from error


def _material_state(project: InductorProject) -> ManifestMaterialState:
    selection = project.design.core_material
    return ManifestMaterialState(
        resolved=selection is not None,
        ref=None if selection is None else selection.ref,
        revision_id=None if selection is None else selection.revision_id,
        bh_series_id=None if selection is None else selection.bh_series_id,
        manual_compatibility_acknowledged=(
            project.design.manual_material_compatibility_acknowledged
        ),
    )


def _maxwell_evidence(
    result: MaxwellExportResult,
    expected_stage_names: tuple[str, ...],
) -> tuple[
    tuple[ManifestStage, ...],
    RunStatus,
    tuple[str, ...],
    tuple[ManifestArtifact, ...],
]:
    stages = tuple(
        ManifestStage(
            name=stage.name,
            status=(
                StageStatus.SUCCEEDED if stage.succeeded else StageStatus.FAILED
            ),
            diagnostic=stage.message,
        )
        for stage in result.stages
    )
    received_stage_names = tuple(stage.name for stage in result.stages)
    all_stages_succeeded = bool(result.stages) and all(
        stage.succeeded for stage in result.stages
    )
    sequence_diagnostic: str | None = None
    if all_stages_succeeded and received_stage_names != expected_stage_names:
        sequence_diagnostic = (
            "Maxwell adapter stage sequence mismatch: "
            f"expected {expected_stage_names!r}; received {received_stage_names!r}."
        )
        stages += (
            ManifestStage(
                name="stage-sequence",
                status=StageStatus.FAILED,
                diagnostic=sequence_diagnostic,
            ),
        )
    status = (
        RunStatus.SUCCEEDED
        if all_stages_succeeded and received_stage_names == expected_stage_names
        else RunStatus.FAILED
    )
    diagnostics = tuple(stage.message for stage in result.stages if not stage.succeeded)
    if sequence_diagnostic is not None:
        diagnostics += (sequence_diagnostic,)
    saved = any(stage.name == "save" and stage.succeeded for stage in result.stages)
    artifacts = (
        (
            ManifestArtifact(
                kind="aedt-project",
                path=result.project_path.as_posix(),
            ),
        )
        if saved
        else ()
    )
    return stages, status, diagnostics, artifacts


def _femm_evidence(
    result: FemmSolveResult,
) -> tuple[
    tuple[ManifestStage, ...],
    RunStatus,
    tuple[str, ...],
    tuple[ManifestArtifact, ...],
]:
    return (
        (
            ManifestStage(
                name="generate",
                status=StageStatus.SUCCEEDED,
                diagnostic="; ".join(result.messages),
            ),
        ),
        RunStatus.SUCCEEDED,
        (),
        (
            ManifestArtifact(
                kind="femm-project",
                path=result.fem_path.as_posix(),
            ),
        ),
    )


def _manifest_for_result(
    project: InductorProject,
    planned_run: PlannedRun,
    result: AdapterResult,
    *,
    run_id: str,
    application_version: str,
) -> RunManifest:
    backend = planned_run.request.backend
    if backend is RunBackend.FEMM:
        if not isinstance(result, FemmSolveResult):
            raise TypeError("FEMM run returned a non-FEMM adapter result.")
        stages, status, diagnostics, artifacts = _femm_evidence(result)
        solver_version = result.solver_version
        adapter_version = result.adapter_version
    else:
        if not isinstance(result, MaxwellExportResult):
            raise TypeError("Maxwell run returned a non-Maxwell adapter result.")
        expected_stage_names = (
            GEOMETRY_ONLY_STAGE_NAMES
            if isinstance(planned_run, GeometryOnlyRunPlan)
            else STAGE_NAMES
            if backend is RunBackend.MAXWELL_3D
            else STAGE_NAMES_2D
        )
        stages, status, diagnostics, artifacts = _maxwell_evidence(
            result,
            expected_stage_names,
        )
        solver_version = str(SUPPORTED_AEDT_RELEASE)
        adapter_version = result.pyaedt_version
    return _build_manifest(
        project,
        planned_run,
        run_id=run_id,
        application_version=application_version,
        solver_version=solver_version,
        adapter_version=adapter_version,
        stages=stages,
        status=status,
        diagnostics=diagnostics,
        artifacts=artifacts,
    )


def _build_manifest(
    project: InductorProject,
    planned_run: PlannedRun,
    *,
    run_id: str,
    application_version: str,
    solver_version: str | None,
    adapter_version: str | None,
    stages: tuple[ManifestStage, ...],
    status: RunStatus,
    diagnostics: tuple[str, ...],
    artifacts: tuple[ManifestArtifact, ...],
) -> RunManifest:
    backend = planned_run.request.backend
    return RunManifest(
        run_id=run_id,
        project_id=project.project_id,
        project_schema_version=_PROJECT_SCHEMA_VERSION,
        backend=backend,
        mode=planned_run.request.mode,
        dimensional_representation=(
            DimensionalRepresentation.THREE_DIMENSIONAL
            if backend is RunBackend.MAXWELL_3D
            else DimensionalRepresentation.EQUIVALENT_CROSS_SECTION
        ),
        frequency_hz=project.operating_point.frequency_hz,
        winding_temperature_c=project.operating_point.winding_temperature_c,
        core_temperature_c=project.operating_point.core_temperature_c,
        windings=planned_run.effective_inputs,
        material=_material_state(project),
        mesh_intent=project.simulation_recipe.mesh_intent,
        maximum_passes=project.simulation_recipe.maximum_passes,
        percent_error=project.simulation_recipe.percent_error,
        requested_outputs=project.simulation_recipe.requested_outputs,
        geometry_only=isinstance(planned_run, GeometryOnlyRunPlan),
        application_version=application_version,
        solver_version=solver_version,
        adapter_version=adapter_version,
        warnings=planned_run.warnings,
        stages=stages,
        status=status,
        diagnostics=diagnostics,
        artifacts=artifacts,
        results=None,
    )


def _failed_manifest(
    project: InductorProject,
    planned_run: PlannedRun,
    diagnostic: str,
    *,
    run_id: str,
    application_version: str,
    solver_version: str | None,
    adapter_version: str | None,
) -> RunManifest:
    return _build_manifest(
        project,
        planned_run,
        run_id=run_id,
        application_version=application_version,
        solver_version=solver_version,
        adapter_version=adapter_version,
        stages=(
            ManifestStage(
                name="generate",
                status=StageStatus.FAILED,
                diagnostic=diagnostic,
            ),
        ),
        status=RunStatus.FAILED,
        diagnostics=(diagnostic,),
        artifacts=(),
    )


def _generation_failure(
    project: InductorProject,
    planned_run: PlannedRun,
    error: Exception,
    *,
    run_id: str,
    application_version: str,
) -> RunGenerationFailed:
    diagnostic = f"{type(error).__name__}: {error}"
    return RunGenerationFailed(
        planned_run,
        _failed_manifest(
            project,
            planned_run,
            diagnostic,
            run_id=run_id,
            application_version=application_version,
            solver_version=None,
            adapter_version=None,
        ),
    )


def generate_run(
    project: InductorProject,
    request: RunRequest,
    catalog: CatalogRepository,
    capabilities: CapabilitySnapshot,
    output_directory: Path,
    *,
    maxwell3d_exporter: Maxwell3dExporter,
    maxwell2d_exporter: Maxwell2dExporter,
    femm_solver: FemmSolver,
    run_id: str,
    application_version: str,
    non_graphical: bool = True,
) -> RunOutcome:
    if request.mode is RunMode.GENERATE_AND_SOLVE:
        raise MaxwellExportBlocked((_GENERATE_AND_SOLVE_BLOCK,))
    if request.backend is not RunBackend.FEMM:
        support_issues = aedt_support_issues(
            SUPPORTED_AEDT_RELEASE,
            SUPPORTED_AEDT_EDITION,
            capabilities,
        )
        if support_issues:
            raise MaxwellExportBlocked(support_issues)

    planned_run = plan_run(project, request, catalog, capabilities)
    adapter_result: AdapterResult
    try:
        if request.backend is RunBackend.MAXWELL_3D:
            adapter_result = _export_maxwell3d_plan(
                project,
                planned_run,
                maxwell3d_exporter,
                output_directory,
                non_graphical=non_graphical,
            )
        elif request.backend is RunBackend.MAXWELL_2D:
            if not isinstance(planned_run, SolveReadyRunPlan):
                raise TypeError("Maxwell 2D unexpectedly produced a Geometry-Only plan.")
            adapter_result = _export_maxwell2d_plan(
                project,
                planned_run,
                maxwell2d_exporter,
                output_directory,
                non_graphical=non_graphical,
            )
        else:
            if not isinstance(planned_run, SolveReadyRunPlan):
                raise TypeError("FEMM unexpectedly produced a Geometry-Only plan.")
            adapter_result = _export_femm_plan(
                project,
                planned_run,
                femm_solver,
                output_directory,
            )
    except _AdapterDispatchError as dispatch_failure:
        raise _generation_failure(
            project,
            planned_run,
            dispatch_failure.error,
            run_id=run_id,
            application_version=application_version,
        ) from dispatch_failure.error

    if (
        request.backend is RunBackend.FEMM
        and isinstance(adapter_result, FemmSolveResult)
        and (adapter_result.analyzed or adapter_result.results is not None)
    ):
        diagnostic = (
            "FEMM Generate Only adapter returned nonconforming evidence: "
            f"analyzed={adapter_result.analyzed}, "
            f"results_present={adapter_result.results is not None}."
        )
        raise RunGenerationFailed(
            planned_run,
            _failed_manifest(
                project,
                planned_run,
                diagnostic,
                run_id=run_id,
                application_version=application_version,
                solver_version=adapter_result.solver_version,
                adapter_version=adapter_result.adapter_version,
            ),
        )

    try:
        manifest = _manifest_for_result(
            project,
            planned_run,
            adapter_result,
            run_id=run_id,
            application_version=application_version,
        )
    except Exception as error:
        raise _generation_failure(
            project,
            planned_run,
            error,
            run_id=run_id,
            application_version=application_version,
        ) from error
    if manifest.status is RunStatus.FAILED:
        raise RunGenerationFailed(planned_run, manifest)
    return RunOutcome(
        planned_run=planned_run,
        adapter_result=adapter_result,
        manifest=manifest,
    )


def _normalized_value_to_document(value: NormalizedValue) -> object:
    if isinstance(value, ComplexValue):
        return {"real": value.real, "imaginary": value.imaginary}
    if isinstance(value, MatrixValue):
        return {
            "rowLabels": list(value.row_labels),
            "columnLabels": list(value.column_labels),
            "values": [
                [_normalized_value_to_document(item) for item in row]
                for row in value.values
            ],
        }
    return value


def _quantity_to_document(quantity: NormalizedQuantity) -> dict[str, object]:
    return {
        "quantity": quantity.quantity.value,
        "scope": quantity.scope,
        "availability": quantity.availability.value,
        "value": (
            None
            if quantity.value is None
            else _normalized_value_to_document(quantity.value)
        ),
        "unit": quantity.unit,
        "currentConvention": quantity.current_convention.value,
        "approximation": quantity.approximation,
        "reason": quantity.reason,
        "provenance": quantity.provenance,
    }


def _results_to_document(results: NormalizedResultSet) -> dict[str, object]:
    return {
        "runId": results.run_id,
        "backend": results.backend.value,
        "quantities": [
            _quantity_to_document(quantity) for quantity in results.quantities
        ],
    }


def run_manifest_to_document(manifest: RunManifest) -> dict[str, object]:
    ref = manifest.material.ref
    return {
        "runId": manifest.run_id,
        "projectId": manifest.project_id,
        "projectSchemaVersion": manifest.project_schema_version,
        "backend": manifest.backend.value,
        "mode": manifest.mode.value,
        "dimensionalRepresentation": manifest.dimensional_representation.value,
        "frequencyHz": manifest.frequency_hz,
        "windingTemperatureC": manifest.winding_temperature_c,
        "coreTemperatureC": manifest.core_temperature_c,
        "windings": [
            {
                "windingId": winding.winding_id,
                "acRmsCurrentA": winding.ac_rms_current_a,
                "acPeakCurrentA": winding.ac_peak_current_a,
                "phaseDeg": winding.phase_deg,
                "dcCurrentA": winding.dc_current_a,
                "currentDirection": winding.current_direction.value,
            }
            for winding in manifest.windings
        ],
        "material": {
            "resolved": manifest.material.resolved,
            "ref": (
                None
                if ref is None
                else {
                    "manufacturer": ref.manufacturer,
                    "name": ref.name,
                    "grade": ref.grade,
                }
            ),
            "revisionId": manifest.material.revision_id,
            "bhSeriesId": manifest.material.bh_series_id,
            "manualCompatibilityAcknowledged": (
                manifest.material.manual_compatibility_acknowledged
            ),
        },
        "meshIntent": manifest.mesh_intent.value,
        "maximumPasses": manifest.maximum_passes,
        "percentError": manifest.percent_error,
        "requestedOutputs": [
            output.value for output in manifest.requested_outputs
        ],
        "geometryOnly": manifest.geometry_only,
        "applicationVersion": manifest.application_version,
        "solverVersion": manifest.solver_version,
        "adapterVersion": manifest.adapter_version,
        "warnings": list(manifest.warnings),
        "stages": [
            {
                "name": stage.name,
                "status": stage.status.value,
                "diagnostic": stage.diagnostic,
            }
            for stage in manifest.stages
        ],
        "status": manifest.status.value,
        "diagnostics": list(manifest.diagnostics),
        "artifacts": [
            {"kind": artifact.kind, "path": artifact.path}
            for artifact in manifest.artifacts
        ],
        "results": (
            None
            if manifest.results is None
            else _results_to_document(manifest.results)
        ),
    }


def run_manifest_json(manifest: RunManifest) -> str:
    return json.dumps(
        run_manifest_to_document(manifest),
        indent=2,
        sort_keys=True,
    ) + "\n"
