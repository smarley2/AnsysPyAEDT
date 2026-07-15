from __future__ import annotations

import json
import re
import sys
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.parse import urljoin

import requests
import yaml
from bs4 import BeautifulSoup
from bs4.element import Tag
from jsonschema import Draft202012Validator

from tools.scrape_kdm_powder_toroids_guard import ensure_complete_family_results

BASE_URL = "https://www.kdm-mag.com"
INDEX_URL = f"{BASE_URL}/products/alloy-powder-cores-346.html"
ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "catalog" / "cores" / "kdm-powder.yaml"
SUMMARY_PATH = ROOT / "artifacts" / "kdm-scrape-summary.json"
SCHEMA_PATH = ROOT / "schemas" / "catalog" / "core.v1.schema.json"
CATALOG_REVISION = f"kdm-web-{date.today().isoformat()}"


@dataclass(frozen=True)
class Family:
    code: str
    material_name: str

    def matches_part_number(self, part_number: str) -> bool:
        normalized = part_number.upper()
        prefix, separator, variant = self.code.upper().partition("-")
        if not normalized.startswith(prefix):
            return False
        return not separator or normalized.endswith(f"-{variant}")


FAMILIES = (
    Family("KS", "Sendust"),
    Family("KS-HF", "Super Sendust"),
    Family("KPH", "Sendust Plus"),
    Family("KSF", "Si-Fe"),
    Family("KNF", "Neu Flux"),
    Family("KH", "High Flux"),
    Family("KH-H", "High Flux Plus"),
    Family("KAM", "Nanodust"),
)


