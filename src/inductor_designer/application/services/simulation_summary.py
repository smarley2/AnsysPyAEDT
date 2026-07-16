from __future__ import annotations

from inductor_designer.domain.aedt_target import ModelDimension
from inductor_designer.domain.project import InductorProject
from inductor_designer.simulation.capabilities import (
    CapabilitySnapshot,
    select_dc_bias_strategy,
)


def simulation_summary(
    project: InductorProject, capabilities: CapabilitySnapshot
) -> tuple[str, ...]:
    """Human-readable simulation/compatibility lines for the Guided Studio UI."""
    decision = select_dc_bias_strategy(capabilities, project.dimension_mode)
    approximate = " (approximate)" if decision.approximate else ""
    lines = [
        f"Target: AEDT {project.target_release} {project.target_edition.value} "
        f"({project.dimension_mode.value})",
        f"DC bias: {decision.strategy.value}{approximate}",
        decision.reason,
    ]
    if project.dimension_mode is ModelDimension.TWO_D:
        lines.append(
            "2D model is a documented approximate XY cross-section equivalent."
        )
    return tuple(lines)
