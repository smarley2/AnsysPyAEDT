from __future__ import annotations

from inductor_designer.application.services.simulation_summary import simulation_summary
from tests.unit.domain.test_project import make_project


def test_summary_identifies_backend_independent_project() -> None:
    lines = simulation_summary(make_project())
    assert lines[0] == "Project: backend-independent"
    assert lines[-1] == "Run backend and mode are selected at generation time."


def test_summary_reports_shared_operating_point() -> None:
    lines = simulation_summary(make_project())
    assert lines[1] == (
        "Operating point: 100000 Hz; winding temperature 20 °C; "
        "core temperature 25 °C."
    )
