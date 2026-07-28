from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
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
from inductor_designer.domain.project import CatalogCoreSelection
from inductor_designer.domain.validation import ValidationCategory, validate_project
from tests.unit.domain.test_project import (
    make_operating_point,
    make_project,
    make_winding,
)
from tools.build_catalog import build

ROOT = Path(__file__).resolve().parents[2]


def test_milestone_1_exit_criterion(tmp_path: Path) -> None:
    index = tmp_path / "catalog.sqlite"
    build(ROOT / "catalog", ROOT / "schemas" / "catalog", index)
    catalog = SqliteCatalogRepository(index)

    project = select_core(make_project(), catalog, "0077071A7")
    second_winding = make_winding(
        winding_id="w2",
        label="w2",
        start_angle_deg=180.0,
    )
    first_operating_point = project.operating_point.windings[0]
    project = replace(
        project,
        design=replace(
            project.design,
            windings=(project.design.windings[0], second_winding),
        ),
        operating_point=make_operating_point(
            first_operating_point,
            replace(first_operating_point, winding_id="w2"),
        ),
    )

    issues = validate_project(
        project,
        known_conductors=catalog.list_conductor_names(),
    )
    assert not [issue for issue in issues if issue.category is ValidationCategory.ERROR]

    repository = ProjectRepository(SchemaRepository(ROOT / "schemas"))
    path = tmp_path / "exit.inductor.json"
    repository.save(project, path)
    assert repository.load(path) == project

    comparison = compare_core_snapshot(project, catalog)
    assert comparison is not None and comparison.status is SnapshotStatus.UNCHANGED

    with sqlite3.connect(index) as connection:
        row = connection.execute(
            "SELECT record_json FROM cores WHERE part_number = ?",
            ("0077071A7",),
        ).fetchone()
        assert row is not None
        record = core_record_from_json(json.loads(row[0]))
        changed = replace(record, al_value_nh=record.al_value_nh + 5.0)
        connection.execute(
            "UPDATE cores SET record_json = ? WHERE part_number = ?",
            (
                json.dumps(core_record_to_json(changed), sort_keys=True),
                "0077071A7",
            ),
        )
        connection.commit()

    comparison = compare_core_snapshot(project, catalog)
    assert comparison is not None and comparison.status is SnapshotStatus.CHANGED

    adopted = adopt_core_revision(project, catalog)
    assert isinstance(adopted.design.core, CatalogCoreSelection)
    assert adopted.design.core.snapshot.al_value_nh == pytest.approx(
        record.al_value_nh + 5.0
    )
    repository.save(adopted, path)
    assert repository.load(path) == adopted
