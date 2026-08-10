from __future__ import annotations

from inductor_designer.application.services.result_normalization import (
    normalize_scalar_results,
)
from inductor_designer.domain.project import RequestedOutput
from inductor_designer.simulation.raw_results import RawFieldSection, RawScalarResults
from inductor_designer.simulation.run_contracts import (
    NormalizedResultSet,
    ResultAvailability,
    RunBackend,
)


def normalize(
    raw: RawScalarResults,
    backend: RunBackend,
    quantity: RequestedOutput,
    *,
    dc_biased: bool = False,
) -> NormalizedResultSet:
    return normalize_scalar_results(
        raw,
        run_id="r",
        backend=backend,
        requested_outputs=(quantity,),
        provenance="test provenance",
        dc_biased=dc_biased,
    )


def test_femm_says_why_it_reports_no_flux_density() -> None:
    result_set = normalize(
        RawScalarResults(), RunBackend.FEMM, RequestedOutput.FLUX_DENSITY
    )

    entry = result_set.quantities[0]
    assert entry.availability is ResultAvailability.UNAVAILABLE
    assert entry.reason is not None
    assert entry.reason.startswith("flux-density.not_exposed")
    assert "components" in entry.reason
    assert "cancel" in entry.reason


def test_femm_says_the_same_for_current_density() -> None:
    result_set = normalize(
        RawScalarResults(), RunBackend.FEMM, RequestedOutput.CURRENT_DENSITY
    )

    assert result_set.quantities[0].reason is not None
    assert result_set.quantities[0].reason.startswith("current-density.not_exposed")


def test_femm_never_emits_a_section_entry() -> None:
    result_set = normalize(
        RawScalarResults(), RunBackend.FEMM, RequestedOutput.FLUX_DENSITY
    )

    assert len(result_set.quantities) == 1


def test_maxwell_current_density_is_grouped_per_winding() -> None:
    raw = RawScalarResults(
        current_density_sections=(
            RawFieldSection(
                section_id="winding.w1.turn04.inner-bore",
                scope="winding.w1.section.winding.w1.turn04.inner-bore",
                area_m2=3e-6,
                mean=2.0e6,
                maximum=2.4e6,
            ),
            RawFieldSection(
                section_id="winding.w2.turn02.inner-bore",
                scope="winding.w2.section.winding.w2.turn02.inner-bore",
                area_m2=3e-6,
                mean=1.0e6,
                maximum=1.1e6,
            ),
        )
    )

    scopes = {
        entry.scope
        for entry in normalize(
            raw, RunBackend.MAXWELL_3D, RequestedOutput.CURRENT_DENSITY
        ).quantities
    }

    assert "winding.w1.worst-section-mean" in scopes
    assert "winding.w2.worst-section-mean" in scopes


def test_a_dc_biased_maxwell_run_labels_its_field_values() -> None:
    raw = RawScalarResults(
        flux_density_sections=(
            RawFieldSection(
                section_id="core.00.span-start",
                scope="core.section.core.00.span-start",
                area_m2=1e-4,
                mean=0.31,
                maximum=0.42,
            ),
        )
    )

    entry = next(
        item
        for item in normalize(
            raw, RunBackend.MAXWELL_3D, RequestedOutput.FLUX_DENSITY, dc_biased=True
        ).quantities
        if item.scope == "core.maximum"
    )

    assert entry.approximation is not None
    assert "DC-biased" in entry.approximation
