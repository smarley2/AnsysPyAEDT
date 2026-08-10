# M8a Solve Execution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `Generate and Solve` actually run a solve on Maxwell 3D, Maxwell 2D and FEMM, with live stage progress, cooperative cancellation, a durable on-disk status, and truthful failed-stage diagnostics — without normalizing a single result value.

**Architecture:** The existing generation path already dispatches one planned run to one adapter and writes `run-manifest.json` into a project-local run directory. M8a extends that path in place: the stage sequences gain a solve stage, the adapters emit a progress event around every stage and check a cancellation token between stages, `start_project_run` writes a `running` manifest before dispatch and overwrites it at the end, and the Qt `GenerationController` streams the events and offers `Cancel`. Result extraction is deliberately absent: `RunManifest.results` stays `None` for the whole of M8a.

**Tech Stack:** Python 3.13, PySide6/QML, PyAEDT against AEDT 2025 R2 Commercial, pyFEMM against FEMM 4.2, pytest with `pytest-xdist`, Ruff, strict mypy.

## Global Constraints

- The only supported AEDT target is AEDT 2025 R2 Commercial.
- `domain`, `geometry`, `materials` and `simulation` import no PyAEDT, no Qt, no SQLite and no operating-system API; `tools/check_architecture.py` enforces this.
- Never change a physical assumption, schema, catalog value, unit, source reference or approximation silently.
- Add or update tests before implementing a feature or a fix.
- A partial artifact or an interrupted analysis is never reported as successful (roadmap realignment section 8).
- Every run leaves a truthful `run-manifest.json` in its own non-overwriting `runs/<run-id>-<backend>/` directory (ADR 0007).
- The project current is RMS; the solver excitation is peak (ADR 0006). M8a changes neither.
- Diagnostic codes are lowercase dotted `<quantity>.<reason>` strings.
- All code, comments, commits and UI copy in English.
- Full suite: `.venv/Scripts/python.exe -m pytest -n 8`. Live suites are behind the `aedt` and `femm` markers.

## Scope

In scope: solve execution, progress, cancellation, durable status, failed-stage diagnostics, a solve log written into the reserved `results/` directory, and the UI controls that drive all of it.

Out of scope, owned by later slices: every normalized result value, R/L/Z, losses, energy, convergence data, JSON/CSV export, the Review result display (M8b), and all field results including representative cross sections (M8c, specified in the [2026-08-10 Representative Cross Sections design](../specs/2026-08-10-representative-cross-sections-design.md)).

## File Structure

| File | Responsibility |
| --- | --- |
| `src/inductor_designer/simulation/run_control.py` (create) | Pure cancellation token, stage event, progress sink protocol, `RunCancelled` |
| `src/inductor_designer/simulation/run_contracts.py` (modify) | Add `RunStatus.RUNNING` |
| `src/inductor_designer/application/ports/maxwell_exporter.py` (modify) | Solve stage names; `solve`, `progress`, `cancellation` on the request |
| `src/inductor_designer/application/ports/maxwell2d_exporter.py` (modify) | Same, for 2D |
| `src/inductor_designer/application/ports/femm_solver.py` (modify) | `progress` and `cancellation` on the FEMM request |
| `src/inductor_designer/adapters/pyaedt/maxwell3d.py` (modify) | `analyze` stage, per-stage events, between-stage cancellation |
| `src/inductor_designer/adapters/pyaedt/maxwell2d.py` (modify) | Same, for 2D |
| `src/inductor_designer/adapters/femm/solver.py` (modify) | Analyze on request, events, cancellation before analyze |
| `src/inductor_designer/application/services/maxwell_export.py` (modify) | Accept `generate-and-solve`, pick stage names by mode, carry events through |
| `src/inductor_designer/application/services/project_run.py` (modify) | Durable `running` manifest, cancellation outcome, solve log artifact |
| `src/inductor_designer/application/services/solve_log.py` (create) | Render stage events into `results/solve-log.txt` |
| `src/inductor_designer/ui/generation_controller.py` (modify) | Stream events, expose `cancel()` |
| `src/inductor_designer/ui/simulation_controller.py` (modify) | Mode selector, cancel wiring, remove the M8 block note |
| `src/inductor_designer/ui/qml/SimulationStep.qml` (modify) | Mode control, progress list, Cancel button |

---

### Task 1: Run control primitives

**Files:**
- Create: `src/inductor_designer/simulation/run_control.py`
- Modify: `src/inductor_designer/simulation/run_contracts.py`
- Test: `tests/unit/simulation/test_run_control.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `CancellationToken` with `cancel() -> None`, `cancelled` property and `raise_if_cancelled() -> None`; `RunCancelled(RuntimeError)` with a `stage_name: str | None`; `StageEvent(stage_name: str, phase: StagePhase, message: str | None)`; `StagePhase` enum with `STARTED`, `SUCCEEDED`, `FAILED`, `CANCELLED`; `ProgressSink` protocol with `emit(event: StageEvent) -> None`; `RunStatus.RUNNING`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/simulation/test_run_control.py
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


def test_run_status_has_running() -> None:
    assert RunStatus.RUNNING.value == "running"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/simulation/test_run_control.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'inductor_designer.simulation.run_control'`

- [ ] **Step 3: Write the implementation**

