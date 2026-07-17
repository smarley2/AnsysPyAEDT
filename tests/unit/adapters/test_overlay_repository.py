from __future__ import annotations

import json
import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from inductor_designer.adapters.materials import overlay_repository
from inductor_designer.adapters.materials.overlay_repository import (
    FileOverlayMaterialRepository,
)
from inductor_designer.materials.records import MaterialStatus
from inductor_designer.materials.serde import (
    material_record_to_json,
    points_csv,
    sha256_hex,
)
from tests.contract.test_material_repository_contract import _record


def test_save_uses_sanitized_layout(tmp_path: Path) -> None:
    source = b"h,b\n0,0\n100,0.2\n"
    record = _record(source, revision_id="123456789abc")
    repository = FileOverlayMaterialRepository(tmp_path)

    repository.save(record, {"bh-source.csv": source})

    revision = tmp_path / "ACME_Materials" / "Test_Ferrite" / "N_87" / "W123456789abc"
    assert (revision / "record.json").is_file()
    assert (revision / "points-bh_room_temperature.csv").read_text() == points_csv(
        record.series[0]
    )
    assert (revision / "sources" / "bh_source_csv").read_bytes() == source


def test_get_rejects_tampered_source(tmp_path: Path) -> None:
    source = b"h,b\n0,0\n100,0.2\n"
    record = _record(source)
    repository = FileOverlayMaterialRepository(tmp_path)
    repository.save(record, {"bh-source.csv": source})
    source_path = (
        tmp_path
        / "ACME_Materials"
        / "Test_Ferrite"
        / "N_87"
        / "abcdef123456"
        / "sources"
        / "bh_source_csv"
    )
    source_path.write_bytes(b"tampered")

    with pytest.raises(ValueError, match="sha256.*bh-source.csv"):
        repository.get(record.ref, record.revision_id)


def test_get_rejects_csv_json_point_disagreement(tmp_path: Path) -> None:
    source = b"h,b\n0,0\n100,0.2\n"
    record = _record(source)
    repository = FileOverlayMaterialRepository(tmp_path)
    repository.save(record, {"bh-source.csv": source})
    csv_path = (
        tmp_path
        / "ACME_Materials"
        / "Test_Ferrite"
        / "N_87"
        / "abcdef123456"
        / "points-bh_room_temperature.csv"
    )
    csv_path.write_text("x,y\n0.0,0.0\n100.0,0.3\n")

    with pytest.raises(ValueError, match="CSV/JSON.*bh_room_temperature"):
        repository.get(record.ref, record.revision_id)


def test_get_rejects_record_stored_under_wrong_ref(tmp_path: Path) -> None:
    source = b"h,b\n0,0\n100,0.2\n"
    record = _record(source)
    repository = FileOverlayMaterialRepository(tmp_path)
    repository.save(record, {"bh-source.csv": source})
    record_path = (
        tmp_path
        / "ACME_Materials"
        / "Test_Ferrite"
        / "N_87"
        / "abcdef123456"
        / "record.json"
    )
    document = material_record_to_json(record)
    document["revisionId"] = "000000000000"
    record_path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")

    with pytest.raises(ValueError, match="identity.*path"):
        repository.get(record.ref, record.revision_id)


def test_resave_replaces_directory_and_removes_stale_artifacts(tmp_path: Path) -> None:
    source = b"h,b\n0,0\n100,0.2\n"
    stale_source = b"stale"
    current = _record(source)
    stale_provenance = replace(
        current.sources[0], filename="stale.csv", sha256=sha256_hex(stale_source)
    )
    stale_series = replace(
        current.series[0], series_id="stale_series", source_filename="stale.csv"
    )
    initial = replace(
        current,
        sources=(*current.sources, stale_provenance),
        series=(*current.series, stale_series),
    )
    repository = FileOverlayMaterialRepository(tmp_path)
    repository.save(initial, {"bh-source.csv": source, "stale.csv": stale_source})

    repository.save(current, {"bh-source.csv": source})

    revision = tmp_path / "ACME_Materials" / "Test_Ferrite" / "N_87" / "abcdef123456"
    assert repository.get(current.ref, current.revision_id) == current
    assert not (revision / "points-stale_series.csv").exists()
    assert not (revision / "sources" / "stale_csv").exists()


