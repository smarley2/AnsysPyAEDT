from __future__ import annotations

import pytest

from inductor_designer.adapters.pyaedt.polyline_data import polyline_data
from inductor_designer.geometry.core_solid import FinishedCore
from inductor_designer.geometry.primitives import LineSegment, Vec3
from inductor_designer.geometry.turn_path import build_turn_loop

CORE = FinishedCore(r_inner_m=0.01, r_outer_m=0.02, half_height_m=0.005, corner_radius_m=0.0)


def test_turn_loop_converts_to_13_points_and_8_kinds() -> None:
    loop = build_turn_loop(CORE, layer=1, insulated_diameter_m=0.001, station_deg=30.0)
    data = polyline_data(loop, closed=True)
    assert data.kinds == ("Line", "Arc", "Line", "Arc", "Line", "Arc", "Line", "Arc")
    # 8 shared joints + 4 arc midpoints + explicit closing duplicate of the start
    assert len(data.points) == 13
    assert data.points[-1] == data.points[0]


def test_open_path_keeps_order_and_dedupes_joints() -> None:
    a = LineSegment(Vec3(0.0, 0.0, 0.0), Vec3(1.0, 0.0, 0.0))
    b = LineSegment(Vec3(1.0, 0.0, 0.0), Vec3(1.0, 1.0, 0.0))
    data = polyline_data((a, b), closed=False)
    assert data.points == ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0))
    assert data.kinds == ("Line", "Line")


def test_closed_flag_rejects_open_path() -> None:
    a = LineSegment(Vec3(0.0, 0.0, 0.0), Vec3(1.0, 0.0, 0.0))
    with pytest.raises(ValueError, match="return"):
        polyline_data((a,), closed=True)
