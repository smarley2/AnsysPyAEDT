from __future__ import annotations

from pathlib import Path

import pytest

from inductor_designer.adapters.pyaedt.maxwell3d import PyaedtMaxwell3dExporter
from inductor_designer.application.ports.maxwell_exporter import (
    SOLVE_STAGE_NAMES,
    STAGE_NAMES,
    Maxwell3dExportRequest,
    Maxwell3dExportResult,
)
from inductor_designer.domain.aedt_target import AedtEdition, AedtRelease
from tests.fakes.maxwell3d_app import FakeMaxwell3dApp, FakeMaxwell3dAppFactory
from tests.unit.simulation.test_plan_builder import build, make_definition

pytestmark = pytest.mark.usefixtures("fake_maxwell_boundary")


def export(
    tmp_path: Path, app: FakeMaxwell3dApp, **overrides: object
) -> Maxwell3dExportResult:
    base: dict[str, object] = {
        "plan": build((make_definition(),)),
        "release": AedtRelease(2025, 2),
        "edition": AedtEdition.COMMERCIAL,
        "non_graphical": True,
        "output_directory": tmp_path / "out",
        "project_name": "Result_case",
        "solve": True,
    }
    base.update(overrides)
    return PyaedtMaxwell3dExporter(app_factory=FakeMaxwell3dAppFactory(app)).export(
        Maxwell3dExportRequest(**base)  # type: ignore[arg-type]
    )


def test_a_solved_run_attaches_raw_results(tmp_path: Path) -> None:
    result = export(tmp_path, FakeMaxwell3dApp())

    assert result.raw_results is not None
    assert result.raw_results.windings[0].winding_id == "w1"
    assert result.raw_results.copper_loss_w == pytest.approx(3.0)
    assert result.raw_results.core_loss_w == pytest.approx(1.25)
    # No magnetic energy: an AC Magnetic design exposes no energy report
    # quantity, so nothing is asked for and nothing can come back.
    assert result.raw_results.magnetic_energy_j is None
    assert result.raw_results.convergence is not None


def test_per_winding_scalars_come_from_the_matrix_diagonal(tmp_path: Path) -> None:
    raw = export(tmp_path, FakeMaxwell3dApp()).raw_results

    assert raw is not None
    winding = raw.windings[0]
    assert winding.resistance_ohm == pytest.approx(0.125)
    assert winding.inductance_h == pytest.approx(1e-4)
    assert winding.impedance is not None
    assert winding.impedance.real == pytest.approx(0.125)
    assert winding.impedance.imag > 0.0


def test_both_matrix_kinds_are_reported(tmp_path: Path) -> None:
    raw = export(tmp_path, FakeMaxwell3dApp()).raw_results

    assert raw is not None
    assert {matrix.kind for matrix in raw.matrices} == {"resistance", "inductance"}


def test_a_generate_only_run_attaches_no_results(tmp_path: Path) -> None:
    result = export(tmp_path, FakeMaxwell3dApp(), solve=False)

    assert result.raw_results is None
    assert tuple(stage.name for stage in result.stages) == STAGE_NAMES


def test_the_results_stage_appears_after_analyze(tmp_path: Path) -> None:
    result = export(tmp_path, FakeMaxwell3dApp())

    names = tuple(stage.name for stage in result.stages)
    assert names == SOLVE_STAGE_NAMES
    assert names.index("analyze") < names.index("results")


def test_an_extraction_failure_never_fails_the_solved_run(tmp_path: Path) -> None:
    app = FakeMaxwell3dApp()
    app.fail_solution_values = True

    result = export(tmp_path, app)

    stage = next(item for item in result.stages if item.name == "results")
    assert stage.succeeded is True, "the solve itself succeeded"
    assert result.succeeded(SOLVE_STAGE_NAMES) is True
    assert result.raw_results is not None
    assert result.raw_results.diagnostics, "the failure is recorded, not swallowed"
    assert result.raw_results.windings == ()


def test_a_cancelled_run_extracts_nothing(tmp_path: Path) -> None:
    from inductor_designer.simulation.run_control import CancellationToken

    token = CancellationToken()
    app = FakeMaxwell3dApp()
    app.on_call["create_setup"] = token.cancel

    result = export(tmp_path, app, cancellation=token)

    assert result.raw_results is None
    assert "results" not in [stage.name for stage in result.stages]
