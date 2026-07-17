# Milestone 4.5: Automation Interfaces — MCP Server and FEMM 2D Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the inductor designer drivable by AI end to end: an MCP server exposing catalog browsing, project creation/validation, AEDT generation, and in-loop FEMM solving — with FEMM as a user-selectable alternative backend to Ansys for the 2D equivalent model, returning R/L results per winding.

**Architecture:** FEMM consumes the **same** solver-independent `Maxwell2dDesignPlan` the AEDT 2D adapter uses: a pure translation module maps the plan to a `FemmProblem` (circuits with ±1-turn conductor blocks, linear materials, planar depth, frequency), a `FemmSolver` port + pyfemm adapter builds/solves the `.fem` and extracts circuit impedances. A backend enum dispatches per call (CLI `--backend`, MCP tool argument) — project files are backend-agnostic. The MCP layer is deliberately thin: pure, unit-testable tool functions over the existing application services, registered in a FastMCP server behind an optional extra.

**Tech Stack:** `pyfemm` (optional `femm` extra; drives the freeware FEMM 4.2 via ActiveX, lazy import), `mcp` Python SDK / FastMCP (optional `mcp` extra, also in `dev` so CI exercises registration), stdlib elsewhere. FEMM 4.2 is installed on the dev machine (2026-07-17), so the live `@femm` tests run during execution, not as a deferred handoff.

## Global Constraints

- Python `>=3.10,<3.14`; mypy strict over `src` and `tools`; Ruff line 100 (`E,F,I,B,UP,ANN,SIM`); branch coverage `fail_under = 80`.
- Architecture rules (`tools/check_architecture.py`): inner packages (`domain`, `geometry`, `materials`, `simulation`) and `application` stay pure — `femm`/pyfemm imports live in `adapters/femm` only (lazy, inside a factory), `mcp` SDK imports live in `mcp_server/server.py` only (lazy). `mcp_server/tools.py` must import neither `mcp` nor any solver SDK.
- Every file starts with `from __future__ import annotations`; frozen slots dataclasses with `__post_init__` invariants.
- Units meters/hertz/amperes/degrees; floats reaching manifests/results rounded `round(x, 9)`; complex values serialized as `[re, im]` pairs.
- **pyfemm-return discipline (M4 lesson): FEMM/pyaedt-style libraries fail soft. Check returns where pyfemm returns anything; verify persisted artifacts in live tests, not just API acceptance.**
- FEMM-touching tests carry `@pytest.mark.femm` and skip unless `pyfemm` imports AND `INDUCTOR_FEMM_LIVE=1`; CI runs `-m "not aedt and not ui and not femm"` (update the CI workflow and all gate commands accordingly). The live FEMM run is the arbiter for exact pyfemm call semantics — fix adapter + fakes to match reality.
- Environment: `.venv\Scripts\python.exe`. Gates after every task: `-m pytest tests -q -m "not aedt and not ui and not femm"`, `-m ruff check .`, `-m mypy`, `python tools/check_architecture.py` (plus `-m pytest tests -q -m ui` on UI-adjacent tasks — none planned).
- Conventional commits.

## Design decisions (reviewed with Fabio Posser, 2026-07-17: Q1 one combined milestone, Q2 full MCP loop, Q3 FEMM as in-loop solver — all confirmed; FEMM is an OPTION beside Ansys 2D, user chooses per call)

