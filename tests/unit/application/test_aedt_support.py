from inductor_designer.application.services.aedt_support import (
    SUPPORTED_AEDT_EDITION,
    SUPPORTED_AEDT_RELEASE,
    aedt_support_issues,
)
from inductor_designer.domain.aedt_target import AedtEdition, AedtRelease
from inductor_designer.simulation.capabilities import (
    CapabilityReviewStatus,
    CapabilitySnapshot,
)


def test_supported_target_is_exactly_2025_r2_commercial() -> None:
    assert AedtRelease(2025, 2) == SUPPORTED_AEDT_RELEASE
    assert SUPPORTED_AEDT_EDITION is AedtEdition.COMMERCIAL
    assert aedt_support_issues(
        SUPPORTED_AEDT_RELEASE,
        SUPPORTED_AEDT_EDITION,
    ) == ()


def test_unsupported_release_and_student_edition_are_rejected() -> None:
    assert aedt_support_issues(
        AedtRelease(2024, 2),
        AedtEdition.STUDENT,
    ) == (
        "Only AEDT 2025 R2 Commercial is supported; "
        "requested AEDT 2024.2 student.",
    )


def test_capability_evidence_must_match_the_project_target() -> None:
    capabilities = CapabilitySnapshot(
        release=AedtRelease(2026, 1),
        edition=AedtEdition.COMMERCIAL,
        include_dc_fields_3d=None,
        discovered_limits=(),
        evidence_source="test",
        review_status=CapabilityReviewStatus.UNREVIEWED,
    )
    assert aedt_support_issues(
        AedtRelease(2025, 2),
        AedtEdition.COMMERCIAL,
        capabilities,
    ) == (
        "Capability evidence for AEDT 2026.1 commercial does not match "
        "the requested AEDT 2025.2 commercial environment.",
    )
