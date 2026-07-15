from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from inductor_designer.geometry.core_solid import FinishedCore
from inductor_designer.geometry.packing import PackedWinding


@dataclass(frozen=True, slots=True)
class PlanarConductor:
    x_m: float
    y_m: float
    radius_m: float
    polarity: int


@dataclass(frozen=True, slots=True)
class PlanarWinding:
    winding_id: str
    conductors: tuple[PlanarConductor, ...]


@dataclass(frozen=True, slots=True)
class PlanarModel:
    r_inner_m: float
    r_outer_m: float
    depth_m: float
    windings: tuple[PlanarWinding, ...]


def _conductor(r: float, theta_deg: float, radius: float, polarity: int) -> PlanarConductor:
    theta = math.radians(theta_deg)
    return PlanarConductor(
        x_m=round(r * math.cos(theta), 9),
        y_m=round(r * math.sin(theta), 9),
        radius_m=radius,
        polarity=polarity,
    )


def build_planar_model(
    core: FinishedCore,
    packings: Sequence[PackedWinding],
    bare_radius_m: Mapping[str, float],
) -> PlanarModel:
    windings: list[PlanarWinding] = []
    for packing in packings:
        radius = bare_radius_m[packing.winding_id]
        conductors: list[PlanarConductor] = []
        for layer in packing.layers:
            r_in = core.r_inner_m - layer.radial_build_m
            r_out = core.r_outer_m + layer.radial_build_m
            for station in layer.station_deg:
                conductors.append(_conductor(r_in, station, radius, +1))
                conductors.append(_conductor(r_out, station, radius, -1))
        windings.append(PlanarWinding(packing.winding_id, tuple(conductors)))
    return PlanarModel(
        r_inner_m=core.r_inner_m,
        r_outer_m=core.r_outer_m,
        depth_m=round(2.0 * core.half_height_m, 9),
        windings=tuple(windings),
    )