```python
# src/inductor_designer/simulation/run_control.py
"""Cooperative cancellation and stage progress, free of Qt and solver imports.

A run is cancelled only between stages: a PyAEDT or pyFEMM call in flight is
never interrupted, because a half-executed solver call cannot be described
truthfully in a manifest.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class RunCancelled(RuntimeError):
    """Raised at a stage boundary after the user cancelled the run."""

    def __init__(self, stage_name: str | None = None) -> None:
        self.stage_name = stage_name
        super().__init__(
            "Run cancelled before stage "
            f"{stage_name!r}." if stage_name else "Run cancelled."
        )


class CancellationToken:
    """Thread-safe one-way flag; the UI thread cancels, the worker observes."""

    def __init__(self) -> None:
        self._event = threading.Event()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> None:
        self._event.set()

    def raise_if_cancelled(self, stage_name: str | None = None) -> None:
        if self._event.is_set():
            raise RunCancelled(stage_name)


class StagePhase(str, Enum):
    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class StageEvent:
    stage_name: str
    phase: StagePhase
    message: str | None


class ProgressSink(Protocol):
    def emit(self, event: StageEvent) -> None: ...
```

Add to `src/inductor_designer/simulation/run_contracts.py`, inside `RunStatus`, immediately after `PLANNED`:

```python
    RUNNING = "running"
```

- [ ] **Step 4: Run the tests**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/simulation/test_run_control.py tests/unit/simulation/test_run_contracts.py -q`
Expected: PASS

- [ ] **Step 5: Run the architecture check**

Run: `.venv/Scripts/python.exe -m tools.check_architecture`
Expected: clean exit, no output

- [ ] **Step 6: Commit**

```bash
git add src/inductor_designer/simulation/run_control.py src/inductor_designer/simulation/run_contracts.py tests/unit/simulation/test_run_control.py
git commit -m "feat(simulation): add cancellation token, stage events and running status"
```

---

### Task 2: Solve stage names and request fields on the exporter ports

**Files:**
- Modify: `src/inductor_designer/application/ports/maxwell_exporter.py:13-58`
- Modify: `src/inductor_designer/application/ports/maxwell2d_exporter.py`
- Modify: `src/inductor_designer/application/ports/femm_solver.py:11-20`
- Test: `tests/unit/application/test_exporter_ports.py`

**Interfaces:**
- Consumes: `CancellationToken`, `ProgressSink` from Task 1.
- Produces: `SOLVE_STAGE_NAMES = STAGE_NAMES + ("analyze",)` and `SOLVE_STAGE_NAMES_2D = STAGE_NAMES_2D + ("analyze",)`; `Maxwell3dExportRequest`, `Maxwell2dExportRequest` and `FemmSolveRequest` each gain `solve: bool = False`, `progress: ProgressSink | None = None`, `cancellation: CancellationToken | None = None`. `FemmSolveRequest.analyze` keeps its existing meaning and is set from `solve` by the caller.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/application/test_exporter_ports.py
from pathlib import Path

from inductor_designer.application.ports.maxwell2d_exporter import (
    SOLVE_STAGE_NAMES_2D,
    STAGE_NAMES_2D,
)
from inductor_designer.application.ports.maxwell_exporter import (
    SOLVE_STAGE_NAMES,
    STAGE_NAMES,
)


def test_solve_stage_names_append_analyze_to_the_generate_sequence() -> None:
    assert SOLVE_STAGE_NAMES == STAGE_NAMES + ("analyze",)
    assert SOLVE_STAGE_NAMES_2D == STAGE_NAMES_2D + ("analyze",)


def test_generate_sequences_are_unchanged() -> None:
    assert STAGE_NAMES[-1] == "save"
    assert STAGE_NAMES_2D[-1] == "save"


def test_export_request_defaults_to_generate_only(tmp_path: Path) -> None:
    from inductor_designer.application.ports.maxwell_exporter import (
        Maxwell3dExportRequest,
    )
    from inductor_designer.domain.aedt_target import AedtEdition, AedtRelease

    request = Maxwell3dExportRequest(
        plan=None,  # type: ignore[arg-type]
        release=AedtRelease(2025, 2),
        edition=AedtEdition.COMMERCIAL,
        non_graphical=True,
        output_directory=tmp_path,
        project_name="x",
    )
    assert request.solve is False
    assert request.progress is None
    assert request.cancellation is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/application/test_exporter_ports.py -q`
Expected: FAIL, `ImportError: cannot import name 'SOLVE_STAGE_NAMES'`

- [ ] **Step 3: Write the implementation**

In `maxwell_exporter.py`, after `GEOMETRY_ONLY_STAGE_NAMES`:

```python
# The solve sequence is the generate sequence plus one analyze stage, so a
# Generate Only manifest and a Generate and Solve manifest stay comparable
# stage for stage.
SOLVE_STAGE_NAMES: tuple[str, ...] = STAGE_NAMES + ("analyze",)
```

and add three fields to `Maxwell3dExportRequest`:

```python
    solve: bool = False
    progress: ProgressSink | None = None
    cancellation: CancellationToken | None = None
```

with the import:

```python
from inductor_designer.simulation.run_control import CancellationToken, ProgressSink
```

Mirror both changes in `maxwell2d_exporter.py` (`SOLVE_STAGE_NAMES_2D`, same three fields on `Maxwell2dExportRequest`), and add the same `progress` and `cancellation` fields to `FemmSolveRequest`.

