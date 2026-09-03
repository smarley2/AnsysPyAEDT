# Blank Project On Launch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A launch with no `--project` opens a blank unsaved project, so every screen — the Core & Material core list above all — is live, and `File > New`/`File > Open`/`File > Save As` work from the shortcut.

**Architecture:** `main()` stops branching on "is there a project": it always builds a `ProjectSession`, holding either the loaded document or `new_project()` with `document_path = None`. Only the file-bound work (argument checks, lock, load, run reconciliation) stays behind `if args.project is not None`. `ProjectSession` gains `newProject()`, mirroring `openProject` minus the file. `GuidedStudioController` stops raising on a project with no geometry.

**Tech Stack:** Python 3.13, PySide6 (QtQml/QtQuick), pytest + pytest-xdist, ruff, mypy strict, `tools.check_architecture`.

## Global Constraints

- English for code, comments, docs, UI copy, logs, branches, commits.
- `domain`, `geometry`, `materials`, `simulation` and solver-independent recipes import no PyAEDT, Qt, SQLite or OS APIs. `application` additionally imports no `inductor_designer.adapters`.
- Never change a physical assumption, schema, catalog value, unit or source reference silently.
- Tests come before the implementation they cover.
- Verification per task: `.venv/Scripts/python.exe -m pytest -q <the task's test files>`. Final gate: `ruff check .`, `mypy src tools`, `python -m tools.check_architecture`, and `pytest -q -n 8 -m "not aedt and not femm"`.
- Never run tests marked `aedt` or `femm`; never start an AEDT session.
- Spec: `docs/superpowers/specs/2026-09-03-blank-project-on-launch-design.md`.

---

## File Structure

- Create `src/inductor_designer/application/services/new_project.py` — the blank-project factory, pure, domain imports only.
- Create `tests/unit/application/test_new_project.py` — the factory's defaults and their schema validity.
- Modify `src/inductor_designer/ui/guided_studio_controller.py` (constructor, ~line 80) — tolerate a project with no geometry.
- Modify `src/inductor_designer/ui/project_session.py` — `newProject()` slot; `_adopt_loaded_project` takes `Path | None`.
- Modify `src/inductor_designer/ui/main.py` (~lines 376-560) — always build the session.
- Modify `src/inductor_designer/ui/qml/Main.qml` — `File > New`; `File > Save` routes to Save As when there is no document path.
- Modify `tests/ui/test_app_menu.py`, `tests/ui/test_project_session.py`, `tests/ui/test_guided_studio_controller.py` — the behaviour tests.
- Modify `packaging/release_notes.md` — the "No sample project is shipped" section documents a flow that cannot be performed.

---

### Task 1: The blank-project factory

**Files:**
- Create: `src/inductor_designer/application/services/new_project.py`
- Test: `tests/unit/application/test_new_project.py`

**Interfaces:**
- Consumes: `inductor_designer.domain.project`, `inductor_designer.domain.winding`.
- Produces: `new_project() -> InductorProject`, and the module constant `BLANK_CONDUCTOR_NAME: str = "AWG 18"`.

- [ ] **Step 1: Write the failing test**

