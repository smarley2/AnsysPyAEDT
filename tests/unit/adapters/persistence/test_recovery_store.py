from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from inductor_designer.adapters.persistence.project_repository import ProjectRepository
from inductor_designer.adapters.persistence.recovery_store import (
    RECOVERY_DOCUMENT_FILENAME,
    RECOVERY_INDEX_FILENAME,
    RecoveryStore,
)
from inductor_designer.adapters.persistence.schema_repository import SchemaRepository
from tests.unit.domain.test_project import make_project

NOW = datetime(2026, 8, 18, 10, 15, 0, tzinfo=timezone.utc)


def _store(tmp_path: Path) -> RecoveryStore:
    return RecoveryStore(
        tmp_path / "recovery", ProjectRepository(SchemaRepository(Path("schemas")))
    )


def test_nothing_written_reads_as_no_snapshot(tmp_path: Path) -> None:
    assert _store(tmp_path).read() is None


def test_write_then_read_round_trips_the_project(tmp_path: Path) -> None:
    store = _store(tmp_path)
    document_path = tmp_path / "boost.inductor.json"
    project = replace(make_project(), description="unsaved edit")

    snapshot = store.write(project, document_path, now=NOW)

    assert snapshot.document_path == document_path
    assert snapshot.saved_at_utc == "2026-08-18T10:15:00+00:00"
    assert snapshot.project_path.name == RECOVERY_DOCUMENT_FILENAME
    reread = store.read()
    assert reread is not None
    assert store.load_project(reread).description == "unsaved edit"


def test_an_unsaved_project_records_no_document_path(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.write(make_project(), None, now=NOW)

    snapshot = store.read()
    assert snapshot is not None
    assert snapshot.document_path is None


def test_write_overwrites_the_previous_snapshot(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.write(replace(make_project(), description="old"), None, now=NOW)
    store.write(replace(make_project(), description="new"), None, now=NOW)

    snapshot = store.read()
    assert snapshot is not None
    assert store.load_project(snapshot).description == "new"


def test_a_non_finite_value_is_refused_and_leaves_the_old_snapshot(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    store.write(replace(make_project(), description="good"), None, now=NOW)
    good = make_project()
    # `min_spacing_m` has no domain-level finiteness guard (see
    # test_project_repository.py's own non-finite tests), so this is what
    # actually reaches schema validation instead of being rejected at
    # construction time the way OperatingPoint.frequency_hz now is.
    broken = replace(
        good,
        design=replace(
            good.design,
            windings=(
                replace(good.design.windings[0], min_spacing_m=float("nan")),
                *good.design.windings[1:],
            ),
        ),
    )
    # A different moment than the good write's: the module docstring's safety
    # mechanism is writing the document BEFORE the index, so a broken write
    # that fails validation never reaches the index at all. Reusing `NOW` for
    # both writes would let the index get overwritten first (the ordering bug
    # MINOR 7 describes) without this test noticing, because the timestamp
    # would happen to match either way.
    later = NOW.replace(hour=NOW.hour + 1)

    with pytest.raises(ValueError):
        store.write(broken, None, now=later)

    snapshot = store.read()
    assert snapshot is not None
    assert store.load_project(snapshot).description == "good"
    assert snapshot.saved_at_utc == NOW.isoformat()


def test_a_corrupt_index_reads_as_no_snapshot(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.write(make_project(), None, now=NOW)
    (tmp_path / "recovery" / RECOVERY_INDEX_FILENAME).write_text(
        "not json", encoding="utf-8"
    )

    assert store.read() is None


def test_clear_removes_both_files(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.write(make_project(), None, now=NOW)

    store.clear()

    assert store.read() is None
    assert not (tmp_path / "recovery" / RECOVERY_DOCUMENT_FILENAME).exists()
    assert not (tmp_path / "recovery" / RECOVERY_INDEX_FILENAME).exists()


def test_the_index_records_the_document_path_as_written(tmp_path: Path) -> None:
    store = _store(tmp_path)
    document_path = tmp_path / "boost.inductor.json"
    store.write(make_project(), document_path, now=NOW)

    index = json.loads(
        (tmp_path / "recovery" / RECOVERY_INDEX_FILENAME).read_text(encoding="utf-8")
    )
    assert index["documentPath"] == str(document_path)
    assert index["savedAtUtc"] == "2026-08-18T10:15:00+00:00"


def test_a_missing_document_with_a_valid_index_reads_as_no_snapshot(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    store.write(make_project(), None, now=NOW)
    store.document_path.unlink()

    assert store.read() is None


def test_a_crash_replacing_the_index_leaves_the_previous_index_intact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The index must get the same mkstemp + os.replace treatment as the
    document (`ProjectRepository.save`), or a crash mid-write silently
    discards an otherwise-valid snapshot. `os.replace` is shared by both
    writes, so the first call (the document's) is left real and only the
    second (the index's) is made to fail -- isolating the index write without
    also breaking the document write that must precede it."""
    import os as os_module

    store = _store(tmp_path)
    store.write(replace(make_project(), description="old"), None, now=NOW)
    original_index = (tmp_path / "recovery" / RECOVERY_INDEX_FILENAME).read_text(
        encoding="utf-8"
    )
    real_replace = os_module.replace
    calls = {"count": 0}

    def fragile_replace(source: object, destination: object) -> None:
        calls["count"] += 1
        if calls["count"] == 1:
            real_replace(source, destination)
            return
        raise OSError("crash mid-replace")

    monkeypatch.setattr(os_module, "replace", fragile_replace)

    with pytest.raises(OSError):
        store.write(replace(make_project(), description="new"), None, now=NOW)

    assert (
        tmp_path / "recovery" / RECOVERY_INDEX_FILENAME
    ).read_text(encoding="utf-8") == original_index
