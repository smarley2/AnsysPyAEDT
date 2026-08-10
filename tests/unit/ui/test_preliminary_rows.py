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
    DIMENSIONLESS,
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
            effective_area=estimated(6.56e-5),
            path_length=estimated(0.0814),
            volume=estimated(5.34e-6),
            mu_r_effective=estimated(795.7747154594767),
            mu_r_initial=estimated(994.7183943243459),
            al_catalog=estimated(1.25e-6),
            al_effective=estimated(1e-6),
            al_deviation=estimated(-0.2),
            stored_energy=estimated(7.5e-4),
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
                inductance=estimated(1e-4),
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
        "Effective area A_e",
        "Magnetic path length l_e",
        "Effective volume V_e",
        "Effective relative permeability",
        "Initial relative permeability (from catalog A_L)",
        "Catalog A_L",
        "Effective A_L",
        "A_L deviation",
        "Stored energy",
    ]
    assert rows[0]["text"] == "84.700 mT"
    assert rows[5]["state"] == ResultState.UNAVAILABLE.value
    assert rows[6]["text"] == "65.6000 mm²"
    assert rows[7]["text"] == "81.40 mm"
    assert rows[8]["text"] == "5.340 cm³"
    assert rows[9]["text"] == "795.8"
    assert rows[10]["text"] == "994.7"
    assert rows[11]["text"] == "1250.00 nH/N²"
    assert rows[12]["text"] == "1000.00 nH/N²"
    assert rows[13]["text"] == "-20.00 %"
    assert rows[14]["text"] == "0.7500 mJ"


def test_a_dimensionless_cell_carries_no_unit_suffix_or_trailing_space() -> None:
    """A permeability has no unit, and "795.8 " would show as a stray space."""
    assert cell(estimated(795.7747154594767), DIMENSIONLESS)["text"] == "795.8"


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
    assert row["inductance"]["text"] == "100.000 µH"


def test_totals_report_the_refusal_instead_of_a_partial_sum() -> None:
    rows = total_rows(make_result())

    assert [row["label"] for row in rows] == [
        "Total wire loss",
        "Core loss",
        "Total preliminary loss",
    ]
    assert rows[0]["text"] == "0.2430 W"
    assert rows[2]["state"] == ResultState.UNAVAILABLE.value
