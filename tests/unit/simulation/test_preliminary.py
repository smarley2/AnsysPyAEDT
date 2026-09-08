from __future__ import annotations

import math
from dataclasses import replace

import pytest

from inductor_designer.domain.project import ManualCoreSelection
from inductor_designer.domain.winding import CurrentDirection, WindingDirection
from inductor_designer.simulation.inductance_estimate import (
    AL_TOLERANCE_NOTE,
    INDUCTANCE_EXCLUSION_NOTE,
    STORED_ENERGY_INTEGRATED_NOTE,
)
from inductor_designer.simulation.preliminary import (
    CANCELLED_MMF_NOTE,
    COUPLING_NOTE,
    PreliminaryRequest,
    PreliminaryResult,
    estimate_preliminary,
)
from inductor_designer.simulation.preliminary_contracts import (
    DiagnosticCode,
    ResultState,
)
from inductor_designer.simulation.winding_estimate import (
    WireLoss,
    conductor_area_m2,
    wire_resistance_and_loss,
)


def test_a_missing_core_makes_only_core_quantities_unavailable(
    sample_request: PreliminaryRequest,
) -> None:
    request = replace(sample_request, core=None)

    result = estimate_preliminary(request)

    assert isinstance(result, PreliminaryResult)
    assert result.core.b_dc.code == DiagnosticCode.FLUX_DENSITY_NO_CORE_SELECTED
    assert result.core.core_loss.state is ResultState.UNAVAILABLE
    # windings are independent of the core selection
    assert result.windings[0].j_ac_rms.state is ResultState.ESTIMATED
    assert result.windings[0].wire_loss.state is ResultState.ESTIMATED


def test_core_loss_reports_its_own_code_not_the_flux_density_reason(
    sample_request: PreliminaryRequest,
) -> None:
    """A missing core makes flux density Unavailable with a flux_density.*
    code. Core loss is unavailable for a *different* reason -- it has no flux
    density to work from -- and must carry its own core_loss.* code instead of
    the upstream flux_density.* code being stamped straight across.
    """
    request = replace(sample_request, core=None)

    result = estimate_preliminary(request)

    assert result.core.b_dc.code == DiagnosticCode.FLUX_DENSITY_NO_CORE_SELECTED
    assert result.core.core_loss.code == DiagnosticCode.CORE_LOSS_NO_FLUX_DENSITY
    assert "flux" in str(result.core.core_loss.message).lower()


def test_total_wire_loss_sums_available_windings(
    sample_request: PreliminaryRequest,
) -> None:
    result = estimate_preliminary(sample_request)

    # Derived independently from the fixture's own inputs (conftest.py: AWG 18
    # bare diameter, 0.4 m wire length, 20 C, 2 A RMS / 0 A DC, two identical
    # windings) -- not from result.windings, or this could never fail.
    area = conductor_area_m2(0.001024)
    per_winding = wire_resistance_and_loss(
        area,
        wire_length_m=0.4,
        winding_temperature_c=20.0,
        ac_rms_current_a=2.0,
        dc_current_a=0.0,
    )
    assert isinstance(per_winding, WireLoss)
    expected = 2 * per_winding.loss_w

    assert result.totals.total_wire_loss.state is ResultState.ESTIMATED
    assert result.totals.total_wire_loss.value is not None
    assert math.isclose(result.totals.total_wire_loss.value, expected)


def test_total_loss_is_unavailable_unless_both_components_exist(
    sample_request: PreliminaryRequest,
) -> None:
    result = estimate_preliminary(replace(sample_request, core=None))

    assert result.totals.total_loss.state is ResultState.UNAVAILABLE
    assert result.totals.total_loss.code == DiagnosticCode.TOTAL_LOSS_INCOMPLETE


