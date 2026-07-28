from __future__ import annotations

from inductor_designer.domain.project import InductorProject


def simulation_summary(project: InductorProject) -> tuple[str, ...]:
    """Describe shared Project inputs without choosing a run backend."""
    operating_point = project.operating_point
    return (
        "Project: backend-independent",
        (
            f"Operating point: {operating_point.frequency_hz:g} Hz; "
            f"winding temperature {operating_point.winding_temperature_c:g} °C; "
            f"core temperature {operating_point.core_temperature_c:g} °C."
        ),
        "Run backend and mode are selected at generation time.",
    )
