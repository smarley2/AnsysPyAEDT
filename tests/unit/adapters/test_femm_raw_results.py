from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from inductor_designer.adapters.femm.solver import PyfemmSolver
from inductor_designer.application.ports.femm_solver import FemmSolveResult
from tests.fakes.femm_module import FakeFemmModule, FakeFemmModuleFactory
from tests.unit.adapters.test_femm_solver import make_request


def solve(tmp_path: Path, **overrides: object) -> FemmSolveResult:
    request = replace(make_request(tmp_path), **overrides)  # type: ignore[arg-type]
    return PyfemmSolver(module_factory=FakeFemmModuleFactory(FakeFemmModule())).solve(
        request
    )


def test_an_analyzed_run_reports_per_winding_scalars(tmp_path: Path) -> None:
    result = solve(tmp_path, analyze=True)

    assert result.raw_results is not None
    winding = result.raw_results.windings[0]
    assert winding.resistance_ohm is not None
    assert winding.inductance_h is not None
    assert winding.impedance is not None


def test_femm_reports_no_matrix_no_core_loss_and_no_energy(tmp_path: Path) -> None:
    raw = solve(tmp_path, analyze=True).raw_results

    assert raw is not None
    assert raw.matrices == ()
    assert raw.core_loss_w is None
    assert raw.magnetic_energy_j is None
    assert raw.convergence is None


def test_copper_loss_is_the_cycle_mean_of_the_reported_circuits(
    tmp_path: Path,
) -> None:
    result = solve(tmp_path, analyze=True)

    assert result.results is not None and result.raw_results is not None
    expected = sum(
        0.5 * winding.resistance_ohm * abs(complex(*winding.current_a)) ** 2
        for winding in result.results.values()
    )
    assert result.raw_results.copper_loss_w == pytest.approx(expected)


def test_a_generate_only_run_reports_no_raw_results(tmp_path: Path) -> None:
    assert solve(tmp_path, analyze=False).raw_results is None