def test_every_winding_row_is_reported_even_without_a_conductor(
    sample_request: PreliminaryRequest,
) -> None:
    """w1 has no resolved conductor, but the fixture still supplies a 0.4 m
    packing for it. The packing length does not depend on the conductor
    record, so wire_length must be Estimated at 0.4 even though the copper
    area, current densities, resistance, and wire loss all stay Unavailable.
    """
    request = replace(sample_request, conductors_by_winding={})

    result = estimate_preliminary(request)

    assert len(result.windings) == len(sample_request.project.design.windings)
    w1 = result.windings[0]
    assert w1.j_ac_rms.code == DiagnosticCode.CURRENT_DENSITY_NO_CONDUCTOR
    assert w1.wire_length.state is ResultState.ESTIMATED
    assert w1.wire_length.value == 0.4
    assert w1.resistance.state is ResultState.UNAVAILABLE
    assert w1.wire_loss.state is ResultState.UNAVAILABLE


def test_missing_packing_length_message_describes_the_length_not_other_fields(
    sample_request: PreliminaryRequest,
) -> None:
    """When there is no packing geometry at all, wire_length is Unavailable
    with WIRE_LOSS_NO_GEOMETRY. That code is reused from the resistance/loss
    diagnostic, but the message attached to a length must describe the length
    itself, not claim resistance and wire loss cannot be estimated.
    """
    request = replace(sample_request, packings_by_winding={})

    result = estimate_preliminary(request)

    w1 = result.windings[0]
    assert w1.wire_length.code == DiagnosticCode.WIRE_LOSS_NO_GEOMETRY
    assert "resistance" not in str(w1.wire_length.message).lower()
    assert "wire loss" not in str(w1.wire_length.message).lower()


def test_the_result_records_the_pinned_revision_and_is_deterministic(
    sample_request: PreliminaryRequest,
) -> None:
    first = estimate_preliminary(sample_request)
    second = estimate_preliminary(sample_request)

    assert first == second
    assert first.material_revision_id == "0123456789ab"


def test_a_missing_loss_series_does_not_suppress_a_computable_flux_density(
    sample_request: PreliminaryRequest,
) -> None:
    """The fixture has a B-H series but no loss series: core flux density is
    still Estimated while core loss is Unavailable -- these are evaluated
    independently, exactly as the module docstring promises.
    """
    result = estimate_preliminary(sample_request)

    assert result.core.b_dc.state is ResultState.ESTIMATED
    assert result.core.b_peak_magnitude.state is ResultState.ESTIMATED
    assert result.core.core_loss.state is ResultState.UNAVAILABLE


def test_total_wire_loss_is_unavailable_when_one_winding_is_missing(
    sample_request: PreliminaryRequest,
) -> None:
    """One winding loses its conductor record; the other still resolves. A
    total that needs a missing component must be Unavailable, never a partial
    sum silently labelled Estimated -- summing only the surviving winding
    would under-report the true total with no diagnostic.
    """
    conductor = sample_request.conductors_by_winding["w2"]
    request = replace(sample_request, conductors_by_winding={"w2": conductor})

    result = estimate_preliminary(request)

    w1 = next(row for row in result.windings if row.winding_id == "w1")
    w2 = next(row for row in result.windings if row.winding_id == "w2")
    assert w1.wire_loss.state is ResultState.UNAVAILABLE
    assert w2.wire_loss.state is ResultState.ESTIMATED
    assert result.totals.total_wire_loss.state is ResultState.UNAVAILABLE
    assert result.totals.total_wire_loss.code == DiagnosticCode.TOTAL_LOSS_INCOMPLETE
    assert "w1" in str(result.totals.total_wire_loss.message)


def test_wire_length_survives_an_out_of_range_winding_temperature(
    sample_request: PreliminaryRequest,
) -> None:
    """At 150 C, resistance and wire loss are refused by the copper-
    temperature guard, but the packing length is known and temperature-
    independent, so wire_length must still be Estimated -- carrying only the
    lead-exclusion note, not the wire-loss exclusion note (which is about
    loss mechanisms, not length).
    """
    hot_operating_point = replace(
        sample_request.project.operating_point, winding_temperature_c=150.0
    )
    hot_project = replace(sample_request.project, operating_point=hot_operating_point)
    request = replace(sample_request, project=hot_project)

    result = estimate_preliminary(request)

    w1 = result.windings[0]
    assert w1.resistance.state is ResultState.UNAVAILABLE
    assert w1.resistance.code == DiagnosticCode.WIRE_LOSS_TEMPERATURE_OUT_OF_RANGE
    assert w1.wire_loss.code == DiagnosticCode.WIRE_LOSS_TEMPERATURE_OUT_OF_RANGE

    assert w1.wire_length.state is ResultState.ESTIMATED
    assert w1.wire_length.value == 0.4
    assert any("closed-loop turn length" in note for note in w1.wire_length.notes)
    assert not any("skin effect" in note for note in w1.wire_length.notes)


