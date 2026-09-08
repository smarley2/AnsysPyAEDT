"""The gapped E+E core body.

Six independent dimensions describe the pair; the overall width and height
are derived from them rather than entered again, because a core whose stated
overall width disagrees with its own legs is a core nobody can build. The
toroid's ``FinishedCore`` follows the same rule with its four.

Gap lengths are kept individually rather than summed at construction:
distributed gaps stop being interchangeable with one gap of the same total as
soon as fringing is modelled (which M11a deliberately does not do), and the
geometry has to draw each one.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from inductor_designer.geometry.toroid.core_solid import CoreGeometryError

_DIMENSION_FIELDS = (
    "centre_leg_width_m",
    "depth_m",
    "window_width_m",
    "window_height_m",
    "outer_leg_width_m",
    "yoke_thickness_m",
)


@dataclass(frozen=True, slots=True)
class FinishedECore:
    """One E+E pair, with the gap stack ground into its centre leg.

    ``outer_legs_gapped`` distinguishes the two builds: False is the
    ground-centre-leg build, where the outer legs stay mated; True is the
    shim build, where a spacer between the halves gaps all three legs, so
    each outer leg carries the same stack.
    """

    centre_leg_width_m: float
    depth_m: float
    window_width_m: float
    window_height_m: float
    outer_leg_width_m: float
    yoke_thickness_m: float
    gaps: tuple[float, ...] = ()
    gap_spacings_m: tuple[float, ...] = ()
    outer_legs_gapped: bool = False

    def __post_init__(self) -> None:
        for field_name in _DIMENSION_FIELDS:
            value: float = getattr(self, field_name)
            if not isfinite(value) or value <= 0.0:
                raise CoreGeometryError(
                    f"FinishedECore {field_name} must be a positive number, got {value!r}"
                )
        for index, gap in enumerate(self.gaps):
            if not isfinite(gap) or gap <= 0.0:
                raise CoreGeometryError(
                    f"FinishedECore gap {index + 1} must be a positive length, got {gap!r}"
                )
        for index, spacing in enumerate(self.gap_spacings_m):
            if not isfinite(spacing) or spacing <= 0.0:
                raise CoreGeometryError(
                    f"FinishedECore gap spacing {index + 1} must be a positive "
                    f"length, got {spacing!r}"
                )
        # N gaps are separated by exactly N-1 segments of core. Any other
        # count describes nothing a machinist could grind.
        expected_spacings = max(len(self.gaps) - 1, 0)
        if len(self.gap_spacings_m) != expected_spacings:
            raise CoreGeometryError(
                f"FinishedECore needs {expected_spacings} gap spacing(s) for "
                f"{len(self.gaps)} gap(s), got {len(self.gap_spacings_m)}"
            )
        occupied = self.total_gap_m + sum(self.gap_spacings_m)
        if occupied > self.centre_leg_length_m:
            raise CoreGeometryError(
                f"FinishedECore gaps and their spacings occupy {occupied:.4f} m "
                f"of a centre leg {self.centre_leg_length_m:.4f} m long"
            )

    @property
    def overall_width_m(self) -> float:
        """A = F + 2E + 2G."""
        return self.centre_leg_width_m + 2.0 * (self.window_width_m + self.outer_leg_width_m)

    @property
    def overall_height_m(self) -> float:
        """B = 2(D + H)."""
        return 2.0 * (self.window_height_m + self.yoke_thickness_m)

    @property
    def centre_leg_length_m(self) -> float:
        """Both halves' windows: the flux path through the centre leg."""
        return 2.0 * self.window_height_m

    @property
    def total_gap_m(self) -> float:
        return sum(self.gaps)

    @property
    def centre_leg_area_m2(self) -> float:
        """A_c = F*C. Flux density is quoted against this, by convention."""
        return self.centre_leg_width_m * self.depth_m

    @property
    def yoke_area_m2(self) -> float:
        """A_y = H*C."""
        return self.yoke_thickness_m * self.depth_m

    @property
    def outer_leg_area_m2(self) -> float:
        """A_o = G*C, per leg; there are two."""
        return self.outer_leg_width_m * self.depth_m

    @property
    def yoke_run_m(self) -> float:
        """Centreline run from the centre leg to an outer leg: E + F/2 + G/2."""
        return (
            self.window_width_m
            + self.centre_leg_width_m / 2.0
            + self.outer_leg_width_m / 2.0
        )
