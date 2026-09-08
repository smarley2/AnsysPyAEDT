from __future__ import annotations

import pytest

from inductor_designer.domain.project import CatalogCoreSelection, CoreOverride, ManualCoreSelection
from inductor_designer.geometry.toroid.core_solid import (
    CoreGeometryError,
    FinishedCore,
    resolve_finished_core,
    resolve_magnetic_core,
)
from tests.unit.domain.test_catalog_records import make_core


def test_catalog_core_uses_finished_bounds() -> None:
    selection = CatalogCoreSelection("0077071A7", make_core(), ())
    core = resolve_finished_core(selection)
    snapshot = selection.snapshot
    assert core.r_outer_m == pytest.approx(snapshot.outer_diameter.max_m / 2)
    assert core.r_inner_m == pytest.approx(snapshot.inner_diameter.min_m / 2)
    assert core.half_height_m == pytest.approx(snapshot.height.max_m / 2)
    assert core.corner_radius_m == 0.0


def test_catalog_core_falls_back_to_nominal_without_bounds() -> None:
    import dataclasses

    from inductor_designer.domain.catalog_records import Dimension

    record = dataclasses.replace(
        make_core(),
        outer_diameter=Dimension(0.030, None, None),
        inner_diameter=Dimension(0.016, None, None),
        height=Dimension(0.012, None, None),
    )
    core = resolve_finished_core(CatalogCoreSelection(record.part_number, record, ()))
    assert core.r_outer_m == pytest.approx(0.015)
    assert core.r_inner_m == pytest.approx(0.008)


def test_override_replaces_finished_value() -> None:
    selection = CatalogCoreSelection(
        "0077071A7",
        make_core(),
        (CoreOverride("outer_diameter_m", 0.0340, "measured sample"),),
    )
    assert resolve_finished_core(selection).r_outer_m == pytest.approx(0.0170)


def test_magnetic_core_is_the_nominal_body_inside_the_coated_envelope() -> None:
    """The solver meshes ferrite, not coating plus tolerance band.

    Handing the coated envelope to a solver as the magnetic body overstated the
    cross-section by about a quarter on a small powder toroid.
    """
    selection = CatalogCoreSelection("0077071A7", make_core(), ())
    snapshot = selection.snapshot

    magnetic = resolve_magnetic_core(selection)

    assert magnetic.r_outer_m == pytest.approx(snapshot.outer_diameter.nominal_m / 2)
    assert magnetic.r_inner_m == pytest.approx(snapshot.inner_diameter.nominal_m / 2)
    assert magnetic.half_height_m == pytest.approx(snapshot.height.nominal_m / 2)

    coated = resolve_finished_core(selection)
    assert magnetic.r_outer_m < coated.r_outer_m
    assert magnetic.r_inner_m > coated.r_inner_m
    assert magnetic.half_height_m < coated.half_height_m


def test_magnetic_core_honours_an_override() -> None:
    selection = CatalogCoreSelection(
        "0077071A7",
        make_core(),
        (CoreOverride("outer_diameter_m", 0.0340, "measured sample"),),
    )
    assert resolve_magnetic_core(selection).r_outer_m == pytest.approx(0.0170)


def test_a_manual_core_has_one_body() -> None:
    """No tolerance data exists for entered dimensions, so both resolvers agree."""
    manual = ManualCoreSelection(0.0269, 0.0147, 0.0112, 0.0005)

    assert resolve_magnetic_core(manual) == resolve_finished_core(manual)


def test_manual_core_used_as_is() -> None:
    manual = ManualCoreSelection(0.0269, 0.0147, 0.0112, 0.0005)
    core = resolve_finished_core(manual)
    assert core == FinishedCore(0.00735, 0.01345, 0.0056, 0.0005)


def test_invalid_dimensions_raise() -> None:
    with pytest.raises(CoreGeometryError):
        resolve_finished_core(ManualCoreSelection(0.010, 0.012, 0.005, 0.0))
    with pytest.raises(CoreGeometryError):
        FinishedCore(0.005, 0.010, 0.004, 0.0045)
