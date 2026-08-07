"""No Qt import: every conversion and label is testable without a QGuiApplication."""

from __future__ import annotations

from inductor_designer.simulation.preliminary import (
    CorePreliminary,
    PreliminaryResult,
    PreliminaryTotals,
    WindingPreliminary,
)
from inductor_designer.simulation.preliminary_contracts import (
    DiagnosticCode,
    ResultState,
    estimated,
    unavailable,
)
from inductor_designer.ui.preliminary_rows import (
    MILLITESLA,
    cell,
    core_rows,
    total_rows,
    winding_rows,
)

REFUSED = unavailable(
    DiagnosticCode.CORE_LOSS_NO_LOSS_DATA_FOR_DC_BIAS,
    "Loss data does not cover the requested DC bias.",
)


def make_result() -> PreliminaryResult:
    return PreliminaryResult(
        core=CorePreliminary(
            b_dc=estimated(0.0847, ("odd symmetry assumed",)),
            b_min=estimated(-0.01),
            b_max=estimated(0.18),
            b_ac_peak=estimated(0.095),
            b_peak_magnitude=estimated(0.18),
            core_loss=REFUSED,
        ),
        windings=(
            WindingPreliminary(
                winding_id="w1",
                conductor_area=estimated(8.2258e-7),
                j_ac_rms=estimated(2.4313e6),
                j_ac_peak=estimated(3.4384e6),
                j_dc=estimated(6.0784e6),
                wire_length=estimated(0.4),
                resistance=estimated(0.008379),
                wire_loss=estimated(0.243),
            ),
        ),
        totals=PreliminaryTotals(
            total_wire_loss=estimated(0.243), core_loss=REFUSED, total_loss=REFUSED
        ),
        material_revision_id="rev-1",
        bh_series_id=None,
        notes=("odd symmetry assumed",),
    )


def test_an_estimated_cell_is_scaled_rounded_and_suffixed() -> None:
    row = cell(estimated(0.0847), MILLITESLA)

    assert row["state"] == ResultState.ESTIMATED.value
    assert row["text"] == "84.700 mT"
    assert row["code"] == ""
    assert row["message"] == ""


def test_a_negative_estimate_keeps_its_sign() -> None:
    assert cell(estimated(-0.01), MILLITESLA)["text"] == "-10.000 mT"


def test_an_unavailable_cell_shows_the_state_with_its_code_and_message() -> None:
    row = cell(REFUSED, MILLITESLA)

    assert row["state"] == ResultState.UNAVAILABLE.value
    assert row["text"] == "Unavailable"
    assert row["code"] == DiagnosticCode.CORE_LOSS_NO_LOSS_DATA_FOR_DC_BIAS
    assert row["message"] == "Loss data does not cover the requested DC bias."


def test_notes_travel_with_the_cell() -> None:
    assert cell(estimated(0.1, ("linear permeability approximation",)), MILLITESLA)[
        "notes"
    ] == ["linear permeability approximation"]


def test_core_rows_cover_the_specified_core_summary() -> None:
    rows = core_rows(make_result())

    assert [row["label"] for row in rows] == [
        "DC flux density",
        "AC flux-density swing",
        "Minimum flux density",
        "Maximum flux density",
        "Peak flux-density magnitude",
        "Core loss",
    ]
    assert rows[0]["text"] == "84.700 mT"
    assert rows[5]["state"] == ResultState.UNAVAILABLE.value


def test_winding_rows_cover_every_specified_winding_quantity() -> None:
    rows = winding_rows(make_result())

    assert len(rows) == 1
    row = rows[0]
    assert row["windingId"] == "w1"
    assert row["conductorArea"]["text"] == "0.8226 mm²"
    assert row["jAcRms"]["text"] == "2.431 A/mm²"
    assert row["jAcPeak"]["text"] == "3.438 A/mm²"
    assert row["jDc"]["text"] == "6.078 A/mm²"
    assert row["wireLength"]["text"] == "400.00 mm"
    assert row["resistance"]["text"] == "8.3790 mΩ"
    assert row["wireLoss"]["text"] == "0.2430 W"


def test_totals_report_the_refusal_instead_of_a_partial_sum() -> None:
    rows = total_rows(make_result())

    assert [row["label"] for row in rows] == [
        "Total wire loss",
        "Core loss",
        "Total preliminary loss",
    ]
    assert rows[0]["text"] == "0.2430 W"
    assert rows[2]["state"] == ResultState.UNAVAILABLE.value
