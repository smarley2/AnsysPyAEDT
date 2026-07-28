from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence

from inductor_designer.domain.project import RequestedOutput, SimulationRecipe
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
    GeometryOnlyMaxwell3dPlan,
    GeometryOnlyTurnPlan,
    GeometryOnlyWindingPlan,
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
    dc_bias_notes,
    material_spec_from_material_record,
)
from inductor_designer.simulation.run_contracts import EffectiveWindingInput


def _polarity(
    definition: WindingDefinition,
    current_direction: CurrentDirection,
) -> Polarity:
    positive = (current_direction is CurrentDirection.FORWARD) == (
        definition.winding_direction is WindingDirection.COUNTERCLOCKWISE
    )
    return Polarity.POSITIVE if positive else Polarity.NEGATIVE


def _effective_inputs_by_id(
    windings: Sequence[WindingDefinition],
    effective_inputs: Sequence[EffectiveWindingInput],
) -> tuple[dict[str, EffectiveWindingInput], tuple[str, ...]]:
    winding_ids = {definition.winding_id for definition in windings}
    effective_ids = [item.winding_id for item in effective_inputs]
    counts = Counter(effective_ids)
    duplicate = sorted(winding_id for winding_id, count in counts.items() if count > 1)
    by_id = {item.winding_id: item for item in effective_inputs}
    missing = sorted(winding_ids - set(by_id))
    unknown = sorted(set(by_id) - winding_ids)
    issues: list[str] = []
    if missing:
        issues.append(f"Missing effective winding inputs: {missing}.")
    if duplicate:
        issues.append(f"Duplicate effective winding ids: {duplicate}.")
    if unknown:
        issues.append(f"Unknown effective winding ids: {unknown}.")
    return by_id, tuple(issues)


def build_maxwell3d_plan(
    core: FinishedCore,
    packings: Sequence[PackedWinding],
    windings: Sequence[WindingDefinition],
    effective_inputs: Sequence[EffectiveWindingInput],
    bare_diameter_m: Mapping[str, float],
    *,
    frequency_hz: float,
    recipe: SimulationRecipe,
    dc_bias_decision: DcBiasDecision | None = None,
    material_record: MaterialRecord,
    material_bh_series_id: str | None,
) -> Maxwell3dDesignPlan:
    issues: list[str] = []
    by_id = {definition.winding_id: definition for definition in windings}
    effective_by_id, effective_issues = _effective_inputs_by_id(
        windings, effective_inputs
    )
    issues.extend(effective_issues)
    if not packings:
        issues.append("No packed windings; nothing to export.")
    missing = [p.winding_id for p in packings if p.winding_id not in by_id]
    if missing:
        issues.append(f"Packings without winding definitions: {missing}.")
    if issues:
        raise PlanBuildError(tuple(issues))
    material = material_spec_from_material_record(
        None,
        material_record,
        bh_series_id=material_bh_series_id,
    )

    identifiers = unique_identifiers([packing.winding_id for packing in packings])
    groups: list[WindingGroupPlan] = []
    max_bare = 0.0
    for packing in packings:
        definition = by_id[packing.winding_id]
        effective = effective_by_id[packing.winding_id]
        base = identifiers[packing.winding_id]
        bare = bare_diameter_m[packing.winding_id]
        max_bare = max(max_bare, bare)
        polarity = _polarity(definition, effective.current_direction)
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
                current_peak_a=effective.ac_peak_current_a,
                phase_deg=effective.phase_deg,
                dc_current_a=effective.dc_current_a,
                turns=tuple(turns),
            )
        )

    reports: list[ReportPlan] = []
    for group in groups:
        if RequestedOutput.RESISTANCE in recipe.requested_outputs:
            reports.append(
                ReportPlan(
                    name=f"{group.name}_Resistance",
                    expression=f"{MATRIX_NAME}.R({group.name},{group.name})",
                )
            )
        if RequestedOutput.INDUCTANCE in recipe.requested_outputs:
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
            frequency_hz=frequency_hz,
            maximum_passes=recipe.maximum_passes,
            percent_error=recipe.percent_error,
        ),
        matrix_name=MATRIX_NAME,
        reports=tuple(reports),
        notes=tuple(notes),
        dc_bias=dc_bias_decision,
    )


def build_geometry_only_maxwell3d_plan(
    core: FinishedCore,
    packings: Sequence[PackedWinding],
    windings: Sequence[WindingDefinition],
    bare_diameter_m: Mapping[str, float],
) -> GeometryOnlyMaxwell3dPlan:
    issues: list[str] = []
    by_id = {definition.winding_id: definition for definition in windings}
    if not packings:
        issues.append("No packed windings; nothing to export.")
    missing = [packing.winding_id for packing in packings if packing.winding_id not in by_id]
    if missing:
        issues.append(f"Packings without winding definitions: {missing}.")
    if issues:
        raise PlanBuildError(tuple(issues))

    identifiers = unique_identifiers([packing.winding_id for packing in packings])
    groups: list[GeometryOnlyWindingPlan] = []
    for packing in packings:
        base = identifiers[packing.winding_id]
        turns: list[GeometryOnlyTurnPlan] = []
        counter = 1
        for layer in packing.layers:
            for station in layer.station_deg:
                turns.append(
                    GeometryOnlyTurnPlan(
                        name=f"{base}_L{layer.index:02d}_T{counter:03d}",
                        segments=build_turn_loop(
                            core,
                            layer.index,
                            packing.insulated_diameter_m,
                            station,
                        ),
                        bare_diameter_m=bare_diameter_m[packing.winding_id],
                    )
                )
                counter += 1
        groups.append(
            GeometryOnlyWindingPlan(
                name=base,
                winding_id=packing.winding_id,
                turns=tuple(turns),
            )
        )
    return GeometryOnlyMaxwell3dPlan(
        design_name=DESIGN_NAME,
        core_name=core_name(),
        core_profile=build_core_profile(core),
        windings=tuple(groups),
        notes=(),
    )
