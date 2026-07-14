from __future__ import annotations

import pytest

from inductor_designer.domain.catalog_records import (
    ConductorRecord,
    ConductorStandard,
    CoreFamily,
    CoreRecord,
    Dimension,
    ReviewStatus,
)
from inductor_designer.materials.identity import MaterialRef


def make_core(**overrides: object) -> CoreRecord:
    values: dict[str, object] = {
        "manufacturer": "Magnetics",
        "family": CoreFamily.POWDER_TOROID,
        "part_number": "0077071A7",
        "material": MaterialRef("Magnetics", "Kool Mu", "60"),
        "coating": "black epoxy",
        "catalog_revision": "powder-core-2024",
        "source_url": "https://www.mag-inc.com/example",
        "source_page": 10,
        "outer_diameter": Dimension(0.02692, 0.0264, 0.0274),
        "inner_diameter": Dimension(0.01473, 0.0144, 0.0151),
        "height": Dimension(0.01118, 0.0109, 0.0115),
        "effective_area_m2": 65.4e-6,
        "path_length_m": 0.0635,
        "volume_m3": 4.15e-6,
        "al_value_nh": 61.0,
        "review_status": ReviewStatus.DRAFT,
        "reviewed_by": None,
    }
    values.update(overrides)
    return CoreRecord(**values)  # type: ignore[arg-type]


def test_core_record_valid() -> None:
    core = make_core()
    assert core.part_number == "0077071A7"


def test_dimension_rejects_inverted_bounds() -> None:
    with pytest.raises(ValueError, match="min_m <= nominal_m <= max_m"):
        Dimension(0.02, 0.021, 0.022)


def test_dimension_rejects_non_positive_nominal() -> None:
    with pytest.raises(ValueError, match="nominal_m"):
        Dimension(0.0, None, None)


def test_core_rejects_inner_not_smaller_than_outer() -> None:
    with pytest.raises(ValueError, match="inner_diameter"):
        make_core(inner_diameter=Dimension(0.03, None, None))


def test_core_rejects_non_positive_effective_values() -> None:
    with pytest.raises(ValueError, match="effective_area_m2"):
        make_core(effective_area_m2=0.0)


def test_conductor_record_valid() -> None:
    wire = ConductorRecord(
        name="AWG 18",
        standard=ConductorStandard.AWG,
        bare_diameter_m=0.00102362,
        grade1_diameter_m=None,
        grade2_diameter_m=None,
        source="ASTM B258 formula",
        catalog_revision="round-wire-1",
        review_status=ReviewStatus.DRAFT,
        reviewed_by=None,
    )
    assert wire.standard is ConductorStandard.AWG


def test_conductor_rejects_insulation_not_larger_than_bare() -> None:
    with pytest.raises(ValueError, match="grade1_diameter_m"):
        ConductorRecord(
            name="AWG 18",
            standard=ConductorStandard.AWG,
            bare_diameter_m=0.001,
            grade1_diameter_m=0.001,
            grade2_diameter_m=None,
            source="test",
            catalog_revision="round-wire-1",
            review_status=ReviewStatus.DRAFT,
            reviewed_by=None,
        )
