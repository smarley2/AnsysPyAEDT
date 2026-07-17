from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from inductor_designer.simulation.femm_problem import FemmProblem


@dataclass(frozen=True, slots=True)
class FemmSolveRequest:
    problem: FemmProblem
    output_directory: Path
    project_name: str
    analyze: bool


@dataclass(frozen=True, slots=True)
class FemmWindingResult:
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


class FemmSolver(Protocol):
    def solve(self, request: FemmSolveRequest) -> FemmSolveResult: ...
