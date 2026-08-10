from __future__ import annotations

from pathlib import Path

import pytest

from inductor_designer.adapters.pyaedt.maxwell3d import PyaedtMaxwell3dExporter
from inductor_designer.application.ports.maxwell_exporter import (
    SOLVE_STAGE_NAMES,
    STAGE_NAMES,
    Maxwell3dExportRequest,
)
from inductor_designer.domain.aedt_target import AedtEdition, AedtRelease
from inductor_designer.simulation.run_control import (
    CancellationToken,
    StageEvent,
    StagePhase,
)
from tests.fakes.maxwell3d_app import FakeMaxwell3dApp, FakeMaxwell3dAppFactory
from tests.unit.simulation.test_plan_builder import build, make_definition

pytestmark = pytest.mark.usefixtures("fake_maxwell_boundary")


class RecordingSink:
    def __init__(self) -> None:
        self.events: list[StageEvent] = []

    def emit(self, event: StageEvent) -> None:
        self.events.append(event)


def make_request(tmp_path: Path, **overrides: object) -> Maxwell3dExportRequest:
    base: dict[str, object] = {
        "plan": build((make_definition(),)),
        "release": AedtRelease(2025, 2),
        "edition": AedtEdition.COMMERCIAL,
        "non_graphical": True,
        "output_directory": tmp_path / "out",
        "project_name": "Solve_case",
    }
    base.update(overrides)
    return Maxwell3dExportRequest(**base)  # type: ignore[arg-type]


def export(
    tmp_path: Path, app: FakeMaxwell3dApp, **overrides: object
) -> tuple[FakeMaxwell3dApp, tuple[str, ...], object]:
    exporter = PyaedtMaxwell3dExporter(app_factory=FakeMaxwell3dAppFactory(app))
    result = exporter.export(make_request(tmp_path, **overrides))
    return app, tuple(stage.name for stage in result.stages), result


def test_solve_request_runs_the_analyze_stage(tmp_path: Path) -> None:
    app, names, result = export(tmp_path, FakeMaxwell3dApp(), solve=True)

    assert names == SOLVE_STAGE_NAMES
    assert result.succeeded(SOLVE_STAGE_NAMES) is True  # type: ignore[attr-defined]
    assert app.analyzed_setups == ("Setup1",)


def test_generate_only_request_never_analyzes(tmp_path: Path) -> None:
    app, names, result = export(tmp_path, FakeMaxwell3dApp())

    assert names == STAGE_NAMES
    assert app.analyzed_setups == ()
    assert result.succeeded(STAGE_NAMES) is True  # type: ignore[attr-defined]


def test_analyze_runs_after_the_project_is_saved(tmp_path: Path) -> None:
    _, names, _ = export(tmp_path, FakeMaxwell3dApp(), solve=True)

    assert names.index("save") < names.index("analyze")


def test_progress_sink_sees_started_then_succeeded_for_each_stage(
    tmp_path: Path,
) -> None:
    sink = RecordingSink()

    export(tmp_path, FakeMaxwell3dApp(), solve=True, progress=sink)

    started = [
        event.stage_name for event in sink.events if event.phase is StagePhase.STARTED
    ]
    succeeded = [
        event.stage_name for event in sink.events if event.phase is StagePhase.SUCCEEDED
    ]
    assert started == list(SOLVE_STAGE_NAMES)
    assert succeeded == list(SOLVE_STAGE_NAMES)
    assert not [
        event for event in sink.events if event.phase is StagePhase.FAILED
    ]


def test_cancellation_between_stages_stops_before_analyze(tmp_path: Path) -> None:
    token = CancellationToken()
    app = FakeMaxwell3dApp()
    app.on_call["create_setup"] = token.cancel

    _, names, result = export(tmp_path, app, solve=True, cancellation=token)

    assert "analyze" not in names
    assert names[-1] == "cancelled"
    assert "save" in names, "an interrupted run still preserves what it reached"
    assert app.analyzed_setups == ()
    assert result.succeeded(SOLVE_STAGE_NAMES) is False  # type: ignore[attr-defined]


def test_cancellation_emits_a_cancelled_event(tmp_path: Path) -> None:
    token = CancellationToken()
    app = FakeMaxwell3dApp()
    app.on_call["create_setup"] = token.cancel
    sink = RecordingSink()

    export(tmp_path, app, solve=True, cancellation=token, progress=sink)

    cancelled = [
        event for event in sink.events if event.phase is StagePhase.CANCELLED
    ]
    assert len(cancelled) == 1
    assert cancelled[0].stage_name == "matrix"


def test_the_solve_is_started_without_blocking_the_process(tmp_path: Path) -> None:
    app, _, _ = export(tmp_path, FakeMaxwell3dApp(), solve=True)

    assert app.analyze_blocking == [False]


def test_cancellation_during_analyze_stops_the_solver(tmp_path: Path) -> None:
    token = CancellationToken()
    app = FakeMaxwell3dApp()
    app.running_polls = [1] * 5
    app.on_poll = token.cancel

    _, names, result = export(tmp_path, app, solve=True, cancellation=token)

    assert app.stopped == [True]
    assert names[-1] == "cancelled"
    assert "results" not in names, "an interrupted solve has nothing to read"
    assert result.succeeded(SOLVE_STAGE_NAMES) is False  # type: ignore[attr-defined]


def test_failed_analyze_is_recorded_as_a_failed_stage(tmp_path: Path) -> None:
    app = FakeMaxwell3dApp()
    app.fail_analyze = True

    _, names, result = export(tmp_path, app, solve=True)

    assert names[-1] == "analyze"
    assert result.stages[-1].succeeded is False  # type: ignore[attr-defined]
    assert result.succeeded(SOLVE_STAGE_NAMES) is False  # type: ignore[attr-defined]


def test_an_uncancelled_token_changes_nothing(tmp_path: Path) -> None:
    _, names, _ = export(
        tmp_path, FakeMaxwell3dApp(), solve=True, cancellation=CancellationToken()
    )

    assert names == SOLVE_STAGE_NAMES
