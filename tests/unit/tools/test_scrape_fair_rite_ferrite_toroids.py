from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from tools.fair_rite_toroid_catalog import build_catalog
from tools.fair_rite_toroid_parser import (
    ParsedDimension,
    RawProduct,
    coating_from_part_number,
    discover_product_urls,
    merge_duplicate_products,
    parse_dimension,
    parse_product_page,
    uncoated_counterpart,
)

ROOT = Path(__file__).resolve().parents[3]


def test_parse_symmetric_tolerance() -> None:
    assert parse_dimension("22.10 ±0.40") == ParsedDimension(22.10, 21.70, 22.50)


def test_parse_negative_one_sided_tolerance() -> None:
    assert parse_dimension("3.30 -0.25") == ParsedDimension(3.30, 3.05, 3.30)


def test_parse_positive_one_sided_tolerance() -> None:
    assert parse_dimension("4.75 +0.25") == ParsedDimension(4.75, 4.75, 5.00)


def test_parse_limit_only_dimensions() -> None:
    assert parse_dimension("75.85 Max") == ParsedDimension(None, None, 75.85)
    assert parse_dimension("37.60 Min") == ParsedDimension(None, 37.60, None)


def test_malformed_tolerance_is_not_invented() -> None:
    with pytest.raises(ValueError, match="malformed tolerance"):
        parse_dimension("38.85 ±075")


def test_discover_product_urls_deduplicates_and_filters() -> None:
    html = """
    <a href='/product/toroids-5980001801/'>5980001801</a>
    <a href='https://fair-rite.com/product/toroids-5980001801/'>duplicate</a>
    <a href='/product/not-a-toroid/'>ignore</a>
    <a href='/product/toroids-5943011121/'>5943011121</a>
    """
    assert discover_product_urls(html, "https://fair-rite.com/category/") == [
        "https://fair-rite.com/product/toroids-5943011121/",
        "https://fair-rite.com/product/toroids-5980001801/",
    ]


def test_parse_uncoated_product_page() -> None:
    html = (Path(__file__).parent / "fixtures/fair_rite_uncoated.html").read_text()
    product = parse_product_page(html, "https://fair-rite.com/product/toroids-5980001801/")
    assert product.part_number == "5980001801"
    assert product.material_code == "80"
    assert product.coating == "uncoated (burnished)"
    assert product.dimensions["A"] == ParsedDimension(22.1, 21.7, 22.5)
    assert product.dimensions["B"] == ParsedDimension(13.7, 13.4, 14.0)
    assert product.dimensions["C"] == ParsedDimension(6.35, 6.10, 6.60)
    assert product.al_value_nh == 330.0
    assert product.area_cm2 == 0.260
    assert product.path_cm == 5.42
    assert product.volume_cm3 == 1.420


def test_parse_coated_product_page() -> None:
    html = (Path(__file__).parent / "fixtures/fair_rite_coated.html").read_text()
    product = parse_product_page(html, "https://fair-rite.com/product/toroids-5943011121/")
    assert product.coating == "thermo-set plastic"
    assert product.dimensions["A"] == ParsedDimension(None, None, 75.85)
    assert product.dimensions["B"] == ParsedDimension(None, 37.60, None)
    assert product.dimensions["C"] == ParsedDimension(None, None, 13.60)


def test_coated_product_uses_verified_uncoated_nominals() -> None:
    uncoated = RawProduct(
        part_number="5943011101",
        material_code="43",
        coating="uncoated (burnished)",
        source_url="https://fair-rite.com/product/toroids-5943011101/",
        dimensions={
            "A": ParsedDimension(73.65, 72.15, 75.15),
            "B": ParsedDimension(38.85, 38.10, 39.60),
            "C": ParsedDimension(12.70, 12.30, 13.10),
        },
        al_value_nh=1300.0,
        area_cm2=2.15,
        path_cm=16.7,
        volume_cm3=35.9,
    )
    coated = RawProduct(
        part_number="5943011121",
        material_code="43",
        coating="thermo-set plastic",
        source_url="https://fair-rite.com/product/toroids-5943011121/",
        dimensions={
            "A": ParsedDimension(None, None, 75.85),
            "B": ParsedDimension(None, 37.60, None),
            "C": ParsedDimension(None, None, 13.60),
        },
        al_value_nh=1300.0,
        area_cm2=2.15,
        path_cm=16.7,
        volume_cm3=35.9,
    )

    records, unresolved = build_catalog([uncoated, coated], "fair-rite-web-test")
    assert unresolved == []
    coated_record = next(r for r in records if r["partNumber"] == "5943011121")
    assert coated_record["outerDiameter"] == {
        "nominalM": pytest.approx(0.07365),
        "minM": None,
        "maxM": pytest.approx(0.07585),
    }
    assert coated_record["innerDiameter"] == {
        "nominalM": pytest.approx(0.03885),
        "minM": pytest.approx(0.03760),
        "maxM": None,
    }
    assert coated_record["height"] == {
        "nominalM": pytest.approx(0.01270),
        "minM": None,
        "maxM": pytest.approx(0.01360),
    }


