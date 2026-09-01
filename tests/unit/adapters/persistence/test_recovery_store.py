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
    assert _store(tmp_path).read(None) is None


def test_write_then_read_round_trips_the_project(tmp_path: Path) -> None:
    store = _store(tmp_path)
    document_path = tmp_path / "boost.inductor.json"
    project = replace(make_project(), description="unsaved edit")

    snapshot = store.write(project, document_path, now=NOW)

    assert snapshot.document_path == document_path
    assert snapshot.saved_at_utc == "2026-08-18T10:15:00+00:00"
    assert snapshot.project_path.name.endswith(RECOVERY_DOCUMENT_FILENAME)
    reread = store.read(document_path)
    assert reread is not None
    assert store.load_project(reread).description == "unsaved edit"


def test_an_unsaved_project_records_no_document_path(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.write(make_project(), None, now=NOW)

    snapshot = store.read(None)
    assert snapshot is not None
    assert snapshot.document_path is None


def test_write_overwrites_the_previous_snapshot(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.write(replace(make_project(), description="old"), None, now=NOW)
    store.write(replace(make_project(), description="new"), None, now=NOW)

    snapshot = store.read(None)
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

    snapshot = store.read(None)
    assert snapshot is not None
    assert store.load_project(snapshot).description == "good"
    assert snapshot.saved_at_utc == NOW.isoformat()


def test_a_corrupt_index_reads_as_no_snapshot(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.write(make_project(), None, now=NOW)
    store.slot_for(None).index_path.write_text("not json", encoding="utf-8")

    assert store.read(None) is None


def test_clear_removes_both_files(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.write(make_project(), None, now=NOW)
    slot = store.slot_for(None)

    store.clear(None)

    assert store.read(None) is None
    assert not slot.document_path.exists()
    assert not slot.index_path.exists()


def test_the_index_records_the_document_path_as_written(tmp_path: Path) -> None:
    store = _store(tmp_path)
    document_path = tmp_path / "boost.inductor.json"
    store.write(make_project(), document_path, now=NOW)

    index = json.loads(
        store.slot_for(document_path).index_path.read_text(encoding="utf-8")
    )
    assert index["documentPath"] == str(document_path)
    assert index["savedAtUtc"] == "2026-08-18T10:15:00+00:00"


def test_a_missing_document_with_a_valid_index_reads_as_no_snapshot(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    store.write(make_project(), None, now=NOW)
    store.slot_for(None).document_path.unlink()

    assert store.read(None) is None


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
    original_index = store.slot_for(None).index_path.read_text(encoding="utf-8")
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

    assert store.slot_for(None).index_path.read_text(encoding="utf-8") == original_index


def test_two_documents_do_not_share_one_slot(tmp_path: Path) -> None:
    """The defect this task exists for: one global slot meant the second
    project's autosave overwrote the first's, and because the recovery offer
    only fires when the document path matches, the first project's unsaved
    work was not even offered -- it was gone."""
    store = _store(tmp_path)
    first = tmp_path / "a" / "boost.inductor.json"
    second = tmp_path / "b" / "boost.inductor.json"

    store.write(replace(make_project(), description="first"), first, now=NOW)
    store.write(replace(make_project(), description="second"), second, now=NOW)

    assert store.load_project(store.read(first)).description == "first"
    assert store.load_project(store.read(second)).description == "second"


def test_the_same_document_by_two_spellings_is_one_slot(tmp_path: Path) -> None:
    """`main.py` passes `args.project` unresolved, so a relative launch and an
    absolute one must not produce two snapshots of one project."""
    store = _store(tmp_path)
    absolute = tmp_path / "a" / "boost.inductor.json"
    # Same file, spelled differently: resolving collapses the `..` back to
    # the same path `absolute` already is.
    respelled = tmp_path / "a" / ".." / "a" / "boost.inductor.json"

    store.write(replace(make_project(), description="only spelling"), absolute, now=NOW)

    snapshot = store.read(respelled)
    assert snapshot is not None
    assert store.load_project(snapshot).description == "only spelling"


def test_clearing_one_slot_leaves_the_other(tmp_path: Path) -> None:
    """A save in one window must not discard the other window's recovery copy."""
    store = _store(tmp_path)
    first = tmp_path / "a" / "boost.inductor.json"
    second = tmp_path / "b" / "boost.inductor.json"
    store.write(replace(make_project(), description="first"), first, now=NOW)
    store.write(replace(make_project(), description="second"), second, now=NOW)

    store.clear(first)

    assert store.read(first) is None
    reread = store.read(second)
    assert reread is not None
    assert store.load_project(reread).description == "second"


def test_an_unsaved_project_keeps_its_own_reserved_slot(tmp_path: Path) -> None:
    """`document_path is None` has nothing to key on; it must still not collide
    with a saved project's slot."""
    store = _store(tmp_path)
    saved = tmp_path / "boost.inductor.json"
    store.write(replace(make_project(), description="saved project"), saved, now=NOW)
    store.write(replace(make_project(), description="unsaved project"), None, now=NOW)

    saved_snapshot = store.read(saved)
    unsaved_snapshot = store.read(None)
    assert saved_snapshot is not None
    assert unsaved_snapshot is not None
    assert store.load_project(saved_snapshot).description == "saved project"
    assert store.load_project(unsaved_snapshot).description == "unsaved project"


def test_slot_filenames_do_not_contain_the_document_path(tmp_path: Path) -> None:
    """This directory sits next to the log directory the diagnostic bundle
    collects from, and nothing here redacts a filename -- the digest keeps the
    path itself out of it."""
    store = _store(tmp_path)
    document_path = tmp_path / "secret-project-name" / "boost.inductor.json"

    store.write(make_project(), document_path, now=NOW)

    slot = store.slot_for(document_path)
    assert "secret-project-name" not in slot.index_path.name
    assert "secret-project-name" not in slot.document_path.name
    assert RECOVERY_INDEX_FILENAME in slot.index_path.name