def test_serialization_failure_preserves_previous_revision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = b"h,b\n0,0\n100,0.2\n"
    original = _record(source)
    replacement = replace(original, notes="replacement")
    repository = FileOverlayMaterialRepository(tmp_path)
    repository.save(original, {"bh-source.csv": source})

    def fail_points_csv(_series: object) -> str:
        raise OSError("serialization failed")

    with monkeypatch.context() as patch:
        patch.setattr(overlay_repository, "points_csv", fail_points_csv)
        with pytest.raises(OSError, match="serialization failed"):
            repository.save(replacement, {"bh-source.csv": source})

    assert repository.get(original.ref, original.revision_id) == original
    repository.save(replacement, {"bh-source.csv": source})
    assert repository.get(original.ref, original.revision_id) == replacement


def test_staging_write_failure_preserves_previous_revision_and_is_retryable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = b"h,b\n0,0\n100,0.2\n"
    original = _record(source, status=MaterialStatus.REVIEWED)
    approved = replace(original, status=MaterialStatus.APPROVED, approved_by="approver")
    repository = FileOverlayMaterialRepository(tmp_path)
    repository.save(original, {"bh-source.csv": source})
    original_write_bytes = Path.write_bytes

    def fail_staging_write(path: Path, data: bytes) -> int:
        if ".staging-" in str(path):
            raise OSError("staging write failed")
        return original_write_bytes(path, data)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "write_bytes", fail_staging_write)
        with pytest.raises(OSError, match="staging write failed"):
            repository.save(approved, {"bh-source.csv": source})

    assert repository.get(original.ref, original.revision_id) == original
    repository.save(approved, {"bh-source.csv": source})
    assert repository.get(original.ref, original.revision_id) == approved


def test_swap_failure_rolls_back_previous_revision_and_is_retryable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = b"h,b\n0,0\n100,0.2\n"
    original = _record(source)
    replacement = replace(original, notes="replacement")
    repository = FileOverlayMaterialRepository(tmp_path)
    repository.save(original, {"bh-source.csv": source})
    original_replace = Path.replace

    def fail_staging_swap(path: Path, target: Path) -> Path:
        if ".staging-" in path.name:
            raise OSError("swap failed")
        return original_replace(path, target)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "replace", fail_staging_swap)
        with pytest.raises(OSError, match="swap failed"):
            repository.save(replacement, {"bh-source.csv": source})

    assert repository.get(original.ref, original.revision_id) == original
    repository.save(replacement, {"bh-source.csv": source})
    assert repository.get(original.ref, original.revision_id) == replacement


def test_backup_cleanup_failure_rolls_back_and_is_retryable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = b"h,b\n0,0\n100,0.2\n"
    original = _record(source)
    replacement = replace(original, notes="replacement")
    repository = FileOverlayMaterialRepository(tmp_path)
    repository.save(original, {"bh-source.csv": source})
    original_rmtree = shutil.rmtree

    def fail_backup_cleanup(path: Path, *args: object, **kwargs: object) -> None:
        if ".backup-" in Path(path).name:
            raise OSError("backup cleanup failed")
        original_rmtree(path, *args, **kwargs)  # type: ignore[arg-type]

    with monkeypatch.context() as patch:
        patch.setattr(shutil, "rmtree", fail_backup_cleanup)
        with pytest.raises(OSError, match="backup cleanup failed"):
            repository.save(replacement, {"bh-source.csv": source})

    assert repository.get(original.ref, original.revision_id) == original
    repository.save(replacement, {"bh-source.csv": source})
    assert repository.get(original.ref, original.revision_id) == replacement
    assert not tuple(tmp_path.rglob("*.backup-*"))
