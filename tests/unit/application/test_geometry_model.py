from __future__ import annotations

import sqlite3
from dataclasses import replace

import pytest

from inductor_designer.application.services.geometry_model import (
    GeometryModel,
    GeometryModelError,
    build_geometry_model,
    insulated_diameter,
)
from inductor_designer.domain.catalog_records import (
    ConductorRecord,
    ConductorStandard,
    CoreRecord,
    ReviewStatus,
)
from inductor_designer.geometry.symmetry import SymmetryRefusal
from tests.unit.domain.test_catalog_records import make_core
from tests.unit.domain.test_project import make_operating_point, make_project, make_winding


def make_conductor(**overrides: object) -> ConductorRecord:
    values: dict[str, object] = {
        "name": "AWG 18",
        "standard": ConductorStandard.AWG,
        "bare_diameter_m": 0.00102362,
        "grade1_diameter_m": 0.001072,
        "grade2_diameter_m": 0.001118,
        "source": "test",
        "catalog_revision": "round-wire-2",
        "review_status": ReviewStatus.DRAFT,
        "reviewed_by": None,
    }
    values.update(overrides)
    return ConductorRecord(**values)  # type: ignore[arg-type]


class FakeCatalog:
    def __init__(self, conductors: dict[str, ConductorRecord]) -> None:
        self._conductors = conductors

    def get_core(self, part_number: str) -> CoreRecord | None:
        return make_core() if part_number == "0077071A7" else None

    def list_cores(self) -> tuple[CoreRecord, ...]:
        return (make_core(),)

    def get_conductor(self, name: str) -> ConductorRecord | None:
        return self._conductors.get(name)

    def list_conductor_names(self) -> tuple[str, ...]:
        return tuple(self._conductors)


CATALOG = FakeCatalog({"AWG 18": make_conductor()})


def test_insulated_diameter_prefers_grade2() -> None:
    assert insulated_diameter(make_conductor()) == 0.001118
    assert insulated_diameter(make_conductor(grade2_diameter_m=None)) == 0.001072
    with pytest.raises(GeometryModelError, match="AWG 18"):
        insulated_diameter(make_conductor(grade1_diameter_m=None, grade2_diameter_m=None))


def test_build_model_end_to_end() -> None:
    project = make_project(
        design=replace(
            make_project().design,
            windings=(
                make_winding(winding_id="w1", start_angle_deg=0.0, sector_deg=150.0, turns=10),
                make_winding(winding_id="w2", start_angle_deg=180.0, sector_deg=150.0, turns=10),
            ),
        ),
        operating_point=make_operating_point(
            make_operating_point().windings[0],
            replace(make_operating_point().windings[0], winding_id="w2"),
        ),
    )
    model = build_geometry_model(project, CATALOG)
    assert isinstance(model, GeometryModel)
    assert len(model.packings) == 2
    assert model.collisions == ()
    assert model.symmetry.multiplier == 2  # type: ignore[union-attr]
    assert model.planar.depth_m > 0
    assert model.insulated_diameter_m["w1"] == 0.001118


def test_validation_errors_block() -> None:
    project = make_project(design=replace(make_project().design, windings=(make_winding(turns=0),)))
    with pytest.raises(GeometryModelError) as excinfo:
        build_geometry_model(project, CATALOG)
    assert any("winding.turns" in issue for issue in excinfo.value.issues)


def test_missing_core_blocks() -> None:
    project = make_project(design=replace(make_project().design, core=None))
    with pytest.raises(GeometryModelError, match="core"):
        build_geometry_model(project, CATALOG)


def test_packing_overflow_blocks_with_max_turns() -> None:
    project = make_project(
        design=replace(make_project().design, windings=(make_winding(turns=5000),))
    )
    with pytest.raises(GeometryModelError) as excinfo:
        build_geometry_model(project, CATALOG)
    assert any("5000" in issue for issue in excinfo.value.issues)


def test_asymmetric_project_gets_refusal_not_error() -> None:
    project = make_project(
        design=replace(
            make_project().design,
            windings=(
                make_winding(winding_id="w1", sector_deg=150.0, turns=10),
                make_winding(winding_id="w2", start_angle_deg=180.0, sector_deg=100.0, turns=10),
            ),
        ),
        operating_point=make_operating_point(
            make_operating_point().windings[0],
            replace(make_operating_point().windings[0], winding_id="w2"),
        ),
    )
    model = build_geometry_model(project, CATALOG)
    assert isinstance(model.symmetry, SymmetryRefusal)


def test_conductor_without_insulation_blocks() -> None:
    catalog = FakeCatalog(
        {"AWG 18": make_conductor(grade1_diameter_m=None, grade2_diameter_m=None)}
    )
    project = make_project(design=replace(make_project().design, windings=(make_winding(turns=5),)))
    with pytest.raises(GeometryModelError, match="insulated"):
        build_geometry_model(project, catalog)


def test_bare_diameter_recorded() -> None:
    project = make_project(design=replace(make_project().design, windings=(make_winding(turns=5),)))
    model = build_geometry_model(project, CATALOG)
    assert model.bare_diameter_m["w1"] == pytest.approx(0.00102362)


class ListingFailsCatalog:
    """A repository failure surfacing from `list_conductor_names`.

    `SqliteCatalogRepository` opens a fresh `sqlite3.connect()` per call, so a
    catalog file deleted or locked mid-session raises `OSError`/
    `sqlite3.OperationalError`, not a `GeometryModelError` -- this stands in
    for that failure.
    """

    def get_core(self, part_number: str) -> CoreRecord | None:
        return None

    def list_cores(self) -> tuple[CoreRecord, ...]:
        return ()

    def get_conductor(self, name: str) -> ConductorRecord | None:
        return None

    def list_conductor_names(self) -> tuple[str, ...]:
        raise OSError("catalog file is locked")


class LookupFailsCatalog:
    """A repository failure surfacing from `get_conductor` for one winding."""

    def __init__(self, names: tuple[str, ...]) -> None:
        self._names = names

    def get_core(self, part_number: str) -> CoreRecord | None:
        return None

    def list_cores(self) -> tuple[CoreRecord, ...]:
        return ()

    def list_conductor_names(self) -> tuple[str, ...]:
        return self._names

    def get_conductor(self, name: str) -> ConductorRecord | None:
        raise sqlite3.OperationalError("database is locked")


def test_a_catalog_listing_failure_becomes_a_geometry_model_error() -> None:
    project = make_project(design=replace(make_project().design, windings=(make_winding(turns=5),)))
    with pytest.raises(GeometryModelError, match="Catalog is unavailable"):
        build_geometry_model(project, ListingFailsCatalog())


def test_a_catalog_conductor_lookup_failure_becomes_a_geometry_model_error() -> None:
    project = make_project(design=replace(make_project().design, windings=(make_winding(turns=5),)))
    with pytest.raises(GeometryModelError, match="Catalog is unavailable"):
        build_geometry_model(project, LookupFailsCatalog(("AWG 18",)))
