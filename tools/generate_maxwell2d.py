"""Generate a ready-to-solve approximate Maxwell 2D project from an inductor project file."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from inductor_designer.adapters.catalog.sqlite_repository import SqliteCatalogRepository
from inductor_designer.adapters.compatibility.matrix_repository import (
    MatrixCapabilityRepository,
)
from inductor_designer.adapters.femm.solver import PyfemmSolver
from inductor_designer.adapters.persistence.project_repository import ProjectRepository
from inductor_designer.adapters.persistence.schema_repository import SchemaRepository
from inductor_designer.adapters.pyaedt.maxwell2d import PyaedtMaxwell2dExporter
from inductor_designer.application.ports.femm_solver import FemmSolver
from inductor_designer.application.ports.maxwell2d_exporter import Maxwell2dExporter
from inductor_designer.application.services.maxwell_export import (
    MaxwellExportBlocked,
    export_femm2d,
    export_maxwell2d,
    femm_manifest_json,
    generation_manifest_json,
)
from inductor_designer.domain.aedt_target import ModelDimension
from tools.build_catalog import build

ROOT = Path(__file__).resolve().parents[1]


def main(
    argv: Sequence[str] | None = None,
    *,
    exporter: Maxwell2dExporter | None = None,
    femm_solver: FemmSolver | None = None,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument(
        "--matrix", type=Path, default=ROOT / "compatibility" / "aedt-matrix.yml"
    )
    parser.add_argument("--graphical", action="store_true")
    parser.add_argument(
        "--force-2d",
        action="store_true",
        help="Override the project's dimension mode to 2d for this export.",
    )
    parser.add_argument(
        "--backend",
        choices=["aedt", "femm"],
        default="aedt",
        help="Solver backend to generate for.",
    )
    parser.add_argument(
        "--no-analyze",
        action="store_true",
        help="FEMM backend only: write the .fem file without running the analysis.",
    )
    args = parser.parse_args(argv)

    args.output_directory.mkdir(parents=True, exist_ok=True)
    index = args.output_directory / "catalog.sqlite"
    build(ROOT / "catalog", ROOT / "schemas" / "catalog", index)
    catalog = SqliteCatalogRepository(index)
    repository = ProjectRepository(SchemaRepository(ROOT / "schemas"))
    project = repository.load(args.project)
    if args.force_2d:
        project = replace(project, dimension_mode=ModelDimension.TWO_D)
    capabilities = MatrixCapabilityRepository(args.matrix).snapshot_for(
        project.target_release, project.target_edition
    )

    args.evidence.parent.mkdir(parents=True, exist_ok=True)

    if args.backend == "femm":
        try:
            femm_outcome = export_femm2d(
                project,
                catalog,
                femm_solver if femm_solver is not None else PyfemmSolver(),
                args.output_directory,
                capabilities=capabilities,
                analyze=not args.no_analyze,
            )
        except MaxwellExportBlocked as blocked:
            for issue in blocked.issues:
                print(f"BLOCKED: {issue}", file=sys.stderr)
            return 1

        args.evidence.write_text(femm_manifest_json(femm_outcome), encoding="utf-8")
        femm_result = femm_outcome.result
        if femm_result.results:
            for name, winding in femm_result.results.items():
                print(f"{name}: R={winding.resistance_ohm}ohm L={winding.inductance_h}H")
        print(f"fem: {femm_result.fem_path}")
        analyzed_ok = femm_result.analyzed and bool(femm_result.results)
        unanalyzed_ok = not femm_result.analyzed and femm_result.fem_path is not None
        return 0 if analyzed_ok or unanalyzed_ok else 1

    try:
        outcome = export_maxwell2d(
            project,
            catalog,
            exporter if exporter is not None else PyaedtMaxwell2dExporter(),
            args.output_directory,
            capabilities=capabilities,
            non_graphical=not args.graphical,
        )
    except MaxwellExportBlocked as blocked:
        for issue in blocked.issues:
            print(f"BLOCKED: {issue}", file=sys.stderr)
        return 1

    args.evidence.write_text(generation_manifest_json(outcome), encoding="utf-8")
    for stage in outcome.result.stages:
        status = "ok" if stage.succeeded else "FAILED"
        print(f"{stage.name}: {status} - {stage.message}")
    return 0 if outcome.result.succeeded() else 1


if __name__ == "__main__":
    raise SystemExit(main())
