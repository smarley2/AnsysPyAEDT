"""One preliminary result per project (specification sections 4.3 and 5).

Each quantity is evaluated independently: a missing loss curve makes core loss
unavailable while flux density, current density, and wire loss stay estimated.
Results are derived data and are never persisted into the Project document.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field, replace

from inductor_designer.domain.catalog_records import ConductorRecord
from inductor_designer.domain.project import (
    InductorProject,
    ManualCoreSelection,
    MaterialRevisionSelection,
)
from inductor_designer.domain.winding import (
    CurrentDirection,
    WindingDefinition,
    mmf_sign,
)
from inductor_designer.geometry.packing import PackedWinding
from inductor_designer.simulation.core_loss_estimate import core_loss_w
from inductor_designer.simulation.inductance_estimate import (
    AL_TOLERANCE_NOTE,
    CatalogReference,
    CoreInductance,
    al_deviation,
    catalog_reference,
    core_inductance,
    stored_energy_j,
)
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
    # Depends on the core, not on this winding's conductor record, so it stays
    # estimated when the copper quantities are refused.
    inductance: PreliminaryValue


@dataclass(frozen=True, slots=True)
class CorePreliminary:
    b_dc: PreliminaryValue
    b_min: PreliminaryValue
    b_max: PreliminaryValue
    b_ac_peak: PreliminaryValue
    b_peak_magnitude: PreliminaryValue
    core_loss: PreliminaryValue
    effective_area: PreliminaryValue
    path_length: PreliminaryValue
    volume: PreliminaryValue
    mu_r_effective: PreliminaryValue
    mu_r_initial: PreliminaryValue
    al_catalog: PreliminaryValue
    al_effective: PreliminaryValue
    al_deviation: PreliminaryValue
    stored_energy: PreliminaryValue


@dataclass(frozen=True, slots=True)
class PreliminaryTotals:
    total_wire_loss: PreliminaryValue
    core_loss: PreliminaryValue
    total_loss: PreliminaryValue


@dataclass(frozen=True, slots=True)
class WindingCoupling:
    """How one winding couples to another through the shared core.

    One entry per ordered pair, because with unequal turns the pair reads
    differently from each side: `common_mode` and `differential_mode` are what
    `winding_id` sees, `mutual` is symmetric.
    """

    winding_id: str
    other_winding_id: str
    mutual: PreliminaryValue
    common_mode: PreliminaryValue
    differential_mode: PreliminaryValue


@dataclass(frozen=True, slots=True)
class PreliminaryResult:
    core: CorePreliminary
    windings: tuple[WindingPreliminary, ...]
    totals: PreliminaryTotals
    material_revision_id: str | None
    bh_series_id: str | None
    notes: tuple[str, ...] = field(default_factory=tuple)
    couplings: tuple[WindingCoupling, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class _CoreEcho:
    """What the core itself states, reported independently of the flux estimate.

    A missing B-H series must not make the core's area, or its datasheet
    inductance factor, read Unavailable -- the same reason wire length is
    evaluated independently of wire loss. Everything here comes from
    `CoreMagneticProperties` alone.
    """

    effective_area: PreliminaryValue
    path_length: PreliminaryValue
    volume: PreliminaryValue
    al_catalog: PreliminaryValue
    mu_r_initial: PreliminaryValue


def _echoed(value: float, name: str, notes: tuple[str, ...]) -> PreliminaryValue:
    if not math.isfinite(value):
        return unavailable(
            DiagnosticCode.CORE_GEOMETRY_NOT_FINITE,
            f"Core {name} is not a finite number, so the core dimensions are "
            "out of range.",
        )
    if not value > 0.0:
        return unavailable(
            DiagnosticCode.CORE_GEOMETRY_NON_POSITIVE,
            f"Core {name} must be positive; got {value:g}.",
        )
    return estimated(value, notes)


def _core_echo(core: CoreMagneticProperties) -> _CoreEcho:
    reference = catalog_reference(core)
    if isinstance(reference, CatalogReference):
        # The tolerance caveat belongs to the values that reference the catalog.
        catalog_notes = (*core.notes, AL_TOLERANCE_NOTE)
        al_catalog = estimated(reference.al_catalog_h, catalog_notes)
        mu_r_initial = estimated(reference.mu_r_initial, catalog_notes)
    else:
        al_catalog = reference
        mu_r_initial = reference
    return _CoreEcho(
        effective_area=_echoed(core.effective_area_m2, "effective area", core.notes),
        path_length=_echoed(core.path_length_m, "magnetic path length", core.notes),
        volume=_echoed(core.volume_m3, "effective volume", core.notes),
        al_catalog=al_catalog,
        mu_r_initial=mu_r_initial,
    )


def _no_core_echo() -> _CoreEcho:
    """With no core selected there is nothing of the core's own to report.

    The dimensions get their own `core_geometry.*` code rather than the
    flux-density one: a run manifest triaged on `core_geometry.*` must find
    every reason the echo was withheld, including this one. The datasheet rows
    get the no-catalog-value code, which is exactly what no core means for them.
    """
    geometry_reason = unavailable(
        DiagnosticCode.CORE_GEOMETRY_NO_CORE_SELECTED,
        "No core is selected, so it has no effective area, magnetic path "
        "length, or volume to report.",
    )
    catalog_reason = unavailable(
        DiagnosticCode.AL_CHECK_NO_CATALOG_AL,
        "No core is selected, so there is no manufacturer inductance factor to "
        "reference.",
    )
    return _CoreEcho(
        effective_area=geometry_reason,
        path_length=geometry_reason,
        volume=geometry_reason,
        al_catalog=catalog_reason,
        mu_r_initial=catalog_reason,
    )


def _core_all(flux_reason: PreliminaryValue, echo: _CoreEcho) -> CorePreliminary:
    """One flux-density reason, reported identically for every B quantity.

    Core loss, inductance, and stored energy each get their OWN diagnostic
    (CORE_LOSS_NO_FLUX_DENSITY, INDUCTANCE_NO_FLUX_DENSITY,
    STORED_ENERGY_NO_FLUX_DENSITY): stamping the flux-density code onto them
    would claim they failed for a reason they didn't -- they failed because
    flux density was unavailable. The core echo -- dimensions, catalog A_L, and
    the permeability that A_L implies -- does not depend on flux density at all,
    so it is passed in already evaluated and stays visible here.
    """
    core_loss_reason = unavailable(
        DiagnosticCode.CORE_LOSS_NO_FLUX_DENSITY,
        "Core loss requires a flux-density estimate, which is unavailable: "
        f"{flux_reason.message}",
    )
    inductance_reason = unavailable(
        DiagnosticCode.INDUCTANCE_NO_FLUX_DENSITY,
        "Inductance requires a flux-density estimate, which is unavailable: "
        f"{flux_reason.message}",
    )
    energy_reason = unavailable(
        DiagnosticCode.STORED_ENERGY_NO_FLUX_DENSITY,
        "Stored energy requires a flux-density estimate, which is unavailable: "
        f"{flux_reason.message}",
    )
    return CorePreliminary(
        b_dc=flux_reason,
        b_min=flux_reason,
        b_max=flux_reason,
        b_ac_peak=flux_reason,
        b_peak_magnitude=flux_reason,
        core_loss=core_loss_reason,
        effective_area=echo.effective_area,
        path_length=echo.path_length,
        volume=echo.volume,
        mu_r_effective=inductance_reason,
        mu_r_initial=echo.mu_r_initial,
        al_catalog=echo.al_catalog,
        al_effective=inductance_reason,
        # The deviation is the one part of the check that needs an operating
        # point, so it follows inductance rather than the echo.
        al_deviation=inductance_reason,
        stored_energy=energy_reason,
    )


def _al_deviation(
    al_effective: PreliminaryValue,
    al_catalog: PreliminaryValue,
    core_notes: tuple[str, ...],
) -> PreliminaryValue:
    """How far the effective inductance factor sits from the catalog one.

    Needs both sides, so it reports whichever is missing -- the effective value
    first, because that is the one an operating point can withhold.
    """
    if al_effective.state is not ResultState.ESTIMATED or al_effective.value is None:
        return al_effective
    if al_catalog.state is not ResultState.ESTIMATED or al_catalog.value is None:
        return al_catalog
    deviation = al_deviation(al_effective.value, al_catalog.value)
    if deviation is None:
        return unavailable(
            DiagnosticCode.AL_CHECK_NOT_FINITE,
            "The ratio of effective to catalog inductance factor overflows, so "
            "the deviation is not reported.",
        )
    return estimated(deviation, (*core_notes, AL_TOLERANCE_NOTE))


def _core_estimates(
    request: PreliminaryRequest,
    fields: FieldStrengths,
    densities: FluxDensities,
    core: CoreMagneticProperties,
    echo: _CoreEcho,
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
    inductance = core_inductance(fields, densities, core)
    if isinstance(inductance, CoreInductance):
        inductance_notes = inductance.notes + core.notes
        mu_r_effective = estimated(inductance.mu_r_effective, inductance_notes)
        al_effective = estimated(inductance.al_effective_h, inductance_notes)
    else:
        mu_r_effective = inductance
        al_effective = inductance
    deviation = _al_deviation(al_effective, echo.al_catalog, core.notes)
    return CorePreliminary(
        b_dc=estimated(densities.b_dc_t, notes),
        b_min=estimated(densities.b_min_t, notes),
        b_max=estimated(densities.b_max_t, notes),
        b_ac_peak=estimated(densities.b_ac_peak_t, notes),
        b_peak_magnitude=estimated(densities.b_peak_magnitude_t, notes),
        core_loss=loss,
        effective_area=echo.effective_area,
        path_length=echo.path_length,
        volume=echo.volume,
        mu_r_effective=mu_r_effective,
        mu_r_initial=echo.mu_r_initial,
        al_catalog=echo.al_catalog,
        al_effective=al_effective,
        al_deviation=deviation,
        stored_energy=stored_energy_j(fields, densities, core),
    )


def _winding_inductance(turns: int, al_effective: PreliminaryValue) -> PreliminaryValue:
    """`turns**2 * A_L`, or the core's own reason unchanged.

    Returning `al_effective` itself is deliberate: the winding's inductance
    failed for exactly the core's reason, so it carries the same code, message
    and notes rather than a paraphrase.
    """
    if al_effective.state is not ResultState.ESTIMATED or al_effective.value is None:
        return al_effective
    return estimated(turns**2 * al_effective.value, al_effective.notes)


CANCELLED_MMF_NOTE = (
    "the design's windings cancel, so this inductance is evaluated from this "
    "winding's own ampere-turns with every other winding's current ignored. The "
    "core itself carries no net flux at this operating point: a differentially "
    "driven pair measures only its leakage inductance, which is lower than this "
    "value, while a common-mode drive measures the whole of it"
)


def _own_mmf_al(
    request: PreliminaryRequest,
    definition: WindingDefinition,
    core: CoreMagneticProperties,
    material: MaterialRevisionSelection,
) -> PreliminaryValue:
    """`A_L` from one winding's ampere-turns alone.

    Reached only when the windings cancel exactly, which leaves the net-MMF
    permeability undefined (`inductance.no_excitation`) and would otherwise
    report no inductance at all for a common-mode choke -- the design whose
    whole point is that its windings cancel. Everything else, including every
    core row, still comes from the net ampere-turns.
    """
    operating_point = request.project.operating_point
    own = tuple(
        item
        for item in operating_point.windings
        if item.winding_id == definition.winding_id
    )
    fields = field_strengths(
        replace(operating_point, windings=own),
        {definition.winding_id: definition.turns},
        core.path_length_m,
        {definition.winding_id: definition.winding_direction},
    )
    if isinstance(fields, PreliminaryValue):
        return fields
    densities = flux_densities(material, fields, operating_point.core_temperature_c)
    if isinstance(densities, PreliminaryValue):
        return densities
    inductance = core_inductance(fields, densities, core)
    if not isinstance(inductance, CoreInductance):
        return inductance
    return estimated(
        inductance.al_effective_h,
        (*inductance.notes, *core.notes, CANCELLED_MMF_NOTE),
    )


def _al_for(
    request: PreliminaryRequest,
    definition: WindingDefinition,
    al_effective: PreliminaryValue,
) -> PreliminaryValue:
    """The inductance factor this winding's own inductance is built from."""
    material = request.project.design.core_material
    if (
        al_effective.code == DiagnosticCode.INDUCTANCE_NO_EXCITATION
        and request.core is not None
        and material is not None
    ):
        return _own_mmf_al(request, definition, request.core, material)
    return al_effective