- [ ] **Step 4: Run the tests**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/application -q && .venv/Scripts/python.exe -m mypy src tools`
Expected: PASS, then `Success: no issues found`

- [ ] **Step 5: Commit**

```bash
git add src/inductor_designer/application/ports tests/unit/application/test_exporter_ports.py
git commit -m "feat(ports): add solve stage names, progress and cancellation to run requests"
```

---

### Task 3: Maxwell 3D analyze stage, progress events and cancellation

**Files:**
- Modify: `src/inductor_designer/adapters/pyaedt/maxwell3d.py:332-420`
- Test: `tests/unit/adapters/test_maxwell3d_solve.py`

**Interfaces:**
- Consumes: `SOLVE_STAGE_NAMES`, request fields from Task 2; `StageEvent`, `StagePhase`, `CancellationToken`, `RunCancelled` from Task 1.
- Produces: a `Maxwell3dExportResult` whose stage tuple equals `SOLVE_STAGE_NAMES` on a successful solve, and whose last recorded stage is the one that was running when cancellation was observed. The fake app protocol gains `analyze_setup(name: str) -> bool` and `nominal_adaptive` convergence text via `setup_convergence(name: str) -> str`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/adapters/test_maxwell3d_solve.py
from pathlib import Path

from inductor_designer.application.ports.maxwell_exporter import (
    SOLVE_STAGE_NAMES,
    Maxwell3dExportRequest,
)
from inductor_designer.simulation.run_control import (
    CancellationToken,
    StageEvent,
    StagePhase,
)
from tests.unit.adapters.maxwell3d_fakes import (
    FakeMaxwell3dAppFactory,
    maxwell3d_plan_fixture,
)
from inductor_designer.adapters.pyaedt.maxwell3d import PyaedtMaxwell3dExporter


class RecordingSink:
    def __init__(self) -> None:
        self.events: list[StageEvent] = []

    def emit(self, event: StageEvent) -> None:
        self.events.append(event)


def _request(tmp_path: Path, **overrides: object) -> Maxwell3dExportRequest:
    from inductor_designer.application.services.aedt_support import (
        SUPPORTED_AEDT_EDITION,
        SUPPORTED_AEDT_RELEASE,
    )

    base = {
        "plan": maxwell3d_plan_fixture(),
        "release": SUPPORTED_AEDT_RELEASE,
        "edition": SUPPORTED_AEDT_EDITION,
        "non_graphical": True,
        "output_directory": tmp_path,
        "project_name": "solve_case",
    }
    base.update(overrides)
    return Maxwell3dExportRequest(**base)  # type: ignore[arg-type]


def test_solve_request_runs_the_analyze_stage(tmp_path: Path) -> None:
    factory = FakeMaxwell3dAppFactory()
    exporter = PyaedtMaxwell3dExporter(factory)

    result = exporter.export(_request(tmp_path, solve=True))

    assert tuple(stage.name for stage in result.stages) == SOLVE_STAGE_NAMES
    assert result.succeeded(SOLVE_STAGE_NAMES) is True
    assert factory.app.analyzed_setups == ("Setup1",)


def test_generate_only_request_never_analyzes(tmp_path: Path) -> None:
    factory = FakeMaxwell3dAppFactory()
    exporter = PyaedtMaxwell3dExporter(factory)

    result = exporter.export(_request(tmp_path, solve=False))

    assert "analyze" not in tuple(stage.name for stage in result.stages)
    assert factory.app.analyzed_setups == ()


def test_progress_sink_sees_started_then_succeeded_for_each_stage(
    tmp_path: Path,
) -> None:
    sink = RecordingSink()
    exporter = PyaedtMaxwell3dExporter(FakeMaxwell3dAppFactory())

    exporter.export(_request(tmp_path, solve=True, progress=sink))

    started = [e.stage_name for e in sink.events if e.phase is StagePhase.STARTED]
    assert started == list(SOLVE_STAGE_NAMES)
    assert all(
        e.phase is not StagePhase.FAILED for e in sink.events
    )


def test_cancellation_between_stages_stops_before_analyze(tmp_path: Path) -> None:
    token = CancellationToken()
    factory = FakeMaxwell3dAppFactory()
    factory.app.on_stage("mesh", token.cancel)
    exporter = PyaedtMaxwell3dExporter(factory)

    result = exporter.export(_request(tmp_path, solve=True, cancellation=token))

    names = tuple(stage.name for stage in result.stages)
    assert "analyze" not in names
    assert names[-1] == "cancelled"
    assert result.succeeded(SOLVE_STAGE_NAMES) is False
    assert factory.app.analyzed_setups == ()


def test_failed_analyze_is_recorded_as_a_failed_stage(tmp_path: Path) -> None:
    factory = FakeMaxwell3dAppFactory()
    factory.app.fail_analyze = True
    exporter = PyaedtMaxwell3dExporter(factory)

    result = exporter.export(_request(tmp_path, solve=True))

    analyze = [stage for stage in result.stages if stage.name == "analyze"]
    assert len(analyze) == 1
    assert analyze[0].succeeded is False
    assert result.succeeded(SOLVE_STAGE_NAMES) is False
```

`tests/unit/adapters/maxwell3d_fakes.py` already holds the fake app and plan fixture used by the existing Maxwell 3D adapter tests. Extend it rather than writing a second fake: add `analyzed_setups: tuple[str, ...]`, `fail_analyze: bool`, an `on_stage(name, callback)` hook that the fake calls when the named stage runs, and

```python
    def analyze_setup(self, name: str) -> bool:
        if self.fail_analyze:
            raise RuntimeError("Solver returned a nonzero exit code.")
        self.analyzed_setups += (name,)
        return True

    def setup_convergence(self, name: str) -> str:
        return "3 passes, 0.42% error"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/adapters/test_maxwell3d_solve.py -q`
Expected: FAIL, `TypeError: Maxwell3dExportRequest.__init__() got an unexpected keyword argument 'solve'` is already fixed by Task 2, so the real failure is `AssertionError` on the missing `analyze` stage.

- [ ] **Step 3: Write the implementation**

Add the analyze stage function and the protocol methods in `maxwell3d.py`:

```python
def _stage_analyze(app: Maxwell3dApp, plan: Maxwell3dDesignPlan) -> str:
    if not app.analyze_setup(plan.setup.name):
        raise RuntimeError(f"Setup {plan.setup.name} did not solve.")
    return f"Solved {plan.setup.name}: {app.setup_convergence(plan.setup.name)}."
```

Extend the `Maxwell3dApp` protocol with:

```python
    def analyze_setup(self, name: str) -> bool: ...

    def setup_convergence(self, name: str) -> str: ...
```

