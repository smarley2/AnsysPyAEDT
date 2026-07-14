# ruff: noqa
"""One-time generator for the 2025 Magnetics powder-toroid catalog import."""

from __future__ import annotations

import argparse
import re
from collections import Counter
from pathlib import Path
from typing import Any

import pdfplumber

START_PAGE_INDEX = 155  # PDF page 156, printed catalog page 154
END_PAGE_INDEX = 198  # exclusive; printed catalog page 196
SOURCE_URL = (
    "https://www.mag-inc.com/Media/Magnetics/File-Library/"
    "Product%20Literature/Powder%20Core%20Literature/"
    "Magnetics-Powder-Core-Catalog.pdf"
)
MATERIALS = [
    ("Kool Mu", "77", "A7", "black epoxy"),
    ("Kool Mu MAX", "79", "A7", "black epoxy"),
    ("Kool Mu Hf", "76", "A7", "black epoxy"),
    ("Kool Mu Ultra", "70", "A7", "black epoxy"),
    ("XFlux", "78", "A7", "brown epoxy"),
    ("XFlux Ultra", "74", "A7", "brown epoxy"),
    ("Edge", "59", "A2", "green epoxy"),
    ("High Flux", "58", "A2", "khaki epoxy"),
    ("MPP", "55", "A2", "gray epoxy"),
]
PART_RE = re.compile(r"^(?:C?\d{6,7}A[279Y])$")
NUMBER_RE = re.compile(r"[\d,]+(?:\.\d+)?")
REVIEWED_PARTS = {
    "0077021A7",
    "0077041A7",
    "0077071A7",
    "0077083A7",
    "0077090A7",
    "0077109A7",
    "0077256A7",
    "0077550A7",
    "C058071A2",
    "C058083A2",
}
CURRENT_REVIEWED_COATING = {
    "C058071A2": "black epoxy",
    "C058083A2": "black epoxy",
}
EXPECTED_INDEX_ONLY = ["0055340A2", "0055341A2"]
EXPECTED_DATA_ONLY = ["0058443A2", "0058876A2", "0059534A2", "0078937A7"]


def groups_by_top(words: list[dict[str, Any]], tolerance: float = 1.5):
    groups: list[list[Any]] = []
    for word in sorted(words, key=lambda item: (float(item["top"]), float(item["x0"]))):
        if not groups or abs(float(word["top"]) - float(groups[-1][0])) > tolerance:
            groups.append([float(word["top"]), [word]])
        else:
            groups[-1][1].append(word)
    return groups


def line_text(words: list[dict[str, Any]]) -> str:
    return " ".join(
        str(word["text"]) for word in sorted(words, key=lambda item: float(item["x0"]))
    )


def number_in_region(
    words: list[dict[str, Any]], x0: float, x1: float
) -> float | None:
    values: list[tuple[float, float]] = []
    for word in words:
        center = (float(word["x0"]) + float(word["x1"])) / 2
        text = str(word["text"]).replace(",", "")
        if x0 <= center < x1 and re.fullmatch(r"\d+(?:\.\d+)?", text):
            values.append((float(word["x0"]), float(text)))
    return min(values)[1] if values else None


def normalize_part_token(token: str) -> str:
    cleaned = token.lstrip("*")
    if cleaned.startswith("CO"):
        cleaned = "C0" + cleaned[2:]
    return cleaned


def canonical_part_number(part: str, material_index: int, row_suffix: str) -> str:
    _, material_code, finish_code, _ = MATERIALS[material_index]
    prefix = "C0" if part.startswith("C") else "00"
    return f"{prefix}{material_code}{row_suffix}{finish_code}"


def rounded(value: float) -> float:
    return round(value, 12)


