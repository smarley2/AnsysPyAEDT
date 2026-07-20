from __future__ import annotations

from dataclasses import replace

import pytest

from inductor_designer.materials.fitting import MU0
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
from inductor_designer.materials.validation import (
    IssueSeverity,
    MaterialIssue,
    validate_record,
    validate_series,
)


def _source() -> SourceProvenance:
    return SourceProvenance(
        kind=SourceKind.CSV,
        filename="curve.csv",
        sha256="a" * 64,
        url="https://example.com/curve.csv",
        page=None,
        captured_at="2026-07-17T12:00:00+00:00",
        description="Validation fixture",
    )


def _bh_series(
    *,
    x_unit: str = "A/m",
    y_unit: str = "T",
    points: tuple[tuple[float, float], ...] = ((0.0, 0.0), (1.0, 2.0 * MU0)),
) -> PointSeries:
    return PointSeries(
        series_id="bh",
        kind=SeriesKind.BH_CURVE,
        x_unit=x_unit,
        y_unit=y_unit,
        conditions=CurveConditions(None, 25.0, None),
        points=tuple(CurvePoint(x, y) for x, y in points),
        source_filename="curve.csv",
    )


def _loss_series(
    *,
    x_unit: str = "T",
    y_unit: str = "W/m3",
    frequency_hz: float | None = 100_000.0,
    points: tuple[tuple[float, float], ...] = ((0.1, 1000.0),),
) -> PointSeries:
    return PointSeries(
        series_id="loss",
        kind=SeriesKind.LOSS_TABLE,
        x_unit=x_unit,
        y_unit=y_unit,
        conditions=CurveConditions(frequency_hz, 25.0, None),
        points=tuple(CurvePoint(x, y) for x, y in points),
        source_filename="curve.csv",
    )


def _record(
    *,
    sources: tuple[SourceProvenance, ...] | None = None,
    series: tuple[PointSeries, ...] | None = None,
    relative_permeability: float | None = 60.0,
    steinmetz: SteinmetzFit | None = None,
) -> MaterialRecord:
    return MaterialRecord(
        ref=MaterialRef("Magnetics", "Kool Mu", "60"),
        revision_id="0123456789ab",
        status=MaterialStatus.DRAFT,
        created_at="2026-07-17T12:00:00+00:00",
        reviewed_by=None,
        approved_by=None,
        sources=(_source(),) if sources is None else sources,
        series=(_bh_series(),) if series is None else series,
        relative_permeability=relative_permeability,
        steinmetz=steinmetz,
        notes="",
    )


def _summary(issues: tuple[MaterialIssue, ...]) -> tuple[tuple[str, IssueSeverity], ...]:
    return tuple((issue.code, issue.severity) for issue in issues)


@pytest.mark.parametrize(
    ("series", "expected"),
    [
        (_bh_series(x_unit="invalid"), (("unit-family", IssueSeverity.ERROR),)),
        (_loss_series(y_unit="invalid"), (("unit-family", IssueSeverity.ERROR),)),
        (
            _bh_series(points=((0.0, 0.0), (1.0, 5.1))),
            (("range-b", IssueSeverity.ERROR),),
        ),
        (
            _loss_series(points=((5.1, 1000.0),)),
            (("range-b", IssueSeverity.ERROR),),
        ),
        (
            _bh_series(points=((0.0, 0.0), (10_000_001.0, 5.0))),
            (
                ("range-h", IssueSeverity.ERROR),
                ("slope-below-mu0", IssueSeverity.WARNING),
            ),
        ),
        (
            _loss_series(points=((0.1, 0.0),)),
            (("loss-positive", IssueSeverity.ERROR),),
        ),
        (
            _bh_series(
                points=(
                    (0.0, 0.0),
                    (2.0, 4.0 * MU0),
                    (1.0, 5.0 * MU0),
                    (2.0, 7.0 * MU0),
                )
            ),
            (
                ("duplicate-h", IssueSeverity.ERROR),
                ("monotonic-h", IssueSeverity.ERROR),
            ),
        ),
        (
            _bh_series(points=((0.0, 0.0), (2.0, 3.0 * MU0), (1.0, 4.0 * MU0))),
            (("monotonic-h", IssueSeverity.ERROR),),
        ),
        (
            _bh_series(points=((0.0, 0.0), (1.0, 0.0))),
            (
                ("monotonic-b", IssueSeverity.ERROR),
                ("slope-below-mu0", IssueSeverity.WARNING),
            ),
        ),
        (
            _bh_series(
                points=((0.0, 0.0), (1.0, 3.0 * MU0), (2.0, 2.0 * MU0))
            ),
            (
                ("monotonic-b", IssueSeverity.ERROR),
                ("slope-below-mu0", IssueSeverity.WARNING),
            ),
        ),
        (
            _bh_series(points=((1.0, 2.0 * MU0), (2.0, 4.0 * MU0))),
            (("origin", IssueSeverity.ERROR),),
        ),
        (
            _bh_series(points=((0.0, 0.0), (1.0, 0.5 * MU0))),
            (("slope-below-mu0", IssueSeverity.WARNING),),
        ),
        (
            _loss_series(frequency_hz=None),
            (("loss-frequency-missing", IssueSeverity.ERROR),),
        ),
    ],
    ids=[
        "bh-unit-family",
        "loss-unit-family",
        "bh-range-b",
        "loss-range-b",
        "range-h",
        "loss-positive",
        "duplicate-h",
        "monotonic-h",
        "monotonic-b",
        "decreasing-b",
        "origin",
        "slope-below-mu0",
        "loss-frequency-missing",
    ],
)
def test_validate_series_reports_each_d6_violation(
    series: PointSeries, expected: tuple[tuple[str, IssueSeverity], ...]
) -> None:
    assert _summary(validate_series(series)) == expected


