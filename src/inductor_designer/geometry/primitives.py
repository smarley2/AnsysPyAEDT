from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Vec3:
    x: float
    y: float
    z: float

    def __add__(self, other: Vec3) -> Vec3:
        return Vec3(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: Vec3) -> Vec3:
        return Vec3(self.x - other.x, self.y - other.y, self.z - other.z)

    def scaled(self, k: float) -> Vec3:
        return Vec3(self.x * k, self.y * k, self.z * k)

    def dot(self, other: Vec3) -> float:
        return self.x * other.x + self.y * other.y + self.z * other.z

    def cross(self, other: Vec3) -> Vec3:
        return Vec3(
            self.y * other.z - self.z * other.y,
            self.z * other.x - self.x * other.z,
            self.x * other.y - self.y * other.x,
        )

    def norm(self) -> float:
        return math.sqrt(self.dot(self))

    def normalized(self) -> Vec3:
        length = self.norm()
        if length == 0.0:
            raise ValueError("Cannot normalize a zero vector")
        return self.scaled(1.0 / length)

    def rounded(self) -> Vec3:
        return Vec3(round(self.x, 9), round(self.y, 9), round(self.z, 9))


@dataclass(frozen=True, slots=True)
class LineSegment:
    start: Vec3
    end: Vec3

    def length(self) -> float:
        return (self.end - self.start).norm()

    def sample(self, count: int) -> tuple[Vec3, ...]:
        if count < 2:
            raise ValueError("sample count must be >= 2")
        step = 1.0 / (count - 1)
        return tuple(
            self.start + (self.end - self.start).scaled(i * step) for i in range(count)
        )


def _rotate(point: Vec3, center: Vec3, axis: Vec3, angle_rad: float) -> Vec3:
    """Rodrigues rotation of point around the axis line through center."""
    v = point - center
    k = axis
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)
    rotated = (
        v.scaled(cos_a) + k.cross(v).scaled(sin_a) + k.scaled(k.dot(v) * (1.0 - cos_a))
    )
    return center + rotated


@dataclass(frozen=True, slots=True)
class ArcSegment:
    center: Vec3
    normal: Vec3
    start: Vec3
    sweep_rad: float

    def __post_init__(self) -> None:
        if abs(self.normal.norm() - 1.0) > 1e-9:
            raise ValueError("ArcSegment normal must be a unit vector")
        if (self.start - self.center).norm() == 0.0:
            raise ValueError("ArcSegment start must differ from center")

    def radius(self) -> float:
        return (self.start - self.center).norm()

    def end(self) -> Vec3:
        return _rotate(self.start, self.center, self.normal, self.sweep_rad)

    def length(self) -> float:
        return abs(self.sweep_rad) * self.radius()

    def sample(self, count: int) -> tuple[Vec3, ...]:
        if count < 2:
            raise ValueError("sample count must be >= 2")
        step = self.sweep_rad / (count - 1)
        return tuple(
            _rotate(self.start, self.center, self.normal, i * step) for i in range(count)
        )


PathSegment = LineSegment | ArcSegment


def path_length(segments: Sequence[PathSegment]) -> float:
    return sum(segment.length() for segment in segments)


def sample_path(
    segments: Sequence[PathSegment], max_arc_step_rad: float = 0.26
) -> tuple[Vec3, ...]:
    points: list[Vec3] = []
    for segment in segments:
        if isinstance(segment, LineSegment):
            new = segment.sample(2)
        else:
            count = max(2, math.ceil(abs(segment.sweep_rad) / max_arc_step_rad) + 1)
            new = segment.sample(count)
        for point in new:
            if not points or (point - points[-1]).norm() > 1e-12:
                points.append(point)
    return tuple(points)


def half_plane_point(theta_deg: float, r: float, z: float) -> Vec3:
    theta = math.radians(theta_deg)
    return Vec3(r * math.cos(theta), r * math.sin(theta), z)
