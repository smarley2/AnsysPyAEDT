from __future__ import annotations

import cmath
import math

from inductor_designer.application.ports.femm_solver import (
    FemmSolveRequest,
    FemmSolveResult,
    FemmWindingResult,
)


def _current_components(current_peak_a: float, phase_deg: float) -> tuple[float, float]:
    phasor = cmath.rect(current_peak_a, math.radians(phase_deg))
    return phasor.real, phasor.imag


class RecordingFemmSolver:
    """Port fake: records requests, never invokes FEMM."""

    def __init__(self) -> None:
        self.requests: list[FemmSolveRequest] = []

    def solve(self, request: FemmSolveRequest) -> FemmSolveResult:
        self.requests.append(request)
        fem_path = request.output_directory / f"{request.project_name}.fem"

        if request.analyze:
            results = {
                circuit.name: FemmWindingResult(
                    resistance_ohm=0.1,
                    inductance_h=1e-4,
                    current_a=_current_components(
                        circuit.current_peak_a,
                        circuit.phase_deg,
                    ),
                    voltage_v=(0.2, 0.126),
                    flux_linkage_wb=(1e-4, 0.0),
                )
                for circuit in request.problem.circuits
            }
        else:
            results = None

        return FemmSolveResult(
            fem_path=fem_path,
            analyzed=request.analyze,
            results=results,
            messages=("recorded peak-current phasors",),
            adapter_version="recording-fake",
            solver_version=None,
        )
