from __future__ import annotations

import math

from inductor_designer.geometry.core_solid import FinishedCore
from inductor_designer.geometry.primitives import ArcSegment, LineSegment, PathSegment, Vec3


def build_core_profile(core: FinishedCore) -> tuple[PathSegment, ...]:
    """Closed core cross-section outline in the θ=0 half-plane (XZ plane).

    Revolving this outline around Z yields the finished core solid. Arc
    sweeps are +π/2 with normal (0, 1, 0), the same convention as the
    committed turn loops.
    """
    hh = core.half_height_m
    c = core.corner_radius_m
    r_in = core.r_inner_m
    r_out = core.r_outer_m

    def p(r: float, z: float) -> Vec3:
        return Vec3(r, 0.0, z)

    if c == 0.0:
        return (
            LineSegment(p(r_in, -hh), p(r_in, hh)),
            LineSegment(p(r_in, hh), p(r_out, hh)),
            LineSegment(p(r_out, hh), p(r_out, -hh)),
            LineSegment(p(r_out, -hh), p(r_in, -hh)),
        )

    normal = Vec3(0.0, 1.0, 0.0)
    quarter = math.pi / 2.0
    return (
        LineSegment(p(r_in, -(hh - c)), p(r_in, hh - c)),
        ArcSegment(p(r_in + c, hh - c), normal, p(r_in, hh - c), quarter),
        LineSegment(p(r_in + c, hh), p(r_out - c, hh)),
        ArcSegment(p(r_out - c, hh - c), normal, p(r_out - c, hh), quarter),
        LineSegment(p(r_out, hh - c), p(r_out, -(hh - c))),
        ArcSegment(p(r_out - c, -(hh - c)), normal, p(r_out, -(hh - c)), quarter),
        LineSegment(p(r_out - c, -hh), p(r_in + c, -hh)),
        ArcSegment(p(r_in + c, -(hh - c)), normal, p(r_in + c, -hh), quarter),
    )