COUPLING_NOTE = (
    "mutual coupling is evaluated at k = 1: the lumped effective-core model "
    "carries no leakage path, so every turn of one winding links every turn of "
    "the other. The reported mode is therefore an upper bound. The mode the "
    "mutual subtracts from is reported unavailable rather than as a number, "
    "because at k = 1 it is not a leakage measurement -- see its reason. The "
    "two modes are named for driving both windings' terminals forward "
    "(common) and one of them reversed (differential), whatever current "
    "directions the operating point currently carries; which of the two "
    "cancels is set by the winding senses alone"
)

CANCELLING_MODE_MESSAGE = (
    "The series mode the mutual subtracts from is leakage inductance, and the "
    "lumped effective-core model has no leakage path: at k = 1 it can only "
    "return the residual of two equal terms, which is zero whenever the two "
    "windings carry the same number of turns. A number here would be a "
    "modeling floor, not an estimate, so none is reported. Solve the design "
    "with FEMM, Maxwell 2D or Maxwell 3D for this mode -- those backends carry "
    "the air paths that make k < 1. Reversing a current direction cannot "
    "change it: the two modes are defined by how the pair is driven, not by "
    "the operating point, and which one cancels follows the winding senses."
)


def _couplings(
    windings: tuple[WindingDefinition, ...],
    al_by_winding: Mapping[str, PreliminaryValue],
) -> tuple[WindingCoupling, ...]:
    """`M = s_i s_j N_i N_j sqrt(A_Li A_Lj)`, plus the two series modes.

    The signs are the winding senses alone (`mmf_sign` at forward current), so
    the pair reads the same whichever way the operating point happens to drive
    it, and a pair wound against each other reports a negative mutual.
    """
    entries: list[WindingCoupling] = []
    for first in windings:
        for second in windings:
            if first.winding_id == second.winding_id:
                continue
            al_first = al_by_winding[first.winding_id]
            al_second = al_by_winding[second.winding_id]
            unusable = next(
                (
                    value
                    for value in (al_first, al_second)
                    if value.state is not ResultState.ESTIMATED or value.value is None
                ),
                None,
            )
            if unusable is not None:
                entries.append(
                    WindingCoupling(
                        winding_id=first.winding_id,
                        other_winding_id=second.winding_id,
                        mutual=unusable,
                        common_mode=unusable,
                        differential_mode=unusable,
                    )
                )
                continue
            assert al_first.value is not None and al_second.value is not None
            sign = mmf_sign(
                first.winding_direction, CurrentDirection.FORWARD
            ) * mmf_sign(second.winding_direction, CurrentDirection.FORWARD)
            mutual = (
                sign
                * first.turns
                * second.turns
                * math.sqrt(al_first.value * al_second.value)
            )
            self_inductance = first.turns**2 * al_first.value
            notes = (*al_first.notes, COUPLING_NOTE)
            # Only the mode the mutual adds to is an estimate. The other one is
            # the difference of two terms this model makes equal, so it reported
            # 0.000 uH for a matched pair -- read as a computed cancellation
            # when it was the k = 1 assumption showing through.
            aiding = estimated(self_inductance + abs(mutual), notes)
            cancelling = unavailable(
                DiagnosticCode.COUPLING_NO_LEAKAGE_PATH, CANCELLING_MODE_MESSAGE
            )
            entries.append(
                WindingCoupling(
                    winding_id=first.winding_id,
                    other_winding_id=second.winding_id,
                    mutual=estimated(mutual, notes),
                    common_mode=aiding if mutual >= 0.0 else cancelling,
                    differential_mode=cancelling if mutual >= 0.0 else aiding,
                )
            )
    return tuple(entries)


