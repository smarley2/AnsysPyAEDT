from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from inductor_designer.geometry.core_solid import FinishedCore
from inductor_designer.geometry.packing import PackedWinding
from inductor_designer.geometry.primitives import Vec3, sample_path
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


def tessellate_winding(
    core: FinishedCore, packing: PackedWinding, tube_sides: int = 12
) -> Mesh:
    d = packing.insulated_diameter_m
    radius = d / 2.0
    meshes: list[Mesh] = []
    # Design decision (reviewed 2026-07-14): each turn is one closed loop; no
    # turn-to-turn connector is modeled or drawn. Maxwell (M3) assigns one
    # coil terminal per closed turn and groups them into the winding.
    for layer in packing.layers:
        for station in layer.station_deg:
            loop = build_turn_loop(core, layer.index, d, station)
            # build_turn_loop's segments already trace a closed path, so the
            # sampled polyline's last point already coincides with its first
            # (to float precision) — appending it again would create a
            # zero-length step and blow up tangent computation in tube().
            points = list(sample_path(loop))
            meshes.append(tube(points, radius, tube_sides))
    return _merge(meshes)
