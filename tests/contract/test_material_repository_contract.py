from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest

from inductor_designer.adapters.materials.overlay_repository import (
    FileOverlayMaterialRepository,
)
from inductor_designer.application.ports.material_repository import (
    MaterialLookupError,
    MaterialRepository,
)
from inductor_designer.materials.identity import MaterialRef
from inductor_designer.materials.records import (
    CurveConditions,
    CurvePoint,
    MaterialRecord,
    MaterialStatus,
    PointSeries,
    SeriesKind,
    SourceKind,
    SourceProvenance,
)
from inductor_designer.materials.serde import sha256_hex
from tests.fakes.material_repository import InMemoryMaterialRepository


def _record(
    source: bytes,
    *,
    revision_id: str = "abcdef123456",
    status: MaterialStatus = MaterialStatus.DRAFT,
    created_at: str = "2026-07-17T08:00:00+00:00",
) -> MaterialRecord:
    reviewed_by = "reviewer@example.com" if status is not MaterialStatus.DRAFT else None
    approved_by = "approver@example.com" if status is MaterialStatus.APPROVED else None
    return MaterialRecord(
        ref=MaterialRef("ACME Materials", "Test Ferrite", "N 87"),
        revision_id=revision_id,
        status=status,
        created_at=created_at,
        reviewed_by=reviewed_by,
        approved_by=approved_by,
        sources=(
            SourceProvenance(
                kind=SourceKind.CSV,
                filename="bh-source.csv",
                sha256=sha256_hex(source),
                url="https://example.com/bh.csv",
                page=None,
                captured_at="2026-07-17T07:00:00+00:00",
                description="B-H source points",
            ),
        ),
        series=(
            PointSeries(
                series_id="bh_room_temperature",
                kind=SeriesKind.BH_CURVE,
                x_unit="A/m",
                y_unit="T",
                conditions=CurveConditions(None, 25.0, None),
                points=(CurvePoint(0.0, 0.0), CurvePoint(100.0, 0.2)),
                source_filename="bh-source.csv",
                extraction=None,
            ),
        ),
        relative_permeability=1600.0,
        steinmetz=None,
        notes="Contract fixture",
    )