def test_an_unacknowledged_manual_core_material_pair_blocks_core_quantities(
    sample_request: PreliminaryRequest,
) -> None:
    """Specification section 4.1: selecting a material for a Manual core
    requires a visible compatibility acknowledgment before Preliminary can
    treat the pair as complete. Generation and solve already honor this
    (`run_planning.py`, `domain/validation.py`); the estimator did not.
    """
    manual_core = ManualCoreSelection(0.0272, 0.0138, 0.0112, 0.0)
    project = replace(
        sample_request.project,
        design=replace(
            sample_request.project.design,
            core=manual_core,
            manual_material_compatibility_acknowledged=False,
        ),
    )
    request = replace(sample_request, project=project)

    result = estimate_preliminary(request)

    assert result.core.b_dc.state is ResultState.UNAVAILABLE
    assert (
        result.core.b_dc.code
        == DiagnosticCode.FLUX_DENSITY_MANUAL_COMPATIBILITY_UNACKNOWLEDGED
    )
    assert result.core.core_loss.state is ResultState.UNAVAILABLE
    # Per-quantity independence: winding rows never depend on the core's
    # acknowledgment state.
    assert result.windings[0].j_ac_rms.state is ResultState.ESTIMATED
    assert result.windings[0].wire_length.state is ResultState.ESTIMATED
    assert result.windings[0].resistance.state is ResultState.ESTIMATED
    assert result.windings[0].wire_loss.state is ResultState.ESTIMATED


def test_acknowledging_the_manual_core_material_pair_restores_core_estimates(
    sample_request: PreliminaryRequest,
) -> None:
    manual_core = ManualCoreSelection(0.0272, 0.0138, 0.0112, 0.0)
    project = replace(
        sample_request.project,
        design=replace(
            sample_request.project.design,
            core=manual_core,
            manual_material_compatibility_acknowledged=True,
        ),
    )
    request = replace(sample_request, project=project)

    result = estimate_preliminary(request)

    assert result.core.b_dc.state is ResultState.ESTIMATED


def test_the_core_reports_its_inductance_factor_and_stored_energy(
    sample_request: PreliminaryRequest,
) -> None:
    result = estimate_preliminary(sample_request)

    assert result.core.al_effective.state is ResultState.ESTIMATED
    assert result.core.mu_r_effective.state is ResultState.ESTIMATED
    assert result.core.stored_energy.state is ResultState.ESTIMATED
    assert result.core.al_deviation.state is ResultState.ESTIMATED
    assert INDUCTANCE_EXCLUSION_NOTE in result.notes
    # The fixture records a B-H series, so energy follows the integrated path.
    assert STORED_ENERGY_INTEGRATED_NOTE in result.notes


def test_every_winding_inductance_is_its_turns_squared_times_the_core_factor(
    sample_request: PreliminaryRequest,
) -> None:
    result = estimate_preliminary(sample_request)

    al_effective = result.core.al_effective.value
    assert al_effective is not None
    for row, definition in zip(
        result.windings, sample_request.project.design.windings, strict=True
    ):
        assert row.inductance.value == pytest.approx(definition.turns**2 * al_effective)


def test_the_effective_geometry_echo_reports_the_values_actually_used(
    sample_request: PreliminaryRequest,
) -> None:
    result = estimate_preliminary(sample_request)

    core = sample_request.core
    assert core is not None
    assert result.core.effective_area.value == core.effective_area_m2
    assert result.core.path_length.value == core.path_length_m
    assert result.core.volume.value == core.volume_m3


