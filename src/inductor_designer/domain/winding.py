from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite


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


class WindingLeg(str, Enum):
    """Which leg of a legged core a winding sits on.

    Only `CENTRE` is read today. The value exists because outer-leg winding
    is a later family's problem, not because anything interprets it yet.
    """

    CENTRE = "centre"


@dataclass(frozen=True, slots=True)
class ToroidPlacement:
    """Turns placed by angle about a toroid's axis -- the original two fields."""

    start_angle_deg: float
    sector_deg: float

    def __post_init__(self) -> None:
        for field_name in ("start_angle_deg", "sector_deg"):
            value: float = getattr(self, field_name)
            if not isfinite(value):
                raise ValueError(f"ToroidPlacement {field_name} must be finite")


@dataclass(frozen=True, slots=True)
class LegPlacement:
    """Turns placed along a leg, inside the winding window.

    `window_start_m` and `window_span_m` are the one-for-one analogue of the
    toroid's start angle and sector: two windings share a window by taking
    different spans, exactly as two windings share a toroid by taking
    different sectors.
    """

    leg: WindingLeg
    window_start_m: float
    window_span_m: float

    def __post_init__(self) -> None:
        if not isfinite(self.window_start_m) or self.window_start_m < 0.0:
            raise ValueError(
                f"LegPlacement window_start_m must be a non-negative number, "
                f"got {self.window_start_m!r}"
            )
        if not isfinite(self.window_span_m) or self.window_span_m <= 0.0:
            raise ValueError(
                f"LegPlacement window_span_m must be a positive length, "
                f"got {self.window_span_m!r}"
            )


#: A winding's placement, per core family. A union rather than a shared pair
#: of numbers with a family-dependent meaning: an angle reinterpreted as a
#: fraction of a window is the kind of overloaded value that makes a design
#: impossible to audit.
WindingPlacement = ToroidPlacement | LegPlacement


@dataclass(frozen=True, slots=True)
class WindingDefinition:
    """Declarative winding description; geometric feasibility is Milestone 2 work."""

    winding_id: str
    label: str
    turns: int
    conductor_name: str
    mode: ConductorMode
    placement: WindingPlacement
    min_spacing_m: float
    min_clearance_m: float
    winding_direction: WindingDirection
    terminal_intent: str

    def __post_init__(self) -> None:
        if not self.winding_id.strip():
            raise ValueError("WindingDefinition winding_id cannot be blank")


def require_toroid_placement(winding: WindingDefinition) -> ToroidPlacement:
    """The winding's toroid placement, or a refusal naming the winding.

    Toroid geometry states this assumption once, at the entry of whatever
    needs it, rather than reaching through `.placement` and failing later
    with an attribute error nobody can act on. Nothing in the toroid package
    learns what a leg is; it simply refuses one.
    """
    if not isinstance(winding.placement, ToroidPlacement):
        raise ValueError(
            f"Winding {winding.winding_id} is placed on a leg, not around a "
            "toroid, so toroid geometry cannot place it."
        )
    return winding.placement
