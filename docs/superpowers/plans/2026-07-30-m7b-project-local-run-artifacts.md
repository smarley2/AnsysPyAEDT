# M7b Project-Local Run Artifacts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every generation run writes into a new, non-overwriting
`<project-directory>/runs/<run-id>-<backend>/` directory next to the saved
`*.inductor.json` document, always leaves a truthful `run-manifest.json` there
with project-relative artifact paths, runs the solver hidden by default with an
opt-in visible window, and exposes the run folder and generated solver file for
the M7c screens to open.

**Architecture:** Three new solver-independent application services —
`run_directory.py` (run id, directory allocation, relative artifact paths),
`solver_visibility.py` (per-backend visible-window support), and
`project_run.py` (the one entry point every caller uses) — plus one new port and
Windows adapter for opening a path. `generate_run` stays the low-level exporter
dispatcher and gains two parameters; all three existing entry points (Qt UI, MCP
server, CLI tools) drop their private output-directory and manifest-writing code
and call `start_project_run` instead. No QML file is touched: M7c wires the
`Show solver window` checkbox and the `Open generated file` / `Open run folder`
buttons to the ports this plan delivers and tests.

**Tech Stack:** Python 3.10–3.13, frozen dataclasses and enums, stdlib only
(`pathlib`, `datetime`, `os`, `sys`), pytest, Ruff, strict mypy, PySide6 for the
existing UI entry point.

## Global Constraints

- Owner: one executor per working tree. Do not run two agents in the same tree.
- Entry condition: M7a is accepted; `main` starts at `491c005`.
- Branch: `m7b/project-local-run-artifacts`. Squash-merge to `main` after the
  final whole-branch review.
- This plan implements
  [ADR 0007](../../adr/0007-project-local-run-artifacts-and-solver-visibility.md)
  and specification section 4.4 of
  `docs/superpowers/specs/2026-07-26-preliminary-calculations-and-guided-flow-design.md`.
  Do not reopen their approved product decisions.
- Scope is run artifacts and solver visibility. No QML file, no Guided Studio
  screen, no estimator change, no solve execution. Screens are M7c; solving and
  `results/` population are M8.
- The canonical layout, copied verbatim from ADR 0007:

  ```text
  <project-directory>/
    <project-name>.inductor.json
    runs/
      <run-id>-<backend>/
        run-manifest.json
        <generated solver project>
        results/
  ```

- Run id is a UTC timestamp `YYYYMMDD-HHMMSS`, with a `-2`, `-3` … suffix when
  an earlier run already owns that second. The run id in `run-manifest.json` and
  the run directory name always carry the same id (decision, Fabio 2026-07-30).
- Backend labels in directory names are the existing `RunBackend` values:
  `maxwell-3d`, `maxwell-2d`, `femm`.
- Run directories are created with `exist_ok=False`. Nothing existing is ever
  overwritten, moved, or cleaned up — except an empty directory a blocked run
  never wrote into.
- A failed run keeps its directory and its `run-manifest.json`. Partial output is
  never reported as success.
- Solver operation is background/non-graphical by default. Visible operation is
  per-run and opt-in, and is reported unsupported with a reason rather than
  silently ignored.
- Manifest artifact paths are POSIX strings relative to the project directory.
  An artifact outside the project directory falls back to an absolute POSIX path.
- Python 3.10 is the floor: use `datetime.timezone.utc`, never `datetime.UTC`.
- The quality CI job runs on `ubuntu-latest` and the test matrix runs on several
  operating systems: no test may call a Windows-only API, and Windows-only code
  must sit behind `if sys.platform == "win32":` so strict mypy narrows it.
- English for code, tests, docs, diagnostics, and commits.
- Run these gates before every commit:
  `.venv/Scripts/python.exe -m pytest tests -q -m "not aedt and not femm"`,
  `.venv/Scripts/python.exe -m ruff check .`,
  `.venv/Scripts/python.exe -m mypy src tools`,
  `.venv/Scripts/python.exe tools/check_architecture.py`,
  `git diff --check`.

## Contracts this plan consumes

Read these before Task 1; the plan relies on their exact names.

| Type | Location | Used for |
| --- | --- | --- |
| `RunBackend` | `simulation/run_contracts.py:16` | directory label (`.value`) |
| `RunRequest`, `RunMode` | `simulation/run_contracts.py:22` | run request |
| `RunManifest`, `ManifestArtifact` | `simulation/run_contracts.py:103` | manifest and artifact paths |
| `generate_run` | `application/services/maxwell_export.py:431` | exporter dispatch |
| `RunOutcome`, `RunGenerationFailed` | `application/services/maxwell_export.py:78` | success and failure evidence |
| `MaxwellExportBlocked` | `application/services/maxwell_export.py:66` | blocked before any adapter call |
| `RunPlanningError` | `application/services/run_planning.py:55` | invalid project |
| `run_manifest_json` | `application/services/maxwell_export.py:659` | manifest serialization |
| `aedt_support_issues`, `SUPPORTED_AEDT_RELEASE`, `SUPPORTED_AEDT_EDITION` | `application/services/aedt_support.py` | AEDT visibility support |
| `CapabilitySnapshot` | `simulation/capabilities.py` | installed-solver evidence |
| `FemmSolveRequest` | `application/ports/femm_solver.py:11` | FEMM window visibility |
| `RecordingFemmSolver`, `RecordingMaxwell3dExporter`, `RecordingMaxwell2dExporter` | `tests/fakes/` | port fakes for every new test |

The application layer may import `pathlib`, `datetime`, and `os`
(`tools/check_architecture.py` forbids only `PySide6`, `ansys`, `femm`, `mcp`,
`pyaedt`, `sqlite3` and `inductor_designer.adapters` there). Keep it passing.

---

### Task 1: Run id and run-directory allocation

**Files:**
- Create: `src/inductor_designer/application/services/run_directory.py`
- Test: `tests/unit/application/test_run_directory.py`

**Interfaces:**
- Consumes: `RunBackend`.
- Produces: `RUNS_DIRECTORY_NAME`, `RESULTS_DIRECTORY_NAME`,
  `MANIFEST_FILENAME`, `RunDirectoryError`, `RunLocation` (fields `run_id`,
  `project_directory`, `directory`, `results_directory`; property
  `manifest_path`), `run_id_for(moment)`,
  `allocate_run_directory(project_document_path, backend, *, now=None)`,
  `artifact_path_for_manifest(path, project_directory)`,
  `discard_empty_run_directory(location)`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/application/test_run_directory.py`:

```python
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from inductor_designer.application.services.run_directory import (
    MANIFEST_FILENAME,
    RunDirectoryError,
    RunLocation,
    allocate_run_directory,
    artifact_path_for_manifest,
    discard_empty_run_directory,
    run_id_for,
)
from inductor_designer.simulation.run_contracts import RunBackend

MOMENT = datetime(2026, 7, 30, 10, 15, 0, tzinfo=timezone.utc)


def saved_project(tmp_path: Path) -> Path:
    path = tmp_path / "boost.inductor.json"
    path.write_text("{}", encoding="utf-8")
    return path


def test_run_id_is_a_utc_timestamp() -> None:
    assert run_id_for(MOMENT) == "20260730-101500"


def test_run_id_converts_a_local_moment_to_utc() -> None:
    local = MOMENT.astimezone(timezone(timedelta(hours=2)))

    assert run_id_for(local) == "20260730-101500"


def test_allocation_creates_the_adr_layout_next_to_the_project(tmp_path: Path) -> None:
    document = saved_project(tmp_path)

    location = allocate_run_directory(document, RunBackend.MAXWELL_3D, now=MOMENT)

    assert isinstance(location, RunLocation)
    assert location.run_id == "20260730-101500"
    assert location.project_directory == tmp_path.resolve()
    assert location.directory == tmp_path.resolve() / "runs" / "20260730-101500-maxwell-3d"
    assert location.directory.is_dir()
    assert location.results_directory == location.directory / "results"
    assert location.results_directory.is_dir()
    assert location.manifest_path == location.directory / MANIFEST_FILENAME


def test_each_backend_gets_its_own_directory(tmp_path: Path) -> None:
    document = saved_project(tmp_path)

    first = allocate_run_directory(document, RunBackend.MAXWELL_2D, now=MOMENT)
    second = allocate_run_directory(document, RunBackend.FEMM, now=MOMENT)

    assert first.directory.name == "20260730-101500-maxwell-2d"
    assert second.directory.name == "20260730-101500-femm"


def test_a_second_run_in_the_same_second_suffixes_the_run_id(tmp_path: Path) -> None:
    document = saved_project(tmp_path)

    first = allocate_run_directory(document, RunBackend.FEMM, now=MOMENT)
    second = allocate_run_directory(document, RunBackend.FEMM, now=MOMENT)
    third = allocate_run_directory(document, RunBackend.FEMM, now=MOMENT)

    assert first.run_id == "20260730-101500"
    assert second.run_id == "20260730-101500-2"
    assert third.run_id == "20260730-101500-3"
    assert second.directory.name == "20260730-101500-2-femm"
    assert len({first.directory, second.directory, third.directory}) == 3


