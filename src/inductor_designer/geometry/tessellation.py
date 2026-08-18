from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from inductor_designer.domain.winding import CurrentDirection, WindingDirection, mmf_sign
from inductor_designer.geometry.core_solid import FinishedCore
from inductor_designer.geometry.packing import PackedLayer, PackedWinding, start_azimuth_deg
from inductor_designer.geometry.primitives import Vec3, half_plane_point, sample_path
from inductor_designer.geometry.turn_path import build_turn_loop


@dataclass(frozen=True, slots=True)
class Mesh:
    positions: tuple[float, ...]
    normals: tuple[float, ...]

    def __post_init__(self) -> None:
        if len(self.positions) != len(self.normals):
            raise ValueError("positions and normals must have equal length")
        if len(self.positions) % 9 != 0:
            raise ValueError("triangle soup length must be divisible by 9")


def _merge(meshes: Sequence[Mesh]) -> Mesh:
    positions: list[float] = []
    normals: list[float] = []
    for mesh in meshes:
        positions.extend(mesh.positions)
        normals.extend(mesh.normals)
    return Mesh(tuple(positions), tuple(normals))


def _emit_quad(
    positions: list[float],
    normals: list[float],
    a: Vec3,
    b: Vec3,
    c: Vec3,
    d: Vec3,
    na: Vec3,
    nb: Vec3,
    nc: Vec3,
    nd: Vec3,
) -> None:
    for tri in ((a, b, c), (a, c, d)):
        norms = {id(a): na, id(b): nb, id(c): nc, id(d): nd}
        for vertex in tri:
            positions.extend((vertex.x, vertex.y, vertex.z))
            n = norms[id(vertex)]
            normals.extend((n.x, n.y, n.z))


def _cross_section_outline(core: FinishedCore, corner_samples: int) -> list[tuple[float, float]]:
    """Closed (r, z) outline of the cross-section, counter-clockwise."""
    c = core.corner_radius_m
    ri, ro, hh = core.r_inner_m, core.r_outer_m, core.half_height_m
    if c <= 0.0:
        return [(ri, -hh), (ro, -hh), (ro, hh), (ri, hh)]
    outline: list[tuple[float, float]] = []
    corners = (
        ((ro - c, -(hh - c)), -90.0),
        ((ro - c, hh - c), 0.0),
        ((ri + c, hh - c), 90.0),
        ((ri + c, -(hh - c)), 180.0),
    )
    for (cr, cz), start_deg in corners:
        for i in range(corner_samples + 1):
            angle = math.radians(start_deg + 90.0 * i / corner_samples)
            outline.append((cr + c * math.cos(angle), cz + c * math.sin(angle)))
    return outline


def tessellate_core(
    core: FinishedCore, angular_segments: int = 96, corner_samples: int = 4
) -> Mesh:
    outline = _cross_section_outline(core, corner_samples)
    count = len(outline)
    positions: list[float] = []
    normals: list[float] = []

    def at(theta: float, r: float, z: float) -> Vec3:
        return Vec3(r * math.cos(theta), r * math.sin(theta), z)

    for s in range(angular_segments):
        t0 = 2.0 * math.pi * s / angular_segments
        t1 = 2.0 * math.pi * (s + 1) / angular_segments
        for i in range(count):
            (r0, z0) = outline[i]
            (r1, z1) = outline[(i + 1) % count]
            a = at(t0, r0, z0)
            b = at(t1, r0, z0)
            c_v = at(t1, r1, z1)
            d = at(t0, r1, z1)
            edge1 = b - a
            edge2 = d - a
            face_n = edge1.cross(edge2)
            n = face_n.normalized() if face_n.norm() > 0 else Vec3(0.0, 0.0, 1.0)
            _emit_quad(positions, normals, a, b, c_v, d, n, n, n, n)
    return Mesh(tuple(positions), tuple(normals))