def test_a_missing_bh_series_does_not_hide_the_core_geometry(
    sample_request: PreliminaryRequest,
) -> None:
    """The echo is independent of flux density: the dimensions are still known."""
    project = replace(
        sample_request.project,
        operating_point=replace(
            sample_request.project.operating_point, core_temperature_c=85.0
        ),
    )

    result = estimate_preliminary(replace(sample_request, project=project))

    assert result.core.b_dc.state is ResultState.UNAVAILABLE
    assert result.core.effective_area.state is ResultState.ESTIMATED
    assert result.core.al_effective.state is ResultState.UNAVAILABLE
    assert result.core.al_effective.code == DiagnosticCode.INDUCTANCE_NO_FLUX_DENSITY
    assert (
        result.core.stored_energy.code
        == DiagnosticCode.STORED_ENERGY_NO_FLUX_DENSITY
    )


def test_how_the_effective_area_was_obtained_reaches_the_assumptions(
    sample_request: PreliminaryRequest,
) -> None:
    """The A_e provenance note (Manual-core formula, or catalog overrides) rides
    on `CoreMagneticProperties.notes`. It used to reach the screen only through
    `b_dc`, which carries no notes when flux density is refused -- exactly when
    the geometry rows are the only core numbers left.
    """
    core = sample_request.core
    assert core is not None
    request = replace(
        sample_request, core=replace(core, notes=("HOW-A_e-WAS-OBTAINED",))
    )
    project = replace(
        request.project,
        operating_point=replace(request.project.operating_point, core_temperature_c=85.0),
    )

    result = estimate_preliminary(replace(request, project=project))

    assert result.core.b_dc.state is ResultState.UNAVAILABLE
    assert result.core.effective_area.state is ResultState.ESTIMATED
    assert "HOW-A_e-WAS-OBTAINED" in result.notes


def test_the_catalog_tolerance_caveat_stays_off_the_inductance_values(
    sample_request: PreliminaryRequest,
) -> None:
    """That caveat is about the DEVIATION mixing roll-off with catalog
    tolerance. An inductance does not depend on the catalog value at all, so
    claiming the caveat applies to it would misdescribe the number.
    """
    result = estimate_preliminary(sample_request)

    assert AL_TOLERANCE_NOTE in result.core.al_deviation.notes
    assert AL_TOLERANCE_NOTE in result.core.al_catalog.notes
    assert AL_TOLERANCE_NOTE in result.core.mu_r_initial.notes
    assert AL_TOLERANCE_NOTE not in result.core.al_effective.notes
    assert AL_TOLERANCE_NOTE not in result.core.mu_r_effective.notes
    assert AL_TOLERANCE_NOTE not in result.windings[0].inductance.notes


def test_no_core_leaves_the_geometry_echo_unavailable(
    sample_request: PreliminaryRequest,
) -> None:
    result = estimate_preliminary(replace(sample_request, core=None))

    # Its own code, not the flux-density one, so triaging a manifest on
    # `core_geometry.*` finds this case too.
    assert (
        result.core.effective_area.code
        == DiagnosticCode.CORE_GEOMETRY_NO_CORE_SELECTED
    )
    # No core means no datasheet to reference either.
    assert result.core.al_catalog.code == DiagnosticCode.AL_CHECK_NO_CATALOG_AL
    assert result.core.mu_r_initial.code == DiagnosticCode.AL_CHECK_NO_CATALOG_AL
    assert result.core.al_effective.code == DiagnosticCode.INDUCTANCE_NO_FLUX_DENSITY
    assert result.windings[0].inductance.code == (
        DiagnosticCode.INDUCTANCE_NO_FLUX_DENSITY
    )


def test_the_catalog_reference_survives_a_missing_bh_series(
    sample_request: PreliminaryRequest,
) -> None:
    """The catalog A_L and the initial permeability derived from it depend only
    on the core's datasheet numbers and its dimensions -- not on flux density,
    not on the operating point. Withholding them when flux density is refused
    hid a datasheet value for a reason it does not depend on. Only the deviation
    needs the effective A_L, so only the deviation goes unavailable.
    """
    project = replace(
        sample_request.project,
        operating_point=replace(
            sample_request.project.operating_point, core_temperature_c=85.0
        ),
    )

    result = estimate_preliminary(replace(sample_request, project=project))

    assert result.core.b_dc.state is ResultState.UNAVAILABLE
    assert result.core.al_catalog.state is ResultState.ESTIMATED
    assert result.core.al_catalog.value == pytest.approx(61e-9)
    assert result.core.mu_r_initial.state is ResultState.ESTIMATED
    assert result.core.al_deviation.code == DiagnosticCode.INDUCTANCE_NO_FLUX_DENSITY


