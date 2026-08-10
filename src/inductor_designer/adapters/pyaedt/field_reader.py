"""Reads B and J off evaluated areas, in 3D and in 2D.

One evaluated area is one ``RawFieldSection``: a representative cross section
in 3D, a whole region in 2D. Each is read independently, so one area failing
never costs the others and never fails the run.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from inductor_designer.simulation.raw_results import RawFieldSection

# Maxwell's field-quantity names and calculator functions. Assumed, and proven
# only by a live run: an unrecognized name yields no data, which becomes a
# per-section diagnostic and an unavailable quantity, never a wrong number.
FLUX_DENSITY_QUANTITY = "Mag_B"
CURRENT_DENSITY_QUANTITY = "Mag_J"
INTEGRATE = "Integrate"
MAXIMUM = "Maximum"
SURFACE = "surface"


@dataclass(frozen=True, slots=True)
class EvaluatedArea:
    """A named surface in the design, with the area its mean divides by."""

    name: str
    section_id: str
    scope: str
    area_m2: float


class FieldCapableApp(Protocol):
    def field_value(
        self,
        quantity: str,
        scalar_function: str,
        object_name: str,
        object_type: str,
    ) -> float: ...


def read_field_areas(
    app: FieldCapableApp,
    areas: Sequence[EvaluatedArea],
    quantity: str,
) -> tuple[RawFieldSection, ...]:
    sections: list[RawFieldSection] = []
    for area in areas:
        mean: float | None
        maximum: float | None
        diagnostic: str | None
        try:
            if area.area_m2 <= 0.0:
                raise ValueError(f"evaluated area {area.name} has no positive area")
            integral = app.field_value(quantity, INTEGRATE, area.name, SURFACE)
            maximum = app.field_value(quantity, MAXIMUM, area.name, SURFACE)
            mean = integral / area.area_m2
            diagnostic = None
        except Exception as error:  # noqa: BLE001 - one area failing is evidence
            mean = maximum = None
            diagnostic = f"{type(error).__name__}: {error}"
        sections.append(
            RawFieldSection(
                section_id=area.section_id,
                scope=area.scope,
                area_m2=area.area_m2,
                mean=mean,
                maximum=maximum,
                diagnostic=diagnostic,
            )
        )
    return tuple(sections)
