from __future__ import annotations

import math

import pytest

from inductor_designer.geometry.core_solid import FinishedCore
from inductor_designer.geometry.packing import WindingSpec, pack_winding
from inductor_designer.geometry.primitives import Vec3
from inductor_designer.geometry.tessellation import Mesh, tessellate_core, tessellate_winding, tube

CORE = FinishedCore(r_inner_m=0.00973, r_outer_m=0.01683, half_height_m=0.005715,
                    corner_radius_m=0.0)
D = 0.001118


def triangle_count(mesh: Mesh) -> int:
    assert len(mesh.positions) == len(mesh.normals)
    assert len(mesh.positions) % 9 == 0
    return len(mesh.positions) // 9


def test_mesh_invariants() -> None:
    with pytest.raises(ValueError):
        Mesh(positions=(0.0,) * 8, normals=(0.0,) * 8)
    with pytest.raises(ValueError):
        Mesh(positions=(0.0,) * 9, normals=(0.0,) * 18)


def test_core_mesh_bounds() -> None:
    mesh = tessellate_core(CORE, angular_segments=48)
    assert triangle_count(mesh) > 0
    xs = mesh.positions[0::3]
    zs = mesh.positions[2::3]
    radius = max(math.hypot(x, y) for x, y in zip(mesh.positions[0::3],
                                                  mesh.positions[1::3], strict=True))
    assert radius == pytest.approx(CORE.r_outer_m, rel=1e-6)
    assert max(zs) == pytest.approx(CORE.half_height_m, rel=1e-6)
    assert min(xs) < 0 < max(xs)  # full revolution


def test_tube_straight_segment() -> None:
    points = [Vec3(0.0, 0.0, 0.0), Vec3(0.0, 0.0, 0.01)]
    mesh = tube(points, radius=0.001, sides=8)
    assert triangle_count(mesh) == 8 * 2
    radii = [
        math.hypot(x, y)
        for x, y in zip(mesh.positions[0::3], mesh.positions[1::3], strict=True)
    ]
    assert all(r == pytest.approx(0.001, rel=1e-9) for r in radii)


def test_tube_rejects_degenerate() -> None:
    with pytest.raises(ValueError):
        tube([Vec3(0.0, 0.0, 0.0)], radius=0.001)


def test_winding_mesh_scales_with_turns() -> None:
    small = pack_winding(CORE, WindingSpec("w1", 3, D, 0.0, 300.0, 0.0001, 0.001))
    large = pack_winding(CORE, WindingSpec("w1", 12, D, 0.0, 300.0, 0.0001, 0.001))
    mesh_small = tessellate_winding(CORE, small)
    mesh_large = tessellate_winding(CORE, large)
    assert triangle_count(mesh_large) > triangle_count(mesh_small)


def test_winding_mesh_stays_outside_axis() -> None:
    packing = pack_winding(CORE, WindingSpec("w1", 8, D, 0.0, 300.0, 0.0001, 0.001))
    mesh = tessellate_winding(CORE, packing)
    for x, y in zip(mesh.positions[0::3], mesh.positions[1::3], strict=True):
        assert math.hypot(x, y) > 0.001
