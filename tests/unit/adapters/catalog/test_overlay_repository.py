"""A user's own cores, layered over the shipped index.

Design: `docs/superpowers/specs/2026-09-04-user-core-catalog-design.md`.

The rules that matter here are the refusals. A shipped part number can never
be replaced by a local file -- a project's Review page citing `0077109A7`
while the numbers behind it are someone's edit is the failure this catalog's
provenance rules exist to prevent -- and an imported core is always `draft`,
because an import is not the human reviewer `catalog/README.md` requires.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from inductor_designer.adapters.catalog.overlay_repository import (
    CoreOverlayError,
    OverlayCatalogRepository,
    write_overlay_core,
)
from inductor_designer.adapters.catalog.sqlite_repository import SqliteCatalogRepository
from inductor_designer.application.ports.catalog import CatalogRepository
from inductor_designer.domain.catalog_records import CoreRecord, ReviewStatus
from tools.build_catalog import build

ROOT = Path(__file__).resolve().parents[4]


@pytest.fixture(scope="module")
def index_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("catalog") / "catalog.sqlite"
    build(ROOT / "catalog", ROOT / "schemas" / "catalog", out)
    return out


def _custom_core(
    shipped: SqliteCatalogRepository, part_number: str = "BRUSA-TEST-1"
) -> CoreRecord:
    """A record shaped exactly like a shipped one, with a part number that is
    not in the index -- the same thing a filled template produces."""
    template = shipped.list_cores()[0]
    return replace(template, part_number=part_number, manufacturer="BRUSA")


def test_adapter_satisfies_port(index_path: Path, tmp_path: Path) -> None:
    repository: CatalogRepository = OverlayCatalogRepository(
        SqliteCatalogRepository(index_path), tmp_path / "catalog-overlay"
    )
    assert repository is not None


def test_an_overlay_core_is_offered_beside_the_shipped_ones(
    index_path: Path, tmp_path: Path
) -> None:
    shipped = SqliteCatalogRepository(index_path)
    overlay_root = tmp_path / "catalog-overlay"
    write_overlay_core(overlay_root, _custom_core(shipped))
    repository = OverlayCatalogRepository(shipped, overlay_root)

    part_numbers = [core.part_number for core in repository.list_cores()]
    assert "BRUSA-TEST-1" in part_numbers
    assert len(part_numbers) == len(shipped.list_cores()) + 1
    assert part_numbers == sorted(part_numbers)
    assert repository.get_core("BRUSA-TEST-1") is not None
    assert repository.overlay_part_numbers() == ("BRUSA-TEST-1",)


def test_conductors_still_come_from_the_shipped_index(
    index_path: Path, tmp_path: Path
) -> None:
    """Only cores are overlaid; everything else the port promises is
    delegated untouched."""
    shipped = SqliteCatalogRepository(index_path)
    repository = OverlayCatalogRepository(shipped, tmp_path / "catalog-overlay")
    assert repository.list_conductor_names() == shipped.list_conductor_names()
    assert repository.get_conductor("AWG 18") is not None


def test_a_part_number_the_catalog_already_ships_is_refused(
    index_path: Path, tmp_path: Path
) -> None:
    shipped = SqliteCatalogRepository(index_path)
    overlay_root = tmp_path / "catalog-overlay"
    existing = shipped.list_cores()[0]
    edited = replace(existing, al_value_nh=existing.al_value_nh * 2.0)

    with pytest.raises(CoreOverlayError, match=existing.part_number):
        write_overlay_core(overlay_root, edited, shipped=shipped)

    # And the shipped record is untouched by the attempt.
    assert shipped.get_core(existing.part_number) == existing


def test_a_file_whose_part_number_is_later_shipped_does_not_win(
    index_path: Path, tmp_path: Path
) -> None:
    """The one case the import-time refusal cannot cover: a release adds a
    part number a user had already imported. The shipped record wins, and the
    ignored file is named so the user does not have to guess which numbers
    are in play."""
    shipped = SqliteCatalogRepository(index_path)
    overlay_root = tmp_path / "catalog-overlay"
    existing = shipped.list_cores()[0]
    # Written with no `shipped` argument: this is the state a file reaches
    # when the catalog grew the part number after the file was written.
    write_overlay_core(overlay_root, replace(existing, manufacturer="BRUSA"))
    repository = OverlayCatalogRepository(shipped, overlay_root)

    assert repository.get_core(existing.part_number) == existing
    assert repository.shadowed_part_numbers() == (existing.part_number,)
    assert len(repository.list_cores()) == len(shipped.list_cores())
    assert repository.overlay_part_numbers() == ()


def test_an_unreadable_overlay_file_is_skipped_not_fatal(
    index_path: Path, tmp_path: Path
) -> None:
    """One corrupt file must not take the whole core list with it -- the same
    tolerance `FileOverlayMaterialRepository._parse_or_skip` already has."""
    shipped = SqliteCatalogRepository(index_path)
    overlay_root = tmp_path / "catalog-overlay"
    write_overlay_core(overlay_root, _custom_core(shipped))
    (overlay_root / "cores" / "broken.json").write_text("not json {{{", encoding="utf-8")
    repository = OverlayCatalogRepository(shipped, overlay_root)

    assert "BRUSA-TEST-1" in [core.part_number for core in repository.list_cores()]
    assert repository.unreadable_files() == ("broken.json",)


def test_writing_forces_draft_whatever_the_record_claims(
    index_path: Path, tmp_path: Path
) -> None:
    """`catalog/README.md`: only a human reviewer may set `reviewed`, after
    checking every number against the cited source page. An import is not
    that reviewer, so a file claiming otherwise is demoted, not trusted."""
    shipped = SqliteCatalogRepository(index_path)
    overlay_root = tmp_path / "catalog-overlay"
    claimed = replace(
        _custom_core(shipped),
        review_status=ReviewStatus.REVIEWED,
        reviewed_by="me, honestly",
    )
    write_overlay_core(overlay_root, claimed)

    stored = OverlayCatalogRepository(shipped, overlay_root).get_core("BRUSA-TEST-1")
    assert stored is not None
    assert stored.review_status is ReviewStatus.DRAFT
    assert stored.reviewed_by is None


def test_a_missing_overlay_directory_is_simply_empty(
    index_path: Path, tmp_path: Path
) -> None:
    """Every launch before the first import is this case."""
    shipped = SqliteCatalogRepository(index_path)
    repository = OverlayCatalogRepository(shipped, tmp_path / "never-created")
    assert repository.list_cores() == shipped.list_cores()
    assert repository.overlay_part_numbers() == ()