def test_an_existing_run_directory_is_never_overwritten(tmp_path: Path) -> None:
    document = saved_project(tmp_path)
    existing = tmp_path / "runs" / "20260730-101500-femm"
    existing.mkdir(parents=True)
    (existing / "keep.txt").write_text("evidence", encoding="utf-8")

    location = allocate_run_directory(document, RunBackend.FEMM, now=MOMENT)

    assert location.directory != existing
    assert (existing / "keep.txt").read_text(encoding="utf-8") == "evidence"


def test_an_unsaved_project_is_refused_with_an_actionable_message(tmp_path: Path) -> None:
    with pytest.raises(RunDirectoryError, match="save the project"):
        allocate_run_directory(
            tmp_path / "never-saved.inductor.json",
            RunBackend.MAXWELL_3D,
            now=MOMENT,
        )


def test_a_directory_instead_of_a_document_is_refused(tmp_path: Path) -> None:
    with pytest.raises(RunDirectoryError):
        allocate_run_directory(tmp_path, RunBackend.MAXWELL_3D, now=MOMENT)


def test_artifact_paths_are_relative_to_the_project_directory(tmp_path: Path) -> None:
    artifact = tmp_path / "runs" / "20260730-101500-femm" / "Boost_2d.fem"

    assert (
        artifact_path_for_manifest(artifact, tmp_path)
        == "runs/20260730-101500-femm/Boost_2d.fem"
    )


def test_an_artifact_outside_the_project_directory_stays_absolute(tmp_path: Path) -> None:
    outside = tmp_path.parent / "elsewhere" / "Boost.aedt"

    value = artifact_path_for_manifest(outside, tmp_path)

    assert value == outside.resolve().as_posix()
    assert value.endswith("elsewhere/Boost.aedt")


def test_an_empty_run_directory_is_discarded(tmp_path: Path) -> None:
    location = allocate_run_directory(saved_project(tmp_path), RunBackend.FEMM, now=MOMENT)

    assert discard_empty_run_directory(location) is True
    assert not location.directory.exists()


def test_a_run_directory_holding_evidence_is_kept(tmp_path: Path) -> None:
    location = allocate_run_directory(saved_project(tmp_path), RunBackend.FEMM, now=MOMENT)
    location.manifest_path.write_text("{}", encoding="utf-8")

    assert discard_empty_run_directory(location) is False
    assert location.manifest_path.is_file()
```

- [ ] **Step 2: Run the test and verify RED**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/application/test_run_directory.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named
'inductor_designer.application.services.run_directory'`.

- [ ] **Step 3: Implement the run directory service**

Create `src/inductor_designer/application/services/run_directory.py`:

```python
"""Project-local run directories (ADR 0007).

A run lives next to the saved project document:

    <project-directory>/runs/<run-id>-<backend>/

Directories are created with ``exist_ok=False`` so a run can never overwrite an
earlier one, and the run id carries a ``-2``, ``-3`` ... suffix when an earlier
run already owns that UTC second. The run id in ``run-manifest.json`` and the
directory name always match.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from inductor_designer.simulation.run_contracts import RunBackend

RUNS_DIRECTORY_NAME = "runs"
RESULTS_DIRECTORY_NAME = "results"
MANIFEST_FILENAME = "run-manifest.json"

# A second holding this many runs is a runaway caller, not a double click.
_MAX_RUNS_PER_SECOND = 100


class RunDirectoryError(ValueError):
    """A run directory could not be allocated."""


@dataclass(frozen=True, slots=True)
class RunLocation:
    """Where one run writes. Paths are absolute; manifest paths are relative."""

    run_id: str
    project_directory: Path
    directory: Path
    results_directory: Path

    @property
    def manifest_path(self) -> Path:
        return self.directory / MANIFEST_FILENAME


def run_id_for(moment: datetime) -> str:
    """UTC ``YYYYMMDD-HHMMSS``; a local moment is converted, never truncated."""
    return moment.astimezone(timezone.utc).strftime("%Y%m%d-%H%M%S")


def allocate_run_directory(
    project_document_path: Path,
    backend: RunBackend,
    *,
    now: datetime | None = None,
) -> RunLocation:
    """Create one new run directory beside the saved project document."""
    if not project_document_path.is_file():
        raise RunDirectoryError(
            f"Project document {project_document_path} does not exist; "
            "save the project before starting a run."
        )
    project_directory = project_document_path.resolve().parent
    base_id = run_id_for(datetime.now(timezone.utc) if now is None else now)
    runs_root = project_directory / RUNS_DIRECTORY_NAME
    for attempt in range(1, _MAX_RUNS_PER_SECOND + 1):
        run_id = base_id if attempt == 1 else f"{base_id}-{attempt}"
        directory = runs_root / f"{run_id}-{backend.value}"
        try:
            directory.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            continue
        results_directory = directory / RESULTS_DIRECTORY_NAME
        results_directory.mkdir()
        return RunLocation(
            run_id=run_id,
            project_directory=project_directory,
            directory=directory,
            results_directory=results_directory,
        )
    raise RunDirectoryError(
        f"Could not allocate a run directory under {runs_root}: "
        f"{_MAX_RUNS_PER_SECOND} runs already exist for {base_id}."
    )


def artifact_path_for_manifest(path: Path, project_directory: Path) -> str:
    """Relative POSIX path so the project directory can be moved (ADR 0007).

    An artifact outside the project directory keeps an absolute path rather than
    a misleading ``../..`` chain.
    """
    resolved = path.resolve()
    try:
        return resolved.relative_to(project_directory.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def discard_empty_run_directory(location: RunLocation) -> bool:
    """Remove a run directory a blocked run never wrote into.

    Returns ``False`` and changes nothing when any evidence is present: a failed
    run keeps its directory and manifest.
    """
    try:
        location.results_directory.rmdir()
    except OSError:
        return False
    try:
        location.directory.rmdir()
    except OSError:
        location.results_directory.mkdir(exist_ok=True)
        return False
    return True
```

- [ ] **Step 4: Run the test and verify GREEN**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/application/test_run_directory.py -q`
Expected: `13 passed`.

- [ ] **Step 5: Run the gates and commit**

```bash
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m mypy src tools
.venv/Scripts/python.exe tools/check_architecture.py
git add src/inductor_designer/application/services/run_directory.py tests/unit/application/test_run_directory.py
git commit -m "feat(application): allocate project-local run directories"
```

---

### Task 2: Visible-window support per backend

**Files:**
- Create: `src/inductor_designer/application/services/solver_visibility.py`
- Test: `tests/unit/application/test_solver_visibility.py`

**Interfaces:**
- Consumes: `RunBackend`, `CapabilitySnapshot`, `aedt_support_issues`.
- Produces: `VisibilitySupport` (fields `supported`, `reason`) and
  `visible_window_support(backend, capabilities) -> VisibilitySupport`.

ADR 0007: an unavailable visible mode is disabled with an explanation; it never
silently changes behaviour.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/application/test_solver_visibility.py`:

```python
from __future__ import annotations

import pytest

from inductor_designer.application.services.solver_visibility import (
    VisibilitySupport,
    visible_window_support,
)
from inductor_designer.domain.aedt_target import AedtEdition, AedtRelease
from inductor_designer.simulation.capabilities import (
    CapabilityReviewStatus,
    CapabilitySnapshot,
)
from inductor_designer.simulation.run_contracts import RunBackend

SUPPORTED = CapabilitySnapshot(
    release=AedtRelease(2025, 2),
    edition=AedtEdition.COMMERCIAL,
    include_dc_fields_3d=True,
    discovered_limits=(),
    evidence_source="M7b visibility test",
    review_status=CapabilityReviewStatus.REVIEWED,
)
UNSUPPORTED = CapabilitySnapshot(
    release=AedtRelease(2024, 2),
    edition=AedtEdition.COMMERCIAL,
    include_dc_fields_3d=None,
    discovered_limits=(),
    evidence_source="M7b visibility test",
    review_status=CapabilityReviewStatus.REVIEWED,
)


@pytest.mark.parametrize(
    "backend",
    [RunBackend.MAXWELL_3D, RunBackend.MAXWELL_2D, RunBackend.FEMM],
)
def test_every_backend_supports_a_visible_window_on_a_supported_install(
    backend: RunBackend,
) -> None:
    support = visible_window_support(backend, SUPPORTED)

    assert support == VisibilitySupport(supported=True, reason=None)


@pytest.mark.parametrize("backend", [RunBackend.MAXWELL_3D, RunBackend.MAXWELL_2D])
def test_maxwell_visibility_is_unsupported_when_the_install_does_not_match(
    backend: RunBackend,
) -> None:
    support = visible_window_support(backend, UNSUPPORTED)

    assert support.supported is False
    assert "2024.2" in str(support.reason)


def test_femm_visibility_does_not_depend_on_the_aedt_install() -> None:
    support = visible_window_support(RunBackend.FEMM, UNSUPPORTED)

    assert support.supported is True


def test_a_supported_result_carries_no_reason() -> None:
    with pytest.raises(ValueError, match="no reason"):
        VisibilitySupport(supported=True, reason="unused")


def test_an_unsupported_result_requires_a_reason() -> None:
    with pytest.raises(ValueError, match="reason"):
        VisibilitySupport(supported=False, reason="  ")
```