@pytest.fixture(params=("file", "memory"))
def repository(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[MaterialRepository]:
    if request.param == "file":
        yield FileOverlayMaterialRepository(tmp_path / "overlay")
    else:
        yield InMemoryMaterialRepository()


def test_save_get_and_sources_round_trip(repository: MaterialRepository) -> None:
    source = b"h,b\n0,0\n100,0.2\n"
    record = _record(source)

    repository.save(record, {"bh-source.csv": source})

    assert repository.get(record.ref, record.revision_id) == record
    assert repository.source_bytes(record.ref, record.revision_id) == {
        "bh-source.csv": source
    }
    assert repository.list_revisions(record.ref) == (record.revision_id,)


def test_approved_revision_is_immutable(repository: MaterialRepository) -> None:
    source = b"h,b\n0,0\n100,0.2\n"
    approved = _record(source, status=MaterialStatus.APPROVED)
    repository.save(approved, {"bh-source.csv": source})

    with pytest.raises(ValueError, match="approved.*immutable"):
        repository.save(replace(approved, notes="changed"), {"bh-source.csv": source})

    assert repository.get(approved.ref, approved.revision_id) == approved


def test_same_draft_revision_can_be_resaved(repository: MaterialRepository) -> None:
    source = b"h,b\n0,0\n100,0.2\n"
    draft = _record(source)
    repository.save(draft, {"bh-source.csv": source})
    reviewed = replace(
        draft,
        status=MaterialStatus.REVIEWED,
        reviewed_by="reviewer@example.com",
    )

    repository.save(reviewed, {"bh-source.csv": source})

    assert repository.get(draft.ref, draft.revision_id) == reviewed


def test_save_rejects_source_hash_mismatch(repository: MaterialRepository) -> None:
    expected = b"expected"
    record = _record(expected)

    with pytest.raises(ValueError, match="sha256.*bh-source.csv"):
        repository.save(record, {"bh-source.csv": b"tampered"})

    assert repository.list_revisions(record.ref) == ()


@pytest.mark.parametrize(
    "sources",
    ({}, {"bh-source.csv": b"source", "extra.csv": b"extra"}),
)
def test_save_requires_exact_source_keys(
    repository: MaterialRepository, sources: dict[str, bytes]
) -> None:
    record = _record(b"source")

    with pytest.raises(ValueError, match="sources mapping.*provenance"):
        repository.save(record, sources)

    assert repository.list_revisions(record.ref) == ()


def test_save_get_canonicalization_matches_between_file_and_memory(tmp_path: Path) -> None:
    source = b"h,b\n0,0\n100,0.2\n"
    record = _record(source)
    noncanonical = replace(
        record.series[0],
        conditions=CurveConditions(None, 25.0000000004, 0.0000000004),
        points=(record.series[0].points[0], CurvePoint(100.0, 0.1234567894)),
    )
    record = replace(
        record,
        series=(noncanonical,),
        relative_permeability=1600.0000000004,
    )
    repositories: tuple[MaterialRepository, ...] = (
        FileOverlayMaterialRepository(tmp_path / "overlay"),
        InMemoryMaterialRepository(),
    )

    for repository in repositories:
        repository.save(record, {"bh-source.csv": source})

    loaded = tuple(repository.get(record.ref, record.revision_id) for repository in repositories)
    assert loaded[0] == loaded[1] == record
    assert loaded[0].series[0].points[-1].y == 0.123456789
    assert loaded[0].series[0].conditions == CurveConditions(None, 25.0, 0.0)
    assert loaded[0].relative_permeability == 1600.0


def test_latest_approved_uses_created_at(repository: MaterialRepository) -> None:
    source = b"h,b\n0,0\n100,0.2\n"
    ref = _record(source).ref
    lexically_later = _record(
        source,
        revision_id="111111111111",
        status=MaterialStatus.APPROVED,
        created_at="2026-07-17T10:00:00+02:00",
    )
    chronologically_newer = _record(
        source,
        revision_id="ffffffffffff",
        status=MaterialStatus.APPROVED,
        created_at="2026-07-17T08:30:00+00:00",
    )
    repository.save(lexically_later, {"bh-source.csv": source})
    repository.save(chronologically_newer, {"bh-source.csv": source})

    assert repository.latest_approved(ref) == chronologically_newer


def test_save_rejects_material_path_alias(repository: MaterialRepository) -> None:
    source = b"h,b\n0,0\n100,0.2\n"
    first = _record(source)
    alias = replace(
        first,
        ref=MaterialRef("ACME-Materials", "Test Ferrite", "N 87"),
        revision_id="111111111111",
    )
    repository.save(first, {"bh-source.csv": source})

    with pytest.raises(ValueError, match="material identity.*collide"):
        repository.save(alias, {"bh-source.csv": source})


def test_list_materials_returns_distinct_sorted_identities(
    repository: MaterialRepository,
) -> None:
    source = b"h,b\n0,0\n100,0.2\n"
    acme_ref = MaterialRef("ACME", "Ferrite", "N87")
    magnetics_ref = MaterialRef("Magnetics", "Kool Mu", "60")
    acme = replace(_record(source), ref=acme_ref)
    acme_second_revision = replace(
        _record(source, revision_id="111111111111"),
        ref=acme_ref,
    )
    magnetics = replace(
        _record(source, revision_id="222222222222"),
        ref=magnetics_ref,
    )
    alias = replace(
        _record(source, revision_id="333333333333"),
        ref=MaterialRef("Magnetics", "Kool-Mu", "60"),
    )
    repository.save(magnetics, {"bh-source.csv": source})
    repository.save(acme, {"bh-source.csv": source})
    repository.save(acme_second_revision, {"bh-source.csv": source})

    with pytest.raises(ValueError, match="material identity.*collide"):
        repository.save(alias, {"bh-source.csv": source})

    assert repository.list_materials() == (acme_ref, magnetics_ref)


def test_material_path_alias_is_typed_unknown(repository: MaterialRepository) -> None:
    source = b"h,b\n0,0\n100,0.2\n"
    stored = _record(source)
    alias = MaterialRef("ACME-Materials", "Test Ferrite", "N 87")
    repository.save(stored, {"bh-source.csv": source})

    with pytest.raises(MaterialLookupError):
        repository.get(alias, stored.revision_id)
    with pytest.raises(MaterialLookupError):
        repository.source_bytes(alias, stored.revision_id)
    assert repository.list_revisions(alias) == ()
    assert repository.latest_approved(alias) is None


def test_revision_path_alias_is_typed_unknown(repository: MaterialRepository) -> None:
    source = b"h,b\n0,0\n100,0.2\n"
    stored = _record(source)
    repository.save(stored, {"bh-source.csv": source})

    with pytest.raises(MaterialLookupError):
        repository.get(stored.ref, stored.revision_id.upper())
    with pytest.raises(MaterialLookupError):
        repository.source_bytes(stored.ref, stored.revision_id.upper())


def test_save_rejects_sanitized_series_collision(repository: MaterialRepository) -> None:
    source = b"h,b\n0,0\n100,0.2\n"
    record = _record(source)
    colliding = replace(record.series[0], series_id="bh-room-temperature")
    record = replace(record, series=(record.series[0], colliding))

    with pytest.raises(ValueError, match="series identifiers collide"):
        repository.save(record, {"bh-source.csv": source})


def test_save_rejects_sanitized_source_collision(repository: MaterialRepository) -> None:
    first = b"first"
    second = b"second"
    record = _record(first)
    sources = (
        replace(record.sources[0], filename="source-a", sha256=sha256_hex(first)),
        replace(record.sources[0], filename="source_a", sha256=sha256_hex(second)),
    )
    record = replace(record, sources=sources, series=())

    with pytest.raises(ValueError, match="source filenames collide"):
        repository.save(record, {"source-a": first, "source_a": second})


def test_unknown_material_raises_typed_lookup_error(repository: MaterialRepository) -> None:
    unknown = MaterialRef("Unknown", "Unknown", "Unknown")

    with pytest.raises(MaterialLookupError):
        repository.get(unknown, "000000000000")
    with pytest.raises(MaterialLookupError):
        repository.source_bytes(unknown, "000000000000")
    assert repository.list_revisions(unknown) == ()
    assert repository.latest_approved(unknown) is None
