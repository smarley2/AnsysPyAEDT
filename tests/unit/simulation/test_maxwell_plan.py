from __future__ import annotations

from dataclasses import replace

import pytest

from inductor_designer.domain.catalog_records import (
    CoreFamily,
    CoreRecord,
    Dimension,
    ReviewStatus,
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
    SteinmetzFit,
)
from inductor_designer.simulation.maxwell_plan import (
    PlanBuildError,
    core_material_spec,
    material_spec_from_material_record,
)


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


def make_approved_material_record(
    *,
    status: MaterialStatus = MaterialStatus.APPROVED,
    relative_permeability: float | None = None,
) -> MaterialRecord:
    source = SourceProvenance(
        kind=SourceKind.CSV,
        filename="bh.csv",
        sha256="0" * 64,
        url="https://example.com/material.pdf",
        page=1,
        captured_at="2026-07-17T08:32:00+00:00",
        description="B-H curve",
    )
    return MaterialRecord(
        ref=MaterialRef("Magnetics", "Kool Mu", "60"),
        revision_id="0123456789ab",
        status=status,
        created_at="2026-07-17T08:32:00+00:00",
        reviewed_by=(
            "reviewer@example.com"
            if status in (MaterialStatus.REVIEWED, MaterialStatus.APPROVED)
            else None
        ),
        approved_by="approver@example.com" if status is MaterialStatus.APPROVED else None,
        sources=(source,),
        series=(
            PointSeries(
                series_id="bh",
                kind=SeriesKind.BH_CURVE,
                x_unit="A/m",
                y_unit="T",
                conditions=CurveConditions(None, 25.0, None),
                points=(CurvePoint(0.0, 0.0), CurvePoint(100.0, 0.025132741)),
                source_filename=source.filename,
            ),
            PointSeries(
                series_id="loss_100khz",
                kind=SeriesKind.LOSS_TABLE,
                x_unit="T",
                y_unit="W/m3",
                conditions=CurveConditions(100_000.0, 25.0, None),
                points=(CurvePoint(0.05, 1200.0), CurvePoint(0.1, 4500.0)),
                source_filename=source.filename,
            ),
        ),
        relative_permeability=relative_permeability,
        steinmetz=SteinmetzFit(2.5, 1.4, 2.3, 0.01, 0.02),
        notes="Approved nonlinear material.",
    )


def make_multi_bh_material_record() -> MaterialRecord:
    record = make_approved_material_record()
    bh_25c = replace(record.series[0], series_id="bh-25c")
    bh_100c = replace(
        record.series[0],
        series_id="bh-100c",
        conditions=CurveConditions(None, 100.0, None),
        points=(CurvePoint(0.0, 0.0), CurvePoint(120.0, 0.03)),
    )
    return replace(record, series=(bh_25c, bh_100c, record.series[1]))


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


def test_approved_record_becomes_nonlinear_material_with_scalar_fallback() -> None:
    record = make_approved_material_record()

    spec = material_spec_from_material_record(
        make_core_record(family=CoreFamily.FERRITE_TOROID), record
    )

    assert spec.name == "Magnetics_Kool_Mu_60_r0123456789ab"
    assert spec.relative_permeability == pytest.approx(200.0, rel=1e-7)
    assert spec.conductivity_s_per_m == 0.0
    assert spec.draft is False
    assert spec.bh_curve == ((0.0, 0.0), (0.025132741, 100.0))
    assert spec.steinmetz is record.steinmetz
    assert spec.material_revision == record.revision_id
    assert spec.bh_series_id is None


def test_imported_record_becomes_nonlinear_material_with_scalar_fallback() -> None:
    record = make_approved_material_record(status=MaterialStatus.IMPORTED)

    spec = material_spec_from_material_record(
        make_core_record(family=CoreFamily.FERRITE_TOROID), record
    )

    assert spec.draft is False
    assert spec.material_revision == record.revision_id


def test_selected_bh_series_is_exported_without_changing_record() -> None:
    record = make_multi_bh_material_record()

    spec = material_spec_from_material_record(
        make_core_record(), record, bh_series_id="bh-100c"
    )

    assert spec.bh_curve == ((0.0, 0.0), (0.03, 120.0))
    assert spec.bh_series_id == "bh-100c"
    assert record == make_multi_bh_material_record()


def test_approved_record_prefers_explicit_scalar_permeability() -> None:
    spec = material_spec_from_material_record(
        make_core_record(), make_approved_material_record(relative_permeability=75.0)
    )

    assert spec.relative_permeability == 75.0


def test_non_approved_material_record_is_refused() -> None:
    with pytest.raises(PlanBuildError, match="approved"):
        material_spec_from_material_record(
            make_core_record(), make_approved_material_record(status=MaterialStatus.REVIEWED)
        )


def test_multiple_bh_series_are_refused_as_ambiguous() -> None:
    with pytest.raises(PlanBuildError, match="multiple B-H.*bh_series_id"):
        material_spec_from_material_record(make_core_record(), make_multi_bh_material_record())


@pytest.mark.parametrize(
    ("series_id", "message"),
    (("missing", "unknown B-H series"), ("loss_100khz", "does not name a B-H series")),
)
def test_invalid_selected_bh_series_is_refused(series_id: str, message: str) -> None:
    with pytest.raises(PlanBuildError, match=message):
        material_spec_from_material_record(
            make_core_record(), make_multi_bh_material_record(), bh_series_id=series_id
        )


def test_explicit_single_bh_series_is_recorded() -> None:
    spec = material_spec_from_material_record(
        make_core_record(), make_approved_material_record(), bh_series_id="bh"
    )

    assert spec.bh_series_id == "bh"


def test_approved_physically_invalid_material_record_is_refused() -> None:
    invalid = make_approved_material_record(relative_permeability=0.5)

    with pytest.raises(PlanBuildError, match="relative permeability"):
        material_spec_from_material_record(make_core_record(), invalid)
