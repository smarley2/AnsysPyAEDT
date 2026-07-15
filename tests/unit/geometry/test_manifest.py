from __future__ import annotations

import json
from pathlib import Path

from inductor_designer.adapters.catalog.sqlite_repository import SqliteCatalogRepository
from inductor_designer.adapters.persistence.project_repository import ProjectRepository
from inductor_designer.adapters.persistence.schema_repository import SchemaRepository
from inductor_designer.application.services.geometry_model import build_geometry_model
from inductor_designer.geometry.manifest import build_manifest, manifest_json
from tests.unit.application.test_geometry_model import CATALOG
from tests.unit.domain.test_project import make_project, make_winding
from tools.build_catalog import build

ROOT = Path(__file__).resolve().parents[3]
GOLDEN = ROOT / "tests" / "golden" / "sample_geometry_manifest.json"


def two_winding_project() -> object:
    return make_project(
        windings=(
            make_winding(winding_id="w1", start_angle_deg=0.0, sector_deg=150.0, turns=10),
            make_winding(winding_id="w2", start_angle_deg=180.0, sector_deg=150.0, turns=10),
        )
    )


def test_manifest_structure() -> None:
    model = build_geometry_model(two_winding_project(), CATALOG)  # type: ignore[arg-type]
    manifest = build_manifest(model)
    assert manifest["schemaVersion"] == 1
    core = manifest["core"]
    assert core["name"] == "Core"  # type: ignore[index]
    windings = manifest["windings"]
    assert [w["windingId"] for w in windings] == ["w1", "w2"]  # type: ignore[index]
    w1 = windings[0]  # type: ignore[index]
    assert len(w1["layers"][0]["turnNames"]) == 10
    assert w1["layers"][0]["turnNames"][0] == "w1_L01_T001"
    assert manifest["symmetry"] is not None
    assert manifest["symmetryRefusal"] is None
    assert manifest["collisions"] == []
    assert manifest["planar"]["conductorCount"] == 40  # type: ignore[index]


def test_manifest_json_deterministic() -> None:
    model_a = build_geometry_model(two_winding_project(), CATALOG)  # type: ignore[arg-type]
    model_b = build_geometry_model(two_winding_project(), CATALOG)  # type: ignore[arg-type]
    assert manifest_json(model_a) == manifest_json(model_b)
    parsed = json.loads(manifest_json(model_a))
    assert parsed == json.loads(manifest_json(model_a))


def test_golden_manifest(tmp_path: Path) -> None:
    index = tmp_path / "catalog.sqlite"
    build(ROOT / "catalog", ROOT / "schemas" / "catalog", index)
    catalog = SqliteCatalogRepository(index)
    repo = ProjectRepository(SchemaRepository(ROOT / "schemas"))
    project = repo.load(ROOT / "tests" / "fixtures" / "sample_geometry_project.inductor.json")
    model = build_geometry_model(project, catalog)
    assert manifest_json(model) == GOLDEN.read_text(encoding="utf-8")
