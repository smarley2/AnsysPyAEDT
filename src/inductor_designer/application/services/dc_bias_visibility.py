"""Whether the selected backend would silently ignore a project's DC bias.

Maxwell 2D and FEMM run AC-only (`DcBiasStrategy.AC_ONLY_DC_IGNORED`,
`simulation/capabilities.py`) whenever a project carries a nonzero DC winding
current. The UI must surface that before a run starts, not discover it after
(decision: Fabio Posser, 2026-08-07).
"""

from __future__ import annotations

from dataclasses import dataclass

from inductor_designer.simulation.capabilities import (
    CapabilitySnapshot,
    DcBiasStrategy,
    ModelDimension,
    select_dc_bias_strategy,
)
from inductor_designer.simulation.run_contracts import RunBackend


@dataclass(frozen=True, slots=True)
class DcBiasVisibility:
    ignored: bool
    notice: str

    def __post_init__(self) -> None:
        if self.ignored and not self.notice.strip():
            raise ValueError("an ignored DC bias requires a nonblank notice")
        if not self.ignored and self.notice:
            raise ValueError("no notice when DC bias is not ignored")


def dc_bias_visibility(
    backend: RunBackend,
    capabilities: CapabilitySnapshot,
    *,
    dc_requested: bool,
) -> DcBiasVisibility:
    """Whether generating with `backend` right now would ignore a requested DC bias."""
    if not dc_requested:
        return DcBiasVisibility(ignored=False, notice="")
    dimension = (
        ModelDimension.THREE_D if backend is RunBackend.MAXWELL_3D else ModelDimension.TWO_D
    )
    decision = select_dc_bias_strategy(capabilities, dimension)
    if decision.strategy is not DcBiasStrategy.AC_ONLY_DC_IGNORED:
        return DcBiasVisibility(ignored=False, notice="")
    return DcBiasVisibility(ignored=True, notice=decision.reason)
