from __future__ import annotations

import math
from dataclasses import dataclass

from inductor_designer.geometry.core_solid import FinishedCore
from inductor_designer.geometry.primitives import LineSegment, Vec3
from inductor_designer.geometry.turn_path import build_turn_loop


@dataclass(frozen=True, slots=True)
class TerminalDisk:
    """Circular coil-terminal sheet crossing one turn conductor."""

    center: Vec3
    station_deg: float
    radius_m: float

    @property
    def normal(self) -> Vec3:
        """Radial unit vector at the station: positive = outward current."""
        theta = math.radians(self.station_deg)
        return Vec3(round(math.cos(theta), 9), round(math.sin(theta), 9), 0.0)


def build_terminal_disk(
    core: FinishedCore,
    layer: int,
    insulated_diameter_m: float,
    bare_diameter_m: float,
    station_deg: float,
) -> TerminalDisk:
    loop = build_turn_loop(core, layer, insulated_diameter_m, station_deg)
    bottom = loop[6]
    if not isinstance(bottom, LineSegment):
        raise TypeError("Turn loop segment 6 must be the bottom straight run")
    center = (bottom.start + (bottom.end - bottom.start).scaled(0.5)).rounded()
    return TerminalDisk(
        center=center,
        station_deg=station_deg,
        radius_m=round(bare_diameter_m / 2.0, 9),
    )
