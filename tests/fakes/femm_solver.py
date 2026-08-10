from __future__ import annotations

import cmath
import math

from inductor_designer.application.ports.femm_solver import (
    FemmSolveRequest,
    FemmSolveResult,
    FemmWindingResult,
)
from inductor_designer.simulation.run_control import (
    StagePhase,
    emit_stage_event,
    is_cancelled,
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
        messages = ["recorded peak-current phasors"]
        emit_stage_event(
            request.progress, "generate", StagePhase.SUCCEEDED, messages[-1]
        )

        analyzed = request.analyze and not is_cancelled(request.cancellation)
        if request.analyze and not analyzed:
            messages.append("Run cancelled before the FEMM analysis.")
            emit_stage_event(
                request.progress, "analyze", StagePhase.CANCELLED, messages[-1]
            )

        if analyzed:
            emit_stage_event(request.progress, "analyze", StagePhase.STARTED, None)
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
            messages.append(f"Analyzed; {len(results)} circuit(s) extracted.")
            emit_stage_event(
                request.progress, "analyze", StagePhase.SUCCEEDED, messages[-1]
            )
        else:
            results = None

        return FemmSolveResult(
            fem_path=fem_path,
            analyzed=analyzed,
            results=results,
            messages=tuple(messages),
            adapter_version="recording-fake",
            solver_version=None,
        )
