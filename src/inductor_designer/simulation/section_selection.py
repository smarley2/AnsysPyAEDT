"""Deterministic section selection (2026-08-10 representative cross sections).

Pure: the same project and the same run frequency produce the same sections,
in the same order, with the same identifiers, on any machine.
"""

from __future__ import annotations

from collections.abc import Sequence

from inductor_designer.domain.winding import WindingDefinition
from inductor_designer.simulation.sections import (
    CORE_FEATURE_PRECEDENCE,
    SECTION_DEDUPE_TOLERANCE_DEG,
    CoreSection,
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
