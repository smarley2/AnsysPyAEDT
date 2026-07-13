import pytest

from inductor_designer.simulation.capabilities import (
    AedtEdition,
    AedtRelease,
    CapabilitySnapshot,
    DcBiasStrategy,
    ModelDimension,
    select_dc_bias_strategy,
)


def snapshot(release: str, include_dc_fields: bool) -> CapabilitySnapshot:
    return CapabilitySnapshot(
        release=AedtRelease.parse(release),
        edition=AedtEdition.COMMERCIAL,
        include_dc_fields_3d=include_dc_fields,
        discovered_limits=(),
        evidence_source="controlled-spike",
    )


def test_2025_r1_3d_uses_native_dc_fields_when_observed() -> None:
    decision = select_dc_bias_strategy(snapshot("2025.1", True), ModelDimension.THREE_D)
    assert decision.strategy is DcBiasStrategy.NATIVE_INCLUDE_DC_FIELDS
    assert decision.approximate is False


def test_2024_r2_3d_uses_documented_incremental_fallback() -> None:
    decision = select_dc_bias_strategy(snapshot("2024.2", False), ModelDimension.THREE_D)
    assert decision.strategy is DcBiasStrategy.MAGNETOSTATIC_INCREMENTAL_FALLBACK
    assert decision.approximate is True


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
    )

    decision = select_dc_bias_strategy(capabilities, ModelDimension.THREE_D)

    assert decision.strategy is DcBiasStrategy.BLOCKED
    assert "not been reviewed" in decision.reason


def test_native_flag_before_2025_r1_is_rejected_as_inconsistent_evidence() -> None:
    with pytest.raises(ValueError, match="Include DC Fields cannot be recorded before 2025 R1"):
        snapshot("2024.2", True)