- [ ] **Step 2: Run the test and verify RED**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/application/test_solver_visibility.py -q`
Expected: FAIL with `ModuleNotFoundError` for
`inductor_designer.application.services.solver_visibility`.

- [ ] **Step 3: Implement the support query**

Create `src/inductor_designer/application/services/solver_visibility.py`:

```python
"""Per-backend `Show solver window` support (ADR 0007).

Background operation is always available. Visible operation is reported
unsupported with a reason so the UI can disable the choice and explain it
instead of silently running hidden.
"""

from __future__ import annotations

from dataclasses import dataclass

from inductor_designer.application.services.aedt_support import (
    SUPPORTED_AEDT_EDITION,
    SUPPORTED_AEDT_RELEASE,
    aedt_support_issues,
)
from inductor_designer.simulation.capabilities import CapabilitySnapshot
from inductor_designer.simulation.run_contracts import RunBackend


@dataclass(frozen=True, slots=True)
class VisibilitySupport:
    supported: bool
    reason: str | None

    def __post_init__(self) -> None:
        if self.supported and self.reason is not None:
            raise ValueError("supported visibility carries no reason")
        if not self.supported and not (self.reason or "").strip():
            raise ValueError("unsupported visibility requires a reason")


def visible_window_support(
    backend: RunBackend, capabilities: CapabilitySnapshot
) -> VisibilitySupport:
    """FEMM always shows its window on request; Maxwell needs a supported AEDT."""
    if backend is RunBackend.FEMM:
        return VisibilitySupport(supported=True, reason=None)
    issues = aedt_support_issues(
        SUPPORTED_AEDT_RELEASE,
        SUPPORTED_AEDT_EDITION,
        capabilities,
    )
    if issues:
        return VisibilitySupport(supported=False, reason="; ".join(issues))
    return VisibilitySupport(supported=True, reason=None)
```

- [ ] **Step 4: Run the test and verify GREEN**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/application/test_solver_visibility.py -q`
Expected: `8 passed`.

- [ ] **Step 5: Run the gates and commit**

```bash
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m mypy src tools
.venv/Scripts/python.exe tools/check_architecture.py
git add src/inductor_designer/application/services/solver_visibility.py tests/unit/application/test_solver_visibility.py
git commit -m "feat(application): report per-backend solver-window support"
```

---

### Task 3: FEMM window visibility through the port

**Files:**
- Modify: `src/inductor_designer/application/ports/femm_solver.py:11-19`
- Modify: `src/inductor_designer/adapters/femm/solver.py:103-113`
- Test: `tests/unit/adapters/test_femm_solver.py`

**Interfaces:**
- Produces: `FemmSolveRequest.show_window: bool = False`, honoured by
  `PyfemmSolver.solve` as `femm.openfemm(0)` when visible and
  `femm.openfemm(1)` when hidden.

`pyfemm` takes the *hide* flag: `openfemm(1)` hides the window, `openfemm(0)`
shows it. The adapter currently hardcodes `1`.

- [ ] **Step 1: Write the failing test**

`tests/unit/adapters/test_femm_solver.py` already has `make_request(tmp_path,
analyze=True)`, a `run(...)` helper, and `FakeFemmModule` from
`tests/fakes/femm_module.py`, which records every call as `(name, args)`. Give
the request builder the new flag and add two tests.

Change the existing builder:

```python
def make_request(
    tmp_path: Path, analyze: bool = True, show_window: bool = False
) -> FemmSolveRequest:
    plan = build2d((make_definition(),))  # type: ignore[arg-type]
    problem = femm_problem_from_plan(plan)
    return FemmSolveRequest(
        problem=problem,
        output_directory=tmp_path,
        project_name="test_inductor",
        analyze=analyze,
        show_window=show_window,
    )
```

Append the tests:

```python
def _openfemm_args(module: FakeFemmModule) -> tuple[object, ...]:
    return next(args for name, args in module.calls if name == "openfemm")


def test_a_hidden_run_hides_the_femm_window(tmp_path: Path) -> None:
    module = FakeFemmModule()
    solver = PyfemmSolver(module_factory=FakeFemmModuleFactory(module))

    solver.solve(make_request(tmp_path, show_window=False))

    assert _openfemm_args(module) == (1,)


def test_a_visible_run_shows_the_femm_window(tmp_path: Path) -> None:
    module = FakeFemmModule()
    solver = PyfemmSolver(module_factory=FakeFemmModuleFactory(module))

    solver.solve(make_request(tmp_path, show_window=True))

    assert _openfemm_args(module) == (0,)
```

- [ ] **Step 2: Run the test and verify RED**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/adapters/test_femm_solver.py -q`
Expected: FAIL with `TypeError: FemmSolveRequest.__init__() got an unexpected
keyword argument 'show_window'`.

- [ ] **Step 3: Add the field and honour it**

In `src/inductor_designer/application/ports/femm_solver.py`, extend the request:

```python
@dataclass(frozen=True, slots=True)
class FemmSolveRequest:
    """FEMM request whose problem circuits carry AC peak magnitude and phase."""

    problem: FemmProblem
    output_directory: Path
    project_name: str
    analyze: bool
    show_window: bool = False
```

In `src/inductor_designer/adapters/femm/solver.py`, replace the hardcoded call:

```python
            # pyfemm takes the *hide* flag: 1 hides the window, 0 shows it.
            femm.openfemm(0 if request.show_window else 1)
```

- [ ] **Step 4: Run the tests and verify GREEN**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/adapters tests/contract tests/unit/application -q`
Expected: all pass; the default `show_window=False` keeps every existing caller
— including `tests/contract/test_femm_solver_contract.py` — hidden.

- [ ] **Step 5: Run the gates and commit**

```bash
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m mypy src tools
.venv/Scripts/python.exe tools/check_architecture.py
git add src/inductor_designer/application/ports/femm_solver.py src/inductor_designer/adapters/femm/solver.py tests
git commit -m "feat(femm): allow a visible FEMM window per run"
```

---

### Task 4: `generate_run` gains visibility and project-relative artifacts

**Files:**
- Modify: `src/inductor_designer/application/services/maxwell_export.py`
- Test: `tests/unit/application/test_maxwell_export.py`

**Interfaces:**
- Consumes: Task 1 `artifact_path_for_manifest`, Task 3 `show_window`.
- Produces: `generate_run(..., show_solver_window: bool = False,
  artifact_base_directory: Path | None = None)`. The `non_graphical` parameter
  is removed; adapters keep their own `non_graphical` field.

Rules:

- `show_solver_window=False` (default) means `non_graphical=True` for both
  Maxwell adapters and `show_window=False` for FEMM.
- With `artifact_base_directory` set, every `ManifestArtifact.path` is relative
  to it. With it unset the previous absolute POSIX behaviour is kept, so the M6
  golden manifests in `tests/golden/` stay valid unchanged.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/application/test_maxwell_export.py`:

```python
def generate_one(
    backend: RunBackend,
    *,
    show_solver_window: bool = False,
    artifact_base_directory: Path | None = None,
    output_directory: Path = OUTPUT_DIRECTORY,
) -> tuple[RunOutcome, RecordingMaxwell3dExporter, RecordingMaxwell2dExporter, RecordingFemmSolver]:
    maxwell3d = RecordingMaxwell3dExporter()
    maxwell2d = RecordingMaxwell2dExporter()
    femm = RecordingFemmSolver()
    outcome = generate_run(
        project_for_runs(),
        RunRequest(backend, RunMode.GENERATE_ONLY),
        CATALOG,
        CAPABILITIES,
        output_directory,
        maxwell3d_exporter=maxwell3d,
        maxwell2d_exporter=maxwell2d,
        femm_solver=femm,
        run_id=f"m7b-{backend.value}",
        application_version="0.7.0-test",
        show_solver_window=show_solver_window,
        artifact_base_directory=artifact_base_directory,
    )
    return outcome, maxwell3d, maxwell2d, femm


def test_generation_is_non_graphical_by_default() -> None:
    _, maxwell3d, _, _ = generate_one(RunBackend.MAXWELL_3D)
    _, _, maxwell2d, _ = generate_one(RunBackend.MAXWELL_2D)
    _, _, _, femm = generate_one(RunBackend.FEMM)

    assert maxwell3d.requests[0].non_graphical is True
    assert maxwell2d.requests[0].non_graphical is True
    assert femm.requests[0].show_window is False


