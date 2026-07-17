from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

LATEST_PROJECT_SCHEMA_VERSION = 3


def _migrate_v1_to_v2(document: dict[str, object]) -> dict[str, object]:
    migrated = dict(document)
    migrated["schemaVersion"] = 2
    raw_target = migrated["target"]
    assert isinstance(raw_target, dict)
    target = dict(raw_target)
    target.setdefault("dimensionMode", "3d")
    migrated["target"] = target
    migrated["core"] = None
    migrated["windings"] = []
    return migrated


def _migrate_v2_to_v3(document: dict[str, object]) -> dict[str, object]:
    migrated = dict(document)
    migrated["schemaVersion"] = 3
    migrated["materials"] = []
    return migrated


_MIGRATIONS: dict[int, Callable[[dict[str, object]], dict[str, object]]] = {
    1: _migrate_v1_to_v2,
    2: _migrate_v2_to_v3,
}


class SchemaRepository:
    def __init__(self, root: Path) -> None:
        self._root = root

    def load_project_schema(self, version: int) -> Mapping[str, object]:
        path = self._root / "project" / f"v{version}.schema.json"
        if not path.is_file():
            raise ValueError(f"Unsupported project schema version: {version}")
        loaded: Any = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError(f"Project schema is not a JSON object: {path}")
        return loaded

    def validate_project(self, document: Mapping[str, object]) -> None:
        version = document.get("schemaVersion")
        if not isinstance(version, int):
            raise ValueError("Project schemaVersion must be an integer")
        schema = self.load_project_schema(version)
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(document)

    def migrate_project(self, document: Mapping[str, object]) -> dict[str, object]:
        self.validate_project(document)
        current: dict[str, object] = dict(document)
        version = current["schemaVersion"]
        assert isinstance(version, int)
        while version < LATEST_PROJECT_SCHEMA_VERSION:
            current = _MIGRATIONS[version](current)
            next_version = current["schemaVersion"]
            assert isinstance(next_version, int)
            version = next_version
        self.validate_project(current)
        return current
