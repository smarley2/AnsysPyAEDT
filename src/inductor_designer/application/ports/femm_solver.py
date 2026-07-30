from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from inductor_designer.simulation.femm_problem import FemmProblem


@dataclass(frozen=True, slots=True)
class FemmSolveRequest:
    """FEMM request whose problem circuits carry AC peak magnitude and phase."""

    problem: FemmProblem
    output_directory: Path
    project_name: str
    analyze: bool
    show_window: bool = False


@dataclass(frozen=True, slots=True)
class FemmWindingResult:
    """Extracted complex circuit quantities stored as Cartesian ``(real, imag)``."""

    resistance_ohm: float
    inductance_h: float
    current_a: tuple[float, float]
    voltage_v: tuple[float, float]
    flux_linkage_wb: tuple[float, float]


@dataclass(frozen=True, slots=True)
class FemmSolveResult:
    fem_path: Path
    analyzed: bool
    results: Mapping[str, FemmWindingResult] | None
    messages: tuple[str, ...]
    adapter_version: str | None = None
    solver_version: str | None = None


class FemmSolver(Protocol):
    def solve(self, request: FemmSolveRequest) -> FemmSolveResult: ...
