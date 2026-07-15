from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import cast

import requests
import yaml

from tools.scrape_kdm_powder_toroids import Family, parse_records, validate_records

ROOT = Path(__file__).resolve().parents[1]
DATASHEET_URL = "https://www.kdm-mag.com/products/details-toroidal-1381.html"
OUTPUT_PATH = ROOT / "catalog" / "cores" / "kdm-mpp.yaml"
SUMMARY_PATH = ROOT / "artifacts" / "kdm-mpp-summary.json"
CATALOG_REVISION = f"kdm-web-{date.today().isoformat()}"


def run_import(
    *,
    output_path: Path = OUTPUT_PATH,
    summary_path: Path = SUMMARY_PATH,
    datasheet_url: str = DATASHEET_URL,
) -> list[dict[str, object]]:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "Chrome/126 Safari/537.36 AnsysPyAEDT-catalog-import"
            )
        }
    )
    records = parse_records(
        session,
        Family("KM", "MPP"),
        datasheet_url,
        datasheet_url,
    )
    if not records:
        raise RuntimeError("No KDM MPP records were generated")
    validate_records(records)
    records.sort(key=lambda record: str(record["partNumber"]))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "# KDM MPP toroidal powder cores extracted from the manufacturer datasheet table.\n"
        "# All records remain draft pending human review.\n"
        + yaml.safe_dump(
            {"records": records}, sort_keys=False, allow_unicode=True, width=120
        ),
        encoding="utf-8",
    )
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(
            {
                "datasheetUrl": datasheet_url,
                "catalogRevision": CATALOG_REVISION,
                "totalRecords": len(records),
                "grades": sorted(
                    {
                        str(cast(dict[str, object], record["material"])["grade"])
                        for record in records
                    }
                ),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    parser.add_argument("--summary", type=Path, default=SUMMARY_PATH)
    parser.add_argument("--datasheet-url", default=DATASHEET_URL)
    args = parser.parse_args(argv)
    run_import(
        output_path=args.output,
        summary_path=args.summary,
        datasheet_url=args.datasheet_url,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
