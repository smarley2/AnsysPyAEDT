"""The Maxwell report-quantity names this application asks for.

One table, because these names are the only part of the scalar result path
that cannot be proven without a live AEDT session. A name Maxwell does not
recognize returns no data, which surfaces as an ``unavailable`` quantity with
a reason - never as a wrong number. Correct a name here and nothing else
changes.
"""

from __future__ import annotations

import re

SOLID_LOSS_EXPRESSION = "SolidLoss"
CORE_LOSS_EXPRESSION = "CoreLoss"
ENERGY_EXPRESSION = "Total_Energy"

DEVICE_EXPRESSIONS: tuple[str, ...] = (
    SOLID_LOSS_EXPRESSION,
    CORE_LOSS_EXPRESSION,
    ENERGY_EXPRESSION,
)

# Maxwell writes a matrix entry as <matrix>.<symbol>(<row>,<column>).
MATRIX_KINDS: dict[str, str] = {"L": "inductance", "R": "resistance"}

_MATRIX_PATTERN = re.compile(r"^[^.]+\.(?P<symbol>[LR])\((?P<row>[^,]+),(?P<column>[^)]+)\)$")


def matrix_expressions(
    matrix_name: str, winding_names: tuple[str, ...]
) -> tuple[str, ...]:
    return tuple(
        f"{matrix_name}.{symbol}({row},{column})"
        for row in winding_names
        for column in winding_names
        for symbol in MATRIX_KINDS
    )


def parse_matrix_expression(expression: str) -> tuple[str, str, str] | None:
    """``("inductance", row, column)`` for a matrix entry, ``None`` otherwise."""
    match = _MATRIX_PATTERN.match(expression)
    if match is None:
        return None
    return (
        MATRIX_KINDS[match["symbol"]],
        match["row"],
        match["column"],
    )
