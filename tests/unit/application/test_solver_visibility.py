from __future__ import annotations

import pytest

from inductor_designer.application.services.solver_visibility import (
    VisibilitySupport,
    visible_window_support,
)
from inductor_designer.domain.aedt_target import AedtEdition, AedtRelease
from inductor_designer.simulation.capabilities import (
    CapabilityReviewStatus,
    CapabilitySnapshot,
)
from inductor_designer.simulation.run_contracts import RunBackend

SUPPORTED = CapabilitySnapshot(
    release=AedtRelease(2025, 2),
    edition=AedtEdition.COMMERCIAL,
    include_dc_fields_3d=True,
    discovered_limits=(),
    evidence_source="M7b visibility test",
    review_status=CapabilityReviewStatus.REVIEWED,
)
UNSUPPORTED = CapabilitySnapshot(
    release=AedtRelease(2024, 2),
    edition=AedtEdition.COMMERCIAL,
    include_dc_fields_3d=None,
    discovered_limits=(),
    evidence_source="M7b visibility test",
    review_status=CapabilityReviewStatus.REVIEWED,
)


@pytest.mark.parametrize(
    "backend",
    [RunBackend.MAXWELL_3D, RunBackend.MAXWELL_2D, RunBackend.FEMM],
)
def test_every_backend_supports_a_visible_window_on_a_supported_install(
    backend: RunBackend,
) -> None:
    support = visible_window_support(backend, SUPPORTED)

    assert support == VisibilitySupport(supported=True, reason=None)


@pytest.mark.parametrize("backend", [RunBackend.MAXWELL_3D, RunBackend.MAXWELL_2D])
def test_maxwell_visibility_is_unsupported_when_the_install_does_not_match(
    backend: RunBackend,
) -> None:
    support = visible_window_support(backend, UNSUPPORTED)

    assert support.supported is False
    assert "2024.2" in str(support.reason)


def test_femm_visibility_does_not_depend_on_the_aedt_install() -> None:
    support = visible_window_support(RunBackend.FEMM, UNSUPPORTED)

    assert support.supported is True


def test_a_supported_result_carries_no_reason() -> None:
    with pytest.raises(ValueError, match="no reason"):
        VisibilitySupport(supported=True, reason="unused")


def test_an_unsupported_result_requires_a_reason() -> None:
    with pytest.raises(ValueError, match="reason"):
        VisibilitySupport(supported=False, reason="  ")
