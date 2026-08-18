"""Raw backend values into the Normalized Result Set.

The rule from the roadmap realignment section 8 is absolute here: a quantity
that cannot be obtained without misrepresentation is ``unavailable`` with a
reason. Nothing is estimated, and nothing is silently omitted.
"""

from __future__ import annotations

import math
from collections.abc import Mapping

from inductor_designer.application.services.field_normalization import (
    normalize_field_results,
)
from inductor_designer.domain.project import RequestedOutput
from inductor_designer.simulation.failure_advice import convergence_advice
from inductor_designer.simulation.raw_results import RawFieldSection, RawScalarResults
from inductor_designer.simulation.result_vocabulary import (
    DEVICE_SCOPE,
    FIELD_QUANTITIES,
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

FEMM_FIELD_REASON = (
    "FEMM's block integrals expose the field components, not the magnitude, "
    "and around a toroid those components cancel; a magnitude mean cannot be "
    "obtained without misrepresentation."
)

DERIVED_TOTAL_LOSS_NOTE = (
    "Sum of the reported copper loss and core loss; the backend did not "
    "report a total."
)


def _finite(value: NormalizedValue) -> bool:
    """Whether every number inside a scalar, complex or matrix value is finite."""
    if isinstance(value, MatrixValue):
        return all(_finite(cell) for row in value.values for cell in row)
    if isinstance(value, ComplexValue):
        return math.isfinite(value.real) and math.isfinite(value.imaginary)
    return math.isfinite(value)


def _available(
    quantity: RequestedOutput,
    scope: str,
    value: NormalizedValue,
    provenance: str,
    *,
    approximation: str | None = None,
) -> NormalizedQuantity:
    if not _finite(value):
        # AEDT answers a report request it cannot evaluate with NaN rather than
        # with an error -- a Maxwell 3D matrix over two windings does exactly
        # that -- and "available: nan H" is a wrong number wearing the label of
        # a right one. Observed live on AEDT 2025.2, 2026-08-14.
        return _unavailable(
            quantity,
            scope,
            f"{reason_code(quantity, NOT_REPORTED)}: The backend returned a "
            "non-finite value, so the quantity was not evaluated.",
        )
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


SELF_INDUCTANCE_NOTE = (
    "Self-inductance: the diagonal of the solver's winding matrix, which "
    "excludes the other windings' currents. It is not what a meter reads with "
    "every winding energised."
)
APPARENT_INDUCTANCE_NOTE = (
    "Apparent inductance at this operating point: flux linkage over current "
    "with every winding energised, so it carries the mutual term. Two aiding "
    "windings read L + M here and two opposing ones read L - M, where the "
    "Maxwell backends report the self term L instead."
)


def _turn_length_note(turn_length_m: float, modelled_m: float) -> str:
    return (
        "Scaled from the cross-section to the whole turn: the XY model carries "
        "the complete magnetic circuit but only the two axial legs of each "
        f"turn's copper, {modelled_m * 1000.0:.3f} mm of the "
        f"{turn_length_m * 1000.0:.3f} mm the packing gives one turn, so the "
        f"solved resistance is multiplied by {turn_length_m / modelled_m:.4f}. "
        "The factor assumes the radial legs and corner arcs carry the same "
        "current distribution as the modelled axial legs; the inductance needs "
        "no such correction, since the flux path is modelled whole."
    )


def _inductance_convention(backend: RunBackend) -> str:
    """Which inductance the backend reports, in its own words.

    FEMM's circuit result is the apparent inductance and Maxwell's matrix
    diagonal is the self inductance. Measured 2026-08-14 on one pair of 10-turn
    windings: FEMM read 18.147 uH aiding and 1.414 uH opposing, whose half-sum
    9.78 uH matches Maxwell 2D's 9.819 uH self term. Same physics, two
    definitions, and they used to be published under one unqualified label.
    """
    return (
        APPARENT_INDUCTANCE_NOTE
        if backend is RunBackend.FEMM
        else SELF_INDUCTANCE_NOTE
    )


def _winding_entries(
    quantity: RequestedOutput,
    raw: RawScalarResults,
    provenance: str,
    backend: RunBackend,
    resistance_scale: Mapping[str, tuple[float, float]] | None = None,
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
        convention = (
            _inductance_convention(backend)
            if quantity is RequestedOutput.INDUCTANCE
            else None
        )
        lengths = (resistance_scale or {}).get(winding.winding_id)
        if quantity is RequestedOutput.RESISTANCE:
            value: float | complex | None = winding.resistance_ohm
            if value is not None and lengths is not None:
                turn_length_m, modelled_m = lengths
                value = value * (turn_length_m / modelled_m)
                convention = _turn_length_note(turn_length_m, modelled_m)
        elif quantity is RequestedOutput.INDUCTANCE:
            value = winding.inductance_h
        else:
            value = winding.impedance
            if value is not None and lengths is not None:
                # Only the resistive part is short; the reactance is complete.
                turn_length_m, modelled_m = lengths
                value = complex(
                    value.real * (turn_length_m / modelled_m), value.imag
                )
                convention = _turn_length_note(turn_length_m, modelled_m)
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
                    approximation=convention,
                )
            )
        else:
            entries.append(
                _available(
                    quantity, scope, value, provenance, approximation=convention
                )
            )
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


