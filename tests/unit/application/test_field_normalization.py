from __future__ import annotations

from collections.abc import Sequence

import pytest

from inductor_designer.application.services.field_normalization import (
    DC_BIASED_FIELD_NOTE,
    normalize_field_results,
)
from inductor_designer.domain.project import RequestedOutput
from inductor_designer.simulation.raw_results import RawFieldSection
from inductor_designer.simulation.run_contracts import (
    CurrentConvention,
    NormalizedQuantity,
    ResultAvailability,
)


def section(
    name: str, mean: float | None, maximum: float | None, area: float = 1e-4
) -> RawFieldSection:
    return RawFieldSection(
        section_id=name,
        scope=f"core.section.{name}",
        area_m2=area,
        mean=mean,
        maximum=maximum,
        diagnostic=None if mean is not None else "no data",
    )


def normalize(
    sections: Sequence[RawFieldSection], *, dc_biased: bool = False
) -> tuple[NormalizedQuantity, ...]:
    return normalize_field_results(
        RequestedOutput.FLUX_DENSITY,
        sections,
        scope="core",
        provenance="Maxwell 3D field calculator",
        dc_biased=dc_biased,
    )


def find(entries: Sequence[NormalizedQuantity], scope: str) -> NormalizedQuantity:
    return next(entry for entry in entries if entry.scope == scope)


def test_each_section_is_reported_individually() -> None:
    entries = normalize([section("a", 0.1, 0.2), section("b", 0.3, 0.5)])

    assert find(entries, "core.section.a").value == 0.1
    assert find(entries, "core.section.b").value == 0.3


def test_a_section_entry_names_its_area_in_the_provenance() -> None:
    entry = find(normalize([section("a", 0.1, 0.2)]), "core.section.a")

    assert entry.provenance is not None
    assert "area" in entry.provenance


def test_the_worst_section_mean_is_the_maximum_of_the_section_means() -> None:
    entries = normalize([section("a", 0.1, 0.2), section("b", 0.3, 0.5)])

    assert find(entries, "core.worst-section-mean").value == 0.3


def test_the_average_is_weighted_by_section_area() -> None:
    entries = normalize(
        [section("a", 0.1, 0.2, area=1e-4), section("b", 0.3, 0.5, area=3e-4)]
    )

    assert find(entries, "core.area-weighted-average").value == pytest.approx(0.25)


def test_the_point_maximum_is_the_maximum_over_sections() -> None:
    entries = normalize([section("a", 0.1, 0.2), section("b", 0.3, 0.5)])

    assert find(entries, "core.maximum").value == 0.5


def test_a_failed_section_is_named_and_the_aggregates_say_so() -> None:
    entries = normalize([section("a", 0.1, 0.2), section("b", None, None)])

    failed = find(entries, "core.section.b")
    assert failed.availability is ResultAvailability.UNAVAILABLE
    assert failed.reason is not None and "b" in failed.reason

    aggregate = find(entries, "core.worst-section-mean")
    assert aggregate.availability is ResultAvailability.AVAILABLE
    assert aggregate.approximation is not None
    assert "b" in aggregate.approximation


def test_every_section_failing_makes_the_aggregate_unavailable() -> None:
    entries = normalize([section("a", None, None), section("b", None, None)])

    aggregate = find(entries, "core.worst-section-mean")
    assert aggregate.availability is ResultAvailability.UNAVAILABLE
    assert aggregate.reason is not None
    assert aggregate.reason.startswith("flux-density.")


def test_without_dc_bias_the_values_carry_the_peak_convention() -> None:
    entries = normalize([section("a", 0.1, 0.2)])

    entry = find(entries, "core.maximum")
    assert entry.current_convention is CurrentConvention.AC_PEAK
    assert entry.approximation is None


def test_with_dc_bias_the_values_are_combined_and_labelled() -> None:
    entries = normalize([section("a", 0.1, 0.2)], dc_biased=True)

    entry = find(entries, "core.maximum")
    assert entry.current_convention is CurrentConvention.COMBINED
    assert entry.approximation == DC_BIASED_FIELD_NOTE


def test_no_section_at_all_reports_not_exposed() -> None:
    aggregate = find(normalize([]), "core.worst-section-mean")

    assert aggregate.availability is ResultAvailability.UNAVAILABLE
    assert "not_exposed" in (aggregate.reason or "")


def test_the_three_aggregates_are_always_present() -> None:
    scopes = {entry.scope for entry in normalize([])}

    assert {
        "core.worst-section-mean",
        "core.area-weighted-average",
        "core.maximum",
    } <= scopes
