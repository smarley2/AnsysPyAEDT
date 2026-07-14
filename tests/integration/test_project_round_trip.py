from __future__ import annotations

import dataclasses
import json
import sqlite3
from pathlib import Path

import pytest

from inductor_designer.adapters.catalog.sqlite_repository import SqliteCatalogRepository
from inductor_designer.adapters.persistence.project_repository import ProjectRepository
from inductor_designer.adapters.persistence.record_serde import (
    core_record_from_json,
    core_record_to_json,
)
from inductor_designer.adapters.persistence.schema_repository import SchemaRepository
from inductor_designer.application.services.catalog_revisions import (
    SnapshotStatus,
    adopt_core_revision,
    compare_core_snapshot,
    select_core,
)
from inductor_designer.domain.aedt_target import AedtEdition, AedtRelease, ModelDimension
from inductor_designer.domain.project import CatalogCoreSelection, InductorProject
from inductor_designer.domain.validation import ValidationCategory, validate_project
from inductor_designer.domain.winding import (
    ConductorMode,
    CurrentDirection,
    WindingDefinition,
    WindingDirection,
)
from tools.build_catalog import build

ROOT = Path(__file__).resolve().parents[2]


def make_winding(winding_id: str, start_angle_deg: float) -> WindingDefinition:
    return WindingDefinition(
        winding_id=winding_id,
        label=winding_id,
        turns=15,
        conductor_name="AWG 18",
        mode=ConductorMode.SOLID,
        start_angle_deg=start_angle_deg,
        sector_deg=150.0,
        min_spacing_m=0.0002,
        min_clearance_m=0.001,
        winding_direction=WindingDirection.CLOCKWISE,
        current_direction=CurrentDirection.FORWARD,
        terminal_intent="",
        ac_magnitude_a=2.0,
        ac_phase_deg=0.0,
        frequency_hz=100_000.0,
        dc_current_a=5.0,
    )


def test_milestone_1_exit_criterion(tmp_path: Path) -> None:
    index = tmp_path / "catalog.sqlite"
    build(ROOT / "catalog", ROOT / "schemas" / "catalog", index)
    catalog = SqliteCatalogRepository(index)

    empty = InductorProject(
        project_id="3f0e8f5e-8f4e-4a5e-9d5b-6c4f2b1a0d9c",
        name="M1 exit project",
        description="",
        target_release=AedtRelease(2025, 2),
        target_edition=AedtEdition.COMMERCIAL,
        dimension_mode=ModelDimension.THREE_D,
        core=None,
        windings=(),
    )
    project = select_core(empty, catalog, "0077071A7")
    project = dataclasses.replace(
        project, windings=(make_winding("w1", 0.0), make_winding("w2", 180.0))
    )

    issues = validate_project(project, known_conductors=catalog.list_conductor_names())
    assert not [i for i in issues if i.category is ValidationCategory.ERROR]

    repo = ProjectRepository(SchemaRepository(ROOT / "schemas"))
    path = tmp_path / "exit.inductor.json"
    repo.save(project, path)
    assert repo.load(path) == project

    comparison = compare_core_snapshot(project, catalog)
    assert comparison is not None and comparison.status is SnapshotStatus.UNCHANGED

    with sqlite3.connect(index) as connection:
        row = connection.execute(
            "SELECT record_json FROM cores WHERE part_number = ?", ("0077071A7",)
        ).fetchone()
        record = core_record_from_json(json.loads(row[0]))
        changed = dataclasses.replace(record, al_value_nh=record.al_value_nh + 5.0)
        connection.execute(
            "UPDATE cores SET record_json = ? WHERE part_number = ?",
            (json.dumps(core_record_to_json(changed), sort_keys=True), "0077071A7"),
        )
        connection.commit()

    comparison = compare_core_snapshot(project, catalog)
    assert comparison is not None and comparison.status is SnapshotStatus.CHANGED

    adopted = adopt_core_revision(project, catalog)
    assert isinstance(adopted.core, CatalogCoreSelection)
    assert adopted.core.snapshot.al_value_nh == pytest.approx(record.al_value_nh + 5.0)
    repo.save(adopted, path)
    assert repo.load(path) == adopted
