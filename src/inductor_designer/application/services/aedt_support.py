from __future__ import annotations

from inductor_designer.domain.aedt_target import AedtEdition, AedtRelease
from inductor_designer.simulation.capabilities import CapabilitySnapshot

SUPPORTED_AEDT_RELEASE = AedtRelease(2025, 2)
SUPPORTED_AEDT_EDITION = AedtEdition.COMMERCIAL


def aedt_support_issues(
    release: AedtRelease,
    edition: AedtEdition,
    capabilities: CapabilitySnapshot | None = None,
) -> tuple[str, ...]:
    issues: list[str] = []
    if release != SUPPORTED_AEDT_RELEASE or edition is not SUPPORTED_AEDT_EDITION:
        issues.append(
            "Only AEDT 2025 R2 Commercial is supported; "
            f"requested AEDT {release} {edition.value}."
        )
    if capabilities is not None and (
        capabilities.release != release or capabilities.edition is not edition
    ):
        issues.append(
            f"Capability evidence for AEDT {capabilities.release} "
            f"{capabilities.edition.value} does not match the requested "
            f"AEDT {release} {edition.value} environment."
        )
    return tuple(issues)
