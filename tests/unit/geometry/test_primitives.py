from __future__ import annotations

import math

import pytest

from inductor_designer.geometry.primitives import (
    ArcSegment,
    LineSegment,
    Vec3,
    half_plane_point,
    path_length,
    sample_path,
)


def test_vec3_algebra() -> None:
    a = Vec3(1.0, 2.0, 3.0)
    b = Vec3(4.0, 5.0, 6.0)
    assert a + b == Vec3(5.0, 7.0, 9.0)
    assert b - a == Vec3(3.0, 3.0, 3.0)
    assert a.scaled(2.0) == Vec3(2.0, 4.0, 6.0)
    assert a.dot(b) == pytest.approx(32.0)
    assert Vec3(1.0, 0.0, 0.0).cross(Vec3(0.0, 1.0, 0.0)) == Vec3(0.0, 0.0, 1.0)
    assert Vec3(3.0, 4.0, 0.0).norm() == pytest.approx(5.0)
    assert Vec3(0.0, 0.0, 2.0).normalized() == Vec3(0.0, 0.0, 1.0)


def test_normalized_rejects_zero() -> None:
    with pytest.raises(ValueError, match="zero"):
        Vec3(0.0, 0.0, 0.0).normalized()


def test_line_segment() -> None:
    seg = LineSegment(Vec3(0.0, 0.0, 0.0), Vec3(3.0, 0.0, 4.0))
    assert seg.length() == pytest.approx(5.0)
    points = seg.sample(3)
    assert points[0] == seg.start and points[-1] == seg.end
    assert points[1] == Vec3(1.5, 0.0, 2.0)


def test_arc_quarter_circle() -> None:
    arc = ArcSegment(
        center=Vec3(0.0, 0.0, 0.0),
        normal=Vec3(0.0, 0.0, 1.0),
        start=Vec3(1.0, 0.0, 0.0),
        sweep_rad=math.pi / 2,
    )
    assert arc.radius() == pytest.approx(1.0)
    assert arc.length() == pytest.approx(math.pi / 2)
    end = arc.end()
    assert end.x == pytest.approx(0.0, abs=1e-12)
    assert end.y == pytest.approx(1.0)


def test_arc_negative_sweep() -> None:
    arc = ArcSegment(Vec3(0.0, 0.0, 0.0), Vec3(0.0, 0.0, 1.0), Vec3(1.0, 0.0, 0.0), -math.pi / 2)
    assert arc.end().y == pytest.approx(-1.0)
    assert arc.length() == pytest.approx(math.pi / 2)


def test_path_helpers() -> None:
    line = LineSegment(Vec3(0.0, 0.0, 0.0), Vec3(1.0, 0.0, 0.0))
    arc = ArcSegment(Vec3(1.0, 1.0, 0.0), Vec3(0.0, 0.0, 1.0), Vec3(1.0, 0.0, 0.0), math.pi / 2)
    total = path_length([line, arc])
    assert total == pytest.approx(1.0 + math.pi / 2)
    points = sample_path([line, arc])
    assert points[0] == Vec3(0.0, 0.0, 0.0)
    assert len(points) >= 4
    assert all(points[i] != points[i + 1] for i in range(len(points) - 1))


def test_half_plane_point() -> None:
    p = half_plane_point(90.0, 2.0, 0.5)
    assert p.x == pytest.approx(0.0, abs=1e-12)
    assert p.y == pytest.approx(2.0)
    assert p.z == 0.5
