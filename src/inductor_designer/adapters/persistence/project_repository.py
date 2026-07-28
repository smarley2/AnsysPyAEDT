from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from inductor_designer.adapters.persistence.record_serde import (
    core_record_from_json,
    core_record_to_json,
)
from inductor_designer.adapters.persistence.schema_repository import SchemaRepository
from inductor_designer.domain.project import (
    CatalogCoreSelection,
    CoreOverride,
    CoreSelection,
    Design,
    InductorProject,
    ManualCoreSelection,
    MaterialRevisionSelection,
    MeshIntent,
    OperatingPoint,
    RequestedOutput,
    SimulationRecipe,
    WindingOperatingPoint,
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
        "terminalIntent": winding.terminal_intent,
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
        terminal_intent=data["terminalIntent"],
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


def _material_to_json(
    material: MaterialRevisionSelection | None,
) -> dict[str, object] | None:
    if material is None:
        return None
    return {
        "ref": {
            "manufacturer": material.ref.manufacturer,
            "name": material.ref.name,
            "grade": material.ref.grade,
        },
        "revisionId": material.revision_id,
        "bhSeriesId": material.bh_series_id,
        "snapshot": material_record_to_json(material.snapshot),
    }


def _material_from_json(
    data: Mapping[str, Any] | None,
) -> MaterialRevisionSelection | None:
    if data is None:
        return None
    ref = data["ref"]
    return MaterialRevisionSelection(
        ref=MaterialRef(ref["manufacturer"], ref["name"], ref["grade"]),
        revision_id=data["revisionId"],
        snapshot=material_record_from_json(data["snapshot"]),
        bh_series_id=data["bhSeriesId"],
    )


def _design_to_json(design: Design) -> dict[str, object]:
    return {
        "core": _core_to_json(design.core),
        "windings": [_winding_to_json(winding) for winding in design.windings],
        "coreMaterial": _material_to_json(design.core_material),
        "manualMaterialCompatibilityAcknowledged": (
            design.manual_material_compatibility_acknowledged
        ),
    }


def _design_from_json(data: Mapping[str, Any]) -> Design:
    return Design(
        core=_core_from_json(data["core"]),
        windings=tuple(_winding_from_json(winding) for winding in data["windings"]),
        core_material=_material_from_json(data["coreMaterial"]),
        manual_material_compatibility_acknowledged=data[
            "manualMaterialCompatibilityAcknowledged"
        ],
    )


def _operating_point_to_json(operating_point: OperatingPoint) -> dict[str, object]:
    return {
        "frequencyHz": operating_point.frequency_hz,
        "windingTemperatureC": operating_point.winding_temperature_c,
        "coreTemperatureC": operating_point.core_temperature_c,
        "windings": [
            {
                "windingId": winding.winding_id,
                "acRmsCurrentA": winding.ac_rms_current_a,
                "acPhaseDeg": winding.ac_phase_deg,
                "dcCurrentA": winding.dc_current_a,
                "currentDirection": winding.current_direction.value,
            }
            for winding in operating_point.windings
        ],
    }


def _operating_point_from_json(data: Mapping[str, Any]) -> OperatingPoint:
    return OperatingPoint(
        frequency_hz=data["frequencyHz"],
        winding_temperature_c=data["windingTemperatureC"],
        core_temperature_c=data["coreTemperatureC"],
        windings=tuple(
            WindingOperatingPoint(
                winding_id=winding["windingId"],
                ac_rms_current_a=winding["acRmsCurrentA"],
                ac_phase_deg=winding["acPhaseDeg"],
                dc_current_a=winding["dcCurrentA"],
                current_direction=CurrentDirection(winding["currentDirection"]),
            )
            for winding in data["windings"]
        ),
    )


def _simulation_recipe_to_json(recipe: SimulationRecipe) -> dict[str, object]:
    return {
        "meshIntent": recipe.mesh_intent.value,
        "maximumPasses": recipe.maximum_passes,
        "percentError": recipe.percent_error,
        "requestedOutputs": [output.value for output in recipe.requested_outputs],
    }


def _simulation_recipe_from_json(data: Mapping[str, Any]) -> SimulationRecipe:
    return SimulationRecipe(
        mesh_intent=MeshIntent(data["meshIntent"]),
        maximum_passes=data["maximumPasses"],
        percent_error=data["percentError"],
        requested_outputs=tuple(RequestedOutput(output) for output in data["requestedOutputs"]),
    )


def project_to_document(project: InductorProject) -> dict[str, object]:
    return {
        "schemaVersion": 5,
        "projectId": project.project_id,
        "metadata": {"name": project.name, "description": project.description},
        "design": _design_to_json(project.design),
        "operatingPoint": _operating_point_to_json(project.operating_point),
        "simulationRecipe": _simulation_recipe_to_json(project.simulation_recipe),
    }


def project_from_document(document: Mapping[str, Any]) -> InductorProject:
    metadata = document["metadata"]
    return InductorProject(
        project_id=document["projectId"],
        name=metadata["name"],
        description=metadata["description"],
        design=_design_from_json(document["design"]),
        operating_point=_operating_point_from_json(document["operatingPoint"]),
        simulation_recipe=_simulation_recipe_from_json(document["simulationRecipe"]),
    )


class ProjectRepository:
    def __init__(self, schemas: SchemaRepository) -> None:
        self._schemas = schemas

    def load(self, path: Path) -> InductorProject:
        loaded: Any = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError(f"Project document is not a JSON object: {path}")
        self._schemas.validate_project(loaded)
        return project_from_document(loaded)

    def save(self, project: InductorProject, path: Path) -> None:
        document = project_to_document(project)
        self._schemas.validate_project(document)
        serialized = json.dumps(document, indent=2, sort_keys=True) + "\n"
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(
                descriptor,
                "w",
                encoding="utf-8",
                newline="",
            ) as stream:
                descriptor = -1
                stream.write(serialized)
                stream.flush()
            os.replace(temporary_path, path)
        finally:
            if descriptor != -1:
                os.close(descriptor)
            temporary_path.unlink(missing_ok=True)