Replace the stage loop in `export` so it selects the sequence, emits events, and honours the token. The loop keeps its existing failure behaviour, including the diagnostic save:

```python
        stages_to_run = _STAGES + ((("analyze", _stage_analyze),) if request.solve else ())
        for name, stage in stages_to_run:
            try:
                if request.cancellation is not None:
                    request.cancellation.raise_if_cancelled(name)
            except RunCancelled:
                stages.append(
                    StageRecord(
                        name="cancelled",
                        succeeded=False,
                        message=f"Run cancelled before stage {name!r}.",
                    )
                )
                _emit(request.progress, name, StagePhase.CANCELLED, None)
                _save_after_interruption(app, project_path, stages)
                return result()
            _emit(request.progress, name, StagePhase.STARTED, None)
            try:
                message = stage(app, plan)
            except Exception as error:  # noqa: BLE001 - stage boundary
                stages.append(StageRecord(name=name, succeeded=False, message=str(error)))
                _emit(request.progress, name, StagePhase.FAILED, str(error))
                _save_after_interruption(app, project_path, stages)
                return result()
            stages.append(StageRecord(name=name, succeeded=True, message=message))
            _emit(request.progress, name, StagePhase.SUCCEEDED, message)
```

with two helpers:

```python
def _emit(
    progress: ProgressSink | None,
    stage_name: str,
    phase: StagePhase,
    message: str | None,
) -> None:
    if progress is not None:
        progress.emit(StageEvent(stage_name=stage_name, phase=phase, message=message))


def _save_after_interruption(
    app: Maxwell3dApp, project_path: Path, stages: list[StageRecord]
) -> None:
    """Preserve whatever the design reached; never claim the run succeeded."""
    try:
        app.save_project(str(project_path))
        stages.append(
            StageRecord(
                name="save",
                succeeded=True,
                message="Diagnostic save after an interrupted run.",
            )
        )
    except Exception as error:  # noqa: BLE001 - diagnostic save is best effort
        stages.append(StageRecord(name="save", succeeded=False, message=str(error)))
```

The `save` stage stays where it already is for the normal path; `analyze` runs after it, so a solve that fails still leaves the saved pre-solve project on disk.

- [ ] **Step 4: Run the tests**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/adapters -q`
Expected: PASS, including the pre-existing Maxwell 3D adapter tests

- [ ] **Step 5: Commit**

```bash
git add src/inductor_designer/adapters/pyaedt/maxwell3d.py tests/unit/adapters
git commit -m "feat(maxwell3d): add the analyze stage with progress events and cancellation"
```

---

### Task 4: Maxwell 2D analyze stage, progress events and cancellation

**Files:**
- Modify: `src/inductor_designer/adapters/pyaedt/maxwell2d.py`
- Test: `tests/unit/adapters/test_maxwell2d_solve.py`

**Interfaces:**
- Consumes: `SOLVE_STAGE_NAMES_2D` from Task 2; the helpers `_emit` and `_save_after_interruption` are duplicated deliberately rather than shared, because the two adapters own independent stage tables and must stay independently readable.
- Produces: the same stage/event/cancellation behaviour for the 2D exporter.

- [ ] **Step 1: Write the failing test**

Repeat the five tests from Task 3 against the 2D exporter, using the existing 2D fakes module and `SOLVE_STAGE_NAMES_2D`. The full code, so it can be written without reading Task 3:

```python
# tests/unit/adapters/test_maxwell2d_solve.py
from pathlib import Path

from inductor_designer.adapters.pyaedt.maxwell2d import PyaedtMaxwell2dExporter
from inductor_designer.application.ports.maxwell2d_exporter import (
    SOLVE_STAGE_NAMES_2D,
    Maxwell2dExportRequest,
)
from inductor_designer.application.services.aedt_support import (
    SUPPORTED_AEDT_EDITION,
    SUPPORTED_AEDT_RELEASE,
)
from inductor_designer.simulation.run_control import (
    CancellationToken,
    StageEvent,
    StagePhase,
)
from tests.unit.adapters.maxwell2d_fakes import (
    FakeMaxwell2dAppFactory,
    maxwell2d_plan_fixture,
)


class RecordingSink:
    def __init__(self) -> None:
        self.events: list[StageEvent] = []

    def emit(self, event: StageEvent) -> None:
        self.events.append(event)


def _request(tmp_path: Path, **overrides: object) -> Maxwell2dExportRequest:
    base = {
        "plan": maxwell2d_plan_fixture(),
        "release": SUPPORTED_AEDT_RELEASE,
        "edition": SUPPORTED_AEDT_EDITION,
        "non_graphical": True,
        "output_directory": tmp_path,
        "project_name": "solve_case_2d",
    }
    base.update(overrides)
    return Maxwell2dExportRequest(**base)  # type: ignore[arg-type]


def test_solve_request_runs_the_analyze_stage(tmp_path: Path) -> None:
    factory = FakeMaxwell2dAppFactory()
    result = PyaedtMaxwell2dExporter(factory).export(_request(tmp_path, solve=True))
    assert tuple(stage.name for stage in result.stages) == SOLVE_STAGE_NAMES_2D
    assert factory.app.analyzed_setups == ("Setup1",)


def test_generate_only_request_never_analyzes(tmp_path: Path) -> None:
    factory = FakeMaxwell2dAppFactory()
    result = PyaedtMaxwell2dExporter(factory).export(_request(tmp_path, solve=False))
    assert "analyze" not in tuple(stage.name for stage in result.stages)
    assert factory.app.analyzed_setups == ()


def test_progress_sink_sees_every_stage(tmp_path: Path) -> None:
    sink = RecordingSink()
    PyaedtMaxwell2dExporter(FakeMaxwell2dAppFactory()).export(
        _request(tmp_path, solve=True, progress=sink)
    )
    started = [e.stage_name for e in sink.events if e.phase is StagePhase.STARTED]
    assert started == list(SOLVE_STAGE_NAMES_2D)


