from __future__ import annotations

import pytest

from inductor_designer.domain.catalog_records import (
    CoreFamily,
    CoreRecord,
    Dimension,
    ReviewStatus,
)
from inductor_designer.materials.identity import MaterialRef
from inductor_designer.simulation.maxwell_plan import PlanBuildError, core_material_spec


def make_core_record(
    family: CoreFamily = CoreFamily.POWDER_TOROID,
    grade: str = "60",
    review_status: ReviewStatus = ReviewStatus.REVIEWED,
) -> CoreRecord:
    return CoreRecord(
        manufacturer="Magnetics",
        family=family,
        part_number="0077071A7",
        material=MaterialRef(manufacturer="Magnetics", name="Kool Mu", grade=grade),
        coating="black epoxy",
        catalog_revision="magnetics-powder-2025",
        source_url="https://example.com/catalog.pdf",
        source_page=173,
        outer_diameter=Dimension(nominal_m=0.03279, min_m=None, max_m=0.03366),
        inner_diameter=Dimension(nominal_m=0.02009, min_m=0.01946, max_m=None),
        height=Dimension(nominal_m=0.01067, min_m=None, max_m=0.01143),
        effective_area_m2=6.56e-05,
        path_length_m=0.0814,
        volume_m3=5.34e-06,
        al_value_nh=61.0,
        review_status=review_status,
        reviewed_by="Fabio Posser",
    )


def test_powder_grade_becomes_linear_material() -> None:
    spec = core_material_spec(make_core_record())
    assert spec.name == "Magnetics_Kool_Mu_60"
    assert spec.relative_permeability == 60.0
    assert spec.conductivity_s_per_m == 0.0
    assert spec.draft is False


def test_draft_record_marks_material_draft() -> None:
    spec = core_material_spec(make_core_record(review_status=ReviewStatus.DRAFT))
    assert spec.draft is True


def test_ferrite_family_is_refused() -> None:
    with pytest.raises(PlanBuildError, match="powder"):
        core_material_spec(make_core_record(family=CoreFamily.FERRITE_TOROID))


def test_non_numeric_grade_is_refused() -> None:
    with pytest.raises(PlanBuildError, match="numeric"):
        core_material_spec(make_core_record(grade="N87"))
