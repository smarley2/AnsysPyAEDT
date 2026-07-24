import pytest

from inductor_designer.simulation.capabilities import (
    AedtEdition,
    AedtRelease,
    CapabilityReviewStatus,
    CapabilitySnapshot,
    DcBiasStrategy,
    ModelDimension,
    select_dc_bias_strategy,
)


def snapshot(
    release: str,
    include_dc_fields: bool,
    review_status: CapabilityReviewStatus = CapabilityReviewStatus.REVIEWED,
) -> CapabilitySnapshot:
    return CapabilitySnapshot(
        release=AedtRelease.parse(release),
        edition=AedtEdition.COMMERCIAL,
        include_dc_fields_3d=include_dc_fields,
        discovered_limits=(),
        evidence_source="controlled-spike",
        review_status=review_status,
    )


def test_2025_r1_3d_uses_native_dc_fields_when_observed() -> None:
    decision = select_dc_bias_strategy(snapshot("2025.1", True), ModelDimension.THREE_D)
    assert decision.strategy is DcBiasStrategy.NATIVE_INCLUDE_DC_FIELDS
    assert decision.approximate is False


def test_reviewed_environment_without_native_dc_is_blocked_without_fallback() -> None:
    decision = select_dc_bias_strategy(
        snapshot("2025.2", False),
        ModelDimension.THREE_D,
    )

    assert decision.strategy is DcBiasStrategy.BLOCKED
    assert decision.approximate is False
    assert "no fallback is supported" in decision.reason


def test_2d_dc_bias_is_blocked_until_a_supported_policy_exists() -> None:
    decision = select_dc_bias_strategy(snapshot("2026.1", True), ModelDimension.TWO_D)
    assert decision.strategy is DcBiasStrategy.BLOCKED
    assert "Maxwell 2D" in decision.reason


def test_unknown_3d_capability_is_blocked_instead_of_guessed() -> None:
    capabilities = CapabilitySnapshot(
        release=AedtRelease.parse("2026.1"),
        edition=AedtEdition.STUDENT,
        include_dc_fields_3d=None,
        discovered_limits=(),
        evidence_source="trivial-design-spike",
        review_status=CapabilityReviewStatus.REVIEWED,
    )

    decision = select_dc_bias_strategy(capabilities, ModelDimension.THREE_D)

    assert decision.strategy is DcBiasStrategy.BLOCKED
    assert "not been reviewed" in decision.reason


def test_native_flag_before_2025_r1_is_rejected_as_inconsistent_evidence() -> None:
    with pytest.raises(ValueError, match="Include DC Fields cannot be recorded before 2025 R1"):
        snapshot("2024.2", True)


@pytest.mark.parametrize(
    ("release", "include_dc_fields"),
    [("2025.1", True), ("2024.2", False)],
    ids=["native-flag", "non-native-flag"],
)
def test_unreviewed_boolean_evidence_cannot_select_a_3d_strategy(
    release: str,
    include_dc_fields: bool,
) -> None:
    capabilities = snapshot(
        release,
        include_dc_fields,
        CapabilityReviewStatus.UNREVIEWED,
    )

    decision = select_dc_bias_strategy(capabilities, ModelDimension.THREE_D)

    assert decision.strategy is DcBiasStrategy.BLOCKED
    assert "not been reviewed" in decision.reason


def test_later_release_without_native_capability_remains_blocked() -> None:
    decision = select_dc_bias_strategy(snapshot("2025.1", False), ModelDimension.THREE_D)

    assert decision.strategy is DcBiasStrategy.BLOCKED
    assert "no fallback is supported" in decision.reason


@pytest.mark.parametrize(
    "value",
    ["2024.1", "2023.2", "2100.1", "02024.2", "2024.02"],
)
def test_release_parser_rejects_values_outside_the_supported_20xx_range(
    value: str,
) -> None:
    with pytest.raises(ValueError, match="Invalid AEDT release"):
        AedtRelease.parse(value)


@pytest.mark.parametrize("year, release", [(2024, 1), (2023, 2), (2100, 1)])
def test_direct_release_construction_rejects_values_outside_supported_range(
    year: int,
    release: int,
) -> None:
    with pytest.raises(ValueError, match="Invalid AEDT release"):
        AedtRelease(year, release)


@pytest.mark.parametrize("value", ["2024.2", "2025.1", "2099.2"])
def test_release_parser_accepts_supported_20xx_boundaries(value: str) -> None:
    assert str(AedtRelease.parse(value)) == value
