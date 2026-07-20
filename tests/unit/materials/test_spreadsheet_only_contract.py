from __future__ import annotations

import pytest

from inductor_designer.materials.records import (
    CurveConditions,
    CurvePoint,
    PointSeries,
    SeriesKind,
    SourceKind,
)


def test_source_kind_only_accepts_table_imports() -> None:
    assert tuple(kind.value for kind in SourceKind) == ("csv", "spreadsheet")

    with pytest.raises(ValueError):
        SourceKind("image")


def test_point_series_has_no_image_extraction_metadata() -> None:
    series = PointSeries(
        series_id="bh",
        kind=SeriesKind.BH_CURVE,
        x_unit="A/m",
        y_unit="T",
        conditions=CurveConditions(None, 25.0, None),
        points=(CurvePoint(0.0, 0.0), CurvePoint(1.0, 0.001)),
        source_filename="bh.csv",
    )

    assert not hasattr(series, "extraction")