def _winding_row(
    request: PreliminaryRequest, winding_id: str, inductance: PreliminaryValue
) -> WindingPreliminary:
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
            inductance=inductance,
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
        inductance=inductance,
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
            ),
            _no_core_echo(),
        )
    elif material is None:
        core = _core_all(
            unavailable(
                DiagnosticCode.FLUX_DENSITY_NO_MATERIAL_SELECTED,
                "No core material revision is selected, so core flux density "
                "and core loss cannot be estimated.",
            ),
            _core_echo(request.core),
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
            ),
            _core_echo(request.core),
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
            {
                definition.winding_id: definition.winding_direction
                for definition in design.windings
            },
        )
        echo = _core_echo(request.core)
        if isinstance(fields, PreliminaryValue):
            core = _core_all(fields, echo)
        else:
            densities = flux_densities(
                material,
                fields,
                request.project.operating_point.core_temperature_c,
            )
            if isinstance(densities, PreliminaryValue):
                core = _core_all(densities, echo)
            else:
                core = _core_estimates(
                    request, fields, densities, request.core, echo
                )

    al_by_winding = {
        definition.winding_id: _al_for(request, definition, core.al_effective)
        for definition in design.windings
    }
    windings = tuple(
        _winding_row(
            request,
            definition.winding_id,
            _winding_inductance(
                definition.turns, al_by_winding[definition.winding_id]
            ),
        )
        for definition in design.windings
    )
    couplings = _couplings(design.windings, al_by_winding)

    notes: list[str] = []
    for value in (
        core.b_dc,
        core.core_loss,
        # The geometry echo carries how A_e, l_e and V_e were obtained, and it
        # is the only carrier of that provenance when flux density is refused.
        core.effective_area,
        core.al_effective,
        core.al_deviation,
        core.stored_energy,
        *(row.wire_loss for row in windings),
        # A winding's inductance normally repeats the notes `core.al_effective`
        # already carried, which the dedupe below drops. When the windings
        # cancel it is the ONLY carrier of the caveat on the number reported,
        # and dropping it would leave that number unqualified on screen.
        *(row.inductance for row in windings),
        # The k = 1 caveat only ever appears here.
        *(coupling.mutual for coupling in couplings),
    ):
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
        couplings=couplings,
    )
