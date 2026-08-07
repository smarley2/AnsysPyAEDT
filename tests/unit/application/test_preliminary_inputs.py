from __future__ import annotations

import math
from dataclasses import replace

from inductor_designer.application.services.geometry_model import build_geometry_model
from inductor_designer.application.services.preliminary_inputs import (
    CATALOG_OVERRIDE_NOTE,
    MANUAL_CORE_PATH_NOTE,
    build_preliminary_request,
    core_magnetic_properties,
)
from inductor_designer.domain.project import (
    CatalogCoreSelection,
    CoreOverride,
    ManualCoreSelection,
)
from tests.unit.application.test_geometry_model import CATALOG
from tests.unit.domain.test_catalog_records import make_core
from tests.unit.domain.test_project import make_project


def test_no_core_has_no_magnetic_properties() -> None:
    assert core_magnetic_properties(None) is None


def test_catalog_core_uses_the_manufacturer_effective_values() -> None:
    record = make_core()
    selection = CatalogCoreSelection(record.part_number, record, ())

    properties = core_magnetic_properties(selection)

    assert properties is not None
    assert properties.path_length_m == record.path_length_m
    assert properties.volume_m3 == record.volume_m3
    assert properties.notes == ()


def test_catalog_core_with_dimension_overrides_says_so() -> None:
    record = make_core()
    selection = CatalogCoreSelection(
        record.part_number,
        record,
        (CoreOverride("outer_diameter_m", 0.03, "measured"),),
    )

    properties = core_magnetic_properties(selection)

    assert properties is not None
    assert properties.path_length_m == record.path_length_m
    assert properties.notes == (CATALOG_OVERRIDE_NOTE,)


def test_manual_core_computes_the_mean_path_length_and_volume() -> None:
    selection = ManualCoreSelection(
        outer_diameter_m=0.0272,
        inner_diameter_m=0.0138,
        height_m=0.0112,
        corner_radius_m=0.0,
    )

    properties = core_magnetic_properties(selection)

    expected_path = math.pi * (0.0272 + 0.0138) / 2.0
    expected_volume = ((0.0272 - 0.0138) / 2.0) * 0.0112 * expected_path
    assert properties is not None
    assert properties.path_length_m == expected_path
    assert properties.volume_m3 == expected_volume
    assert properties.notes == (MANUAL_CORE_PATH_NOTE,)


def test_request_carries_conductors_and_packings_from_the_geometry_model() -> None:
    project = make_project()
    geometry = build_geometry_model(project, CATALOG)

    request = build_preliminary_request(project, CATALOG, geometry)

    assert request.project is project
    assert request.core is not None
    assert set(request.conductors_by_winding) == {"w1"}
    assert request.conductors_by_winding["w1"].name == "AWG 18"
    assert set(request.packings_by_winding) == {"w1"}
    assert request.packings_by_winding["w1"].wire_length_m > 0.0


def test_request_without_geometry_keeps_conductors_and_drops_packings() -> None:
    """Specification section 9: geometry failure invalidates only geometry-dependent results."""
    project = make_project()

    request = build_preliminary_request(project, CATALOG, None)

    assert set(request.conductors_by_winding) == {"w1"}
    assert request.packings_by_winding == {}


def test_request_skips_a_winding_whose_conductor_is_not_in_the_catalog() -> None:
    project = make_project()
    unknown = replace(project.design.windings[0], conductor_name="AWG 99")
    project = replace(
        project, design=replace(project.design, windings=(unknown,))
    )

    request = build_preliminary_request(project, CATALOG, None)

    assert request.conductors_by_winding == {}
