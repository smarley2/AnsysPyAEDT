"""Turns selected sections into non-model sheets in a Maxwell 3D design.

Non-model is the whole point: the sheets exist so a reader can open the saved
project and see exactly which surfaces produced each reported number, and they
must not touch the mesh or the solution.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Protocol

from inductor_designer.adapters.pyaedt.field_reader import EvaluatedArea
from inductor_designer.geometry.naming import sanitize_identifier
from inductor_designer.simulation.maxwell_plan import CorePlan
from inductor_designer.simulation.result_vocabulary import (
    conductor_section_scope,
    core_section_scope,
)
from inductor_designer.simulation.sections import ConductorSection, CoreSection


class SheetCapableApp(Protocol):
    def create_section_rectangle(
        self,
        name: str,
        azimuth_deg: float,
        r_inner_m: float,
        r_outer_m: float,
        half_height_m: float,
    ) -> str: ...

    def create_section_disc(
        self,
        name: str,
        center_m: tuple[float, float, float],
        normal: tuple[float, float, float],
        radius_m: float,
    ) -> str: ...


def _sheet_name(section_id: str) -> str:
    """A section id as an AEDT object name.

    Replacing only the dots left the hyphen in ids like `core.00.span-start`,
    and AEDT rejects an object name containing one: `CreateRectangle` came back
    as `GrpcApiError: Failed to execute gRPC AEDT command: CreateRectangle` and
    took the design handle with it, so the following stage failed with
    `'NoneType' object has no attribute 'InsertSetup'`. Measured on AEDT 2025.2,
    2026-08-17. `sanitize_identifier` replaces every character AEDT refuses, not
    just the ones a given id happens to contain.
    """
    return f"Sec_{sanitize_identifier(section_id)}"


def create_core_section_sheets(
    app: SheetCapableApp,
    core: CorePlan,
    sections: Sequence[CoreSection],
    *,
    r_inner_m: float,
    r_outer_m: float,
    half_height_m: float,
) -> tuple[EvaluatedArea, ...]:
    """One rectangle per plane, spanning the core cross section."""
    areas: list[EvaluatedArea] = []
    cross_section_m2 = (r_outer_m - r_inner_m) * 2.0 * half_height_m
    for section in sections:
        name = _sheet_name(section.section_id)
        created = app.create_section_rectangle(
            name,
            section.azimuth_deg,
            r_inner_m,
            r_outer_m,
            half_height_m,
        )
        areas.append(
            EvaluatedArea(
                name=created,
                section_id=section.section_id,
                scope=core_section_scope(section.section_id),
                area_m2=cross_section_m2,
            )
        )
    return tuple(areas)


def create_conductor_section_sheets(
    app: SheetCapableApp, sections: Sequence[ConductorSection]
) -> tuple[EvaluatedArea, ...]:
    """One disc per station, perpendicular to the local wire direction."""
    areas: list[EvaluatedArea] = []
    for section in sections:
        name = _sheet_name(section.section_id)
        created = app.create_section_disc(
            name, section.center_m, section.normal, section.radius_m
        )
        areas.append(
            EvaluatedArea(
                name=created,
                section_id=section.section_id,
                scope=conductor_section_scope(section.winding_id, section.section_id),
                area_m2=math.pi * section.radius_m**2,
            )
        )
    return tuple(areas)
