from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema.exceptions import ValidationError

from inductor_designer.adapters.persistence.project_repository import project_to_document
from inductor_designer.adapters.persistence.schema_repository import (
    LATEST_PROJECT_SCHEMA_VERSION,
    SchemaRepository,
)
from tests.unit.domain.test_project import make_project

SCHEMAS = Path(__file__).resolve().parents[4] / "schemas"


@pytest.fixture
def schema_repository() -> SchemaRepository:
    return SchemaRepository(SCHEMAS)


def test_latest_version_is_five() -> None:
    assert LATEST_PROJECT_SCHEMA_VERSION == 5


def test_v5_project_validates(schema_repository: SchemaRepository) -> None:
    schema_repository.validate_project(project_to_document(make_project()))


@pytest.mark.parametrize("version", [1, 2, 3, 4])
def test_legacy_project_versions_are_rejected(version: int) -> None:
    with pytest.raises(
        ValueError,
        match=rf"Unsupported project schema version: {version}; expected 5",
    ):
        SchemaRepository(SCHEMAS).validate_project({"schemaVersion": version})


def test_unknown_project_version_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unsupported project schema version: 99; expected 5"):
        SchemaRepository(SCHEMAS).validate_project({"schemaVersion": 99})


def test_v5_rejects_legacy_top_level_fields(schema_repository: SchemaRepository) -> None:
    document = project_to_document(make_project())
    document["target"] = {}

    with pytest.raises(ValidationError):
        schema_repository.validate_project(document)


def test_v5_requires_operating_point_current_direction(
    schema_repository: SchemaRepository,
) -> None:
    document = project_to_document(make_project())
    del document["operatingPoint"]["windings"][0]["currentDirection"]  # type: ignore[index]

    with pytest.raises(ValidationError):
        schema_repository.validate_project(document)


def test_sample_fixture_is_v5(schema_repository: SchemaRepository) -> None:
    fixture = SCHEMAS.parents[0] / "tests" / "fixtures" / "sample_geometry_project.inductor.json"
    document = json.loads(fixture.read_text(encoding="utf-8"))

    schema_repository.validate_project(document)
