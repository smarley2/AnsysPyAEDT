"""Turns wound on an E core's centre leg, inside the winding window.

The direct analogue of ``geometry/toroid/packing.py``: that packer fills a
sector with angular stations at a minimum pitch; this one fills a span of the
leg with axial stations at the same kind of pitch, and builds outward from the
leg face in layers when one run is not enough.

Two windings share a window by taking different spans, exactly as two
windings share a toroid by taking different sectors, so the placement concept
carries across without either family knowing about the other's coordinates.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from inductor_designer.geometry.ecore.body import FinishedECore


class LegPackingError(ValueError):
    """The winding does not fit the window, and how many turns did.

    Mirrors ``PackingError``: the caller reports the shortfall, so the count
    that fit travels with the refusal rather than being recomputed.
    """

    def __init__(self, winding_id: str, max_turns: int, message: str) -> None:
        super().__init__(message)
        self.winding_id = winding_id
        self.max_turns = max_turns


@dataclass(frozen=True, slots=True)
class LegWindingSpec:
    winding_id: str
    turns: int
    insulated_diameter_m: float
    window_start_m: float
    window_span_m: float
    min_spacing_m: float
    min_clearance_m: float


@dataclass(frozen=True, slots=True)
class PackedLegLayer:
    """One run of turns along the leg, `offset_m` out from the leg face."""

    index: int
    offset_m: float
    station_m: tuple[float, ...]
    pitch_m: float


@dataclass(frozen=True, slots=True)
class PackedLegWinding:
    winding_id: str
    insulated_diameter_m: float
    window_start_m: float
    window_span_m: float
    layers: tuple[PackedLegLayer, ...]
    wire_length_m: float


def _turn_length_m(core: FinishedECore, offset_m: float, diameter_m: float) -> float:
    """One turn around the centre leg at this layer.

    A rounded rectangle: the leg's own perimeter, plus the four corner arcs
    the wire's own radius sweeps at that offset. Expressed as the closed-form
    perimeter rather than by sampling `LineSegment`/`ArcSegment`, because the
    only consumer here is a wire length -- the drawn path is the preview's
    business (task 7).
    """
    radius = offset_m + diameter_m / 2.0
    return (
        2.0 * (core.centre_leg_width_m + core.depth_m) + 2.0 * math.pi * radius
    )


def pack_leg_winding(core: FinishedECore, spec: LegWindingSpec) -> PackedLegWinding:
    """Fill the winding's span, layer by layer outward from the leg face."""
    pitch = spec.insulated_diameter_m + spec.min_spacing_m
    if pitch <= 0.0 or not math.isfinite(pitch):
        raise LegPackingError(spec.winding_id, 0, "Wire pitch must be a positive length")

    # The window's usable depth: its width, less the clearance the wire has to
    # keep from the outer leg it faces.
    usable = core.window_width_m - spec.min_clearance_m
    max_layers = int(math.floor(usable / spec.insulated_diameter_m))
    if max_layers < 1:
        raise LegPackingError(
            spec.winding_id,
            0,
            f"Wire does not fit the window at layer 1: "
            f"{spec.insulated_diameter_m * 1000.0:.2f} mm of wire in "
            f"{usable * 1000.0:.1f} mm of usable window",
        )

    per_layer = int(math.floor(spec.window_span_m / pitch))
    if per_layer < 1:
        raise LegPackingError(
            spec.winding_id,
            0,
            f"Not one turn fits the {spec.window_span_m * 1000.0:.1f} mm span at a "
            f"{pitch * 1000.0:.2f} mm pitch",
        )

    capacity = per_layer * max_layers
    if spec.turns > capacity:
        raise LegPackingError(
            spec.winding_id,
            capacity,
            f"{spec.turns} turns do not fit the window: only {capacity} fit "
            f"({max_layers} layer(s) of {per_layer})",
        )

    layers: list[PackedLegLayer] = []
    remaining = spec.turns
    wire_length = 0.0
    for index in range(1, max_layers + 1):
        if remaining <= 0:
            break
        count = min(per_layer, remaining)
        remaining -= count
        offset = (index - 1) * spec.insulated_diameter_m
        # Centred in the span, so a partly filled layer does not crowd one
        # end of the window.
        used = (count - 1) * pitch
        first = spec.window_start_m + (spec.window_span_m - used) / 2.0
        layers.append(
            PackedLegLayer(
                index=index,
                offset_m=offset,
                station_m=tuple(round(first + step * pitch, 12) for step in range(count)),
                pitch_m=pitch,
            )
        )
        wire_length += count * _turn_length_m(core, offset, spec.insulated_diameter_m)

    return PackedLegWinding(
        winding_id=spec.winding_id,
        insulated_diameter_m=spec.insulated_diameter_m,
        window_start_m=spec.window_start_m,
        window_span_m=spec.window_span_m,
        layers=tuple(layers),
        wire_length_m=wire_length,
    )