```python
"""The project a launch with no `--project` opens (spec 2026-09-03).

Every value here is either an existing convention in this repository or an
inert placeholder, and each is asserted rather than described: a default
nobody notices is how an invented physical assumption ships.
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from inductor_designer.adapters.persistence.project_repository import ProjectRepository
from inductor_designer.adapters.persistence.schema_repository import SchemaRepository
from inductor_designer.application.services.new_project import (
    BLANK_CONDUCTOR_NAME,
    new_project,
)
from inductor_designer.domain.winding import (
    ConductorMode,
    CurrentDirection,
    WindingDirection,
)

ROOT = Path(__file__).resolve().parents[3]


def test_the_blank_project_has_no_core_and_no_material() -> None:
    project = new_project()
    assert project.design.core is None
    assert project.design.core_material is None
    assert project.design.manual_material_compatibility_acknowledged is False


def test_the_blank_project_carries_exactly_one_winding() -> None:
    """Not zero: `GuidedStudioController.addWinding` copies the last winding
    and refuses when there are none, so a zero-winding project could never
    grow its first one."""
    project = new_project()
    (winding,) = project.design.windings
    assert winding.winding_id == "w1"
    assert winding.turns == 1
    assert winding.conductor_name == BLANK_CONDUCTOR_NAME
    assert winding.mode is ConductorMode.SOLID
    assert winding.start_angle_deg == 0.0
    assert winding.sector_deg == 360.0
    assert winding.min_spacing_m == 0.0002
    assert winding.min_clearance_m == 0.001
    assert winding.winding_direction is WindingDirection.CLOCKWISE

    (excitation,) = project.operating_point.windings
    assert excitation.winding_id == winding.winding_id
    assert excitation.ac_rms_current_a == 0.0
    assert excitation.dc_current_a == 0.0
    assert excitation.current_direction is CurrentDirection.FORWARD


def test_the_blank_operating_point_and_recipe_match_the_repository_defaults() -> None:
    project = new_project()
    assert project.operating_point.frequency_hz == 100_000.0
    assert project.operating_point.winding_temperature_c == 20.0
    assert project.operating_point.core_temperature_c == 25.0
    assert project.simulation_recipe.maximum_passes == 10
    assert project.simulation_recipe.percent_error == 1.0
    assert [output.value for output in project.simulation_recipe.requested_outputs] == [
        "resistance",
        "inductance",
    ]


def test_each_blank_project_gets_its_own_dashed_uuid() -> None:
    """`schemas/project/v5.schema.json` declares `projectId` as `format: uuid`,
    which `uuid4().hex` does not satisfy -- a blank project carrying one could
    never be saved, and saving is the only thing a blank project is for."""
    first, second = new_project(), new_project()
    assert str(UUID(first.project_id)) == first.project_id
    assert first.project_id != second.project_id


def test_the_blank_project_round_trips_through_the_real_schema(tmp_path: Path) -> None:
    repository = ProjectRepository(SchemaRepository(ROOT / "schemas"))
    target = tmp_path / "blank.inductor.json"
    repository.save(new_project(), target)
    assert repository.load(target).design.core is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest -q tests/unit/application/test_new_project.py`
Expected: collection error — `ModuleNotFoundError: No module named 'inductor_designer.application.services.new_project'`

- [ ] **Step 3: Write minimal implementation**