def test_a_visible_run_reaches_every_adapter() -> None:
    _, maxwell3d, _, _ = generate_one(RunBackend.MAXWELL_3D, show_solver_window=True)
    _, _, maxwell2d, _ = generate_one(RunBackend.MAXWELL_2D, show_solver_window=True)
    _, _, _, femm = generate_one(RunBackend.FEMM, show_solver_window=True)

    assert maxwell3d.requests[0].non_graphical is False
    assert maxwell2d.requests[0].non_graphical is False
    assert femm.requests[0].show_window is True


def test_artifact_paths_are_relative_to_the_given_base(tmp_path: Path) -> None:
    run_directory = tmp_path / "runs" / "20260730-101500-femm"
    run_directory.mkdir(parents=True)

    outcome, _, _, _ = generate_one(
        RunBackend.FEMM,
        artifact_base_directory=tmp_path,
        output_directory=run_directory,
    )

    assert [artifact.path for artifact in outcome.manifest.artifacts] == [
        "runs/20260730-101500-femm/Boost_inductor_2d.fem"
    ]


def test_without_a_base_the_artifact_path_is_unchanged() -> None:
    outcome, _, _, _ = generate_one(RunBackend.FEMM)

    assert outcome.manifest.artifacts[0].path.endswith("outputs/m6/Boost_inductor_2d.fem")
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/application/test_maxwell_export.py -q`
Expected: FAIL with `TypeError: generate_run() got an unexpected keyword
argument 'show_solver_window'`.

- [ ] **Step 3: Implement the parameters**

In `src/inductor_designer/application/services/maxwell_export.py`:

1. Import the helper:

```python
from inductor_designer.application.services.run_directory import (
    artifact_path_for_manifest,
)
```

2. Give the two evidence builders an artifact base. In `_maxwell_evidence`, add
   a keyword-only parameter and use it for the saved project:

```python
def _maxwell_evidence(
    result: MaxwellExportResult,
    expected_stage_names: tuple[str, ...],
    *,
    artifact_base_directory: Path | None,
) -> tuple[
    tuple[ManifestStage, ...],
    RunStatus,
    tuple[str, ...],
    tuple[ManifestArtifact, ...],
]:
```

   and replace the artifact construction with:

```python
    artifacts = (
        (
            ManifestArtifact(
                kind="aedt-project",
                path=_artifact_path(result.project_path, artifact_base_directory),
            ),
        )
        if saved
        else ()
    )
```

   Do the same in `_femm_evidence` for `result.fem_path` with
   `kind="femm-project"`, adding the same keyword-only parameter.

3. Add the shared helper next to them:

```python
def _artifact_path(path: Path, artifact_base_directory: Path | None) -> str:
    """Project-relative when a base is given (ADR 0007), absolute otherwise."""
    if artifact_base_directory is None:
        return path.as_posix()
    return artifact_path_for_manifest(path, artifact_base_directory)
```

4. Thread the base through `_manifest_for_result` — add
   `artifact_base_directory: Path | None` as a keyword-only parameter and pass
   it to both evidence builders.

5. In `generate_run`, replace `non_graphical: bool = True` with:

```python
    show_solver_window: bool = False,
    artifact_base_directory: Path | None = None,
```

   and inside the body compute `non_graphical = not show_solver_window` before
   the dispatch, passing it to `_export_maxwell3d_plan` and
   `_export_maxwell2d_plan` exactly as before, passing
   `show_solver_window=show_solver_window` to `_export_femm_plan`, and passing
   `artifact_base_directory=artifact_base_directory` to `_manifest_for_result`.

6. In `_export_femm_plan`, take `*, show_solver_window: bool` and build the
   request with `show_window=show_solver_window`.

- [ ] **Step 4: Run the tests and verify GREEN**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/application tests/unit/ui tests/unit/mcp_server tests/unit/tools -q`
Expected: all pass, including the unchanged M6 golden manifest comparison. Fix
the three `non_graphical=not args.graphical` / `non_graphical=...` call sites in
`tools/generate_maxwell3d.py`, `tools/generate_maxwell2d.py`, and
`src/inductor_designer/ui/generation_lines.py` by passing
`show_solver_window=args.graphical` (CLI) or dropping the argument (UI) — Tasks
6 and 8 rewrite those call sites properly.

- [ ] **Step 5: Run the gates and commit**

```bash
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m mypy src tools
.venv/Scripts/python.exe tools/check_architecture.py
git add src/inductor_designer/application/services/maxwell_export.py src/inductor_designer tools tests
git commit -m "feat(application): add solver-window visibility and relative artifact paths"
```

---

### Task 5: The one project-local run entry point

**Files:**
- Create: `src/inductor_designer/application/services/project_run.py`
- Test: `tests/unit/application/test_project_run.py`

**Interfaces:**
- Consumes: Tasks 1 and 4.
- Produces: `ProjectRunResult` (fields `location`, `outcome`, `manifest_path`),
  `ProjectRunFailed` (attributes `location`, `manifest`, `manifest_path`), and
  `start_project_run(project, project_document_path, request, catalog,
  capabilities, *, maxwell3d_exporter, maxwell2d_exporter, femm_solver,
  application_version, show_solver_window=False, now=None) -> ProjectRunResult`.

Behaviour:

- Allocate the run directory, run `generate_run` into it, write
  `run-manifest.json` into it, and return the location.
- A `RunGenerationFailed` keeps its directory and manifest and is re-raised as
  `ProjectRunFailed` — truthful evidence, never a success claim.
- Anything raised before an adapter wrote (`RunPlanningError`,
  `MaxwellExportBlocked`, and any other exception) discards the still-empty run
  directory and propagates unchanged.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/application/test_project_run.py`:

```python
from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from inductor_designer.application.services.maxwell_export import MaxwellExportBlocked
from inductor_designer.application.services.project_run import (
    ProjectRunFailed,
    ProjectRunResult,
    start_project_run,
)
from inductor_designer.application.services.run_planning import RunPlanningError
from inductor_designer.domain.project import InductorProject
from inductor_designer.simulation.run_contracts import (
    RunBackend,
    RunMode,
    RunRequest,
    RunStatus,
)
from tests.fakes.femm_solver import RecordingFemmSolver
from tests.fakes.maxwell2d_exporter import RecordingMaxwell2dExporter
from tests.fakes.maxwell_exporter import RecordingMaxwell3dExporter
from tests.unit.application.test_geometry_model import CATALOG
from tests.unit.application.test_maxwell_export import CAPABILITIES, project_for_runs

MOMENT = datetime(2026, 7, 30, 10, 15, 0, tzinfo=timezone.utc)


def saved_project(tmp_path: Path) -> Path:
    path = tmp_path / "boost.inductor.json"
    path.write_text("{}", encoding="utf-8")
    return path


def run(
    tmp_path: Path,
    backend: RunBackend = RunBackend.FEMM,
    *,
    project: InductorProject | None = None,
    show_solver_window: bool = False,
) -> ProjectRunResult:
    return start_project_run(
        project_for_runs() if project is None else project,
        saved_project(tmp_path),
        RunRequest(backend, RunMode.GENERATE_ONLY),
        CATALOG,
        CAPABILITIES,
        maxwell3d_exporter=RecordingMaxwell3dExporter(),
        maxwell2d_exporter=RecordingMaxwell2dExporter(),
        femm_solver=RecordingFemmSolver(),
        application_version="0.7.0-test",
        show_solver_window=show_solver_window,
        now=MOMENT,
    )


def test_a_run_writes_its_manifest_into_its_own_directory(tmp_path: Path) -> None:
    result = run(tmp_path)

    assert result.location.directory == tmp_path.resolve() / "runs" / "20260730-101500-femm"
    assert result.manifest_path == result.location.manifest_path
    document = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert document["runId"] == "20260730-101500"
    assert document["status"] == RunStatus.SUCCEEDED.value


def test_manifest_artifact_paths_are_project_relative(tmp_path: Path) -> None:
    result = run(tmp_path)

    document = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert [artifact["path"] for artifact in document["artifacts"]] == [
        "runs/20260730-101500-femm/Boost_inductor_2d.fem"
    ]


def test_a_second_run_never_overwrites_the_first(tmp_path: Path) -> None:
    first = run(tmp_path)
    second = run(tmp_path)

    assert first.location.directory != second.location.directory
    assert first.manifest_path.is_file()
    assert second.manifest_path.is_file()
    assert second.location.run_id == "20260730-101500-2"


def test_the_results_directory_is_reserved_and_empty(tmp_path: Path) -> None:
    result = run(tmp_path)

    assert result.location.results_directory.is_dir()
    assert list(result.location.results_directory.iterdir()) == []


