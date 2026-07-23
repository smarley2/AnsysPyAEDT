from __future__ import annotations

from dataclasses import replace

import pytest

from inductor_designer.application.services.material_import import (
    MaterialImportError,
    approve_material,
    import_curve_csv,
    new_draft_record,
    new_imported_record,
    review_material,
)
from inductor_designer.materials.identity import MaterialRef
from inductor_designer.materials.records import (
    CurveConditions,
    CurvePoint,
    MaterialStatus,
    PointSeries,
    SeriesKind,
    SourceKind,
    SourceProvenance,
)


def _source(filename: str) -> SourceProvenance:
    return SourceProvenance(
        kind=SourceKind.CSV,
        filename=filename,
        sha256="a" * 64,
        url=f"https://example.com/{filename}",
        page=None,
        captured_at="2026-07-17T12:00:00+00:00",
        description="Material import fixture",
    )


def _bh_series() -> PointSeries:
    source = _source("bh.csv")
    return import_curve_csv(
        "x,y\n0,0\n1,0.001\n2,0.002\n",
        series_id="bh",
        kind=SeriesKind.BH_CURVE,
        x_unit="A/m",
        y_unit="T",
        conditions=CurveConditions(None, 25.0, None),
        source=source,
    )


def test_import_curve_csv_canonicalizes_rounds_and_sorts_cgs_points() -> None:
    source = _source("bh-cgs.csv")

    series = import_curve_csv(
        "x,y\n2,3\n0,0\n1,1\n",
        series_id="bh-cgs",
        kind=SeriesKind.BH_CURVE,
        x_unit="Oe",
        y_unit="kG",
        conditions=CurveConditions(None, 25.0, None),
        source=source,
    )

    assert series.points == (
        CurvePoint(0.0, 0.0),
        CurvePoint(79.577471546, 0.1),
        CurvePoint(159.154943092, 0.3),
    )
    assert series.source_filename == source.filename


def test_import_curve_csv_reports_unit_family_issues() -> None:
    source = _source("wrong-units.csv")

    with pytest.raises(MaterialImportError) as caught:
        import_curve_csv(
            "x,y\n0,0\n1,1\n",
            series_id="bh",
            kind=SeriesKind.BH_CURVE,
            x_unit="T",
            y_unit="T",
            conditions=CurveConditions(None, None, None),
            source=source,
        )

    assert caught.value.issues == ("B-H series units must describe H and B",)
    assert str(caught.value) == "B-H series units must describe H and B"


def test_new_draft_record_fits_loss_csvs_at_multiple_frequencies() -> None:
    frequencies = (10_000.0, 50_000.0)
    flux_densities = (0.05, 0.1, 0.2)
    sources = tuple(_source(f"loss-{int(frequency)}.csv") for frequency in frequencies)
    series = tuple(
        import_curve_csv(
            "x,y\n"
            + "".join(
                f"{flux_density},{2.5 * frequency**1.4 * flux_density**2.3}\n"
                for flux_density in flux_densities
            ),
            series_id=f"loss-{int(frequency)}",
            kind=SeriesKind.LOSS_TABLE,
            x_unit="T",
            y_unit="W/m3",
            conditions=CurveConditions(frequency, 25.0, None),
            source=source,
        )
        for frequency, source in zip(frequencies, sources, strict=True)
    )

    record = new_draft_record(
        MaterialRef("Example", "Ferrite", "F1"),
        series=series,
        sources=sources,
        created_at="2026-07-17T12:00:00+00:00",
    )

    assert record.status is MaterialStatus.DRAFT
    assert record.revision_id
    assert record.steinmetz is not None
    assert record.steinmetz.k == pytest.approx(2.5, abs=1e-6)
    assert record.steinmetz.alpha == pytest.approx(1.4, abs=1e-6)
    assert record.steinmetz.beta == pytest.approx(2.3, abs=1e-6)


def test_new_imported_record_fit_ignores_loss_origin() -> None:
    frequencies = (10_000.0, 50_000.0)
    flux_densities = (0.05, 0.1, 0.2)
    sources = tuple(_source(f"origin-loss-{int(frequency)}.csv") for frequency in frequencies)
    series = tuple(
        import_curve_csv(
            "x,y\n0,0\n"
            + "".join(
                f"{flux_density},{2.5 * frequency**1.4 * flux_density**2.3}\n"
                for flux_density in flux_densities
            ),
            series_id=f"origin-loss-{int(frequency)}",
            kind=SeriesKind.LOSS_TABLE,
            x_unit="T",
            y_unit="W/m3",
            conditions=CurveConditions(frequency, 25.0, None),
            source=source,
        )
        for frequency, source in zip(frequencies, sources, strict=True)
    )

    record = new_imported_record(
        MaterialRef("Example", "Ferrite", "F1"),
        series=series,
        sources=sources,
        created_at="2026-07-17T12:00:00+00:00",
    )

    assert record.steinmetz is not None
    assert record.steinmetz.k == pytest.approx(2.5, abs=1e-6)
    assert record.steinmetz.alpha == pytest.approx(1.4, abs=1e-6)
    assert record.steinmetz.beta == pytest.approx(2.3, abs=1e-6)