def test_cancellation_between_stages_stops_before_analyze(tmp_path: Path) -> None:
    token = CancellationToken()
    factory = FakeMaxwell2dAppFactory()
    factory.app.on_stage("mesh", token.cancel)
    result = PyaedtMaxwell2dExporter(factory).export(
        _request(tmp_path, solve=True, cancellation=token)
    )
    names = tuple(stage.name for stage in result.stages)
    assert "analyze" not in names
    assert names[-1] == "cancelled"
    assert factory.app.analyzed_setups == ()


def test_failed_analyze_is_recorded_as_a_failed_stage(tmp_path: Path) -> None:
    factory = FakeMaxwell2dAppFactory()
    factory.app.fail_analyze = True
    result = PyaedtMaxwell2dExporter(factory).export(_request(tmp_path, solve=True))
    analyze = [stage for stage in result.stages if stage.name == "analyze"]
    assert len(analyze) == 1 and analyze[0].succeeded is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/adapters/test_maxwell2d_solve.py -q`
Expected: FAIL on the missing `analyze` stage

- [ ] **Step 3: Write the implementation**

Apply the Task 3 implementation shape to `maxwell2d.py`: add `analyze_setup` and `setup_convergence` to the 2D app protocol and its fake, add

```python
def _stage_analyze(app: Maxwell2dApp, plan: Maxwell2dDesignPlan) -> str:
    if not app.analyze_setup(plan.setup.name):
        raise RuntimeError(f"Setup {plan.setup.name} did not solve.")
    return f"Solved {plan.setup.name}: {app.setup_convergence(plan.setup.name)}."
```

and replace the 2D stage loop with the same select-emit-check-run loop, including local `_emit` and `_save_after_interruption` helpers.

- [ ] **Step 4: Run the tests**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/adapters -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/inductor_designer/adapters/pyaedt/maxwell2d.py tests/unit/adapters
git commit -m "feat(maxwell2d): add the analyze stage with progress events and cancellation"
```

---

### Task 5: FEMM solve execution

**Files:**
- Modify: `src/inductor_designer/adapters/femm/solver.py:170-220`
- Test: `tests/unit/adapters/test_femm_solve.py`

**Interfaces:**
- Consumes: `FemmSolveRequest.analyze`, `.progress`, `.cancellation`.
- Produces: `FemmSolveResult.analyzed is True` and `results` populated with the raw circuit quantities when `analyze` is true; unchanged Generate Only behaviour otherwise. Stage names emitted by FEMM are `generate` and `analyze`, so a FEMM manifest reads the same way as a Maxwell one.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/adapters/test_femm_solve.py
from pathlib import Path

from inductor_designer.adapters.femm.solver import PyfemmSolver
from inductor_designer.application.ports.femm_solver import FemmSolveRequest
from inductor_designer.simulation.run_control import (
    CancellationToken,
    StageEvent,
    StagePhase,
)
from tests.unit.adapters.femm_fakes import FakeFemmModule, femm_problem_fixture


class RecordingSink:
    def __init__(self) -> None:
        self.events: list[StageEvent] = []

    def emit(self, event: StageEvent) -> None:
        self.events.append(event)


def _request(tmp_path: Path, **overrides: object) -> FemmSolveRequest:
    base = {
        "problem": femm_problem_fixture(),
        "output_directory": tmp_path,
        "project_name": "solve_case_femm",
        "analyze": False,
    }
    base.update(overrides)
    return FemmSolveRequest(**base)  # type: ignore[arg-type]


def test_analyze_request_solves_and_extracts_raw_circuit_quantities(
    tmp_path: Path,
) -> None:
    femm = FakeFemmModule()
    result = PyfemmSolver(femm).solve(_request(tmp_path, analyze=True))
    assert femm.analyze_calls == 1
    assert result.analyzed is True
    assert result.results is not None


def test_generate_only_request_does_not_analyze(tmp_path: Path) -> None:
    femm = FakeFemmModule()
    result = PyfemmSolver(femm).solve(_request(tmp_path, analyze=False))
    assert femm.analyze_calls == 0
    assert result.analyzed is False
    assert result.results is None


def test_progress_sink_sees_generate_and_analyze(tmp_path: Path) -> None:
    sink = RecordingSink()
    PyfemmSolver(FakeFemmModule()).solve(
        _request(tmp_path, analyze=True, progress=sink)
    )
    started = [e.stage_name for e in sink.events if e.phase is StagePhase.STARTED]
    assert started == ["generate", "analyze"]


def test_cancellation_before_analyze_skips_the_solve(tmp_path: Path) -> None:
    token = CancellationToken()
    token.cancel()
    femm = FakeFemmModule()
    result = PyfemmSolver(femm).solve(
        _request(tmp_path, analyze=True, cancellation=token)
    )
    assert femm.analyze_calls == 0
    assert result.analyzed is False
    assert any("cancelled" in message.casefold() for message in result.messages)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/adapters/test_femm_solve.py -q`
Expected: FAIL on the missing progress and cancellation handling

- [ ] **Step 3: Write the implementation**

In `solver.py`, emit `generate` around the existing problem construction, then guard the analyze block:

```python
            _emit(request.progress, "generate", StagePhase.SUCCEEDED, messages[-1])
            if request.analyze:
                if request.cancellation is not None and request.cancellation.cancelled:
                    messages.append("Run cancelled before the FEMM analysis.")
                    return FemmSolveResult(
                        fem_path=fem_path,
                        analyzed=False,
                        results=None,
                        messages=tuple(messages),
                        adapter_version=adapter_version,
                        solver_version=solver_version,
                    )
                _emit(request.progress, "analyze", StagePhase.STARTED, None)
                femm.mi_analyze(1)
