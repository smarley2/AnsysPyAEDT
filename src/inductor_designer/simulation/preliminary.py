"""One preliminary result per project (specification sections 4.3 and 5).

Each quantity is evaluated independently: a missing loss curve makes core loss
unavailable while flux density, current density, and wire loss stay estimated.
Results are derived data and are never persisted into the Project document.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from inductor_designer.domain.catalog_records import ConductorRecord
from inductor_designer.domain.project import InductorProject, ManualCoreSelection
from inductor_designer.geometry.packing import PackedWinding
from inductor_designer.simulation.core_loss_estimate import core_loss_w
from inductor_designer.simulation.magnetic_estimate import (
    FieldStrengths,
    FluxDensities,
    field_strengths,
    flux_densities,
)
from inductor_designer.simulation.preliminary_contracts import (
    CoreMagneticProperties,
    DiagnosticCode,
    PreliminaryValue,
    ResultState,
    estimated,
    unavailable,
)
from inductor_designer.simulation.winding_estimate import (
    LEAD_EXCLUSION_NOTE,
    WireLoss,
    conductor_area_m2,
    current_densities,
    wire_resistance_and_loss,
)


@dataclass(frozen=True, slots=True)
class PreliminaryRequest:
    """Everything the estimator needs, already resolved by the caller.

    Taking records rather than repositories keeps this module free of SQLite and
    the filesystem, and makes every test constructible without I/O.
    """

    project: InductorProject
    core: CoreMagneticProperties | None
    conductors_by_winding: Mapping[str, ConductorRecord]
    packings_by_winding: Mapping[str, PackedWinding]


@dataclass(frozen=True, slots=True)
class WindingPreliminary:
    winding_id: str
    conductor_area: PreliminaryValue
    j_ac_rms: PreliminaryValue
    j_ac_peak: PreliminaryValue
    j_dc: PreliminaryValue
    wire_length: PreliminaryValue
    resistance: PreliminaryValue
    wire_loss: PreliminaryValue


@dataclass(frozen=True, slots=True)
class CorePreliminary:
    b_dc: PreliminaryValue
    b_min: PreliminaryValue
    b_max: PreliminaryValue
    b_ac_peak: PreliminaryValue
    b_peak_magnitude: PreliminaryValue
    core_loss: PreliminaryValue


@dataclass(frozen=True, slots=True)
class PreliminaryTotals:
    total_wire_loss: PreliminaryValue
    core_loss: PreliminaryValue
    total_loss: PreliminaryValue


@dataclass(frozen=True, slots=True)
class PreliminaryResult:
    core: CorePreliminary
    windings: tuple[WindingPreliminary, ...]
    totals: PreliminaryTotals
    material_revision_id: str | None
    bh_series_id: str | None
    notes: tuple[str, ...] = field(default_factory=tuple)


def _core_all(flux_reason: PreliminaryValue) -> CorePreliminary:
    """One flux-density reason, reported identically for every B quantity.

    Core loss gets its OWN diagnostic (CORE_LOSS_NO_FLUX_DENSITY): stamping
    the flux-density code onto core loss would claim core loss failed for a
    reason it didn't -- it failed because flux density was unavailable.
    """
    core_loss_reason = unavailable(
        DiagnosticCode.CORE_LOSS_NO_FLUX_DENSITY,
        "Core loss requires a flux-density estimate, which is unavailable: "
        f"{flux_reason.message}",
    )
    return CorePreliminary(
        b_dc=flux_reason,
        b_min=flux_reason,
        b_max=flux_reason,
        b_ac_peak=flux_reason,
        b_peak_magnitude=flux_reason,
        core_loss=core_loss_reason,
    )


def _core_estimates(
    request: PreliminaryRequest,
    fields: FieldStrengths,
    densities: FluxDensities,
    core: CoreMagneticProperties,
) -> CorePreliminary:
    material = request.project.design.core_material
    if material is None:  # guarded by the caller
        raise AssertionError("_core_estimates requires a selected material")
    operating_point = request.project.operating_point
    loss = core_loss_w(
        material,
        b_ac_peak_t=densities.b_ac_peak_t,
        frequency_hz=operating_point.frequency_hz,
        core_temperature_c=operating_point.core_temperature_c,
        h_dc_a_per_m=fields.h_dc_a_per_m,
        core_volume_m3=core.volume_m3,
    )
    # The core's own notes describe how its path length and volume were
    # obtained, which is an assumption behind every B value below.
    notes = densities.notes + core.notes
    return CorePreliminary(
        b_dc=estimated(densities.b_dc_t, notes),
        b_min=estimated(densities.b_min_t, notes),
        b_max=estimated(densities.b_max_t, notes),
        b_ac_peak=estimated(densities.b_ac_peak_t, notes),
        b_peak_magnitude=estimated(densities.b_peak_magnitude_t, notes),
        core_loss=loss,
    )


def _winding_row(request: PreliminaryRequest, winding_id: str) -> WindingPreliminary:
    # Wire length is packing geometry, not a loss computation: it is known and
    # temperature-independent whenever a packing exists, regardless of
    # whether a conductor record resolved or whether resistance and wire loss
    # are later refused by the copper-temperature guard. It is computed once,
    # here, so both return paths below report the same value. It carries
    # only the lead-exclusion note -- the wire-loss exclusion note describes
    # excluded loss mechanisms, which do not apply to a length.
    packing = request.packings_by_winding.get(winding_id)
    wire_length_m = packing.wire_length_m if packing is not None else 0.0
    if wire_length_m > 0.0:
        length = estimated(wire_length_m, (LEAD_EXCLUSION_NOTE,))
    else:
        length = unavailable(
            DiagnosticCode.WIRE_LOSS_NO_GEOMETRY,
            "Winding geometry produced no modeled wire length, so its "
            "length cannot be estimated.",
        )

    conductor = request.conductors_by_winding.get(winding_id)
    if conductor is None:
        reason = unavailable(
            DiagnosticCode.CURRENT_DENSITY_NO_CONDUCTOR,
            f"Winding {winding_id} has no resolved conductor record, so its "
            "copper area, current densities, and wire loss cannot be estimated.",
        )
        return WindingPreliminary(
            winding_id=winding_id,
            conductor_area=reason,
            j_ac_rms=reason,
            j_ac_peak=reason,
            j_dc=reason,
            wire_length=length,
            resistance=reason,
            wire_loss=reason,
        )

    area = conductor_area_m2(conductor.bare_diameter_m)
    excitation = next(
        (
            item
            for item in request.project.operating_point.windings
            if item.winding_id == winding_id
        ),
        None,
    )
    ac_rms = excitation.ac_rms_current_a if excitation is not None else 0.0
    dc = excitation.dc_current_a if excitation is not None else 0.0
    densities = current_densities(area, ac_rms, dc)

    loss = wire_resistance_and_loss(
        area,
        wire_length_m,
        request.project.operating_point.winding_temperature_c,
        ac_rms,
        dc,
    )

    if isinstance(loss, WireLoss):
        resistance = estimated(loss.resistance_ohm, loss.notes)
        wire_loss = estimated(loss.loss_w, loss.notes)
    else:
        resistance = loss
        wire_loss = loss

    return WindingPreliminary(
        winding_id=winding_id,
        conductor_area=estimated(area),
        j_ac_rms=estimated(densities.j_ac_rms_a_per_m2),
        j_ac_peak=estimated(densities.j_ac_peak_a_per_m2),
        j_dc=estimated(densities.j_dc_a_per_m2),
        wire_length=length,
        resistance=resistance,
        wire_loss=wire_loss,
    )


def _totals(
    windings: tuple[WindingPreliminary, ...], core_loss: PreliminaryValue
) -> PreliminaryTotals:
    # A total that needs a missing component is Unavailable, never a partial
    # sum: total_wire_loss is Estimated only when EVERY winding resolved, so
    # dropping one winding's conductor cannot silently halve the reported
    # total.
    missing = [
        row.winding_id
        for row in windings
        if row.wire_loss.state is not ResultState.ESTIMATED
        or row.wire_loss.value is None
    ]
    if windings and not missing:
        total_wire = estimated(
            sum(row.wire_loss.value for row in windings if row.wire_loss.value is not None)
        )
    elif not windings:
        total_wire = unavailable(
            DiagnosticCode.TOTAL_LOSS_INCOMPLETE,
            "The design has no windings, so no wire loss total is reported.",
        )
    else:
        names = ", ".join(missing)
        total_wire = unavailable(
            DiagnosticCode.TOTAL_LOSS_INCOMPLETE,
            "Total wire loss requires every winding's wire loss to be "
            f"estimated; {len(missing)} of {len(windings)} winding(s) "
            f"({names}) did not resolve, so no partial sum is reported.",
        )

    if (
        total_wire.state is ResultState.ESTIMATED
        and core_loss.state is ResultState.ESTIMATED
        and total_wire.value is not None
        and core_loss.value is not None
    ):
        total = estimated(total_wire.value + core_loss.value)
    else:
        total = unavailable(
            DiagnosticCode.TOTAL_LOSS_INCOMPLETE,
            "Total preliminary loss requires both wire loss and core loss; one "
            "component is unavailable, so no partial total is reported.",
        )
    return PreliminaryTotals(
        total_wire_loss=total_wire, core_loss=core_loss, total_loss=total
    )


def estimate_preliminary(request: PreliminaryRequest) -> PreliminaryResult:
    design = request.project.design
    material = design.core_material

    if request.core is None:
        core = _core_all(
            unavailable(
                DiagnosticCode.FLUX_DENSITY_NO_CORE_SELECTED,
                "No core is selected, so core flux density and core loss cannot "
                "be estimated.",
            )
        )
    elif material is None:
        core = _core_all(
            unavailable(
                DiagnosticCode.FLUX_DENSITY_NO_MATERIAL_SELECTED,
                "No core material revision is selected, so core flux density "
                "and core loss cannot be estimated.",
            )
        )
    elif (
        isinstance(design.core, ManualCoreSelection)
        and not design.manual_material_compatibility_acknowledged
    ):
        # Specification section 4.1: a Manual core paired with a material
        # requires a visible compatibility acknowledgment before Preliminary
        # can treat the pair as complete. Generation and solve already refuse
        # an unacknowledged pair (`run_planning.py`, `domain/validation.py`);
        # this closes the same gap here. Winding quantities do not depend on
        # the core, so they stay estimated below.
        core = _core_all(
            unavailable(
                DiagnosticCode.FLUX_DENSITY_MANUAL_COMPATIBILITY_UNACKNOWLEDGED,
                "The Manual core and pinned material pair is not yet "
                "acknowledged, so core flux density and core loss cannot be "
                "estimated. Confirm material compatibility on the Core & "
                "Material screen.",
            )
        )
    else:
        # Built from the design itself, never taken from the caller, so this
        # can never disagree with WindingDefinition.turns.
        turns_by_winding = {
            definition.winding_id: definition.turns for definition in design.windings
        }
        fields = field_strengths(
            request.project.operating_point,
            turns_by_winding,
            request.core.path_length_m,
        )
        if isinstance(fields, PreliminaryValue):
            core = _core_all(fields)
        else:
            densities = flux_densities(
                material,
                fields,
                request.project.operating_point.core_temperature_c,
            )
            if isinstance(densities, PreliminaryValue):
                core = _core_all(densities)
            else:
                core = _core_estimates(request, fields, densities, request.core)

    windings = tuple(
        _winding_row(request, definition.winding_id) for definition in design.windings
    )

    notes: list[str] = []
    for value in (core.b_dc, core.core_loss, *(row.wire_loss for row in windings)):
        for note in value.notes:
            if note not in notes:
                notes.append(note)

    return PreliminaryResult(
        core=core,
        windings=windings,
        totals=_totals(windings, core.core_loss),
        material_revision_id=material.revision_id if material is not None else None,
        bh_series_id=material.bh_series_id if material is not None else None,
        notes=tuple(notes),
    )
