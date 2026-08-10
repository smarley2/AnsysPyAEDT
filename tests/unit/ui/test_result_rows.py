from __future__ import annotations

from inductor_designer.domain.project import RequestedOutput
from inductor_designer.simulation.run_contracts import (
    ComplexValue,
    CurrentConvention,
    MatrixValue,
    NormalizedQuantity,
    NormalizedResultSet,
    ResultAvailability,
    RunBackend,
)
from inductor_designer.ui.result_rows import result_rows


def available(
    quantity: RequestedOutput,
    scope: str,
    value: object,
    *,
    approximation: str | None = None,
) -> NormalizedQuantity:
    return NormalizedQuantity(
        quantity=quantity,
        scope=scope,
        availability=ResultAvailability.AVAILABLE,
        value=value,  # type: ignore[arg-type]
        unit="unit",
        current_convention=CurrentConvention.NOT_APPLICABLE,
        approximation=approximation,
        reason=None,
        provenance="test",
    )


def unavailable(quantity: RequestedOutput, scope: str, reason: str) -> NormalizedQuantity:
    return NormalizedQuantity(
        quantity=quantity,
        scope=scope,
        availability=ResultAvailability.UNAVAILABLE,
        value=None,
        unit=None,
        current_convention=CurrentConvention.NOT_APPLICABLE,
        approximation=None,
        reason=reason,
        provenance=None,
    )


def rows(*quantities: NormalizedQuantity) -> list[dict[str, str]]:
    return result_rows(
        NormalizedResultSet(
            run_id="r", backend=RunBackend.FEMM, quantities=tuple(quantities)
        )
    )


def test_a_resistance_renders_in_milliohms_with_its_winding() -> None:
    row = rows(available(RequestedOutput.RESISTANCE, "winding.w1", 0.125))[0]

    assert row["label"] == "Resistance (w1)"
    assert row["text"].startswith("125.0")
    assert row["text"].endswith("mΩ")


def test_an_inductance_renders_in_microhenries() -> None:
    row = rows(available(RequestedOutput.INDUCTANCE, "winding.w1", 1e-4))[0]

    assert row["text"] == "100.000 µH"


def test_an_impedance_renders_both_parts() -> None:
    row = rows(
        available(
            RequestedOutput.IMPEDANCE,
            "winding.w1",
            ComplexValue(real=0.125, imaginary=0.079),
        )
    )[0]

    assert "j" in row["text"]
    assert row["text"].count("mΩ") == 2


def test_a_device_loss_has_no_scope_suffix() -> None:
    row = rows(available(RequestedOutput.COPPER_LOSS, "device", 3.0))[0]

    assert row["label"] == "Copper loss"
    assert row["text"] == "3.0000 W"


def test_a_derived_total_loss_shows_its_note() -> None:
    row = rows(
        available(
            RequestedOutput.TOTAL_LOSS,
            "device",
            4.25,
            approximation="Sum of the reported copper loss and core loss.",
        )
    )[0]

    assert "Sum of the reported" in row["text"]


def test_a_matrix_points_at_the_export_rather_than_filling_a_cell() -> None:
    row = rows(
        available(
            RequestedOutput.MATRICES,
            "device.inductance",
            MatrixValue(
                row_labels=("w1", "w2"),
                column_labels=("w1", "w2"),
                values=((1.0, 0.0), (0.0, 1.0)),
            ),
        )
    )[0]

    assert row["label"] == "Matrix (inductance)"
    assert "2x2" in row["text"]
    assert "results.json" in row["text"]


def test_an_unavailable_quantity_shows_its_reason_not_a_blank() -> None:
    row = rows(
        unavailable(
            RequestedOutput.CORE_LOSS,
            "device",
            "core-loss.not_reported: FEMM does not report a core loss.",
        )
    )[0]

    assert row["text"].startswith("core-loss.not_reported")


def test_every_quantity_produces_exactly_one_row() -> None:
    produced = rows(
        available(RequestedOutput.RESISTANCE, "winding.w1", 0.1),
        available(RequestedOutput.RESISTANCE, "winding.w2", 0.2),
        unavailable(RequestedOutput.CORE_LOSS, "device", "core-loss.not_reported: x"),
    )

    assert len(produced) == 3
