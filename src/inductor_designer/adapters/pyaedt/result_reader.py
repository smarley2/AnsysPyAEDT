"""Reads scalar results out of a solved Maxwell design.

Shared by the 3D and 2D adapters: both ask the same report quantities of the
same solution data. Extraction never fails a solved run - a read error becomes
a diagnostic that the normalizer turns into explicit unavailable reasons.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Protocol

from inductor_designer.simulation.raw_results import (
    RawConvergence,
    RawMatrix,
    RawScalarResults,
    RawWindingResult,
)
from inductor_designer.simulation.result_expressions import (
    CORE_LOSS_EXPRESSION,
    DEVICE_EXPRESSIONS,
    SOLID_LOSS_EXPRESSION,
    matrix_expressions,
    parse_matrix_expression,
)


class ResultCapableApp(Protocol):
    def solution_values(
        self, expressions: tuple[str, ...]
    ) -> Mapping[str, object]: ...

    def convergence_rows(self, name: str) -> tuple[tuple[int, float], ...]: ...


def _real(value: object) -> float | None:
    if isinstance(value, complex):
        return float(value.real)
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _matrix_from(
    values: Mapping[str, object], kind: str, winding_names: tuple[str, ...]
) -> RawMatrix | None:
    rows: list[tuple[float, ...]] = []
    for row in winding_names:
        entries: list[float] = []
        for column in winding_names:
            found = next(
                (
                    _real(value)
                    for expression, value in values.items()
                    if parse_matrix_expression(expression) == (kind, row, column)
                ),
                None,
            )
            if found is None:
                return None
            entries.append(found)
        rows.append(tuple(entries))
    return RawMatrix(kind=kind, labels=winding_names, values=tuple(rows))


def read_scalar_results(
    app: ResultCapableApp,
    *,
    matrix_name: str,
    winding_names: tuple[str, ...],
    setup_name: str,
    frequency_hz: float,
) -> RawScalarResults:
    try:
        expressions = matrix_expressions(matrix_name, winding_names) + DEVICE_EXPRESSIONS
        values = dict(app.solution_values(expressions))
    except Exception as error:  # noqa: BLE001 - a read error is evidence, not a crash
        return RawScalarResults(diagnostics=(f"{type(error).__name__}: {error}",))

    diagnostics: list[str] = []
    inductance = _matrix_from(values, "inductance", winding_names)
    resistance = _matrix_from(values, "resistance", winding_names)
    matrices = tuple(item for item in (resistance, inductance) if item is not None)

    windings: list[RawWindingResult] = []
    for index, name in enumerate(winding_names):
        r = None if resistance is None else resistance.values[index][index]
        inductance_h = None if inductance is None else inductance.values[index][index]
        impedance = (
            complex(r, 2.0 * math.pi * frequency_hz * inductance_h)
            if r is not None and inductance_h is not None
            else None
        )
        windings.append(
            RawWindingResult(
                winding_id=name,
                resistance_ohm=r,
                inductance_h=inductance_h,
                impedance=impedance,
            )
        )

    try:
        passes = app.convergence_rows(setup_name)
    except Exception as error:  # noqa: BLE001 - same rule as above
        diagnostics.append(f"{type(error).__name__}: {error}")
        passes = ()

    return RawScalarResults(
        windings=tuple(windings),
        matrices=matrices,
        copper_loss_w=_real(values.get(SOLID_LOSS_EXPRESSION)),
        core_loss_w=_real(values.get(CORE_LOSS_EXPRESSION)),
        convergence=RawConvergence(passes=passes) if passes else None,
        solver_status=f"Solved setup {setup_name}.",
        diagnostics=tuple(diagnostics),
    )
