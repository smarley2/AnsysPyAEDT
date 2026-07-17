from __future__ import annotations

from collections.abc import Mapping, Sequence

from inductor_designer.domain.catalog_records import CoreRecord
from inductor_designer.domain.winding import (
    ConductorMode,
    CurrentDirection,
    WindingDefinition,
    WindingDirection,
)
from inductor_designer.geometry.core_profile import build_core_profile
from inductor_designer.geometry.core_solid import FinishedCore
from inductor_designer.geometry.naming import core_name, unique_identifiers
from inductor_designer.geometry.packing import PackedWinding
from inductor_designer.geometry.terminals import build_terminal_disk
from inductor_designer.geometry.turn_path import build_turn_loop
from inductor_designer.materials.records import MaterialRecord
from inductor_designer.simulation.capabilities import DcBiasDecision, DcBiasStrategy
from inductor_designer.simulation.maxwell_plan import (
    DESIGN_NAME,
    MATRIX_NAME,
    REGION_PADDING_PERCENT,
    SETUP_NAME,
    SOLUTION_TYPE,
    SOLUTION_TYPE_DC,
    CorePlan,
    Maxwell3dDesignPlan,
    MeshPlan,
    PlanBuildError,
    Polarity,
    RegionPlan,
    ReportPlan,
    SetupPlan,
    TerminalPlan,
    TurnPlan,
    WindingGroupPlan,
    core_material_spec,
    dc_bias_notes,
    material_spec_from_material_record,
)


def _polarity(definition: WindingDefinition) -> Polarity:
    positive = (definition.current_direction is CurrentDirection.FORWARD) == (
        definition.winding_direction is WindingDirection.COUNTERCLOCKWISE
    )
    return Polarity.POSITIVE if positive else Polarity.NEGATIVE


def build_maxwell3d_plan(
    core: FinishedCore,
    core_record: CoreRecord,
    packings: Sequence[PackedWinding],
    windings: Sequence[WindingDefinition],
    bare_diameter_m: Mapping[str, float],
    dc_bias_decision: DcBiasDecision | None = None,
    material_record: MaterialRecord | None = None,
) -> Maxwell3dDesignPlan:
    issues: list[str] = []
    by_id = {definition.winding_id: definition for definition in windings}
    if not packings:
        issues.append("No packed windings; nothing to export.")
    missing = [p.winding_id for p in packings if p.winding_id not in by_id]
    if missing:
        issues.append(f"Packings without winding definitions: {missing}.")
    frequencies = sorted({definition.frequency_hz for definition in windings})
    if len(frequencies) > 1:
        issues.append(f"All windings must share one frequency; got {frequencies}.")
    if issues:
        raise PlanBuildError(tuple(issues))
    material = (
        core_material_spec(core_record)
        if material_record is None
        else material_spec_from_material_record(core_record, material_record)
    )

    identifiers = unique_identifiers([packing.winding_id for packing in packings])
    groups: list[WindingGroupPlan] = []
    max_bare = 0.0
    for packing in packings:
        definition = by_id[packing.winding_id]
        base = identifiers[packing.winding_id]
        bare = bare_diameter_m[packing.winding_id]
        max_bare = max(max_bare, bare)
        polarity = _polarity(definition)
        turns: list[TurnPlan] = []
        counter = 1
        for layer in packing.layers:
            for station in layer.station_deg:
                name = f"{base}_L{layer.index:02d}_T{counter:03d}"
                turns.append(
                    TurnPlan(
                        name=name,
                        segments=build_turn_loop(
                            core, layer.index, packing.insulated_diameter_m, station
                        ),
                        bare_diameter_m=bare,
                        terminal=TerminalPlan(
                            name=f"{name}_Term",
                            disk=build_terminal_disk(
                                core,
                                layer.index,
                                packing.insulated_diameter_m,
                                bare,
                                station,
                            ),
                            polarity=polarity,
                        ),
                    )
                )
                counter += 1
        groups.append(
            WindingGroupPlan(
                name=base,
                winding_id=packing.winding_id,
                is_solid=definition.mode is ConductorMode.SOLID,
                current_peak_a=definition.ac_magnitude_a,
                phase_deg=definition.ac_phase_deg,
                dc_current_a=definition.dc_current_a,
                turns=tuple(turns),
            )
        )

    reports: list[ReportPlan] = []
    for group in groups:
        reports.append(
            ReportPlan(
                name=f"{group.name}_Resistance",
                expression=f"{MATRIX_NAME}.R({group.name},{group.name})",
            )
        )
        reports.append(
            ReportPlan(
                name=f"{group.name}_Inductance",
                expression=f"{MATRIX_NAME}.L({group.name},{group.name})",
            )
        )

    notes: list[str] = []
    if material.draft:
        notes.append(
            f"Core material {material.name} derives from a draft catalog record; "
            "verify against the manufacturer catalog before trusting results."
        )
    dc_requested = any(group.dc_current_a != 0.0 for group in groups)
    notes.extend(
        dc_bias_notes(
            dc_bias_decision, dc_requested, nonlinear_material=bool(material.bh_curve)
        )
    )

    native_dc = (
        dc_bias_decision is not None
        and dc_bias_decision.strategy is DcBiasStrategy.NATIVE_INCLUDE_DC_FIELDS
        and dc_requested
    )
    solution_type = SOLUTION_TYPE_DC if native_dc else SOLUTION_TYPE

    width = core.r_outer_m - core.r_inner_m
    height = 2.0 * core.half_height_m
    return Maxwell3dDesignPlan(
        design_name=DESIGN_NAME,
        solution_type=solution_type,
        core=CorePlan(name=core_name(), profile=build_core_profile(core), material=material),
        windings=tuple(groups),
        region=RegionPlan(padding_percent=REGION_PADDING_PERCENT),
        mesh=MeshPlan(
            conductor_max_length_m=round(1.5 * max_bare, 9),
            core_max_length_m=round(min(width, height) / 3.0, 9),
        ),
        setup=SetupPlan(
            name=SETUP_NAME,
            frequency_hz=frequencies[0],
            maximum_passes=10,
            percent_error=1.0,
        ),
        matrix_name=MATRIX_NAME,
        reports=tuple(reports),
        notes=tuple(notes),
        dc_bias=dc_bias_decision,
    )
