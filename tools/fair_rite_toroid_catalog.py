from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from tools.fair_rite_toroid_parser import (
    ParsedDimension,
    RawProduct,
    UnresolvedProduct,
    merge_duplicate_products,
    uncoated_counterpart,
)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "catalog" / "core.v1.schema.json"


def _magnetics_match(left: RawProduct, right: RawProduct) -> bool:
    values = (
        (left.al_value_nh, right.al_value_nh),
        (left.area_cm2, right.area_cm2),
        (left.path_cm, right.path_cm),
        (left.volume_cm3, right.volume_cm3),
    )
    return left.material_code == right.material_code and all(
        math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-12) for a, b in values
    )


def _dimension_to_si(dimension: ParsedDimension) -> dict[str, float | None]:
    if dimension.nominal_mm is None:
        raise ValueError("Dimension does not have a nominal value")
    return {
        "nominalM": dimension.nominal_mm / 1_000,
        "minM": None if dimension.min_mm is None else dimension.min_mm / 1_000,
        "maxM": None if dimension.max_mm is None else dimension.max_mm / 1_000,
    }


def _record(
    product: RawProduct,
    dimensions: dict[str, ParsedDimension],
    revision: str,
) -> dict[str, Any]:
    return {
        "partNumber": product.part_number,
        "manufacturer": "Fair-Rite",
        "family": "ferrite-toroid",
        "material": {
            "manufacturer": "Fair-Rite",
            "name": f"{product.material_code} Material",
            "grade": product.material_code,
        },
        "coating": product.coating,
        "catalogRevision": revision,
        "sourceUrl": product.source_url,
        "sourcePage": 1,
        "outerDiameter": _dimension_to_si(dimensions["A"]),
        "innerDiameter": _dimension_to_si(dimensions["B"]),
        "height": _dimension_to_si(dimensions["C"]),
        "effectiveAreaM2": product.area_cm2 * 1e-4,
        "pathLengthM": product.path_cm * 1e-2,
        "volumeM3": product.volume_cm3 * 1e-6,
        "alValueNh": product.al_value_nh,
        "reviewStatus": "draft",
        "reviewedBy": None,
    }


def build_catalog(
    products: list[RawProduct], revision: str
) -> tuple[list[dict[str, Any]], list[UnresolvedProduct]]:
    products = merge_duplicate_products(products)
    by_part = {product.part_number: product for product in products}
    records: list[dict[str, Any]] = []
    unresolved: list[UnresolvedProduct] = []

    for product in products:
        dimensions = product.dimensions
        if all(dimensions[key].nominal_mm is not None for key in ("A", "B", "C")):
            records.append(_record(product, dimensions, revision))
            continue

        counterpart_number = uncoated_counterpart(product.part_number)
        counterpart = by_part.get(counterpart_number)
        if counterpart is None:
            unresolved.append(
                UnresolvedProduct(
                    part_number=product.part_number,
                    material_code=product.material_code,
                    product_url=product.source_url,
                    coating=product.coating,
                    reason="no unambiguous nominal-dimension counterpart",
                    available_dimensions=dimensions,
                    attempted_match=counterpart_number,
                )
            )
            continue
        if not _magnetics_match(product, counterpart):
            unresolved.append(
                UnresolvedProduct(
                    part_number=product.part_number,
                    material_code=product.material_code,
                    product_url=product.source_url,
                    coating=product.coating,
                    reason="coated/uncoated magnetic parameters conflict",
                    available_dimensions=dimensions,
                    attempted_match=counterpart_number,
                )
            )
            continue
        if not all(
            counterpart.dimensions[key].nominal_mm is not None for key in ("A", "B", "C")
        ):
            unresolved.append(
                UnresolvedProduct(
                    part_number=product.part_number,
                    material_code=product.material_code,
                    product_url=product.source_url,
                    coating=product.coating,
                    reason="counterpart does not publish complete nominal dimensions",
                    available_dimensions=dimensions,
                    attempted_match=counterpart_number,
                )
            )
            continue

        paired = {
            "A": ParsedDimension(
                counterpart.dimensions["A"].nominal_mm,
                dimensions["A"].min_mm,
                dimensions["A"].max_mm,
            ),
            "B": ParsedDimension(
                counterpart.dimensions["B"].nominal_mm,
                dimensions["B"].min_mm,
                dimensions["B"].max_mm,
            ),
            "C": ParsedDimension(
                counterpart.dimensions["C"].nominal_mm,
                dimensions["C"].min_mm,
                dimensions["C"].max_mm,
            ),
        }
        records.append(_record(product, paired, revision))

    return sorted(records, key=lambda item: str(item["partNumber"])), sorted(
        unresolved, key=lambda item: item.part_number
    )


def validate_records(records: list[dict[str, Any]], schema_path: Path = SCHEMA_PATH) -> None:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    failures: list[str] = []
    for record in records:
        errors = sorted(validator.iter_errors(record), key=lambda error: list(error.path))
        if errors:
            failures.append(
                f"{record['partNumber']}: " + "; ".join(error.message for error in errors)
            )
    if failures:
        raise RuntimeError("Schema validation failed:\n" + "\n".join(failures[:25]))


def render_unresolved(items: list[UnresolvedProduct]) -> str:
    lines = [
        "# Fair-Rite ferrite toroids requiring manual review",
        "",
        (
            "Products listed here were excluded from the canonical YAML because a "
            "required value could not be resolved without invention."
        ),
        "",
    ]
    if not items:
        lines.extend(["No unresolved Fair-Rite toroids were found.", ""])
        return "\n".join(lines)
    for item in items:
        lines.extend(
            [
                f"## `{item.part_number}`",
                "",
                f"- Material: `{item.material_code}`",
                f"- Product URL: {item.product_url}",
                f"- Coating: {item.coating}",
                f"- Reason: {item.reason}",
                (
                    f"- Attempted counterpart: `{item.attempted_match}`"
                    if item.attempted_match
                    else "- Attempted counterpart: none"
                ),
                (
                    "- Missing fields: "
                    + (
                        ", ".join(item.missing_fields)
                        if item.missing_fields
                        else "none explicitly identified"
                    )
                ),
                f"- Available dimensions: `{item.available_dimensions}`",
                f"- Review action: {item.review_action}",
                "",
            ]
        )
    return "\n".join(lines)