def test_a_failed_run_keeps_its_directory_and_manifest(tmp_path: Path) -> None:
    class FailingFemmSolver(RecordingFemmSolver):
        def solve(self, request):  # type: ignore[no-untyped-def]
            raise RuntimeError("FEMM refused the problem")

    with pytest.raises(ProjectRunFailed) as failure:
        start_project_run(
            project_for_runs(),
            saved_project(tmp_path),
            RunRequest(RunBackend.FEMM, RunMode.GENERATE_ONLY),
            CATALOG,
            CAPABILITIES,
            maxwell3d_exporter=RecordingMaxwell3dExporter(),
            maxwell2d_exporter=RecordingMaxwell2dExporter(),
            femm_solver=FailingFemmSolver(),
            application_version="0.7.0-test",
            now=MOMENT,
        )

    error = failure.value
    assert error.manifest.status is RunStatus.FAILED
    document = json.loads(error.manifest_path.read_text(encoding="utf-8"))
    assert document["status"] == RunStatus.FAILED.value
    assert "FEMM refused the problem" in " ".join(document["diagnostics"])
    assert error.location.directory.is_dir()


def test_a_blocked_run_leaves_no_empty_directory_behind(tmp_path: Path) -> None:
    document_path = saved_project(tmp_path)

    with pytest.raises(MaxwellExportBlocked):
        start_project_run(
            project_for_runs(),
            document_path,
            RunRequest(RunBackend.FEMM, RunMode.GENERATE_AND_SOLVE),
            CATALOG,
            CAPABILITIES,
            maxwell3d_exporter=RecordingMaxwell3dExporter(),
            maxwell2d_exporter=RecordingMaxwell2dExporter(),
            femm_solver=RecordingFemmSolver(),
            application_version="0.7.0-test",
            now=MOMENT,
        )

    assert list((tmp_path / "runs").iterdir()) == []


def test_an_invalid_project_is_refused_without_creating_a_run(tmp_path: Path) -> None:
    project = project_for_runs()
    broken = replace(project, design=replace(project.design, windings=()))

    with pytest.raises(RunPlanningError):
        run(tmp_path, project=broken)

    assert list((tmp_path / "runs").iterdir()) == []


def test_an_unsaved_project_never_starts_a_run(tmp_path: Path) -> None:
    with pytest.raises(Exception, match="save the project"):
        start_project_run(
            project_for_runs(),
            tmp_path / "never-saved.inductor.json",
            RunRequest(RunBackend.FEMM, RunMode.GENERATE_ONLY),
            CATALOG,
            CAPABILITIES,
            maxwell3d_exporter=RecordingMaxwell3dExporter(),
            maxwell2d_exporter=RecordingMaxwell2dExporter(),
            femm_solver=RecordingFemmSolver(),
            application_version="0.7.0-test",
            now=MOMENT,
        )

    assert not (tmp_path / "runs").exists()
```

- [ ] **Step 2: Run the test and verify RED**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/application/test_project_run.py -q`
Expected: FAIL with `ModuleNotFoundError` for
`inductor_designer.application.services.project_run`.

- [ ] **Step 3: Implement the service**

Create `src/inductor_designer/application/services/project_run.py`:

```python
"""The one entry point for a project-local run (ADR 0007).

Every caller — Qt UI, MCP server, CLI tool — routes through this service so a
run always lands in its own directory beside the saved project document and
always leaves a truthful ``run-manifest.json`` there, successful or not.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from inductor_designer.application.ports.catalog import CatalogRepository
from inductor_designer.application.ports.femm_solver import FemmSolver
from inductor_designer.application.ports.maxwell2d_exporter import Maxwell2dExporter
from inductor_designer.application.ports.maxwell_exporter import Maxwell3dExporter
from inductor_designer.application.services.maxwell_export import (
    RunGenerationFailed,
    RunOutcome,
    generate_run,
    run_manifest_json,
)
from inductor_designer.application.services.run_directory import (
    RunLocation,
    allocate_run_directory,
    discard_empty_run_directory,
)
from inductor_designer.domain.project import InductorProject
from inductor_designer.simulation.capabilities import CapabilitySnapshot
from inductor_designer.simulation.run_contracts import RunManifest, RunRequest


@dataclass(frozen=True, slots=True)
class ProjectRunResult:
    location: RunLocation
    outcome: RunOutcome
    manifest_path: Path


class ProjectRunFailed(RuntimeError):
    """A run that reached an adapter and failed; its evidence is on disk."""

    def __init__(
        self,
        location: RunLocation,
        manifest: RunManifest,
        manifest_path: Path,
    ) -> None:
        self.location = location
        self.manifest = manifest
        self.manifest_path = manifest_path
        super().__init__("; ".join(manifest.diagnostics))


def _write_manifest(location: RunLocation, manifest: RunManifest) -> Path:
    location.manifest_path.write_text(run_manifest_json(manifest), encoding="utf-8")
    return location.manifest_path


def start_project_run(
    project: InductorProject,
    project_document_path: Path,
    request: RunRequest,
    catalog: CatalogRepository,
    capabilities: CapabilitySnapshot,
    *,
    maxwell3d_exporter: Maxwell3dExporter,
    maxwell2d_exporter: Maxwell2dExporter,
    femm_solver: FemmSolver,
    application_version: str,
    show_solver_window: bool = False,
    now: datetime | None = None,
) -> ProjectRunResult:
    """Run one backend into a new project-local run directory."""
    location = allocate_run_directory(project_document_path, request.backend, now=now)
    try:
        outcome = generate_run(
            project,
            request,
            catalog,
            capabilities,
            location.directory,
            maxwell3d_exporter=maxwell3d_exporter,
            maxwell2d_exporter=maxwell2d_exporter,
            femm_solver=femm_solver,
            run_id=location.run_id,
            application_version=application_version,
            show_solver_window=show_solver_window,
            artifact_base_directory=location.project_directory,
        )
    except RunGenerationFailed as failed:
        manifest_path = _write_manifest(location, failed.manifest)
        raise ProjectRunFailed(location, failed.manifest, manifest_path) from failed
    except Exception:
        # Blocked or invalid before any adapter wrote: leave no empty directory.
        discard_empty_run_directory(location)
        raise
    return ProjectRunResult(
        location=location,
        outcome=outcome,
        manifest_path=_write_manifest(location, outcome.manifest),
    )
```

- [ ] **Step 4: Run the test and verify GREEN**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/application/test_project_run.py -q`
Expected: `8 passed`.

- [ ] **Step 5: Run the gates and commit**

```bash
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m mypy src tools
.venv/Scripts/python.exe tools/check_architecture.py
git add src/inductor_designer/application/services/project_run.py tests/unit/application/test_project_run.py
git commit -m "feat(application): route every run through a project-local directory"
```

---

### Task 6: Qt UI generation uses the project directory

**Files:**
- Modify: `src/inductor_designer/ui/generation_lines.py`
- Modify: `src/inductor_designer/ui/generation_controller.py:60-70`
- Modify: `src/inductor_designer/ui/main.py:80-127`
- Test: `tests/unit/ui/test_generation_lines.py`
- Test: `tests/ui/test_generation_controller.py`

**Interfaces:**
- Consumes: Task 5 `start_project_run`, `ProjectRunFailed`.
- Produces: `run_generation(backend, project, project_document_path, catalog,
  capabilities, *, maxwell3d_exporter, maxwell2d_exporter, femm_solver,
  show_solver_window=False) -> GenerationResult`; `GenerationResult` gains
  `run_directory: Path | None = None` and `generated_file: Path | None = None`;
  `GenerationController` gains read-only `last_run_directory` and
  `last_generated_file` Python properties for M7c to bind.

The `artifacts/studio/<project-name>` output path disappears: runs go beside the
project document the UI already loaded.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/ui/test_generation_lines.py`:

```python
def test_generation_writes_into_the_project_run_directory(tmp_path: Path) -> None:
    document = tmp_path / "boost.inductor.json"
    document.write_text("{}", encoding="utf-8")

    result = run_generation(
        GenerationBackend.FEMM_2D,
        project_for_runs(),
        document,
        CATALOG,
        CAPABILITIES,
        maxwell3d_exporter=RecordingMaxwell3dExporter(),
        maxwell2d_exporter=RecordingMaxwell2dExporter(),
        femm_solver=RecordingFemmSolver(),
    )

    assert result.run_directory is not None
    assert result.run_directory.parent == tmp_path.resolve() / "runs"
    assert (result.run_directory / "run-manifest.json").is_file()
    assert result.generated_file is not None
    assert result.generated_file.suffix == ".fem"
    assert any("run folder" in line for line in result.lines)


def test_a_visible_run_is_requested_only_when_asked(tmp_path: Path) -> None:
    document = tmp_path / "boost.inductor.json"
    document.write_text("{}", encoding="utf-8")
    femm = RecordingFemmSolver()

    run_generation(
        GenerationBackend.FEMM_2D,
        project_for_runs(),
        document,
        CATALOG,
        CAPABILITIES,
        maxwell3d_exporter=RecordingMaxwell3dExporter(),
        maxwell2d_exporter=RecordingMaxwell2dExporter(),
        femm_solver=femm,
        show_solver_window=True,
    )

    assert femm.requests[0].show_window is True


def test_an_unsaved_project_reports_a_blocked_run(tmp_path: Path) -> None:
    result = run_generation(
        GenerationBackend.FEMM_2D,
        project_for_runs(),
        tmp_path / "never-saved.inductor.json",
        CATALOG,
        CAPABILITIES,
        maxwell3d_exporter=RecordingMaxwell3dExporter(),
        maxwell2d_exporter=RecordingMaxwell2dExporter(),
        femm_solver=RecordingFemmSolver(),
    )

    assert result.run_directory is None
    assert any("save the project" in line for line in result.lines)
```

