from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

LATEST_PROJECT_SCHEMA_VERSION = 5


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
        if version != LATEST_PROJECT_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported project schema version: {version}; "
                f"expected {LATEST_PROJECT_SCHEMA_VERSION}"
            )
        schema = self.load_project_schema(LATEST_PROJECT_SCHEMA_VERSION)
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(document)
