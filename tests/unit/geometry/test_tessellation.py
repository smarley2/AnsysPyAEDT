from __future__ import annotations

import math

import pytest

from inductor_designer.domain.winding import CurrentDirection, WindingDirection
from inductor_designer.geometry.primitives import Vec3
from inductor_designer.geometry.toroid.core_solid import FinishedCore
from inductor_designer.geometry.toroid.packing import WindingSpec, pack_winding
from inductor_designer.geometry.toroid.tessellation import (
    Mesh,
    start_bead,
    tessellate_core,
    tessellate_winding,
    tube,
    wrap_arrow,
    wrap_arrow_path,
)
from inductor_designer.simulation.maxwell_plan import Polarity, winding_polarity
from tests.unit.domain.test_project import make_winding

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
        return wrap_arrow_path(CORE, packing, sense, current)[-1]

    def radius(sense: WindingDirection, current: CurrentDirection) -> float:
        return math.hypot(tip(sense, current).x, tip(sense, current).y)

    aiding = radius(CCW, FORWARD)
    assert radius(CW, REVERSE) == aiding  # both reversed: unchanged
    assert radius(CCW, REVERSE) != aiding  # current reversed: turned round
    assert radius(CW, FORWARD) != aiding  # sense reversed: turned round
    assert radius(CCW, REVERSE) == radius(CW, FORWARD)


def test_the_arrow_runs_the_way_the_solver_is_told_the_current_goes() -> None:
    """`winding_polarity` makes the bore leg the winding's positive go leg, and
    the 2D cut view draws that as a dot in the bore. So positive ampere-turns run
    up through the bore, out across the top and down the outer wall. This arrow
    was built inverted -- climbing the outer wall on positive ampere-turns -- and
    the cut view is what caught it, so the two are pinned together here.
    """
    packing = pack_winding(CORE, WindingSpec("w1", 8, D, 0.0, 180.0, 0.0001, 0.001))
    definition = make_winding(winding_id="w1", winding_direction=CCW)
    assert winding_polarity(definition, FORWARD) is Polarity.POSITIVE

    positive = wrap_arrow_path(CORE, packing, CCW, FORWARD)
    negative = wrap_arrow_path(CORE, packing, CW, FORWARD)

    tail, up_end, across_end, tip = positive
    assert math.hypot(tail.x, tail.y) < CORE.r_inner_m  # starts inside the bore
    assert up_end.z > tail.z  # climbs it
    assert math.hypot(across_end.x, across_end.y) > CORE.r_outer_m  # out over the top
    assert across_end.z == up_end.z
    assert tip.z < across_end.z  # then down the outer wall
    assert math.hypot(tip.x, tip.y) > CORE.r_outer_m

    # The same path walked backwards, so one flow's tail is the other's tip.
    assert [(p.x, p.y, p.z) for p in negative] == [
        (p.x, p.y, p.z) for p in reversed(positive)
    ]


def test_the_wrap_arrow_stays_clear_of_the_wire() -> None:
    """Above the turns, outside them, or inside the free bore -- never buried in
    one: the marker has to stay legible against the wire it describes."""
    packing = pack_winding(CORE, WindingSpec("w1", 8, D, 0.0, 180.0, 0.0001, 0.001))
    build = packing.layers[0].radial_build_m
    turn_top = CORE.half_height_m + build + D / 2.0
    turn_outer = CORE.r_outer_m + build + D / 2.0
    turn_bore = CORE.r_inner_m - build - D / 2.0

    for sense in (CCW, CW):
        mesh = wrap_arrow(CORE, packing, sense, FORWARD)
        for x, y, z in zip(
            mesh.positions[0::3], mesh.positions[1::3], mesh.positions[2::3], strict=True
        ):
            radius = math.hypot(x, y)
            assert z > turn_top or radius > turn_outer or radius < turn_bore


def _mean_azimuth_deg(mesh: Mesh) -> float:
    """Mean vertex azimuth, wrapped into [0, 360) as the sector angles are."""
    azimuths = [
        math.degrees(math.atan2(y, x)) % 360.0
        for x, y in zip(mesh.positions[0::3], mesh.positions[1::3], strict=True)
    ]
    return sum(azimuths) / len(azimuths)


def test_the_start_bead_sits_at_the_lead_in_end_outside_the_turns() -> None:
    """Which end the wire started from is otherwise unreadable: sector, lean and
    arrow all look the same at either end."""
    packing = pack_winding(CORE, WindingSpec("w1", 8, D, 20.0, 180.0, 0.0001, 0.001))
    build = packing.layers[0].radial_build_m

    mesh = start_bead(CORE, packing, CCW)
    vertices = list(
        zip(mesh.positions[0::3], mesh.positions[1::3], mesh.positions[2::3], strict=True)
    )

    assert min(math.hypot(x, y) for x, y, _ in vertices) > CORE.r_outer_m + build
    assert _mean_azimuth_deg(mesh) == pytest.approx(packing.lead_in_deg, abs=1.0)
    # The lead-in is the low-azimuth end of the sector, before the first turn.
    assert packing.start_deg <= packing.lead_in_deg < packing.layers[0].station_deg[0]


def test_the_start_bead_moves_to_the_other_end_when_the_sense_flips() -> None:
    """Stations run up in azimuth, so a clockwise winding is fed in at the high
    end of its sector. The bead sat at the low end whichever way the winding was
    wound, so flipping the sense leaned the turns over and left the start put.
    """
    packing = pack_winding(CORE, WindingSpec("w1", 8, D, 20.0, 180.0, 0.0001, 0.001))

    ccw = _mean_azimuth_deg(start_bead(CORE, packing, CCW))
    cw = _mean_azimuth_deg(start_bead(CORE, packing, CW))

    assert ccw == pytest.approx(packing.lead_in_deg, abs=1.0)
    assert cw == pytest.approx(packing.lead_out_deg % 360.0, abs=1.0)
    assert cw > packing.layers[0].station_deg[-1] > ccw


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