Import `project_for_runs`, `CATALOG`, `CAPABILITIES`, and the three fakes the
same way `tests/unit/application/test_project_run.py` does. Update every
existing call in this file and in `tests/ui/test_generation_controller.py` to
the new signature — they currently pass an output directory.

- [ ] **Step 2: Run the tests and verify RED**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/ui/test_generation_lines.py -q`
Expected: FAIL — `run_generation()` does not accept a project document path.

- [ ] **Step 3: Rewrite the UI generation seam**

In `src/inductor_designer/ui/generation_lines.py`:

1. Replace the `generate_run` / `uuid4` imports with:

```python
from inductor_designer.application.services.project_run import (
    ProjectRunFailed,
    start_project_run,
)
```

   Keep the `MaxwellExportBlocked` and `RunPlanningError` imports; add
   `from inductor_designer.application.services.run_directory import RunDirectoryError`.

2. Extend the result:

```python
@dataclass(frozen=True, slots=True)
class GenerationResult(Sequence[str]):
    """UI display lines with optional immutable failed-run evidence."""

    lines: tuple[str, ...]
    failed_manifest: RunManifest | None = None
    run_directory: Path | None = None
    generated_file: Path | None = None
```

3. Replace the body of `run_generation`:

```python
def run_generation(
    backend: GenerationBackend,
    project: InductorProject,
    project_document_path: Path,
    catalog: CatalogRepository,
    capabilities: CapabilitySnapshot,
    *,
    maxwell3d_exporter: Maxwell3dExporter,
    maxwell2d_exporter: Maxwell2dExporter,
    femm_solver: FemmSolver,
    show_solver_window: bool = False,
) -> GenerationResult:
    """Run one backend into the project's run directory. Never raises."""
    try:
        result = start_project_run(
            project,
            project_document_path,
            RunRequest(_RUN_BACKENDS[backend], RunMode.GENERATE_ONLY),
            catalog,
            capabilities,
            maxwell3d_exporter=maxwell3d_exporter,
            maxwell2d_exporter=maxwell2d_exporter,
            femm_solver=femm_solver,
            application_version=__version__,
            show_solver_window=show_solver_window,
        )
        adapter_result = result.outcome.adapter_result
        lines: list[str] = []
        generated_file: Path | None = None
        if isinstance(adapter_result, MaxwellExportResult):
            generated_file = adapter_result.project_path
            lines.extend(_stage_lines(adapter_result.stages))
        elif isinstance(adapter_result, FemmSolveResult):
            generated_file = adapter_result.fem_path
            lines.append(f"fem: {adapter_result.fem_path}")
            for winding in result.outcome.manifest.windings:
                winding_result = (
                    adapter_result.results.get(winding.winding_id)
                    if adapter_result.results is not None
                    else None
                )
                if winding_result is None:
                    lines.append(f"{winding.winding_id}: not analyzed")
                else:
                    lines.append(
                        f"{winding.winding_id}: R={winding_result.resistance_ohm:g} ohm  "
                        f"L={winding_result.inductance_h:g} H"
                    )
        else:
            raise TypeError("Run generation returned an unknown adapter result.")
        lines.append(f"run folder: {result.location.directory}")
        return GenerationResult(
            tuple(lines),
            run_directory=result.location.directory,
            generated_file=generated_file,
        )
    except ProjectRunFailed as error:
        return GenerationResult(
            tuple(
                f"Generation failed: {diagnostic}"
                for diagnostic in error.manifest.diagnostics
            )
            + (f"run folder: {error.location.directory}",),
            failed_manifest=error.manifest,
            run_directory=error.location.directory,
        )
    except (MaxwellExportBlocked, RunPlanningError) as error:
        return GenerationResult(tuple(f"BLOCKED: {issue}" for issue in error.issues))
    except RunDirectoryError as error:
        return GenerationResult((f"BLOCKED: {error}",))
    except Exception as error:  # noqa: BLE001 - the UI must never crash from generation
        return GenerationResult((f"Generation failed: {error}",))
```

In `src/inductor_designer/ui/generation_controller.py`, store the last run
paths next to the failed manifest so M7c can bind them:

```python
    @property
    def last_run_directory(self) -> Path | None:
        return self._last_run_directory

    @property
    def last_generated_file(self) -> Path | None:
        return self._last_generated_file
```

Initialise both to `None` in `__init__`, reset them at the start of `generate`,
and set them from the `GenerationResult` in the worker alongside
`_failed_manifest`. Import `Path` under `TYPE_CHECKING` as the module already
does for its other types.

In `src/inductor_designer/ui/main.py`:

- give `_build_generation_controller` a `project_document_path: Path` parameter
  and pass `args.project` from the call site at line 191;
- delete the `output_directory` line and the now-unused `sanitize_identifier`
  import;
- pass `project_document_path` into `run_generation` inside `runner`.

- [ ] **Step 4: Run the tests and verify GREEN**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/ui tests/ui -q`
Expected: all pass, including the existing controller tests.

- [ ] **Step 5: Run the gates and commit**

```bash
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m mypy src tools
.venv/Scripts/python.exe tools/check_architecture.py
git add src/inductor_designer/ui tests/unit/ui tests/ui
git commit -m "feat(ui): generate into the project run directory"
```

---

### Task 7: MCP tools use the project directory

**Files:**
- Modify: `src/inductor_designer/mcp_server/tools.py:60-245`
- Modify: `src/inductor_designer/mcp_server/server.py` (only if `output_root` becomes unused)
- Test: `tests/unit/mcp_server/test_tools.py`
- Test: `tests/integration/test_mcp_session.py`

**Interfaces:**
- Consumes: Task 5 `start_project_run`, `ProjectRunFailed`.
- Produces: `generate_maxwell3d(context, path)` and `generate_2d(context, path,
  backend, analyze)` returning the manifest document plus a new `"runDirectory"`
  key; `read_manifest(context, path)` reading any `run-manifest.json`.

`_output_dir`, the duplicated `run-manifest.json` writes, and the `uuid4` run ids
all disappear — the service owns them now. `read_manifest` cannot keep its
`output_root` containment check, because manifests now live wherever the user's
project lives; it is replaced by a narrower rule that still refuses arbitrary
files: the path must be named `run-manifest.json` and sit directly inside a
`runs/<run-directory>/`. `test_read_manifest_traversal_attack_returns_error` is
replaced by the equivalent test for that rule.

- [ ] **Step 1: Write the failing tests**

The module already provides `context`, `document`, and `_save` fixtures/helpers.
Use them. Replace `test_read_manifest_roundtrip` and
`test_read_manifest_traversal_attack_returns_error`, and append the rest:

```python
def test_generate_maxwell3d_writes_into_the_project_run_directory(
    context: tools.ToolContext, document: dict[str, object], tmp_path: Path
) -> None:
    target = tmp_path / "saved.inductor.json"
    _save(context, document, target)

    result = tools.generate_maxwell3d(context, str(target))

    run_directory = Path(str(result["runDirectory"]))
    assert run_directory.parent == tmp_path.resolve() / "runs"
    assert run_directory.name.endswith("-maxwell-3d")
    assert run_directory.name == f"{result['runId']}-maxwell-3d"
    assert result["status"] == "succeeded"
    assert json.loads(
        (run_directory / "run-manifest.json").read_text(encoding="utf-8")
    )["runId"] == result["runId"]
    assert result["artifacts"][0]["path"].startswith("runs/")  # type: ignore[index]


def test_a_failed_generation_returns_the_manifest_and_its_run_directory(
    context: tools.ToolContext, document: dict[str, object], tmp_path: Path
) -> None:
    class _RaisingMaxwell3dExporter(RecordingMaxwell3dExporter):
        def export(self, request: object) -> object:  # type: ignore[override]
            raise RuntimeError("MCP Maxwell 3D adapter failed")

    broken_context = replace(context, maxwell3d_exporter=_RaisingMaxwell3dExporter())
    target = tmp_path / "saved.inductor.json"
    _save(broken_context, document, target)

    result = tools.generate_maxwell3d(broken_context, str(target))

    run_directory = Path(str(result["runDirectory"]))
    assert result["status"] == "failed"
    assert result["diagnostics"] == ["RuntimeError: MCP Maxwell 3D adapter failed"]
    assert result["issues"] == result["diagnostics"]
    assert json.loads(
        (run_directory / "run-manifest.json").read_text(encoding="utf-8")
    )["status"] == "failed"


def test_read_manifest_roundtrip(
    context: tools.ToolContext, document: dict[str, object], tmp_path: Path
) -> None:
    target = tmp_path / "saved.inductor.json"
    _save(context, document, target)
    generated = tools.generate_maxwell3d(context, str(target))
    manifest_path = Path(str(generated["runDirectory"])) / "run-manifest.json"

    result = tools.read_manifest(context, str(manifest_path))

    assert result["runId"] == generated["runId"]


def test_read_manifest_refuses_a_path_outside_a_run_directory(
    context: tools.ToolContext, tmp_path: Path
) -> None:
    stray = tmp_path / "run-manifest.json"
    stray.write_text("{}", encoding="utf-8")

    assert "error" in tools.read_manifest(context, str(stray))
    assert "error" in tools.read_manifest(context, "../../etc/passwd")
```

The two existing generate tests that assert
`context.output_root / "M2_golden_sample" / "run-manifest.json"`
(`test_generate_maxwell3d_returns_manifest_and_writes_evidence` and
`test_generate_2d_femm_failure_returns_and_writes_failed_manifest`, plus the
2D twins) must have that assertion replaced with the run-directory manifest
path; keep every other assertion in them unchanged.

- [ ] **Step 2: Run the tests and verify RED**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/mcp_server -q`
Expected: FAIL — `KeyError: 'runDirectory'`.

- [ ] **Step 3: Rewrite the two generate tools**

In `src/inductor_designer/mcp_server/tools.py`:

1. Replace the `generate_run` / `run_manifest_json` / `uuid4` /
   `sanitize_identifier` imports with:

```python
from inductor_designer.application.services.project_run import (
    ProjectRunFailed,
    start_project_run,
)
```

   and keep `json` for decoding what the service wrote.

2. Delete `_output_dir` and replace `_failed_run_result`:

```python
def _failed_run_result(error: ProjectRunFailed) -> dict[str, object]:
    """The service already wrote the manifest; report it verbatim."""
    result: dict[str, object] = dict(
        json.loads(error.manifest_path.read_text(encoding="utf-8"))
    )
    result["runDirectory"] = str(error.location.directory)
    result["error"] = str(error)
    result["issues"] = list(error.manifest.diagnostics)
    return result
```

3. Replace the body of `generate_maxwell3d`:

```python
def generate_maxwell3d(context: ToolContext, path: str) -> dict[str, object]:
    try:
        document_path = Path(path)
        project = ProjectRepository(context.schemas).load(document_path)
        capabilities = MatrixCapabilityRepository(context.matrix_path).snapshot_for(
            SUPPORTED_AEDT_RELEASE,
            SUPPORTED_AEDT_EDITION,
        )
        result = start_project_run(
            project,
            document_path,
            RunRequest(RunBackend.MAXWELL_3D, RunMode.GENERATE_ONLY),
            context.catalog,
            capabilities,
            maxwell3d_exporter=context.maxwell3d_exporter,
            maxwell2d_exporter=context.maxwell2d_exporter,
            femm_solver=context.femm_solver,
            application_version=__version__,
        )
    except ProjectRunFailed as error:
        return _failed_run_result(error)
    except Exception as error:
        return _failure(error)
    document: dict[str, object] = dict(
        json.loads(result.manifest_path.read_text(encoding="utf-8"))
    )
    document["runDirectory"] = str(result.location.directory)
    return document
```

   Apply the same shape to `generate_2d`, keeping its existing backend mapping
   and its `RunMode.GENERATE_AND_SOLVE` selection for FEMM with `analyze=True`
   unchanged — that mode is still blocked until M8 and must stay blocked.

4. Replace `read_manifest`:

```python
def read_manifest(context: ToolContext, path: str) -> dict[str, object]:
    """Read one run manifest. Only a manifest inside a run directory qualifies."""
    resolved = Path(path).resolve()
    if (
        resolved.name != MANIFEST_FILENAME
        or resolved.parent.parent.name != RUNS_DIRECTORY_NAME
    ):
        return _failure(
            ValueError(f"Not a run manifest inside a run directory: {path!r}")
        )
    try:
        document = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception as error:
        return _failure(error)
    return dict(document)
```

   importing `MANIFEST_FILENAME` and `RUNS_DIRECTORY_NAME` from
   `inductor_designer.application.services.run_directory`.

5. Run `grep -rn "output_root" src tests`. If nothing outside `ToolContext` uses
   it, delete the field and its wiring in `src/inductor_designer/mcp_server/server.py`
   and in every test that builds a `ToolContext`.

- [ ] **Step 4: Run the tests and verify GREEN**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/mcp_server tests/integration/test_mcp_session.py -q`
Expected: all pass.

- [ ] **Step 5: Run the gates and commit**

```bash
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m mypy src tools
.venv/Scripts/python.exe tools/check_architecture.py
git add src/inductor_designer/mcp_server tests
git commit -m "feat(mcp): generate into project-local run directories"
```

---

### Task 8: CLI tools and PowerShell scripts

**Files:**
- Modify: `tools/generate_maxwell3d.py`
- Modify: `tools/generate_maxwell2d.py`
- Modify: `tools/run_aedt_maxwell3d.ps1`
- Modify: `tools/run_aedt_maxwell2d.ps1`
- Test: `tests/unit/tools/test_generate_maxwell3d.py`
- Test: `tests/unit/tools/test_generate_maxwell2d.py`

**Interfaces:**
- Consumes: Task 5 `start_project_run`, `ProjectRunFailed`.
- Produces: `--work-directory` replaces `--output-directory` in both CLI tools.
  It holds the built `catalog.sqlite` only; the run itself lands beside
  `--project`. `--evidence` keeps writing its manifest copy.

The PowerShell scripts copy the fixture project into the artifacts workspace
first, so live AEDT runs never write `runs/` into the tracked
`tests/fixtures/` directory.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/tools/test_generate_maxwell3d.py`:

```python
def test_the_run_lands_beside_the_project_document(tmp_path: Path) -> None:
    project_directory = tmp_path / "project"
    project_directory.mkdir()
    project_path = project_directory / "sample.inductor.json"
    project_path.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    work_directory = tmp_path / "work"
    evidence = work_directory / "generation-manifest.json"

    exit_code = main(
        [
            "--project",
            str(project_path),
            "--work-directory",
            str(work_directory),
            "--evidence",
            str(evidence),
        ],
        exporter=RecordingMaxwell3dExporter(),
    )

    assert exit_code == 0
    runs = sorted((project_directory / "runs").iterdir())
    assert len(runs) == 1
    assert runs[0].name.endswith("-maxwell-3d")
    assert (runs[0] / "run-manifest.json").is_file()
    assert evidence.is_file()
    assert not (work_directory / "runs").exists()
```

Reuse the module's existing `FIXTURE` constant and its recording exporter; if
the module builds its own stub exporter, keep using that one rather than adding
another. Mirror the same test in `tests/unit/tools/test_generate_maxwell2d.py`
with `-maxwell-2d`.

- [ ] **Step 2: Run the test and verify RED**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/tools -q`
Expected: FAIL — `unrecognized arguments: --work-directory`.

- [ ] **Step 3: Rewrite both CLI tools**

In `tools/generate_maxwell3d.py` (and the same edits in
`tools/generate_maxwell2d.py`, keeping its backend and `--graphical` handling):

```python
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument(
        "--work-directory",
        type=Path,
        required=True,
        help="Workspace for the built catalog index; the run itself is written "
        "beside --project in <project-directory>/runs/.",
    )
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--graphical", action="store_true")
```

```python
    args.work_directory.mkdir(parents=True, exist_ok=True)
    index = args.work_directory / "catalog.sqlite"
```

```python
    try:
        result = start_project_run(
            project,
            args.project,
            RunRequest(RunBackend.MAXWELL_3D, RunMode.GENERATE_ONLY),
            catalog,
            capabilities,
            maxwell3d_exporter=(
                exporter if exporter is not None else PyaedtMaxwell3dExporter()
            ),
            maxwell2d_exporter=PyaedtMaxwell2dExporter(),
            femm_solver=PyfemmSolver(),
            application_version=__version__,
            show_solver_window=args.graphical,
        )
    except ProjectRunFailed as failed:
        args.evidence.parent.mkdir(parents=True, exist_ok=True)
        args.evidence.write_text(
            failed.manifest_path.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        print(f"Run folder: {failed.location.directory}", file=sys.stderr)
        for diagnostic in failed.manifest.diagnostics:
            print(f"FAILED: {diagnostic}", file=sys.stderr)
        return 1
    except (MaxwellExportBlocked, RunPlanningError) as blocked:
        for issue in blocked.issues:
            print(f"BLOCKED: {issue}", file=sys.stderr)
        return 1

    args.evidence.parent.mkdir(parents=True, exist_ok=True)
    args.evidence.write_text(
        result.manifest_path.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    print(f"Run folder: {result.location.directory}")
    adapter_result = result.outcome.adapter_result
```

