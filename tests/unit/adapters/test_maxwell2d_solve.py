from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from inductor_designer.adapters.pyaedt.maxwell2d import PyaedtMaxwell2dExporter
from inductor_designer.application.ports.maxwell2d_exporter import (
    SOLVE_STAGE_NAMES_2D,
    STAGE_NAMES_2D,
    Maxwell2dExportRequest,
)
from inductor_designer.simulation.run_control import (
    CancellationToken,
    StageEvent,
    StagePhase,
)
from tests.contract.test_maxwell2d_exporter_contract import make_request
from tests.fakes.maxwell2d_app import FakeMaxwell2dApp, FakeMaxwell2dAppFactory

pytestmark = pytest.mark.usefixtures("fake_maxwell_boundary")


class RecordingSink:
    def __init__(self) -> None:
        self.events: list[StageEvent] = []

    def emit(self, event: StageEvent) -> None:
        self.events.append(event)


def export(
    tmp_path: Path, app: FakeMaxwell2dApp, **overrides: object
) -> tuple[tuple[str, ...], object]:
    request: Maxwell2dExportRequest = replace(make_request(tmp_path), **overrides)  # type: ignore[arg-type]
    result = PyaedtMaxwell2dExporter(app_factory=FakeMaxwell2dAppFactory(app)).export(
        request
    )
    return tuple(stage.name for stage in result.stages), result


def test_solve_request_runs_the_analyze_stage(tmp_path: Path) -> None:
    app = FakeMaxwell2dApp()

    names, result = export(tmp_path, app, solve=True)

    assert names == SOLVE_STAGE_NAMES_2D
    assert result.succeeded(SOLVE_STAGE_NAMES_2D) is True  # type: ignore[attr-defined]
    assert app.analyzed_setups == ("Setup1",)


def test_generate_only_request_never_analyzes(tmp_path: Path) -> None:
    app = FakeMaxwell2dApp()

    names, _ = export(tmp_path, app)

    assert names == STAGE_NAMES_2D
    assert app.analyzed_setups == ()


def test_analyze_runs_after_the_project_is_saved(tmp_path: Path) -> None:
    names, _ = export(tmp_path, FakeMaxwell2dApp(), solve=True)

    assert names.index("save") < names.index("analyze")


def test_progress_sink_sees_every_stage(tmp_path: Path) -> None:
    sink = RecordingSink()

    export(tmp_path, FakeMaxwell2dApp(), solve=True, progress=sink)

    started = [
        event.stage_name for event in sink.events if event.phase is StagePhase.STARTED
    ]
    assert started == list(SOLVE_STAGE_NAMES_2D)


def test_cancellation_between_stages_stops_before_analyze(tmp_path: Path) -> None:
    token = CancellationToken()
    app = FakeMaxwell2dApp()
    app.on_call["create_setup"] = token.cancel

    names, _ = export(tmp_path, app, solve=True, cancellation=token)

    assert "analyze" not in names
    assert names[-1] == "cancelled"
    assert "save" in names
    assert app.analyzed_setups == ()


def test_the_solve_is_started_without_blocking_the_process(tmp_path: Path) -> None:
    app = FakeMaxwell2dApp()

    export(tmp_path, app, solve=True)

    assert app.analyze_blocking == [False]


def test_cancellation_during_analyze_stops_the_solver(tmp_path: Path) -> None:
    token = CancellationToken()
    app = FakeMaxwell2dApp()
    app.running_polls = [1] * 5
    app.on_poll = token.cancel

    names, result = export(tmp_path, app, solve=True, cancellation=token)

    assert app.stopped == [True]
    assert names[-1] == "cancelled"
    assert "results" not in names
    assert result.succeeded(SOLVE_STAGE_NAMES_2D) is False  # type: ignore[attr-defined]


def test_failed_analyze_is_recorded_as_a_failed_stage(tmp_path: Path) -> None:
    app = FakeMaxwell2dApp()
    app.fail_analyze = True

    names, result = export(tmp_path, app, solve=True)

    assert names[-1] == "analyze"
    assert result.stages[-1].succeeded is False  # type: ignore[attr-defined]
    assert result.succeeded(SOLVE_STAGE_NAMES_2D) is False  # type: ignore[attr-defined]
