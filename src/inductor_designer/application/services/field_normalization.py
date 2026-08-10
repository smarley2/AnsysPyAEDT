"""Per-section field values and their two aggregates.

The design fixes what is reported: every section individually, the worst
section mean, the across-section area-weighted average, and the point maximum.
Aggregates come from the sections that evaluated; when some failed, the
aggregate says which. When all failed, there is no aggregate, only a reason.
"""

from __future__ import annotations

from collections.abc import Sequence

from inductor_designer.domain.project import RequestedOutput
from inductor_designer.simulation.raw_results import RawFieldSection
from inductor_designer.simulation.result_vocabulary import (
    NOT_EXPOSED,
    convention_for,
    reason_code,
    unit_for,
)
from inductor_designer.simulation.run_contracts import (
    CurrentConvention,
    NormalizedQuantity,
    ResultAvailability,
)

DC_BIASED_FIELD_NOTE = (
    "DC-biased total field from one solve: the DC and AC components cannot be "
    "separated without a second, superposition-invalid solve."
)


def _entry(
    quantity: RequestedOutput,
    scope: str,
    value: float | None,
    provenance: str,
    *,
    dc_biased: bool,
    reason: str | None = None,
    approximation: str | None = None,
) -> NormalizedQuantity:
    convention = (
        CurrentConvention.COMBINED if dc_biased else convention_for(quantity)
    )
    if value is None:
        return NormalizedQuantity(
            quantity=quantity,
            scope=scope,
            availability=ResultAvailability.UNAVAILABLE,
            value=None,
            unit=None,
            current_convention=convention,
            approximation=None,
            reason=reason or f"{reason_code(quantity, NOT_EXPOSED)}: no value.",
            provenance=None,
        )
    notes = [note for note in (approximation, DC_BIASED_FIELD_NOTE if dc_biased else None) if note]
    return NormalizedQuantity(
        quantity=quantity,
        scope=scope,
        availability=ResultAvailability.AVAILABLE,
        value=value,
        unit=unit_for(quantity),
        current_convention=convention,
        approximation=" ".join(notes) or None,
        reason=None,
        provenance=provenance,
    )


def normalize_field_results(
    quantity: RequestedOutput,
    sections: Sequence[RawFieldSection],
    *,
    scope: str,
    provenance: str,
    dc_biased: bool = False,
) -> tuple[NormalizedQuantity, ...]:
    """One entry per section, plus the worst-section, average and maximum."""
    entries: list[NormalizedQuantity] = []
    for section in sections:
        entries.append(
            _entry(
                quantity,
                section.scope,
                section.mean,
                f"{provenance}; section {section.section_id}, "
                f"area {section.area_m2:.6g} m^2",
                dc_biased=dc_biased,
                reason=(
                    None
                    if section.mean is not None
                    else f"{reason_code(quantity, NOT_EXPOSED)}: "
                    f"section {section.section_id} did not evaluate. "
                    f"{section.diagnostic or ''}".strip()
                ),
            )
        )

    evaluated = [section for section in sections if section.mean is not None]
    failed = [section.section_id for section in sections if section.mean is None]
    partial_note = (
        f"Computed from {len(evaluated)} of {len(sections)} sections; "
        f"{', '.join(failed)} did not evaluate."
        if failed and evaluated
        else None
    )
    if not sections:
        empty_reason = (
            f"{reason_code(quantity, NOT_EXPOSED)}: the backend evaluated no "
            "area for this quantity."
        )
    else:
        empty_reason = (
            f"{reason_code(quantity, NOT_EXPOSED)}: no section evaluated; "
            f"{', '.join(failed)} failed."
        )

    means = [section.mean for section in evaluated if section.mean is not None]
    worst = max(means, default=None)
    total_area = sum(section.area_m2 for section in evaluated)
    average = (
        sum(
            section.mean * section.area_m2
            for section in evaluated
            if section.mean is not None
        )
        / total_area
        if means and total_area > 0.0
        else None
    )
    maximum = max(
        (section.maximum for section in evaluated if section.maximum is not None),
        default=None,
    )

    entries.append(
        _entry(
            quantity,
            f"{scope}.worst-section-mean",
            worst,
            provenance,
            dc_biased=dc_biased,
            reason=empty_reason,
            approximation=partial_note,
        )
    )
    entries.append(
        _entry(
            quantity,
            f"{scope}.area-weighted-average",
            average,
            provenance,
            dc_biased=dc_biased,
            reason=empty_reason,
            approximation=partial_note,
        )
    )
    entries.append(
        _entry(
            quantity,
            f"{scope}.maximum",
            maximum,
            provenance,
            dc_biased=dc_biased,
            reason=empty_reason,
            approximation=partial_note,
        )
    )
    return tuple(entries)