def test_the_catalog_reference_survives_an_unexcited_operating_point(
    sample_request: PreliminaryRequest,
) -> None:
    """Same reasoning at zero excitation: the datasheet does not stop being the
    datasheet because no current flows.
    """
    operating_point = sample_request.project.operating_point
    unexcited = tuple(
        replace(winding, ac_rms_current_a=0.0, dc_current_a=0.0)
        for winding in operating_point.windings
    )
    project = replace(
        sample_request.project,
        operating_point=replace(operating_point, windings=unexcited),
    )

    result = estimate_preliminary(replace(sample_request, project=project))

    assert result.core.al_effective.code == DiagnosticCode.INDUCTANCE_NO_EXCITATION
    assert result.core.al_catalog.state is ResultState.ESTIMATED
    assert result.core.mu_r_initial.state is ResultState.ESTIMATED
    assert result.core.al_deviation.code == DiagnosticCode.INDUCTANCE_NO_EXCITATION


def test_cancelling_windings_still_report_their_own_inductance(
    sample_request: PreliminaryRequest,
) -> None:
    """A common-mode choke is the design whose windings cancel by construction.

    The core rows must stay on the net ampere-turns -- zero flux, no net
    permeability -- while each winding still reports the inductance its own
    ampere-turns produce, labelled so nobody reads it as the differential-mode
    value.
    """
    operating_point = sample_request.project.operating_point
    opposed = (
        operating_point.windings[0],
        replace(
            operating_point.windings[1], current_direction=CurrentDirection.REVERSE
        ),
    )
    project = replace(
        sample_request.project,
        operating_point=replace(operating_point, windings=opposed),
    )

    result = estimate_preliminary(replace(sample_request, project=project))

    assert result.core.b_ac_peak.value == pytest.approx(0.0)
    assert result.core.al_effective.code == DiagnosticCode.INDUCTANCE_NO_EXCITATION
    for row in result.windings:
        assert row.inductance.state is ResultState.ESTIMATED
        assert row.inductance.value is not None
        assert row.inductance.value > 0.0
        assert CANCELLED_MMF_NOTE in row.inductance.notes
    assert CANCELLED_MMF_NOTE not in result.core.b_ac_peak.notes
    # The caveat has to reach the assumptions list the screen shows, which is
    # built from `result.notes`.
    assert CANCELLED_MMF_NOTE in result.notes


def test_mutual_and_the_aiding_series_mode_are_reported_for_a_pair(
    sample_request: PreliminaryRequest,
) -> None:
    """M = N1 N2 A_L at k = 1, and only the mode M adds to carries a number.

    The other mode is `L - M`, a difference this model makes exactly zero for a
    matched pair. Reported as 0.000 uH it read as a computed cancellation when
    it was the k = 1 assumption showing through, so it is refused instead.
    """
    result = estimate_preliminary(sample_request)

    assert [(c.winding_id, c.other_winding_id) for c in result.couplings] == [
        ("w1", "w2"),
        ("w2", "w1"),
    ]
    coupling = result.couplings[0]
    al = result.core.al_effective.value
    self_inductance = result.windings[0].inductance.value
    assert al is not None and self_inductance is not None
    assert coupling.mutual.value == pytest.approx(10 * 10 * al)
    assert coupling.common_mode.value == pytest.approx(self_inductance + 10 * 10 * al)
    assert coupling.differential_mode.state is ResultState.UNAVAILABLE
    assert (
        coupling.differential_mode.code == DiagnosticCode.COUPLING_NO_LEAKAGE_PATH
    )
    assert COUPLING_NOTE in coupling.mutual.notes
    assert COUPLING_NOTE in result.notes


