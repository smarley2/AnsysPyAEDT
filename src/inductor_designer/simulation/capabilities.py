from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True, order=True, slots=True)
class AedtRelease:
    year: int
    release: int

    @classmethod
    def parse(cls, value: str) -> AedtRelease:
        parts = value.split(".")
        if len(parts) != 2 or not all(part.isdigit() for part in parts):
            raise ValueError(f"Invalid AEDT release: {value}")
        parsed = cls(int(parts[0]), int(parts[1]))
        if parsed.year < 2022 or parsed.release not in (1, 2):
            raise ValueError(f"Invalid AEDT release: {value}")
        return parsed

    def __str__(self) -> str:
        return f"{self.year}.{self.release}"


class AedtEdition(str, Enum):
    COMMERCIAL = "commercial"
    STUDENT = "student"


class ModelDimension(str, Enum):
    TWO_D = "2d"
    THREE_D = "3d"


class DcBiasStrategy(str, Enum):
    NATIVE_INCLUDE_DC_FIELDS = "native-include-dc-fields"
    MAGNETOSTATIC_INCREMENTAL_FALLBACK = "magnetostatic-incremental-fallback"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class CapabilitySnapshot:
    release: AedtRelease
    edition: AedtEdition
    include_dc_fields_3d: bool | None
    discovered_limits: tuple[str, ...]
    evidence_source: str

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
        DcBiasStrategy.MAGNETOSTATIC_INCREMENTAL_FALLBACK,
        True,
        "Use the documented Magnetostatic operating-point and "
        "incremental-linearization approximation.",
    )
