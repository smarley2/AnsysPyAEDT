from __future__ import annotations

import math
from dataclasses import replace

from inductor_designer.simulation.preliminary import (
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
    request = replace(sample_request, core_record=None)

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
    request = replace(sample_request, core_record=None)

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
    result = estimate_preliminary(replace(sample_request, core_record=None))

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