def _frames(points: Sequence[Vec3]) -> list[tuple[Vec3, Vec3, Vec3]]:
    """(tangent, normal, binormal) per point via parallel transport."""
    if len(points) < 2:
        raise ValueError("tube needs at least 2 points")
    tangents: list[Vec3] = []
    for i in range(len(points)):
        if i == 0:
            direction = points[1] - points[0]
        elif i == len(points) - 1:
            direction = points[-1] - points[-2]
        else:
            direction = points[i + 1] - points[i - 1]
        if direction.norm() == 0.0:
            raise ValueError("degenerate step in tube path")
        tangents.append(direction.normalized())
    seed = Vec3(0.0, 0.0, 1.0)
    if abs(tangents[0].dot(seed)) > 0.9:
        seed = Vec3(1.0, 0.0, 0.0)
    normal = (seed - tangents[0].scaled(tangents[0].dot(seed))).normalized()
    frames: list[tuple[Vec3, Vec3, Vec3]] = []
    for tangent in tangents:
        projected = normal - tangent.scaled(tangent.dot(normal))
        if projected.norm() < 1e-9:
            projected = seed - tangent.scaled(tangent.dot(seed))
        normal = projected.normalized()
        frames.append((tangent, normal, tangent.cross(normal)))
    return frames


def tube(points: Sequence[Vec3], radius: float, sides: int = 12) -> Mesh:
    frames = _frames(points)
    rings: list[list[Vec3]] = []
    ring_normals: list[list[Vec3]] = []
    for point, (_, normal, binormal) in zip(points, frames, strict=True):
        ring: list[Vec3] = []
        ring_n: list[Vec3] = []
        for s in range(sides):
            phi = 2.0 * math.pi * s / sides
            radial = normal.scaled(math.cos(phi)) + binormal.scaled(math.sin(phi))
            ring.append(point + radial.scaled(radius))
            ring_n.append(radial)
        rings.append(ring)
        ring_normals.append(ring_n)
    positions: list[float] = []
    normals: list[float] = []
    for i in range(len(rings) - 1):
        for s in range(sides):
            s_next = (s + 1) % sides
            _emit_quad(
                positions,
                normals,
                rings[i][s],
                rings[i][s_next],
                rings[i + 1][s_next],
                rings[i + 1][s],
                ring_normals[i][s],
                ring_normals[i][s_next],
                ring_normals[i + 1][s_next],
                ring_normals[i + 1][s],
            )
    return Mesh(tuple(positions), tuple(normals))


def _cone(base: Vec3, tip: Vec3, radius: float, sides: int = 12) -> Mesh:
    """Solid cone from a disc at `base` to `tip`, for an arrow head."""
    axis = tip - base
    if axis.norm() == 0.0:
        raise ValueError("cone needs a non-zero axis")
    tangent = axis.normalized()
    seed = Vec3(0.0, 0.0, 1.0)
    if abs(tangent.dot(seed)) > 0.9:
        seed = Vec3(1.0, 0.0, 0.0)
    normal = (seed - tangent.scaled(tangent.dot(seed))).normalized()
    binormal = tangent.cross(normal)
    rim: list[tuple[Vec3, Vec3]] = []
    for s in range(sides):
        phi = 2.0 * math.pi * s / sides
        radial = normal.scaled(math.cos(phi)) + binormal.scaled(math.sin(phi))
        rim.append((base + radial.scaled(radius), radial))
    positions: list[float] = []
    normals: list[float] = []
    back = tangent.scaled(-1.0)
    for s in range(sides):
        (first, first_n), (second, second_n) = rim[s], rim[(s + 1) % sides]
        for vertex, vertex_n in (
            (first, first_n),
            (second, second_n),
            (tip, tangent),
            # Cap, so the head reads solid rather than hollow from behind.
            (first, back),
            (base, back),
            (second, back),
        ):
            positions.extend((vertex.x, vertex.y, vertex.z))
            normals.extend((vertex_n.x, vertex_n.y, vertex_n.z))
    return Mesh(tuple(positions), tuple(normals))


def _rounded_corner(
    previous: Vec3, corner: Vec3, following: Vec3, fillet: float, samples: int = 6
) -> list[Vec3]:
    """Quadratic Bezier easing a right-angle turn, so the tube does not pinch."""
    start = corner + (previous - corner).normalized().scaled(fillet)
    end = corner + (following - corner).normalized().scaled(fillet)
    points: list[Vec3] = []
    for index in range(samples + 1):
        t = index / samples
        points.append(
            start.scaled((1 - t) ** 2)
            + corner.scaled(2 * (1 - t) * t)
            + end.scaled(t**2)
        )
    return points


