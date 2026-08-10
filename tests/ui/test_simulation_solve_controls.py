from __future__ import annotations

import threading

import pytest

pytest.importorskip("PySide6")

from PySide6.QtGui import QGuiApplication  # noqa: E402

from inductor_designer.simulation.run_contracts import RunMode  # noqa: E402
from inductor_designer.simulation.run_control import (  # noqa: E402
    StageEvent,
    StagePhase,
)
from inductor_designer.ui.generation_controller import GenerationController  # noqa: E402
from inductor_designer.ui.generation_lines import (  # noqa: E402
    GenerationResult,
    UiRunRequest,
)
from inductor_designer.ui.simulation_controller import SimulationController  # noqa: E402
from tests.ui.conftest import wait_until_idle  # noqa: E402
from tests.unit.application.test_maxwell_export import CAPABILITIES  # noqa: E402
from tests.unit.domain.test_project import make_project  # noqa: E402

pytestmark = pytest.mark.ui


class RecordingRunner:
    """Stands in for the real run service; records the request it was given."""

    def __init__(self) -> None:
        self.requests: list[UiRunRequest] = []
        self.block_until_cancelled = False

    def __call__(self, request: UiRunRequest) -> GenerationResult:
        self.requests.append(request)
        request.progress.emit(
            StageEvent(stage_name="launch", phase=StagePhase.STARTED, message=None)
        )
        if self.block_until_cancelled:
            for _ in range(500):
                if request.cancellation.cancelled:
                    break
                threading.Event().wait(0.01)
            return GenerationResult(("Run cancelled before stage 'mesh'.",))
        request.progress.emit(
            StageEvent(stage_name="analyze", phase=StagePhase.SUCCEEDED, message="ok")
        )
        return GenerationResult(("done",))


def build(session_dirty: bool = False) -> tuple[
    QGuiApplication, SimulationController, GenerationController, RecordingRunner
]:
    from inductor_designer.ui.project_session import ProjectSession

    app = QGuiApplication.instance() or QGuiApplication([])
    runner = RecordingRunner()
    generation = GenerationController(runner)
    from pathlib import Path

    # A saved, clean project passes the run gate.
    session = ProjectSession(make_project(), document_path=Path("saved.inductor.json"))
    controller = SimulationController(session, generation, CAPABILITIES)
    return app, controller, generation, runner


def test_mode_defaults_to_generate_only() -> None:
    _, controller, _, _ = build()

    assert controller.mode == RunMode.GENERATE_ONLY.value
    assert RunMode.GENERATE_AND_SOLVE.value in controller.modeOptions


def test_mode_can_be_set_to_generate_and_solve() -> None:
    _, controller, _, _ = build()

    assert controller.setMode(RunMode.GENERATE_AND_SOLVE.value) is True
    assert controller.mode == RunMode.GENERATE_AND_SOLVE.value


def test_an_unknown_mode_is_refused() -> None:
    _, controller, _, _ = build()

    assert controller.setMode("solve-everything") is False
    assert controller.mode == RunMode.GENERATE_ONLY.value


def test_generate_passes_the_selected_mode_to_the_runner() -> None:
    app, controller, generation, runner = build()
    controller.setMode(RunMode.GENERATE_AND_SOLVE.value)

    controller.generate()
    wait_until_idle(app, generation)

    assert runner.requests[-1].solve is True


def test_generate_only_mode_asks_for_no_solve() -> None:
    app, controller, generation, runner = build()

    controller.generate()
    wait_until_idle(app, generation)

    assert runner.requests[-1].solve is False


def test_stage_events_stream_into_the_lines_while_the_run_works() -> None:
    """Progress is visible during the run, not only in the final summary."""
    app, controller, generation, runner = build()
    controller.setMode(RunMode.GENERATE_AND_SOLVE.value)
    runner.block_until_cancelled = True

    controller.generate()
    streamed = False
    for _ in range(500):
        app.processEvents()
        if any(line.startswith("launch") for line in generation.lines):
            streamed = True
            break
        threading.Event().wait(0.01)
    controller.cancel()
    wait_until_idle(app, generation)

    assert streamed is True


def test_cancel_marks_the_token_and_reports_the_cancellation() -> None:
    app, controller, generation, runner = build()
    controller.setMode(RunMode.GENERATE_AND_SOLVE.value)
    runner.block_until_cancelled = True

    controller.generate()
    for _ in range(500):
        if generation.busy and runner.requests:
            break
        app.processEvents()
        threading.Event().wait(0.01)
    assert controller.cancel() is True
    wait_until_idle(app, generation)

    assert runner.requests[-1].cancellation.cancelled is True
    assert any("cancel" in line.casefold() for line in generation.lines)


def test_cancel_is_refused_when_no_run_is_in_flight() -> None:
    _, controller, _, _ = build()

    assert controller.cancel() is False