- **D1 — One plan, two backends.** FEMM consumes `Maxwell2dDesignPlan` unchanged (its content is solver-neutral; the FEMM adapter ignores `solution_type`). Backend choice = per-call argument (`Backend2d` enum: `"aedt"` | `"femm"`), never project data — the same `.inductor.json` generates for either.
- **D2 — FEMM problem shape:** planar magnetics, meters, `depth = plan.model_depth_m`, frequency from `plan.setup.frequency_hz`; open boundary via FEMM's asymptotic boundary builder (`mi_makeABC()`) instead of the padded region + balloon (the FEMM idiom for open problems).
- **D3 — Materials:** core = linear μr from `plan.core.material` (σ=0), conductors = copper with σ=58 MS/m when the winding `is_solid` (FEMM then resolves skin/proximity in solid conductors), σ=0 for stranded. Nonlinear B-H arrives with Milestone 5 for both backends.
- **D4 — Excitations:** one series circuit per winding at the AC peak current; each conductor circle is one block of that circuit with `turns = +1` (Positive polarity) or `-1` (Negative). Phase: applied as a complex circuit current when the live run confirms pyfemm accepts complex `mi_addcircprop` values; otherwise magnitude-only with a manifest note (verify-at-FEMM).
- **D5 — Results:** per winding from `mo_getcircuitproperties` → complex `Z = V/I`, `R = Re(Z)`, `L = Im(Z)/(2πf)`, plus raw current/voltage/flux-linkage. Loss integrals deferred (Milestone 5 pairs them with real material data).
- **D6 — MCP scope:** nine pure tool functions — `list_cores`, `get_core`, `list_conductors`, `validate_project`, `save_project` (accepts a full schema-v2 project document; JSON-schema validation is the guardrail, no bespoke builder DSL), `geometry_summary`, `generate_maxwell3d`, `generate_2d` (with `backend`), `read_manifest`. FEMM solving happens inside `generate_2d(backend="femm", analyze=True)`.
- **D7 — Dependency policy:** `pyfemm` in a new `femm` extra; `mcp` in a new `mcp` extra AND appended to `dev` (so CI imports the server module); FEMM itself (freeware, Aladdin license) is user-installed like AEDT — never bundled, recorded in docs.
- **D8 — Manifests:** existing AEDT manifests gain `"backend": "aedt"`; the FEMM path writes the same schemaVersion-2 manifest shape with `"backend": "femm"` and a `femmResults` block (`{winding: {resistanceOhm, inductanceH, currentA: [re, im], voltageV: [re, im], fluxLinkageWb: [re, im]}}`), `dcBias` identified-blocked as for any 2D path.
- **D9 — DC bias on FEMM:** same 2D policy — always blocked/identified; FEMM magnetics has no DC-biased AC solve.
- **D10 (amended 2026-07-17 by Fabio) — backend choice in the Windows app too.** Guided Studio gains its first generation controls: a backend selector (Maxwell 3D / Maxwell 2D / FEMM 2D) plus a Generate button in the Simulation section, running generation off the UI thread and streaming stage/result lines into the panel (Task 10).

## File structure

| File | Responsibility |
|---|---|
| `src/inductor_designer/adapters/femm/__init__.py`, `model.py` (new) | Pure plan → `FemmProblem` translation |
| `src/inductor_designer/adapters/femm/solver.py` (new) | pyfemm adapter (lazy factory), build/solve/extract |
| `src/inductor_designer/application/ports/femm_solver.py` (new) | Port protocol + request/result DTOs |
| `src/inductor_designer/application/services/maxwell_export.py` (modify) | `Backend2d`, `export_2d` dispatch, femm manifest, `backend` key |
| `src/inductor_designer/mcp_server/__init__.py`, `tools.py`, `server.py` (new) | MCP tool functions (pure) + FastMCP registration |
| `tools/generate_maxwell2d.py` (modify) | `--backend {aedt,femm}` |
| `pyproject.toml` (modify) | `femm`/`mcp` extras, `femm` marker, `inductor-designer-mcp` script |
| `tests/fakes/femm_solver.py`, `tests/fakes/femm_module.py` (new) | Recording fakes |
| `src/inductor_designer/ui/main.py`, `ui/qml/Main.qml`, new `ui/generation_controller.py` (modify/new) | Backend selector + Generate action |
| `docs/development/automation-mcp-femm.md` (new); ROADMAP, spec, plans/README (modify) | Procedures + milestone record |

---

### Task 1: Record the milestone — ROADMAP, spec, plan index, markers, extras

**Files:**
- Modify: `docs/development/ROADMAP.md` (insert new section between M4 and M5)
- Modify: `docs/superpowers/specs/2026-07-12-pyaedt-inductor-application-design.md` (goals + boundary rules additions)
- Modify: `docs/superpowers/plans/README.md` (row for this plan)
- Modify: `pyproject.toml` (`femm`/`mcp` extras, `mcp` into dev, `femm` pytest marker, console script placeholder comes in Task 8)
- Modify: `.github/workflows/*.yml` (test commands gain `and not femm`)
- Test: none (docs/config; gates prove pyproject stays valid)

**Interfaces:** none.

- [ ] **Step 1: ROADMAP section** — insert after the Milestone 4 current-state block:

```markdown
## Milestone 4.5: Automation interfaces — MCP server and FEMM 2D backend

Requirements added 2026-07-17 by Fabio Posser:

- Expose the designer over MCP so an AI client can create projects, validate
  them, generate solver designs, run simulations, and read results by itself.
- Offer FEMM (https://www.femm.info) as a user-selectable alternative to
  Ansys Maxwell for the 2D equivalent model, including an in-loop solve with
  R/L result extraction.

- Translate the solver-independent 2D design plan to a FEMM planar problem
  (circuits with signed one-turn conductor blocks, linear materials,
  asymptotic open boundary), solve headless, and extract per-winding
  impedance results.
- Select the 2D backend per call (CLI flag, MCP argument); project files stay
  backend-agnostic.
- Serve catalog, project, generation, and solve operations as MCP tools over
  stdio behind an optional extra.

Exit criterion: an MCP client session can create a valid project, generate a
ready-to-solve Maxwell design, run a FEMM solve of the 2D equivalent, and
read back per-winding R/L — with the backend chosen per call.
```

- [ ] **Step 2: Spec amendment** — in §2 goals add two bullets recording the same two requirements (dated); in §4.2 optional integrations add "FEMM 4.2 via pyfemm (user-installed freeware; never bundled)" and "MCP server (optional extra) exposing application services as tools".

- [ ] **Step 3: pyproject** — add:

```toml
femm = ["pyfemm>=0.1.3"]
mcp = ["mcp>=1.0,<2"]
```

append `"mcp>=1.0,<2",` to the `dev` extra; add marker line `"femm: requires a local FEMM 4.2 installation"` next to the `aedt`/`ui` markers. Reinstall `pip install -e ".[dev,ui]"`.

- [ ] **Step 4: CI + plan index** — every `-m "not aedt and not ui"` in workflows and docs gate snippets becomes `-m "not aedt and not ui and not femm"`; add the plan row to `docs/superpowers/plans/README.md`.

- [ ] **Step 5: Gates, commit**

```bash
git add docs/development/ROADMAP.md docs/superpowers/specs/2026-07-12-pyaedt-inductor-application-design.md docs/superpowers/plans/README.md pyproject.toml .github/workflows
git commit -m "docs: record Milestone 4.5 automation requirements (MCP + FEMM)"
```

---

### Task 2: FEMM problem translation (pure)

**Files:**
- Create: `src/inductor_designer/adapters/femm/__init__.py` (`"""FEMM backend adapters."""`)
- Create: `src/inductor_designer/adapters/femm/model.py`
- Test: `tests/unit/adapters/test_femm_model.py`