def test_new_imported_record_rejects_zero_b_with_nonzero_loss() -> None:
    source = _source("loss.csv")
    series = import_curve_csv(
        "x,y\n0,1\n0.1,2\n",
        series_id="loss",
        kind=SeriesKind.LOSS_TABLE,
        x_unit="T",
        y_unit="W/m3",
        conditions=CurveConditions(100_000.0, 25.0, None),
        source=source,
    )

    with pytest.raises(MaterialImportError, match="zero B"):
        new_imported_record(
            MaterialRef("Example", "Ferrite", "F1"),
            series=(series,),
            sources=(source,),
            created_at="2026-07-17T12:00:00+00:00",
        )


def test_new_draft_record_keeps_optional_fit_empty_for_log_collinear_losses() -> None:
    samples = ((1_000.0, 0.01), (2_000.0, 0.02), (4_000.0, 0.04))
    sources = tuple(_source(f"loss-{int(frequency)}.csv") for frequency, _ in samples)
    series = tuple(
        import_curve_csv(
            f"x,y\n{flux_density},{2.5 * frequency**1.4 * flux_density**2.3}\n",
            series_id=f"loss-{int(frequency)}",
            kind=SeriesKind.LOSS_TABLE,
            x_unit="T",
            y_unit="W/m3",
            conditions=CurveConditions(frequency, 25.0, None),
            source=source,
        )
        for (frequency, flux_density), source in zip(samples, sources, strict=True)
    )

    record = new_draft_record(
        MaterialRef("Example", "Ferrite", "F1"),
        series=series,
        sources=sources,
        created_at="2026-07-17T12:00:00+00:00",
    )

    assert record.status is MaterialStatus.DRAFT
    assert record.revision_id
    assert record.steinmetz is None


def test_review_and_approve_reject_record_with_error_issues() -> None:
    source = _source("bh.csv")
    series = _bh_series()

    record = new_draft_record(
        MaterialRef("Example", "Ferrite", "F1"),
        series=(replace(series, points=(CurvePoint(0.0, 0.0), CurvePoint(1.0, 0.0))),),
        sources=(source,),
        created_at="2026-07-17T12:00:00+00:00",
    )

    with pytest.raises(MaterialImportError) as review_error:
        review_material(record, "reviewer@example.com")
    assert "B values must be strictly increasing" in review_error.value.issues

    reviewed = replace(record, status=MaterialStatus.REVIEWED, reviewed_by="reviewer@example.com")
    with pytest.raises(MaterialImportError) as approve_error:
        approve_material(reviewed, "approver@example.com")
    assert "B values must be strictly increasing" in approve_error.value.issues


def test_clean_lifecycle_preserves_revision_id() -> None:
    source = _source("bh.csv")
    series = _bh_series()
    draft = new_draft_record(
        MaterialRef("Example", "Ferrite", "F1"),
        series=(series,),
        sources=(source,),
        created_at="2026-07-17T12:00:00+00:00",
    )

    reviewed = review_material(draft, "reviewer@example.com")
    approved = approve_material(reviewed, "approver@example.com")

    assert reviewed.status is MaterialStatus.REVIEWED
    assert approved.status is MaterialStatus.APPROVED
    assert reviewed.revision_id == draft.revision_id
    assert approved.revision_id == draft.revision_id


def test_new_draft_revision_id_changes_when_series_content_changes() -> None:
    source = _source("bh.csv")
    series = _bh_series()
    ref = MaterialRef("Example", "Ferrite", "F1")
    created_at = "2026-07-17T12:00:00+00:00"

    original = new_draft_record(
        ref, series=(series,), sources=(source,), created_at=created_at
    )
    changed = new_draft_record(
        ref,
        series=(replace(series, points=series.points[:-1] + (CurvePoint(2.0, 0.003),)),),
        sources=(source,),
        created_at=created_at,
    )

    assert changed.revision_id != original.revision_id
