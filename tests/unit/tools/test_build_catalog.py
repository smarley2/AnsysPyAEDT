from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
import yaml

from tools.build_catalog import build, main

ROOT = Path(__file__).resolve().parents[3]


def build_default(tmp_path: Path) -> Path:
    out = tmp_path / "catalog.sqlite"
    build(ROOT / "catalog", ROOT / "schemas" / "catalog", out)
    return out


def test_build_from_canonical_sources(tmp_path: Path) -> None:
    out = build_default(tmp_path)
    with sqlite3.connect(out) as connection:
        cores = connection.execute("SELECT COUNT(*) FROM cores").fetchone()[0]
        conductors = connection.execute("SELECT COUNT(*) FROM conductors").fetchone()[0]
        meta = dict(connection.execute("SELECT key, value FROM meta"))
    assert cores >= 15
    assert conductors == 35
    assert meta["schemaVersion"] == "1"
    assert meta["coreCount"] == str(cores)


def test_record_json_round_trips(tmp_path: Path) -> None:
    out = build_default(tmp_path)
    with sqlite3.connect(out) as connection:
        row = connection.execute(
            "SELECT record_json FROM cores WHERE part_number = ?", ("0077071A7",)
        ).fetchone()
    record = json.loads(row[0])
    assert record["partNumber"] == "0077071A7"


def test_build_is_deterministic(tmp_path: Path) -> None:
    first = build_default(tmp_path)
    second = tmp_path / "second.sqlite"
    build(ROOT / "catalog", ROOT / "schemas" / "catalog", second)
    assert first.read_bytes() == second.read_bytes()


def test_invalid_record_fails_build(tmp_path: Path) -> None:
    source = tmp_path / "catalog"
    (source / "cores").mkdir(parents=True)
    (source / "conductors").mkdir()
    (source / "cores" / "bad.yaml").write_text(
        yaml.safe_dump({"records": [{"partNumber": "X"}]}), encoding="utf-8"
    )
    (source / "conductors" / "round-wire.yaml").write_text(
        yaml.safe_dump({"records": []}), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="bad.yaml"):
        build(source, ROOT / "schemas" / "catalog", tmp_path / "out.sqlite")


def test_main_cli(tmp_path: Path) -> None:
    out = tmp_path / "cli.sqlite"
    code = main(
        [
            "--source", str(ROOT / "catalog"),
            "--schemas", str(ROOT / "schemas" / "catalog"),
            "--out", str(out),
        ]
    )
    assert code == 0
    assert out.is_file()
