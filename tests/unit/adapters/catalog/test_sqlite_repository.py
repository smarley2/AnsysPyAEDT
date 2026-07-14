from __future__ import annotations

from pathlib import Path

import pytest

from inductor_designer.adapters.catalog.sqlite_repository import SqliteCatalogRepository
from inductor_designer.application.ports.catalog import CatalogRepository
from inductor_designer.domain.catalog_records import CoreFamily, ReviewStatus
from tools.build_catalog import build

ROOT = Path(__file__).resolve().parents[4]

EXPECTED_POWDER_CORE_COUNT = 1_923
EXPECTED_POWDER_MATERIALS = {
    "Edge",
    "High Flux",
    "Kool Mu",
    "Kool Mu Hf",
    "Kool Mu MAX",
    "Kool Mu Ultra",
    "MPP",
    "XFlux",
    "XFlux Ultra",
}
REVIEWED_POWDER_PART_NUMBERS = {
    "0077021A7",
    "0077041A7",
    "0077071A7",
    "0077083A7",
    "0077090A7",
    "0077109A7",
    "0077256A7",
    "0077550A7",
    "C058071A2",
    "C058083A2",
}


@pytest.fixture(scope="module")
def index_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("catalog") / "catalog.sqlite"
    build(ROOT / "catalog", ROOT / "schemas" / "catalog", out)
    return out


@pytest.fixture(scope="module")
def repository(index_path: Path) -> SqliteCatalogRepository:
    return SqliteCatalogRepository(index_path)


def test_adapter_satisfies_port(repository: SqliteCatalogRepository) -> None:
    catalog_repository: CatalogRepository = repository
    assert catalog_repository is not None


def test_get_core(repository: SqliteCatalogRepository) -> None:
    core = repository.get_core("0077071A7")
    assert core is not None
    assert core.material.name == "Kool Mu"
    assert repository.get_core("does-not-exist") is None


def test_list_cores_sorted(repository: SqliteCatalogRepository) -> None:
    cores = repository.list_cores()
    part_numbers = [core.part_number for core in cores]
    assert part_numbers == sorted(part_numbers)


def test_complete_powder_toroid_catalog(repository: SqliteCatalogRepository) -> None:
    powder_cores = tuple(
        core
        for core in repository.list_cores()
        if core.family is CoreFamily.POWDER_TOROID
    )
    part_numbers = {core.part_number for core in powder_cores}

    assert len(powder_cores) == EXPECTED_POWDER_CORE_COUNT
    assert len(part_numbers) == EXPECTED_POWDER_CORE_COUNT
    assert {core.material.name for core in powder_cores} == EXPECTED_POWDER_MATERIALS
    assert {core.source_page for core in powder_cores} == set(range(154, 197))


def test_powder_toroids_use_asymmetric_finished_bounds(
    repository: SqliteCatalogRepository,
) -> None:
    powder_cores = (
        core
        for core in repository.list_cores()
        if core.family is CoreFamily.POWDER_TOROID
    )

    for core in powder_cores:
        assert core.outer_diameter.min_m is None
        assert core.outer_diameter.max_m is not None
        assert core.inner_diameter.min_m is not None
        assert core.inner_diameter.max_m is None
        assert core.height.min_m is None
        assert core.height.max_m is not None


def test_existing_powder_reviews_are_preserved(
    repository: SqliteCatalogRepository,
) -> None:
    reviewed = {
        core.part_number
        for core in repository.list_cores()
        if core.family is CoreFamily.POWDER_TOROID
        and core.review_status is ReviewStatus.REVIEWED
    }

    assert reviewed == REVIEWED_POWDER_PART_NUMBERS
    for part_number in reviewed:
        core = repository.get_core(part_number)
        assert core is not None
        assert core.reviewed_by == "Fabio Posser"


def test_catalog_data_table_representative_records(
    repository: SqliteCatalogRepository,
) -> None:
    expected = {
        "0077141A7": ("Kool Mu", "60", 154, 13.0, 0.00356, 0.00127),
        "C058031A2": ("High Flux", "60", 161, 25.0, 0.00787, 0.00345),
        "0078050A7": ("XFlux", "125", 166, 56.0, 0.01270, 0.00699),
        "0058443A2": ("High Flux", "75", 180, 169.0, 0.04674, 0.02332),
        "0059534A2": ("Edge", "19", 183, 33.0, 0.05400, 0.02810),
        "0078171A7": ("XFlux", "26", 196, 80.0, 0.16510, 0.08689),
    }

    for part_number, (
        material,
        grade,
        source_page,
        al_value_nh,
        nominal_od_m,
        minimum_id_m,
    ) in expected.items():
        core = repository.get_core(part_number)
        assert core is not None
        assert core.material.name == material
        assert core.material.grade == grade
        assert core.source_page == source_page
        assert core.al_value_nh == pytest.approx(al_value_nh)
        assert core.outer_diameter.nominal_m == pytest.approx(nominal_od_m)
        assert core.inner_diameter.min_m == pytest.approx(minimum_id_m)
        assert core.review_status is ReviewStatus.DRAFT


def test_locator_only_rows_without_core_data_are_not_invented(
    repository: SqliteCatalogRepository,
) -> None:
    assert repository.get_core("0055340A2") is None
    assert repository.get_core("0055341A2") is None


def test_conductors(repository: SqliteCatalogRepository) -> None:
    names = repository.list_conductor_names()
    assert "AWG 18" in names
    wire = repository.get_conductor("AWG 18")
    assert wire is not None and wire.bare_diameter_m == pytest.approx(0.00102362, rel=1e-3)


def test_missing_index_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        SqliteCatalogRepository(tmp_path / "missing.sqlite")
