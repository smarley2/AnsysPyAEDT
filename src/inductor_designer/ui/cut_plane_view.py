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
from inductor_designer.geometry.packing import PackedWinding, start_azimuth_deg
from inductor_designer.simulation.maxwell_plan import (
    Polarity,
    invert_polarity,
    winding_polarity,
)
from inductor_designer.ui.preview_geometry import PALETTE

_MM_PER_M = 1000.0

_NO_CONDUCTORS = "This design has no conductors, so only the core annulus is drawn."
_START_NOTE = "The ringed dot marks where each winding starts."


@dataclass(frozen=True, slots=True)
class CutPlaneCircle:
    x_mm: float
    y_mm: float
    radius_mm: float
    color: str
    into_plane: bool


@dataclass(frozen=True, slots=True)
class CutPlaneStart:
    """Where a winding's wire is fed in, in the same plane as the conductors."""

    x_mm: float
    y_mm: float
    radius_mm: float
    color: str


@dataclass(frozen=True, slots=True)
class CutPlaneDrawing:
    r_inner_mm: float
    r_outer_mm: float
    depth_mm: float
    extent_mm: float
    circles: tuple[CutPlaneCircle, ...]
    starts: tuple[CutPlaneStart, ...]
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
    starts: list[CutPlaneStart] = []
    packings = {packing.winding_id: packing for packing in model.packings}
    # Sorted by winding id so a winding keeps the colour `build_preview_entries`
    # gives it in the 3D view, which sorts the same way.
    ordered = sorted(planar.windings, key=lambda winding: winding.winding_id)
    for index, winding in enumerate(ordered):
        color = PALETTE[index % len(PALETTE)]
        packing = packings.get(winding.winding_id)
        if packing is not None and packing.layers:
            starts.append(_start(model, packing, color))
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
        + [math.hypot(start.x_mm, start.y_mm) + start.radius_mm for start in starts]
    )
    note = (
        _NO_CONDUCTORS
        if not circles
        else (
            f"Model depth {depth_mm:.2f} mm, twice the core half height. {_START_NOTE}"
        )
    )
    return CutPlaneDrawing(
        r_inner_mm=planar.r_inner_m * _MM_PER_M,
        r_outer_mm=r_outer_mm,
        depth_mm=depth_mm,
        extent_mm=extent_mm,
        circles=tuple(circles),
        starts=tuple(starts),
        note=note,
    )


def _start(model: GeometryModel, packing: PackedWinding, color: str) -> CutPlaneStart:
    """The 3D start bead, seen from above.

    Same azimuth, radius and size as `geometry.tessellation.start_bead`, so the
    two previews mark one point rather than two, and both move when the wound
    sense flips. The radius follows `model.core`, the coated envelope the wire
    was packed against, not the ferrite annulus this view outlines.
    """
    d = packing.insulated_diameter_m
    sense = model.winding_direction[packing.winding_id]
    theta = math.radians(start_azimuth_deg(packing, sense))
    radius = model.core.r_outer_m + packing.layers[0].radial_build_m + 2.0 * d
    return CutPlaneStart(
        x_mm=radius * math.cos(theta) * _MM_PER_M,
        y_mm=radius * math.sin(theta) * _MM_PER_M,
        radius_mm=1.6 * d * _MM_PER_M,
        color=color,
    )
