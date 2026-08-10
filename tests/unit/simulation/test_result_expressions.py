from __future__ import annotations

from inductor_designer.simulation.result_expressions import (
    CORE_LOSS_EXPRESSION,
    DEVICE_EXPRESSIONS,
    ENERGY_EXPRESSION,
    SOLID_LOSS_EXPRESSION,
    matrix_expressions,
    parse_matrix_expression,
)


def test_matrix_expressions_cover_every_pair_and_both_kinds() -> None:
    expressions = matrix_expressions("Matrix1", ("w1", "w2"))

    assert "Matrix1.L(w1,w1)" in expressions
    assert "Matrix1.L(w1,w2)" in expressions
    assert "Matrix1.R(w2,w2)" in expressions
    assert len(expressions) == 2 * 2 * 2


def test_one_winding_yields_one_pair_per_kind() -> None:
    assert matrix_expressions("Matrix1", ("w1",)) == (
        "Matrix1.L(w1,w1)",
        "Matrix1.R(w1,w1)",
    )


def test_an_expression_round_trips_back_to_its_meaning() -> None:
    assert parse_matrix_expression("Matrix1.L(w1,w2)") == ("inductance", "w1", "w2")
    assert parse_matrix_expression("Matrix1.R(w2,w1)") == ("resistance", "w2", "w1")


def test_a_device_expression_is_not_a_matrix_expression() -> None:
    assert parse_matrix_expression(SOLID_LOSS_EXPRESSION) is None
    assert parse_matrix_expression("nonsense") is None


def test_device_expressions_are_the_assumed_maxwell_names() -> None:
    assert DEVICE_EXPRESSIONS == (
        SOLID_LOSS_EXPRESSION,
        CORE_LOSS_EXPRESSION,
        ENERGY_EXPRESSION,
    )
    assert SOLID_LOSS_EXPRESSION == "SolidLoss"
    assert CORE_LOSS_EXPRESSION == "CoreLoss"
    assert ENERGY_EXPRESSION == "Total_Energy"
