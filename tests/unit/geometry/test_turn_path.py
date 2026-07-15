from __future__ import annotations

import math

import pytest

from inductor_designer.geometry.core_solid import FinishedCore
from inductor_designer.geometry.primitives import ArcSegment, LineSegment, path_length
from inductor_designer.geometry.turn_path import (
    TurnGeometryError,
    build_connector,
    build_lead,
    build_turn_loop,
    radial_build_m,
    turn_loop_length_m,
)

CORE = FinishedCore(r_inner_m=0.00973, r_outer_m=0.01683, half_height_m=0.005715,
                    corner_radius_m=0.0005)
D = 0.001118  # AWG 18 grade 2 draft


def test_radial_build() -> None:
    assert radial_build_m(1, D) == pytest.approx(D / 2)
    assert radial_build_m(3, D) == pytest.approx(2.5 * D)
    with pytest.raises(ValueError):
        radial_build_m(0, D)


def test_loop_is_closed_and_continuous() -> None:
    loop = build_turn_loop(CORE, 1, D, station_deg=30.0)
    assert len(loop) == 8
    for i, segment in enumerate(loop):
        nxt = loop[(i + 1) % 8]
        seg_end = segment.end() if isinstance(segment, ArcSegment) else segment.end
        nxt_start = nxt.start
        assert (seg_end - nxt_start).norm() < 1e-12, f"gap after segment {i}"


def test_loop_lies_in_half_plane() -> None:
    theta = math.radians(30.0)
    normal = (-math.sin(theta), math.cos(theta), 0.0)
    loop = build_turn_loop(CORE, 1, D, station_deg=30.0)
    for segment in loop:
        for point in (segment.start,):
            assert point.x * normal[0] + point.y * normal[1] == pytest.approx(0.0, abs=1e-12)


def test_loop_length_matches_analytic() -> None:
    loop = build_turn_loop(CORE, 2, D, station_deg=0.0)
    assert path_length(loop) == pytest.approx(turn_loop_length_m(CORE, 2, D), rel=1e-9)


def test_analytic_length_value() -> None:
    b = radial_build_m(1, D)
    c = CORE.corner_radius_m
    expected = (
        2 * (2 * CORE.half_height_m - 2 * c)
        + 2 * (CORE.r_outer_m - CORE.r_inner_m - 2 * c)
        + 2 * math.pi * (c + b)
    )
    assert turn_loop_length_m(CORE, 1, D) == pytest.approx(expected)


def test_bore_exhaustion_raises() -> None:
    with pytest.raises(TurnGeometryError, match="bore"):
        build_turn_loop(CORE, 9, D, station_deg=0.0)  # 9th layer eats the whole bore


def test_connector_and_lead() -> None:
    connector = build_connector(CORE, 1, D, from_deg=10.0, to_deg=25.0)
    assert connector.radius() == pytest.approx(CORE.r_outer_m + D / 2)
    assert connector.length() == pytest.approx(math.radians(15.0) * connector.radius())
    lead = build_lead(CORE, 1, D, station_deg=10.0)
    assert isinstance(lead, LineSegment)
    assert lead.length() == pytest.approx(3 * D)
