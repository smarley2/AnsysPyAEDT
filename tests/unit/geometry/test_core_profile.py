from __future__ import annotations

from inductor_designer.geometry.core_profile import build_core_profile
from inductor_designer.geometry.core_solid import FinishedCore
from inductor_designer.geometry.primitives import ArcSegment, LineSegment, Vec3


def _endpoint(segment: LineSegment | ArcSegment) -> Vec3:
    return segment.end if isinstance(segment, LineSegment) else segment.end()


def _is_closed(profile: tuple[LineSegment | ArcSegment, ...]) -> bool:
    for first, second in zip(profile, profile[1:], strict=False):
        if (_endpoint(first) - second.start).norm() > 1e-9:
            return False
    return (_endpoint(profile[-1]) - profile[0].start).norm() < 1e-9


def test_rectangle_profile_without_corner_radius() -> None:
    core = FinishedCore(r_inner_m=0.01, r_outer_m=0.02, half_height_m=0.005, corner_radius_m=0.0)
    profile = build_core_profile(core)
    assert len(profile) == 4
    assert all(isinstance(segment, LineSegment) for segment in profile)
    assert profile[0].start == Vec3(0.01, 0.0, -0.005)
    assert _is_closed(profile)


def test_rounded_profile_closes_and_lies_in_xz_plane() -> None:
    core = FinishedCore(r_inner_m=0.01, r_outer_m=0.02, half_height_m=0.005, corner_radius_m=0.001)
    profile = build_core_profile(core)
    assert len(profile) == 8
    assert _is_closed(profile)
    for segment in profile:
        assert abs(segment.start.y) < 1e-12
