from __future__ import annotations

import math

import pytest

from inductor_designer.domain.winding import CurrentDirection, WindingDirection
from inductor_designer.geometry.core_solid import FinishedCore
from inductor_designer.geometry.packing import WindingSpec, pack_winding
from inductor_designer.geometry.primitives import Vec3
from inductor_designer.geometry.tessellation import (
    Mesh,
    start_bead,
    tessellate_core,
    tessellate_winding,
    tube,
    wrap_arrow,
    wrap_arrow_path,
)

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


CCW = WindingDirection.COUNTERCLOCKWISE
CW = WindingDirection.CLOCKWISE


def test_winding_mesh_scales_with_turns() -> None:
    small = pack_winding(CORE, WindingSpec("w1", 3, D, 0.0, 300.0, 0.0001, 0.001))
    large = pack_winding(CORE, WindingSpec("w1", 12, D, 0.0, 300.0, 0.0001, 0.001))
    mesh_small = tessellate_winding(CORE, small, CCW)
    mesh_large = tessellate_winding(CORE, large, CCW)
    assert triangle_count(mesh_large) > triangle_count(mesh_small)


def test_winding_mesh_stays_outside_axis() -> None:
    packing = pack_winding(CORE, WindingSpec("w1", 8, D, 0.0, 300.0, 0.0001, 0.001))
    mesh = tessellate_winding(CORE, packing, CCW)
    for x, y in zip(mesh.positions[0::3], mesh.positions[1::3], strict=True):
        assert math.hypot(x, y) > 0.001


def _azimuths_by_height(mesh: Mesh) -> tuple[float, float]:
    """Mean azimuth of the highest and the lowest vertices, in degrees."""
    points = list(
        zip(mesh.positions[0::3], mesh.positions[1::3], mesh.positions[2::3], strict=True)
    )
    top = max(z for _, _, z in points)
    bottom = min(z for _, _, z in points)
    span = top - bottom

    def mean_azimuth(target: float) -> float:
        selected = [
            math.degrees(math.atan2(y, x))
            for x, y, z in points
            if abs(z - target) < span / 100.0
        ]
        return sum(selected) / len(selected)

    return mean_azimuth(top), mean_azimuth(bottom)


def test_the_two_winding_senses_lean_the_turns_opposite_ways() -> None:
    """Coplanar turns drew clockwise and counter-clockwise pixel-identically, so
    the Windings screen could not show that the choice had taken effect."""
    packing = pack_winding(CORE, WindingSpec("w1", 8, D, 0.0, 180.0, 0.0001, 0.001))

    ccw_top, ccw_bottom = _azimuths_by_height(tessellate_winding(CORE, packing, CCW))
    cw_top, cw_bottom = _azimuths_by_height(tessellate_winding(CORE, packing, CW))

    ccw_lean = ccw_top - ccw_bottom
    assert cw_top - cw_bottom == pytest.approx(-ccw_lean)
    # Half the turn-to-turn pitch, split either side of mid-height. The sampled
    # band holds tube-surface vertices whose centerline sits below the extreme
    # height and which therefore carry less of the lean, so the measured value
    # approaches that from below.
    lean = packing.layers[0].pitch_deg / 2.0
    assert 0.5 * lean < ccw_lean <= lean


FORWARD = CurrentDirection.FORWARD
REVERSE = CurrentDirection.REVERSE


def test_the_arrow_follows_the_current_not_just_the_wound_sense() -> None:
    """The two choices multiply into one flow direction (`mmf_sign`), so the
    arrow has to read the product: reversing either one turns it round, and
    reversing both leaves it alone."""
    packing = pack_winding(CORE, WindingSpec("w1", 8, D, 0.0, 180.0, 0.0001, 0.001))

    def tip(sense: WindingDirection, current: CurrentDirection) -> Vec3:
        return wrap_arrow_path(CORE, packing, sense, current)[2]

    aiding = tip(CCW, FORWARD)
    assert tip(CW, REVERSE).z == aiding.z  # both reversed: unchanged
    assert tip(CCW, REVERSE).z != aiding.z  # current reversed: turned round
    assert tip(CW, FORWARD).z != aiding.z  # sense reversed: turned round
    assert tip(CCW, REVERSE).z == tip(CW, FORWARD).z


