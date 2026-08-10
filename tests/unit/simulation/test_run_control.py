from __future__ import annotations

import threading

import pytest

from inductor_designer.simulation.run_contracts import RunStatus
from inductor_designer.simulation.run_control import (
    CancellationToken,
    RunCancelled,
    StageEvent,
    StagePhase,
)


def test_token_starts_uncancelled_and_does_not_raise() -> None:
    token = CancellationToken()
    assert token.cancelled is False
    token.raise_if_cancelled()


def test_token_raises_after_cancel() -> None:
    token = CancellationToken()
    token.cancel()
    assert token.cancelled is True
    with pytest.raises(RunCancelled):
        token.raise_if_cancelled()


def test_raise_if_cancelled_names_the_stage_it_stopped_before() -> None:
    token = CancellationToken()
    token.cancel()
    with pytest.raises(RunCancelled) as cancelled:
        token.raise_if_cancelled("mesh")
    assert cancelled.value.stage_name == "mesh"
    assert "mesh" in str(cancelled.value)


def test_cancel_is_visible_across_threads() -> None:
    token = CancellationToken()
    seen: list[bool] = []
    ready = threading.Event()

    def watcher() -> None:
        ready.wait(timeout=5.0)
        seen.append(token.cancelled)

    thread = threading.Thread(target=watcher)
    thread.start()
    token.cancel()
    ready.set()
    thread.join(timeout=5.0)
    assert seen == [True]


def test_cancel_is_idempotent() -> None:
    token = CancellationToken()
    token.cancel()
    token.cancel()
    assert token.cancelled is True


def test_stage_event_carries_stage_and_phase() -> None:
    event = StageEvent(stage_name="mesh", phase=StagePhase.STARTED, message=None)
    assert event.stage_name == "mesh"
    assert event.phase is StagePhase.STARTED
    assert event.message is None


def test_run_status_has_running() -> None:
    assert RunStatus.RUNNING.value == "running"
