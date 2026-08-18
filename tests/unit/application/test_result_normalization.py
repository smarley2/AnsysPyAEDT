from __future__ import annotations

from collections.abc import Sequence

import pytest

from inductor_designer.application.services.result_normalization import (
    DERIVED_TOTAL_LOSS_NOTE,
    MAXWELL_ENERGY_REASON,
    normalize_scalar_results,
)
from inductor_designer.domain.project import RequestedOutput
from inductor_designer.simulation.raw_results import (
    RawConvergence,
    RawMatrix,
    RawScalarResults,
    RawWindingResult,
)
from inductor_designer.simulation.run_contracts import (
    ComplexValue,
    MatrixValue,
    NormalizedQuantity,
    NormalizedResultSet,
    ResultAvailability,
    RunBackend,
)

ALL_SCALARS = tuple(
    output
    for output in RequestedOutput
    if output not in (RequestedOutput.FLUX_DENSITY, RequestedOutput.CURRENT_DENSITY)
)


def normalize(
    raw: RawScalarResults,
    outputs: Sequence[RequestedOutput] = ALL_SCALARS,
) -> NormalizedResultSet:
    return normalize_scalar_results(
        raw,
        run_id="20260810-120000",
        backend=RunBackend.MAXWELL_3D,
        requested_outputs=tuple(outputs),
        provenance="Maxwell 3D solution data",
    )


def find(
    result_set: NormalizedResultSet, quantity: RequestedOutput, scope: str
) -> NormalizedQuantity:
    return next(
        item
        for item in result_set.quantities
        if item.quantity is quantity and item.scope == scope
    )


def test_a_reported_resistance_is_available_with_unit_and_provenance() -> None:
    raw = RawScalarResults(
        windings=(RawWindingResult(winding_id="w1", resistance_ohm=0.125),)
    )

    entry = find(normalize(raw), RequestedOutput.RESISTANCE, "winding.w1")

    assert entry.availability is ResultAvailability.AVAILABLE
    assert entry.value == 0.125
    assert entry.unit == "ohm"
    assert entry.provenance == "Maxwell 3D solution data"
    assert entry.reason is None


def test_a_missing_quantity_is_unavailable_with_a_dotted_reason() -> None:
    raw = RawScalarResults(windings=(RawWindingResult(winding_id="w1"),))

    entry = find(normalize(raw), RequestedOutput.INDUCTANCE, "winding.w1")

    assert entry.availability is ResultAvailability.UNAVAILABLE
    assert entry.value is None
    assert entry.reason is not None
    assert entry.reason.startswith("inductance.not_reported")


def test_each_backend_states_which_inductance_it_reports() -> None:
    """FEMM reports apparent inductance, Maxwell the matrix self term.

    Measured on one pair of 10-turn windings: FEMM 18.147 uH aiding and
    1.414 uH opposing, half-sum 9.78 uH, against Maxwell 2D's 9.819 uH self
    term. Both were published under the same unqualified label.
    """
    raw = RawScalarResults(
        windings=(RawWindingResult(winding_id="w1", inductance_h=1e-5),)
    )

    for backend, expected in (
        (RunBackend.FEMM, "Apparent inductance"),
        (RunBackend.MAXWELL_2D, "Self-inductance"),
        (RunBackend.MAXWELL_3D, "Self-inductance"),
    ):
        result = normalize_scalar_results(
            raw,
            run_id="20260814-120000",
            backend=backend,
            requested_outputs=(RequestedOutput.INDUCTANCE, RequestedOutput.RESISTANCE),
            provenance="solution data",
        )
        entry = find(result, RequestedOutput.INDUCTANCE, "winding.w1")
        assert entry.approximation is not None
        assert entry.approximation.startswith(expected)
        # The convention belongs to inductance alone.
        assert find(result, RequestedOutput.RESISTANCE, "winding.w1") is not None


