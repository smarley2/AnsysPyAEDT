"""Representative cross sections, exactly as the 2026-08-10 design defines them.

Pure geometry description: what is evaluated and where. Creating the surfaces
and reading a field off them belongs to the solver adapters.
"""

from __future__ import annotations

from dataclasses import dataclass

# Two planes closer than this are the same plane for evaluation purposes.
SECTION_DEDUPE_TOLERANCE_DEG = 0.5

# Feature precedence when two planes collide: a span edge is more meaningful
# than a span midpoint, which is more meaningful than a gap midpoint.
CORE_FEATURE_PRECEDENCE: tuple[str, ...] = (
    "span-start",
    "span-end",
    "span-mid",
    "gap-mid",
)

CONDUCTOR_STATIONS: tuple[str, ...] = (
    "inner-bore",
    "top-face",
    "outer-wall",
    "bottom-face",
)


@dataclass(frozen=True, slots=True)
class CoreSection:
    """One r-z half-plane through the core, at a layout-anchored azimuth."""

    section_id: str
    azimuth_deg: float
    feature: str


@dataclass(frozen=True, slots=True)
class ConductorSection:
    """One disc perpendicular to the wire at a named station on one turn."""

    section_id: str
    winding_id: str
    turn_index: int
    station: str
    center_m: tuple[float, float, float]
    normal: tuple[float, float, float]
    radius_m: float