def test_reversing_a_current_direction_does_not_move_the_two_modes(
    sample_request: PreliminaryRequest,
) -> None:
    """The modes are named for how the pair is driven, so the operating point's
    current directions cannot decide which of them cancels -- the winding senses
    do. Reported as numbers, both modes looked frozen at the same values."""
    operating_point = sample_request.project.operating_point
    reversed_second = (
        operating_point.windings[0],
        replace(
            operating_point.windings[1], current_direction=CurrentDirection.REVERSE
        ),
    )
    project = replace(
        sample_request.project,
        operating_point=replace(operating_point, windings=reversed_second),
    )

    result = estimate_preliminary(replace(sample_request, project=project))

    coupling = result.couplings[0]
    assert coupling.mutual.value is not None
    assert coupling.mutual.value > 0.0
    assert coupling.common_mode.state is ResultState.ESTIMATED
    assert coupling.differential_mode.state is ResultState.UNAVAILABLE


def test_windings_wound_against_each_other_report_a_negative_mutual(
    sample_request: PreliminaryRequest,
) -> None:
    """The sign follows the winding senses, not the current directions.

    Driving both terminals forward on an opposed pair cancels, so the
    common-mode value is the one that collapses.
    """
    design = sample_request.project.design
    flipped = (
        design.windings[0],
        replace(
            design.windings[1], winding_direction=WindingDirection.COUNTERCLOCKWISE
        ),
    )
    project = replace(
        sample_request.project, design=replace(design, windings=flipped)
    )

    result = estimate_preliminary(replace(sample_request, project=project))

    coupling = result.couplings[0]
    assert coupling.mutual.value is not None
    assert coupling.mutual.value < 0.0
    assert coupling.common_mode.state is ResultState.UNAVAILABLE
    assert coupling.common_mode.code == DiagnosticCode.COUPLING_NO_LEAKAGE_PATH
    assert coupling.differential_mode.value == pytest.approx(
        2.0 * (result.windings[0].inductance.value or 0.0)
    )


def test_a_single_winding_design_reports_no_coupling(
    sample_request: PreliminaryRequest,
) -> None:
    design = sample_request.project.design
    operating_point = sample_request.project.operating_point
    project = replace(
        sample_request.project,
        design=replace(design, windings=design.windings[:1]),
        operating_point=replace(operating_point, windings=operating_point.windings[:1]),
    )

    result = estimate_preliminary(replace(sample_request, project=project))

    assert result.couplings == ()


def test_no_current_at_all_still_reports_no_winding_inductance(
    sample_request: PreliminaryRequest,
) -> None:
    """The own-ampere-turn fallback must not invent excitation that is absent."""
    operating_point = sample_request.project.operating_point
    unexcited = tuple(
        replace(winding, ac_rms_current_a=0.0, dc_current_a=0.0)
        for winding in operating_point.windings
    )
    project = replace(
        sample_request.project,
        operating_point=replace(operating_point, windings=unexcited),
    )

    result = estimate_preliminary(replace(sample_request, project=project))

    for row in result.windings:
        assert row.inductance.code == DiagnosticCode.INDUCTANCE_NO_EXCITATION


def test_a_core_without_a_catalog_al_still_reports_inductance(
    sample_request: PreliminaryRequest,
) -> None:
    core = sample_request.core
    assert core is not None
    request = replace(sample_request, core=replace(core, al_value_nh=None))

    result = estimate_preliminary(request)

    assert result.core.al_effective.state is ResultState.ESTIMATED
    assert result.core.al_catalog.code == DiagnosticCode.AL_CHECK_NO_CATALOG_AL
    assert result.core.al_deviation.code == DiagnosticCode.AL_CHECK_NO_CATALOG_AL
    assert result.core.mu_r_initial.code == DiagnosticCode.AL_CHECK_NO_CATALOG_AL
    assert result.windings[0].inductance.state is ResultState.ESTIMATED


def test_inductance_survives_a_missing_conductor_record(
    sample_request: PreliminaryRequest,
) -> None:
    """Inductance depends on the core, not on the copper, unlike every other
    winding quantity. Dropping the conductor must not take it down with the
    current densities.
    """
    result = estimate_preliminary(replace(sample_request, conductors_by_winding={}))

    assert result.windings[0].j_ac_rms.state is ResultState.UNAVAILABLE
    assert result.windings[0].inductance.state is ResultState.ESTIMATED


