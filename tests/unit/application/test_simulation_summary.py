from __future__ import annotations

from dataclasses import replace

from inductor_designer.application.services.simulation_summary import simulation_summary
from inductor_designer.domain.aedt_target import ModelDimension
from tests.unit.application.test_maxwell_export import NATIVE_SNAPSHOT, SNAPSHOT
from tests.unit.domain.test_project import make_project


def test_blocked_summary_carries_reason() -> None:
    lines = simulation_summary(make_project(), SNAPSHOT)
    assert lines[0] == "Target: AEDT 2025.2 commercial (3d)"
    assert lines[1] == "DC bias: blocked"
    assert "Include DC Fields" in lines[2]


def test_native_summary() -> None:
    lines = simulation_summary(make_project(), NATIVE_SNAPSHOT)
    assert lines[1] == "DC bias: native-include-dc-fields"


def test_two_d_summary_adds_approximation_line() -> None:
    project = replace(make_project(), dimension_mode=ModelDimension.TWO_D)
    lines = simulation_summary(project, SNAPSHOT)
    assert lines[-1].startswith("2D model is a documented approximate")
