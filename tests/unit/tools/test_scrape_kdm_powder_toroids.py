from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.scrape_kdm_powder_toroids import FAMILIES, Family, parse_records, validate_records
from tools.scrape_kdm_powder_toroids_guard import ensure_complete_family_results


class FakeSession:
    pass


def parse_mpp_html(monkeypatch: pytest.MonkeyPatch, html: str) -> list[dict[str, object]]:
    response = SimpleNamespace(
        text=html,
        url="https://www.kdm-mag.com/products/details-toroidal-1381.html",
    )
    monkeypatch.setattr(
        "tools.scrape_kdm_powder_toroids.fetch", lambda session, url: response
    )
    return parse_records(
        FakeSession(),
        Family("KM", "MPP"),
        "https://www.kdm-mag.com/products/mpp",
        response.url,
    )


def test_bulk_import_scope_excludes_deferred_variants_and_separate_mpp() -> None:
    assert {family.code for family in FAMILIES} == {
        "KS",
        "KS-HF",
        "KPH",
        "KSF",
        "KNF",
        "KH",
        "KH-H",
        "KAM",
    }


def test_complete_family_results_accepts_mpp() -> None:
    summaries = [
        {"code": "KS", "records": 10, "error": None},
        {"code": "KM", "records": 117, "error": None},
    ]
    ensure_complete_family_results(summaries, required_codes={"KS", "KM"})


def test_missing_mpp_fails_closed() -> None:
    summaries = [
        {"code": "KS", "records": 10, "error": None},
        {"code": "KM", "records": 0, "error": "No valid data rows parsed"},
    ]
    with pytest.raises(RuntimeError, match="KM"):
        ensure_complete_family_results(summaries, required_codes={"KS", "KM"})


def test_omitted_family_fails_closed() -> None:
    with pytest.raises(RuntimeError, match="KM"):
        ensure_complete_family_results(
            [{"code": "KS", "records": 10, "error": None}],
            required_codes={"KS", "KM"},
        )


def test_mpp_datasheet_rows_are_parsed(monkeypatch: pytest.MonkeyPatch) -> None:
    html = (Path(__file__).parent / "fixtures/kdm_mpp.html").read_text()
    records = parse_mpp_html(monkeypatch, html)
    assert [record["partNumber"] for record in records] == [
        "KM050-026A",
        "KM050-060A",
        "KM401-125A",
    ]
    assert records[0]["material"] == {
        "manufacturer": "KDM",
        "name": "MPP",
        "grade": "26",
    }
    assert records[0]["alValueNh"] == 12.0
    assert records[0]["outerDiameter"] == {
        "nominalM": pytest.approx(0.01270),
        "minM": None,
        "maxM": pytest.approx(0.01346),
    }
    assert records[0]["innerDiameter"] == {
        "nominalM": pytest.approx(0.00762),
        "minM": pytest.approx(0.00699),
        "maxM": None,
    }
    assert records[0]["height"] == {
        "nominalM": pytest.approx(0.00475),
        "minM": None,
        "maxM": pytest.approx(0.00551),
    }
    assert records[0]["effectiveAreaM2"] == pytest.approx(1.14e-5)
    assert records[0]["pathLengthM"] == pytest.approx(0.0312)
    assert records[0]["volumeM3"] == pytest.approx(3.56e-7)
    outer = records[0]["outerDiameter"]
    inner = records[0]["innerDiameter"]
    assert isinstance(outer, dict)
    assert isinstance(inner, dict)
    assert outer["maxM"] == 0.01346
    assert inner["minM"] == 0.00699
    assert records[0]["effectiveAreaM2"] == 1.14e-5
    assert records[0]["pathLengthM"] == 0.0312
    assert records[0]["volumeM3"] == 3.56e-7
    validate_records(records)


def test_conflicting_mpp_duplicate_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    html = (Path(__file__).parent / "fixtures/kdm_mpp.html").read_text()
    html = html.replace(
        "<td>125</td><td>420</td>\n<td><a href='/uploads/KM401-125A-v2.pdf'>",
        "<td>125</td><td>421</td>\n<td><a href='/uploads/KM401-125A-v2.pdf'>",
    )

    with pytest.raises(RuntimeError, match="KM401-125A"):
        parse_mpp_html(monkeypatch, html)


def test_empty_mpp_table_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(RuntimeError, match="No valid data rows"):
        parse_mpp_html(monkeypatch, "<html><body><table></table></body></html>")


def test_mpp_import_writes_separate_canonical_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tools.scrape_kdm_mpp as module

    records = [
        {
            "partNumber": "KM050-026A",
            "manufacturer": "KDM",
            "family": "powder-toroid",
            "material": {"manufacturer": "KDM", "name": "MPP", "grade": "26"},
            "coating": "manufacturer standard coating (unspecified)",
            "catalogRevision": "kdm-web-test",
            "sourceUrl": "https://www.kdm-mag.com/uploads/KM050-026A.pdf",
            "sourcePage": 1,
            "outerDiameter": {"nominalM": 0.0127, "minM": None, "maxM": 0.01346},
            "innerDiameter": {"nominalM": 0.00762, "minM": 0.00699, "maxM": None},
            "height": {"nominalM": 0.00475, "minM": None, "maxM": 0.00551},
            "effectiveAreaM2": 1.14e-5,
            "pathLengthM": 0.0312,
            "volumeM3": 3.56e-7,
            "alValueNh": 12.0,
            "reviewStatus": "draft",
            "reviewedBy": None,
        }
    ]
    monkeypatch.setattr(module, "parse_records", lambda *args: records.copy())
    output = tmp_path / "kdm-mpp.yaml"
    summary = tmp_path / "summary.json"

    imported = module.run_import(output_path=output, summary_path=summary)

    assert [record["partNumber"] for record in imported] == ["KM050-026A"]
    assert "KM050-026A" in output.read_text()
    assert json.loads(summary.read_text())["totalRecords"] == 1
