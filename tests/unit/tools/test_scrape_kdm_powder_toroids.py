from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.scrape_kdm_powder_toroids import Family, parse_records
from tools.scrape_kdm_powder_toroids_guard import ensure_complete_family_results


class FakeSession:
    pass


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
    response = SimpleNamespace(
        text=html,
        url="https://www.kdm-mag.com/products/details-toroidal-1381.html",
    )
    monkeypatch.setattr(
        "tools.scrape_kdm_powder_toroids.fetch", lambda session, url: response
    )
    records = parse_records(
        FakeSession(),
        Family("KM", "MPP"),
        "https://www.kdm-mag.com/products/mpp",
        response.url,
    )
    assert [record["partNumber"] for record in records] == [
        "KM050-026A",
        "KM050-060A",
    ]
    assert records[0]["material"] == {
        "manufacturer": "KDM",
        "name": "MPP",
        "grade": "26",
    }
    assert records[0]["alValueNh"] == 12.0
