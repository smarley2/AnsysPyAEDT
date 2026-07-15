from __future__ import annotations

import math

from inductor_designer.geometry.core_solid import FinishedCore
from inductor_designer.geometry.primitives import (
    ArcSegment,
    LineSegment,
    PathSegment,
    Vec3,
    half_plane_point,
)


class TurnGeometryError(ValueError):
    """A turn cannot be constructed at the requested layer."""


def radial_build_m(layer: int, insulated_diameter_m: float) -> float:
    if layer < 1:
        raise ValueError(f"layer must be >= 1, got {layer!r}")
    return (layer - 0.5) * insulated_diameter_m


def _out_of_plane(theta_deg: float) -> Vec3:
    theta = math.radians(theta_deg)
    return Vec3(-math.sin(theta), math.cos(theta), 0.0)


def build_turn_loop(
    core: FinishedCore,
    layer: int,
    insulated_diameter_m: float,
    station_deg: float,
) -> tuple[PathSegment, ...]:
    d = insulated_diameter_m
    b = radial_build_m(layer, d)
    c = core.corner_radius_m
    hh = core.half_height_m
    if core.r_inner_m - b - d / 2.0 <= 0.0:
        raise TurnGeometryError(
            f"Layer {layer} exhausts the core bore: r_inner={core.r_inner_m}, build={b}"
        )

    def p(r: float, z: float) -> Vec3:
        return half_plane_point(station_deg, r, z)

    normal = _out_of_plane(station_deg)
    r_in = core.r_inner_m - b
    r_out = core.r_outer_m + b
    quarter = math.pi / 2.0

    inner_top_center = p(core.r_inner_m + c, hh - c)
    outer_top_center = p(core.r_outer_m - c, hh - c)
    outer_bottom_center = p(core.r_outer_m - c, -(hh - c))
    inner_bottom_center = p(core.r_inner_m + c, -(hh - c))

    segments: tuple[PathSegment, ...] = (
        LineSegment(p(r_in, -(hh - c)), p(r_in, hh - c)),
        ArcSegment(inner_top_center, normal, p(r_in, hh - c), quarter),
        LineSegment(p(core.r_inner_m + c, hh + b), p(core.r_outer_m - c, hh + b)),
        ArcSegment(outer_top_center, normal, p(core.r_outer_m - c, hh + b), quarter),
        LineSegment(p(r_out, hh - c), p(r_out, -(hh - c))),
        ArcSegment(outer_bottom_center, normal, p(r_out, -(hh - c)), quarter),
        LineSegment(p(core.r_outer_m - c, -(hh + b)), p(core.r_inner_m + c, -(hh + b))),
        ArcSegment(inner_bottom_center, normal, p(core.r_inner_m + c, -(hh + b)), quarter),
    )
    return segments


def build_connector(
    core: FinishedCore,
    layer: int,
    insulated_diameter_m: float,
    from_deg: float,
    to_deg: float,
) -> ArcSegment:
    b = radial_build_m(layer, insulated_diameter_m)
    radius = core.r_outer_m + b
    return ArcSegment(
        center=Vec3(0.0, 0.0, 0.0),
        normal=Vec3(0.0, 0.0, 1.0),
        start=half_plane_point(from_deg, radius, 0.0),
        sweep_rad=math.radians(to_deg - from_deg),
    )


def build_lead(
    core: FinishedCore,
    layer: int,
    insulated_diameter_m: float,
    station_deg: float,
) -> LineSegment:
    b = radial_build_m(layer, insulated_diameter_m)
    r0 = core.r_outer_m + b
    return LineSegment(
        half_plane_point(station_deg, r0, 0.0),
        half_plane_point(station_deg, r0 + 3.0 * insulated_diameter_m, 0.0),
    )


def turn_loop_length_m(core: FinishedCore, layer: int, insulated_diameter_m: float) -> float:
    b = radial_build_m(layer, insulated_diameter_m)
    c = core.corner_radius_m
    height = 2.0 * core.half_height_m
    width = core.r_outer_m - core.r_inner_m
    return 2.0 * (height - 2.0 * c) + 2.0 * (width - 2.0 * c) + 2.0 * math.pi * (c + b)
