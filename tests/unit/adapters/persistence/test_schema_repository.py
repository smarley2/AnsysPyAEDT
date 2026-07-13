import json
from pathlib import Path

import pytest
from jsonschema.exceptions import ValidationError

from inductor_designer.adapters.persistence.schema_repository import SchemaRepository


def test_minimal_v1_project_is_valid() -> None:
    document = json.loads(
        Path("tests/fixtures/projects/minimal-v1.inductor.json").read_text(encoding="utf-8")
    )
    SchemaRepository(Path("schemas")).validate_project(document)


def test_unknown_project_version_is_rejected() -> None:
    repository = SchemaRepository(Path("schemas"))

    with pytest.raises(ValueError, match="Unsupported project schema version: 99"):
        repository.validate_project({"schemaVersion": 99})


def test_missing_project_identifier_is_rejected() -> None:
    repository = SchemaRepository(Path("schemas"))

    with pytest.raises(ValidationError):
        repository.validate_project(
            {
                "schemaVersion": 1,
                "metadata": {"name": "Missing identifier"},
                "target": {"aedtRelease": "2024.2", "edition": "commercial"},
            }
        )