**Interfaces (frozen slots dataclasses):**
- `FemmMaterial(name: str, relative_permeability: float, conductivity_ms_per_m: float)` — note **MS/m** (FEMM's unit).
- `FemmCircuit(name: str, current_peak_a: float, phase_deg: float)`.
- `FemmConductor(x_m: float, y_m: float, radius_m: float, material: str, circuit: str, turns: int)` — `turns` ±1.
- `FemmAnnulus(r_inner_m: float, r_outer_m: float, material: str)`.
- `FemmProblem(frequency_hz: float, depth_m: float, core: FemmAnnulus, materials: tuple[FemmMaterial, ...], circuits: tuple[FemmCircuit, ...], conductors: tuple[FemmConductor, ...])`.
- `COPPER_CONDUCTIVITY_MS_PER_M = 58.0`, `AIR_MATERIAL = "Air"`.
- `femm_problem_from_plan(plan: Maxwell2dDesignPlan) -> FemmProblem` — materials: air (μr 1, σ 0), core spec (μr from `plan.core.material.relative_permeability`, σ 0), one conductor material per solidity actually used (`Copper_solid` σ 58 / `Copper_stranded` σ 0, μr 1); one circuit per winding (`current_peak_a`, `phase_deg`); conductors with `turns=+1` for `Polarity.POSITIVE` else `-1`.

- [ ] **Step 1: Write the failing tests**

```python
from __future__ import annotations

from inductor_designer.adapters.femm.model import (
    COPPER_CONDUCTIVITY_MS_PER_M,
    femm_problem_from_plan,
)
from inductor_designer.simulation.maxwell_plan import Polarity
from tests.unit.simulation.test_plan_builder import make_definition
from tests.unit.simulation.test_plan_builder2d import build2d


def test_problem_maps_plan_essentials() -> None:
    plan = build2d((make_definition(),))
    problem = femm_problem_from_plan(plan)  # type: ignore[arg-type]
    assert problem.frequency_hz == 100_000.0
    assert problem.depth_m == plan.model_depth_m
    assert problem.core.r_inner_m == plan.core.r_inner_m
    assert problem.core.material == plan.core.material.name
    assert [c.name for c in problem.circuits] == ["w1"]
    assert problem.circuits[0].current_peak_a == 2.0
    assert len(problem.conductors) == 8


def test_polarity_becomes_signed_turns() -> None:
    plan = build2d((make_definition(),))
    problem = femm_problem_from_plan(plan)  # type: ignore[arg-type]
    signs = {conductor.turns for conductor in problem.conductors}
    assert signs == {1, -1}
    positives = [c for c in problem.conductors if c.turns == 1]
    assert len(positives) == 4
    by_name = {
        c.name: c.polarity for group in plan.windings for c in group.conductors
    }
    for conductor, plan_conductor in zip(problem.conductors, plan.windings[0].conductors):
        expected = 1 if plan_conductor.polarity is Polarity.POSITIVE else -1
        assert conductor.turns == expected


def test_solid_winding_gets_conductive_copper() -> None:
    plan = build2d((make_definition(),))  # SOLID mode default
    problem = femm_problem_from_plan(plan)  # type: ignore[arg-type]
    materials = {m.name: m for m in problem.materials}
    assert problem.conductors[0].material == "Copper_solid"
    assert materials["Copper_solid"].conductivity_ms_per_m == COPPER_CONDUCTIVITY_MS_PER_M
    assert materials["Air"].relative_permeability == 1.0
```

(Drop the unused `by_name` line when implementing — keep the zip-based polarity check.)

- [ ] **Step 2: verify failure** (module not found), **Step 3: implement** exactly the interfaces above (straightforward mapping; `__post_init__` guards: positive radius/frequency/depth, `turns in (-1, 1)`), **Step 4: gates**, **Step 5: commit** `feat(adapters): pure FEMM problem translation from the 2D plan`.

---

### Task 3: FEMM solver port and recording fake

**Files:**
- Create: `src/inductor_designer/application/ports/femm_solver.py`
- Create: `tests/fakes/femm_solver.py`
- Test: `tests/contract/test_femm_solver_contract.py`

**Interfaces:**
- `FemmSolveRequest(problem: FemmProblem, output_directory: Path, project_name: str, analyze: bool)`.
- `FemmWindingResult(resistance_ohm: float, inductance_h: float, current_a: tuple[float, float], voltage_v: tuple[float, float], flux_linkage_wb: tuple[float, float])` — complex as `(re, im)`, all `round(_, 9)` at the adapter boundary.
- `FemmSolveResult(fem_path: Path, analyzed: bool, results: Mapping[str, FemmWindingResult] | None, messages: tuple[str, ...])` — `results` is `None` when `analyze=False`.
- `class FemmSolver(Protocol): def solve(self, request: FemmSolveRequest) -> FemmSolveResult: ...`
- Fake `RecordingFemmSolver`: records requests; returns `fem_path=output_directory / f"{project_name}.fem"`, `analyzed=request.analyze`, and when analyzed a deterministic result per circuit: `resistance_ohm=0.1`, `inductance_h=1e-4`, `current_a=(circuit.current_peak_a, 0.0)`, `voltage_v=(0.2, 0.126)`, `flux_linkage_wb=(1e-4, 0.0)`.

Contract test: fake records the request; `analyze=True` yields one result per circuit keyed by circuit name; `analyze=False` yields `results is None`; fem path under the output directory.

Commit: `feat(application): FEMM solver port with recording fake`.

---

### Task 4: pyfemm adapter

**Files:**
- Create: `src/inductor_designer/adapters/femm/solver.py`
- Create: `tests/fakes/femm_module.py`
- Test: `tests/unit/adapters/test_femm_solver.py`

**Interfaces:**
- `FemmModule(Protocol)` — the pyfemm surface used, all `Any`-typed methods: `openfemm(flag)`, `newdocument(doctype)`, `mi_probdef(...)`, `mi_addnode`, `mi_addarc`, `mi_addblocklabel`, `mi_addmaterial`, `mi_addcircprop`, `mi_selectlabel`, `mi_setblockprop`, `mi_clearselected`, `mi_makeABC()`, `mi_zoomnatural()`, `mi_saveas(path)`, `mi_analyze(flag)`, `mi_loadsolution()`, `mo_getcircuitproperties(name)`, `closefemm()`.
- `DefaultFemmModuleFactory` — lazy `import femm`; `PyfemmSolver(module_factory=None)` implementing the port.
- Geometry per circle (core outer, core inner, every conductor): two nodes at `(x−r, y)`/`(x+r, y)`, two 180° arcs (`mi_addarc(x1, y1, x2, y2, 180, 5)`); block labels: conductor centers; core label at `((r_inner+r_outer)/2, 0)`; air label just outside the core at `(0, r_outer * 1.5)` — **verify-at-FEMM** that it falls inside the ABC region.
- Sequence: `openfemm(1)` (hidden), `newdocument(0)` (magnetics), `mi_probdef(frequency_hz, "meters", "planar", 1e-8, depth_m, 30)`, materials (`mi_addmaterial(name, mu, mu, 0, 0, sigma_ms, 0, 0, 1, 0, 0, 0)`), circuits (`mi_addcircprop(name, current_peak_a, 1)` — phase handling per D4, note when dropped), geometry, block props (`mi_selectlabel(x, y)` → `mi_setblockprop(material, 1, 0, circuit, 0, 0, turns)` → `mi_clearselected()`), `mi_makeABC()`, `mi_saveas(str(fem_path))`; when `analyze`: `mi_analyze(1)`, `mi_loadsolution()`, per circuit `mo_getcircuitproperties(name)` → `(current, voltage, flux)` complex → `Z = V/I`, `R=round(Z.real, 9)`, `L=round(Z.imag/(2π·f), 9)`; `closefemm()` in `finally`.
- **Return-checking (M4 lesson):** `mo_getcircuitproperties` returning a falsy/None or non-3-sequence raises `RuntimeError`; `fem_path.exists()` verified after `mi_saveas` and included in messages.
- Fake pyfemm module (`tests/fakes/femm_module.py`): records every call `(name, args)`; `mo_getcircuitproperties` returns `(2+0j, 0.2+0.126j, 1e-4+0j)`; `mi_saveas` touches the file (so the exists-check passes); factory records creations. Unit tests: call sequence (probdef before geometry, makeABC before saveas, analyze only when requested), signed turns forwarded to `mi_setblockprop`, R/L math (`R=0.1`, `L=Im(Z)/(2πf)` with `Z=(0.2+0.126j)/2`), closefemm always called (also on injected failure).

Commit: `feat(adapters): pyfemm solver builds, solves, and extracts circuit impedances`.

---

### Task 5: Backend dispatch service and manifests

**Files:**
- Modify: `src/inductor_designer/application/services/maxwell_export.py`
- Test: `tests/unit/application/test_maxwell_export.py` (extend)

**Interfaces:**
- `class Backend2d(str, Enum): AEDT = "aedt"; FEMM = "femm"`.
- `FemmExportOutcome(plan: Maxwell2dDesignPlan, problem: FemmProblem, result: FemmSolveResult, capabilities: CapabilitySnapshot, decision: DcBiasDecision)`.
- `export_femm2d(project, catalog, solver: FemmSolver, output_directory, *, capabilities, analyze: bool = True) -> FemmExportOutcome` — same `_validated_model` gate (TWO_D, catalog core, collisions), same `build_maxwell2d_plan` with the 2D blocked decision, then `femm_problem_from_plan` + `solver.solve(...)`, `project_name = f"{sanitize_identifier(project.name)}_2d"`.
- `femm_manifest_json(outcome: FemmExportOutcome) -> str` — schemaVersion 2, `"backend": "femm"`, `dimension: "2d"`, designName = plan.design_name, `femPath`, `analyzed`, `dcBias`/`capabilities`/`coreMaterial`/`windings`/`notes` blocks as the AEDT manifest, plus `femmResults` per D8 (`None` when not analyzed).
- `generation_manifest_json` gains `"backend": "aedt"`.
- Wait — import direction: `application` importing `adapters.femm.model` breaks layering (application must not depend on adapters). **Move check:** `femm_problem_from_plan` + the `Femm*` dataclasses are pure; if `tools/check_architecture.py` or the architecture docs forbid application→adapters imports, relocate `model.py` to `src/inductor_designer/simulation/femm_problem.py` in Task 2 instead (same content; simulation may not import pathlib — the model module doesn't). **Implementer: check `docs/architecture/README.md` dependency rules first and place the pure model in `simulation/` if application→adapters is disallowed (it is the safer default; do that unless the checker/docs say otherwise, and keep `adapters/femm/` for the pyfemm solver only).** Update Task 2/3/4 import paths accordingly — the port and adapter both consume the model.

Tests: femm export happy path via `RecordingFemmSolver` (manifest backend "femm", `femmResults` populated, dcBias blocked, determinism), `analyze=False` → `femmResults` null, AEDT manifests carry `backend: "aedt"` (extend one existing assertion).

Commit: `feat(application): user-selectable 2D backend with FEMM solve outcome and manifest`.

---

### Task 6: CLI backend flag and FEMM live test

**Files:**
- Modify: `tools/generate_maxwell2d.py` (`--backend {aedt,femm}` default `aedt`; femm path prints per-winding R/L lines and writes the femm manifest as `--evidence`; `--no-analyze` flag maps to `analyze=False`)
- Test: `tests/unit/tools/test_generate_maxwell2d.py` (extend: `--backend femm` with `RecordingFemmSolver` injected via a new `femm_solver=None` keyword on `main`, evidence has `backend == "femm"` and R/L present; exit 0)
- Test: `tests/integration/femm/test_femm_live.py` — `pytestmark = pytest.mark.femm`; skips unless `importlib.util.find_spec("femm")` and `os.environ.get("INDUCTOR_FEMM_LIVE") == "1"`; loads the sample fixture, forces TWO_D, `export_femm2d` with the real `PyfemmSolver`; asserts `.fem` exists, `analyzed`, both windings present with `resistance_ohm > 0` and `inductance_h > 0`, and **re-opens the saved `.fem` text to confirm the circuits and depth landed** (persistence check, M4 lesson).

Commit: `feat(tools): FEMM backend option on the 2D generation CLI`.

---

### Task 7: MCP tool functions (pure)

**Files:**
- Create: `src/inductor_designer/mcp_server/__init__.py` (docstring only)
- Create: `src/inductor_designer/mcp_server/tools.py`
- Test: `tests/unit/mcp_server/test_tools.py`

**Interfaces:** a `ToolContext` frozen dataclass carrying wiring so every tool stays a pure function:

```python
@dataclass(frozen=True, slots=True)
class ToolContext:
    catalog: CatalogRepository
    schemas: SchemaRepository
    matrix_path: Path
    output_root: Path
    maxwell3d_exporter: Maxwell3dExporter
    maxwell2d_exporter: Maxwell2dExporter
    femm_solver: FemmSolver
```

Tool functions (all take `context` first, return JSON-able `dict[str, object]`; errors return `{"error": str(...), "issues": [...]}` rather than raising — MCP clients need structured failures):

- `list_cores(context)` → `{"cores": [{"partNumber", "manufacturer", "material", "grade", "reviewStatus"}...]}`
- `get_core(context, part_number)` → full record dict via the existing serde, or error.
- `list_conductors(context)` → names.
- `save_project(context, document: dict, path: str)` — validate against schema v2 via `SchemaRepository`/`ProjectRepository` round trip, save deterministically, return `{"path", "projectId"}` or validation issues.
- `validate_project(context, path)` → `{"issues": [...]}` from `validate_project` domain service (empty = valid).
- `geometry_summary(context, path)` → the geometry manifest dict (`build_manifest`), or blocked issues.
- `generate_maxwell3d(context, path)` → the parsed generation manifest dict (capabilities from `MatrixCapabilityRepository(context.matrix_path)`).
- `generate_2d(context, path, backend: str = "aedt", analyze: bool = True)` → parsed manifest dict for either backend (`Backend2d(backend)`; invalid → error dict).
- `read_manifest(context, path)` → parsed JSON of a previously written evidence file under `output_root` (path-traversal guard: resolved path must be inside `output_root`).

Output directories: per-call `context.output_root / <sanitized project name>`. Unit tests use `RecordingMaxwell3dExporter`/`RecordingMaxwell2dExporter`/`RecordingFemmSolver` + the temp SQLite catalog fixture pattern from `tests/ui/test_preview_smoke.py`; cover: happy path per tool, invalid backend, schema-invalid document, traversal guard.

Commit: `feat(mcp): pure MCP tool functions over application services`.

---

### Task 8: FastMCP server registration

**Files:**
- Create: `src/inductor_designer/mcp_server/server.py`
- Modify: `pyproject.toml` (`[project.scripts] inductor-designer-mcp = "inductor_designer.mcp_server.server:main"`)
- Test: `tests/unit/mcp_server/test_server.py`

**Interfaces:**
- `build_context(root: Path, catalog_index: Path | None = None) -> ToolContext` — builds the catalog (reusing the `tools.build_catalog.build` + `SqliteCatalogRepository` pattern from the CLIs), real exporters (`PyaedtMaxwell3dExporter`, `PyaedtMaxwell2dExporter`, `PyfemmSolver`), matrix default `root/"compatibility"/"aedt-matrix.yml"`, `output_root = root/"artifacts"/"mcp"`.
- `create_server(context: ToolContext) -> "FastMCP"` — lazy `from mcp.server.fastmcp import FastMCP`; registers each Task-7 function as a tool (thin lambdas/closures binding `context`; docstrings become tool descriptions — write one operational sentence each, they are the AI client's only manual).
- `main(argv=None) -> int` — args `--root` (default cwd), `--catalog-index`; `create_server(...).run()` (stdio).

Test (mcp SDK present via dev extra): `create_server` on a fake-backed context exposes exactly the nine tool names; calling the `list_cores` tool through FastMCP's in-process interface returns the catalog rows (one round-trip proves registration wiring; deeper behavior is Task 7's coverage). If FastMCP's testing interface proves awkward, assert via `server._tool_manager.list_tools()` names + direct closure call — note which was used.

Commit: `feat(mcp): FastMCP stdio server and console script`.

---

### Task 9: Exit-criterion session test

**Files:**
- Test: `tests/integration/test_mcp_session.py`

Scripted AI-session flow against the pure tools with recording fakes (no MCP transport — Task 8 proved registration): build context (temp catalog, temp output root, real matrix file), then:

1. `list_cores` → pick `0077071A7`.
2. `save_project` with a schema-v2 document built from the sample fixture JSON (loaded, `dimensionMode` kept `"3d"`).
3. `validate_project` → no issues.
4. `geometry_summary` → winding turn counts present.
5. `generate_maxwell3d` → manifest `succeeded`, `dcBias.strategy == "native-include-dc-fields"` (real matrix), `backend == "aedt"`.
6. `generate_2d(backend="femm", analyze=True)` → manifest `backend == "femm"`, `femmResults` has both windings with positive R and L.
7. `read_manifest` on the written femm evidence → equals step-6 dict.

Assert the whole chain with no error dicts. This is the milestone exit-criterion proof at CI level; the live arbiter is Task 6's `@femm` test plus the AEDT-marked tests already accepted in M4.

Commit: `test: MCP session drives design, generation, and FEMM solve end to end`.

---

### Task 10: Guided Studio backend selection and Generate action

**Files:**
- Create: `src/inductor_designer/ui/generation_controller.py`
- Modify: `src/inductor_designer/ui/main.py`, `src/inductor_designer/ui/qml/Main.qml`
- Test: `tests/unit/ui/test_generation_controller.py` (pure parts) and extend `tests/ui/` smoke (ui-marked)

**Interfaces:**
- `GenerationBackend(str, Enum): MAXWELL_3D = "Maxwell 3D"; MAXWELL_2D = "Maxwell 2D (Ansys)"; FEMM_2D = "FEMM 2D"` in `generation_controller.py`.
- `run_generation(backend: GenerationBackend, project: InductorProject, catalog, capabilities, output_directory, *, maxwell3d_exporter, maxwell2d_exporter, femm_solver) -> tuple[str, ...]` — PURE function returning display lines: per-stage `name: ok/FAILED - message` for Maxwell paths, per-winding `w1: R=…Ω L=…H` lines plus fem path for FEMM. Dimension-mode mismatch (e.g. 3D backend on a 2d project) returns the blocked issues as lines, does not raise. All logic lives here — unit-tested with the recording fakes; keep it Qt-free (module may import Qt only in the controller class below; the `ui` package already requires the PySide6 extra so a module-level Qt import is acceptable, but `run_generation` itself must be callable in the plain unit suite — put it in the same file and import PySide6 lazily inside the controller class if needed, or split the pure part into `generation_lines.py` if mypy/test isolation demands; implementer's call, name the choice in the report).
- `GenerationController(QObject)` — constructed with a callable `(backend_label: str) -> tuple[str, ...]`; `@Slot(str)` `generate(backend_label)` spawns a `threading.Thread` invoking it and emits a `linesChanged` signal with the result (cross-thread QObject signal emission is queue-safe); `Property` `lines` (list, notify=linesChanged) and `busy` (bool, notify).
- `ui/main.py`: when a project is loaded, build the controller with real exporters (`PyaedtMaxwell3dExporter`, `PyaedtMaxwell2dExporter`, `PyfemmSolver`), matrix-based capabilities, output under `artifacts/studio/<sanitized-name>`; context properties `generationController` and `backendChoices` (enum labels list; empty list + null controller when no project).
- `Main.qml`: in the Simulation section — `ComboBox { id: backendCombo; model: backendChoices }`, `Button { enabled: generationController !== null && !generationController.busy; text: generationController !== null && generationController.busy ? "Generating…" : "Generate"; onClicked: generationController.generate(backendCombo.currentText) }`, and a `Repeater` over `generationController !== null ? generationController.lines : []` styled like the summary lines; whole block `visible: generationController !== null`.

Steps: TDD the pure `run_generation` (three backends via recording fakes, blocked dimension case), then a ui-marked controller test (offscreen: call `generate`, process events until `busy` is false, assert lines), then QML wiring with `pytest -m ui` green.

Commit: `feat(ui): backend selection and generation from Guided Studio`

---

### Task 11: Docs, gates, live FEMM verification

**Files:**
- Create: `docs/development/automation-mcp-femm.md` — MCP server usage (client config snippet for `inductor-designer-mcp`, tool list with one-line descriptions), FEMM installation (download femm.info 4.2, `pip install -e ".[femm]"`, `INDUCTOR_FEMM_LIVE=1` for live tests), backend selection examples (CLI + MCP), verify-at-FEMM risk list (ABC region label placement, complex circuit current/phase, `mi_analyze` headless flag).
- Modify: ROADMAP M4.5 `### Current state` (implementation complete pending live FEMM verification), `README.md` row.

Gates (full set incl. `-m ui`), coverage noted. FEMM is installed: the controller runs `INDUCTOR_FEMM_LIVE=1 pytest tests/integration/femm -m femm` and the live CLI FEMM generation during THIS task, fixing adapter+fakes against pyfemm reality (M4 convention). Remaining human validation for Fabio: (1) open the generated `.fem` in FEMM, sanity-check geometry/materials/circuits, judge R/L plausibility vs the AEDT 2D solve; (2) click through the Guided Studio backend selector + Generate; (3) optionally drive `inductor-designer-mcp` from an MCP client; (4) accept M4.5 in the ROADMAP.

Commit: `docs: MCP and FEMM automation procedures and M4.5 status`.

---

## Self-review notes

- Requirements → tasks: MCP server (T7/T8/T9), FEMM backend + user choice (T2–T6), in-loop solve + results (T4/T5/T6), Windows-app backend choice (T10), record-the-requirement (T1), exit criterion (T9 + T11 verification).
- Cross-task names: `FemmProblem`/`femm_problem_from_plan` (T2→T3/T4/T5; placement decision in T5 note applies from T2 — implementer resolves before writing T2 code by checking the architecture rules, default `simulation/femm_problem.py`), `FemmSolver`/`FemmSolveRequest`/`FemmSolveResult` (T3→T4/T5/T6/T7), `Backend2d`/`export_femm2d`/`femm_manifest_json` (T5→T6/T7), `ToolContext` + nine tool functions (T7→T8/T9).
- Verify-at-FEMM risks (arbiter = T6 live test + T10 handoff): `mi_makeABC()` no-arg behavior and air-label placement, complex/phased circuit currents, `mi_addmaterial` positional signature, `mi_analyze(1)` headless semantics, `mo_getcircuitproperties` return shape.
- Verify-at-MCP risk: FastMCP in-process test interface (T8 names its fallback).
- M4 lessons applied: falsy-return guards + artifact persistence checks are explicit steps, not afterthoughts.