```python
"""The project a launch with no `--project` opens (spec 2026-09-03).

Pure: domain types and `uuid` only, no catalog, filesystem or Qt. The
defaults are product policy, so they live in the application layer beside the
other services rather than in `domain`, which stays descriptive.
"""

from __future__ import annotations

from uuid import uuid4

from inductor_designer.domain.project import (
    Design,
    InductorProject,
    MeshIntent,
    OperatingPoint,
    RequestedOutput,
    SimulationRecipe,
    WindingOperatingPoint,
)
from inductor_designer.domain.winding import (
    ConductorMode,
    CurrentDirection,
    WindingDefinition,
    WindingDirection,
)

#: Pinned rather than read from the catalog, so the default never shifts when
#: a conductor is added to the index. The gauge this repository's own fixtures
#: wind with; `tests/unit/application/test_new_project.py` pins that the built
#: index actually carries it.
BLANK_CONDUCTOR_NAME = "AWG 18"


def new_project() -> InductorProject:
    """A blank, unsaved project: no core, one winding, nothing excited.

    No core, because selecting one is the user's first act and a preselected
    core reads as a recommendation nobody made. One winding rather than none,
    because `GuidedStudioController.addWinding` grows the list by copying its
    last entry and refuses when there is nothing to copy.
    """
    winding = WindingDefinition(
        winding_id="w1",
        label="Winding 1",
        turns=1,
        conductor_name=BLANK_CONDUCTOR_NAME,
        mode=ConductorMode.SOLID,
        start_angle_deg=0.0,
        # A single winding around the whole toroid. `addWinding` then refuses a
        # second winding until this sector is reduced, and says so.
        sector_deg=360.0,
        min_spacing_m=0.0002,
        min_clearance_m=0.001,
        winding_direction=WindingDirection.CLOCKWISE,
        terminal_intent="",
    )
    return InductorProject(
        # Dashed: `schemas/project/v5.schema.json` declares `projectId` as
        # `format: uuid`, which rejects `uuid4().hex`.
        project_id=str(uuid4()),
        name="Untitled inductor",
        description="",
        design=Design(
            core=None,
            windings=(winding,),
            core_material=None,
            manual_material_compatibility_acknowledged=False,
        ),
        # 100 kHz and the two temperatures are this repository's existing
        # defaults (`tests/unit/domain/test_project.py`'s `make_operating_point`
        # and `OperatingPoint`'s own field defaults), not a new physical
        # assumption introduced here.
        operating_point=OperatingPoint(
            frequency_hz=100_000.0,
            windings=(
                WindingOperatingPoint(
                    winding_id=winding.winding_id,
                    ac_rms_current_a=0.0,
                    ac_phase_deg=0.0,
                    dc_current_a=0.0,
                    current_direction=CurrentDirection.FORWARD,
                ),
            ),
        ),
        simulation_recipe=SimulationRecipe(
            mesh_intent=MeshIntent.STANDARD,
            maximum_passes=10,
            percent_error=1.0,
            requested_outputs=(
                RequestedOutput.RESISTANCE,
                RequestedOutput.INDUCTANCE,
            ),
        ),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest -q tests/unit/application/test_new_project.py`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/inductor_designer/application/services/new_project.py tests/unit/application/test_new_project.py
git commit -m "feat(application): add the blank project a launch with no document opens"
```

---

### Task 2: The pinned conductor must exist in the built catalog

**Files:**
- Test: `tests/unit/application/test_new_project.py` (append)

**Interfaces:**
- Consumes: `BLANK_CONDUCTOR_NAME` from Task 1, `SqliteCatalogRepository`, `tools.build_catalog.build`.
- Produces: nothing.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/application/test_new_project.py`:

```python
def test_the_pinned_conductor_exists_in_the_built_catalog(
    tmp_path: Path,
) -> None:
    """A pinned gauge is only safe while the shipped index carries it. Without
    this, dropping `AWG 18` from `catalog/conductors/round-wire.yaml` would
    leave the Windings screen on first launch naming a conductor no lookup can
    resolve, and every other test would stay green."""
    from inductor_designer.adapters.catalog.sqlite_repository import (
        SqliteCatalogRepository,
    )
    from tools.build_catalog import build

    index = tmp_path / "catalog.sqlite"
    build(ROOT / "catalog", ROOT / "schemas" / "catalog", index)
    assert BLANK_CONDUCTOR_NAME in SqliteCatalogRepository(index).list_conductor_names()
```

- [ ] **Step 2: Run test to verify it passes for the right reason**

