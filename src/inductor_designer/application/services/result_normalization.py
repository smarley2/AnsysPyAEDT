"""Raw backend values into the Normalized Result Set.

The rule from the roadmap realignment section 8 is absolute here: a quantity
that cannot be obtained without misrepresentation is ``unavailable`` with a
reason. Nothing is estimated, and nothing is silently omitted.
"""

from __future__ import annotations

from inductor_designer.domain.project import RequestedOutput
from inductor_designer.simulation.raw_results import RawScalarResults
from inductor_designer.simulation.result_vocabulary import (
    DEVICE_SCOPE,
    NOT_EXPOSED,
    NOT_REPORTED,
    PER_WINDING_QUANTITIES,
    SCALAR_QUANTITIES,
    convention_for,
    reason_code,
    unit_for,
    winding_scope,
)
from inductor_designer.simulation.run_contracts import (
    ComplexValue,
    MatrixValue,
    NormalizedQuantity,
    NormalizedResultSet,
    NormalizedValue,
    ResultAvailability,
    RunBackend,
)

DERIVED_TOTAL_LOSS_NOTE = (
    "Sum of the reported copper loss and core loss; the backend did not "
    "report a total."
)


def _available(
    quantity: RequestedOutput,
    scope: str,
    value: NormalizedValue,
    provenance: str,
    *,
    approximation: str | None = None,
) -> NormalizedQuantity:
    return NormalizedQuantity(
        quantity=quantity,
        scope=scope,
        availability=ResultAvailability.AVAILABLE,
        value=value,
        unit=unit_for(quantity),
        current_convention=convention_for(quantity),
        approximation=approximation,
        reason=None,
        provenance=provenance,
    )


def _unavailable(
    quantity: RequestedOutput, scope: str, reason: str
) -> NormalizedQuantity:
    return NormalizedQuantity(
        quantity=quantity,
        scope=scope,
        availability=ResultAvailability.UNAVAILABLE,
        value=None,
        unit=None,
        current_convention=convention_for(quantity),
        approximation=None,
        reason=reason,
        provenance=None,
    )


def _missing(
    quantity: RequestedOutput,
    scope: str,
    raw: RawScalarResults,
    detail: str,
    *,
    code: str = NOT_REPORTED,
) -> NormalizedQuantity:
    """An unavailable entry that carries any extraction diagnostic with it."""
    suffix = f" {' '.join(raw.diagnostics)}" if raw.diagnostics else ""
    return _unavailable(quantity, scope, f"{reason_code(quantity, code)}: {detail}{suffix}")


def _winding_entries(
    quantity: RequestedOutput, raw: RawScalarResults, provenance: str
) -> tuple[NormalizedQuantity, ...]:
    if not raw.windings:
        return (
            _missing(
                quantity,
                DEVICE_SCOPE,
                raw,
                "The backend reported no per-winding results.",
            ),
        )
    entries: list[NormalizedQuantity] = []
    for winding in raw.windings:
        scope = winding_scope(winding.winding_id)
        if quantity is RequestedOutput.RESISTANCE:
            value: float | complex | None = winding.resistance_ohm
        elif quantity is RequestedOutput.INDUCTANCE:
            value = winding.inductance_h
        else:
            value = winding.impedance
        if value is None:
            entries.append(
                _missing(
                    quantity,
                    scope,
                    raw,
                    f"The backend reported no {quantity.value} for "
                    f"{winding.winding_id}.",
                )
            )
        elif isinstance(value, complex):
            entries.append(
                _available(
                    quantity,
                    scope,
                    ComplexValue(real=value.real, imaginary=value.imag),
                    provenance,
                )
            )
        else:
            entries.append(_available(quantity, scope, value, provenance))
    return tuple(entries)


