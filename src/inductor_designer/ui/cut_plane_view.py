"""Millimetre drawing data for the 2D cut plane preview.

Pure and Qt-free. It reads the same `PlanarModel` that `build_maxwell2d_plan`
iterates, so the drawing the user checks is the model that reaches FEMM and
Maxwell 2D.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from inductor_designer.application.services.geometry_model import GeometryModel
from inductor_designer.domain.project import InductorProject
from inductor_designer.simulation.maxwell_plan import (
    Polarity,
    invert_polarity,
    winding_polarity,
)
from inductor_designer.ui.preview_geometry import PALETTE

_MM_PER_M = 1000.0

_NO_CONDUCTORS = "This design has no conductors, so only the core annulus is drawn."


@dataclass(frozen=True, slots=True)
class CutPlaneCircle:
    x_mm: float
    y_mm: float
    radius_mm: float
    color: str
    into_plane: bool


@dataclass(frozen=True, slots=True)
class CutPlaneDrawing:
    r_inner_mm: float
    r_outer_mm: float
    depth_mm: float
    extent_mm: float
    circles: tuple[CutPlaneCircle, ...]
    note: str


def build_cut_plane_drawing(
    model: GeometryModel,
    project: InductorProject,
) -> CutPlaneDrawing:
    planar = model.planar
    definitions = {
        winding.winding_id: winding for winding in project.design.windings
    }
    directions = {
        point.winding_id: point.current_direction
        for point in project.operating_point.windings
    }

    circles: list[CutPlaneCircle] = []
    # Sorted by winding id so a winding keeps the colour `build_preview_entries`
    # gives it in the 3D view, which sorts the same way.
    ordered = sorted(planar.windings, key=lambda winding: winding.winding_id)
    for index, winding in enumerate(ordered):
        color = PALETTE[index % len(PALETTE)]
        base = winding_polarity(
            definitions[winding.winding_id], directions[winding.winding_id]
        )
        for conductor in winding.conductors:
            polarity = base if conductor.polarity > 0 else invert_polarity(base)
            circles.append(
                CutPlaneCircle(
                    x_mm=conductor.x_m * _MM_PER_M,
                    y_mm=conductor.y_m * _MM_PER_M,
                    radius_mm=conductor.radius_m * _MM_PER_M,
                    color=color,
                    into_plane=polarity is Polarity.NEGATIVE,
                )
            )

    r_outer_mm = planar.r_outer_m * _MM_PER_M
    depth_mm = planar.depth_m * _MM_PER_M
    extent_mm = max(
        [r_outer_mm]
        + [math.hypot(circle.x_mm, circle.y_mm) + circle.radius_mm for circle in circles]
    )
    note = (
        _NO_CONDUCTORS
        if not circles
        else f"Model depth {depth_mm:.2f} mm, twice the core half height."
    )
    return CutPlaneDrawing(
        r_inner_mm=planar.r_inner_m * _MM_PER_M,
        r_outer_mm=r_outer_mm,
        depth_mm=depth_mm,
        extent_mm=extent_mm,
        circles=tuple(circles),
        note=note,
    )
