from __future__ import annotations

import struct

from PySide6.QtCore import Property, QByteArray, QObject
from PySide6.QtGui import QVector3D
from PySide6.QtQuick3D import QQuick3DGeometry

from inductor_designer.application.services.geometry_model import GeometryModel
from inductor_designer.geometry.tessellation import Mesh, tessellate_core, tessellate_winding

_PALETTE = ("#e07a5f", "#3d9970", "#3f88c5", "#f2bb05", "#9656a1", "#2a9d8f")


class MeshGeometry(QQuick3DGeometry):
    def __init__(self, mesh: Mesh) -> None:
        super().__init__()
        vertex_count = len(mesh.positions) // 3
        interleaved = bytearray()
        for i in range(vertex_count):
            interleaved += struct.pack(
                "<6f",
                mesh.positions[3 * i],
                mesh.positions[3 * i + 1],
                mesh.positions[3 * i + 2],
                mesh.normals[3 * i],
                mesh.normals[3 * i + 1],
                mesh.normals[3 * i + 2],
            )
        self.setVertexData(QByteArray(bytes(interleaved)))
        self.setStride(24)
        self.addAttribute(
            QQuick3DGeometry.Attribute.PositionSemantic,  # type: ignore[attr-defined]
            0,
            QQuick3DGeometry.Attribute.F32Type,  # type: ignore[attr-defined]
        )
        self.addAttribute(
            QQuick3DGeometry.Attribute.NormalSemantic,  # type: ignore[attr-defined]
            12,
            QQuick3DGeometry.Attribute.F32Type,  # type: ignore[attr-defined]
        )
        self.setPrimitiveType(QQuick3DGeometry.PrimitiveType.Triangles)
        xs = mesh.positions[0::3]
        ys = mesh.positions[1::3]
        zs = mesh.positions[2::3]
        self.setBounds(
            QVector3D(min(xs), min(ys), min(zs)), QVector3D(max(xs), max(ys), max(zs))
        )


class PreviewEntry(QObject):
    def __init__(self, geometry: MeshGeometry, color: str, opacity: float) -> None:
        super().__init__()
        self._geometry = geometry
        self._color = color
        self._opacity = opacity
        geometry.setParent(self)

    @Property(QObject, constant=True)
    def geometry(self) -> MeshGeometry:
        return self._geometry

    @Property(str, constant=True)
    def color(self) -> str:
        return self._color

    @Property(float, constant=True)
    def opacity(self) -> float:
        return self._opacity


def build_preview_entries(model: GeometryModel) -> list[PreviewEntry]:
    entries = [PreviewEntry(MeshGeometry(tessellate_core(model.core)), "#8a8a8a", 0.35)]
    for i, packing in enumerate(sorted(model.packings, key=lambda p: p.winding_id)):
        mesh = tessellate_winding(model.core, packing)
        entries.append(PreviewEntry(MeshGeometry(mesh), _PALETTE[i % len(_PALETTE)], 1.0))
    return entries
