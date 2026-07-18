from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum


class AxisScale(str, Enum):
    LINEAR = "linear"
    LOG = "log"


@dataclass(frozen=True, slots=True)
class AxisCalibration:
    scale: AxisScale
    pixel_a: float
    value_a: float
    pixel_b: float
    value_b: float

    def __post_init__(self) -> None:
        if self.pixel_a == self.pixel_b:
            raise ValueError("pixel anchors must differ")
        if self.value_a == self.value_b:
            raise ValueError("value anchors must differ")
        if self.scale is AxisScale.LOG and (self.value_a <= 0 or self.value_b <= 0):
            raise ValueError("logarithmic axis values must be positive")

    def value_at(self, pixel: float) -> float:
        t = (pixel - self.pixel_a) / (self.pixel_b - self.pixel_a)
        if self.scale is AxisScale.LINEAR:
            return self.value_a + t * (self.value_b - self.value_a)
        log_a = math.log10(self.value_a)
        log_b = math.log10(self.value_b)
        return math.pow(10.0, log_a + t * (log_b - log_a))


@dataclass(frozen=True, slots=True)
class CropRegion:
    left: int
    top: int
    width: int
    height: int

    def __post_init__(self) -> None:
        if self.left < 0 or self.top < 0:
            raise ValueError("crop origin must be non-negative")
        if self.width <= 0 or self.height <= 0:
            raise ValueError("crop dimensions must be positive")


@dataclass(frozen=True, slots=True)
class PixelPoint:
    x_px: float
    y_px: float


@dataclass(frozen=True, slots=True)
class ExtractionRecord:
    crop: CropRegion
    x_axis: AxisCalibration
    y_axis: AxisCalibration
    pixel_points: tuple[PixelPoint, ...]


def extract_points(record: ExtractionRecord) -> tuple[tuple[float, float], ...]:
    """Map pixel points to raw-unit coordinate pairs while preserving order."""
    x_axis = AxisCalibration(
        record.x_axis.scale,
        round(record.x_axis.pixel_a, 9),
        round(record.x_axis.value_a, 9),
        round(record.x_axis.pixel_b, 9),
        round(record.x_axis.value_b, 9),
    )
    y_axis = AxisCalibration(
        record.y_axis.scale,
        round(record.y_axis.pixel_a, 9),
        round(record.y_axis.value_a, 9),
        round(record.y_axis.pixel_b, 9),
        round(record.y_axis.value_b, 9),
    )
    return tuple(
        (
            round(x_axis.value_at(round(point.x_px, 9)), 9),
            round(y_axis.value_at(round(point.y_px, 9)), 9),
        )
        for point in record.pixel_points
    )
