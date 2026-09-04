"""Millimetre drawing data for the 2D cut plane preview.

Pure and Qt-free. It reads the same `PlanarModel` that `build_maxwell2d_plan`
iterates, so the drawing the user checks is the model that reaches FEMM and
Maxwell 2D.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from inductor_designer.application.services.geometry_model import (
    ECoreGeometryModel,
    GeometryModel,
)
from inductor_designer.domain.project import InductorProject
from inductor_designer.geometry.toroid.packing import PackedWinding, start_azimuth_deg
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
class CutPlaneCircleOutline:
    """A disc of core, or the bore cut back out of one."""

    x_mm: float
    y_mm: float
    radius_mm: float
    cutout: bool


@dataclass(frozen=True, slots=True)
class CutPlaneRect:
    """A leg, a yoke, or a gap cut into one. `x_mm`/`y_mm` are its centre."""

    x_mm: float
    y_mm: float
    width_mm: float
    height_mm: float
    cutout: bool


#: The core's own cross-section, painted in order: a `cutout` shape paints the
#: background back over what came before it, which is how the toroid has always
#: drawn its bore. A list of shapes rather than a pair of radii plus a list of
#: rectangles, so no drawing is ever half-populated -- one renderer serves both
#: families and neither carries the other's unused fields.
CutPlaneShape = CutPlaneCircleOutline | CutPlaneRect


@dataclass(frozen=True, slots=True)
class CutPlaneDrawing:
    outline: tuple[CutPlaneShape, ...]
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
    r_inner_mm = planar.r_inner_m * _MM_PER_M
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
        # The annulus it always drew: the outer disc, then the bore painted
        # back out of it.
        outline=(
            CutPlaneCircleOutline(0.0, 0.0, r_outer_mm, cutout=False),
            CutPlaneCircleOutline(0.0, 0.0, r_inner_mm, cutout=True),
        ),
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


_ECORE_UNGAPPED_NOTE = (
    "Section through the centre leg. This pair is ungapped, so the leg is "
    "continuous."
)
_ECORE_GAPPED_NOTE = (
    "Section through the centre leg. Total gap {total:.2f} mm in {count} "
    "break(s); each break is where the iron stops."
)


def build_ecore_cut_plane_drawing(
    model: ECoreGeometryModel,
    project: InductorProject,
) -> CutPlaneDrawing:
    """The E+E pair in section, with its gaps and the turns beside the leg.

    The plane cuts through the centre leg, so a turn wrapping that leg is cut
    twice -- once each side, with opposite polarity -- exactly as a toroid's
    turn is cut at its bore and again at its outside.
    """
    body = model.body
    half_width = body.overall_width_m / 2.0 * _MM_PER_M
    leg_half = body.centre_leg_width_m / 2.0 * _MM_PER_M
    window_half = body.window_height_m * _MM_PER_M
    yoke = body.yoke_thickness_m * _MM_PER_M
    outer = body.outer_leg_width_m * _MM_PER_M
    depth_mm = body.depth_m * _MM_PER_M

    outline: list[CutPlaneShape] = [
        # Centre leg, spanning both halves' windows.
        CutPlaneRect(0.0, 0.0, leg_half * 2.0, window_half * 2.0, cutout=False),
        # The two yokes, each spanning the full outline width.
        CutPlaneRect(
            0.0, window_half + yoke / 2.0, half_width * 2.0, yoke, cutout=False
        ),
        CutPlaneRect(
            0.0, -(window_half + yoke / 2.0), half_width * 2.0, yoke, cutout=False
        ),
    ]
    outer_centre = half_width - outer / 2.0
    for sign in (1.0, -1.0):
        outline.append(
            CutPlaneRect(
                sign * outer_centre, 0.0, outer, window_half * 2.0, cutout=False
            )
        )

    # The gap stack sits where the two halves meet, centred on the joint, with
    # the user's segments of core between the breaks.
    stack_mm = (body.total_gap_m + sum(body.gap_spacings_m)) * _MM_PER_M
    cursor = -stack_mm / 2.0
    for index, gap in enumerate(body.gaps):
        gap_mm = gap * _MM_PER_M
        outline.append(
            CutPlaneRect(
                0.0, cursor + gap_mm / 2.0, leg_half * 2.0, gap_mm, cutout=True
            )
        )
        cursor += gap_mm
        if index < len(body.gap_spacings_m):
            cursor += body.gap_spacings_m[index] * _MM_PER_M

    directions = {
        point.winding_id: point.current_direction
        for point in project.operating_point.windings
    }
    definitions = {winding.winding_id: winding for winding in project.design.windings}
    circles: list[CutPlaneCircle] = []
    ordered = sorted(model.packings, key=lambda packing: packing.winding_id)
    for index, packing in enumerate(ordered):
        color = PALETTE[index % len(PALETTE)]
        base = winding_polarity(
            definitions[packing.winding_id], directions[packing.winding_id]
        )
        radius_mm = packing.insulated_diameter_m / 2.0 * _MM_PER_M
        for layer in packing.layers:
            x_mm = leg_half + (layer.offset_m * _MM_PER_M) + radius_mm
            for station in layer.station_m:
                # Stations run along the leg from its lower end; the drawing is
                # centred on the joint between the halves.
                y_mm = station * _MM_PER_M - window_half
                circles.append(
                    CutPlaneCircle(
                        x_mm=x_mm,
                        y_mm=y_mm,
                        radius_mm=radius_mm,
                        color=color,
                        into_plane=base is Polarity.NEGATIVE,
                    )
                )
                circles.append(
                    CutPlaneCircle(
                        x_mm=-x_mm,
                        y_mm=y_mm,
                        radius_mm=radius_mm,
                        color=color,
                        into_plane=invert_polarity(base) is Polarity.NEGATIVE,
                    )
                )

    extent_mm = max(
        [half_width, window_half + yoke]
        + [abs(circle.x_mm) + circle.radius_mm for circle in circles]
        + [abs(circle.y_mm) + circle.radius_mm for circle in circles]
    )
    note = (
        _ECORE_UNGAPPED_NOTE
        if not body.gaps
        else _ECORE_GAPPED_NOTE.format(
            total=body.total_gap_m * _MM_PER_M, count=len(body.gaps)
        )
    )
    return CutPlaneDrawing(
        outline=tuple(outline),
        depth_mm=depth_mm,
        extent_mm=extent_mm,
        circles=tuple(circles),
        starts=(),
        note=note,
    )
