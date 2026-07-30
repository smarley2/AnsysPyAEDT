"""Per-backend `Show solver window` support (ADR 0007).

Background operation is always available. Visible operation is reported
unsupported with a reason so the UI can disable the choice and explain it
instead of silently running hidden.
"""

from __future__ import annotations

from dataclasses import dataclass

from inductor_designer.application.services.aedt_support import (
    SUPPORTED_AEDT_EDITION,
    SUPPORTED_AEDT_RELEASE,
    aedt_support_issues,
)
from inductor_designer.simulation.capabilities import CapabilitySnapshot
from inductor_designer.simulation.run_contracts import RunBackend


@dataclass(frozen=True, slots=True)
class VisibilitySupport:
    supported: bool
    reason: str | None

    def __post_init__(self) -> None:
        if self.supported and self.reason is not None:
            raise ValueError("supported visibility carries no reason")
        if not self.supported and not (self.reason or "").strip():
            raise ValueError("unsupported visibility requires a reason")


def visible_window_support(
    backend: RunBackend, capabilities: CapabilitySnapshot
) -> VisibilitySupport:
    """FEMM always shows its window on request; Maxwell needs a supported AEDT."""
    if backend is RunBackend.FEMM:
        return VisibilitySupport(supported=True, reason=None)
    issues = aedt_support_issues(
        SUPPORTED_AEDT_RELEASE,
        SUPPORTED_AEDT_EDITION,
        capabilities,
    )
    if issues:
        return VisibilitySupport(supported=False, reason="; ".join(issues))
    return VisibilitySupport(supported=True, reason=None)