def test_missing_coated_counterpart_is_reported() -> None:
    coated = RawProduct(
        part_number="5943011121",
        material_code="43",
        coating="thermo-set plastic",
        source_url="https://fair-rite.com/product/toroids-5943011121/",
        dimensions={
            "A": ParsedDimension(None, None, 75.85),
            "B": ParsedDimension(None, 37.60, None),
            "C": ParsedDimension(None, None, 13.60),
        },
        al_value_nh=1300.0,
        area_cm2=2.15,
        path_cm=16.7,
        volume_cm3=35.9,
    )
    records, unresolved = build_catalog([coated], "fair-rite-web-test")
    assert records == []
    assert unresolved[0].part_number == "5943011121"
    assert unresolved[0].reason == "no unambiguous nominal-dimension counterpart"
    assert unresolved[0].attempted_match == "5943011101"


def test_magnetic_mismatch_prevents_pairing() -> None:
    base = RawProduct(
        part_number="5943011101",
        material_code="43",
        coating="uncoated (burnished)",
        source_url="u",
        dimensions={
            "A": ParsedDimension(73.65, 72.15, 75.15),
            "B": ParsedDimension(38.85, 38.10, 39.60),
            "C": ParsedDimension(12.70, 12.30, 13.10),
        },
        al_value_nh=1300.0,
        area_cm2=2.15,
        path_cm=16.7,
        volume_cm3=35.9,
    )
    coated = RawProduct(
        part_number="5943011121",
        material_code="43",
        coating="thermo-set plastic",
        source_url="c",
        dimensions={
            "A": ParsedDimension(None, None, 75.85),
            "B": ParsedDimension(None, 37.60, None),
            "C": ParsedDimension(None, None, 13.60),
        },
        al_value_nh=1400.0,
        area_cm2=2.15,
        path_cm=16.7,
        volume_cm3=35.9,
    )
    records, unresolved = build_catalog([base, coated], "rev")
    assert [r["partNumber"] for r in records] == ["5943011101"]
    assert unresolved[0].reason == "coated/uncoated magnetic parameters conflict"


def test_identical_duplicates_are_deduplicated() -> None:
    html = (Path(__file__).parent / "fixtures/fair_rite_uncoated.html").read_text()
    product = parse_product_page(html, "https://fair-rite.com/product/toroids-5980001801/")
    assert merge_duplicate_products([product, product]) == [product]


def test_conflicting_duplicates_fail() -> None:
    html = (Path(__file__).parent / "fixtures/fair_rite_uncoated.html").read_text()
    product = parse_product_page(html, "https://fair-rite.com/product/toroids-5980001801/")
    conflicting = RawProduct(**{**product.__dict__, "al_value_nh": 331.0})
    with pytest.raises(RuntimeError, match="Conflicting duplicate"):
        merge_duplicate_products([product, conflicting])


def test_generated_record_matches_schema() -> None:
    html = (Path(__file__).parent / "fixtures/fair_rite_uncoated.html").read_text()
    product = parse_product_page(html, "https://fair-rite.com/product/toroids-5980001801/")
    records, unresolved = build_catalog([product], "fair-rite-web-test")
    assert unresolved == []
    schema = json.loads((ROOT / "schemas/catalog/core.v1.schema.json").read_text())
    errors = list(Draft202012Validator(schema).iter_errors(records[0]))
    assert errors == []


def test_dimension_parser_handles_split_table_cells() -> None:
    html = """
    <html><body>
    <div>Part Number: 5980001801</div><div>80 TOROID</div><div>80 Material</div>
    <table>
      <tr><td>A</td><td>22.1</td><td>±0.40</td><td>0.870</td></tr>
      <tr><td>B</td><td>13.7</td><td>±0.30</td><td>0.540</td></tr>
      <tr><td>C</td><td>6.35</td><td>±0.25</td><td>0.250</td></tr>
    </table>
    <table>
      <tr><td>A_L(nH)</td><td>330 ±25%</td></tr>
      <tr><td>Ae(cm2)</td><td>0.260</td></tr>
      <tr><td>l_e(cm)</td><td>5.42</td></tr>
      <tr><td>V_e(cm3)</td><td>1.420</td></tr>
    </table>
    </body></html>
    """
    product = parse_product_page(html, "https://fair-rite.com/product/toroids-5980001801/")
    assert product.dimensions["A"] == ParsedDimension(22.1, 21.7, 22.5)


def test_coating_digit_and_counterpart_rules() -> None:
    assert coating_from_part_number("5976000211") == "Parylene C"
    assert coating_from_part_number("5943011121") == "thermo-set plastic"
    assert coating_from_part_number("5980001801") == "uncoated (burnished)"
    assert uncoated_counterpart("5943011121") == "5943011101"


def test_run_import_writes_valid_local_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tools.scrape_fair_rite_ferrite_toroids as module

    category = "<a href='/product/toroids-5980001801/'>5980001801</a>"
    product_html = (Path(__file__).parent / "fixtures/fair_rite_uncoated.html").read_text()

    def fake_fetch(session: object, url: str) -> str:
        if "product-category" in url:
            return category
        return product_html

    monkeypatch.setattr(module, "fetch", fake_fetch)
    monkeypatch.setattr(module, "MIN_EXPECTED_PRODUCTS", 1)
    output = tmp_path / "fair-rite-ferrite.yaml"
    unresolved = tmp_path / "fair-rite-ferrite-unresolved.md"
    summary = tmp_path / "summary.json"

    records, unresolved_items = module.run_import(
        output_path=output,
        unresolved_path=unresolved,
        summary_path=summary,
    )

    assert len(records) == 1
    assert unresolved_items == []
    assert "5980001801" in output.read_text()
    assert "No unresolved Fair-Rite toroids" in unresolved.read_text()
    assert json.loads(summary.read_text())["importedRecords"] == 1