Keep the remaining stage printing and the `succeeded(STAGE_NAMES)` return value
exactly as they are, renaming the local variable to `adapter_result`. Replace
the `generate_run` / `run_manifest_json` / `uuid4` imports with
`from inductor_designer.application.services.project_run import (ProjectRunFailed,
start_project_run)`. Also catch `RunDirectoryError` alongside the blocked
errors so an unsaved project prints `BLOCKED: ...` instead of a traceback.

In `tools/run_aedt_maxwell3d.ps1` (and the 2D twin), replace the argument block:

```powershell
$workDirectory = Join-Path $repoRoot "artifacts\maxwell3d\$Release-$Edition"
New-Item -ItemType Directory -Force -Path $workDirectory | Out-Null
$projectCopy = Join-Path $workDirectory (Split-Path -Leaf $Project)
Copy-Item -Path $Project -Destination $projectCopy -Force
$evidence = Join-Path $workDirectory 'generation-manifest.json'

$arguments = @(
    '-m', 'tools.generate_maxwell3d',
    '--project', $projectCopy,
    '--work-directory', $workDirectory,
    '--evidence', $evidence
)
```

- [ ] **Step 4: Run the tests and verify GREEN**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/tools -q`
Expected: all pass.

- [ ] **Step 5: Run the gates and commit**

```bash
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m mypy src tools
.venv/Scripts/python.exe tools/check_architecture.py
git add tools tests/unit/tools
git commit -m "feat(tools): write CLI runs into the project run directory"
```

---

### Task 9: Open the generated file or the run folder

**Files:**
- Create: `src/inductor_designer/application/ports/path_opener.py`
- Create: `src/inductor_designer/adapters/system/__init__.py`
- Create: `src/inductor_designer/adapters/system/path_opener.py`
- Test: `tests/unit/adapters/system/test_path_opener.py`

**Interfaces:**
- Produces: `PathOpener` Protocol with `open_path(path: Path) -> None`, and
  `DesktopPathOpener(launcher: Callable[[str], None] | None = None)` implementing
  it. M7c binds the Review screen's `Open generated file` and `Open run folder`
  buttons to this port using the paths Task 6 exposes.

The adapter is Windows-only by ADR 0004; the injectable `launcher` keeps the
tests platform-independent so the Linux CI job passes.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/adapters/system/test_path_opener.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from inductor_designer.adapters.system.path_opener import DesktopPathOpener


def test_opening_a_file_hands_it_to_the_shell(tmp_path: Path) -> None:
    opened: list[str] = []
    target = tmp_path / "Boost.aedt"
    target.write_text("project", encoding="utf-8")

    DesktopPathOpener(launcher=opened.append).open_path(target)

    assert opened == [str(target)]


def test_opening_a_folder_hands_it_to_the_shell(tmp_path: Path) -> None:
    opened: list[str] = []

    DesktopPathOpener(launcher=opened.append).open_path(tmp_path)

    assert opened == [str(tmp_path)]


def test_a_missing_path_is_refused_before_the_shell_is_called(tmp_path: Path) -> None:
    opened: list[str] = []

    with pytest.raises(FileNotFoundError, match="does not exist"):
        DesktopPathOpener(launcher=opened.append).open_path(tmp_path / "gone.aedt")

    assert opened == []
```

Create `tests/unit/adapters/system/__init__.py` (empty) so the package matches
the rest of the test tree.

- [ ] **Step 2: Run the test and verify RED**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/adapters/system -q`
Expected: FAIL with `ModuleNotFoundError` for
`inductor_designer.adapters.system.path_opener`.

- [ ] **Step 3: Implement the port and adapter**

Create `src/inductor_designer/application/ports/path_opener.py`:

```python
"""Port for opening a generated solver project or its run folder (ADR 0007)."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class PathOpener(Protocol):
    def open_path(self, path: Path) -> None: ...
```

Create `src/inductor_designer/adapters/system/__init__.py` (empty) and
`src/inductor_designer/adapters/system/path_opener.py`:

```python
"""Hand a file or folder to the Windows shell (ADR 0004, ADR 0007).

The generated solver project is an independent, user-owned output: opening it
never imports, synchronizes, or compares anything back into the project
document.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from pathlib import Path


def _shell_launcher() -> Callable[[str], None]:
    if sys.platform != "win32":
        raise RuntimeError(
            "Opening a path from the application is supported on Windows only."
        )
    return os.startfile


class DesktopPathOpener:
    """Port adapter; `launcher` is injectable so tests never touch the shell."""

    def __init__(self, launcher: Callable[[str], None] | None = None) -> None:
        self._launcher = launcher

    def open_path(self, path: Path) -> None:
        if not path.exists():
            raise FileNotFoundError(f"Cannot open {path}: it does not exist.")
        launcher = self._launcher if self._launcher is not None else _shell_launcher()
        launcher(str(path))
```

- [ ] **Step 4: Run the test and verify GREEN**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/adapters/system -q`
Expected: `3 passed`.

- [ ] **Step 5: Run the gates and commit**

```bash
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m mypy src tools
.venv/Scripts/python.exe tools/check_architecture.py
git add src/inductor_designer/application/ports/path_opener.py src/inductor_designer/adapters/system tests/unit/adapters/system
git commit -m "feat(adapters): open a generated file or run folder in the shell"
```

---

### Task 10: Documentation and whole-branch verification

**Files:**
- Modify: `docs/development/ROADMAP.md` (the M7b paragraph at lines 589-596)
- Modify: `docs/development/automation-mcp-femm.md`
- Modify: `docs/superpowers/plans/README.md`
- Modify: `README.md` (only the run/output instructions that name `artifacts/`)

**Interfaces:**
- Consumes: everything above. Produces no code.

- [ ] **Step 1: Update the roadmap**

Replace the "remaining M7 work is unstarted" paragraph with an M7b section that
records what shipped: project-local `runs/<run-id>-<backend>/` directories,
non-overwriting run ids with same-second suffixes, `run-manifest.json` written
by the application for successful and failed runs, project-relative artifact
paths, background-by-default generation with an opt-in visible solver window for
all three backends, and the `PathOpener` port. State plainly that M7c still owns
every Guided Studio screen, including the `Show solver window` control and the
`Open generated file` / `Open run folder` buttons, and that M8 owns `results/`.

- [ ] **Step 2: Update the other documents**

- `docs/development/automation-mcp-femm.md`: the MCP generate tools now write
  into the project's `runs/` directory and return `runDirectory`;
  `read_manifest` takes the path of a `run-manifest.json`.
- `docs/superpowers/plans/README.md`: add this plan to the index next to M7a.
- `README.md`: replace any `--output-directory` usage with `--work-directory`
  and say that generated projects land in `<project-directory>/runs/`.

- [ ] **Step 3: Run every gate on the whole branch**

```bash
.venv/Scripts/python.exe -m pytest tests -q -m "not aedt and not femm"
.venv/Scripts/python.exe -m pytest tests/ui -q
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m mypy src tools
.venv/Scripts/python.exe tools/check_architecture.py
git diff --check
```

Record the real counts you observe; do not copy numbers from an earlier
milestone. Then confirm no run directory leaked into the working tree:

```bash
git status --porcelain
```

Expected: no `runs/` entry anywhere under `tests/fixtures/`.

- [ ] **Step 4: Commit**

```bash
git add docs README.md
git commit -m "docs: record M7b project-local run artifacts"
```

---

## Acceptance evidence for Fabio

Automated gates cannot prove the Windows and AEDT behaviour. Before accepting
M7b, run on your machine:

1. `tools\run_aedt_maxwell3d.ps1 -Release 2025.2 -Edition commercial` — confirm
   the run directory appears under
   `artifacts\maxwell3d\2025.2-commercial\runs\<timestamp>-maxwell-3d\`, holds
   `run-manifest.json` plus the `.aedt` project and an empty `results\`, and that
   the manifest's `artifacts[].path` is relative (`runs/...`).
2. The same script a second time — confirm the first run directory is untouched
   and the second gets its own.
3. The same script with `-Graphical` — confirm the AEDT window is visible and the
   run still succeeds.
4. `.venv\Scripts\python.exe -m pytest tests -q -m "aedt"` and `-m "femm"` — the
   live suites still pass.
