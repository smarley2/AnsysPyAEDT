from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from inductor_designer.adapters.persistence.project_repository import (
    ProjectRepository,
    project_from_document,
    project_to_document,
)
from inductor_designer.adapters.persistence.schema_repository import SchemaRepository
from inductor_designer.domain.project import (
    Design,
    ManualCoreSelection,
    MaterialRevisionSelection,
    WindingOperatingPoint,
)
from tests.unit.domain.test_project import (
    make_material_series,
    make_operating_point,
    make_project,
    make_winding,
    material_record_with_series,
)

SCHEMAS = Path(__file__).resolve().parents[4] / "schemas"
FIXTURES = Path(__file__).resolve().parents[3] / "fixtures"


def repository() -> ProjectRepository:
    return ProjectRepository(SchemaRepository(SCHEMAS))


def test_document_round_trip_preserves_project() -> None:
    design = Design(
        core=make_project().design.core,
        windings=(
            make_winding(winding_id="w1"),
            make_winding(winding_id="w2", start_angle_deg=180.0),
        ),
        core_material=None,
        manual_material_compatibility_acknowledged=False,
    )
    project = make_project(
        design=design,
        operating_point=make_operating_point(
            make_operating_point().windings[0],
            WindingOperatingPoint(
                winding_id="w2",
                ac_rms_current_a=2.0,
                ac_phase_deg=0.0,
                dc_current_a=5.0,
                current_direction=make_operating_point().windings[0].current_direction,
            ),
        ),
    )

    assert project_from_document(project_to_document(project)) == project


def test_document_has_only_v5_design_operating_point_and_recipe_fields() -> None:
    document = project_to_document(make_project())

    assert document["schemaVersion"] == 5
    assert set(document) == {
        "schemaVersion",
        "projectId",
        "metadata",
        "design",
        "operatingPoint",
        "simulationRecipe",
    }
    assert "target" not in document
    assert "materials" not in document
    assert "frequencyHz" not in document["design"]["windings"][0]  # type: ignore[index]


def test_pinned_material_snapshot_round_trips_byte_identically(tmp_path: Path) -> None:
    snapshot = material_record_with_series(make_material_series())
    material = MaterialRevisionSelection(
        snapshot.ref,
        snapshot.revision_id,
        snapshot,
        bh_series_id="bh-25c",
    )
    original = make_project(
        design=Design(
            core=make_project().design.core,
            windings=make_project().design.windings,
            core_material=material,
            manual_material_compatibility_acknowledged=False,
        )
    )
    repo = repository()
    first = tmp_path / "first.inductor.json"
    second = tmp_path / "second.inductor.json"

    repo.save(original, first)
    restored = repo.load(first)
    repo.save(restored, second)
    document = json.loads(first.read_text(encoding="utf-8"))

    assert restored == original
    assert first.read_bytes() == second.read_bytes()
    assert document["design"]["coreMaterial"]["bhSeriesId"] == "bh-25c"  # type: ignore[index]
    assert document["design"]["coreMaterial"]["snapshot"]["status"] == "approved"  # type: ignore[index]


def test_fixture_maps_to_domain() -> None:
    document = json.loads((FIXTURES / "sample_geometry_project.inductor.json").read_text())
    project = project_from_document(document)

    assert project.design.windings[0].conductor_name == "AWG 18"
    assert project.operating_point.windings[0].ac_rms_current_a == 2.0


def test_save_and_load_round_trip(tmp_path: Path) -> None:
    repo = repository()
    project = make_project()
    path = tmp_path / "boost.inductor.json"

    repo.save(project, path)

    assert repo.load(path) == project


def test_save_and_load_round_trip_manual_core(tmp_path: Path) -> None:
    repo = repository()
    project = make_project(
        design=Design(
            core=ManualCoreSelection(0.0269, 0.0147, 0.0112, 0.0),
            windings=make_project().design.windings,
            core_material=None,
            manual_material_compatibility_acknowledged=False,
        )
    )
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


def test_save_replace_failure_preserves_existing_file_and_cleans_temp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = repository()
    path = tmp_path / "existing.inductor.json"
    repo.save(make_project(), path)
    original = path.read_bytes()

    def reject_replace(source: str | bytes, destination: str | bytes) -> None:
        raise OSError("injected replace failure")

    monkeypatch.setattr(os, "replace", reject_replace)

    with pytest.raises(OSError, match="injected replace failure"):
        repo.save(make_project(name="Updated project"), path)

    assert path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize("version", [1, 2, 3, 4])
def test_load_rejects_legacy_project_versions(tmp_path: Path, version: int) -> None:
    path = tmp_path / f"legacy-v{version}.inductor.json"
    path.write_text(json.dumps({"schemaVersion": version}), encoding="utf-8")

    with pytest.raises(
        ValueError,
        match=rf"Unsupported project schema version: {version}; expected 5",
    ):
        repository().load(path)
