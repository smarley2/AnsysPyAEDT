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
from inductor_designer.application.services.geometry_model import build_geometry_model
from inductor_designer.application.services.maxwell_export import (
    Backend2d,
    export_femm2d,
    export_maxwell2d,
    export_maxwell3d,
    femm_manifest_json,
    generation_manifest_json,
)
from inductor_designer.domain.validation import validate_project as domain_validate_project
from inductor_designer.geometry.manifest import build_manifest
from inductor_designer.geometry.naming import sanitize_identifier

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
    output_root: Path
    maxwell3d_exporter: Maxwell3dExporter
    maxwell2d_exporter: Maxwell2dExporter
    femm_solver: FemmSolver


def _failure(error: Exception) -> dict[str, object]:
    issues = getattr(error, "issues", None)
    return {"error": str(error), "issues": list(issues) if issues else [str(error)]}


def _output_dir(context: ToolContext, project_name: str) -> Path:
    directory = context.output_root / sanitize_identifier(project_name)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


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
        migrated = context.schemas.migrate_project(document)
        project = project_from_document(migrated)
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
        project = ProjectRepository(context.schemas).load(Path(path))
        capabilities = MatrixCapabilityRepository(context.matrix_path).snapshot_for(
            project.target_release, project.target_edition
        )
        output_dir = _output_dir(context, project.name)
        outcome = export_maxwell3d(
            project,
            context.catalog,
            context.maxwell3d_exporter,
            output_dir,
            capabilities=capabilities,
        )
        manifest_text = generation_manifest_json(outcome)
        (output_dir / "generation-manifest.json").write_text(manifest_text, encoding="utf-8")
    except Exception as error:
        return _failure(error)
    return dict(json.loads(manifest_text))


def generate_2d(
    context: ToolContext, path: str, backend: str = "aedt", analyze: bool = True
) -> dict[str, object]:
    try:
        backend_2d = Backend2d(backend)
    except Exception as error:
        return _failure(error)
    try:
        project = ProjectRepository(context.schemas).load(Path(path))
        capabilities = MatrixCapabilityRepository(context.matrix_path).snapshot_for(
            project.target_release, project.target_edition
        )
        output_dir = _output_dir(context, project.name)
        if backend_2d is Backend2d.FEMM:
            femm_outcome = export_femm2d(
                project,
                context.catalog,
                context.femm_solver,
                output_dir,
                capabilities=capabilities,
                analyze=analyze,
            )
            manifest_text = femm_manifest_json(femm_outcome)
            evidence_name = "femm-manifest.json"
        else:
            outcome = export_maxwell2d(
                project,
                context.catalog,
                context.maxwell2d_exporter,
                output_dir,
                capabilities=capabilities,
            )
            manifest_text = generation_manifest_json(outcome)
            evidence_name = "generation-manifest.json"
        (output_dir / evidence_name).write_text(manifest_text, encoding="utf-8")
    except Exception as error:
        return _failure(error)
    return dict(json.loads(manifest_text))


def read_manifest(context: ToolContext, path: str) -> dict[str, object]:
    resolved = (context.output_root / path).resolve()
    if not resolved.is_relative_to(context.output_root.resolve()):
        return _failure(ValueError(f"Path escapes output root: {path!r}"))
    try:
        loaded = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception as error:
        return _failure(error)
    if not isinstance(loaded, dict):
        return _failure(ValueError(f"Manifest is not a JSON object: {resolved}"))
    return dict(loaded)
