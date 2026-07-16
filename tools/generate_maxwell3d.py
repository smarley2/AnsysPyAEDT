"""Generate a ready-to-solve Maxwell 3D project from an inductor project file."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from inductor_designer.adapters.catalog.sqlite_repository import SqliteCatalogRepository
from inductor_designer.adapters.persistence.project_repository import ProjectRepository
from inductor_designer.adapters.persistence.schema_repository import SchemaRepository
from inductor_designer.adapters.pyaedt.maxwell3d import PyaedtMaxwell3dExporter
from inductor_designer.application.ports.maxwell_exporter import Maxwell3dExporter
from inductor_designer.application.services.maxwell_export import (
    MaxwellExportBlocked,
    export_maxwell3d,
    generation_manifest_json,
)
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
    args = parser.parse_args(argv)

    args.output_directory.mkdir(parents=True, exist_ok=True)
    index = args.output_directory / "catalog.sqlite"
    build(ROOT / "catalog", ROOT / "schemas" / "catalog", index)
    catalog = SqliteCatalogRepository(index)
    repository = ProjectRepository(SchemaRepository(ROOT / "schemas"))
    project = repository.load(args.project)

    try:
        outcome = export_maxwell3d(
            project,
            catalog,
            exporter if exporter is not None else PyaedtMaxwell3dExporter(),
            args.output_directory,
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
