from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from inductor_designer.adapters.persistence.record_serde import (
    conductor_record_from_json,
    core_record_from_json,
)
from inductor_designer.domain.catalog_records import ConductorRecord, CoreRecord


class SqliteCatalogRepository:
    def __init__(self, path: Path) -> None:
        if not path.is_file():
            raise FileNotFoundError(f"Catalog index not found: {path}")
        self._path = path

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(f"file:{self._path.as_posix()}?mode=ro", uri=True)

    def get_core(self, part_number: str) -> CoreRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT record_json FROM cores WHERE part_number = ?", (part_number,)
            ).fetchone()
        return core_record_from_json(json.loads(row[0])) if row else None

    def list_cores(self) -> tuple[CoreRecord, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT record_json FROM cores ORDER BY part_number"
            ).fetchall()
        return tuple(core_record_from_json(json.loads(row[0])) for row in rows)

    def get_conductor(self, name: str) -> ConductorRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT record_json FROM conductors WHERE name = ?", (name,)
            ).fetchone()
        return conductor_record_from_json(json.loads(row[0])) if row else None

    def list_conductor_names(self) -> tuple[str, ...]:
        with self._connect() as connection:
            rows = connection.execute("SELECT name FROM conductors ORDER BY name").fetchall()
        return tuple(row[0] for row in rows)