def clean_text(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def normalized_code_text(value: str) -> str:
    value = clean_text(value).upper()
    value = value.replace("（", "(").replace("）", ")")
    value = value.replace("®", "")
    return value


def number(value: str) -> float:
    cleaned = clean_text(value).replace(",", "")
    match = re.search(r"[-+]?\d+(?:\.\d+)?", cleaned)
    if match is None:
        raise ValueError(f"No numeric value in {value!r}")
    return float(match.group(0))


def grade(value: float) -> str:
    return str(int(value)) if value.is_integer() else f"{value:g}"


def scale_si(value: float, factor: float) -> float:
    return round(value * factor, 12)


def fetch(session: requests.Session, url: str) -> requests.Response:
    last_error: Exception | None = None
    for attempt in range(4):
        try:
            response = session.get(url, timeout=45)
            response.raise_for_status()
            if "Internal Error" in response.text and len(response.text) < 10_000:
                raise RuntimeError("site returned an internal-error page")
            return response
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(2**attempt)
    raise RuntimeError(f"Failed to fetch {url}: {last_error}") from last_error


def find_family_urls(session: requests.Session) -> dict[str, str]:
    response = fetch(session, INDEX_URL)
    soup = BeautifulSoup(response.text, "html.parser")
    result: dict[str, str] = {}
    for family in FAMILIES:
        pattern = re.compile(rf"\(\s*{re.escape(family.code)}\s*\)", re.IGNORECASE)
        matches: list[str] = []
        for anchor in soup.find_all("a", href=True):
            text = normalized_code_text(anchor.get_text(" ", strip=True))
            href = anchor.get("href")
            if pattern.search(text) and isinstance(href, str):
                matches.append(urljoin(response.url, href))
        unique = list(dict.fromkeys(matches))
        if not unique:
            raise RuntimeError(f"Could not find product page for {family.code}")
        result[family.code] = unique[0]
    return result


def find_datasheet_url(session: requests.Session, product_url: str) -> str:
    response = fetch(session, product_url)
    soup = BeautifulSoup(response.text, "html.parser")
    candidates: list[str] = []
    for anchor in soup.find_all("a", href=True):
        text = clean_text(anchor.get_text(" ", strip=True)).lower()
        href = anchor.get("href")
        if text.startswith("datasheet") and isinstance(href, str):
            candidates.append(urljoin(response.url, href))
    if not candidates:
        raise RuntimeError("No Datasheet(s) link found on product page")
    return list(dict.fromkeys(candidates))[0]


def candidate_row_cells(row: Tag) -> tuple[list[str], list[str]]:
    cells = row.find_all(["th", "td"], recursive=False)
    if not cells:
        cells = row.find_all(["th", "td"])
    texts = [clean_text(cell.get_text(" ", strip=True)) for cell in cells]
    links: list[str] = []
    for cell in cells:
        for anchor in cell.find_all("a", href=True):
            href = anchor.get("href")
            if isinstance(href, str):
                links.append(urljoin(BASE_URL, href))
    return texts, links


def parse_records(
    session: requests.Session,
    family: Family,
    product_url: str,
    datasheet_url: str,
) -> list[dict[str, object]]:
    response = fetch(session, datasheet_url)
    soup = BeautifulSoup(response.text, "html.parser")
    records: list[dict[str, object]] = []
    rejected: list[list[str]] = []

    for row in soup.find_all("tr"):
        cells, links = candidate_row_cells(row)
        if not cells:
            continue
        part_number = cells[0].strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*", part_number):
            continue
        if not family.matches_part_number(part_number):
            continue

        numeric_cells: list[float] = []
        for cell in cells[1:]:
            try:
                numeric_cells.append(number(cell))
            except ValueError:
                continue
        if len(numeric_cells) < 12:
            rejected.append(cells)
            continue

        (
            before_od_mm,
            before_id_mm,
            before_height_mm,
            after_od_max_mm,
            after_id_min_mm,
            after_height_max_mm,
            area_cm2,
            path_cm,
            volume_cm3,
            _window_area_cm2,
            permeability,
            al_value_nh,
        ) = numeric_cells[:12]

        pdf_links = [link for link in links if link.lower().endswith(".pdf")]
        source_url = pdf_links[0] if pdf_links else response.url
        records.append(
            {
                "partNumber": part_number,
                "manufacturer": "KDM",
                "family": "powder-toroid",
                "material": {
                    "manufacturer": "KDM",
                    "name": family.material_name,
                    "grade": grade(permeability),
                },
                "coating": "manufacturer standard coating (unspecified)",
                "catalogRevision": CATALOG_REVISION,
                "sourceUrl": source_url,
                "sourcePage": 1,
                "outerDiameter": {
                    "nominalM": scale_si(before_od_mm, 1e-3),
                    "minM": None,
                    "maxM": scale_si(after_od_max_mm, 1e-3),
                },
                "innerDiameter": {
                    "nominalM": scale_si(before_id_mm, 1e-3),
                    "minM": scale_si(after_id_min_mm, 1e-3),
                    "maxM": None,
                },
                "height": {
                    "nominalM": scale_si(before_height_mm, 1e-3),
                    "minM": None,
                    "maxM": scale_si(after_height_max_mm, 1e-3),
                },
                "effectiveAreaM2": scale_si(area_cm2, 1e-4),
                "pathLengthM": scale_si(path_cm, 1e-2),
                "volumeM3": scale_si(volume_cm3, 1e-6),
                "alValueNh": al_value_nh,
                "reviewStatus": "draft",
                "reviewedBy": None,
            }
        )

    if not records:
        raise RuntimeError(f"No valid data rows parsed; rejected samples={rejected[:3]!r}")

    unique: dict[str, dict[str, object]] = {}
    for record in records:
        part_number = str(record["partNumber"])
        previous = unique.get(part_number)
        if previous is None:
            unique[part_number] = record
            continue
        previous_data = {key: value for key, value in previous.items() if key != "sourceUrl"}
        record_data = {key: value for key, value in record.items() if key != "sourceUrl"}
        if previous_data != record_data:
            raise RuntimeError(f"Conflicting duplicate KDM part number: {part_number}")
    return list(unique.values())


def validate_records(records: list[dict[str, object]]) -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    failures: list[str] = []
    for record in records:
        errors = sorted(validator.iter_errors(record), key=lambda item: list(item.path))
        if errors:
            failures.append(
                f"{record['partNumber']}: " + "; ".join(error.message for error in errors)
            )
    if failures:
        raise RuntimeError("Schema validation failed:\n" + "\n".join(failures[:20]))


def main() -> int:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "Chrome/126 Safari/537.36 AnsysPyAEDT-catalog-import"
            )
        }
    )

    family_urls = find_family_urls(session)
    all_records: list[dict[str, object]] = []
    summaries: list[dict[str, object]] = []

    for family in FAMILIES:
        product_url = family_urls[family.code]
        entry: dict[str, object] = {
            "code": family.code,
            "materialName": family.material_name,
            "productUrl": product_url,
        }
        try:
            datasheet_url = find_datasheet_url(session, product_url)
            entry["datasheetUrl"] = datasheet_url
            records = parse_records(session, family, product_url, datasheet_url)
            entry["records"] = len(records)
            entry["error"] = None
            all_records.extend(records)
            print(f"{family.code}: {len(records)} records from {datasheet_url}")
        except Exception as exc:  # noqa: BLE001
            entry["records"] = 0
            entry["error"] = str(exc)
            print(f"{family.code}: ERROR: {exc}", file=sys.stderr)
        summaries.append(entry)

    ensure_complete_family_results(
        summaries, required_codes={family.code for family in FAMILIES}
    )

    duplicates: dict[str, int] = {}
    for record in all_records:
        part_number = str(record["partNumber"])
        duplicates[part_number] = duplicates.get(part_number, 0) + 1
    duplicates = {part: count for part, count in duplicates.items() if count > 1}
    if duplicates:
        raise RuntimeError(f"Duplicate KDM part numbers: {duplicates}")

    all_records.sort(key=lambda record: str(record["partNumber"]))
    validate_records(all_records)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        (
            "# KDM toroidal alloy powder cores extracted from the manufacturer's "
            "web datasheet tables.\n"
        )
        + "# New records remain draft pending human review.\n"
        + yaml.safe_dump(
            {"records": all_records},
            sort_keys=False,
            allow_unicode=True,
            width=120,
        ),
        encoding="utf-8",
    )

    inaccessible = [entry["code"] for entry in summaries if entry["error"]]
    summary = {
        "indexUrl": INDEX_URL,
        "catalogRevision": CATALOG_REVISION,
        "totalRecords": len(all_records),
        "accessibleFamilies": len(FAMILIES) - len(inaccessible),
        "inaccessibleFamilies": inaccessible,
        "families": summaries,
    }
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))

    if not all_records:
        raise RuntimeError("No KDM records were generated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
