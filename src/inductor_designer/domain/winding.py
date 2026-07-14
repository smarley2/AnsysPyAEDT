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
    current_direction: CurrentDirection
    terminal_intent: str
    ac_magnitude_a: float
    ac_phase_deg: float
    frequency_hz: float
    dc_current_a: float

    def __post_init__(self) -> None:
        if not self.winding_id.strip():
            raise ValueError("WindingDefinition winding_id cannot be blank")
