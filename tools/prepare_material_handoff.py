"""Prepare a sanitized, reproducible Project for M5a solver validation."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from inductor_designer.adapters.catalog.sqlite_repository import SqliteCatalogRepository
from inductor_designer.adapters.materials import FileOverlayMaterialRepository
from inductor_designer.adapters.persistence.project_repository import ProjectRepository
from inductor_designer.adapters.persistence.schema_repository import SchemaRepository
from inductor_designer.application.ports.material_repository import MaterialLookupError
from inductor_designer.application.services.aedt_support import (
    SUPPORTED_AEDT_EDITION,
    SUPPORTED_AEDT_RELEASE,
)
from inductor_designer.application.services.material_handoff import (
    MaterialHandoffError,
    prepare_material_handoff,
)
from inductor_designer.materials.identity import MaterialRef


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-project", required=True, type=Path)
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--schemas", type=Path, default=Path("schemas"))
    parser.add_argument("--overlay-root", type=Path, default=Path("materials-overlay"))
    parser.add_argument("--manufacturer", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--grade", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--core-part-number", required=True)
    parser.add_argument("--bh-series-id", required=True)
    parser.add_argument("--output-project", required=True, type=Path)
    parser.add_argument("--evidence", required=True, type=Path)
    args = parser.parse_args(argv)

    args.output_project.unlink(missing_ok=True)
    args.evidence.unlink(missing_ok=True)
    try:
        ref = MaterialRef(args.manufacturer, args.name, args.grade)
        material_repository = FileOverlayMaterialRepository(args.overlay_root)
        record = material_repository.get(ref, args.revision)
        sources = material_repository.source_bytes(ref, args.revision)
        project_repository = ProjectRepository(SchemaRepository(args.schemas))
        project = project_repository.load(args.base_project)
        catalog = SqliteCatalogRepository(args.catalog)
        preparation = prepare_material_handoff(
            project,
            catalog,
            record,
            sources,
            core_part_number=args.core_part_number,
            bh_series_id=args.bh_series_id,
        )
        fit = preparation.record.steinmetz
        assert fit is not None

        args.output_project.parent.mkdir(parents=True, exist_ok=True)
        args.evidence.parent.mkdir(parents=True, exist_ok=True)
        project_repository.save(preparation.project, args.output_project)
        evidence = {
            "schemaVersion": 1,
            "supportedEnvironment": {
                "aedtRelease": str(SUPPORTED_AEDT_RELEASE),
                "edition": SUPPORTED_AEDT_EDITION.value,
            },
            "corePartNumber": args.core_part_number,
            "material": {
                "manufacturer": preparation.record.ref.manufacturer,
                "name": preparation.record.ref.name,
                "grade": preparation.record.ref.grade,
            },
            "materialRevision": preparation.record.revision_id,
            "bhSeriesId": preparation.bh_series_id,
            "bhPointCount": preparation.bh_point_count,
            "lossFrequenciesHz": list(preparation.loss_frequencies_hz),
            "steinmetz": {
                "k": fit.k,
                "alpha": fit.alpha,
                "beta": fit.beta,
                "rmsRelativeResidual": fit.rms_relative_residual,
                "maxRelativeResidual": fit.max_relative_residual,
            },
            "sources": [
                {"filename": filename, "sha256": sha256}
                for filename, sha256 in preparation.source_hashes
            ],
            "projectFile": args.output_project.name,
        }
        args.evidence.write_text(
            json.dumps(evidence, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except (MaterialLookupError, MaterialHandoffError, OSError, ValueError) as error:
        args.output_project.unlink(missing_ok=True)
        args.evidence.unlink(missing_ok=True)
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print("MATCH")
    print(f"Project: {args.output_project}")
    print(f"Evidence: {args.evidence}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
