from __future__ import annotations

import argparse
import json
import re
import time
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any

import requests
import yaml

from tools.fair_rite_toroid_catalog import (
    build_catalog,
    render_unresolved,
    validate_records,
)
from tools.fair_rite_toroid_parser import (
    CATEGORY_URL,
    MissingMagneticParameter,
    RawProduct,
    UnresolvedProduct,
    discover_product_urls,
    parse_product_page,
)

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "catalog" / "cores" / "fair-rite-ferrite.yaml"
UNRESOLVED_PATH = ROOT / "docs" / "catalog" / "fair-rite-ferrite-unresolved.md"
SUMMARY_PATH = ROOT / "artifacts" / "fair-rite-ferrite-summary.json"
CATALOG_REVISION = f"fair-rite-web-{date.today().isoformat()}"
MIN_EXPECTED_PRODUCTS = 225


def fetch(session: requests.Session, url: str) -> str:
    last_error: Exception | None = None
    for attempt in range(4):
        try:
            response = session.get(url, timeout=45)
            response.raise_for_status()
            return response.text
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(2**attempt)
    raise RuntimeError(f"Failed to fetch {url}: {last_error}") from last_error


def run_import(
    *,
    category_url: str = CATEGORY_URL,
    output_path: Path = OUTPUT_PATH,
    unresolved_path: Path = UNRESOLVED_PATH,
    summary_path: Path = SUMMARY_PATH,
) -> tuple[list[dict[str, Any]], list[UnresolvedProduct]]:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "Chrome/126 Safari/537.36 AnsysPyAEDT-catalog-import"
            )
        }
    )
    category_html = fetch(session, category_url)
    urls = discover_product_urls(category_html, category_url)
    if len(urls) < MIN_EXPECTED_PRODUCTS:
        raise RuntimeError(
            f"Fair-Rite category returned only {len(urls)} toroids; "
            f"expected at least {MIN_EXPECTED_PRODUCTS}"
        )

    products: list[RawProduct] = []
    unresolved_fetches: list[UnresolvedProduct] = []
    for index, url in enumerate(urls, start=1):
        try:
            products.append(parse_product_page(fetch(session, url), url))
        except MissingMagneticParameter as exc:
            part_match = re.search(r"toroids-(\d{10})", url)
            part_number = part_match.group(1) if part_match else "unknown"
            unresolved_fetches.append(
                UnresolvedProduct(
                    part_number=part_number,
                    material_code=part_number[2:4] if len(part_number) == 10 else "unknown",
                    product_url=url,
                    coating="unknown",
                    reason=f"missing required magnetic parameter: {exc.field}",
                    missing_fields=(exc.field,),
                )
            )
        except Exception as exc:  # noqa: BLE001
            part_match = re.search(r"toroids-(\d{10})", url)
            part_number = part_match.group(1) if part_match else "unknown"
            unresolved_fetches.append(
                UnresolvedProduct(
                    part_number=part_number,
                    material_code=part_number[2:4] if len(part_number) == 10 else "unknown",
                    product_url=url,
                    coating="unknown",
                    reason=f"inaccessible or malformed product page: {exc}",
                )
            )
        print(f"[{index}/{len(urls)}] {url}")

    records, unresolved = build_catalog(products, CATALOG_REVISION)
    unresolved.extend(unresolved_fetches)
    unresolved.sort(key=lambda item: item.part_number)
    if not records:
        raise RuntimeError("No Fair-Rite records were generated")
    validate_records(records)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "# Fair-Rite ferrite toroids extracted from manufacturer product pages.\n"
        "# All records remain draft pending human review.\n"
        + yaml.safe_dump(
            {"records": records}, sort_keys=False, allow_unicode=True, width=120
        ),
        encoding="utf-8",
    )
    unresolved_path.parent.mkdir(parents=True, exist_ok=True)
    unresolved_path.write_text(render_unresolved(unresolved), encoding="utf-8")
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(
            {
                "categoryUrl": category_url,
                "catalogRevision": CATALOG_REVISION,
                "discoveredProducts": len(urls),
                "parsedProducts": len(products),
                "importedRecords": len(records),
                "unresolvedRecords": len(unresolved),
                "materials": sorted({record["material"]["grade"] for record in records}),
                "unresolved": [asdict(item) for item in unresolved],
            },
            indent=2,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )
    return records, unresolved


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--category-url", default=CATEGORY_URL)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    parser.add_argument("--unresolved", type=Path, default=UNRESOLVED_PATH)
    parser.add_argument("--summary", type=Path, default=SUMMARY_PATH)
    args = parser.parse_args(argv)
    run_import(
        category_url=args.category_url,
        output_path=args.output,
        unresolved_path=args.unresolved,
        summary_path=args.summary,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
