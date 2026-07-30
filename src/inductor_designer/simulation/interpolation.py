"""Shared linear interpolation over a recorded (x, y) point series.

Both the magnetic estimate (B-H curves) and the core-loss estimate (loss
tables and Steinmetz-fit envelopes) interpolate a recorded curve and must
never extrapolate beyond it. This is the one place that guards both bounds,
so the guard cannot drift out of sync between the two call sites the way it
previously did -- the B-H interpolator forgot to guard the lower bound and
silently clamped below-range input to the lowest recorded value instead of
refusing it.
"""

from __future__ import annotations

from collections.abc import Sequence


def interpolate_within_range(points: Sequence[tuple[float, float]], x: float) -> float | None:
    """Linearly interpolate y at x from (x, y) points.

    Returns None when x falls outside the recorded [min_x, max_x] range, or
    when there are no points at all -- callers refuse rather than extrapolate.
    """
    ordered = sorted(points, key=lambda point: point[0])
    if not ordered or x < ordered[0][0] or x > ordered[-1][0]:
        return None
    previous = ordered[0]
    for point in ordered:
        if point[0] == x:
            return point[1]
        if point[0] > x:
            span = point[0] - previous[0]
            if span <= 0.0:
                return point[1]
            fraction = (x - previous[0]) / span
            return previous[1] + fraction * (point[1] - previous[1])
        previous = point
    return ordered[-1][1]
