"""Generate a ready-to-solve Maxwell 3D project from an inductor project file."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from uuid import uuid4

from inductor_designer import __version__
from inductor_designer.adapters.catalog.sqlite_repository import SqliteCatalogRepository
from inductor_designer.adapters.compatibility.matrix_repository import (
    MatrixCapabilityRepository,
)
from inductor_designer.adapters.femm.solver import PyfemmSolver
from inductor_designer.adapters.persistence.project_repository import ProjectRepository
from inductor_designer.adapters.persistence.schema_repository import SchemaRepository
from inductor_designer.adapters.pyaedt.maxwell2d import PyaedtMaxwell2dExporter
from inductor_designer.adapters.pyaedt.maxwell3d import PyaedtMaxwell3dExporter
from inductor_designer.application.ports.maxwell_exporter import (
    STAGE_NAMES,
    Maxwell3dExporter,
    Maxwell3dExportResult,
)
from inductor_designer.application.services.aedt_support import (
    SUPPORTED_AEDT_EDITION,
    SUPPORTED_AEDT_RELEASE,
)
from inductor_designer.application.services.maxwell_export import (
    MaxwellExportBlocked,
    RunGenerationFailed,
    generate_run,
    run_manifest_json,
)
from inductor_designer.application.services.run_planning import RunPlanningError
from inductor_designer.simulation.run_contracts import RunBackend, RunMode, RunRequest
from tools.build_catalog import build

ROOT = Path(__file__).resolve().parents[1]


def main(
    argv: Sequence[str] | None = None, *, exporter: Maxwell3dExporter | None = None
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--graphical", action="store_true")
    parser.add_argument("--matrix", type=Path, default=ROOT / "compatibility" / "aedt-matrix.yml")
    args = parser.parse_args(argv)

    args.output_directory.mkdir(parents=True, exist_ok=True)
    index = args.output_directory / "catalog.sqlite"
    build(ROOT / "catalog", ROOT / "schemas" / "catalog", index)
    catalog = SqliteCatalogRepository(index)
    repository = ProjectRepository(SchemaRepository(ROOT / "schemas"))
    project = repository.load(args.project)
    capabilities = MatrixCapabilityRepository(args.matrix).snapshot_for(
        SUPPORTED_AEDT_RELEASE,
        SUPPORTED_AEDT_EDITION,
    )

    try:
        outcome = generate_run(
            project,
            RunRequest(RunBackend.MAXWELL_3D, RunMode.GENERATE_ONLY),
            catalog,
            capabilities,
            args.output_directory,
            maxwell3d_exporter=(
                exporter if exporter is not None else PyaedtMaxwell3dExporter()
            ),
            maxwell2d_exporter=PyaedtMaxwell2dExporter(),
            femm_solver=PyfemmSolver(),
            run_id=str(uuid4()),
            application_version=__version__,
            non_graphical=not args.graphical,
        )
    except RunGenerationFailed as failed:
        args.evidence.parent.mkdir(parents=True, exist_ok=True)
        args.evidence.write_text(
            run_manifest_json(failed.manifest),
            encoding="utf-8",
        )
        for diagnostic in failed.manifest.diagnostics:
            print(f"FAILED: {diagnostic}", file=sys.stderr)
        return 1
    except (MaxwellExportBlocked, RunPlanningError) as blocked:
        for issue in blocked.issues:
            print(f"BLOCKED: {issue}", file=sys.stderr)
        return 1

    args.evidence.parent.mkdir(parents=True, exist_ok=True)
    args.evidence.write_text(
        run_manifest_json(outcome.manifest),
        encoding="utf-8",
    )
    result = outcome.adapter_result
    if not isinstance(result, Maxwell3dExportResult):
        raise TypeError("Maxwell 3D generation returned a non-Maxwell result.")
    for stage in result.stages:
        status = "ok" if stage.succeeded else "FAILED"
        print(f"{stage.name}: {status} - {stage.message}")
    return 0 if result.succeeded(STAGE_NAMES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