MAXWELL_ENERGY_REASON = (
    "An AC Magnetic design exposes no energy quantity: its report categories "
    "hold losses, the winding matrix, flux linkage, induced voltage and input "
    "current, and nothing else. Enumerated live on AEDT 2025 R2 Commercial, "
    "2026-08-18. Energy needs a Magnetostatic or Transient solution."
)


def _magnetic_energy(
    raw: RawScalarResults, backend: RunBackend, provenance: str
) -> NormalizedQuantity:
    """Not exposed on the Maxwell backends, merely unread on FEMM.

    The distinction is the point: this application asked Maxwell for
    `Total_Energy` until 2026-08-18 and read the silence as "the backend
    reported nothing", which invites re-checking every run. AC Magnetic has no
    energy quantity to report, so say so once. FEMM does expose a stored-energy
    block integral that nothing here reads yet, which is `not_reported`.
    """
    if raw.magnetic_energy_j is not None:
        return _available(
            RequestedOutput.MAGNETIC_ENERGY,
            DEVICE_SCOPE,
            raw.magnetic_energy_j,
            provenance,
        )
    if backend is RunBackend.FEMM:
        return _missing(
            RequestedOutput.MAGNETIC_ENERGY,
            DEVICE_SCOPE,
            raw,
            "The backend reported no magnetic-energy.",
        )
    return _missing(
        RequestedOutput.MAGNETIC_ENERGY,
        DEVICE_SCOPE,
        raw,
        MAXWELL_ENERGY_REASON,
        code=NOT_EXPOSED,
    )


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


def _convergence(
    raw: RawScalarResults,
    provenance: str,
    *,
    percent_error_target: float | None = None,
    maximum_passes: int | None = None,
) -> NormalizedQuantity:
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
    advice = convergence_advice(
        final_error_percent=final_error,
        target_percent=percent_error_target,
        completed_passes=final_pass,
        maximum_passes=maximum_passes,
        converged=convergence.converged,
    )
    return _available(
        RequestedOutput.CONVERGENCE,
        DEVICE_SCOPE,
        final_error,
        f"{provenance}: {final_pass} passes, {state}",
        # An unconverged solve stays AVAILABLE: the number is real, and the
        # note is what stops it being read as a converged number.
        approximation=None if advice is None else f"{advice.code}: {advice.action}",
    )


def _field_entries(
    quantity: RequestedOutput,
    raw: RawScalarResults,
    backend: RunBackend,
    provenance: str,
    dc_biased: bool,
) -> tuple[NormalizedQuantity, ...]:
    if backend is RunBackend.FEMM:
        return (
            _unavailable(
                quantity,
                DEVICE_SCOPE,
                f"{reason_code(quantity, NOT_EXPOSED)}: {FEMM_FIELD_REASON}",
            ),
        )
    if quantity is RequestedOutput.FLUX_DENSITY:
        return normalize_field_results(
            quantity,
            raw.flux_density_sections,
            scope="core",
            provenance=provenance,
            dc_biased=dc_biased,
        )
    entries: list[NormalizedQuantity] = []
    by_winding: dict[str, list[RawFieldSection]] = {}
    for section in raw.current_density_sections:
        winding_id = section.scope.split(".")[1] if "." in section.scope else "unknown"
        by_winding.setdefault(winding_id, []).append(section)
    if not by_winding:
        return normalize_field_results(
            quantity,
            (),
            scope=DEVICE_SCOPE,
            provenance=provenance,
            dc_biased=dc_biased,
        )
    for winding_id, sections in by_winding.items():
        entries.extend(
            normalize_field_results(
                quantity,
                tuple(sections),
                scope=winding_scope(winding_id),
                provenance=provenance,
                dc_biased=dc_biased,
            )
        )
    return tuple(entries)


def normalize_scalar_results(
    raw: RawScalarResults,
    *,
    run_id: str,
    backend: RunBackend,
    requested_outputs: tuple[RequestedOutput, ...],
    provenance: str,
    dc_biased: bool = False,
    resistance_scale: Mapping[str, tuple[float, float]] | None = None,
    percent_error_target: float | None = None,
    maximum_passes: int | None = None,
) -> NormalizedResultSet:
    """One entry per requested scalar quantity per scope, never a silent gap.

    `resistance_scale` maps a winding to `(real turn length, modelled length)`
    for a cross-section backend, whose resistance covers only part of each turn.
    Omitted for Maxwell 3D, which models the turns as they are.
    """
    quantities: list[NormalizedQuantity] = []
    for quantity in requested_outputs:
        if quantity in FIELD_QUANTITIES:
            quantities.extend(
                _field_entries(quantity, raw, backend, provenance, dc_biased)
            )
            continue
        if quantity not in SCALAR_QUANTITIES:
            continue
        if quantity in PER_WINDING_QUANTITIES:
            quantities.extend(
                _winding_entries(
                    quantity, raw, provenance, backend, resistance_scale
                )
            )
        elif quantity is RequestedOutput.MATRICES:
            quantities.extend(_matrix_entries(raw, provenance))
        elif quantity is RequestedOutput.TOTAL_LOSS:
            quantities.append(_total_loss(raw, provenance))
        elif quantity is RequestedOutput.CONVERGENCE:
            quantities.append(
                _convergence(
                    raw,
                    provenance,
                    percent_error_target=percent_error_target,
                    maximum_passes=maximum_passes,
                )
            )
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
                _magnetic_energy(raw, backend, provenance)
            )
    return NormalizedResultSet(
        run_id=run_id, backend=backend, quantities=tuple(quantities)
    )
