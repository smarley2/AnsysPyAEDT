from __future__ import annotations

import dataclasses

import pytest

from inductor_designer.application.services.catalog_revisions import (
    SnapshotStatus,
    adopt_core_revision,
    compare_core_snapshot,
    select_core,
)
from inductor_designer.domain.catalog_records import ConductorRecord, CoreRecord
from inductor_designer.domain.project import CatalogCoreSelection
from tests.unit.domain.test_catalog_records import make_core
from tests.unit.domain.test_project import make_project


class FakeCatalog:
    def __init__(self, cores: dict[str, CoreRecord]) -> None:
        self._cores = cores

    def get_core(self, part_number: str) -> CoreRecord | None:
        return self._cores.get(part_number)

    def list_cores(self) -> tuple[CoreRecord, ...]:
        return tuple(self._cores.values())

    def get_conductor(self, name: str) -> ConductorRecord | None:
        return None

    def list_conductor_names(self) -> tuple[str, ...]:
        return ()


def test_select_core_snapshots_current_record() -> None:
    catalog = FakeCatalog({"0077071A7": make_core()})
    project = select_core(make_project(core=None), catalog, "0077071A7")
    assert isinstance(project.core, CatalogCoreSelection)
    assert project.core.snapshot == make_core()
    assert project.core.overrides == ()


def test_select_core_unknown_part_raises() -> None:
    with pytest.raises(LookupError, match="0099999A9"):
        select_core(make_project(core=None), FakeCatalog({}), "0099999A9")


def test_compare_unchanged() -> None:
    catalog = FakeCatalog({"0077071A7": make_core()})
    comparison = compare_core_snapshot(make_project(), catalog)
    assert comparison is not None
    assert comparison.status is SnapshotStatus.UNCHANGED
    assert comparison.changes == ()


def test_compare_detects_changed_field() -> None:
    changed = dataclasses.replace(make_core(), al_value_nh=56.0)
    comparison = compare_core_snapshot(make_project(), FakeCatalog({"0077071A7": changed}))
    assert comparison is not None
    assert comparison.status is SnapshotStatus.CHANGED
    assert any(change.field == "al_value_nh" for change in comparison.changes)


def test_compare_missing_part() -> None:
    comparison = compare_core_snapshot(make_project(), FakeCatalog({}))
    assert comparison is not None
    assert comparison.status is SnapshotStatus.MISSING


def test_compare_returns_none_without_catalog_selection() -> None:
    catalog = FakeCatalog({"0077071A7": make_core()})
    assert compare_core_snapshot(make_project(core=None), catalog) is None


def test_adopt_rewrites_snapshot_and_keeps_overrides() -> None:
    changed = dataclasses.replace(make_core(), al_value_nh=56.0)
    adopted = adopt_core_revision(make_project(), FakeCatalog({"0077071A7": changed}))
    assert isinstance(adopted.core, CatalogCoreSelection)
    assert adopted.core.snapshot.al_value_nh == 56.0


def test_adopt_missing_part_raises() -> None:
    with pytest.raises(LookupError, match="0077071A7"):
        adopt_core_revision(make_project(), FakeCatalog({}))
