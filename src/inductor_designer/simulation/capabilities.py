from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from inductor_designer.domain.aedt_target import AedtEdition, AedtRelease, ModelDimension

__all__ = [
    "AedtEdition",
    "AedtRelease",
    "CapabilityReviewStatus",
    "CapabilitySnapshot",
    "DcBiasDecision",
    "DcBiasStrategy",
    "ModelDimension",
    "select_dc_bias_strategy",
]


class DcBiasStrategy(str, Enum):
    NATIVE_INCLUDE_DC_FIELDS = "native-include-dc-fields"
    BLOCKED = "blocked"


class CapabilityReviewStatus(str, Enum):
    UNREVIEWED = "unreviewed"
    REVIEWED = "reviewed"


@dataclass(frozen=True, slots=True)
class CapabilitySnapshot:
    release: AedtRelease
    edition: AedtEdition
    include_dc_fields_3d: bool | None
    discovered_limits: tuple[str, ...]
    evidence_source: str
    review_status: CapabilityReviewStatus

    def __post_init__(self) -> None:
        if self.include_dc_fields_3d and self.release < AedtRelease(2025, 1):
            raise ValueError("Include DC Fields cannot be recorded before 2025 R1")
        if not self.evidence_source.strip():
            raise ValueError("Capability evidence_source cannot be empty")


@dataclass(frozen=True, slots=True)
class DcBiasDecision:
    strategy: DcBiasStrategy
    approximate: bool
    reason: str


def select_dc_bias_strategy(
    capabilities: CapabilitySnapshot,
    dimension: ModelDimension,
) -> DcBiasDecision:
    if dimension is ModelDimension.TWO_D:
        return DcBiasDecision(
            DcBiasStrategy.BLOCKED,
            False,
            "Maxwell 2D DC-bias generation is blocked until a validated policy is available.",
        )
    if capabilities.review_status is CapabilityReviewStatus.UNREVIEWED:
        return DcBiasDecision(
            DcBiasStrategy.BLOCKED,
            False,
            "The 3D capability evidence has not been reviewed for this environment.",
        )
    if capabilities.include_dc_fields_3d:
        return DcBiasDecision(
            DcBiasStrategy.NATIVE_INCLUDE_DC_FIELDS,
            False,
            "The controlled capability record confirms native 3D Include DC Fields.",
        )
    if capabilities.include_dc_fields_3d is None:
        return DcBiasDecision(
            DcBiasStrategy.BLOCKED,
            False,
            "The 3D Include DC Fields capability has not been reviewed for this environment.",
        )
    return DcBiasDecision(
        DcBiasStrategy.BLOCKED,
        False,
        "Native 3D DC bias is unavailable in this reviewed environment; "
        "no fallback is supported.",
    )
