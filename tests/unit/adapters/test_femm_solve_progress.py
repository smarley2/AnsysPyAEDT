from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from inductor_designer.adapters.femm.solver import PyfemmSolver
from inductor_designer.application.ports.femm_solver import (
    FemmSolveRequest,
    FemmSolveResult,
)
from inductor_designer.simulation.run_control import (
    CancellationToken,
    StageEvent,
    StagePhase,
)
from tests.fakes.femm_module import FakeFemmModule, FakeFemmModuleFactory
from tests.unit.adapters.test_femm_solver import make_request


class RecordingSink:
    def __init__(self) -> None:
        self.events: list[StageEvent] = []

    def emit(self, event: StageEvent) -> None:
        self.events.append(event)


def solve(
    tmp_path: Path, module: FakeFemmModule, **overrides: object
) -> FemmSolveResult:
    request: FemmSolveRequest = replace(make_request(tmp_path), **overrides)  # type: ignore[arg-type]
    return PyfemmSolver(module_factory=FakeFemmModuleFactory(module)).solve(request)


def analyze_calls(module: FakeFemmModule) -> int:
    return sum(1 for name, _ in module.calls if name == "mi_analyze")


def test_analyze_request_solves_and_extracts_raw_circuit_quantities(
    tmp_path: Path,
) -> None:
    module = FakeFemmModule()

    result = solve(tmp_path, module, analyze=True)

    assert analyze_calls(module) == 1
    assert result.analyzed is True
    assert result.results is not None


def test_generate_only_request_does_not_analyze(tmp_path: Path) -> None:
    module = FakeFemmModule()

    result = solve(tmp_path, module, analyze=False)

    assert analyze_calls(module) == 0
    assert result.analyzed is False
    assert result.results is None


def test_progress_sink_sees_generate_and_analyze(tmp_path: Path) -> None:
    sink = RecordingSink()

    solve(tmp_path, FakeFemmModule(), analyze=True, progress=sink)

    started = [
        event.stage_name for event in sink.events if event.phase is StagePhase.STARTED
    ]
    succeeded = [
        event.stage_name for event in sink.events if event.phase is StagePhase.SUCCEEDED
    ]
    assert started == ["generate", "analyze"]
    assert succeeded == ["generate", "analyze"]


def test_generate_only_emits_only_the_generate_stage(tmp_path: Path) -> None:
    sink = RecordingSink()

    solve(tmp_path, FakeFemmModule(), analyze=False, progress=sink)

    assert [event.stage_name for event in sink.events] == ["generate", "generate"]


def test_cancellation_before_analyze_skips_the_solve(tmp_path: Path) -> None:
    token = CancellationToken()
    token.cancel()
    module = FakeFemmModule()
    sink = RecordingSink()

    result = solve(
        tmp_path, module, analyze=True, cancellation=token, progress=sink
    )

    assert analyze_calls(module) == 0
    assert result.analyzed is False
    assert result.results is None
    assert any("cancelled" in message.casefold() for message in result.messages)
    assert any(event.phase is StagePhase.CANCELLED for event in sink.events)


def test_cancellation_still_leaves_the_generated_model_on_disk(
    tmp_path: Path,
) -> None:
    token = CancellationToken()
    token.cancel()

    result = solve(tmp_path, FakeFemmModule(), analyze=True, cancellation=token)

    assert result.fem_path.name == "test_inductor.fem"
    assert any("Saved" in message for message in result.messages)
