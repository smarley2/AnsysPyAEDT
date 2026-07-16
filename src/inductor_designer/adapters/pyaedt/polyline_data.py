from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from inductor_designer.geometry.primitives import ArcSegment, PathSegment, Vec3

_JOINT_TOLERANCE_M = 1e-9


@dataclass(frozen=True, slots=True)
class PolylineData:
    """Point list plus per-segment kinds for pyaedt create_polyline.

    ``kinds`` maps 1:1 to the input segments: a "Line" consumes two shared
    endpoints, an "Arc" consumes start/mid/end (pyaedt 3-point arc).
    """

    points: tuple[tuple[float, float, float], ...]
    kinds: tuple[str, ...]


def arc_midpoint(arc: ArcSegment) -> Vec3:
    return arc.sample(3)[1]


def polyline_data(segments: Sequence[PathSegment], *, closed: bool) -> PolylineData:
    if not segments:
        raise ValueError("polyline_data needs at least one segment")
    points: list[Vec3] = []
    kinds: list[str] = []

    def push(point: Vec3) -> None:
        if not points or (point - points[-1]).norm() > _JOINT_TOLERANCE_M:
            points.append(point)

    for segment in segments:
        push(segment.start)
        if isinstance(segment, ArcSegment):
            push(arc_midpoint(segment))
            push(segment.end())
            kinds.append("Arc")
        else:
            push(segment.end)
            kinds.append("Line")

    if closed and (points[-1] - points[0]).norm() > _JOINT_TOLERANCE_M:
        raise ValueError("Closed path does not return to its start")
    if closed:
        points[-1] = points[0]
    return PolylineData(
        points=tuple((round(p.x, 9), round(p.y, 9), round(p.z, 9)) for p in points),
        kinds=tuple(kinds),
    )
