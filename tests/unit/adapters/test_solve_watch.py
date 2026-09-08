"""The solve watch keeps the process responsive while Maxwell solves.

A blocking `analyze_setup` call parks the whole Python process inside the AEDT
plugin for the length of the solve, which freezes the Qt user interface even
though the run owns a worker thread. These tests pin the non-blocking start and
the poll loop that replaces it.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

import pytest

from inductor_designer.adapters.pyaedt import solve_watch
from inductor_designer.adapters.pyaedt.solve_watch import analyze_watched
from inductor_designer.simulation.run_control import CancellationToken, RunCancelled


@pytest.fixture(autouse=True)
def _no_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(solve_watch, "_POLL_SECONDS", 0.0)


class FakeSolveApp:
    """Records how the solve was started and scripts what the desktop reports."""

    def __init__(self, running: Sequence[float] = ()) -> None:
        self.analyzed: list[str] = []
        self.blocking: list[Any] = []
        self.stopped: list[bool] = []
        self.polls = 0
        self.analyze_result = True
        self.on_poll: Callable[[], None] | None = None
        self.status = solve_watch.NORMAL_COMPLETION
        self.status_asked: list[str] = []
        self._running = list(running)

    def analyze_setup(self, name: str, *, blocking: bool = True) -> bool:
        self.analyzed.append(name)
        self.blocking.append(blocking)
        return self.analyze_result

    @property
    def are_there_simulations_running(self) -> float:
        self.polls += 1
        if self.on_poll is not None:
            self.on_poll()
        return self._running.pop(0) if self._running else 0.0

    def stop_simulations(self, clean_stop: bool = True) -> str:
        self.stopped.append(clean_stop)
        return "stopped"

    def solve_status(self, name: str) -> str:
        self.status_asked.append(name)
        return self.status


def test_the_solve_is_started_without_blocking_the_caller() -> None:
    app = FakeSolveApp()

    analyze_watched(app, "Setup1")

    assert app.analyzed == ["Setup1"]
    assert app.blocking == [False], "a blocking start is what freezes the UI"


def test_the_watch_waits_while_the_desktop_reports_a_running_simulation() -> None:
    app = FakeSolveApp(running=[1, 1, 1])

    analyze_watched(app, "Setup1")

    assert app.polls > 3, "the watch returned before the solver went idle"


def test_a_desktop_that_never_reports_a_simulation_still_finishes() -> None:
    """The solver needs a moment to register, but an idle desktop must end."""
    app = FakeSolveApp()

    analyze_watched(app, "Setup1")

    assert app.polls == solve_watch._IDLE_POLLS_TO_FINISH


def test_a_refused_start_fails_the_stage_without_waiting() -> None:
    app = FakeSolveApp()
    app.analyze_result = False

    with pytest.raises(RuntimeError):
        analyze_watched(app, "Setup1")

    assert app.polls == 0


def test_cancelling_stops_the_running_solver() -> None:
    token = CancellationToken()
    app = FakeSolveApp(running=[1] * 10)
    polls = 0

    def cancel_after_two_polls() -> None:
        nonlocal polls
        polls += 1
        if polls == 2:
            token.cancel()

    app.on_poll = cancel_after_two_polls

    with pytest.raises(RunCancelled):
        analyze_watched(app, "Setup1", cancellation=token)

    assert app.stopped == [True]


def test_an_already_cancelled_run_never_waits_for_the_solver() -> None:
    token = CancellationToken()
    token.cancel()
    app = FakeSolveApp(running=[1] * 10)

    with pytest.raises(RunCancelled):
        analyze_watched(app, "Setup1", cancellation=token)

    assert app.stopped == [True]
    assert app.polls == 0


def test_a_solve_that_died_mid_way_is_not_reported_as_solved() -> None:
    """"No solver running" is not "solved".

    Live on 2026-08-18 a Maxwell 3D run lost its eddy-current child process
    after the first adaptive pass. The desktop went idle, the poll loop ended,
    and the run was recorded `succeeded` -- publishing the losses that one pass
    had produced while every matrix entry read NaN. AEDT's profile said
    `Engine Detected Error` throughout.
    """
    app = FakeSolveApp()
    app.status = "Engine Detected Error"

    with pytest.raises(RuntimeError) as error:
        analyze_watched(app, "Setup1")

    assert "Engine Detected Error" in str(error.value)
    assert "Setup1" in str(error.value)
    assert app.status_asked == ["Setup1"]


def test_a_completed_solve_passes_the_status_check() -> None:
    app = FakeSolveApp()

    analyze_watched(app, "Setup1")

    assert app.status_asked == ["Setup1"]


def test_a_desktop_that_states_no_status_is_not_treated_as_a_failure() -> None:
    """Absence of a verdict is not a verdict: the geometry-only path and older
    profiles expose none, and failing those would fail runs that are fine. An
    incomplete solve still cannot publish a wrong number, because its quantities
    come back unavailable with a reason."""
    app = FakeSolveApp()
    app.status = ""

    analyze_watched(app, "Setup1")
