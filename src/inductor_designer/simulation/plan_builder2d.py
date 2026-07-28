from __future__ import annotations

from collections.abc import Mapping, Sequence

from inductor_designer.domain.project import RequestedOutput, SimulationRecipe
from inductor_designer.domain.winding import (
    ConductorMode,
    CurrentDirection,
    WindingDefinition,
    WindingDirection,
)
from inductor_designer.geometry.naming import core_name, unique_identifiers
from inductor_designer.geometry.planar import PlanarModel
from inductor_designer.materials.records import MaterialRecord
from inductor_designer.simulation.capabilities import DcBiasDecision
from inductor_designer.simulation.maxwell2d_plan import (
    DESIGN_NAME_2D,
    Conductor2dPlan,
    Core2dPlan,
    Maxwell2dDesignPlan,
    Winding2dGroupPlan,
)
from inductor_designer.simulation.maxwell_plan import (
    MATRIX_NAME,
    REGION_PADDING_PERCENT,
    SETUP_NAME,
    SOLUTION_TYPE,
    MeshPlan,
    PlanBuildError,
    Polarity,
    RegionPlan,
    ReportPlan,
    SetupPlan,
    dc_bias_notes,
    material_spec_from_material_record,
)
from inductor_designer.simulation.plan_builder import _effective_inputs_by_id
from inductor_designer.simulation.run_contracts import EffectiveWindingInput

_TWO_D_NOTE = (
    "The 2D model is a documented approximate XY cross-section equivalent; turns and "
    "polarity are represented through coil and winding assignments, and model depth "
    "derives from the core height."
)


def _base_polarity(
    definition: WindingDefinition,
    current_direction: CurrentDirection,
) -> Polarity:
    positive = (current_direction is CurrentDirection.FORWARD) == (
        definition.winding_direction is WindingDirection.COUNTERCLOCKWISE
    )
    return Polarity.POSITIVE if positive else Polarity.NEGATIVE


def _invert(polarity: Polarity) -> Polarity:
    return Polarity.NEGATIVE if polarity is Polarity.POSITIVE else Polarity.POSITIVE


def build_maxwell2d_plan(
    planar: PlanarModel,
    windings: Sequence[WindingDefinition],
    effective_inputs: Sequence[EffectiveWindingInput],
    bare_diameter_m: Mapping[str, float],
    *,
    frequency_hz: float,
    recipe: SimulationRecipe,
    dc_bias_decision: DcBiasDecision | None = None,
    material_record: MaterialRecord,
    material_bh_series_id: str | None,
) -> Maxwell2dDesignPlan:
    issues: list[str] = []
    by_id = {definition.winding_id: definition for definition in windings}
    effective_by_id, effective_issues = _effective_inputs_by_id(
        windings, effective_inputs
    )
    issues.extend(effective_issues)
    if not planar.windings:
        issues.append("No planar windings; nothing to export.")
    missing = [w.winding_id for w in planar.windings if w.winding_id not in by_id]
    if missing:
        issues.append(f"Planar windings without definitions: {missing}.")
    if issues:
        raise PlanBuildError(tuple(issues))
    material = material_spec_from_material_record(
        None,
        material_record,
        bh_series_id=material_bh_series_id,
    )

    identifiers = unique_identifiers([w.winding_id for w in planar.windings])
    groups: list[Winding2dGroupPlan] = []
    max_bare = 0.0
    for planar_winding in planar.windings:
        definition = by_id[planar_winding.winding_id]
        effective = effective_by_id[planar_winding.winding_id]
        base = identifiers[planar_winding.winding_id]
        bare = bare_diameter_m[planar_winding.winding_id]
        max_bare = max(max_bare, bare)
        base_polarity = _base_polarity(definition, effective.current_direction)
        conductors = tuple(
            Conductor2dPlan(
                name=f"{base}_C{index:03d}",
                x_m=conductor.x_m,
                y_m=conductor.y_m,
                radius_m=conductor.radius_m,
                polarity=(
                    base_polarity if conductor.polarity > 0 else _invert(base_polarity)
                ),
            )
            for index, conductor in enumerate(planar_winding.conductors, start=1)
        )
        groups.append(
            Winding2dGroupPlan(
                name=base,
                winding_id=planar_winding.winding_id,
                is_solid=definition.mode is ConductorMode.SOLID,
                current_peak_a=effective.ac_peak_current_a,
                phase_deg=effective.phase_deg,
                dc_current_a=effective.dc_current_a,
                conductors=conductors,
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

    notes: list[str] = [_TWO_D_NOTE]
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

    return Maxwell2dDesignPlan(
        design_name=DESIGN_NAME_2D,
        solution_type=SOLUTION_TYPE,
        model_depth_m=planar.depth_m,
        core=Core2dPlan(
            name=core_name(),
            r_inner_m=planar.r_inner_m,
            r_outer_m=planar.r_outer_m,
            material=material,
        ),
        windings=tuple(groups),
        region=RegionPlan(padding_percent=REGION_PADDING_PERCENT),
        mesh=MeshPlan(
            conductor_max_length_m=round(1.5 * max_bare, 9),
            core_max_length_m=round((planar.r_outer_m - planar.r_inner_m) / 3.0, 9),
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