```

Keep the existing extraction of circuit quantities exactly as it is; M8a stores it raw and normalizes nothing.

- [ ] **Step 4: Run the tests**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/adapters -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/inductor_designer/adapters/femm tests/unit/adapters/test_femm_solve.py
git commit -m "feat(femm): solve on request with progress events and pre-analyze cancellation"
```

---

### Task 6: Accept Generate and Solve in the run services

**Files:**
- Modify: `src/inductor_designer/application/services/maxwell_export.py:64-69,453-520`
- Modify: `src/inductor_designer/application/services/project_run.py:61-110`
- Create: `src/inductor_designer/application/services/solve_log.py`
- Test: `tests/unit/application/test_generate_and_solve.py`
- Test: `tests/integration/test_project_solve_run.py`

**Interfaces:**
- Consumes: everything from Tasks 1–5.
- Produces: `generate_run(..., progress=None, cancellation=None)` accepting `RunMode.GENERATE_AND_SOLVE`; `start_project_run(..., progress=None, cancellation=None)`; `ProjectRunCancelled(RuntimeError)` carrying `location`, `manifest` and `manifest_path`; `write_solve_log(directory: Path, events: Sequence[StageEvent]) -> Path` writing `results/solve-log.txt`; the constant `_GENERATE_AND_SOLVE_BLOCK` and its raise site are deleted.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/application/test_generate_and_solve.py
from pathlib import Path

from inductor_designer.application.services.maxwell_export import generate_run
from inductor_designer.simulation.run_contracts import (
    RunBackend,
    RunMode,
    RunRequest,
    RunStatus,
)
from tests.unit.application.run_service_fakes import (
    solve_capable_environment,  # existing fake catalog, capabilities and exporters
)


def test_generate_and_solve_is_no_longer_blocked(tmp_path: Path) -> None:
    env = solve_capable_environment(tmp_path)
    outcome = generate_run(
        env.project,
        RunRequest(backend=RunBackend.MAXWELL_3D, mode=RunMode.GENERATE_AND_SOLVE),
        env.catalog,
        env.capabilities,
        tmp_path,
        maxwell3d_exporter=env.maxwell3d,
        maxwell2d_exporter=env.maxwell2d,
        femm_solver=env.femm,
        run_id="20260810-120000",
        application_version="test",
    )
    assert outcome.manifest.mode is RunMode.GENERATE_AND_SOLVE
    assert outcome.manifest.status is RunStatus.SUCCEEDED
    assert any(stage.name == "analyze" for stage in outcome.manifest.stages)


def test_solve_mode_manifest_carries_no_results_in_m8a(tmp_path: Path) -> None:
    env = solve_capable_environment(tmp_path)
    outcome = generate_run(
        env.project,
        RunRequest(backend=RunBackend.MAXWELL_3D, mode=RunMode.GENERATE_AND_SOLVE),
        env.catalog,
        env.capabilities,
        tmp_path,
        maxwell3d_exporter=env.maxwell3d,
        maxwell2d_exporter=env.maxwell2d,
        femm_solver=env.femm,
        run_id="20260810-120001",
        application_version="test",
    )
    assert outcome.manifest.results is None


def test_generate_only_femm_still_rejects_analyzed_evidence(tmp_path: Path) -> None:
    env = solve_capable_environment(tmp_path)
    env.femm.force_analyzed = True
    from inductor_designer.application.services.maxwell_export import (
        RunGenerationFailed,
    )

    import pytest

    with pytest.raises(RunGenerationFailed) as failure:
        generate_run(
            env.project,
            RunRequest(backend=RunBackend.FEMM, mode=RunMode.GENERATE_ONLY),
            env.catalog,
            env.capabilities,
            tmp_path,
            maxwell3d_exporter=env.maxwell3d,
            maxwell2d_exporter=env.maxwell2d,
            femm_solver=env.femm,
            run_id="20260810-120002",
            application_version="test",
        )
    assert failure.value.manifest.status is RunStatus.FAILED
```

```python
# tests/integration/test_project_solve_run.py
import json
from pathlib import Path

import pytest

from inductor_designer.application.services.project_run import (
    ProjectRunCancelled,
    start_project_run,
)
from inductor_designer.simulation.run_contracts import (
    RunBackend,
    RunMode,
    RunRequest,
    RunStatus,
)
from inductor_designer.simulation.run_control import CancellationToken
from tests.integration.solve_fixtures import saved_project_environment


def test_solve_run_writes_a_running_manifest_before_the_adapter(tmp_path: Path) -> None:
    env = saved_project_environment(tmp_path)
    seen: list[str] = []

    def peek() -> None:
        manifest_path = next(
            (tmp_path / "runs").glob("*/run-manifest.json")
        )
        seen.append(json.loads(manifest_path.read_text(encoding="utf-8"))["status"])

    env.maxwell3d.before_export = peek
    start_project_run(**env.call(mode=RunMode.GENERATE_AND_SOLVE))
    assert seen == ["running"]


def test_completed_solve_run_overwrites_the_running_manifest(tmp_path: Path) -> None:
    env = saved_project_environment(tmp_path)
    result = start_project_run(**env.call(mode=RunMode.GENERATE_AND_SOLVE))
    document = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert document["status"] == "succeeded"
    assert document["mode"] == "generate-and-solve"


def test_cancelled_run_is_recorded_as_cancelled_with_its_evidence(
    tmp_path: Path,
) -> None:
    env = saved_project_environment(tmp_path)
    token = CancellationToken()
    env.maxwell3d.cancel_at_stage = ("mesh", token)
    with pytest.raises(ProjectRunCancelled) as cancelled:
        start_project_run(
            **env.call(mode=RunMode.GENERATE_AND_SOLVE, cancellation=token)
        )
    manifest = cancelled.value.manifest
    assert manifest.status is RunStatus.CANCELLED
    document = json.loads(
        cancelled.value.manifest_path.read_text(encoding="utf-8")
    )
    assert document["status"] == "cancelled"
    assert document["results"] is None