Run: `.venv/Scripts/python.exe -m pytest -q tests/unit/application/test_new_project.py::test_the_pinned_conductor_exists_in_the_built_catalog`
Expected: PASS. Then prove it can fail: temporarily change `BLANK_CONDUCTOR_NAME` to `"AWG 999"` in `new_project.py`, rerun, expect FAIL, and restore.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/application/test_new_project.py
git commit -m "test(application): pin that the blank project's conductor is in the catalog"
```

---

### Task 3: Guided Studio tolerates a project with no geometry

**Files:**
- Modify: `src/inductor_designer/ui/guided_studio_controller.py:77-87`
- Test: `tests/ui/test_guided_studio_controller.py` (append)

**Interfaces:**
- Consumes: `new_project()` from Task 1.
- Produces: a `GuidedStudioController` whose constructor never raises `GeometryModelError`; `previewEntries == []` and `cutPlaneDrawing["note"]` non-empty for a coreless project.

- [ ] **Step 1: Write the failing test**

Append to `tests/ui/test_guided_studio_controller.py`:

```python
def test_a_project_with_no_core_yet_does_not_break_the_controller() -> None:
    """`__init__` used to call `_build_preview` unguarded, and
    `build_geometry_model` refuses a coreless project ("Project has no core
    selection; geometry needs one."). A blank project therefore raised
    `GeometryModelError` out of the constructor and took the whole launch with
    it -- `refresh()` had this tolerance already, the constructor did not.
    """
    from inductor_designer.application.services.new_project import new_project

    session = ProjectSession(new_project(), None)
    controller = GuidedStudioController(session, CATALOG)

    assert controller.previewEntries == []
    assert controller.cutPlaneDrawing["note"] != ""
    assert controller.windings[0]["turns"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest -q "tests/ui/test_guided_studio_controller.py::test_a_project_with_no_core_yet_does_not_break_the_controller"`
Expected: FAIL with `GeometryModelError: Project has no core selection; geometry needs one.`

- [ ] **Step 3: Write minimal implementation**

In `guided_studio_controller.py`, replace the constructor's unguarded preview build:

```python
        self._preview = self._build_preview(project)
```

with:

```python
        # A project with no core yet -- the blank project a launch with no
        # `--project` opens -- has no geometry to draw, and
        # `build_geometry_model` refuses it rather than inventing one. That is
        # not a startup failure: it is the state the user is about to fix on
        # the Core & Material screen. `refresh()` already suppresses exactly
        # this error for the same reason; without the same tolerance here the
        # constructor raised and took the launch with it.
        self._preview = self._empty_preview()
        with contextlib.suppress(GeometryModelError):
            self._preview = self._build_preview(project)
```

and add, next to `_build_preview`:

```python
    def _empty_preview(self) -> _PreviewState:
        """No geometry to show, and the reason, on the cut plane itself.

        The numbers match the defaults `CutPlaneView.qml` carries for its own
        unset state, so an empty drawing renders exactly as no drawing does.
        """
        return _PreviewState(
            entries=[],
            drawing=CutPlaneDrawing(
                r_inner_mm=0.0,
                r_outer_mm=0.0,
                depth_mm=0.0,
                extent_mm=1.0,
                circles=(),
                starts=(),
                note="Select a core to see the winding cross-section.",
            ),
        )
```

Add the imports the file needs if they are absent: `import contextlib` and `CutPlaneDrawing` from `inductor_designer.ui.cut_plane_view` (`GeometryModelError` is already imported for `refresh()`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest -q tests/ui/test_guided_studio_controller.py tests/ui/test_cut_plane_qml.py`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add src/inductor_designer/ui/guided_studio_controller.py tests/ui/test_guided_studio_controller.py
git commit -m "fix(ui): stop a project with no core from breaking the studio constructor"
```

---

### Task 4: `ProjectSession.newProject()`

**Files:**
- Modify: `src/inductor_designer/ui/project_session.py` (`_adopt_loaded_project`, and a new slot beside `openProject`)
- Test: `tests/ui/test_project_session.py` (append)

**Interfaces:**
- Consumes: `new_project()` from Task 1.
- Produces: `ProjectSession.newProject() -> bool` (a `@Slot(result=bool)`), and `_adopt_loaded_project(path: Path | None, project: InductorProject) -> None`.

- [ ] **Step 1: Write the failing test**

Append to `tests/ui/test_project_session.py`:

```python
def test_new_project_replaces_the_document_with_a_blank_unsaved_one(
    tmp_path: Path,
) -> None:
    """File > New has to leave the session in the same state a launch with no
    `--project` produces -- including not dirty, or the Exit guard nags about
    unsaved changes the user never made."""
    document = tmp_path / "boost.inductor.json"
    document.write_text("{}", encoding="utf-8")
    session = ProjectSession(make_project(), document)
    session.apply(replace(session.project, description="edited"))
    assert session.canUndo is True
    assert session.dirty is True

    assert session.newProject() is True

    assert session.document_path is None
    assert session.documentPath == ""
    assert session.project.design.core is None
    assert session.project.design.windings[0].turns == 1
    assert session.canUndo is False
    assert session.canRedo is False
    assert session.dirty is False


def test_new_project_releases_the_previous_document_lock(tmp_path: Path) -> None:
    """The previous document stays claimed otherwise: a second window could
    not open the file this session no longer has."""
    document = tmp_path / "boost.inductor.json"
    document.write_text("{}", encoding="utf-8")
    lock = ProjectLock(document)
    assert lock.acquire() is LockOutcome.ACQUIRED
    session = ProjectSession(make_project(), document, lock=lock)

    assert session.newProject() is True

    second = ProjectLock(document)
    assert second.acquire() is LockOutcome.ACQUIRED
    second.release()
```

Use the imports the file already has for `ProjectLock`/`LockOutcome`; add them if absent:

```python
from inductor_designer.adapters.system.project_lock import LockOutcome, ProjectLock
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest -q tests/ui/test_project_session.py -k new_project`
Expected: FAIL with `AttributeError: 'ProjectSession' object has no attribute 'newProject'`

- [ ] **Step 3: Write minimal implementation**

Widen `_adopt_loaded_project`'s signature and guard the run reconciliation:

```python
    def _adopt_loaded_project(
        self, path: Path | None, project: InductorProject
    ) -> None:
```

and inside it, replace

```python
        if self._is_run_busy is None or not self._is_run_busy():
            with contextlib.suppress(OSError):
                reconcile_unfinished_runs(path)
```

with

```python
        # `path is None` is File > New and the blank project a launch with no
        # `--project` opens: there is no document, so there is no `runs/`
        # directory beside one to reconcile.
        if path is not None and (self._is_run_busy is None or not self._is_run_busy()):
            with contextlib.suppress(OSError):
                reconcile_unfinished_runs(path)
```

Add the slot after `openProject`:

```python
    @Slot(result=bool)
    def newProject(self) -> bool:
        """Replace the project with a blank unsaved one, in place.

        Same swap-what-is-inside idiom as `openProject`: every controller holds
        this session rather than the project it wraps, so nothing has to be
        rebuilt. The blank project is adopted as its own saved state, which is
        what keeps an untouched new project from reporting unsaved changes --
        `dirty` is a comparison against `_saved_project`, not a flag.
        """
        previous_lock = self._lock
        self._lock = None
        self._adopt_loaded_project(None, new_project())
        self.documentPathChanged.emit()
        if previous_lock is not None:
            previous_lock.release()
        _logger.info("Started a new project.")
        self.set_status("New project")
        return True
```

with the import at the top of the file:

```python
from inductor_designer.application.services.new_project import new_project
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest -q tests/ui/test_project_session.py tests/ui/test_project_session_undo.py tests/ui/test_project_lock_wiring.py tests/ui/test_autosave.py`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add src/inductor_designer/ui/project_session.py tests/ui/test_project_session.py
git commit -m "feat(ui): let a session swap in a blank project the way it swaps in an opened one"
```

---

### Task 5: `main()` always builds the session

**Files:**
- Modify: `src/inductor_designer/ui/main.py:376-560`
- Test: `tests/ui/test_main_wiring.py` (append)

**Interfaces:**
- Consumes: `new_project()` from Task 1, the tolerant `GuidedStudioController` from Task 3.
- Produces: a `main()` in which `projectSession`, `guidedStudioController`, `coreMaterialController`, `preliminaryController`, `simulationController` and `reviewController` are never `None`, and `backendChoices` is always populated.

- [ ] **Step 1: Write the failing test**

Append to `tests/ui/test_main_wiring.py`, following that file's existing `_run_main_with`-style harness (monkeypatch `QtGui.QGuiApplication` to reuse the instance, stub `exec`, capture `create_engine`), with `sys.argv` carrying no `--project`:

```python
def test_a_launch_with_no_project_still_offers_every_screen(
    monkeypatch: pytest.MonkeyPatch, catalog_index: Path
) -> None:
    """The 0.1.0 defect this closes: the installer's shortcuts pass no
    arguments, `session` was built only for a `--project` launch, and every
    controller hung off that -- so the Core & Material core list was literally
    `[]` and File > Open was disabled, which is the one thing that could have
    fixed it. The catalog was never the problem.
    """
    engine, root = _run_main_without_a_project(monkeypatch, catalog_index)
    context = engine.rootContext()

    session = context.contextProperty("projectSession")
    assert session is not None
    assert session.documentPath == ""
    assert session.dirty is False

    core_material = context.contextProperty("coreMaterialController")
    assert core_material is not None
    assert len(core_material.coreOptions) > 0
    assert context.contextProperty("guidedStudioController") is not None
    assert context.contextProperty("preliminaryController") is not None
    assert context.contextProperty("simulationController") is not None
    assert context.contextProperty("reviewController") is not None
    assert len(context.contextProperty("backendChoices")) > 0

    assert root.findChild(QObject, "openProjectMenuItem").property("enabled") is True
    assert root.findChild(QObject, "newProjectMenuItem").property("enabled") is True
    assert root.findChild(QObject, "saveProjectAsMenuItem").property("enabled") is True
    # Nothing has been edited, so there is nothing to save yet.
    assert root.findChild(QObject, "saveProjectMenuItem").property("enabled") is False


def test_a_launch_with_no_project_refuses_to_generate_until_it_is_saved(
    monkeypatch: pytest.MonkeyPatch, catalog_index: Path
) -> None:
    """A run writes a directory beside the document, and there is no document
    yet. The refusal already existed; this pins that the blank project reaches
    it instead of crashing on the way."""
    engine, _root = _run_main_without_a_project(monkeypatch, catalog_index)
    simulation = engine.rootContext().contextProperty("simulationController")

    assert simulation.canGenerate is False
    assert "no document path" in simulation.blockedReason
```

Add the harness beside the file's existing one:

```python
def _run_main_without_a_project(
    monkeypatch: pytest.MonkeyPatch, catalog_index: Path
) -> tuple[object, object]:
    real_app_cls = QtGui.QGuiApplication
    monkeypatch.setattr(
        QtGui,
        "QGuiApplication",
        lambda argv: real_app_cls.instance() or real_app_cls(argv),
    )
    monkeypatch.setattr(real_app_cls, "exec", lambda self: 0)
    real_create_engine = main_module.create_engine
    captured: list[tuple[object, ...]] = []

    def capturing_create_engine(*args: object, **kwargs: object) -> object:
        engine = real_create_engine(*args, **kwargs)
        captured.append((engine, *engine.rootObjects(), *args, *kwargs.values()))
        return engine

    monkeypatch.setattr(main_module, "create_engine", capturing_create_engine)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "inductor-designer",
            "--catalog",
            str(catalog_index),
            "--matrix",
            str(ROOT / "compatibility" / "aedt-matrix.yml"),
        ],
    )
    assert main_module.main() == 0
    _KEEPALIVE.extend(captured)
    engine, root, *_rest = captured[-1]
    QGuiApplication.instance().processEvents()
    return engine, root
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest -q tests/ui/test_main_wiring.py -k no_project`
Expected: FAIL — `projectSession` is `None` (and `newProjectMenuItem` does not exist yet).

- [ ] **Step 3: Write minimal implementation**

In `main()`:

1. Move the `--catalog` and `--matrix` `is_file()` checks (currently inside `if args.project is not None`, at lines ~385-393) out to just above that `if`, so they run on every launch. Keep their exact messages and return codes (2).
2. Move `backend_choices = [backend.value for backend in GenerationBackend]` out of the branch, with the `GenerationBackend` import it needs.
3. After the `if args.project is not None:` block, add:

```python
    if project is None:
        # No `--project`: a blank unsaved project, not a dead shell. The
        # installer's shortcuts pass no arguments, and every screen controller
        # below is built from the session -- so without this the core list, the
        # windings, Preliminary, Simulation and Review are all empty, and
        # File > Open (gated on the session existing) cannot fix it.
        project = new_project()
```

with `from inductor_designer.application.services.new_project import new_project` at the top of the function's import block.

4. Change `session: ProjectSession | None = None` / `if project is not None:` to build unconditionally: keep the whole body, and pass `args.project` (which is `None` for a blank launch) as the document path and `project_lock` (also `None`) as the lock. `ProjectSession(project, args.project, ...)` already accepts both as `None`.
5. Change `if session is not None and generation_controller is not None:` to `if generation_controller is not None:` — both are now always built — and keep the body unchanged.
6. Leave the `preview_entries`/`simulation_summary` computation inside the `args.project` branch. They are launch-time context properties; the Guided Studio controller builds the live preview itself, and Task 3 made a coreless project safe there.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest -q tests/ui/test_main_wiring.py tests/ui/test_main_close_dialog.py tests/ui/test_crash_recovery.py tests/ui/test_project_lock_wiring.py`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add src/inductor_designer/ui/main.py tests/ui/test_main_wiring.py
git commit -m "fix(ui): open a blank project when no document is given"
```

---

### Task 6: `File > New`, and Save with no document path

**Files:**
- Modify: `src/inductor_designer/ui/qml/Main.qml` (the `fileMenu` block at lines 37-80)
- Test: `tests/ui/test_app_menu.py` (append)

**Interfaces:**
- Consumes: `ProjectSession.newProject()` from Task 4.
- Produces: QML objects named `newProjectMenuItem`; `saveProjectMenuItem` routing to `saveProjectAsDialog` when `projectSession.documentPath === ""`.

- [ ] **Step 1: Write the failing test**

Append to `tests/ui/test_app_menu.py`:

```python
def test_new_from_a_dirty_project_warns_first_and_then_blanks_the_session() -> None:
    """File > New must not silently discard unsaved work: it routes through the
    same one guard as File > Open and the window's close button."""
    app, root, session = _loaded_root(Path("boost.inductor.json"))
    session.apply(replace(session.project, description="edited"))
    app.processEvents()

    new_item = root.findChild(QObject, "newProjectMenuItem")
    assert new_item.property("enabled") is True
    _trigger(new_item)
    app.processEvents()

    unsaved_dialog = root.findChild(QObject, "unsavedProjectDialog")
    assert unsaved_dialog.property("visible") is True
    assert session.project.description == "edited"

    assert (
        QMetaObject.invokeMethod(
            root.findChild(QObject, "unsavedProjectDiscardButton"), "clicked"
        )
        is True
    )
    app.processEvents()

    assert session.document_path is None
    assert session.project.design.core is None
    assert session.dirty is False


def test_save_on_a_project_with_no_document_path_offers_save_as_instead() -> None:
    """`Save` writes to the session's document path, and a project started
    from New has none -- the persister raises `RuntimeError` there. The menu
    item asks for a name instead of failing."""
    app, root, session = _loaded_root(None)
    session.apply(replace(session.project, description="edited"))
    app.processEvents()

    save_item = root.findChild(QObject, "saveProjectMenuItem")
    assert save_item.property("enabled") is True
    _trigger(save_item)
    app.processEvents()

    assert root.findChild(QObject, "saveProjectAsDialog").property("visible") is True
    assert session.dirty is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest -q tests/ui/test_app_menu.py -k "new_from_a_dirty or no_document_path"`
Expected: FAIL — `newProjectMenuItem` is `None`; Save reports "Unable to save".

- [ ] **Step 3: Write minimal implementation**

In `Main.qml`, add above `openProjectMenuItem`:

```qml
            MenuItem {
                objectName: "newProjectMenuItem"
                text: qsTr("New")
                enabled: projectSession !== null
                Accessible.name: text
                Accessible.description: enabled ? "" : qsTr(
                    "New is unavailable: no project session is loaded."
                )
                // Same guard as Open and the window's close button: unsaved
                // work is resolved before the project is replaced.
                onTriggered: window.requestGuardedProjectAction(function() {
                    projectSession.newProject()
                })
            }
```

and change `saveProjectMenuItem`'s handler from

```qml
                onTriggered: guidedStudioController.saveDraft()
```

to

```qml
                // A project started from New has no document path, and the
                // persister raises there rather than inventing a filename.
                // Asking for the name is what Save means in that state.
                onTriggered: {
                    if (projectSession.documentPath === "") {
                        saveProjectAsDialog.open()
                    } else {
                        guidedStudioController.saveDraft()
                    }
                }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest -q tests/ui/test_app_menu.py tests/ui/test_main_close_dialog.py`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add src/inductor_designer/ui/qml/Main.qml tests/ui/test_app_menu.py
git commit -m "feat(ui): add File > New, and make Save ask for a name when there is none"
```

---

### Task 7: Release notes, and the full gate

**Files:**
- Modify: `packaging/release_notes.md` (the "No sample project is shipped" section, lines 77-85)

**Interfaces:**
- Consumes: everything above.
- Produces: nothing.

- [ ] **Step 1: Rewrite the section**

Replace it with:

```markdown
## No sample project is shipped

Nothing this installer places on your machine carries a design. The first
launch opens a blank, unsaved project: no core selected, one winding, and a
neutral operating point. Pick a core on **Core & Material**, edit the
winding, then use **File > Save As** to name the file -- a run cannot start
until the project has been saved, because every run writes its directory
beside the project document.

**File > New** starts another blank project at any time, and **File > Open**
loads an existing `.inductor.json` from anywhere it already exists.
```

- [ ] **Step 2: Run the full gate**

```bash
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m mypy src tools
.venv/Scripts/python.exe -m tools.check_architecture
.venv/Scripts/python.exe -m pytest -q -n 8 -m "not aedt and not femm"
```

Expected: ruff "All checks passed!", mypy "Success", `check_architecture` silent, pytest all passed with the new tests included.

- [ ] **Step 3: Launch the real application with no arguments and confirm the core list**

```bash
.venv/Scripts/python.exe -m inductor_designer.ui.main
```

Expected: a window opens with no project given; **Core & Material** lists catalog cores; **File > New**, **Open** and **Save As** are enabled; **Save** is disabled until an edit.

- [ ] **Step 4: Commit**

```bash
git add packaging/release_notes.md
git commit -m "docs(release): describe the blank project the first launch now opens"
```

---

## Self-Review

- Spec coverage: factory and defaults (Task 1), pinned conductor safety (Task 2), tolerant Guided Studio constructor (Task 3), `newProject()` and the pathless `_adopt_loaded_project` (Task 4), `main()` restructuring plus the hoisted `--catalog`/`--matrix` checks and `backendChoices` (Task 5), `File > New` and Save routing (Task 6), release notes (Task 7). The spec's "what stays refused" is asserted in Task 5's second test.
- Names used consistently across tasks: `new_project`, `BLANK_CONDUCTOR_NAME`, `newProject`, `newProjectMenuItem`, `_empty_preview`, `_adopt_loaded_project(path: Path | None, ...)`.
- `SimulationController`'s gate is `canGenerate` / `blockedReason` (`simulation_controller.py:275-283`), and its no-document text is "The project has no document path. Save the project to a file before running." — read, not assumed.
- No placeholders remain.