def parse_page(page: Any, printed_page: int) -> list[dict[str, Any]]:
    words = page.extract_words(x_tolerance=1, y_tolerance=2, keep_blank_chars=False)
    groups = groups_by_top(words)

    before = None
    after = None
    for _, group_words in groups:
        text = line_text(group_words)
        if "Before Finish" in text:
            before = (
                number_in_region(group_words, 160, 245),
                number_in_region(group_words, 245, 335),
                number_in_region(group_words, 335, 430),
            )
        elif "After Finish" in text:
            after = (
                number_in_region(group_words, 160, 245),
                number_in_region(group_words, 245, 335),
                number_in_region(group_words, 335, 430),
            )

    params: dict[str, float | None] = {"ae": None, "le": None, "ve": None}
    labels = {
        ("Cross", "Section"): "ae",
        ("Path", "Length"): "le",
        ("Effective", "Volume"): "ve",
    }
    for _, group_words in groups:
        tokens = [str(word["text"]) for word in group_words]
        key = next(
            (name for label, name in labels.items() if all(part in tokens for part in label)),
            None,
        )
        if key is None:
            continue
        values: list[tuple[float, float]] = []
        for word in group_words:
            center = (float(word["x0"]) + float(word["x1"])) / 2
            text = str(word["text"])
            if 145 < center < 300 and NUMBER_RE.fullmatch(text):
                values.append((float(word["x0"]), float(text.replace(",", ""))))
        if values:
            params[key] = min(values)[1]

    if before is None or after is None or any(value is None for value in before + after):
        raise ValueError(f"Catalog page {printed_page}: could not parse dimensions")
    if any(value is None for value in params.values()):
        raise ValueError(
            f"Catalog page {printed_page}: could not parse physical parameters: {params}"
        )

    left_layout = any(
        str(word["text"]) == "Perm" and float(word["x0"]) < 60 for word in words
    )
    offset = -36 if left_layout else 0
    bounds = [
        (155 + offset, 207 + offset),
        (207 + offset, 253 + offset),
        (253 + offset, 299 + offset),
        (299 + offset, 345 + offset),
        (345 + offset, 391 + offset),
        (391 + offset, 437 + offset),
        (437 + offset, 483 + offset),
        (483 + offset, 529 + offset),
        (529 + offset, 580 + offset),
    ]

    rows: list[tuple[str, float, list[str | None]]] = []
    for top, group_words in groups:
        if not 150 < float(top) < 360:
            continue
        perm_words = [
            word
            for word in group_words
            if 65 + offset
            <= (float(word["x0"]) + float(word["x1"])) / 2
            < 110 + offset
            and re.fullmatch(r"\d+(?:\.\d+)?", str(word["text"]).replace(",", ""))
        ]
        al_words = [
            word
            for word in group_words
            if 110 + offset
            <= (float(word["x0"]) + float(word["x1"])) / 2
            < 155 + offset
            and NUMBER_RE.fullmatch(str(word["text"]))
        ]
        if not perm_words or not al_words:
            continue

        cells: list[str | None] = []
        for x0, x1 in bounds:
            candidates = [
                normalize_part_token(str(word["text"]))
                for word in group_words
                if x0 <= (float(word["x0"]) + float(word["x1"])) / 2 < x1
            ]
            cells.append(
                next(
                    (candidate for candidate in candidates if PART_RE.fullmatch(candidate)),
                    None,
                )
            )
        parts = [part for part in cells if part is not None]
        if not parts:
            continue

        row_suffix = Counter(part[4:7] for part in parts).most_common(1)[0][0]
        canonical_cells = [
            canonical_part_number(part, index, row_suffix) if part is not None else None
            for index, part in enumerate(cells)
        ]
        rows.append(
            (
                str(perm_words[0]["text"]).replace(",", ""),
                float(str(al_words[0]["text"]).replace(",", "")),
                canonical_cells,
            )
        )

    if not rows:
        raise ValueError(f"Catalog page {printed_page}: no toroid rows parsed")

    records: list[dict[str, Any]] = []
    for permeability, al_value, cells in rows:
        for material_index, part_number in enumerate(cells):
            if part_number is None:
                continue
            material_name, _, _, coating = MATERIALS[material_index]
            records.append(
                {
                    "partNumber": part_number,
                    "manufacturer": "Magnetics",
                    "family": "powder-toroid",
                    "material": {
                        "manufacturer": "Magnetics",
                        "name": material_name,
                        "grade": permeability,
                    },
                    "coating": CURRENT_REVIEWED_COATING.get(part_number, coating),
                    "catalogRevision": "magnetics-powder-2025",
                    "sourceUrl": SOURCE_URL,
                    "sourcePage": printed_page,
                    "outerDiameter": {
                        "nominalM": rounded(float(before[0]) / 1000),
                        "minM": None,
                        "maxM": rounded(float(after[0]) / 1000),
                    },
                    "innerDiameter": {
                        "nominalM": rounded(float(before[1]) / 1000),
                        "minM": rounded(float(after[1]) / 1000),
                        "maxM": None,
                    },
                    "height": {
                        "nominalM": rounded(float(before[2]) / 1000),
                        "minM": None,
                        "maxM": rounded(float(after[2]) / 1000),
                    },
                    "effectiveAreaM2": rounded(float(params["ae"]) * 1e-6),
                    "pathLengthM": rounded(float(params["le"]) * 1e-3),
                    "volumeM3": rounded(float(params["ve"]) * 1e-9),
                    "alValueNh": al_value,
                    "reviewStatus": (
                        "reviewed" if part_number in REVIEWED_PARTS else "draft"
                    ),
                    "reviewedBy": (
                        "Fabio Posser" if part_number in REVIEWED_PARTS else None
                    ),
                }
            )
    return records


