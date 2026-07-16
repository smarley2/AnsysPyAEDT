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
from inductor_designer.adapters.persistence.project_repository import ProjectRepository
from inductor_designer.adapters.persistence.schema_repository import SchemaRepository
from inductor_designer.adapters.pyaedt.maxwell2d import PyaedtMaxwell2dExporter
from inductor_designer.application.ports.maxwell2d_exporter import Maxwell2dExporter
from inductor_designer.application.services.maxwell_export import (
    MaxwellExportBlocked,
    export_maxwell2d,
    generation_manifest_json,
)
from inductor_designer.domain.aedt_target import ModelDimension
from tools.build_catalog import build

ROOT = Path(__file__).resolve().parents[1]


def main(
    argv: Sequence[str] | None = None, *, exporter: Maxwell2dExporter | None = None
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

    args.evidence.parent.mkdir(parents=True, exist_ok=True)
    args.evidence.write_text(generation_manifest_json(outcome), encoding="utf-8")
    for stage in outcome.result.stages:
        status = "ok" if stage.succeeded else "FAILED"
        print(f"{stage.name}: {status} - {stage.message}")
    return 0 if outcome.result.succeeded() else 1


if __name__ == "__main__":
    raise SystemExit(main())
