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
    terminal_intent: str

    def __post_init__(self) -> None:
        if not self.winding_id.strip():
            raise ValueError("WindingDefinition winding_id cannot be blank")
