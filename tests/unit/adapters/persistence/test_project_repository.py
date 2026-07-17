from __future__ import annotations

import json
from pathlib import Path

from inductor_designer.adapters.persistence.project_repository import (
    ProjectRepository,
    project_from_document,
    project_to_document,
)
from inductor_designer.adapters.persistence.schema_repository import SchemaRepository
from inductor_designer.domain.project import ManualCoreSelection, MaterialRevisionSelection
from tests.unit.domain.test_project import make_material_record, make_project, make_winding

SCHEMAS = Path(__file__).resolve().parents[4] / "schemas"
FIXTURES = Path(__file__).resolve().parents[3] / "fixtures"


def repository() -> ProjectRepository:
    return ProjectRepository(SchemaRepository(SCHEMAS))


def test_document_round_trip_preserves_project() -> None:
    project = make_project(
        windings=(
            make_winding(winding_id="w1"),
            make_winding(winding_id="w2", start_angle_deg=180.0),
        )
    )
    assert project_from_document(project_to_document(project)) == project


def test_approved_material_snapshot_round_trips_byte_identically(tmp_path: Path) -> None:
    snapshot = make_material_record()
    project = make_project(
        materials=(MaterialRevisionSelection(snapshot.ref, snapshot.revision_id, snapshot),)
    )
    repo = repository()
    first = tmp_path / "first.inductor.json"
    second = tmp_path / "second.inductor.json"

    repo.save(project, first)
    restored_project = repo.load(first)
    repo.save(restored_project, second)
    document = json.loads(first.read_text(encoding="utf-8"))

    assert restored_project == project
    assert first.read_bytes() == second.read_bytes()
    assert document["schemaVersion"] == 3
    assert document["materials"][0]["snapshot"]["status"] == "approved"


def test_fixture_maps_to_domain() -> None:
    document = json.loads((FIXTURES / "project.v2.json").read_text(encoding="utf-8"))
    project = project_from_document(document)
    assert project.windings[0].conductor_name == "AWG 18"


def test_save_and_load_round_trip(tmp_path: Path) -> None:
    repo = repository()
    project = make_project()
    path = tmp_path / "boost.inductor.json"
    repo.save(project, path)
    assert repo.load(path) == project


def test_save_and_load_round_trip_manual_core(tmp_path: Path) -> None:
    repo = repository()
    project = make_project(core=ManualCoreSelection(0.0269, 0.0147, 0.0112, 0.0))
    path = tmp_path / "manual-core.inductor.json"
    repo.save(project, path)
    assert repo.load(path) == project


def test_save_is_deterministic(tmp_path: Path) -> None:
    repo = repository()
    project = make_project()
    first, second = tmp_path / "a.inductor.json", tmp_path / "b.inductor.json"
    repo.save(project, first)
    repo.save(project, second)
    assert first.read_bytes() == second.read_bytes()


def test_sample_fixture_save_is_byte_identical(tmp_path: Path) -> None:
    source = FIXTURES / "sample_geometry_project.inductor.json"
    saved = tmp_path / source.name

    repository().save(repository().load(source), saved)

    assert saved.read_bytes() == source.read_bytes()


def test_load_migrates_v1_documents(tmp_path: Path) -> None:
    v1 = {
        "schemaVersion": 1,
        "projectId": "3f0e8f5e-8f4e-4a5e-9d5b-6c4f2b1a0d9c",
        "metadata": {"name": "Legacy"},
        "target": {"aedtRelease": "2025.2", "edition": "commercial"},
    }
    path = tmp_path / "legacy.inductor.json"
    path.write_text(json.dumps(v1), encoding="utf-8")
    project = repository().load(path)
    assert project.core is None
    assert project.windings == ()
    assert project.materials == ()


def test_load_migrates_v2_documents_with_empty_materials(tmp_path: Path) -> None:
    source = FIXTURES / "project.v2.json"
    path = tmp_path / source.name
    path.write_bytes(source.read_bytes())

    project = repository().load(path)

    assert project.materials == ()