def test_a_non_finite_volume_refuses_only_stored_energy_and_core_loss(
    sample_request: PreliminaryRequest,
) -> None:
    core = sample_request.core
    assert core is not None
    request = replace(sample_request, core=replace(core, volume_m3=float("inf")))

    result = estimate_preliminary(request)

    assert result.core.volume.code == DiagnosticCode.CORE_GEOMETRY_NOT_FINITE
    assert (
        result.core.stored_energy.code
        == DiagnosticCode.STORED_ENERGY_NON_FINITE_VOLUME
    )
    assert result.core.al_effective.state is ResultState.ESTIMATED


# --- The gapped path, through the public entry point ----------------------
#
# The loadline solver and the reluctance network were both unit-tested, and
# nothing called either from `estimate_preliminary`, so every gapped estimate
# silently used `H = NI/l_iron` while its own provenance note said the network
# was used. These tests go through the entry point for exactly that reason.


def _ecore_request(sample_request: PreliminaryRequest, gap_mm: float) -> PreliminaryRequest:
    """`sample_request` with its toroid swapped for an E+E pair.

    The project's pinned material and its recorded B-H series are reused, so
    the only thing that changes between the gapped and ungapped cases is the
    core.
    """
    from inductor_designer.application.services.preliminary_inputs import (
        core_magnetic_properties,
    )
    from inductor_designer.domain.project import ManualECoreSelection
    from inductor_designer.domain.winding import LegPlacement, WindingLeg

    core = ManualECoreSelection(
        centre_leg_width_m=0.0170,
        depth_m=0.0210,
        window_width_m=0.0092,
        window_height_m=0.0187,
        outer_leg_width_m=0.0085,
        yoke_thickness_m=0.0093,
        gaps_m=(gap_mm / 1000.0,) if gap_mm else (),
    )
    windings = tuple(
        replace(
            winding,
            placement=LegPlacement(
                leg=WindingLeg.CENTRE, window_start_m=0.0, window_span_m=0.0187
            ),
        )
        for winding in sample_request.project.design.windings
    )
    project = replace(
        sample_request.project,
        design=replace(sample_request.project.design, core=core, windings=windings),
    )
    properties = core_magnetic_properties(core)
    assert properties is not None
    return replace(sample_request, project=project, core=properties)


def test_a_gap_actually_reaches_the_reported_flux_density(
    sample_request: PreliminaryRequest,
) -> None:
    """The defect this pins: with the loadline unwired, a 1 mm gap changed the
    reported flux density only by the millimetre of iron it removed, because
    `H = NI/l_iron` never saw the gap at all."""
    without = estimate_preliminary(_ecore_request(sample_request, 0.0))
    with_gap = estimate_preliminary(_ecore_request(sample_request, 1.0))

    assert without.core.b_peak_magnitude.value is not None, without.core.b_peak_magnitude
    assert with_gap.core.b_peak_magnitude.value is not None, with_gap.core.b_peak_magnitude
    # A 1 mm gap dominates the reluctance of a ~115 mm iron path at mu_r in the
    # thousands, so flux density must fall by a large factor -- not by the
    # fraction of a percent that the missing millimetre of iron would give.
    assert with_gap.core.b_peak_magnitude.value < (
        without.core.b_peak_magnitude.value / 3.0
    )


def test_the_gap_reaches_the_inductance_factor_too(
    sample_request: PreliminaryRequest,
) -> None:
    """`A_L = mu_abs * A_e / l_iron` carried no gap term, so a gapped core
    reported the inductance factor of the ungapped one."""
    values = []
    for gap_mm in (0.0, 0.5, 1.0):
        estimate = estimate_preliminary(_ecore_request(sample_request, gap_mm))
        assert estimate.core.al_effective.value is not None, estimate.core.al_effective
        values.append(estimate.core.al_effective.value)

    assert values == sorted(values, reverse=True)
    assert values[2] < values[0] / 3.0


def test_the_gapped_estimate_says_it_used_the_loadline(
    sample_request: PreliminaryRequest,
) -> None:
    """A note claiming the network was used must not appear on a number that
    did not use it -- which is precisely what shipped before this."""
    estimate = estimate_preliminary(_ecore_request(sample_request, 1.0))
    notes = " ".join(estimate.core.b_peak_magnitude.notes)
    assert "loadline" in notes.lower()
    assert "fringing" in notes.lower()
