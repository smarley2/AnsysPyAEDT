from __future__ import annotations

import pytest

from inductor_designer.materials.calibration import (
    AxisCalibration,
    AxisScale,
    CropRegion,
    ExtractionRecord,
    PixelPoint,
    extract_points,
)


def test_linear_axis_interpolates_midpoint() -> None:
    axis = AxisCalibration(AxisScale.LINEAR, 10.0, 2.0, 30.0, 6.0)

    assert axis.value_at(20.0) == pytest.approx(4.0)


def test_log_axis_maps_decade_midpoint() -> None:
    axis = AxisCalibration(AxisScale.LOG, 0.0, 1.0, 100.0, 100.0)

    assert axis.value_at(50.0) == pytest.approx(10.0)


def test_inverted_pixel_direction_uses_anchor_order() -> None:
    axis = AxisCalibration(AxisScale.LINEAR, 100.0, 0.0, 0.0, 10.0)

    assert axis.value_at(75.0) == pytest.approx(2.5)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"pixel_a": 1.0, "pixel_b": 1.0}, "pixel anchors"),
        ({"value_a": 2.0, "value_b": 2.0}, "value anchors"),
    ],
)
def test_axis_rejects_equal_anchors(kwargs: dict[str, float], message: str) -> None:
    values = {"pixel_a": 0.0, "value_a": 1.0, "pixel_b": 10.0, "value_b": 2.0}
    values.update(kwargs)

    with pytest.raises(ValueError, match=message):
        AxisCalibration(AxisScale.LINEAR, **values)


@pytest.mark.parametrize(("value_a", "value_b"), [(0.0, 1.0), (1.0, 0.0), (-1.0, 1.0)])
def test_log_axis_rejects_non_positive_anchor(value_a: float, value_b: float) -> None:
    with pytest.raises(ValueError, match="positive"):
        AxisCalibration(AxisScale.LOG, 0.0, value_a, 10.0, value_b)


@pytest.mark.parametrize(
    "crop",
    [
        (-1, 0, 1, 1),
        (0, -1, 1, 1),
        (0, 0, 0, 1),
        (0, 0, 1, 0),
    ],
)
def test_crop_rejects_invalid_bounds(crop: tuple[int, int, int, int]) -> None:
    with pytest.raises(ValueError):
        CropRegion(*crop)


def test_extract_points_round_trips_three_points() -> None:
    record = ExtractionRecord(
        crop=CropRegion(left=5, top=10, width=100, height=200),
        x_axis=AxisCalibration(AxisScale.LINEAR, 0.0, 0.0, 100.0, 1.0),
        y_axis=AxisCalibration(AxisScale.LINEAR, 200.0, 0.0, 0.0, 2.0),
        pixel_points=(
            PixelPoint(0.0, 200.0),
            PixelPoint(50.0, 100.0),
            PixelPoint(100.0, 0.0),
        ),
    )

    assert extract_points(record) == ((0.0, 0.0), (0.5, 1.0), (1.0, 2.0))


def test_extract_points_rounds_each_coordinate_to_nine_decimal_places() -> None:
    record = ExtractionRecord(
        crop=CropRegion(left=0, top=0, width=1, height=1),
        x_axis=AxisCalibration(AxisScale.LINEAR, 0.0, 0.0, 1.0, 1.0),
        y_axis=AxisCalibration(AxisScale.LINEAR, 0.0, 0.0, 1.0, 1.0),
        pixel_points=(PixelPoint(0.1234567896, 0.9876543216),),
    )

    assert extract_points(record) == ((0.12345679, 0.987654322),)
