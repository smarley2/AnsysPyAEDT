from __future__ import annotations

import pytest

from inductor_designer.simulation.raw_results import (
    RawConvergence,
    RawMatrix,
    RawScalarResults,
    RawWindingResult,
)


def test_an_empty_raw_result_reports_nothing_rather_than_zero() -> None:
    raw = RawScalarResults()

    assert raw.windings == ()
    assert raw.matrices == ()
    assert raw.copper_loss_w is None
    assert raw.core_loss_w is None
    assert raw.total_loss_w is None
    assert raw.magnetic_energy_j is None
    assert raw.convergence is None
    assert raw.diagnostics == ()


def test_a_winding_result_keeps_partial_evidence() -> None:
    winding = RawWindingResult(winding_id="w1", resistance_ohm=0.1)

    assert winding.inductance_h is None
    assert winding.impedance is None


def test_a_matrix_must_be_square_against_its_labels() -> None:
    with pytest.raises(ValueError, match="square"):
        RawMatrix(kind="inductance", labels=("w1", "w2"), values=((1.0, 2.0),))


def test_a_square_matrix_is_accepted() -> None:
    matrix = RawMatrix(
        kind="resistance", labels=("w1", "w2"), values=((1.0, 0.1), (0.1, 2.0))
    )

    assert matrix.values[1][0] == 0.1


def test_convergence_rows_are_pass_and_error() -> None:
    convergence = RawConvergence(passes=((1, 12.5), (2, 0.8)), converged=True)

    assert convergence.passes[-1] == (2, 0.8)
    assert convergence.converged is True