def test_a_cross_section_resistance_is_scaled_to_the_whole_turn() -> None:
    """The XY model carries the full flux path but only part of each turn.

    Each turn appears as two axial legs of the model depth, while the real turn
    also runs radially across both core faces, so the solved resistance is short
    by the ratio of the two lengths. The inductance is not scaled: the magnetic
    circuit is modelled whole.
    """
    raw = RawScalarResults(
        windings=(
            RawWindingResult(
                winding_id="w1",
                resistance_ohm=0.010835,
                inductance_h=8.914e-6,
                impedance=complex(0.010835, 5.6),
            ),
        )
    )

    result = normalize_scalar_results(
        raw,
        run_id="20260817-120000",
        backend=RunBackend.MAXWELL_2D,
        requested_outputs=(
            RequestedOutput.RESISTANCE,
            RequestedOutput.INDUCTANCE,
            RequestedOutput.IMPEDANCE,
        ),
        provenance="Maxwell 2D solution data",
        # 51.7 mm of real turn against 2 x 14.48 mm modelled.
        resistance_scale={"w1": (0.0517, 0.02896)},
    )

    factor = 0.0517 / 0.02896
    resistance = find(result, RequestedOutput.RESISTANCE, "winding.w1")
    assert resistance.value == pytest.approx(0.010835 * factor)
    assert resistance.approximation is not None
    assert "51.700 mm" in resistance.approximation
    assert find(
        result, RequestedOutput.INDUCTANCE, "winding.w1"
    ).value == pytest.approx(8.914e-6)
    impedance = find(result, RequestedOutput.IMPEDANCE, "winding.w1")
    assert isinstance(impedance.value, ComplexValue)
    assert impedance.value.real == pytest.approx(0.010835 * factor)
    assert impedance.value.imaginary == pytest.approx(5.6)


def test_without_a_scale_the_resistance_is_reported_as_solved() -> None:
    """Maxwell 3D sweeps the real turn, so it is handed no scale at all."""
    raw = RawScalarResults(
        windings=(RawWindingResult(winding_id="w1", resistance_ohm=0.0175),)
    )

    entry = find(normalize(raw), RequestedOutput.RESISTANCE, "winding.w1")

    assert entry.value == pytest.approx(0.0175)
    assert entry.approximation is None


def test_a_non_finite_value_is_unavailable_rather_than_available() -> None:
    """AEDT answers a report it cannot evaluate with NaN instead of an error.

    A Maxwell 3D matrix over two windings does exactly that, and the run
    reported "available: nan H" for every winding.
    """
    raw = RawScalarResults(
        windings=(
            RawWindingResult(
                winding_id="w1", resistance_ohm=float("nan"), inductance_h=float("inf")
            ),
        )
    )

    result = normalize(raw)

    for quantity in (RequestedOutput.RESISTANCE, RequestedOutput.INDUCTANCE):
        entry = find(result, quantity, "winding.w1")
        assert entry.availability is ResultAvailability.UNAVAILABLE
        assert entry.value is None
        assert entry.reason is not None
        assert "non-finite" in entry.reason


def test_a_matrix_holding_one_non_finite_entry_is_unavailable() -> None:
    raw = RawScalarResults(
        matrices=(
            RawMatrix(
                kind="inductance",
                labels=("w1", "w2"),
                values=((1e-5, float("nan")), (float("nan"), 1e-5)),
            ),
        )
    )

    entry = find(normalize(raw), RequestedOutput.MATRICES, "device.inductance")

    assert entry.availability is ResultAvailability.UNAVAILABLE
    assert entry.reason is not None
    assert "non-finite" in entry.reason


def test_an_impedance_is_reported_as_a_complex_value() -> None:
    raw = RawScalarResults(
        windings=(RawWindingResult(winding_id="w1", impedance=complex(0.1, 3.2)),)
    )

    entry = find(normalize(raw), RequestedOutput.IMPEDANCE, "winding.w1")

    assert entry.value == ComplexValue(real=0.1, imaginary=3.2)


def test_a_reported_matrix_becomes_a_matrix_value() -> None:
    raw = RawScalarResults(
        matrices=(
            RawMatrix(
                kind="inductance",
                labels=("w1", "w2"),
                values=((1e-4, 2e-5), (2e-5, 9e-5)),
            ),
        )
    )

    entry = find(normalize(raw), RequestedOutput.MATRICES, "device.inductance")

    assert isinstance(entry.value, MatrixValue)
    assert entry.value.row_labels == ("w1", "w2")
    assert entry.value.values[0][1] == 2e-5


def test_matrices_are_unavailable_when_the_backend_exposes_none() -> None:
    entry = find(
        normalize(RawScalarResults()), RequestedOutput.MATRICES, "device"
    )

    assert entry.availability is ResultAvailability.UNAVAILABLE
    assert entry.reason is not None
    assert entry.reason.startswith("matrices.not_exposed")


