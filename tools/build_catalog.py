"""Compile canonical catalog YAML into the SQLite index (build artifact, never edited)."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, ValidationError

_DDL = """
CREATE TABLE cores (
    part_number TEXT PRIMARY KEY,
    family TEXT NOT NULL,
    manufacturer TEXT NOT NULL,
    review_status TEXT NOT NULL,
    record_json TEXT NOT NULL
);
CREATE TABLE conductors (
    name TEXT PRIMARY KEY,
    standard TEXT NOT NULL,
    review_status TEXT NOT NULL,
    record_json TEXT NOT NULL
);
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def _load_validator(schema_root: Path, name: str) -> Draft202012Validator:
    schema = json.loads((schema_root / name).read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def _load_records(path: Path, validator: Draft202012Validator) -> list[dict[str, Any]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("records"), list):
        raise ValueError(f"Catalog file must contain a 'records' list: {path.name}")
    records: list[dict[str, Any]] = []
    for index, record in enumerate(data["records"]):
        try:
            validator.validate(record)
        except ValidationError as error:
            raise ValueError(
                f"Invalid record {index} in {path.name}: {error.message}"
            ) from error
        records.append(record)
    return records


def build(source_root: Path, schema_root: Path, out_path: Path) -> None:
    core_validator = _load_validator(schema_root, "core.v1.schema.json")
    conductor_validator = _load_validator(schema_root, "conductor.v1.schema.json")

    cores: list[dict[str, Any]] = []
    for path in sorted((source_root / "cores").glob("*.yaml")):
        cores.extend(_load_records(path, core_validator))
    conductors: list[dict[str, Any]] = []
    for path in sorted((source_root / "conductors").glob("*.yaml")):
        conductors.extend(_load_records(path, conductor_validator))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.unlink(missing_ok=True)
    connection = sqlite3.connect(out_path)
    try:
        connection.executescript(_DDL)
        connection.executemany(
            "INSERT INTO cores VALUES (?, ?, ?, ?, ?)",
            [
                (
                    record["partNumber"],
                    record["family"],
                    record["manufacturer"],
                    record["reviewStatus"],
                    json.dumps(record, sort_keys=True),
                )
                for record in sorted(cores, key=lambda r: str(r["partNumber"]))
            ],
        )
        connection.executemany(
            "INSERT INTO conductors VALUES (?, ?, ?, ?)",
            [
                (
                    record["name"],
                    record["standard"],
                    record["reviewStatus"],
                    json.dumps(record, sort_keys=True),
                )
                for record in sorted(conductors, key=lambda r: str(r["name"]))
            ],
        )
        connection.executemany(
            "INSERT INTO meta VALUES (?, ?)",
            [
                ("schemaVersion", "1"),
                ("coreCount", str(len(cores))),
                ("conductorCount", str(len(conductors))),
            ],
        )
        connection.commit()
    finally:
        connection.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("catalog"))
    parser.add_argument("--schemas", type=Path, default=Path("schemas/catalog"))
    parser.add_argument("--out", type=Path, default=Path("artifacts/catalog/catalog.sqlite"))
    args = parser.parse_args(argv)
    build(args.source, args.schemas, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
