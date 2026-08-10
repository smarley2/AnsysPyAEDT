"""Deterministic section selection (2026-08-10 representative cross sections).

Pure: the same project and the same run frequency produce the same sections,
in the same order, with the same identifiers, on any machine.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from inductor_designer.domain.winding import WindingDefinition
from inductor_designer.geometry.core_solid import FinishedCore
from inductor_designer.geometry.primitives import half_plane_point
from inductor_designer.geometry.turn_path import radial_build_m
from inductor_designer.simulation.sections import (
    CONDUCTOR_STATIONS,
    CORE_FEATURE_PRECEDENCE,
    SECTION_DEDUPE_TOLERANCE_DEG,
    ConductorSection,
    CoreSection,
)
from inductor_designer.simulation.winding_estimate import (
    COPPER_ALPHA_20_PER_C,
    COPPER_MAX_TEMPERATURE_C,
    COPPER_MIN_TEMPERATURE_C,
    COPPER_RHO_20_OHM_M,
)


def _normalize(azimuth_deg: float) -> float:
    value = azimuth_deg % 360.0
    return 0.0 if value == 0.0 else value


def _spans(
    windings: Sequence[WindingDefinition],
) -> tuple[tuple[float, float], ...]:
    """Each winding as ``(start, sector)`` with the start normalized."""
    return tuple(
        (_normalize(winding.start_angle_deg), winding.sector_deg)
        for winding in windings
    )


def _gap_midpoints(spans: Sequence[tuple[float, float]]) -> tuple[float, ...]:
    """Midpoint of every azimuthal arc no winding sector covers."""
    if not spans:
        return ()
    covered = _covered_arcs(spans)
    gaps: list[float] = []
    for index, (_start, end) in enumerate(covered):
        next_start = covered[(index + 1) % len(covered)][0]
        gap = (next_start - end) % 360.0
        if gap > SECTION_DEDUPE_TOLERANCE_DEG:
            gaps.append(_normalize(end + gap / 2.0))
    return tuple(sorted(gaps))


def _covered_arcs(
    spans: Sequence[tuple[float, float]],
) -> list[tuple[float, float]]:
    """Merged ``(start, end)`` arcs, unwrapped, sorted by start."""
    arcs = sorted((start, start + sector) for start, sector in spans)
    merged: list[tuple[float, float]] = []
    for start, end in arcs:
        if merged and start <= merged[-1][1] + SECTION_DEDUPE_TOLERANCE_DEG:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return [(_normalize(start), _normalize(end)) for start, end in merged]


def select_core_sections(
    windings: Sequence[WindingDefinition],
) -> tuple[CoreSection, ...]:
    """Feature-anchored r-z half-planes (design section 5).

    Three planes per winding span - start, midpoint, end - plus the midpoint of
    every uncovered azimuthal gap, deduplicated within
    ``SECTION_DEDUPE_TOLERANCE_DEG`` keeping the higher-precedence feature.
    """
    candidates: list[tuple[float, str]] = []
    for winding in windings:
        start = _normalize(winding.start_angle_deg)
        candidates.append((start, "span-start"))
        candidates.append((_normalize(start + winding.sector_deg / 2.0), "span-mid"))
        candidates.append((_normalize(start + winding.sector_deg), "span-end"))
    candidates.extend((azimuth, "gap-mid") for azimuth in _gap_midpoints(_spans(windings)))

    kept: list[tuple[float, str]] = []
    for azimuth, feature in sorted(
        candidates, key=lambda item: (item[0], CORE_FEATURE_PRECEDENCE.index(item[1]))
    ):
        collision = next(
            (
                index
                for index, (existing, _) in enumerate(kept)
                if _within_tolerance(existing, azimuth)
            ),
            None,
        )
        if collision is None:
            kept.append((azimuth, feature))
            continue
        existing_feature = kept[collision][1]
        if CORE_FEATURE_PRECEDENCE.index(feature) < CORE_FEATURE_PRECEDENCE.index(
            existing_feature
        ):
            kept[collision] = (kept[collision][0], feature)

    return tuple(
        CoreSection(
            section_id=f"core.{index:02d}.{feature}",
            azimuth_deg=azimuth,
            feature=feature,
        )
        for index, (azimuth, feature) in enumerate(sorted(kept))
    )


def _within_tolerance(first: float, second: float) -> bool:
    difference = abs(first - second) % 360.0
    return min(difference, 360.0 - difference) < SECTION_DEDUPE_TOLERANCE_DEG


MU_0 = 4.0e-7 * math.pi


def skin_depth_m(frequency_hz: float, winding_temperature_c: float) -> float | None:
    """Copper skin depth, or ``None`` where resistivity is not validated.

    The resistivity model and its validated temperature range are the ones
    already used for the preliminary wire-loss estimate; this introduces no new
    material constant.
    """
    if not (
        COPPER_MIN_TEMPERATURE_C
        <= winding_temperature_c
        <= COPPER_MAX_TEMPERATURE_C
    ):
        return None
    if frequency_hz <= 0.0:
        return math.inf
    rho = COPPER_RHO_20_OHM_M * (
        1.0 + COPPER_ALPHA_20_PER_C * (winding_temperature_c - 20.0)
    )
    return math.sqrt(rho / (math.pi * frequency_hz * MU_0))


def _station_points(
    core: FinishedCore,
    layer: int,
    insulated_diameter_m: float,
    station_deg: float,
) -> dict[str, tuple[tuple[float, float, float], tuple[float, float, float]]]:
    """Centre and wire tangent at each named station of one turn.

    The turn is the modelled closed loop: up through the bore, out across the
    top face, down the outer wall, back across the bottom face. The tangent at
    each station is that leg's direction, so a disc built on it cuts the wire
    transversely.
    """
    build = radial_build_m(layer, insulated_diameter_m)
    r_inner = core.r_inner_m - build
    r_outer = core.r_outer_m + build
    half_height = core.half_height_m
    axial = (0.0, 0.0, 1.0)
    radial = half_plane_point(station_deg, 1.0, 0.0)
    radial_unit = (radial.x, radial.y, 0.0)

    def point(r: float, z: float) -> tuple[float, float, float]:
        location = half_plane_point(station_deg, r, z)
        return (location.x, location.y, location.z)

    return {
        # In the bore and on the outer wall the wire runs axially; across the
        # faces it runs radially.
        "inner-bore": (point(r_inner, 0.0), axial),
        "top-face": (
            point((core.r_inner_m + core.r_outer_m) / 2.0, half_height + build),
            radial_unit,
        ),
        "outer-wall": (point(r_outer, 0.0), axial),
        "bottom-face": (
            point((core.r_inner_m + core.r_outer_m) / 2.0, -(half_height + build)),
            radial_unit,
        ),
    }


def select_conductor_sections(
    *,
    core: FinishedCore,
    winding_id: str,
    turn_count: int,
    wire_radius_m: float,
    insulated_diameter_m: float,
    layer: int,
    station_deg: float,
    frequency_hz: float,
    winding_temperature_c: float,
) -> tuple[ConductorSection, ...]:
    """Skin-depth-gated discs perpendicular to the wire (design section 6).

    One disc represents the winding exactly while the current distribution is
    uniform: at DC, or wherever the skin depth is not smaller than the wire
    radius. Below that, proximity crowding makes position matter and four
    stations sample it. A temperature outside the validated copper range leaves
    the gate unevaluable, and the conservative four-station branch is taken.
    """
    if turn_count <= 0:
        return ()
    turn_index = (turn_count - 1) // 2
    depth = skin_depth_m(frequency_hz, winding_temperature_c)
    uniform = depth is not None and depth >= wire_radius_m
    stations = CONDUCTOR_STATIONS[:1] if uniform else CONDUCTOR_STATIONS
    points = _station_points(core, layer, insulated_diameter_m, station_deg)
    return tuple(
        ConductorSection(
            section_id=f"winding.{winding_id}.turn{turn_index:02d}.{station}",
            winding_id=winding_id,
            turn_index=turn_index,
            station=station,
            center_m=points[station][0],
            normal=points[station][1],
            radius_m=wire_radius_m,
        )
        for station in stations
    )
