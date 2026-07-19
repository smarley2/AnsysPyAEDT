from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from inductor_designer.adapters.persistence.record_serde import (
    core_record_from_json,
    core_record_to_json,
)
from inductor_designer.adapters.persistence.schema_repository import SchemaRepository
from inductor_designer.domain.aedt_target import AedtEdition, AedtRelease, ModelDimension
from inductor_designer.domain.project import (
    CatalogCoreSelection,
    CoreOverride,
    CoreSelection,
    InductorProject,
    ManualCoreSelection,
    MaterialRevisionSelection,
)
from inductor_designer.domain.winding import (
    ConductorMode,
    CurrentDirection,
    WindingDefinition,
    WindingDirection,
)
from inductor_designer.materials.identity import MaterialRef
from inductor_designer.materials.serde import (
    material_record_from_json,
    material_record_to_json,
)


def _winding_to_json(winding: WindingDefinition) -> dict[str, object]:
    return {
        "windingId": winding.winding_id,
        "label": winding.label,
        "turns": winding.turns,
        "conductor": winding.conductor_name,
        "mode": winding.mode.value,
        "startAngleDeg": winding.start_angle_deg,
        "sectorDeg": winding.sector_deg,
        "minSpacingM": winding.min_spacing_m,
        "minClearanceM": winding.min_clearance_m,
        "windingDirection": winding.winding_direction.value,
        "currentDirection": winding.current_direction.value,
        "terminalIntent": winding.terminal_intent,
        "acMagnitudeA": winding.ac_magnitude_a,
        "acPhaseDeg": winding.ac_phase_deg,
        "frequencyHz": winding.frequency_hz,
        "dcCurrentA": winding.dc_current_a,
    }


def _winding_from_json(data: Mapping[str, Any]) -> WindingDefinition:
    return WindingDefinition(
        winding_id=data["windingId"],
        label=data["label"],
        turns=data["turns"],
        conductor_name=data["conductor"],
        mode=ConductorMode(data["mode"]),
        start_angle_deg=data["startAngleDeg"],
        sector_deg=data["sectorDeg"],
        min_spacing_m=data["minSpacingM"],
        min_clearance_m=data["minClearanceM"],
        winding_direction=WindingDirection(data["windingDirection"]),
        current_direction=CurrentDirection(data["currentDirection"]),
        terminal_intent=data["terminalIntent"],
        ac_magnitude_a=data["acMagnitudeA"],
        ac_phase_deg=data["acPhaseDeg"],
        frequency_hz=data["frequencyHz"],
        dc_current_a=data["dcCurrentA"],
    )


def _core_to_json(core: CoreSelection | None) -> dict[str, object] | None:
    if core is None:
        return None
    if isinstance(core, ManualCoreSelection):
        return {
            "kind": "manual",
            "outerDiameterM": core.outer_diameter_m,
            "innerDiameterM": core.inner_diameter_m,
            "heightM": core.height_m,
            "cornerRadiusM": core.corner_radius_m,
        }
    return {
        "kind": "catalog",
        "partNumber": core.part_number,
        "snapshot": core_record_to_json(core.snapshot),
        "overrides": [
            {"field": o.field, "value": o.value, "reason": o.reason} for o in core.overrides
        ],
    }


def _core_from_json(data: Mapping[str, Any] | None) -> CoreSelection | None:
    if data is None:
        return None
    if data["kind"] == "manual":
        return ManualCoreSelection(
            outer_diameter_m=data["outerDiameterM"],
            inner_diameter_m=data["innerDiameterM"],
            height_m=data["heightM"],
            corner_radius_m=data["cornerRadiusM"],
        )
    return CatalogCoreSelection(
        part_number=data["partNumber"],
        snapshot=core_record_from_json(data["snapshot"]),
        overrides=tuple(
            CoreOverride(o["field"], o["value"], o["reason"]) for o in data["overrides"]
        ),
    )


def project_to_document(project: InductorProject) -> dict[str, object]:
    return {
        "schemaVersion": 4,
        "projectId": project.project_id,
        "metadata": {"name": project.name, "description": project.description},
        "target": {
            "aedtRelease": str(project.target_release),
            "edition": project.target_edition.value,
            "dimensionMode": project.dimension_mode.value,
        },
        "core": _core_to_json(project.core),
        "windings": [_winding_to_json(w) for w in project.windings],
        "materials": [
            {
                "ref": {
                    "manufacturer": material.ref.manufacturer,
                    "name": material.ref.name,
                    "grade": material.ref.grade,
                },
                "revisionId": material.revision_id,
                "bhSeriesId": material.bh_series_id,
                "snapshot": material_record_to_json(material.snapshot),
            }
            for material in project.materials
        ],
    }


def project_from_document(document: Mapping[str, Any]) -> InductorProject:
    metadata = document["metadata"]
    target = document["target"]
    return InductorProject(
        project_id=document["projectId"],
        name=metadata["name"],
        description=metadata.get("description", ""),
        target_release=AedtRelease.parse(target["aedtRelease"]),
        target_edition=AedtEdition(target["edition"]),
        dimension_mode=ModelDimension(target["dimensionMode"]),
        core=_core_from_json(document["core"]),
        windings=tuple(_winding_from_json(w) for w in document["windings"]),
        materials=tuple(
            MaterialRevisionSelection(
                ref=MaterialRef(
                    item["ref"]["manufacturer"],
                    item["ref"]["name"],
                    item["ref"]["grade"],
                ),
                revision_id=item["revisionId"],
                snapshot=material_record_from_json(item["snapshot"]),
                bh_series_id=item.get("bhSeriesId"),
            )
            for item in document.get("materials", [])
        ),
    )


class ProjectRepository:
    def __init__(self, schemas: SchemaRepository) -> None:
        self._schemas = schemas

    def load(self, path: Path) -> InductorProject:
        loaded: Any = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError(f"Project document is not a JSON object: {path}")
        migrated = self._schemas.migrate_project(loaded)
        return project_from_document(migrated)

    def save(self, project: InductorProject, path: Path) -> None:
        document = project_to_document(project)
        self._schemas.validate_project(document)
        path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
