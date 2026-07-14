from __future__ import annotations

import json
from pathlib import Path

from inductor_designer.adapters.persistence.project_repository import (
    ProjectRepository,
    project_from_document,
    project_to_document,
)
from inductor_designer.adapters.persistence.schema_repository import SchemaRepository
from inductor_designer.domain.project import ManualCoreSelection
from tests.unit.domain.test_project import make_project, make_winding

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
