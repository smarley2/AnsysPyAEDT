from __future__ import annotations

import math
from dataclasses import dataclass

from inductor_designer.geometry.core_solid import FinishedCore
from inductor_designer.geometry.turn_path import radial_build_m, turn_loop_length_m


class PackingError(ValueError):
    def __init__(self, winding_id: str, max_turns: int, message: str) -> None:
        super().__init__(message)
        self.winding_id = winding_id
        self.max_turns = max_turns


@dataclass(frozen=True, slots=True)
class WindingSpec:
    winding_id: str
    turns: int
    insulated_diameter_m: float
    start_deg: float
    sector_deg: float
    min_spacing_m: float
    min_clearance_m: float


@dataclass(frozen=True, slots=True)
class PackedLayer:
    index: int
    radial_build_m: float
    station_deg: tuple[float, ...]
    pitch_deg: float
    min_pitch_deg: float


@dataclass(frozen=True, slots=True)
class PackedWinding:
    winding_id: str
    insulated_diameter_m: float
    sector_deg: float
    start_deg: float
    layers: tuple[PackedLayer, ...]
    lead_in_deg: float
    lead_out_deg: float
    wire_length_m: float


def _min_pitch_rad(core: FinishedCore, layer: int, d: float, spacing: float) -> float | None:
    """Minimum angular pitch on layer `layer`, or None when the layer cannot exist."""
    r_k = core.r_inner_m - radial_build_m(layer, d)
    if r_k - d / 2.0 <= 0.0:
        return None
    ratio = (d + spacing) / (2.0 * r_k)
    if ratio >= 1.0:
        return None
    return 2.0 * math.asin(ratio)


def pack_winding(core: FinishedCore, spec: WindingSpec) -> PackedWinding:
    d = spec.insulated_diameter_m
    pitch_1 = _min_pitch_rad(core, 1, d, spec.min_spacing_m)
    if pitch_1 is None:
        raise PackingError(spec.winding_id, 0, "Wire does not fit the core bore at layer 1")
    margin = pitch_1
    usable = math.radians(spec.sector_deg) - 2.0 * margin

    capacities: list[tuple[int, float, float]] = []  # (layer, min_pitch_rad, capacity)
    layer = 1
    while True:
        min_pitch = _min_pitch_rad(core, layer, d, spec.min_spacing_m)
        if min_pitch is None:
            break
        capacity = math.floor(usable / min_pitch) if usable >= min_pitch else 0
        if capacity <= 0:
            break
        capacities.append((layer, min_pitch, float(capacity)))
        layer += 1

    total_capacity = int(sum(capacity for _, _, capacity in capacities))
    if spec.turns > total_capacity:
        raise PackingError(
            spec.winding_id,
            total_capacity,
            f"Winding {spec.winding_id!r} needs {spec.turns} turns; "
            f"only {total_capacity} fit in sector {spec.sector_deg} deg",
        )

    layers: list[PackedLayer] = []
    remaining = spec.turns
    wire_length = 0.0
    for layer_index, min_pitch, layer_capacity in capacities:
        if remaining <= 0:
            break
        count = min(remaining, int(layer_capacity))
        remaining -= count
        pitch = usable / count
        start_rad = math.radians(spec.start_deg) + margin
        stations = tuple(
            round(math.degrees(start_rad + (i + 0.5) * pitch), 9) for i in range(count)
        )
        build = radial_build_m(layer_index, d)
        layers.append(
            PackedLayer(
                index=layer_index,
                radial_build_m=round(build, 9),
                station_deg=stations,
                pitch_deg=round(math.degrees(pitch), 9),
                min_pitch_deg=round(math.degrees(min_pitch), 9),
            )
        )
        # Design decision (reviewed 2026-07-14): each turn is one closed loop;
        # no turn-to-turn connector wire is modeled, so none is counted here.
        wire_length += count * turn_loop_length_m(core, layer_index, d)
    wire_length += 2.0 * 3.0 * d

    return PackedWinding(
        winding_id=spec.winding_id,
        insulated_diameter_m=d,
        sector_deg=spec.sector_deg,
        start_deg=spec.start_deg,
        layers=tuple(layers),
        lead_in_deg=round(spec.start_deg + math.degrees(margin) / 2.0, 9),
        lead_out_deg=round(spec.start_deg + spec.sector_deg - math.degrees(margin) / 2.0, 9),
        wire_length_m=round(wire_length, 9),
    )
