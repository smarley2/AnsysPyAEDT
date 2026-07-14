from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from urllib.parse import urljoin

from bs4 import BeautifulSoup

BASE_URL = "https://fair-rite.com"
CATEGORY_URL = f"{BASE_URL}/product-category/inductive-components/toroids/"
PRODUCT_URL_RE = re.compile(r"/product/toroids-(\d{10})/?$", re.IGNORECASE)


@dataclass(frozen=True)
class ParsedDimension:
    nominal_mm: float | None
    min_mm: float | None
    max_mm: float | None


@dataclass(frozen=True)
class RawProduct:
    part_number: str
    material_code: str
    coating: str
    source_url: str
    dimensions: dict[str, ParsedDimension]
    al_value_nh: float
    area_cm2: float
    path_cm: float
    volume_cm3: float


@dataclass(frozen=True)
class UnresolvedProduct:
    part_number: str
    material_code: str
    product_url: str
    coating: str
    reason: str
    available_dimensions: dict[str, ParsedDimension] | None = None
    missing_fields: tuple[str, ...] = ()
    attempted_match: str | None = None
    review_action: str = (
        "Review the Fair-Rite product page and confirm the missing or ambiguous data."
    )


def clean_text(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").replace("−", "-").split())


def parse_number(value: str) -> float:
    match = re.search(r"[-+]?\d+(?:\.\d+)?", clean_text(value).replace(",", ""))
    if match is None:
        raise ValueError(f"No numeric value in {value!r}")
    return float(match.group(0))


def parse_dimension(value: str) -> ParsedDimension:
    text = clean_text(value)

    limit_match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(Max|Min)", text, re.IGNORECASE)
    if limit_match:
        number = float(limit_match.group(1))
        if limit_match.group(2).lower() == "max":
            return ParsedDimension(None, None, number)
        return ParsedDimension(None, number, None)

    symmetric = re.fullmatch(r"(\d+(?:\.\d+)?)\s*±\s*(\d+(?:\.\d+)?)", text)
    if symmetric:
        nominal_text, tolerance_text = symmetric.groups()
        if "." not in tolerance_text and len(tolerance_text) > 1:
            raise ValueError(f"malformed tolerance in {value!r}")
        nominal_dec = Decimal(nominal_text)
        tolerance_dec = Decimal(tolerance_text)
        return ParsedDimension(
            float(nominal_dec),
            float(nominal_dec - tolerance_dec),
            float(nominal_dec + tolerance_dec),
        )

    one_sided = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([+-])\s*(\d+(?:\.\d+)?)", text)
    if one_sided:
        nominal_text, sign, tolerance_text = one_sided.groups()
        if "." not in tolerance_text and len(tolerance_text) > 1:
            raise ValueError(f"malformed tolerance in {value!r}")
        nominal_dec = Decimal(nominal_text)
        tolerance_dec = Decimal(tolerance_text)
        nominal = float(nominal_dec)
        if sign == "-":
            return ParsedDimension(nominal, float(nominal_dec - tolerance_dec), nominal)
        return ParsedDimension(nominal, nominal, float(nominal_dec + tolerance_dec))

    nominal_match = re.fullmatch(r"\d+(?:\.\d+)?", text)
    if nominal_match:
        number = float(text)
        return ParsedDimension(number, None, None)

    raise ValueError(f"Unsupported dimension notation: {value!r}")


def discover_product_urls(html: str, base_url: str = CATEGORY_URL) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    urls: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        absolute = urljoin(base_url, str(anchor["href"]))
        path = re.sub(r"^https?://[^/]+", "", absolute)
        if PRODUCT_URL_RE.fullmatch(path):
            urls.add(absolute if absolute.endswith("/") else f"{absolute}/")
    return sorted(urls)


def _row_map(soup: BeautifulSoup) -> dict[str, str]:
    rows: dict[str, str] = {}
    for row in soup.find_all("tr"):
        cells = [
            clean_text(cell.get_text(" ", strip=True))
            for cell in row.find_all(["th", "td"])
        ]
        if len(cells) < 2:
            continue
        label = re.sub(r"[^A-Za-z0-9_]", "", cells[0]).lower()
        value = clean_text(" ".join(cells[1:]))
        if label and value and label not in rows:
            rows[label] = value
    return rows


def _extract_labeled_value(rows: dict[str, str], text: str, patterns: tuple[str, ...]) -> str:
    for pattern in patterns:
        normalized = re.sub(r"[^A-Za-z0-9_]", "", pattern).lower()
        if normalized in rows:
            return rows[normalized]
    for pattern in patterns:
        match = re.search(
            rf"{pattern}\s*[: ]?\s*([-+]?\d+(?:\.\d+)?)", text, re.IGNORECASE
        )
        if match:
            return match.group(1)
    raise ValueError(f"Missing labeled value for {patterns!r}")


def _extract_dimension_rows(soup: BeautifulSoup) -> dict[str, ParsedDimension]:
    dimensions: dict[str, ParsedDimension] = {}
    for row in soup.find_all("tr"):
        cells = [
            clean_text(cell.get_text(" ", strip=True))
            for cell in row.find_all(["th", "td"])
        ]
        if len(cells) < 2:
            continue
        label = cells[0].strip().upper()
        if label not in {"A", "B", "C"}:
            continue
        candidates: list[str] = []
        if len(cells) >= 3 and re.fullmatch(
            r"(?:±|[+-])?\s*\d+(?:\.\d+)?|Max|Min", cells[2], re.IGNORECASE
        ):
            candidates.append(clean_text(f"{cells[1]} {cells[2]}"))
        candidates.append(clean_text(cells[1]))
        last_error: ValueError | None = None
        for candidate in candidates:
            try:
                dimensions[label] = parse_dimension(candidate)
                break
            except ValueError as exc:
                last_error = exc
        else:
            raise ValueError(f"Could not parse dimension {label}: {last_error}")
    if set(dimensions) != {"A", "B", "C"}:
        raise ValueError(f"Missing mechanical dimensions: found {sorted(dimensions)}")
    return dimensions


def coating_from_part_number(part_number: str) -> str:
    if not re.fullmatch(r"\d{10}", part_number):
        raise ValueError(f"Invalid Fair-Rite part number: {part_number!r}")
    coating_digit = part_number[8]
    mapping = {
        "0": "uncoated (burnished)",
        "1": "Parylene C",
        "2": "thermo-set plastic",
    }
    try:
        return mapping[coating_digit]
    except KeyError as exc:
        raise ValueError(f"Unsupported Fair-Rite coating digit {coating_digit!r}") from exc


def parse_product_page(html: str, source_url: str) -> RawProduct:
    soup = BeautifulSoup(html, "html.parser")
    text = clean_text(soup.get_text(" ", strip=True))
    part_match = re.search(r"Part Number:\s*(\d{10})", text, re.IGNORECASE)
    if part_match is None:
        slug_match = re.search(r"toroids-(\d{10})", source_url, re.IGNORECASE)
        if slug_match is None:
            raise ValueError("Missing Fair-Rite part number")
        part_number = slug_match.group(1)
    else:
        part_number = part_match.group(1)

    material_code = part_number[2:4]
    if not re.search(rf"\b{re.escape(material_code)}\s+Material\b", text, re.IGNORECASE):
        raise ValueError(f"Product page does not confirm material {material_code}")
    if not re.search(r"\b(?:COATED\s+)?TOROID\b", text, re.IGNORECASE):
        raise ValueError("Product page is not identified as a toroid")

    dimensions = _extract_dimension_rows(soup)
    rows = _row_map(soup)
    al_value_nh = parse_number(
        _extract_labeled_value(rows, text, (r"A_?L\(nH\)", r"AL\(nH\)"))
    )
    area_cm2 = parse_number(
        _extract_labeled_value(rows, text, (r"Ae\(cm2\)", r"Ae\(cm\^?2\)"))
    )
    path_cm = parse_number(
        _extract_labeled_value(rows, text, (r"l_?e\(cm\)", r"le\(cm\)"))
    )
    volume_cm3 = parse_number(
        _extract_labeled_value(rows, text, (r"V_?e\(cm3\)", r"Ve\(cm\^?3\)"))
    )
    return RawProduct(
        part_number=part_number,
        material_code=material_code,
        coating=coating_from_part_number(part_number),
        source_url=source_url,
        dimensions=dimensions,
        al_value_nh=al_value_nh,
        area_cm2=area_cm2,
        path_cm=path_cm,
        volume_cm3=volume_cm3,
    )


def merge_duplicate_products(products: list[RawProduct]) -> list[RawProduct]:
    unique: dict[str, RawProduct] = {}
    for product in products:
        previous = unique.get(product.part_number)
        if previous is None:
            unique[product.part_number] = product
        elif previous != product:
            raise RuntimeError(
                f"Conflicting duplicate Fair-Rite part number: {product.part_number}"
            )
    return [unique[part] for part in sorted(unique)]


def uncoated_counterpart(part_number: str) -> str:
    return f"{part_number[:8]}0{part_number[9:]}"