def test_validate_loss_rejects_frequency_rounded_to_zero() -> None:
    series = _loss_series(frequency_hz=0.0000000004)

    assert ("loss-frequency-missing", IssueSeverity.ERROR) in _summary(
        validate_series(series)
    )


@pytest.mark.parametrize(
    "series",
    [
        _bh_series(x_unit="Oe", y_unit="G"),
        _bh_series(x_unit="kA/m", y_unit="mT"),
        _bh_series(y_unit="kG", points=((0.0, 0.0), (1.0, 2.0 * MU0))),
        _loss_series(x_unit="mT", y_unit="kW/m3"),
        _loss_series(x_unit="G", y_unit="mW/cm3"),
        _loss_series(x_unit="kG"),
    ],
    ids=["bh-cgs", "bh-engineering", "bh-kg", "loss-engineering", "loss-cgs", "loss-kg"],
)
def test_validate_series_accepts_valid_d6_cases(series: PointSeries) -> None:
    assert validate_series(series) == ()


@pytest.mark.parametrize(
    ("record", "expected"),
    [
        (
            _record(relative_permeability=0.5),
            (("permeability-range", IssueSeverity.ERROR),),
        ),
        (
            _record(series=(), relative_permeability=None),
            (("empty-record", IssueSeverity.ERROR),),
        ),
        (
            _record(
                steinmetz=SteinmetzFit(1.0, 1.0, 2.0, 0.0, 0.0),
            ),
            (("fit-without-data", IssueSeverity.ERROR),),
        ),
    ],
    ids=["permeability-range", "empty-record", "fit-without-data"],
)
def test_validate_record_reports_each_d6_violation(
    record: MaterialRecord, expected: tuple[tuple[str, IssueSeverity], ...]
) -> None:
    assert _summary(validate_record(record)) == expected


@pytest.mark.parametrize(
    "record",
    [
        _record(relative_permeability=1.0),
        _record(relative_permeability=1_000_000.0),
        _record(series=(), relative_permeability=60.0),
        _record(
            series=(_loss_series(),),
            steinmetz=SteinmetzFit(1.0, 1.0, 2.0, 0.0, 0.0),
        ),
    ],
    ids=["minimum-permeability", "maximum-permeability", "scalar-only", "fit-with-loss"],
)
def test_validate_record_accepts_valid_d6_cases(record: MaterialRecord) -> None:
    assert validate_record(record) == ()


def test_validate_record_includes_series_issues_in_series_order() -> None:
    bad_bh = _bh_series(x_unit="invalid")
    bad_loss = replace(
        _loss_series(), series_id="loss", conditions=CurveConditions(None, 25.0, None)
    )

    assert _summary(validate_record(_record(series=(bad_bh, bad_loss)))) == (
        ("unit-family", IssueSeverity.ERROR),
        ("loss-frequency-missing", IssueSeverity.ERROR),
    )


def test_validate_record_accepts_csv_backed_series_without_extraction_metadata() -> None:
    assert validate_record(_record()) == ()
