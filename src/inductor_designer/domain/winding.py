from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ConductorMode(str, Enum):
    SOLID = "solid"
    STRANDED = "stranded"


class WindingDirection(str, Enum):
    CLOCKWISE = "cw"
    COUNTERCLOCKWISE = "ccw"


class CurrentDirection(str, Enum):
    FORWARD = "forward"
    REVERSE = "reverse"


def mmf_sign(
    winding_direction: WindingDirection,
    current_direction: CurrentDirection,
) -> float:
    """Sign of a winding's ampere-turns about the core axis: +1 or -1.

    The physical sign is the product of the two independent choices, so a
    counterclockwise winding carrying forward current and a clockwise winding
    carrying reverse current drive the core the same way. Kept here, in the
    domain, because both the solver-facing coil polarity
    (`simulation/maxwell_plan.winding_polarity`) and the preliminary
    ampere-turn sum (`simulation/magnetic_estimate.field_strengths`) must read
    the same convention; they disagreed until 2026-08-14, so the preliminary
    estimate could report flux that added while the exported model cancelled.
    """
    positive = (current_direction is CurrentDirection.FORWARD) == (
        winding_direction is WindingDirection.COUNTERCLOCKWISE
    )
    return 1.0 if positive else -1.0


@dataclass(frozen=True, slots=True)
class WindingDefinition:
    """Declarative winding description; geometric feasibility is Milestone 2 work."""

    winding_id: str
    label: str
    turns: int
    conductor_name: str
    mode: ConductorMode
    start_angle_deg: float
    sector_deg: float
    min_spacing_m: float
    min_clearance_m: float
    winding_direction: WindingDirection
    terminal_intent: str

    def __post_init__(self) -> None:
        if not self.winding_id.strip():
            raise ValueError("WindingDefinition winding_id cannot be blank")