def _matrix_entries(
    raw: RawScalarResults, provenance: str
) -> tuple[NormalizedQuantity, ...]:
    if not raw.matrices:
        return (
            _missing(
                RequestedOutput.MATRICES,
                DEVICE_SCOPE,
                raw,
                "The backend exposes no matrix without reinterpretation.",
                code=NOT_EXPOSED,
            ),
        )
    return tuple(
        _available(
            RequestedOutput.MATRICES,
            f"{DEVICE_SCOPE}.{matrix.kind}",
            MatrixValue(
                row_labels=matrix.labels,
                column_labels=matrix.labels,
                values=tuple(tuple(row) for row in matrix.values),
            ),
            provenance,
        )
        for matrix in raw.matrices
    )


def _device_scalar(
    quantity: RequestedOutput,
    value: float | None,
    raw: RawScalarResults,
    provenance: str,
) -> NormalizedQuantity:
    if value is None:
        return _missing(
            quantity,
            DEVICE_SCOPE,
            raw,
            f"The backend reported no {quantity.value}.",
        )
    return _available(quantity, DEVICE_SCOPE, value, provenance)


def _total_loss(raw: RawScalarResults, provenance: str) -> NormalizedQuantity:
    if raw.total_loss_w is not None:
        return _available(
            RequestedOutput.TOTAL_LOSS, DEVICE_SCOPE, raw.total_loss_w, provenance
        )
    if raw.copper_loss_w is None or raw.core_loss_w is None:
        missing = "copper loss" if raw.copper_loss_w is None else "core loss"
        return _missing(
            RequestedOutput.TOTAL_LOSS,
            DEVICE_SCOPE,
            raw,
            "The backend reported neither a total loss nor a "
            f"{missing} to sum.",
        )
    return _available(
        RequestedOutput.TOTAL_LOSS,
        DEVICE_SCOPE,
        raw.copper_loss_w + raw.core_loss_w,
        f"derived from {provenance}",
        approximation=DERIVED_TOTAL_LOSS_NOTE,
    )


def _convergence(raw: RawScalarResults, provenance: str) -> NormalizedQuantity:
    convergence = raw.convergence
    if convergence is None or not convergence.passes:
        return _missing(
            RequestedOutput.CONVERGENCE,
            DEVICE_SCOPE,
            raw,
            "The backend reported no convergence history.",
            code=NOT_EXPOSED,
        )
    final_pass, final_error = convergence.passes[-1]
    state = (
        "converged"
        if convergence.converged
        else "did not converge"
        if convergence.converged is False
        else "convergence state not reported"
    )
    return _available(
        RequestedOutput.CONVERGENCE,
        DEVICE_SCOPE,
        final_error,
        f"{provenance}: {final_pass} passes, {state}",
    )


def normalize_scalar_results(
    raw: RawScalarResults,
    *,
    run_id: str,
    backend: RunBackend,
    requested_outputs: tuple[RequestedOutput, ...],
    provenance: str,
) -> NormalizedResultSet:
    """One entry per requested scalar quantity per scope, never a silent gap."""
    quantities: list[NormalizedQuantity] = []
    for quantity in requested_outputs:
        if quantity not in SCALAR_QUANTITIES:
            # Field quantities belong to M8c; this service never invents them.
            continue
        if quantity in PER_WINDING_QUANTITIES:
            quantities.extend(_winding_entries(quantity, raw, provenance))
        elif quantity is RequestedOutput.MATRICES:
            quantities.extend(_matrix_entries(raw, provenance))
        elif quantity is RequestedOutput.TOTAL_LOSS:
            quantities.append(_total_loss(raw, provenance))
        elif quantity is RequestedOutput.CONVERGENCE:
            quantities.append(_convergence(raw, provenance))
        elif quantity is RequestedOutput.COPPER_LOSS:
            quantities.append(
                _device_scalar(quantity, raw.copper_loss_w, raw, provenance)
            )
        elif quantity is RequestedOutput.CORE_LOSS:
            quantities.append(
                _device_scalar(quantity, raw.core_loss_w, raw, provenance)
            )
        else:
            quantities.append(
                _device_scalar(quantity, raw.magnetic_energy_j, raw, provenance)
            )
    return NormalizedResultSet(
        run_id=run_id, backend=backend, quantities=tuple(quantities)
    )
