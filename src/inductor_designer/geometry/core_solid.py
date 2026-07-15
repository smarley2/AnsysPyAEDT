from __future__ import annotations

from dataclasses import dataclass

from inductor_designer.domain.project import (
    CatalogCoreSelection,
    CoreSelection,
    ManualCoreSelection,
)


class CoreGeometryError(ValueError):
    """Resolved core dimensions cannot form a valid toroid."""


@dataclass(frozen=True, slots=True)
class FinishedCore:
    """Toroid core in finished (coated) dimensions; the surface the wire sees."""

    r_inner_m: float
    r_outer_m: float
    half_height_m: float
    corner_radius_m: float

    def __post_init__(self) -> None:
        if not 0.0 < self.r_inner_m < self.r_outer_m:
            raise CoreGeometryError(
                f"Need 0 < r_inner < r_outer, got {self.r_inner_m!r}, {self.r_outer_m!r}"
            )
        if self.half_height_m <= 0.0:
            raise CoreGeometryError(f"half_height_m must be positive: {self.half_height_m!r}")
        max_corner = min((self.r_outer_m - self.r_inner_m) / 2.0, self.half_height_m)
        if not 0.0 <= self.corner_radius_m <= max_corner:
            raise CoreGeometryError(
                f"corner_radius_m must be within [0, {max_corner}]: {self.corner_radius_m!r}"
            )


def resolve_finished_core(core: CoreSelection) -> FinishedCore:
    if isinstance(core, ManualCoreSelection):
        return FinishedCore(
            r_inner_m=core.inner_diameter_m / 2.0,
            r_outer_m=core.outer_diameter_m / 2.0,
            half_height_m=core.height_m / 2.0,
            corner_radius_m=core.corner_radius_m,
        )
    assert isinstance(core, CatalogCoreSelection)
    snapshot = core.snapshot
    outer = snapshot.outer_diameter.max_m or snapshot.outer_diameter.nominal_m
    inner = snapshot.inner_diameter.min_m or snapshot.inner_diameter.nominal_m
    height = snapshot.height.max_m or snapshot.height.nominal_m
    for override in core.overrides:
        if override.field == "outer_diameter_m":
            outer = override.value
        elif override.field == "inner_diameter_m":
            inner = override.value
        elif override.field == "height_m":
            height = override.value
    return FinishedCore(
        r_inner_m=inner / 2.0,
        r_outer_m=outer / 2.0,
        half_height_m=height / 2.0,
        corner_radius_m=0.0,
    )
