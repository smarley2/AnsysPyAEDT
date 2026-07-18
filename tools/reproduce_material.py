"""Reproduce a persisted material revision from its recorded sources."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from inductor_designer.adapters.materials import FileOverlayMaterialRepository
from inductor_designer.application.ports.material_repository import MaterialLookupError
from inductor_designer.materials.identity import MaterialRef
from inductor_designer.materials.replay import reproduce_record


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--overlay-root", type=Path, default=Path("materials-overlay"))
    parser.add_argument("--manufacturer", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--grade", required=True)
    parser.add_argument("--revision", required=True)
    args = parser.parse_args(argv)

    try:
        ref = MaterialRef(args.manufacturer, args.name, args.grade)
        repository = FileOverlayMaterialRepository(args.overlay_root)
        record = repository.get(ref, args.revision)
        sources = repository.source_bytes(ref, args.revision)
    except MaterialLookupError:
        print("ERROR: unknown material revision", file=sys.stderr)
        return 1
    except (OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    report = reproduce_record(record, sources)
    if report.matches:
        print("MATCH")
        return 0
    for mismatch in report.mismatches:
        print(mismatch)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
