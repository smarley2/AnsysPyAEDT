from __future__ import annotations

from pathlib import Path

import pytest

from inductor_designer.adapters.catalog.sqlite_repository import SqliteCatalogRepository
from inductor_designer.application.ports.catalog import CatalogRepository
from tools.build_catalog import build

ROOT = Path(__file__).resolve().parents[4]


@pytest.fixture(scope="module")
def index_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("catalog") / "catalog.sqlite"
    build(ROOT / "catalog", ROOT / "schemas" / "catalog", out)
    return out


def test_adapter_satisfies_port(index_path: Path) -> None:
    repository: CatalogRepository = SqliteCatalogRepository(index_path)
    assert repository is not None


def test_get_core(index_path: Path) -> None:
    repository = SqliteCatalogRepository(index_path)
    core = repository.get_core("0077071A7")
    assert core is not None
    assert core.material.name == "Kool Mu"
    assert repository.get_core("does-not-exist") is None


def test_list_cores_sorted(index_path: Path) -> None:
    cores = SqliteCatalogRepository(index_path).list_cores()
    part_numbers = [core.part_number for core in cores]
    assert len(part_numbers) >= 15
    assert part_numbers == sorted(part_numbers)


def test_conductors(index_path: Path) -> None:
    repository = SqliteCatalogRepository(index_path)
    names = repository.list_conductor_names()
    assert "AWG 18" in names
    wire = repository.get_conductor("AWG 18")
    assert wire is not None and wire.bare_diameter_m == pytest.approx(0.00102362, rel=1e-3)


def test_missing_index_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        SqliteCatalogRepository(tmp_path / "missing.sqlite")
