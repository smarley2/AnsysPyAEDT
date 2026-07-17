from __future__ import annotations

import json
from pathlib import Path

import pytest

from inductor_designer.adapters.materials.overlay_repository import (
    FileOverlayMaterialRepository,
)
from inductor_designer.materials.serde import material_record_to_json, points_csv
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