def test_solve_log_lands_in_the_reserved_results_directory(tmp_path: Path) -> None:
    env = saved_project_environment(tmp_path)
    result = start_project_run(**env.call(mode=RunMode.GENERATE_AND_SOLVE))
    log_path = result.location.directory / "results" / "solve-log.txt"
    assert log_path.exists()
    assert "analyze" in log_path.read_text(encoding="utf-8")
    document = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert any(
        artifact["kind"] == "solve-log" for artifact in document["artifacts"]
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/application/test_generate_and_solve.py tests/integration/test_project_solve_run.py -q`
Expected: FAIL, `MaxwellExportBlocked: Generate and Solve execution belongs to M8`

- [ ] **Step 3: Write the implementation**

In `maxwell_export.py`: delete `_GENERATE_AND_SOLVE_BLOCK` and the `if request.mode is RunMode.GENERATE_AND_SOLVE: raise` guard; add `progress` and `cancellation` parameters to `generate_run` and pass `solve=request.mode is RunMode.GENERATE_AND_SOLVE` plus both through to each `_export_*` helper; set `analyze=request.mode is RunMode.GENERATE_AND_SOLVE` in `_export_femm_plan`; select the expected stage names in `_manifest_for_result` by mode:

```python
        expected_stage_names = (
            GEOMETRY_ONLY_STAGE_NAMES
            if isinstance(planned_run, GeometryOnlyRunPlan)
            else _solve_aware(
                STAGE_NAMES if backend is RunBackend.MAXWELL_3D else STAGE_NAMES_2D,
                SOLVE_STAGE_NAMES
                if backend is RunBackend.MAXWELL_3D
                else SOLVE_STAGE_NAMES_2D,
                planned_run.request.mode,
            )
        )
```

```python
def _solve_aware(
    generate_names: tuple[str, ...],
    solve_names: tuple[str, ...],
    mode: RunMode,
) -> tuple[str, ...]:
    return solve_names if mode is RunMode.GENERATE_AND_SOLVE else generate_names
```

Narrow the existing FEMM nonconforming-evidence guard so it only applies to `RunMode.GENERATE_ONLY`. Add `RunCancelled` handling that builds a manifest with `RunStatus.CANCELLED` and raises a new `RunCancelledDuringGeneration` carrying it.

New `solve_log.py`:

```python
"""The human-readable stage log for one run, written into ``results/``."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from inductor_designer.simulation.run_control import StageEvent


def write_solve_log(run_directory: Path, events: Sequence[StageEvent]) -> Path:
    results_directory = run_directory / "results"
    results_directory.mkdir(parents=True, exist_ok=True)
    path = results_directory / "solve-log.txt"
    path.write_text(
        "".join(
            f"{event.stage_name}\t{event.phase.value}\t{event.message or ''}\n"
            for event in events
        ),
        encoding="utf-8",
    )
    return path
```

In `project_run.py`: write the `running` manifest right after `allocate_run_directory`, collect events into a recording sink that is always passed to `generate_run` (chaining to the caller's sink when one is supplied), write the solve log and append its `ManifestArtifact` before the final manifest write, and translate `RunCancelledDuringGeneration` into `ProjectRunCancelled` after writing the cancelled manifest.

- [ ] **Step 4: Run the tests**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/application tests/integration -q`
Expected: PASS, including the existing golden-manifest tests, which must still match byte for byte for Generate Only runs

- [ ] **Step 5: Commit**

```bash
git add src/inductor_designer/application tests/unit/application tests/integration
git commit -m "feat(simulation): execute Generate and Solve with durable status and cancellation"
```

---

### Task 7: Guided Studio solve controls

**Files:**
- Modify: `src/inductor_designer/ui/generation_controller.py:34-133`
- Modify: `src/inductor_designer/ui/simulation_controller.py:33-36,82-91,288-304`
- Modify: `src/inductor_designer/ui/qml/SimulationStep.qml`
- Test: `tests/ui/test_simulation_solve_controls.py`

**Interfaces:**
- Consumes: `CancellationToken`, `StageEvent`, `StagePhase`, `start_project_run` with its new parameters.
- Produces: `GenerationController.generate(backend_label, show_solver_window, solve)`, `GenerationController.cancel()`, a `cancellable` property; `SimulationController.setMode(label) -> bool`, `mode` property returning either `generate-only` or `generate-and-solve`, and `cancel()`.

- [ ] **Step 1: Write the failing test**

```python
# tests/ui/test_simulation_solve_controls.py
from inductor_designer.simulation.run_contracts import RunMode
from tests.ui.controller_fixtures import simulation_controller_environment


def test_mode_defaults_to_generate_only() -> None:
    env = simulation_controller_environment()
    assert env.controller.mode == RunMode.GENERATE_ONLY.value


def test_mode_can_be_set_to_generate_and_solve() -> None:
    env = simulation_controller_environment()
    assert env.controller.setMode(RunMode.GENERATE_AND_SOLVE.value) is True
    assert env.controller.mode == RunMode.GENERATE_AND_SOLVE.value


def test_generate_passes_the_selected_mode_to_the_runner() -> None:
    env = simulation_controller_environment()
    env.controller.setMode(RunMode.GENERATE_AND_SOLVE.value)
    env.controller.generate()
    env.wait_for_idle()
    assert env.runner.calls[-1].solve is True


def test_cancel_marks_the_token_and_the_run_reports_cancelled() -> None:
    env = simulation_controller_environment()
    env.controller.setMode(RunMode.GENERATE_AND_SOLVE.value)
    env.runner.block_until_cancelled = True
    env.controller.generate()
    env.wait_for_busy()
    env.controller.cancel()
    env.wait_for_idle()
    assert env.runner.calls[-1].cancellation.cancelled is True
    assert any("cancel" in line.casefold() for line in env.generation.lines)


def test_cancel_is_refused_when_no_run_is_in_flight() -> None:
    env = simulation_controller_environment()
    assert env.controller.cancel() is False


def test_stage_events_stream_into_the_lines_while_running() -> None:
    env = simulation_controller_environment()
    env.controller.setMode(RunMode.GENERATE_AND_SOLVE.value)
    env.controller.generate()
    env.wait_for_idle()
    assert any(line.startswith("analyze") for line in env.generation.lines)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `set QT_QPA_PLATFORM=offscreen && .venv/Scripts/python.exe -m pytest tests/ui/test_simulation_solve_controls.py -q`
Expected: FAIL, `AttributeError: 'SimulationController' object has no attribute 'setMode'`

- [ ] **Step 3: Write the implementation**

`GenerationController`: create a `CancellationToken` per run, keep it on the instance while `busy`, expose

```python
    @Slot(result=bool)
    def cancel(self) -> bool:
        token = self._token
        if token is None or not self._busy:
            return False
        token.cancel()
        self._append_line("Cancelling after the current stage...")
        return True
```

and pass a sink whose `emit` appends `f"{event.stage_name}\t{event.phase.value}"` to `self._lines` and emits `linesChanged`, so QML sees progress while the worker runs rather than only at the end.

`SimulationController`: replace the fixed `_get_mode_label` with a settable `_mode`, delete `_MODE_NOTE` about M8, pass `solve=self._mode is RunMode.GENERATE_AND_SOLVE` into `self._generation.generate(...)`, and forward `cancel()`.

`SimulationStep.qml`: a two-option mode selector bound to `setMode`, the stage lines list bound to `generation.lines`, and a `Cancel` button `enabled: generation.busy` calling `simulation.cancel()`.

- [ ] **Step 4: Run the tests**

Run: `set QT_QPA_PLATFORM=offscreen && set QSG_RHI_BACKEND=software && .venv/Scripts/python.exe -m pytest tests/ui -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/inductor_designer/ui tests/ui
git commit -m "feat(ui): add the Generate and Solve mode, live stage progress and cancel"
```

---

### Task 8: Acceptance evidence and documentation

**Files:**
- Create: `docs/development/m8a-live-solve-evidence.md`
- Modify: `docs/development/ROADMAP.md`
- Modify: `docs/superpowers/plans/README.md`
- Test: `tests/integration/test_project_solve_run.py` (extend), plus the live suites behind `aedt` and `femm`

**Interfaces:**
- Consumes: the whole slice.
- Produces: the acceptance record. No code interface.

- [ ] **Step 1: Run the full non-live gate**

```bash
.venv/Scripts/python.exe -m ruff check .
```

Expected: `All checks passed!`

- [ ] **Step 2: Run types, architecture and the suite**

```bash
.venv/Scripts/python.exe -m mypy src tools
```

Expected: `Success: no issues found`

```bash
.venv/Scripts/python.exe -m pytest -n 8 -m "not aedt and not femm" -q
```

Expected: all passed, no failures; record the exact count and duration for the acceptance note

- [ ] **Step 3: Run the live evidence on the Windows workstation**

```bash
.venv/Scripts/python.exe -m pytest -m aedt -q
```

Expected: one Maxwell 3D and one Maxwell 2D `generate-and-solve` run reaching `analyze` and finishing `succeeded`

```bash
.venv/Scripts/python.exe -m pytest -m femm -q
```

Expected: one FEMM run with `analyzed=true` in its manifest stages

- [ ] **Step 4: Write the evidence document**

`docs/development/m8a-live-solve-evidence.md` records, per backend: the run directory name, the stage sequence from the manifest, the status, the solve duration, the `results/solve-log.txt` tail, and one deliberately cancelled run showing `status: cancelled` with no `analyze` stage.

- [ ] **Step 5: Update the roadmap and the plan index**

State in both that M8a is implementation-complete and awaiting Fabio Posser's acceptance, that `RunManifest.results` is still `None` by design, and that M8b owns scalar normalization and M8c owns field results.

- [ ] **Step 6: Commit**

```bash
git add docs
git commit -m "docs: record M8a solve execution evidence"
```

---

## Self-Review

**Spec coverage against the roadmap realignment M8 list:** execute all three backends — Tasks 3, 4, 5. Activate `Generate and Solve` in the Guided Studio — Tasks 6, 7. Progress, cancellation, durable status, failure diagnostics — Tasks 1, 6, 7. Honor multi-winding AC RMS current and phase — unchanged, already carried by the effective inputs and asserted by the existing golden manifests. Validate DC-biased behavior where supported — unchanged, `select_dc_bias_strategy` already gates it before planning. Extract and normalize results, representative cross sections, availability presentation, JSON and CSV export — deliberately **not** in this slice; M8b and M8c own them, and this plan states that in its Scope section.

**Placeholder scan:** no TBD, no "handle edge cases", every code step carries its code.

**Type consistency:** `CancellationToken`, `StageEvent`, `StagePhase`, `ProgressSink` and `RunCancelled` are defined in Task 1 and used with those exact names in Tasks 2–7. `SOLVE_STAGE_NAMES` and `SOLVE_STAGE_NAMES_2D` are defined in Task 2 and consumed in Tasks 3, 4 and 6. `write_solve_log` is defined and consumed in Task 6.

**Known deviation to raise at review:** Task 3 and Task 4 duplicate `_emit` and `_save_after_interruption` across the two adapters. That is deliberate — the adapters own independent stage tables and are read independently — but a reviewer may prefer one shared helper in `adapters/pyaedt/`. Decide it at the Task 4 gate rather than mid-implementation.