def test_the_wrap_arrow_follows_the_way_the_wire_is_wound() -> None:
    """Counter-clockwise at forward current -- positive ampere-turns -- climbs
    the outer wall and ends pointing inward over the top; the opposite flow ends
    pointing down the outer wall. So the marker agrees with the coil polarity the
    solver is given."""
    packing = pack_winding(CORE, WindingSpec("w1", 8, D, 0.0, 180.0, 0.0001, 0.001))

    ccw_tail, ccw_corner, ccw_tip = wrap_arrow_path(CORE, packing, CCW, FORWARD)
    cw_tail, cw_corner, cw_tip = wrap_arrow_path(CORE, packing, CW, FORWARD)

    # Same bracket, walked the other way: one sense's tail is the other's tip.
    assert (cw_tail.x, cw_tail.y, cw_tail.z) == (ccw_tip.x, ccw_tip.y, ccw_tip.z)
    assert (cw_tip.x, cw_tip.y, cw_tip.z) == (ccw_tail.x, ccw_tail.y, ccw_tail.z)
    assert (cw_corner.x, cw_corner.y, cw_corner.z) == (
        ccw_corner.x,
        ccw_corner.y,
        ccw_corner.z,
    )
    assert math.hypot(ccw_tip.x, ccw_tip.y) < CORE.r_inner_m  # inward over the top
    assert ccw_tip.z > CORE.half_height_m
    assert math.hypot(cw_tip.x, cw_tip.y) > CORE.r_outer_m  # down the outer wall
    assert cw_tip.z < 0.0


def test_the_wrap_arrow_stays_clear_of_the_wire() -> None:
    """Above the turns or outside them, never buried inside one."""
    packing = pack_winding(CORE, WindingSpec("w1", 8, D, 0.0, 180.0, 0.0001, 0.001))
    build = packing.layers[0].radial_build_m
    turn_top = CORE.half_height_m + build + D / 2.0
    turn_outer = CORE.r_outer_m + build + D / 2.0

    for sense in (CCW, CW):
        mesh = wrap_arrow(CORE, packing, sense, FORWARD)
        for x, y, z in zip(
            mesh.positions[0::3], mesh.positions[1::3], mesh.positions[2::3], strict=True
        ):
            assert z > turn_top or math.hypot(x, y) > turn_outer


def test_the_start_bead_sits_at_the_lead_in_end_outside_the_turns() -> None:
    """Which end the wire started from is otherwise unreadable: sector, lean and
    arrow all look the same at either end."""
    packing = pack_winding(CORE, WindingSpec("w1", 8, D, 20.0, 180.0, 0.0001, 0.001))
    build = packing.layers[0].radial_build_m

    mesh = start_bead(CORE, packing)
    vertices = list(
        zip(mesh.positions[0::3], mesh.positions[1::3], mesh.positions[2::3], strict=True)
    )
    azimuths = [math.degrees(math.atan2(y, x)) for x, y, _ in vertices]

    assert min(math.hypot(x, y) for x, y, _ in vertices) > CORE.r_outer_m + build
    assert sum(azimuths) / len(azimuths) == pytest.approx(packing.lead_in_deg, abs=1.0)
    # The lead-in is the low-azimuth end of the sector, before the first turn.
    assert packing.start_deg <= packing.lead_in_deg < packing.layers[0].station_deg[0]


def test_the_arrow_is_its_own_mesh_and_not_part_of_the_wire() -> None:
    """Turns and marker stay separable, so the drawn wire can be read alone."""
    packing = pack_winding(CORE, WindingSpec("w1", 8, D, 0.0, 180.0, 0.0001, 0.001))

    winding = tessellate_winding(CORE, packing, CCW)
    arrow = wrap_arrow(CORE, packing, CCW, FORWARD)

    assert triangle_count(winding) > triangle_count(arrow) > 0
    assert max(arrow.positions[2::3]) > max(winding.positions[2::3])


def test_leaning_keeps_the_turn_on_the_core() -> None:
    """The lean is a rotation about Z, so it moves no vertex in radius or height
    -- a leaned turn still hugs the same core it was packed against."""
    packing = pack_winding(CORE, WindingSpec("w1", 8, D, 0.0, 180.0, 0.0001, 0.001))

    def radii_and_heights(sense: WindingDirection) -> list[tuple[float, float]]:
        mesh = tessellate_winding(CORE, packing, sense)
        return sorted(
            (round(math.hypot(x, y), 9), round(z, 9))
            for x, y, z in zip(
                mesh.positions[0::3], mesh.positions[1::3], mesh.positions[2::3],
                strict=True,
            )
        )

    assert radii_and_heights(CW) == radii_and_heights(CCW)