def extract(pdf_path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_index in range(START_PAGE_INDEX, END_PAGE_INDEX):
            printed_page = 154 + page_index - START_PAGE_INDEX
            records.extend(parse_page(pdf.pages[page_index], printed_page))

        index_parts: set[str] = set()
        for page_index in range(3, 10):
            text = pdf.pages[page_index].extract_text(x_tolerance=1, y_tolerance=2) or ""
            index_parts.update(re.findall(r"\b(?:C?\d{6,7}A[279Y])\b", text))

    by_part: dict[str, dict[str, Any]] = {}
    for record in records:
        part_number = str(record["partNumber"])
        if part_number in by_part:
            raise ValueError(f"Duplicate extracted part number: {part_number}")
        by_part[part_number] = record
    result = sorted(by_part.values(), key=lambda record: str(record["partNumber"]))

    if "078050A7" in index_parts:
        index_parts.remove("078050A7")
        index_parts.add("0078050A7")
    extracted_parts = {str(record["partNumber"]) for record in result}
    index_only = sorted(index_parts - extracted_parts)
    data_only = sorted(extracted_parts - index_parts)
    if index_only != EXPECTED_INDEX_ONLY or data_only != EXPECTED_DATA_ONLY:
        raise ValueError(
            "Unexpected data-table/index mismatch: "
            f"index_only={index_only} data_only={data_only}"
        )
    if len(result) != 1_923:
        raise ValueError(f"Expected 1,923 records, got {len(result)}")
    return result


def format_number(value: float) -> str:
    if value == 0:
        return "0.0"
    if abs(value) < 1e-4:
        return f"{value:.12g}"
    text = f"{value:.12f}".rstrip("0").rstrip(".")
    return text if "." in text else f"{text}.0"


def format_dimension(dimension: dict[str, Any]) -> str:
    def fmt(value: Any) -> str:
        return "null" if value is None else format_number(float(value))

    return (
        "{nominalM: "
        + fmt(dimension["nominalM"])
        + ", minM: "
        + fmt(dimension["minM"])
        + ", maxM: "
        + fmt(dimension["maxM"])
        + "}"
    )


def render_yaml(records: list[dict[str, Any]]) -> str:
    lines = [
        "# Generated from the 2025 Magnetics Powder Cores Catalog toroid data pages 154-196.",
        "# Newly imported records remain draft until every value is human-reviewed against",
        "# the cited source page. The ten previously reviewed records retain their status.",
        "# Dimensions use Before Finish as nominalM and the applicable After Finish limit:",
        "# OD/HT -> maxM, ID -> minM; the opposite bounds intentionally remain null.",
        "# Data tables are authoritative. Locator-only 0055340A2 and 0055341A2 are omitted",
        "# because the catalog provides no corresponding AL/data row to transcribe.",
        "records:",
    ]
    for record in records:
        material = record["material"]
        lines.extend(
            [
                f'  - partNumber: "{record["partNumber"]}"',
                "    manufacturer: Magnetics",
                "    family: powder-toroid",
                "    material: {"
                f'manufacturer: Magnetics, name: {material["name"]}, grade: "{material["grade"]}"'
                "}",
                f'    coating: {record["coating"]}',
                "    catalogRevision: magnetics-powder-2025",
                f"    sourceUrl: {SOURCE_URL}",
                f'    sourcePage: {record["sourcePage"]}',
                f'    outerDiameter: {format_dimension(record["outerDiameter"])}',
                f'    innerDiameter: {format_dimension(record["innerDiameter"])}',
                f'    height: {format_dimension(record["height"])}',
                f'    effectiveAreaM2: {format_number(float(record["effectiveAreaM2"]))}',
                f'    pathLengthM: {format_number(float(record["pathLengthM"]))}',
                f'    volumeM3: {format_number(float(record["volumeM3"]))}',
                f'    alValueNh: {format_number(float(record["alValueNh"]))}',
                f'    reviewStatus: {record["reviewStatus"]}',
                (
                    "    reviewedBy: null"
                    if record["reviewedBy"] is None
                    else f'    reviewedBy: {record["reviewedBy"]}'
                ),
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    records = extract(args.pdf)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render_yaml(records), encoding="utf-8")
    counts = Counter(str(record["material"]["name"]) for record in records)
    print(f"wrote {len(records)} unique records to {args.out}")
    print(dict(sorted(counts.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
