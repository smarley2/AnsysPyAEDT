from __future__ import annotations

import json
from typing import TYPE_CHECKING

from inductor_designer.geometry.collisions import occupancy_summary
from inductor_designer.geometry.naming import (
    core_name,
    lead_names,
    terminal_names,
    winding_names,
)
from inductor_designer.geometry.symmetry import SymmetryPlan

if TYPE_CHECKING:
    from inductor_designer.application.services.geometry_model import GeometryModel


def build_manifest(model: GeometryModel) -> dict[str, object]:
    occupancy = occupancy_summary(model.packings)
    windings: list[dict[str, object]] = []
    for packing in sorted(model.packings, key=lambda p: p.winding_id):
        names = winding_names(packing)
        layers: list[dict[str, object]] = []
        cursor = 0
        for layer in packing.layers:
            count = len(layer.station_deg)
            layers.append(
                {
                    "layer": layer.index,
                    "radialBuildM": layer.radial_build_m,
                    "pitchDeg": layer.pitch_deg,
                    "minPitchDeg": layer.min_pitch_deg,
                    "stationsDeg": list(layer.station_deg),
                    "turnNames": list(names[cursor : cursor + count]),
                }
            )
            cursor += count
        windings.append(
            {
                "windingId": packing.winding_id,
                "insulatedDiameterM": model.insulated_diameter_m[packing.winding_id],
                "bareDiameterM": model.bare_diameter_m[packing.winding_id],
                "sectorDeg": packing.sector_deg,
                "startDeg": packing.start_deg,
                "occupancy": occupancy[packing.winding_id],
                "leadInDeg": packing.lead_in_deg,
                "leadOutDeg": packing.lead_out_deg,
                "wireLengthM": packing.wire_length_m,
                "leadNames": list(lead_names(packing.winding_id)),
                "terminalNames": list(terminal_names(packing.winding_id)),
                "layers": layers,
            }
        )
    symmetry_plan: dict[str, object] | None = None
    symmetry_refusal: dict[str, object] | None = None
    if isinstance(model.symmetry, SymmetryPlan):
        symmetry_plan = {
            "multiplier": model.symmetry.multiplier,
            "sectorDeg": model.symmetry.sector_deg,
            "cutAnglesDeg": list(model.symmetry.cut_angles_deg),
        }
    else:
        symmetry_refusal = {
            "code": model.symmetry.code,
            "message": model.symmetry.message,
        }
    conductor_count = sum(len(w.conductors) for w in model.planar.windings)
    return {
        "schemaVersion": 1,
        "core": {
            "name": core_name(),
            "rInnerM": round(model.core.r_inner_m, 9),
            "rOuterM": round(model.core.r_outer_m, 9),
            "halfHeightM": round(model.core.half_height_m, 9),
            "cornerRadiusM": round(model.core.corner_radius_m, 9),
        },
        "windings": windings,
        "collisions": [
            {
                "kind": issue.kind,
                "windings": [issue.first_winding, issue.second_winding],
                "requiredM": issue.required_m,
                "actualM": issue.actual_m,
                "message": issue.message,
            }
            for issue in model.collisions
        ],
        "symmetry": symmetry_plan,
        "symmetryRefusal": symmetry_refusal,
        "planar": {
            "depthM": model.planar.depth_m,
            "rInnerM": round(model.planar.r_inner_m, 9),
            "rOuterM": round(model.planar.r_outer_m, 9),
            "conductorCount": conductor_count,
        },
    }


def manifest_json(model: GeometryModel) -> str:
    return json.dumps(build_manifest(model), indent=2, sort_keys=True) + "\n"