@pytest.mark.parametrize(
    ("backend", "expected_reason"),
    [
        (RunBackend.MAXWELL_3D, "magnetic-energy.not_exposed"),
        (RunBackend.MAXWELL_2D, "magnetic-energy.not_exposed"),
        (RunBackend.FEMM, "magnetic-energy.not_reported"),
    ],
)
def test_a_missing_magnetic_energy_says_whether_the_backend_could_report_it(
    backend: RunBackend, expected_reason: str
) -> None:
    """Would catch reporting `not_reported` for every backend alike.

    An AC Magnetic design exposes no energy report quantity at all (enumerated
    live on AEDT 2025 R2 Commercial, 2026-08-18), so on the Maxwell backends the
    gap is permanent and `not_exposed`. FEMM does expose a stored-energy block
    integral that nothing here reads yet, so its gap stays `not_reported` - a
    thing still worth fetching, not a thing that cannot exist.
    """
    result_set = normalize_scalar_results(
        RawScalarResults(),
        run_id="20260818-120000",
        backend=backend,
        requested_outputs=(RequestedOutput.MAGNETIC_ENERGY,),
        provenance="solution data",
    )

    entry = find(result_set, RequestedOutput.MAGNETIC_ENERGY, "device")
    assert entry.availability is ResultAvailability.UNAVAILABLE
    assert entry.reason is not None
    assert entry.reason.startswith(expected_reason)
    assert (MAXWELL_ENERGY_REASON in entry.reason) is (backend is not RunBackend.FEMM)


def test_total_loss_is_derived_from_the_parts_and_says_so() -> None:
    raw = RawScalarResults(copper_loss_w=3.0, core_loss_w=1.25)

    entry = find(normalize(raw), RequestedOutput.TOTAL_LOSS, "device")

    assert entry.value == 4.25
    assert entry.approximation == DERIVED_TOTAL_LOSS_NOTE
    assert entry.provenance is not None
    assert "derived" in entry.provenance


def test_a_reported_total_loss_is_never_overwritten_by_the_sum() -> None:
    raw = RawScalarResults(copper_loss_w=3.0, core_loss_w=1.25, total_loss_w=4.4)

    entry = find(normalize(raw), RequestedOutput.TOTAL_LOSS, "device")

    assert entry.value == 4.4
    assert entry.approximation is None


def test_total_loss_is_unavailable_when_a_part_is_missing() -> None:
    raw = RawScalarResults(copper_loss_w=3.0)

    entry = find(normalize(raw), RequestedOutput.TOTAL_LOSS, "device")

    assert entry.availability is ResultAvailability.UNAVAILABLE
    assert entry.reason is not None
    assert "core loss" in entry.reason


def test_convergence_reports_the_final_error_and_the_history() -> None:
    raw = RawScalarResults(
        convergence=RawConvergence(passes=((1, 12.5), (2, 0.8)), converged=True)
    )

    entry = find(normalize(raw), RequestedOutput.CONVERGENCE, "device")

    assert entry.value == 0.8
    assert entry.provenance is not None
    assert "2 passes" in entry.provenance
    assert entry.unit == "percent"


def test_a_quantity_the_user_did_not_request_is_absent() -> None:
    raw = RawScalarResults(copper_loss_w=3.0)

    result_set = normalize(raw, outputs=(RequestedOutput.RESISTANCE,))

    assert all(
        item.quantity is RequestedOutput.RESISTANCE for item in result_set.quantities
    )


def test_field_quantities_now_report_through_the_field_normalizer() -> None:
    """M8b produced nothing here; M8c routes fields through their own path."""
    result_set = normalize(
        RawScalarResults(), outputs=(RequestedOutput.FLUX_DENSITY,)
    )

    assert result_set.quantities
    assert all(
        entry.quantity is RequestedOutput.FLUX_DENSITY
        for entry in result_set.quantities
    )
    assert all(
        entry.availability is ResultAvailability.UNAVAILABLE
        for entry in result_set.quantities
    ), "a backend that evaluated no area reports nothing, with a reason"


def test_normalization_never_invents_a_scope_without_a_winding() -> None:
    result_set = normalize(RawScalarResults())

    assert all(not item.scope.startswith("winding.") for item in result_set.quantities)


def test_an_extraction_diagnostic_reaches_every_unavailable_reason() -> None:
    raw = RawScalarResults(diagnostics=("RuntimeError: no solution data",))

    entry = find(normalize(raw), RequestedOutput.COPPER_LOSS, "device")

    assert entry.availability is ResultAvailability.UNAVAILABLE
    assert entry.reason is not None
    assert "no solution data" in entry.reason


def test_the_result_set_carries_its_run_and_backend() -> None:
    result_set = normalize(RawScalarResults())

    assert result_set.run_id == "20260810-120000"
    assert result_set.backend is RunBackend.MAXWELL_3D
