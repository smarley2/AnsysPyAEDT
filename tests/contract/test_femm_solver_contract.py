from __future__ import annotations

from pathlib import Path

from inductor_designer.application.ports.femm_solver import FemmSolveRequest
from inductor_designer.simulation.femm_problem import femm_problem_from_plan
from tests.fakes.femm_solver import RecordingFemmSolver
from tests.unit.simulation.test_plan_builder import make_definition
from tests.unit.simulation.test_plan_builder2d import build2d


def make_problem(tmp_path: Path) -> tuple[FemmSolveRequest, RecordingFemmSolver]:
    plan = build2d((make_definition(),))  # type: ignore[arg-type]
    problem = femm_problem_from_plan(plan)
    solver = RecordingFemmSolver()
    request = FemmSolveRequest(
        problem=problem,
        output_directory=tmp_path,
        project_name="test_inductor",
        analyze=True,
    )
    return request, solver


def test_fake_records_request_with_analyze_true(tmp_path: Path) -> None:
    request, solver = make_problem(tmp_path)
    result = solver.solve(request)

    assert solver.requests == [request]
    assert result.fem_path == tmp_path / "test_inductor.fem"
    assert result.analyzed is True
    assert result.messages == ("recorded",)


def test_fake_returns_one_result_per_circuit_when_analyzed(tmp_path: Path) -> None:
    request, solver = make_problem(tmp_path)
    result = solver.solve(request)

    assert result.results is not None
    circuit_names = {circuit.name for circuit in request.problem.circuits}
    assert set(result.results.keys()) == circuit_names
    assert len(result.results) == 1

    for circuit_name, winding_result in result.results.items():
        assert winding_result.resistance_ohm == 0.1
        assert winding_result.inductance_h == 1e-4
        assert winding_result.voltage_v == (0.2, 0.126)
        assert winding_result.flux_linkage_wb == (1e-4, 0.0)
        # current_a should match circuit peak current
        circuit = next(c for c in request.problem.circuits if c.name == circuit_name)
        assert winding_result.current_a == (circuit.current_peak_a, 0.0)


def test_fake_returns_none_results_when_not_analyzed(tmp_path: Path) -> None:
    request, solver = make_problem(tmp_path)
    request_no_analyze = FemmSolveRequest(
        problem=request.problem,
        output_directory=tmp_path,
        project_name="test_inductor",
        analyze=False,
    )
    result = solver.solve(request_no_analyze)

    assert result.analyzed is False
    assert result.results is None
    assert result.fem_path == tmp_path / "test_inductor.fem"
    assert result.messages == ("recorded",)


def test_fake_fem_path_is_under_output_directory(tmp_path: Path) -> None:
    request, solver = make_problem(tmp_path)
    result = solver.solve(request)

    assert result.fem_path.parent == tmp_path
    assert result.fem_path.name == "test_inductor.fem"