def wrap_arrow_path(
    core: FinishedCore,
    packing: PackedWinding,
    sense: WindingDirection,
    current: CurrentDirection,
) -> tuple[Vec3, ...]:
    """The current-flow arrow's corner points, in metres, tip last.

    Positive ampere-turns run up through the bore, outward across the top face
    and down the outer wall. That is the same convention
    `simulation.maxwell_plan.winding_polarity` hands the solvers, where the bore
    leg is the winding's positive go leg, and the same one the 2D cut view draws
    as a dot in the bore. The first cut this arrow was built inverted, climbing
    the outer wall on positive ampere-turns, and the cut view is what caught it.

    Kept separate from the mesh so the direction it states can be asserted as
    points rather than dug back out of a triangle soup.
    """
    layer = packing.layers[0]
    station = layer.station_deg[len(layer.station_deg) // 2]
    d = packing.insulated_diameter_m
    # Wide clearance, not a hair's worth: at three wire diameters the arrow read
    # as one more turn in the fan. It has to float clear of the wire.
    clearance = 4.5 * d
    r_outer = core.r_outer_m + layer.radial_build_m + clearance
    r_inner = core.r_inner_m - layer.radial_build_m - 2.5 * d
    z_top = core.half_height_m + layer.radial_build_m + clearance
    z_low = -0.35 * core.half_height_m
    legs = (
        (r_inner, z_low),
        (r_inner, z_top),
        (r_outer, z_top),
        (r_outer, z_low),
    )
    if mmf_sign(sense, current) < 0.0:
        legs = legs[::-1]
    return tuple(half_plane_point(station, r, z) for r, z in legs)


def wrap_arrow(
    core: FinishedCore,
    packing: PackedWinding,
    sense: WindingDirection,
    current: CurrentDirection,
    tube_sides: int = 12,
) -> Mesh:
    """One staple beside the winding, along the way the current actually flows.

    Sense and current direction are two independent choices whose product is
    what drives the core (`domain.winding.mmf_sign`), so neither alone tells the
    reader where the current goes. This traces the product over one turn's
    cross-section: positive ampere-turns up through the bore, outward across the
    top face and down the outer wall, negative ones the other way round. Reverse
    the current on a counter-clockwise winding and the whole path turns round,
    exactly as the coil polarity handed to the solver does.

    Drawn as the wrap it is rather than one flat radial stroke, which
    foreshortened into a blob from the preview's camera, and offset a few wire
    diameters clear of the turns at the middle station of the first layer.
    """
    d = packing.insulated_diameter_m
    corners = wrap_arrow_path(core, packing, sense, current)
    tail, first, second, tip = corners
    # Stop the shaft short of the tip and hand the rest to the head.
    shaft_end = tip + (second - tip).normalized().scaled(4.5 * d)
    fillet = 3.5 * d
    path = [
        tail,
        *_rounded_corner(tail, first, second, fillet),
        *_rounded_corner(first, second, shaft_end, fillet),
        shaft_end,
    ]
    shaft = tube(path, radius=0.6 * d, sides=tube_sides)
    point = _cone(shaft_end, tip, radius=1.9 * d, sides=tube_sides)
    return _merge((shaft, point))


def _sphere(center: Vec3, radius: float, segments: int = 12) -> Mesh:
    """Latitude-longitude ball, for a marker bead."""
    rings: list[list[Vec3]] = []
    for row in range(segments // 2 + 1):
        theta = math.pi * row / (segments // 2)
        ring = [
            Vec3(
                math.sin(theta) * math.cos(2.0 * math.pi * column / segments),
                math.sin(theta) * math.sin(2.0 * math.pi * column / segments),
                math.cos(theta),
            )
            for column in range(segments)
        ]
        rings.append(ring)
    positions: list[float] = []
    normals: list[float] = []
    for row in range(len(rings) - 1):
        for column in range(segments):
            following = (column + 1) % segments
            a, b = rings[row][column], rings[row][following]
            c, d = rings[row + 1][following], rings[row + 1][column]
            _emit_quad(
                positions,
                normals,
                center + a.scaled(radius),
                center + b.scaled(radius),
                center + c.scaled(radius),
                center + d.scaled(radius),
                a,
                b,
                c,
                d,
            )
    return Mesh(tuple(positions), tuple(normals))


def start_bead(
    core: FinishedCore,
    packing: PackedWinding,
    sense: WindingDirection,
    segments: int = 12,
) -> Mesh:
    """A bead where the winding starts: its first turn, on the outer wall.

    Sector, lean and arrow all leave the two ends of a winding looking alike,
    so this says which end the wire was started from -- the lead the packing
    reserves before the first turn's station. Which of the two ends that is
    depends on the wound sense (`packing.start_azimuth_deg`); the bead sat at
    the low-azimuth end either way until 2026-08-18, so flipping the sense
    leaned the turns over but left the start where it was.
    """
    d = packing.insulated_diameter_m
    layer = packing.layers[0]
    radius = core.r_outer_m + layer.radial_build_m + 2.0 * d
    center = half_plane_point(start_azimuth_deg(packing, sense), radius, 0.0)
    return _sphere(center, 1.6 * d, segments)


def _lean_deg(layer: PackedLayer) -> float:
    """Azimuth the wire gains between the bottom face and the top face.

    A wound turn is not coplanar: the wire advances to the next turn's station
    as it wraps, so bottom to top -- half the way round the cross-section --
    covers half the turn-to-turn pitch. A single turn on a layer has no next
    station, so its own tight-pack pitch sets the lean instead.
    """
    pitch = layer.pitch_deg if len(layer.station_deg) > 1 else layer.min_pitch_deg
    return pitch / 2.0


def _leaned(points: Sequence[Vec3], lean_deg: float, sign: float) -> list[Vec3]:
    """Rotate each point about Z in proportion to its height.

    Which way the wire leans is the only thing that distinguishes a clockwise
    winding from a counter-clockwise one geometrically -- both wrap the same
    cross-section and both advance the same way round the core, so drawing the
    turns coplanar made the two senses pixel-identical, and the Windings screen
    could not show that the choice had taken effect.
    """
    span = max((abs(point.z) for point in points), default=0.0)
    if span <= 0.0 or lean_deg <= 0.0:
        return list(points)
    half = math.radians(sign * lean_deg) / 2.0
    leaned: list[Vec3] = []
    for point in points:
        angle = half * (point.z / span)
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        leaned.append(
            Vec3(
                point.x * cos_a - point.y * sin_a,
                point.x * sin_a + point.y * cos_a,
                point.z,
            )
        )
    return leaned


def tessellate_winding(
    core: FinishedCore,
    packing: PackedWinding,
    sense: WindingDirection,
    tube_sides: int = 12,
) -> Mesh:
    """Draw one winding's turns, leaning each the way `sense` winds it.

    `wrap_arrow` draws the marker that names that direction outright; it stays a
    separate mesh so this one holds nothing but wire.

    The lean is the preview's alone: the exported solver geometry keeps its
    turns coplanar, because the section discs B and J are integrated over are
    placed analytically and assume exactly that. Sense reaches the solver as
    the coil polarity instead, where it belongs -- it changes the flux, never
    the mesh.
    """
    d = packing.insulated_diameter_m
    radius = d / 2.0
    sign = 1.0 if sense is WindingDirection.COUNTERCLOCKWISE else -1.0
    meshes: list[Mesh] = []
    # Design decision (reviewed 2026-07-14): each turn is one closed loop; no
    # turn-to-turn connector is modeled or drawn. Maxwell (M3) assigns one
    # coil terminal per closed turn and groups them into the winding.
    for layer in packing.layers:
        lean_deg = _lean_deg(layer)
        for station in layer.station_deg:
            loop = build_turn_loop(core, layer.index, d, station)
            # build_turn_loop's segments already trace a closed path, so the
            # sampled polyline's last point already coincides with its first
            # (to float precision) — appending it again would create a
            # zero-length step and blow up tangent computation in tube().
            # Leaning rotates about Z by a height-dependent angle, which keeps
            # that coincidence: the two endpoints share a height.
            points = _leaned(list(sample_path(loop)), lean_deg, sign)
            meshes.append(tube(points, radius, tube_sides))
    return _merge(meshes)
