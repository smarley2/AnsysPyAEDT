from __future__ import annotations

import pytest

from inductor_designer.application.services.dc_bias_visibility import (
    DcBiasVisibility,
    dc_bias_visibility,
)
from inductor_designer.domain.aedt_target import AedtEdition, AedtRelease
from inductor_designer.simulation.capabilities import (
    CapabilityReviewStatus,
    CapabilitySnapshot,
)
from inductor_designer.simulation.run_contracts import RunBackend

CAPABILITIES = CapabilitySnapshot(
    release=AedtRelease(2025, 2),
    edition=AedtEdition.COMMERCIAL,
    include_dc_fields_3d=True,
    discovered_limits=(),
    evidence_source="ac-only-2d test",
    review_status=CapabilityReviewStatus.REVIEWED,
)


@pytest.mark.parametrize("backend", [RunBackend.MAXWELL_2D, RunBackend.FEMM])
def test_2d_and_femm_ignore_a_requested_dc_bias(backend: RunBackend) -> None:
    visibility = dc_bias_visibility(backend, CAPABILITIES, dc_requested=True)

    assert visibility.ignored is True
    assert "AC" in visibility.notice


@pytest.mark.parametrize("backend", [RunBackend.MAXWELL_2D, RunBackend.FEMM, RunBackend.MAXWELL_3D])
def test_no_dc_requested_means_nothing_is_ignored(backend: RunBackend) -> None:
    visibility = dc_bias_visibility(backend, CAPABILITIES, dc_requested=False)

    assert visibility == DcBiasVisibility(ignored=False, notice="")


def test_native_3d_dc_is_not_reported_as_ignored() -> None:
    visibility = dc_bias_visibility(RunBackend.MAXWELL_3D, CAPABILITIES, dc_requested=True)

    assert visibility.ignored is False


def test_an_ignored_result_requires_a_notice() -> None:
    with pytest.raises(ValueError, match="notice"):
        DcBiasVisibility(ignored=True, notice=" ")


def test_a_non_ignored_result_carries_no_notice() -> None:
    with pytest.raises(ValueError, match="notice"):
        DcBiasVisibility(ignored=False, notice="unused")
