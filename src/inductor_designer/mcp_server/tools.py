"""Pure MCP tool functions: every function takes ``context`` first and

returns a JSON-able ``dict[str, object]``. Failures never raise — they come
back as ``{"error": ..., "issues": [...]}`` so an MCP client gets a
structured result either way.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from inductor_designer import __version__
from inductor_designer.adapters.compatibility.matrix_repository import (
    MatrixCapabilityRepository,
)
from inductor_designer.adapters.persistence.project_repository import (
    ProjectRepository,
    project_from_document,
)
from inductor_designer.adapters.persistence.record_serde import core_record_to_json
from inductor_designer.adapters.persistence.schema_repository import SchemaRepository
from inductor_designer.application.ports.catalog import CatalogRepository
from inductor_designer.application.ports.femm_solver import FemmSolver
from inductor_designer.application.ports.maxwell2d_exporter import Maxwell2dExporter
from inductor_designer.application.ports.maxwell_exporter import Maxwell3dExporter
from inductor_designer.application.services.aedt_support import (
    SUPPORTED_AEDT_EDITION,
    SUPPORTED_AEDT_RELEASE,
)
from inductor_designer.application.services.geometry_model import build_geometry_model
from inductor_designer.application.services.maxwell_export import run_manifest_json
from inductor_designer.application.services.project_run import (
    ProjectRunFailed,
    start_project_run,
)
from inductor_designer.application.services.run_directory import (
    MANIFEST_FILENAME,
    RUNS_DIRECTORY_NAME,
)
from inductor_designer.domain.validation import validate_project as domain_validate_project
from inductor_designer.geometry.manifest import build_manifest
from inductor_designer.simulation.run_contracts import RunBackend, RunMode, RunRequest

# Every tool below catches plain Exception rather than raising: besides the
# expected OSError/ValueError/KeyError/ValidationError from loading and
# validating documents, the FEMM adapter raises RuntimeError by design, the
# sqlite3-backed catalog can raise sqlite3.Error, and degenerate inputs can
# raise ZeroDivisionError. Narrower tuples left a client-facing crash on any
# of those; catching Exception keeps the "failures never raise" contract.


@dataclass(frozen=True, slots=True)
class ToolContext:
    catalog: CatalogRepository
    schemas: SchemaRepository
    matrix_path: Path
    maxwell3d_exporter: Maxwell3dExporter
    maxwell2d_exporter: Maxwell2dExporter
    femm_solver: FemmSolver


def _failure(error: Exception) -> dict[str, object]:
    issues = getattr(error, "issues", None)
    return {"error": str(error), "issues": list(issues) if issues else [str(error)]}


def _failed_run_result(error: ProjectRunFailed) -> dict[str, object]:
    """The caller already holds the manifest; report it verbatim."""
    result: dict[str, object] = dict(json.loads(run_manifest_json(error.manifest)))
    result["runDirectory"] = str(error.location.directory)
    result["error"] = str(error)
    result["issues"] = list(error.manifest.diagnostics)
    return result


def list_cores(context: ToolContext) -> dict[str, object]:
    try:
        cores = context.catalog.list_cores()
    except Exception as error:
        return _failure(error)
    return {
        "cores": [
            {
                "partNumber": core.part_number,
                "manufacturer": core.manufacturer,
                "material": core.material.name,
                "grade": core.material.grade,
                "reviewStatus": core.review_status.value,
            }
            for core in cores
        ]
    }


def get_core(context: ToolContext, part_number: str) -> dict[str, object]:
    try:
        record = context.catalog.get_core(part_number)
    except Exception as error:
        return _failure(error)
    if record is None:
        return _failure(ValueError(f"Unknown core part number: {part_number!r}"))
    return core_record_to_json(record)


def list_conductors(context: ToolContext) -> dict[str, object]:
    try:
        names = list(context.catalog.list_conductor_names())
    except Exception as error:
        return _failure(error)
    return {"conductors": names}


def save_project(
    context: ToolContext, document: Mapping[str, object], path: str
) -> dict[str, object]:
    try:
        context.schemas.validate_project(document)
        project = project_from_document(document)
        target = Path(path)
        ProjectRepository(context.schemas).save(project, target)
    except Exception as error:
        return _failure(error)
    return {"path": str(target), "projectId": project.project_id}


def validate_project(context: ToolContext, path: str) -> dict[str, object]:
    try:
        project = ProjectRepository(context.schemas).load(Path(path))
        issues = domain_validate_project(
            project, known_conductors=context.catalog.list_conductor_names()
        )
    except Exception as error:
        return _failure(error)
    return {
        "issues": [
            {
                "code": issue.code,
                "category": issue.category.value,
                "message": issue.message,
                "path": issue.path,
            }
            for issue in issues
        ]
    }


def geometry_summary(context: ToolContext, path: str) -> dict[str, object]:
    try:
        project = ProjectRepository(context.schemas).load(Path(path))
        model = build_geometry_model(project, context.catalog)
    except Exception as error:
        return _failure(error)
    return build_manifest(model)


def generate_maxwell3d(context: ToolContext, path: str) -> dict[str, object]:
    try:
        document_path = Path(path)
        project = ProjectRepository(context.schemas).load(document_path)
        capabilities = MatrixCapabilityRepository(context.matrix_path).snapshot_for(
            SUPPORTED_AEDT_RELEASE,
            SUPPORTED_AEDT_EDITION,
        )
        result = start_project_run(
            project,
            document_path,
            RunRequest(RunBackend.MAXWELL_3D, RunMode.GENERATE_ONLY),
            context.catalog,
            capabilities,
            maxwell3d_exporter=context.maxwell3d_exporter,
            maxwell2d_exporter=context.maxwell2d_exporter,
            femm_solver=context.femm_solver,
            application_version=__version__,
        )
        document: dict[str, object] = dict(
            json.loads(run_manifest_json(result.outcome.manifest))
        )
    except ProjectRunFailed as error:
        return _failed_run_result(error)
    except Exception as error:
        return _failure(error)
    document["runDirectory"] = str(result.location.directory)
    return document


def generate_2d(
    context: ToolContext, path: str, backend: str = "aedt", analyze: bool = True
) -> dict[str, object]:
    run_backend = {
        "aedt": RunBackend.MAXWELL_2D,
        "femm": RunBackend.FEMM,
    }.get(backend)
    if run_backend is None:
        return _failure(ValueError(f"Unknown 2D backend: {backend!r}"))
    try:
        document_path = Path(path)
        project = ProjectRepository(context.schemas).load(document_path)
        capabilities = MatrixCapabilityRepository(context.matrix_path).snapshot_for(
            SUPPORTED_AEDT_RELEASE,
            SUPPORTED_AEDT_EDITION,
        )
        result = start_project_run(
            project,
            document_path,
            RunRequest(
                run_backend,
                (
                    RunMode.GENERATE_AND_SOLVE
                    if run_backend is RunBackend.FEMM and analyze
                    else RunMode.GENERATE_ONLY
                ),
            ),
            context.catalog,
            capabilities,
            maxwell3d_exporter=context.maxwell3d_exporter,
            maxwell2d_exporter=context.maxwell2d_exporter,
            femm_solver=context.femm_solver,
            application_version=__version__,
        )
        document: dict[str, object] = dict(
            json.loads(run_manifest_json(result.outcome.manifest))
        )
    except ProjectRunFailed as error:
        return _failed_run_result(error)
    except Exception as error:
        return _failure(error)
    document["runDirectory"] = str(result.location.directory)
    return document


def read_manifest(context: ToolContext, path: str) -> dict[str, object]:
    """Read one run manifest. Only a manifest inside a run directory qualifies."""
    resolved = Path(path).resolve()
    if (
        resolved.name != MANIFEST_FILENAME
        or resolved.parent.parent.name != RUNS_DIRECTORY_NAME
    ):
        return _failure(
            ValueError(f"Not a run manifest inside a run directory: {path!r}")
        )
    try:
        document = json.loads(resolved.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            raise ValueError(f"Run manifest is not a JSON object: {path!r}")
    except Exception as error:
        return _failure(error)
    return dict(document)
