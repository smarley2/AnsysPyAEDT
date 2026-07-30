"""Generate a ready-to-solve Maxwell 3D project from an inductor project file."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

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
    run_manifest_json,
)
from inductor_designer.application.services.project_run import (
    ProjectRunFailed,
    start_project_run,
)
from inductor_designer.application.services.run_directory import RunDirectoryError
from inductor_designer.application.services.run_planning import RunPlanningError
from inductor_designer.simulation.run_contracts import RunBackend, RunMode, RunRequest
from tools.build_catalog import build

ROOT = Path(__file__).resolve().parents[1]


def main(
    argv: Sequence[str] | None = None, *, exporter: Maxwell3dExporter | None = None
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument(
        "--work-directory",
        type=Path,
        required=True,
        help="Workspace for the built catalog index; the run itself is written "
        "beside --project in <project-directory>/runs/.",
    )
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--graphical", action="store_true")
    parser.add_argument("--matrix", type=Path, default=ROOT / "compatibility" / "aedt-matrix.yml")
    args = parser.parse_args(argv)

    args.work_directory.mkdir(parents=True, exist_ok=True)
    index = args.work_directory / "catalog.sqlite"
    build(ROOT / "catalog", ROOT / "schemas" / "catalog", index)
    catalog = SqliteCatalogRepository(index)
    repository = ProjectRepository(SchemaRepository(ROOT / "schemas"))
    project = repository.load(args.project)
    capabilities = MatrixCapabilityRepository(args.matrix).snapshot_for(
        SUPPORTED_AEDT_RELEASE,
        SUPPORTED_AEDT_EDITION,
    )

    try:
        result = start_project_run(
            project,
            args.project,
            RunRequest(RunBackend.MAXWELL_3D, RunMode.GENERATE_ONLY),
            catalog,
            capabilities,
            maxwell3d_exporter=(
                exporter if exporter is not None else PyaedtMaxwell3dExporter()
            ),
            maxwell2d_exporter=PyaedtMaxwell2dExporter(),
            femm_solver=PyfemmSolver(),
            application_version=__version__,
            show_solver_window=args.graphical,
        )
    except ProjectRunFailed as failed:
        args.evidence.parent.mkdir(parents=True, exist_ok=True)
        args.evidence.write_text(
            run_manifest_json(failed.manifest),
            encoding="utf-8",
        )
        print(f"Run folder: {failed.location.directory}", file=sys.stderr)
        for diagnostic in failed.manifest.diagnostics:
            print(f"FAILED: {diagnostic}", file=sys.stderr)
        return 1
    except (MaxwellExportBlocked, RunPlanningError) as blocked:
        for issue in blocked.issues:
            print(f"BLOCKED: {issue}", file=sys.stderr)
        return 1
    except RunDirectoryError as blocked:
        print(f"BLOCKED: {blocked}", file=sys.stderr)
        return 1

    args.evidence.parent.mkdir(parents=True, exist_ok=True)
    args.evidence.write_text(
        run_manifest_json(result.outcome.manifest),
        encoding="utf-8",
    )
    print(f"Run folder: {result.location.directory}")
    adapter_result = result.outcome.adapter_result
    if not isinstance(adapter_result, Maxwell3dExportResult):
        raise TypeError("Maxwell 3D generation returned a non-Maxwell result.")
    for stage in adapter_result.stages:
        status = "ok" if stage.succeeded else "FAILED"
        print(f"{stage.name}: {status} - {stage.message}")
    return 0 if adapter_result.succeeded(STAGE_NAMES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
