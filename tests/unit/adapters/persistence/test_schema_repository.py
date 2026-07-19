import json
from pathlib import Path

import pytest
from jsonschema.exceptions import ValidationError

from inductor_designer.adapters.persistence.schema_repository import (
    LATEST_PROJECT_SCHEMA_VERSION,
    SchemaRepository,
)

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures"


@pytest.fixture
def schema_repository() -> SchemaRepository:
    return SchemaRepository(Path("schemas"))


def _v1_document() -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "projectId": "3f0e8f5e-8f4e-4a5e-9d5b-6c4f2b1a0d9c",
        "metadata": {"name": "Legacy project"},
        "target": {"aedtRelease": "2025.2", "edition": "commercial"},
    }


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


@pytest.mark.parametrize("release", ["2024.2", "2025.1", "2099.2"])
def test_project_schema_accepts_supported_aedt_releases(release: str) -> None:
    document = json.loads(
        Path("tests/fixtures/projects/minimal-v1.inductor.json").read_text(encoding="utf-8")
    )
    document["target"]["aedtRelease"] = release

    SchemaRepository(Path("schemas")).validate_project(document)


@pytest.mark.parametrize("release", ["2024.1", "2023.2", "2100.1"])
def test_project_schema_rejects_aedt_releases_outside_supported_range(
    release: str,
) -> None:
    document = json.loads(
        Path("tests/fixtures/projects/minimal-v1.inductor.json").read_text(encoding="utf-8")
    )
    document["target"]["aedtRelease"] = release

    with pytest.raises(ValidationError):
        SchemaRepository(Path("schemas")).validate_project(document)


def test_latest_version_is_four() -> None:
    assert LATEST_PROJECT_SCHEMA_VERSION == 4


def test_v2_fixture_validates(schema_repository: SchemaRepository) -> None:
    document = json.loads((FIXTURES / "project.v2.json").read_text(encoding="utf-8"))
    schema_repository.validate_project(document)


def test_migrate_v1_to_v4(schema_repository: SchemaRepository) -> None:
    migrated = schema_repository.migrate_project(_v1_document())
    assert migrated["schemaVersion"] == 4
    assert migrated["core"] is None
    assert migrated["windings"] == []
    assert migrated["materials"] == []
    schema_repository.validate_project(migrated)


def test_migrate_v2_to_v4_adds_empty_materials(
    schema_repository: SchemaRepository,
) -> None:
    document = json.loads((FIXTURES / "project.v2.json").read_text(encoding="utf-8"))

    migrated = schema_repository.migrate_project(document)

    assert migrated["schemaVersion"] == 4
    assert migrated["materials"] == []
    schema_repository.validate_project(migrated)


def test_migrate_v3_to_v4_adds_null_bh_series_without_mutating_v3(
    schema_repository: SchemaRepository,
) -> None:
    document = json.loads(
        (FIXTURES / "sample_geometry_project.inductor.json").read_text(encoding="utf-8")
    )
    selection = {
        "ref": {"manufacturer": "Example", "name": "Ferrite", "grade": "F1"},
        "revisionId": "0123456789ab",
        "snapshot": {},
    }
    document["materials"] = [selection]

    migrated = schema_repository.migrate_project(document)

    assert migrated["schemaVersion"] == 4
    assert migrated["materials"] == [{**selection, "bhSeriesId": None}]
    assert "bhSeriesId" not in document["materials"][0]
    assert schema_repository.migrate_project(migrated) == migrated


def test_malformed_v3_material_fails_before_migration(
    schema_repository: SchemaRepository,
) -> None:
    document = json.loads(
        (FIXTURES / "sample_geometry_project.inductor.json").read_text(encoding="utf-8")
    )
    document["materials"] = ["not a mapping"]

    with pytest.raises(ValidationError):
        schema_repository.migrate_project(document)


def test_v4_material_selection_requires_bh_series_id(
    schema_repository: SchemaRepository,
) -> None:
    document = schema_repository.migrate_project(_v1_document())
    document["materials"] = [
        {
            "ref": {"manufacturer": "Example", "name": "Ferrite", "grade": "F1"},
            "revisionId": "0123456789ab",
            "snapshot": {},
        }
    ]

    with pytest.raises(ValidationError):
        schema_repository.validate_project(document)


@pytest.mark.parametrize("bh_series_id", [None, "bh-25c"])
def test_v4_material_selection_accepts_string_or_null_bh_series_id(
    schema_repository: SchemaRepository,
    bh_series_id: str | None,
) -> None:
    document = schema_repository.migrate_project(_v1_document())
    document["materials"] = [
        {
            "ref": {"manufacturer": "Example", "name": "Ferrite", "grade": "F1"},
            "revisionId": "0123456789ab",
            "bhSeriesId": bh_series_id,
            "snapshot": {},
        }
    ]

    schema_repository.validate_project(document)


def test_v4_material_selection_rejects_non_string_bh_series_id(
    schema_repository: SchemaRepository,
) -> None:
    document = schema_repository.migrate_project(_v1_document())
    document["materials"] = [
        {
            "ref": {"manufacturer": "Example", "name": "Ferrite", "grade": "F1"},
            "revisionId": "0123456789ab",
            "bhSeriesId": 25,
            "snapshot": {},
        }
    ]

    with pytest.raises(ValidationError):
        schema_repository.validate_project(document)


@pytest.mark.parametrize("revision_id", ["", "short", "0123456789AB", "0123456789ag"])
def test_v3_material_selection_requires_lowercase_hex_revision(
    schema_repository: SchemaRepository, revision_id: str
) -> None:
    document = json.loads(
        (FIXTURES / "sample_geometry_project.inductor.json").read_text(encoding="utf-8")
    )
    document["materials"] = [
        {
            "ref": {"manufacturer": "Example", "name": "Ferrite", "grade": "F1"},
            "revisionId": revision_id,
            "snapshot": {},
        }
    ]

    with pytest.raises(ValidationError):
        schema_repository.validate_project(document)
