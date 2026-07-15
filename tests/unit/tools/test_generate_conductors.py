from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

from inductor_designer.adapters.persistence.record_serde import conductor_record_from_json
from tools.generate_conductors import generate_records, main

ROOT = Path(__file__).resolve().parents[3]
SCHEMA = json.loads((ROOT / "schemas/catalog/conductor.v1.schema.json").read_text("utf-8"))


def test_records_validate_and_map() -> None:
    validator = Draft202012Validator(SCHEMA)
    records = generate_records()
    for record in records:
        validator.validate(record)
        conductor_record_from_json(record)


def test_awg_range_and_metric_sizes_present() -> None:
    names = {record["name"] for record in generate_records()}
    assert {"AWG 10", "AWG 18", "AWG 32"} <= names
    assert {"0.5 mm", "2.5 mm", "0.315 mm"} <= names
    assert "AWG 9" not in names


def test_awg_18_value() -> None:
    record = next(r for r in generate_records() if r["name"] == "AWG 18")
    assert record["bareDiameterM"] == pytest.approx(0.00102362, rel=1e-3)
    assert record["grade1DiameterM"] == pytest.approx(0.001072, rel=1e-3)


def test_generation_is_deterministic() -> None:
    assert generate_records() == generate_records()


def test_main_writes_committed_file(tmp_path: Path) -> None:
    out = tmp_path / "round-wire.yaml"
    assert main(["--out", str(out)]) == 0
    written = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert written["records"] == generate_records()


def test_committed_file_matches_generator() -> None:
    committed = yaml.safe_load(
        (ROOT / "catalog/conductors/round-wire.yaml").read_text(encoding="utf-8")
    )
    assert committed["records"] == generate_records()


def test_all_records_have_insulated_diameters() -> None:
    for record in generate_records():
        assert record["grade1DiameterM"] is not None, record["name"]
        assert record["grade2DiameterM"] is not None, record["name"]
        bare = record["bareDiameterM"]
        assert bare < record["grade1DiameterM"] < record["grade2DiameterM"]  # type: ignore[operator]


def test_insulation_file_covers_every_conductor() -> None:
    insulation = yaml.safe_load(
        (ROOT / "catalog/conductors/insulation-round-wire.yaml").read_text(encoding="utf-8")
    )
    names = {entry["name"] for entry in insulation["records"]}
    generated = {record["name"] for record in generate_records()}
    assert generated <= names
