from __future__ import annotations

import json
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

from inductor_designer.adapters.persistence.record_serde import core_record_from_json

ROOT = Path(__file__).resolve().parents[3]
CORE_SCHEMA = json.loads((ROOT / "schemas/catalog/core.v1.schema.json").read_text("utf-8"))
CORE_FILES = sorted((ROOT / "catalog/cores").glob("*.yaml"))


def load_records(path: Path) -> list[dict[str, object]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict) and isinstance(data["records"], list)
    return data["records"]


def test_core_files_exist() -> None:
    names = {path.name for path in CORE_FILES}
    assert {"magnetics-powder.yaml", "magnetics-ferrite.yaml"} <= names


def test_every_core_record_validates_and_maps() -> None:
    validator = Draft202012Validator(CORE_SCHEMA)
    seen: set[str] = set()
    total = 0
    for path in CORE_FILES:
        for record in load_records(path):
            validator.validate(record)
            core = core_record_from_json(record)
            assert core.part_number not in seen, f"duplicate {core.part_number}"
            seen.add(core.part_number)
            total += 1
    assert total >= 15
