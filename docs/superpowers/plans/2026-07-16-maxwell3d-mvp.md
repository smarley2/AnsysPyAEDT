# Milestone 3: Maxwell 3D MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate a Maxwell 3D project from a validated inductor project — toroid core solid, one closed round-wire loop per turn, one coil terminal per turn grouped into windings, materials, excitations, air region, mesh intent, AC Magnetic (Eddy Current) setup, matrix, and standard report requests — so that a supported AEDT installation opens it ready to solve.

**Architecture:** A pure `simulation` package turns the Milestone 2 `GeometryModel` outputs into a solver-independent `Maxwell3dDesignPlan` (frozen dataclasses: core plan, per-turn conductor plans with terminal disks and polarities, region/mesh/setup/matrix/report plans). A new application port `Maxwell3dExporter` (mirroring the M0 `AedtGateway` pattern: Protocol + recording fake + lazy PyAEDT adapter) executes the plan as named stages, each recorded in a `StageRecord`, so a partial design is never reported as successful. An application service composes project → geometry model → plan → export request and emits a generation manifest.

**Tech Stack:** Python 3.10–3.13 stdlib, PyAEDT `Maxwell3d` (lazy import, `adapters/pyaedt` only), pytest with the existing `aedt` marker for licensed-machine verification.

## Global Constraints

- Python `>=3.10,<3.14`; mypy `strict = true` over `src` and `tools`; Ruff line length 100 with `E,F,I,B,UP,ANN,SIM`; branch coverage `fail_under = 80`.
- Architecture rules enforced by `tools/check_architecture.py`: `domain`, `geometry`, `materials`, `simulation` never import PySide6/ansys/pyaedt/sqlite3/os/pathlib/etc.; `application` never imports PySide6/ansys/pyaedt/sqlite3. Only `adapters/*`, `tools/`, `tests/` may import `ansys`/`pyaedt`, and PyAEDT imports stay lazy (inside factory `create`). Run the checker after every task touching inner packages.
- No new runtime dependencies.
- Every file starts with `from __future__ import annotations`. Frozen slots dataclasses with `__post_init__` for hard invariants, matching `src/inductor_designer/domain/`.
- Units: meters, degrees, amperes, hertz everywhere in Python; the adapter sets AEDT model units to `meter` before creating geometry so raw floats pass through unconverted.
- Coordinate convention (unchanged from M2): toroid axis = **Z**; core centered on the origin; the radial half-plane at angle θ contains `(cos θ, sin θ, 0)`; angles CCW viewed from +Z.
- Determinism: every float that reaches a plan, name, or manifest is rounded with `round(x, 9)`. Identical inputs produce identical plans and generation manifests (path strings excluded).
- One closed planar D-loop per turn (locked M2 decision): no connectors, no lead wires in Maxwell geometry. Each turn gets one coil terminal; terminals group into one winding per `WindingDefinition`.
- AEDT-touching tests carry `@pytest.mark.aedt` and skip without `INDUCTOR_AEDT_RELEASE`/`INDUCTOR_AEDT_EDITION`; CI runs `-m "not aedt and not ui"`. The real-AEDT integration test is the arbiter for exact PyAEDT keyword names — if a documented kwarg differs in the installed pyaedt, fix the adapter (and its fake) to match reality, never the other way around.
- Environment: use the project venv for all commands: `.venv\Scripts\python.exe`. Gates after every task: `-m pytest tests -q -m "not aedt and not ui"`, `-m ruff check .`, `-m mypy`, `-m tools.check_architecture` (or `python tools/check_architecture.py`).
- Conventional commits. Don't stage unrelated files.

## Proposed design decisions (NOT grilled — Fabio: veto any of these before execution)

- **D1 — Solution type `"EddyCurrent"`.** PyAEDT's canonical name for the AC Magnetic solver on Maxwell 3D. 2025 R2 renames the UI label to "AC Magnetic"; pyaedt accepts `EddyCurrent` across supported versions.
- **D2 — Core material derived from the powder grade.** No material property data exists until Milestone 5 (`MaterialRef` is identity-only). For Magnetics powder toroids the grade string *is* the relative permeability ("60" → μr 60). M3 creates a linear AEDT material: μr = `float(grade)`, conductivity 0 S/m, no core-loss model. Non-numeric grades and ferrite cores raise a typed `PlanBuildError` (the 5 ferrite records are still draft anyway). Material name carries the source identity, e.g. `Magnetics_Kool_Mu_60`. Manifest notes flag the material as draft-derived when the core record is not `reviewed`.
- **D3 — Manual cores are not exportable in M3** (no material identity). Typed refusal.
- **D4 — Conductors modeled at bare copper diameter** with AEDT built-in `copper`; insulation affects placement only (already applied by packing).
- **D5 — Terminal = circular sheet at the midpoint of each turn's bottom straight run** (segment index 6 of the 8-segment loop), radius = bare radius, normal = radial. Created at θ=0 in the YZ plane and rotated to the station angle.
- **D6 — Polarity convention:** positive coil polarity = current flows radially **outward** along the bottom run. Effective polarity = `Positive` when `current_direction == FORWARD` XOR `winding_direction == CLOCKWISE` is false (i.e. FORWARD+CCW → Positive, FORWARD+CW → Negative, etc.). All turns of a winding share one polarity.
- **D7 — Excitation:** winding type `Current`, amplitude = `ac_magnitude_a` (interpreted as peak), phase = `ac_phase_deg`, `is_solid` from `ConductorMode`. All windings must share one `frequency_hz` (typed error otherwise). `dc_current_a` is recorded in the manifest but **not applied** — DC bias is Milestone 4 (`select_dc_bias_strategy` already exists for it).
- **D8 — Region:** air region, 100 % padding on all six directions; Maxwell's default boundary on the region faces (no explicit boundary assignment in the MVP).
- **D9 — Eddy effects** on for solid-mode turn conductors, off for stranded; core has σ=0 so it needs nothing.
- **D10 — Mesh intent:** length-based restrictions only. Conductors: max element `1.5 × bare_d`. Core: max element `min(core_width, core_height)/3`.
- **D11 — Setup/reports:** `Setup1` with MaximumPasses 10, PercentError 1; `Matrix1` over all windings; per-winding `Matrix1.R(w,w)` and `Matrix1.L(w,w)` report definitions created pre-solve (they populate after solving).
- **D12 — Full model only.** No symmetry cutting (M2 symmetry stays data-level).
- **D13 — Collisions block export.** Any `CollisionIssue` from `check_clearances` refuses generation with the issue messages.
- **D14 — M2 should-fix #2 adopted:** a deterministic uniqueness guard on sanitized identifiers, used for every AEDT object name. (Should-fix #1/#3–#6 stay parked: #3 is moot in Maxwell — no leads in geometry.)

## File structure

| File | Responsibility |
|---|---|
| `src/inductor_designer/geometry/naming.py` (modify) | + `unique_identifiers` collision guard |
| `src/inductor_designer/geometry/core_profile.py` (new) | Core cross-section outline in the θ=0 half-plane |
| `src/inductor_designer/geometry/terminals.py` (new) | `TerminalDisk` + placement on a turn loop |
| `src/inductor_designer/simulation/maxwell_plan.py` (new) | Solver-independent plan dataclasses + `core_material_spec` |
| `src/inductor_designer/simulation/plan_builder.py` (new) | `build_maxwell3d_plan` |
| `src/inductor_designer/application/ports/maxwell_exporter.py` (new) | Port protocol, request/result DTOs, `STAGE_NAMES` |
| `src/inductor_designer/application/services/maxwell_export.py` (new) | Orchestration + generation manifest |
| `src/inductor_designer/adapters/pyaedt/polyline_data.py` (new) | Pure `PathSegment` → point/segment-kind conversion |
| `src/inductor_designer/adapters/pyaedt/maxwell3d.py` (new) | Staged PyAEDT exporter |
| `tools/generate_maxwell3d.py`, `tools/run_aedt_maxwell3d.ps1` (new) | CLI + controlled runner |
| `tests/fakes/maxwell_exporter.py`, `tests/fakes/maxwell3d_app.py` (new) | Recording fakes |

---

### Task 1: Unique identifier guard (M2 should-fix #2)

`sanitize_identifier` collapses distinct raw winding ids (`"a b"` and `"a-b"` → `"a_b"`), which would silently merge AEDT objects. Add a deterministic order-based disambiguator. The M2 manifest keeps using plain `sanitize_identifier` (no golden churn); the Maxwell plan builder uses the new map.

**Files:**
- Modify: `src/inductor_designer/geometry/naming.py`
- Test: `tests/unit/geometry/test_naming.py` (extend)

**Interfaces:**
- Produces: `unique_identifiers(raw_ids: Sequence[str]) -> dict[str, str]` — insertion-ordered, collision-free sanitized names; raises `ValueError` on duplicate raw ids.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/geometry/test_naming.py`:

```python
def test_unique_identifiers_disambiguates_collisions() -> None:
    mapping = unique_identifiers(["a b", "a-b", "a_b"])
    assert mapping == {"a b": "a_b", "a-b": "a_b_2", "a_b": "a_b_3"}


def test_unique_identifiers_skips_already_taken_suffix() -> None:
    mapping = unique_identifiers(["a b", "a_b_2", "a-b"])
    assert mapping == {"a b": "a_b", "a_b_2": "a_b_2", "a-b": "a_b_3"}


def test_unique_identifiers_rejects_duplicate_raw_ids() -> None:
    with pytest.raises(ValueError, match="Duplicate"):
        unique_identifiers(["w1", "w1"])
```

Add `import pytest` and extend the existing `naming` import with `unique_identifiers`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/geometry/test_naming.py -q`
Expected: FAIL — `ImportError: cannot import name 'unique_identifiers'`.

- [ ] **Step 3: Implement**

Append to `src/inductor_designer/geometry/naming.py` (add `from collections.abc import Sequence` to imports):

```python
def unique_identifiers(raw_ids: Sequence[str]) -> dict[str, str]:
    """Deterministic collision-free sanitized identifiers, keyed by raw id.

    Later collisions get an ``_2``, ``_3``, ... suffix in input order.
    """
    result: dict[str, str] = {}
    taken: set[str] = set()
    for raw in raw_ids:
        if raw in result:
            raise ValueError(f"Duplicate raw identifier: {raw!r}")
        candidate = sanitize_identifier(raw)
        if candidate in taken:
            suffix = 2
            while f"{candidate}_{suffix}" in taken:
                suffix += 1
            candidate = f"{candidate}_{suffix}"
        taken.add(candidate)
        result[raw] = candidate
    return result
```

- [ ] **Step 4: Run gates**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/geometry -q` then `-m ruff check .`, `-m mypy`, `python tools/check_architecture.py`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/inductor_designer/geometry/naming.py tests/unit/geometry/test_naming.py
git commit -m "feat(geometry): add collision-free unique_identifiers map"
```

---

### Task 2: Core cross-section profile

Maxwell builds the core by revolving its cross-section outline around Z. Produce that outline in the θ=0 half-plane (the XZ plane), honoring the corner radius when present.

**Files:**
- Create: `src/inductor_designer/geometry/core_profile.py`
- Test: `tests/unit/geometry/test_core_profile.py`

**Interfaces:**
- Consumes: `FinishedCore` (`geometry/core_solid.py`), `LineSegment`/`ArcSegment`/`Vec3` (`geometry/primitives.py`).
- Produces: `build_core_profile(core: FinishedCore) -> tuple[PathSegment, ...]` — closed outline, 4 lines when `corner_radius_m == 0`, else 8 segments (arc sweeps `+π/2` with normal `(0, 1, 0)`, matching the committed turn-loop convention).

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/geometry/test_core_profile.py`:

```python
from __future__ import annotations

from inductor_designer.geometry.core_profile import build_core_profile
from inductor_designer.geometry.core_solid import FinishedCore
from inductor_designer.geometry.primitives import ArcSegment, LineSegment, Vec3


def _endpoint(segment: LineSegment | ArcSegment) -> Vec3:
    return segment.end if isinstance(segment, LineSegment) else segment.end()


def _is_closed(profile: tuple[LineSegment | ArcSegment, ...]) -> bool:
    for first, second in zip(profile, profile[1:]):
        if (_endpoint(first) - second.start).norm() > 1e-9:
            return False
    return (_endpoint(profile[-1]) - profile[0].start).norm() < 1e-9


def test_rectangle_profile_without_corner_radius() -> None:
    core = FinishedCore(r_inner_m=0.01, r_outer_m=0.02, half_height_m=0.005, corner_radius_m=0.0)
    profile = build_core_profile(core)
    assert len(profile) == 4
    assert all(isinstance(segment, LineSegment) for segment in profile)
    assert profile[0].start == Vec3(0.01, 0.0, -0.005)
    assert _is_closed(profile)


def test_rounded_profile_closes_and_lies_in_xz_plane() -> None:
    core = FinishedCore(r_inner_m=0.01, r_outer_m=0.02, half_height_m=0.005, corner_radius_m=0.001)
    profile = build_core_profile(core)
    assert len(profile) == 8
    assert _is_closed(profile)
    for segment in profile:
        assert abs(segment.start.y) < 1e-12
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/geometry/test_core_profile.py -q`
Expected: FAIL — `ModuleNotFoundError: inductor_designer.geometry.core_profile`.

- [ ] **Step 3: Implement**

Create `src/inductor_designer/geometry/core_profile.py`:

```python
from __future__ import annotations

import math

from inductor_designer.geometry.core_solid import FinishedCore
from inductor_designer.geometry.primitives import ArcSegment, LineSegment, PathSegment, Vec3


def build_core_profile(core: FinishedCore) -> tuple[PathSegment, ...]:
    """Closed core cross-section outline in the θ=0 half-plane (XZ plane).

    Revolving this outline around Z yields the finished core solid. Arc
    sweeps are +π/2 with normal (0, 1, 0), the same convention as the
    committed turn loops.
    """
    hh = core.half_height_m
    c = core.corner_radius_m
    r_in = core.r_inner_m
    r_out = core.r_outer_m

    def p(r: float, z: float) -> Vec3:
        return Vec3(r, 0.0, z)

    if c == 0.0:
        return (
            LineSegment(p(r_in, -hh), p(r_in, hh)),
            LineSegment(p(r_in, hh), p(r_out, hh)),
            LineSegment(p(r_out, hh), p(r_out, -hh)),
            LineSegment(p(r_out, -hh), p(r_in, -hh)),
        )

    normal = Vec3(0.0, 1.0, 0.0)
    quarter = math.pi / 2.0
    return (
        LineSegment(p(r_in, -(hh - c)), p(r_in, hh - c)),
        ArcSegment(p(r_in + c, hh - c), normal, p(r_in, hh - c), quarter),
        LineSegment(p(r_in + c, hh), p(r_out - c, hh)),
        ArcSegment(p(r_out - c, hh - c), normal, p(r_out - c, hh), quarter),
        LineSegment(p(r_out, hh - c), p(r_out, -(hh - c))),
        ArcSegment(p(r_out - c, -(hh - c)), normal, p(r_out, -(hh - c)), quarter),
        LineSegment(p(r_out - c, -hh), p(r_in + c, -hh)),
        ArcSegment(p(r_in + c, -(hh - c)), normal, p(r_in + c, -hh), quarter),
    )
```

- [ ] **Step 4: Run gates**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/geometry -q`, then ruff, mypy, architecture check.
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/inductor_designer/geometry/core_profile.py tests/unit/geometry/test_core_profile.py
git commit -m "feat(geometry): core cross-section profile for Maxwell revolve"
```

---

### Task 3: Terminal disks

One coil terminal per closed turn (locked M2/ROADMAP decision). The terminal is a circular sheet crossing the conductor at the midpoint of the bottom straight run; its normal is the radial direction at the station angle.

**Files:**
- Create: `src/inductor_designer/geometry/terminals.py`
- Test: `tests/unit/geometry/test_terminals.py`

**Interfaces:**
- Consumes: `build_turn_loop` (segment index 6 = bottom straight run), `FinishedCore`, `Vec3`.
- Produces: `TerminalDisk(center: Vec3, station_deg: float, radius_m: float)` with property `normal -> Vec3`; `build_terminal_disk(core, layer, insulated_diameter_m, bare_diameter_m, station_deg) -> TerminalDisk`.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/geometry/test_terminals.py`:

```python
from __future__ import annotations

from inductor_designer.geometry.core_solid import FinishedCore
from inductor_designer.geometry.primitives import Vec3
from inductor_designer.geometry.terminals import build_terminal_disk

CORE = FinishedCore(r_inner_m=0.01, r_outer_m=0.02, half_height_m=0.005, corner_radius_m=0.0)


def test_disk_sits_at_bottom_run_midpoint() -> None:
    disk = build_terminal_disk(
        CORE, layer=1, insulated_diameter_m=0.001, bare_diameter_m=0.0008, station_deg=0.0
    )
    # layer 1 radial build = 0.0005; bottom run at z = -(0.005 + 0.0005)
    assert disk.center == Vec3(0.015, 0.0, -0.0055)
    assert disk.radius_m == 0.0004
    assert disk.normal == Vec3(1.0, 0.0, 0.0)


def test_disk_rotates_with_station() -> None:
    disk = build_terminal_disk(
        CORE, layer=1, insulated_diameter_m=0.001, bare_diameter_m=0.0008, station_deg=90.0
    )
    assert disk.center == Vec3(0.0, 0.015, -0.0055)
    assert disk.normal == Vec3(0.0, 1.0, 0.0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/geometry/test_terminals.py -q`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

Create `src/inductor_designer/geometry/terminals.py`:

```python
from __future__ import annotations

import math
from dataclasses import dataclass

from inductor_designer.geometry.core_solid import FinishedCore
from inductor_designer.geometry.primitives import LineSegment, Vec3
from inductor_designer.geometry.turn_path import build_turn_loop


@dataclass(frozen=True, slots=True)
class TerminalDisk:
    """Circular coil-terminal sheet crossing one turn conductor."""

    center: Vec3
    station_deg: float
    radius_m: float

    @property
    def normal(self) -> Vec3:
        """Radial unit vector at the station: positive = outward current."""
        theta = math.radians(self.station_deg)
        return Vec3(round(math.cos(theta), 9), round(math.sin(theta), 9), 0.0)


def build_terminal_disk(
    core: FinishedCore,
    layer: int,
    insulated_diameter_m: float,
    bare_diameter_m: float,
    station_deg: float,
) -> TerminalDisk:
    loop = build_turn_loop(core, layer, insulated_diameter_m, station_deg)
    bottom = loop[6]
    if not isinstance(bottom, LineSegment):
        raise TypeError("Turn loop segment 6 must be the bottom straight run")
    center = (bottom.start + (bottom.end - bottom.start).scaled(0.5)).rounded()
    return TerminalDisk(
        center=center,
        station_deg=station_deg,
        radius_m=round(bare_diameter_m / 2.0, 9),
    )
```

- [ ] **Step 4: Run gates** — geometry tests, ruff, mypy, architecture check. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/inductor_designer/geometry/terminals.py tests/unit/geometry/test_terminals.py
git commit -m "feat(geometry): terminal disk placement on turn loops"
```

---

### Task 4: Maxwell design-plan types and core material spec

Solver-independent plan dataclasses in `simulation` (pure package — no pathlib/os), plus the D2 material derivation.

**Files:**
- Create: `src/inductor_designer/simulation/maxwell_plan.py`
- Test: `tests/unit/simulation/test_maxwell_plan.py`

**Interfaces:**
- Consumes: `PathSegment`, `TerminalDisk`, `CoreRecord`/`CoreFamily`/`ReviewStatus`, `sanitize_identifier`.
- Produces (all `@dataclass(frozen=True, slots=True)` unless noted):
  - `Polarity(str, Enum)`: `POSITIVE = "Positive"`, `NEGATIVE = "Negative"`.
  - `MaterialSpec(name: str, relative_permeability: float, conductivity_s_per_m: float, draft: bool)`.
  - `TerminalPlan(name: str, disk: TerminalDisk, polarity: Polarity)`.
  - `TurnPlan(name: str, segments: tuple[PathSegment, ...], bare_diameter_m: float, terminal: TerminalPlan)`.
  - `WindingGroupPlan(name: str, winding_id: str, is_solid: bool, current_peak_a: float, phase_deg: float, dc_current_a: float, turns: tuple[TurnPlan, ...])`.
  - `CorePlan(name: str, profile: tuple[PathSegment, ...], material: MaterialSpec)`.
  - `RegionPlan(padding_percent: float)`, `MeshPlan(conductor_max_length_m: float, core_max_length_m: float)`, `SetupPlan(name: str, frequency_hz: float, maximum_passes: int, percent_error: float)`, `ReportPlan(name: str, expression: str)`.
  - `Maxwell3dDesignPlan(design_name: str, solution_type: str, core: CorePlan, windings: tuple[WindingGroupPlan, ...], region: RegionPlan, mesh: MeshPlan, setup: SetupPlan, matrix_name: str, reports: tuple[ReportPlan, ...], notes: tuple[str, ...])`.
  - Constants: `SOLUTION_TYPE = "EddyCurrent"`, `DESIGN_NAME = "Inductor3D"`, `SETUP_NAME = "Setup1"`, `MATRIX_NAME = "Matrix1"`, `COPPER_MATERIAL = "copper"`, `REGION_PADDING_PERCENT = 100.0`.
  - `PlanBuildError(ValueError)` with `.issues: tuple[str, ...]` (same shape as `GeometryModelError`).
  - `core_material_spec(record: CoreRecord) -> MaterialSpec`.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/simulation/test_maxwell_plan.py` (create `tests/unit/simulation/__init__.py` if the suite uses package-style tests — mirror whatever `tests/unit/geometry/` does):

```python
from __future__ import annotations

import pytest

from inductor_designer.domain.catalog_records import (
    CoreFamily,
    CoreRecord,
    Dimension,
    ReviewStatus,
)
from inductor_designer.materials.identity import MaterialRef
from inductor_designer.simulation.maxwell_plan import PlanBuildError, core_material_spec


def make_core_record(
    family: CoreFamily = CoreFamily.POWDER_TOROID,
    grade: str = "60",
    review_status: ReviewStatus = ReviewStatus.REVIEWED,
) -> CoreRecord:
    return CoreRecord(
        manufacturer="Magnetics",
        family=family,
        part_number="0077071A7",
        material=MaterialRef(manufacturer="Magnetics", name="Kool Mu", grade=grade),
        coating="black epoxy",
        catalog_revision="magnetics-powder-2025",
        source_url="https://example.com/catalog.pdf",
        source_page=173,
        outer_diameter=Dimension(nominal_m=0.03279, min_m=None, max_m=0.03366),
        inner_diameter=Dimension(nominal_m=0.02009, min_m=0.01946, max_m=None),
        height=Dimension(nominal_m=0.01067, min_m=None, max_m=0.01143),
        effective_area_m2=6.56e-05,
        path_length_m=0.0814,
        volume_m3=5.34e-06,
        al_value_nh=61.0,
        review_status=review_status,
        reviewed_by="Fabio Posser",
    )


def test_powder_grade_becomes_linear_material() -> None:
    spec = core_material_spec(make_core_record())
    assert spec.name == "Magnetics_Kool_Mu_60"
    assert spec.relative_permeability == 60.0
    assert spec.conductivity_s_per_m == 0.0
    assert spec.draft is False


def test_draft_record_marks_material_draft() -> None:
    spec = core_material_spec(make_core_record(review_status=ReviewStatus.DRAFT))
    assert spec.draft is True


def test_ferrite_family_is_refused() -> None:
    with pytest.raises(PlanBuildError, match="powder"):
        core_material_spec(make_core_record(family=CoreFamily.FERRITE_TOROID))


def test_non_numeric_grade_is_refused() -> None:
    with pytest.raises(PlanBuildError, match="numeric"):
        core_material_spec(make_core_record(grade="N87"))
```

Note: if `MaterialRef` field names differ from `manufacturer`/`name`/`grade`, match `src/inductor_designer/materials/identity.py`. Ferrite `CoreRecord` construction may trip `__post_init__` invariants unrelated to this test — if so, keep the powder dimensions as given (they are valid).

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/simulation/test_maxwell_plan.py -q`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

Create `src/inductor_designer/simulation/maxwell_plan.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from inductor_designer.domain.catalog_records import CoreFamily, CoreRecord, ReviewStatus
from inductor_designer.geometry.naming import sanitize_identifier
from inductor_designer.geometry.primitives import PathSegment
from inductor_designer.geometry.terminals import TerminalDisk

SOLUTION_TYPE = "EddyCurrent"
DESIGN_NAME = "Inductor3D"
SETUP_NAME = "Setup1"
MATRIX_NAME = "Matrix1"
COPPER_MATERIAL = "copper"
REGION_PADDING_PERCENT = 100.0


class PlanBuildError(ValueError):
    def __init__(self, issues: tuple[str, ...]) -> None:
        super().__init__("; ".join(issues))
        self.issues = issues


class Polarity(str, Enum):
    POSITIVE = "Positive"
    NEGATIVE = "Negative"


@dataclass(frozen=True, slots=True)
class MaterialSpec:
    """Linear material for Maxwell; Milestone 5 replaces this with real records."""

    name: str
    relative_permeability: float
    conductivity_s_per_m: float
    draft: bool


@dataclass(frozen=True, slots=True)
class TerminalPlan:
    name: str
    disk: TerminalDisk
    polarity: Polarity


@dataclass(frozen=True, slots=True)
class TurnPlan:
    name: str
    segments: tuple[PathSegment, ...]
    bare_diameter_m: float
    terminal: TerminalPlan


@dataclass(frozen=True, slots=True)
class WindingGroupPlan:
    name: str
    winding_id: str
    is_solid: bool
    current_peak_a: float
    phase_deg: float
    dc_current_a: float
    turns: tuple[TurnPlan, ...]


@dataclass(frozen=True, slots=True)
class CorePlan:
    name: str
    profile: tuple[PathSegment, ...]
    material: MaterialSpec


@dataclass(frozen=True, slots=True)
class RegionPlan:
    padding_percent: float


@dataclass(frozen=True, slots=True)
class MeshPlan:
    conductor_max_length_m: float
    core_max_length_m: float


@dataclass(frozen=True, slots=True)
class SetupPlan:
    name: str
    frequency_hz: float
    maximum_passes: int
    percent_error: float


@dataclass(frozen=True, slots=True)
class ReportPlan:
    name: str
    expression: str


@dataclass(frozen=True, slots=True)
class Maxwell3dDesignPlan:
    design_name: str
    solution_type: str
    core: CorePlan
    windings: tuple[WindingGroupPlan, ...]
    region: RegionPlan
    mesh: MeshPlan
    setup: SetupPlan
    matrix_name: str
    reports: tuple[ReportPlan, ...]
    notes: tuple[str, ...]


def core_material_spec(record: CoreRecord) -> MaterialSpec:
    """Milestone 3 material model: powder grade = linear relative permeability.

    Real property data (B-H curves, core loss) arrives with Material Studio in
    Milestone 5; ferrites stay unsupported until then.
    """
    if record.family is not CoreFamily.POWDER_TOROID:
        raise PlanBuildError(
            (
                f"Core family {record.family.value!r} has no Milestone 3 material model; "
                "only powder toroids export.",
            )
        )
    try:
        mu = float(record.material.grade)
    except ValueError as error:
        raise PlanBuildError(
            (f"Powder grade {record.material.grade!r} is not a numeric permeability.",)
        ) from error
    if mu <= 0.0:
        raise PlanBuildError((f"Powder grade {record.material.grade!r} must be positive.",))
    name = sanitize_identifier(
        f"{record.material.manufacturer}_{record.material.name}_{record.material.grade}"
    )
    return MaterialSpec(
        name=name,
        relative_permeability=mu,
        conductivity_s_per_m=0.0,
        draft=record.review_status is not ReviewStatus.REVIEWED,
    )
```

- [ ] **Step 4: Run gates** — simulation tests, ruff, mypy, architecture check (simulation imports only domain/geometry/materials — legal).
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/inductor_designer/simulation/maxwell_plan.py tests/unit/simulation/test_maxwell_plan.py
git commit -m "feat(simulation): Maxwell 3D design-plan types and material spec"
```

---

### Task 5: Plan builder

Compose geometry outputs + winding definitions into a complete `Maxwell3dDesignPlan`.

**Files:**
- Create: `src/inductor_designer/simulation/plan_builder.py`
- Test: `tests/unit/simulation/test_plan_builder.py`

**Interfaces:**
- Consumes: `FinishedCore`, `PackedWinding` (fields: `winding_id`, `insulated_diameter_m`, `layers[].index/.station_deg`), `WindingDefinition`, `CoreRecord`, `build_turn_loop`, `build_terminal_disk`, `build_core_profile`, `unique_identifiers`, `core_name`, Task 4 types.
- Produces: `build_maxwell3d_plan(core: FinishedCore, core_record: CoreRecord, packings: Sequence[PackedWinding], windings: Sequence[WindingDefinition], bare_diameter_m: Mapping[str, float]) -> Maxwell3dDesignPlan`; raises `PlanBuildError`.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/simulation/test_plan_builder.py`:

```python
from __future__ import annotations

import pytest

from inductor_designer.domain.winding import (
    ConductorMode,
    CurrentDirection,
    WindingDefinition,
    WindingDirection,
)
from inductor_designer.geometry.core_solid import FinishedCore
from inductor_designer.geometry.packing import WindingSpec, pack_winding
from inductor_designer.simulation.maxwell_plan import PlanBuildError, Polarity
from inductor_designer.simulation.plan_builder import build_maxwell3d_plan
from tests.unit.simulation.test_maxwell_plan import make_core_record

CORE = FinishedCore(r_inner_m=0.00973, r_outer_m=0.01683, half_height_m=0.005715, corner_radius_m=0.0)
BARE = 0.001


def make_definition(**overrides: object) -> WindingDefinition:
    values: dict[str, object] = {
        "winding_id": "w1",
        "label": "Primary",
        "turns": 4,
        "conductor_name": "AWG 18",
        "mode": ConductorMode.SOLID,
        "start_angle_deg": 0.0,
        "sector_deg": 150.0,
        "min_spacing_m": 0.0002,
        "min_clearance_m": 0.001,
        "winding_direction": WindingDirection.COUNTERCLOCKWISE,
        "current_direction": CurrentDirection.FORWARD,
        "terminal_intent": "",
        "ac_magnitude_a": 2.0,
        "ac_phase_deg": 0.0,
        "frequency_hz": 100_000.0,
        "dc_current_a": 0.0,
    }
    values.update(overrides)
    return WindingDefinition(**values)  # type: ignore[arg-type]


def pack(definition: WindingDefinition) -> object:
    return pack_winding(
        CORE,
        WindingSpec(
            winding_id=definition.winding_id,
            turns=definition.turns,
            insulated_diameter_m=0.0011,
            start_deg=definition.start_angle_deg,
            sector_deg=definition.sector_deg,
            min_spacing_m=definition.min_spacing_m,
            min_clearance_m=definition.min_clearance_m,
        ),
    )


def build(definitions: tuple[WindingDefinition, ...]) -> object:
    packings = tuple(pack(d) for d in definitions)
    return build_maxwell3d_plan(
        CORE,
        make_core_record(),
        packings,
        definitions,
        {d.winding_id: BARE for d in definitions},
    )


def test_plan_shape_and_names() -> None:
    plan = build((make_definition(),))
    assert plan.design_name == "Inductor3D"
    assert plan.solution_type == "EddyCurrent"
    assert plan.core.name == "Core"
    group = plan.windings[0]
    assert group.name == "w1"
    assert [t.name for t in group.turns] == [
        "w1_L01_T001", "w1_L01_T002", "w1_L01_T003", "w1_L01_T004",
    ]
    assert group.turns[0].terminal.name == "w1_L01_T001_Term"
    assert group.turns[0].bare_diameter_m == BARE
    assert len(group.turns[0].segments) == 8


def test_colliding_ids_stay_distinct() -> None:
    plan = build(
        (
            make_definition(winding_id="w 1", start_angle_deg=0.0, sector_deg=100.0),
            make_definition(winding_id="w-1", start_angle_deg=180.0, sector_deg=100.0),
        )
    )
    assert [g.name for g in plan.windings] == ["w_1", "w_1_2"]


def test_polarity_convention() -> None:
    cases = [
        (CurrentDirection.FORWARD, WindingDirection.COUNTERCLOCKWISE, Polarity.POSITIVE),
        (CurrentDirection.FORWARD, WindingDirection.CLOCKWISE, Polarity.NEGATIVE),
        (CurrentDirection.REVERSE, WindingDirection.COUNTERCLOCKWISE, Polarity.NEGATIVE),
        (CurrentDirection.REVERSE, WindingDirection.CLOCKWISE, Polarity.POSITIVE),
    ]
    for current, direction, expected in cases:
        plan = build((make_definition(current_direction=current, winding_direction=direction),))
        assert plan.windings[0].turns[0].terminal.polarity is expected, (current, direction)


def test_mixed_frequencies_refused() -> None:
    with pytest.raises(PlanBuildError, match="frequency"):
        build(
            (
                make_definition(winding_id="w1", sector_deg=100.0),
                make_definition(
                    winding_id="w2", start_angle_deg=180.0, sector_deg=100.0,
                    frequency_hz=50_000.0,
                ),
            )
        )


def test_setup_mesh_reports_and_notes() -> None:
    plan = build((make_definition(dc_current_a=5.0),))
    assert plan.setup.frequency_hz == 100_000.0
    assert plan.mesh.conductor_max_length_m == round(1.5 * BARE, 9)
    assert plan.mesh.core_max_length_m == round(min(0.0071, 0.01143) / 3.0, 9)
    assert [r.expression for r in plan.reports] == ["Matrix1.R(w1,w1)", "Matrix1.L(w1,w1)"]
    assert any("Milestone 4" in note for note in plan.notes)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/simulation/test_plan_builder.py -q`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

Create `src/inductor_designer/simulation/plan_builder.py`:

```python
from __future__ import annotations

from collections.abc import Mapping, Sequence

from inductor_designer.domain.catalog_records import CoreRecord
from inductor_designer.domain.winding import (
    ConductorMode,
    CurrentDirection,
    WindingDefinition,
    WindingDirection,
)
from inductor_designer.geometry.core_profile import build_core_profile
from inductor_designer.geometry.core_solid import FinishedCore
from inductor_designer.geometry.naming import core_name, unique_identifiers
from inductor_designer.geometry.packing import PackedWinding
from inductor_designer.geometry.terminals import build_terminal_disk
from inductor_designer.geometry.turn_path import build_turn_loop
from inductor_designer.simulation.maxwell_plan import (
    DESIGN_NAME,
    MATRIX_NAME,
    REGION_PADDING_PERCENT,
    SETUP_NAME,
    SOLUTION_TYPE,
    CorePlan,
    Maxwell3dDesignPlan,
    MeshPlan,
    PlanBuildError,
    Polarity,
    RegionPlan,
    ReportPlan,
    SetupPlan,
    TerminalPlan,
    TurnPlan,
    WindingGroupPlan,
    core_material_spec,
)


def _polarity(definition: WindingDefinition) -> Polarity:
    positive = (definition.current_direction is CurrentDirection.FORWARD) == (
        definition.winding_direction is WindingDirection.COUNTERCLOCKWISE
    )
    return Polarity.POSITIVE if positive else Polarity.NEGATIVE


def build_maxwell3d_plan(
    core: FinishedCore,
    core_record: CoreRecord,
    packings: Sequence[PackedWinding],
    windings: Sequence[WindingDefinition],
    bare_diameter_m: Mapping[str, float],
) -> Maxwell3dDesignPlan:
    issues: list[str] = []
    by_id = {definition.winding_id: definition for definition in windings}
    if not packings:
        issues.append("No packed windings; nothing to export.")
    missing = [p.winding_id for p in packings if p.winding_id not in by_id]
    if missing:
        issues.append(f"Packings without winding definitions: {missing}.")
    frequencies = sorted({definition.frequency_hz for definition in windings})
    if len(frequencies) > 1:
        issues.append(f"All windings must share one frequency; got {frequencies}.")
    if issues:
        raise PlanBuildError(tuple(issues))
    material = core_material_spec(core_record)

    identifiers = unique_identifiers([packing.winding_id for packing in packings])
    groups: list[WindingGroupPlan] = []
    max_bare = 0.0
    for packing in packings:
        definition = by_id[packing.winding_id]
        base = identifiers[packing.winding_id]
        bare = bare_diameter_m[packing.winding_id]
        max_bare = max(max_bare, bare)
        polarity = _polarity(definition)
        turns: list[TurnPlan] = []
        counter = 1
        for layer in packing.layers:
            for station in layer.station_deg:
                name = f"{base}_L{layer.index:02d}_T{counter:03d}"
                turns.append(
                    TurnPlan(
                        name=name,
                        segments=build_turn_loop(
                            core, layer.index, packing.insulated_diameter_m, station
                        ),
                        bare_diameter_m=bare,
                        terminal=TerminalPlan(
                            name=f"{name}_Term",
                            disk=build_terminal_disk(
                                core,
                                layer.index,
                                packing.insulated_diameter_m,
                                bare,
                                station,
                            ),
                            polarity=polarity,
                        ),
                    )
                )
                counter += 1
        groups.append(
            WindingGroupPlan(
                name=base,
                winding_id=packing.winding_id,
                is_solid=definition.mode is ConductorMode.SOLID,
                current_peak_a=definition.ac_magnitude_a,
                phase_deg=definition.ac_phase_deg,
                dc_current_a=definition.dc_current_a,
                turns=tuple(turns),
            )
        )

    reports: list[ReportPlan] = []
    for group in groups:
        reports.append(
            ReportPlan(
                name=f"{group.name}_Resistance",
                expression=f"{MATRIX_NAME}.R({group.name},{group.name})",
            )
        )
        reports.append(
            ReportPlan(
                name=f"{group.name}_Inductance",
                expression=f"{MATRIX_NAME}.L({group.name},{group.name})",
            )
        )

    notes: list[str] = []
    if material.draft:
        notes.append(
            f"Core material {material.name} derives from a draft catalog record; "
            "verify against the manufacturer catalog before trusting results."
        )
    if any(group.dc_current_a != 0.0 for group in groups):
        notes.append(
            "DC operating currents are recorded but not applied; DC bias is Milestone 4 work."
        )

    width = core.r_outer_m - core.r_inner_m
    height = 2.0 * core.half_height_m
    return Maxwell3dDesignPlan(
        design_name=DESIGN_NAME,
        solution_type=SOLUTION_TYPE,
        core=CorePlan(name=core_name(), profile=build_core_profile(core), material=material),
        windings=tuple(groups),
        region=RegionPlan(padding_percent=REGION_PADDING_PERCENT),
        mesh=MeshPlan(
            conductor_max_length_m=round(1.5 * max_bare, 9),
            core_max_length_m=round(min(width, height) / 3.0, 9),
        ),
        setup=SetupPlan(
            name=SETUP_NAME,
            frequency_hz=frequencies[0],
            maximum_passes=10,
            percent_error=1.0,
        ),
        matrix_name=MATRIX_NAME,
        reports=tuple(reports),
        notes=tuple(notes),
    )
```

Note the test's `core_max_length_m` expectation uses `width = 0.01683 - 0.00973 = 0.0071` and `height = 0.01143`; `min/3 = 0.002366667` after rounding — compute the literal in the test from the same expression, as written.

- [ ] **Step 4: Run gates** — simulation tests, ruff, mypy, architecture check. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/inductor_designer/simulation/plan_builder.py tests/unit/simulation/test_plan_builder.py
git commit -m "feat(simulation): build Maxwell 3D design plan from geometry"
```

---

### Task 6: Export port, recording fake, contract test

Mirror the M0 `AedtGateway` port pattern.

**Files:**
- Create: `src/inductor_designer/application/ports/maxwell_exporter.py`
- Create: `tests/fakes/maxwell_exporter.py`
- Test: `tests/contract/test_maxwell_exporter_contract.py`

**Interfaces:**
- Consumes: `Maxwell3dDesignPlan`, `AedtRelease`, `AedtEdition`.
- Produces:
  - `STAGE_NAMES: tuple[str, ...] = ("launch", "units", "materials", "core", "windings", "terminals", "excitations", "eddy", "region", "mesh", "setup", "matrix", "reports", "validate", "save")`.
  - `Maxwell3dExportRequest(plan, release: AedtRelease, edition: AedtEdition, non_graphical: bool, output_directory: Path, project_name: str)`.
  - `StageRecord(name: str, succeeded: bool, message: str)`.
  - `Maxwell3dExportResult(project_path: Path, design_name: str, pyaedt_version: str, stages: tuple[StageRecord, ...])` with method `succeeded() -> bool` (all stages present and succeeded).
  - `class Maxwell3dExporter(Protocol): def export(self, request: Maxwell3dExportRequest) -> Maxwell3dExportResult: ...`
  - Fake: `RecordingMaxwell3dExporter` with `.requests: list[Maxwell3dExportRequest]`; returns a fully-succeeded result, `pyaedt_version="recording-fake"`.

- [ ] **Step 1: Write the failing contract test**

Create `tests/contract/test_maxwell_exporter_contract.py`:

```python
from __future__ import annotations

from pathlib import Path

from inductor_designer.application.ports.maxwell_exporter import (
    STAGE_NAMES,
    Maxwell3dExportRequest,
)
from inductor_designer.domain.aedt_target import AedtEdition, AedtRelease
from tests.fakes.maxwell_exporter import RecordingMaxwell3dExporter
from tests.unit.simulation.test_plan_builder import build, make_definition


def make_request(tmp_path: Path) -> Maxwell3dExportRequest:
    return Maxwell3dExportRequest(
        plan=build((make_definition(),)),  # type: ignore[arg-type]
        release=AedtRelease(2025, 2),
        edition=AedtEdition.COMMERCIAL,
        non_graphical=True,
        output_directory=tmp_path,
        project_name="Boost_inductor",
    )


def test_fake_records_request_and_reports_full_stage_sequence(tmp_path: Path) -> None:
    exporter = RecordingMaxwell3dExporter()
    request = make_request(tmp_path)
    result = exporter.export(request)
    assert exporter.requests == [request]
    assert tuple(stage.name for stage in result.stages) == STAGE_NAMES
    assert result.succeeded()
    assert result.project_path == tmp_path / "Boost_inductor.aedt"
    assert result.design_name == "Inductor3D"


def test_result_not_succeeded_when_stages_incomplete(tmp_path: Path) -> None:
    exporter = RecordingMaxwell3dExporter()
    full = exporter.export(make_request(tmp_path))
    from dataclasses import replace

    truncated = replace(full, stages=full.stages[:3])
    assert not truncated.succeeded()
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/contract/test_maxwell_exporter_contract.py -q`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement the port**

Create `src/inductor_designer/application/ports/maxwell_exporter.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from inductor_designer.domain.aedt_target import AedtEdition, AedtRelease
from inductor_designer.simulation.maxwell_plan import Maxwell3dDesignPlan

STAGE_NAMES: tuple[str, ...] = (
    "launch",
    "units",
    "materials",
    "core",
    "windings",
    "terminals",
    "excitations",
    "eddy",
    "region",
    "mesh",
    "setup",
    "matrix",
    "reports",
    "validate",
    "save",
)


@dataclass(frozen=True, slots=True)
class Maxwell3dExportRequest:
    plan: Maxwell3dDesignPlan
    release: AedtRelease
    edition: AedtEdition
    non_graphical: bool
    output_directory: Path
    project_name: str


@dataclass(frozen=True, slots=True)
class StageRecord:
    name: str
    succeeded: bool
    message: str


@dataclass(frozen=True, slots=True)
class Maxwell3dExportResult:
    project_path: Path
    design_name: str
    pyaedt_version: str
    stages: tuple[StageRecord, ...]

    def succeeded(self) -> bool:
        """A partial design is never successful (design spec §12)."""
        return len(self.stages) == len(STAGE_NAMES) and all(
            stage.succeeded for stage in self.stages
        )


class Maxwell3dExporter(Protocol):
    def export(self, request: Maxwell3dExportRequest) -> Maxwell3dExportResult: ...
```

Create `tests/fakes/maxwell_exporter.py`:

```python
from __future__ import annotations

from inductor_designer.application.ports.maxwell_exporter import (
    STAGE_NAMES,
    Maxwell3dExportRequest,
    Maxwell3dExportResult,
    StageRecord,
)


class RecordingMaxwell3dExporter:
    """Port fake: records requests, never launches AEDT."""

    def __init__(self) -> None:
        self.requests: list[Maxwell3dExportRequest] = []

    def export(self, request: Maxwell3dExportRequest) -> Maxwell3dExportResult:
        self.requests.append(request)
        return Maxwell3dExportResult(
            project_path=request.output_directory / f"{request.project_name}.aedt",
            design_name=request.plan.design_name,
            pyaedt_version="recording-fake",
            stages=tuple(
                StageRecord(name=name, succeeded=True, message="recorded")
                for name in STAGE_NAMES
            ),
        )
```

- [ ] **Step 4: Run gates** — contract tests, ruff, mypy, architecture check (`application` importing `pathlib` in DTOs is allowed). Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/inductor_designer/application/ports/maxwell_exporter.py tests/fakes/maxwell_exporter.py tests/contract/test_maxwell_exporter_contract.py
git commit -m "feat(application): Maxwell 3D exporter port with recording fake"
```

---

### Task 7: Application export service and generation manifest

Orchestrate project → geometry model → plan → export; refuse 2D projects, manual cores, and collisions; emit a deterministic generation-manifest JSON.

**Files:**
- Create: `src/inductor_designer/application/services/maxwell_export.py`
- Test: `tests/unit/application/test_maxwell_export.py`

**Interfaces:**
- Consumes: `build_geometry_model`, `build_maxwell3d_plan`/`PlanBuildError`, port types, `CatalogCoreSelection`, `ModelDimension`, `sanitize_identifier`.
- Produces:
  - `MaxwellExportBlocked(ValueError)` with `.issues: tuple[str, ...]`.
  - `MaxwellExportOutcome(plan: Maxwell3dDesignPlan, result: Maxwell3dExportResult)` (frozen slots dataclass).
  - `export_maxwell3d(project: InductorProject, catalog: CatalogRepository, exporter: Maxwell3dExporter, output_directory: Path, *, non_graphical: bool = True) -> MaxwellExportOutcome`.
  - `generation_manifest_json(outcome: MaxwellExportOutcome) -> str` — `json.dumps(..., indent=2, sort_keys=True) + "\n"`.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/application/test_maxwell_export.py`:

```python
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from inductor_designer.application.services.maxwell_export import (
    MaxwellExportBlocked,
    export_maxwell3d,
    generation_manifest_json,
)
from inductor_designer.domain.aedt_target import ModelDimension
from inductor_designer.domain.project import ManualCoreSelection
from tests.fakes.maxwell_exporter import RecordingMaxwell3dExporter
from tests.unit.application.test_geometry_model import CATALOG
from tests.unit.domain.test_project import make_project, make_winding


def three_d_project() -> object:
    return replace(
        make_project(
            windings=(
                make_winding(winding_id="w1", start_angle_deg=0.0, sector_deg=150.0, turns=10),
                make_winding(winding_id="w2", start_angle_deg=180.0, sector_deg=150.0, turns=10),
            )
        ),
        dimension_mode=ModelDimension.THREE_D,
    )


def test_export_builds_plan_and_calls_exporter(tmp_path: Path) -> None:
    exporter = RecordingMaxwell3dExporter()
    outcome = export_maxwell3d(three_d_project(), CATALOG, exporter, tmp_path)  # type: ignore[arg-type]
    assert outcome.result.succeeded()
    request = exporter.requests[0]
    assert request.project_name == "Boost_inductor"
    assert [g.name for g in request.plan.windings] == ["w1", "w2"]
    assert request.non_graphical is True


def test_two_d_project_is_blocked(tmp_path: Path) -> None:
    project = replace(three_d_project(), dimension_mode=ModelDimension.TWO_D)  # type: ignore[type-var]
    with pytest.raises(MaxwellExportBlocked, match="3d"):
        export_maxwell3d(project, CATALOG, RecordingMaxwell3dExporter(), tmp_path)  # type: ignore[arg-type]


def test_manual_core_is_blocked(tmp_path: Path) -> None:
    project = replace(
        three_d_project(),  # type: ignore[type-var]
        core=ManualCoreSelection(0.0269, 0.0147, 0.0112, 0.0),
    )
    with pytest.raises(MaxwellExportBlocked, match="catalog cores"):
        export_maxwell3d(project, CATALOG, RecordingMaxwell3dExporter(), tmp_path)  # type: ignore[arg-type]


def test_manifest_is_deterministic_and_carries_stages(tmp_path: Path) -> None:
    exporter = RecordingMaxwell3dExporter()
    outcome = export_maxwell3d(three_d_project(), CATALOG, exporter, tmp_path)  # type: ignore[arg-type]
    manifest = generation_manifest_json(outcome)
    assert manifest == generation_manifest_json(outcome)
    payload = json.loads(manifest)
    assert payload["schemaVersion"] == 1
    assert payload["succeeded"] is True
    assert [stage["name"] for stage in payload["stages"]][0] == "launch"
    assert payload["windings"][0]["turnCount"] == 10
    assert any("Milestone 4" in note for note in payload["notes"])
```

Note: `make_winding()` defaults `dc_current_a=5.0`, which produces the Milestone 4 note. If `make_project`'s default core snapshot (`make_core()` in `tests/unit/domain/test_catalog_records.py`) is not a reviewed powder record with a numeric grade, pass an explicit `CatalogCoreSelection` built from `tests/unit/simulation/test_maxwell_plan.py::make_core_record` instead — check that helper first.

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/application/test_maxwell_export.py -q`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

Create `src/inductor_designer/application/services/maxwell_export.py`:

```python
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from inductor_designer.application.ports.catalog import CatalogRepository
from inductor_designer.application.ports.maxwell_exporter import (
    Maxwell3dExporter,
    Maxwell3dExportRequest,
    Maxwell3dExportResult,
)
from inductor_designer.application.services.geometry_model import build_geometry_model
from inductor_designer.domain.aedt_target import ModelDimension
from inductor_designer.domain.project import CatalogCoreSelection, InductorProject
from inductor_designer.geometry.naming import sanitize_identifier
from inductor_designer.simulation.maxwell_plan import Maxwell3dDesignPlan, PlanBuildError
from inductor_designer.simulation.plan_builder import build_maxwell3d_plan


class MaxwellExportBlocked(ValueError):
    def __init__(self, issues: tuple[str, ...]) -> None:
        super().__init__("; ".join(issues))
        self.issues = issues


@dataclass(frozen=True, slots=True)
class MaxwellExportOutcome:
    plan: Maxwell3dDesignPlan
    result: Maxwell3dExportResult


def export_maxwell3d(
    project: InductorProject,
    catalog: CatalogRepository,
    exporter: Maxwell3dExporter,
    output_directory: Path,
    *,
    non_graphical: bool = True,
) -> MaxwellExportOutcome:
    if project.dimension_mode is not ModelDimension.THREE_D:
        raise MaxwellExportBlocked(
            ("Project dimension mode must be 3d for Maxwell 3D export.",)
        )
    core_selection = project.core
    if not isinstance(core_selection, CatalogCoreSelection):
        raise MaxwellExportBlocked(
            ("Milestone 3 exports catalog cores only; manual cores carry no material identity.",)
        )
    model = build_geometry_model(project, catalog)
    if model.collisions:
        raise MaxwellExportBlocked(tuple(issue.message for issue in model.collisions))
    try:
        plan = build_maxwell3d_plan(
            model.core,
            core_selection.snapshot,
            model.packings,
            project.windings,
            model.bare_diameter_m,
        )
    except PlanBuildError as error:
        raise MaxwellExportBlocked(error.issues) from error
    request = Maxwell3dExportRequest(
        plan=plan,
        release=project.target_release,
        edition=project.target_edition,
        non_graphical=non_graphical,
        output_directory=output_directory,
        project_name=sanitize_identifier(project.name),
    )
    return MaxwellExportOutcome(plan=plan, result=exporter.export(request))


def generation_manifest_json(outcome: MaxwellExportOutcome) -> str:
    plan = outcome.plan
    result = outcome.result
    payload: dict[str, object] = {
        "schemaVersion": 1,
        "designName": result.design_name,
        "projectPath": str(result.project_path),
        "pyaedtVersion": result.pyaedt_version,
        "succeeded": result.succeeded(),
        "solutionType": plan.solution_type,
        "frequencyHz": plan.setup.frequency_hz,
        "coreMaterial": {
            "name": plan.core.material.name,
            "relativePermeability": plan.core.material.relative_permeability,
            "conductivitySPerM": plan.core.material.conductivity_s_per_m,
            "draft": plan.core.material.draft,
        },
        "windings": [
            {
                "name": group.name,
                "windingId": group.winding_id,
                "isSolid": group.is_solid,
                "currentPeakA": group.current_peak_a,
                "phaseDeg": group.phase_deg,
                "dcCurrentA": group.dc_current_a,
                "turnCount": len(group.turns),
            }
            for group in plan.windings
        ],
        "notes": list(plan.notes),
        "stages": [
            {"name": stage.name, "succeeded": stage.succeeded, "message": stage.message}
            for stage in result.stages
        ],
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"
```

- [ ] **Step 4: Run gates** — application tests, ruff, mypy, architecture check. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/inductor_designer/application/services/maxwell_export.py tests/unit/application/test_maxwell_export.py
git commit -m "feat(application): Maxwell 3D export service and generation manifest"
```

---

### Task 8: Polyline data conversion

Pure translation of `PathSegment` sequences into the point list + per-segment kind list PyAEDT's `create_polyline` consumes ("Line" = 2 shared endpoints, "Arc" = start/mid/end 3-point arc). Lives in `adapters/pyaedt` but imports nothing from pyaedt, so it is fully unit-testable.

**Files:**
- Create: `src/inductor_designer/adapters/pyaedt/polyline_data.py`
- Test: `tests/unit/adapters/test_polyline_data.py`

**Interfaces:**
- Consumes: `LineSegment`/`ArcSegment`/`PathSegment`/`Vec3`.
- Produces: `PolylineData(points: tuple[tuple[float, float, float], ...], kinds: tuple[str, ...])`; `polyline_data(segments: Sequence[PathSegment], *, closed: bool) -> PolylineData` — joints deduplicated, floats `round(_, 9)`, `ValueError` if `closed` and the path does not return to its start. For a closed path the final point equals the first (kept, so the last arc keeps its explicit end point).

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/adapters/test_polyline_data.py`:

```python
from __future__ import annotations

import pytest

from inductor_designer.adapters.pyaedt.polyline_data import polyline_data
from inductor_designer.geometry.core_solid import FinishedCore
from inductor_designer.geometry.primitives import LineSegment, Vec3
from inductor_designer.geometry.turn_path import build_turn_loop

CORE = FinishedCore(r_inner_m=0.01, r_outer_m=0.02, half_height_m=0.005, corner_radius_m=0.0)


def test_turn_loop_converts_to_13_points_and_8_kinds() -> None:
    loop = build_turn_loop(CORE, layer=1, insulated_diameter_m=0.001, station_deg=30.0)
    data = polyline_data(loop, closed=True)
    assert data.kinds == ("Line", "Arc", "Line", "Arc", "Line", "Arc", "Line", "Arc")
    # 8 shared joints + 4 arc midpoints + explicit closing duplicate of the start
    assert len(data.points) == 13
    assert data.points[-1] == data.points[0]


def test_open_path_keeps_order_and_dedupes_joints() -> None:
    a = LineSegment(Vec3(0.0, 0.0, 0.0), Vec3(1.0, 0.0, 0.0))
    b = LineSegment(Vec3(1.0, 0.0, 0.0), Vec3(1.0, 1.0, 0.0))
    data = polyline_data((a, b), closed=False)
    assert data.points == ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0))
    assert data.kinds == ("Line", "Line")


def test_closed_flag_rejects_open_path() -> None:
    a = LineSegment(Vec3(0.0, 0.0, 0.0), Vec3(1.0, 0.0, 0.0))
    with pytest.raises(ValueError, match="return"):
        polyline_data((a,), closed=True)
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/adapters/test_polyline_data.py -q`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

Create `src/inductor_designer/adapters/pyaedt/polyline_data.py`:

```python
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from inductor_designer.geometry.primitives import ArcSegment, PathSegment, Vec3

_JOINT_TOLERANCE_M = 1e-9


@dataclass(frozen=True, slots=True)
class PolylineData:
    """Point list plus per-segment kinds for pyaedt create_polyline.

    ``kinds`` maps 1:1 to the input segments: a "Line" consumes two shared
    endpoints, an "Arc" consumes start/mid/end (pyaedt 3-point arc).
    """

    points: tuple[tuple[float, float, float], ...]
    kinds: tuple[str, ...]


def arc_midpoint(arc: ArcSegment) -> Vec3:
    return arc.sample(3)[1]


def polyline_data(segments: Sequence[PathSegment], *, closed: bool) -> PolylineData:
    if not segments:
        raise ValueError("polyline_data needs at least one segment")
    points: list[Vec3] = []
    kinds: list[str] = []

    def push(point: Vec3) -> None:
        if not points or (point - points[-1]).norm() > _JOINT_TOLERANCE_M:
            points.append(point)

    for segment in segments:
        push(segment.start)
        if isinstance(segment, ArcSegment):
            push(arc_midpoint(segment))
            push(segment.end())
            kinds.append("Arc")
        else:
            push(segment.end)
            kinds.append("Line")

    if closed and (points[-1] - points[0]).norm() > _JOINT_TOLERANCE_M:
        raise ValueError("Closed path does not return to its start")
    if closed:
        points[-1] = points[0]
    return PolylineData(
        points=tuple((round(p.x, 9), round(p.y, 9), round(p.z, 9)) for p in points),
        kinds=tuple(kinds),
    )
```

- [ ] **Step 4: Run gates** (create `tests/unit/adapters/` mirroring existing test-package conventions). Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/inductor_designer/adapters/pyaedt/polyline_data.py tests/unit/adapters/test_polyline_data.py
git commit -m "feat(adapters): pure path-segment to polyline data conversion"
```

---

### Task 9: PyAEDT Maxwell 3D exporter — skeleton, launch, geometry stages

Staged exporter mirroring `PyaedtGateway`: structural protocols, lazy import factory, stage records, guaranteed `release_desktop`. This task delivers `launch`, `units`, `materials`, `core`, `windings`, `terminals` stages plus the fake app; Task 10 adds the remaining stages.

**Files:**
- Create: `src/inductor_designer/adapters/pyaedt/maxwell3d.py`
- Create: `tests/fakes/maxwell3d_app.py`
- Test: `tests/unit/adapters/test_maxwell3d_exporter.py`

**Interfaces:**
- Consumes: port DTOs (Task 6), `Maxwell3dDesignPlan`, `polyline_data`.
- Produces:
  - `Maxwell3dApp(Protocol)` — `modeler: Any`, `mesh: Any`, `post: Any`, `materials: Any`, methods `assign_material(assignment, material)`, `assign_coil(...)`, `assign_winding(...)`, `add_winding_coils(...)`, `eddy_effects_on(...)`, `create_setup(name)`, `assign_matrix(...)`, `validate_full_design() -> tuple[list[str], bool]`, `save_project(path) -> bool`, `release_desktop(close_projects, close_desktop)`.
  - `Maxwell3dAppFactory(Protocol)` with `pyaedt_version: str` and `create(**kwargs) -> Maxwell3dApp`; `DefaultMaxwell3dAppFactory` lazily importing `ansys.aedt.core.Maxwell3d`.
  - `PyaedtMaxwell3dExporter(app_factory=None)` implementing the port `export`.
  - Fake: `FakeMaxwell3dApp` recording every call as `(method_name, kwargs)` tuples in `.calls`; `FakeMaxwell3dAppFactory(app, fail_stage=None)`.

- [ ] **Step 1: Write the failing tests**

Create `tests/fakes/maxwell3d_app.py`:

```python
from __future__ import annotations

from typing import Any


class _Recorder:
    def __init__(self, log: list[tuple[str, dict[str, Any]]], prefix: str) -> None:
        self._log = log
        self._prefix = prefix

    def __getattr__(self, name: str) -> Any:
        def record(*args: Any, **kwargs: Any) -> Any:
            merged = dict(kwargs)
            if args:
                merged["_args"] = args
            self._log.append((f"{self._prefix}{name}", merged))
            return f"{self._prefix}{name}-result"

        return record

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_"):
            super().__setattr__(name, value)
        else:
            self._log.append((f"{self._prefix}set.{name}", {"value": value}))


class _FakeMaterial:
    def __init__(self, log: list[tuple[str, dict[str, Any]]], name: str) -> None:
        self._log = log
        self._name = name

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_"):
            super().__setattr__(name, value)
        else:
            self._log.append((f"material.set.{name}", {"material": self._name, "value": value}))


class _FakeMaterials:
    def __init__(self, log: list[tuple[str, dict[str, Any]]]) -> None:
        self._log = log

    def add_material(self, name: str) -> _FakeMaterial:
        self._log.append(("materials.add_material", {"name": name}))
        return _FakeMaterial(self._log, name)


class _FakeSetup:
    def __init__(self, log: list[tuple[str, dict[str, Any]]], name: str) -> None:
        self._log = log
        self.props: dict[str, Any] = {}
        self._name = name

    def update(self) -> bool:
        self._log.append(("setup.update", {"name": self._name, "props": dict(self.props)}))
        return True


class FakeMaxwell3dApp:
    """Duck-typed Maxwell3d recorder. ``raise_on`` maps a method name to an error."""

    def __init__(self, raise_on: str | None = None) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.raise_on = raise_on
        self.modeler = _Recorder(self.calls, "modeler.")
        self.mesh = _Recorder(self.calls, "mesh.")
        self.post = _Recorder(self.calls, "post.")
        self.materials = _FakeMaterials(self.calls)
        self.released: list[tuple[bool, bool]] = []

    def _record(self, name: str, **kwargs: Any) -> Any:
        if self.raise_on == name:
            raise RuntimeError(f"boom in {name}")
        self.calls.append((name, kwargs))
        return True

    def assign_material(self, assignment: Any, material: str) -> Any:
        return self._record("assign_material", assignment=assignment, material=material)

    def assign_coil(self, assignment: Any, **kwargs: Any) -> Any:
        return self._record("assign_coil", assignment=assignment, **kwargs)

    def assign_winding(self, assignment: Any = None, **kwargs: Any) -> Any:
        return self._record("assign_winding", assignment=assignment, **kwargs)

    def add_winding_coils(self, assignment: Any, coils: Any) -> Any:
        return self._record("add_winding_coils", assignment=assignment, coils=coils)

    def eddy_effects_on(self, assignment: Any, **kwargs: Any) -> Any:
        return self._record("eddy_effects_on", assignment=assignment, **kwargs)

    def create_setup(self, name: str) -> _FakeSetup:
        if self.raise_on == "create_setup":
            raise RuntimeError("boom in create_setup")
        self.calls.append(("create_setup", {"name": name}))
        return _FakeSetup(self.calls, name)

    def assign_matrix(self, assignment: Any, **kwargs: Any) -> Any:
        return self._record("assign_matrix", assignment=assignment, **kwargs)

    def validate_full_design(self) -> tuple[list[str], bool]:
        if self.raise_on == "validate_full_design":
            raise RuntimeError("boom in validate_full_design")
        self.calls.append(("validate_full_design", {}))
        return ([], True)

    def save_project(self, path: str) -> bool:
        if self.raise_on == "save_project":
            raise RuntimeError("boom in save_project")
        self.calls.append(("save_project", {"path": path}))
        return True

    def release_desktop(self, close_projects: bool, close_desktop: bool) -> None:
        self.released.append((close_projects, close_desktop))


class FakeMaxwell3dAppFactory:
    pyaedt_version = "fake-pyaedt"

    def __init__(self, app: FakeMaxwell3dApp) -> None:
        self.app = app
        self.create_kwargs: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> FakeMaxwell3dApp:
        self.create_kwargs.append(kwargs)
        return self.app
```

Create `tests/unit/adapters/test_maxwell3d_exporter.py`:

```python
from __future__ import annotations

from pathlib import Path

from inductor_designer.adapters.pyaedt.maxwell3d import PyaedtMaxwell3dExporter
from inductor_designer.application.ports.maxwell_exporter import (
    STAGE_NAMES,
    Maxwell3dExportRequest,
)
from inductor_designer.domain.aedt_target import AedtEdition, AedtRelease
from tests.fakes.maxwell3d_app import FakeMaxwell3dApp, FakeMaxwell3dAppFactory
from tests.unit.simulation.test_plan_builder import build, make_definition


def make_request(tmp_path: Path) -> Maxwell3dExportRequest:
    return Maxwell3dExportRequest(
        plan=build((make_definition(),)),  # type: ignore[arg-type]
        release=AedtRelease(2025, 2),
        edition=AedtEdition.COMMERCIAL,
        non_graphical=True,
        output_directory=tmp_path / "out",
        project_name="Boost_inductor",
    )


def run(tmp_path: Path, app: FakeMaxwell3dApp) -> object:
    exporter = PyaedtMaxwell3dExporter(app_factory=FakeMaxwell3dAppFactory(app))
    return exporter.export(make_request(tmp_path))


def test_successful_export_runs_every_stage_in_order(tmp_path: Path) -> None:
    app = FakeMaxwell3dApp()
    result = run(tmp_path, app)
    assert tuple(stage.name for stage in result.stages) == STAGE_NAMES
    assert result.succeeded()
    assert app.released == [(True, True)]


def test_geometry_calls_are_made(tmp_path: Path) -> None:
    app = FakeMaxwell3dApp()
    run(tmp_path, app)
    names = [name for name, _ in app.calls]
    # units, then 1 core polyline + sweep + material, then 4 turn polylines
    assert ("modeler.set.model_units", {"value": "meter"}) in app.calls
    assert names.count("modeler.create_polyline") == 1 + 4
    assert names.count("modeler.sweep_around_axis") == 1
    assert names.count("modeler.create_circle") == 4
    assert names.count("modeler.rotate") == 4
    polyline_kwargs = [k for n, k in app.calls if n == "modeler.create_polyline"]
    turn_kwargs = polyline_kwargs[1]
    assert turn_kwargs["xsection_type"] == "Circle"
    assert turn_kwargs["material"] == "copper"


def test_failing_stage_truncates_and_still_releases(tmp_path: Path) -> None:
    app = FakeMaxwell3dApp(raise_on="assign_matrix")
    result = run(tmp_path, app)
    assert not result.succeeded()
    assert result.stages[-1].name == "matrix"
    assert result.stages[-1].succeeded is False
    assert "boom" in result.stages[-1].message
    assert app.released == [(True, True)]
```

(The `matrix`-failure assertions exercise Task 10 code; the test file is written once here and both tasks run it — Task 9 may temporarily mark the last test with `@pytest.mark.xfail(strict=True)` removed in Task 10, or simply implement stages in this task order and let Task 10 finish them. Prefer the latter: Task 9 implements ALL stage plumbing plus the six geometry-side stages, with the remaining stage functions raising `NotImplementedError` — the first two tests pass only after Task 10 removes them, so in Task 9 run only the tests that target implemented stages.)

Simpler discipline for the implementer: in Task 9 write the two geometry tests plus the plumbing; add the failure-path test in Task 10 alongside the remaining stages. Keep test code exactly as above, split across the two tasks.

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/adapters/test_maxwell3d_exporter.py -q`
Expected: FAIL — `inductor_designer.adapters.pyaedt.maxwell3d` not found.

- [ ] **Step 3: Implement skeleton + geometry stages**

Create `src/inductor_designer/adapters/pyaedt/maxwell3d.py`:

```python
from __future__ import annotations

import math
from importlib.metadata import version
from typing import Any, Protocol, cast

from inductor_designer.adapters.pyaedt.polyline_data import polyline_data
from inductor_designer.application.ports.maxwell_exporter import (
    Maxwell3dExportRequest,
    Maxwell3dExportResult,
    StageRecord,
)
from inductor_designer.simulation.maxwell_plan import COPPER_MATERIAL, Maxwell3dDesignPlan


class Maxwell3dApp(Protocol):
    modeler: Any
    mesh: Any
    post: Any
    materials: Any

    def assign_material(self, assignment: Any, material: str) -> Any: ...

    def assign_coil(self, assignment: Any, **kwargs: Any) -> Any: ...

    def assign_winding(self, assignment: Any = ..., **kwargs: Any) -> Any: ...

    def add_winding_coils(self, assignment: Any, coils: Any) -> Any: ...

    def eddy_effects_on(self, assignment: Any, **kwargs: Any) -> Any: ...

    def create_setup(self, name: str) -> Any: ...

    def assign_matrix(self, assignment: Any, **kwargs: Any) -> Any: ...

    def validate_full_design(self) -> tuple[list[str], bool]: ...

    def save_project(self, path: str) -> bool: ...

    def release_desktop(self, close_projects: bool, close_desktop: bool) -> None: ...


class Maxwell3dAppFactory(Protocol):
    pyaedt_version: str

    def create(self, **kwargs: object) -> Maxwell3dApp: ...


class DefaultMaxwell3dAppFactory:
    @property
    def pyaedt_version(self) -> str:
        return version("pyaedt")

    def create(self, **kwargs: object) -> Maxwell3dApp:
        from ansys.aedt.core import Maxwell3d

        return cast(Maxwell3dApp, Maxwell3d(**kwargs))


def _stage_units(app: Maxwell3dApp, plan: Maxwell3dDesignPlan) -> str:
    app.modeler.model_units = "meter"
    return "Model units set to meter."


def _stage_materials(app: Maxwell3dApp, plan: Maxwell3dDesignPlan) -> str:
    spec = plan.core.material
    material = app.materials.add_material(spec.name)
    material.permeability = spec.relative_permeability
    material.conductivity = spec.conductivity_s_per_m
    return f"Material {spec.name} created (draft={spec.draft})."


def _stage_core(app: Maxwell3dApp, plan: Maxwell3dDesignPlan) -> str:
    data = polyline_data(plan.core.profile, closed=True)
    app.modeler.create_polyline(
        points=[list(point) for point in data.points],
        segment_type=list(data.kinds),
        name=plan.core.name,
        cover_surface=True,
        close_surface=False,
    )
    app.modeler.sweep_around_axis(plan.core.name, axis="Z", sweep_angle=360)
    app.assign_material(plan.core.name, plan.core.material.name)
    return f"Core {plan.core.name} revolved and assigned {plan.core.material.name}."


def _stage_windings(app: Maxwell3dApp, plan: Maxwell3dDesignPlan) -> str:
    count = 0
    for group in plan.windings:
        for turn in group.turns:
            data = polyline_data(turn.segments, closed=True)
            app.modeler.create_polyline(
                points=[list(point) for point in data.points],
                segment_type=list(data.kinds),
                name=turn.name,
                material=COPPER_MATERIAL,
                xsection_type="Circle",
                xsection_width=turn.bare_diameter_m,
                xsection_num_seg=0,
            )
            count += 1
    return f"{count} turn conductors created."


def _stage_terminals(app: Maxwell3dApp, plan: Maxwell3dDesignPlan) -> str:
    count = 0
    for group in plan.windings:
        for turn in group.turns:
            disk = turn.terminal.disk
            radial = math.hypot(disk.center.x, disk.center.y)
            app.modeler.create_circle(
                orientation="YZ",
                origin=[round(radial, 9), 0.0, disk.center.z],
                radius=disk.radius_m,
                name=turn.terminal.name,
            )
            app.modeler.rotate(turn.terminal.name, axis="Z", angle=disk.station_deg)
            count += 1
    return f"{count} terminal sheets created."


def _stage_excitations(app: Maxwell3dApp, plan: Maxwell3dDesignPlan) -> str:
    raise NotImplementedError  # Task 10


def _stage_eddy(app: Maxwell3dApp, plan: Maxwell3dDesignPlan) -> str:
    raise NotImplementedError  # Task 10


def _stage_region(app: Maxwell3dApp, plan: Maxwell3dDesignPlan) -> str:
    raise NotImplementedError  # Task 10


def _stage_mesh(app: Maxwell3dApp, plan: Maxwell3dDesignPlan) -> str:
    raise NotImplementedError  # Task 10


def _stage_setup(app: Maxwell3dApp, plan: Maxwell3dDesignPlan) -> str:
    raise NotImplementedError  # Task 10


def _stage_matrix(app: Maxwell3dApp, plan: Maxwell3dDesignPlan) -> str:
    raise NotImplementedError  # Task 10


def _stage_reports(app: Maxwell3dApp, plan: Maxwell3dDesignPlan) -> str:
    raise NotImplementedError  # Task 10


def _stage_validate(app: Maxwell3dApp, plan: Maxwell3dDesignPlan) -> str:
    raise NotImplementedError  # Task 10


_STAGES: tuple[tuple[str, Any], ...] = (
    ("units", _stage_units),
    ("materials", _stage_materials),
    ("core", _stage_core),
    ("windings", _stage_windings),
    ("terminals", _stage_terminals),
    ("excitations", _stage_excitations),
    ("eddy", _stage_eddy),
    ("region", _stage_region),
    ("mesh", _stage_mesh),
    ("setup", _stage_setup),
    ("matrix", _stage_matrix),
    ("reports", _stage_reports),
    ("validate", _stage_validate),
)


class PyaedtMaxwell3dExporter:
    """Executes a Maxwell3dDesignPlan as named stages; never reports a partial design."""

    def __init__(self, app_factory: Maxwell3dAppFactory | None = None) -> None:
        self._factory = DefaultMaxwell3dAppFactory() if app_factory is None else app_factory

    def export(self, request: Maxwell3dExportRequest) -> Maxwell3dExportResult:
        request.output_directory.mkdir(parents=True, exist_ok=True)
        project_path = request.output_directory / f"{request.project_name}.aedt"
        plan = request.plan
        stages: list[StageRecord] = []

        def result() -> Maxwell3dExportResult:
            return Maxwell3dExportResult(
                project_path=project_path,
                design_name=plan.design_name,
                pyaedt_version=self._factory.pyaedt_version,
                stages=tuple(stages),
            )

        try:
            app = self._factory.create(
                project=str(project_path),
                design=plan.design_name,
                solution_type=plan.solution_type,
                version=str(request.release),
                non_graphical=request.non_graphical,
                new_desktop=True,
                close_on_exit=False,
                student_version=request.edition.value == "student",
            )
        except Exception as error:  # noqa: BLE001 - stage boundary converts to record
            stages.append(StageRecord(name="launch", succeeded=False, message=str(error)))
            return result()
        stages.append(
            StageRecord(
                name="launch",
                succeeded=True,
                message=f"Maxwell 3D design {plan.design_name!r} opened.",
            )
        )
        try:
            for name, stage in _STAGES:
                try:
                    message = stage(app, plan)
                except Exception as error:  # noqa: BLE001 - stage boundary
                    stages.append(StageRecord(name=name, succeeded=False, message=str(error)))
                    return result()
                stages.append(StageRecord(name=name, succeeded=True, message=message))
            try:
                saved = bool(app.save_project(str(project_path)))
                stages.append(
                    StageRecord(
                        name="save",
                        succeeded=saved,
                        message="Project saved." if saved else "save_project returned False.",
                    )
                )
            except Exception as error:  # noqa: BLE001 - stage boundary
                stages.append(StageRecord(name="save", succeeded=False, message=str(error)))
        finally:
            app.release_desktop(close_projects=True, close_desktop=True)
        return result()
```

In Task 9 run only `test_geometry_calls_are_made` plus a temporary assertion that the export stops at `excitations` with `NotImplementedError` recorded; Task 10 completes the stages and enables the full suite.

- [ ] **Step 4: Run gates** — adapter tests (Task 9 subset), ruff, mypy, architecture check. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/inductor_designer/adapters/pyaedt/maxwell3d.py tests/fakes/maxwell3d_app.py tests/unit/adapters/test_maxwell3d_exporter.py
git commit -m "feat(adapters): staged Maxwell 3D exporter with geometry stages"
```

---

### Task 10: Exporter — excitations, region, mesh, setup, reports, validate

**Files:**
- Modify: `src/inductor_designer/adapters/pyaedt/maxwell3d.py`
- Test: `tests/unit/adapters/test_maxwell3d_exporter.py` (enable full suite; add the tests below)

**Interfaces:**
- Consumes: Task 9 skeleton, `Maxwell3dApp` protocol methods.
- Produces: all `NotImplementedError` stages replaced; full `STAGE_NAMES` sequence achievable.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/adapters/test_maxwell3d_exporter.py` (and remove any Task 9 temporary assertions):

```python
def test_excitations_group_coils_into_windings(tmp_path: Path) -> None:
    app = FakeMaxwell3dApp()
    run(tmp_path, app)
    coil_calls = [k for n, k in app.calls if n == "assign_coil"]
    assert len(coil_calls) == 4
    assert coil_calls[0]["polarity"] == "Positive"
    assert coil_calls[0]["conductors_number"] == 1
    winding_calls = [k for n, k in app.calls if n == "assign_winding"]
    assert len(winding_calls) == 1
    assert winding_calls[0]["winding_type"] == "Current"
    assert winding_calls[0]["is_solid"] is True
    assert winding_calls[0]["current"] == 2.0
    group_calls = [k for n, k in app.calls if n == "add_winding_coils"]
    assert group_calls[0]["assignment"] == "w1"
    assert len(group_calls[0]["coils"]) == 4


def test_eddy_region_mesh_setup_matrix_reports(tmp_path: Path) -> None:
    app = FakeMaxwell3dApp()
    result = run(tmp_path, app)
    assert result.succeeded()
    names = [name for name, _ in app.calls]
    eddy = [k for n, k in app.calls if n == "eddy_effects_on"]
    assert eddy[0]["enable_eddy_effects"] is True
    assert "modeler.create_air_region" in names
    mesh_calls = [k for n, k in app.calls if n == "mesh.assign_length_mesh"]
    assert len(mesh_calls) == 2
    setup_updates = [k for n, k in app.calls if n == "setup.update"]
    assert setup_updates[0]["props"]["Frequency"] == "100000Hz"
    assert setup_updates[0]["props"]["MaximumPasses"] == 10
    matrix = [k for n, k in app.calls if n == "assign_matrix"]
    assert matrix[0]["assignment"] == ["w1"]
    reports = [k for n, k in app.calls if n == "post.create_report"]
    assert len(reports) == 2
    assert ("validate_full_design", {}) in app.calls
    saves = [k for n, k in app.calls if n == "save_project"]
    assert saves[0]["path"].endswith("Boost_inductor.aedt")
```

Also enable `test_successful_export_runs_every_stage_in_order` and `test_failing_stage_truncates_and_still_releases` from Task 9's file.

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/adapters/test_maxwell3d_exporter.py -q`
Expected: FAIL — `NotImplementedError` recorded in the `excitations` stage.

- [ ] **Step 3: Implement the remaining stages**

Replace the seven `NotImplementedError` bodies in `maxwell3d.py`:

```python
def _stage_excitations(app: Maxwell3dApp, plan: Maxwell3dDesignPlan) -> str:
    for group in plan.windings:
        coil_names: list[str] = []
        for turn in group.turns:
            coil = f"{turn.name}_Coil"
            app.assign_coil(
                turn.terminal.name,
                conductors_number=1,
                polarity=turn.terminal.polarity.value,
                name=coil,
            )
            coil_names.append(coil)
        app.assign_winding(
            assignment=None,
            winding_type="Current",
            is_solid=group.is_solid,
            current=group.current_peak_a,
            phase=group.phase_deg,
            name=group.name,
        )
        app.add_winding_coils(assignment=group.name, coils=coil_names)
    return f"{len(plan.windings)} windings excited."


def _stage_eddy(app: Maxwell3dApp, plan: Maxwell3dDesignPlan) -> str:
    solid = [t.name for g in plan.windings if g.is_solid for t in g.turns]
    stranded = [t.name for g in plan.windings if not g.is_solid for t in g.turns]
    if solid:
        app.eddy_effects_on(solid, enable_eddy_effects=True)
    if stranded:
        app.eddy_effects_on(stranded, enable_eddy_effects=False)
    return f"Eddy effects: {len(solid)} solid on, {len(stranded)} stranded off."


def _stage_region(app: Maxwell3dApp, plan: Maxwell3dDesignPlan) -> str:
    pad = plan.region.padding_percent
    app.modeler.create_air_region(pad, pad, pad, pad, pad, pad)
    return f"Air region with {pad:g}% padding."


def _stage_mesh(app: Maxwell3dApp, plan: Maxwell3dDesignPlan) -> str:
    conductors = [t.name for g in plan.windings for t in g.turns]
    app.mesh.assign_length_mesh(
        conductors, maximum_length=plan.mesh.conductor_max_length_m, name="ConductorLength"
    )
    app.mesh.assign_length_mesh(
        [plan.core.name], maximum_length=plan.mesh.core_max_length_m, name="CoreLength"
    )
    return "Length-based mesh restrictions assigned."


def _stage_setup(app: Maxwell3dApp, plan: Maxwell3dDesignPlan) -> str:
    setup = app.create_setup(name=plan.setup.name)
    setup.props["Frequency"] = f"{plan.setup.frequency_hz:g}Hz"
    setup.props["MaximumPasses"] = plan.setup.maximum_passes
    setup.props["PercentError"] = plan.setup.percent_error
    setup.update()
    return f"Setup {plan.setup.name} at {plan.setup.frequency_hz:g} Hz."


def _stage_matrix(app: Maxwell3dApp, plan: Maxwell3dDesignPlan) -> str:
    app.assign_matrix(
        assignment=[group.name for group in plan.windings], matrix_name=plan.matrix_name
    )
    return f"Matrix {plan.matrix_name} over {len(plan.windings)} windings."


def _stage_reports(app: Maxwell3dApp, plan: Maxwell3dDesignPlan) -> str:
    for report in plan.reports:
        app.post.create_report(expressions=[report.expression], plot_name=report.name)
    return f"{len(plan.reports)} reports requested."


def _stage_validate(app: Maxwell3dApp, plan: Maxwell3dDesignPlan) -> str:
    messages, valid = app.validate_full_design()
    if not valid:
        tail = " | ".join(str(entry) for entry in messages[-5:])
        raise RuntimeError(f"Design validation failed: {tail}")
    return "Design validation passed."
```

- [ ] **Step 4: Run gates** — full adapter suite, ruff, mypy, architecture check. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/inductor_designer/adapters/pyaedt/maxwell3d.py tests/unit/adapters/test_maxwell3d_exporter.py
git commit -m "feat(adapters): complete Maxwell 3D export stages through validation"
```

---

### Task 11: CLI, controlled runner, AEDT integration test

**Files:**
- Create: `tools/generate_maxwell3d.py`
- Create: `tools/run_aedt_maxwell3d.ps1`
- Test: `tests/unit/tools/test_generate_maxwell3d.py`
- Test: `tests/integration/aedt/test_maxwell3d_export.py` (`@pytest.mark.aedt`)

**Interfaces:**
- Consumes: `ProjectRepository`/`SchemaRepository`, `SqliteCatalogRepository`, `tools.build_catalog.build`, `export_maxwell3d`, `generation_manifest_json`, `PyaedtMaxwell3dExporter`.
- Produces: `main(argv: Sequence[str] | None = None, *, exporter: Maxwell3dExporter | None = None) -> int` — args `--project PATH --output-directory PATH --evidence PATH [--graphical]`; builds the SQLite catalog index into the output directory from the repo's canonical files; writes the generation manifest to `--evidence`; exit 0 only when `result.succeeded()`. Blocked exports print the issues and exit 1.

- [ ] **Step 1: Write the failing CLI test**

Create `tests/unit/tools/test_generate_maxwell3d.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from tests.fakes.maxwell_exporter import RecordingMaxwell3dExporter
from tools.generate_maxwell3d import main

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "tests" / "fixtures" / "sample_geometry_project.inductor.json"


def test_main_exports_sample_project_and_writes_evidence(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence.json"
    exit_code = main(
        [
            "--project", str(FIXTURE),
            "--output-directory", str(tmp_path / "out"),
            "--evidence", str(evidence),
        ],
        exporter=RecordingMaxwell3dExporter(),
    )
    assert exit_code == 0
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    assert payload["succeeded"] is True
    assert payload["designName"] == "Inductor3D"
    assert [w["name"] for w in payload["windings"]] == ["w1", "w2"]
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/tools/test_generate_maxwell3d.py -q`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement the CLI**

Create `tools/generate_maxwell3d.py`:

```python
"""Generate a ready-to-solve Maxwell 3D project from an inductor project file."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from inductor_designer.adapters.catalog.sqlite_repository import SqliteCatalogRepository
from inductor_designer.adapters.persistence.project_repository import ProjectRepository
from inductor_designer.adapters.persistence.schema_repository import SchemaRepository
from inductor_designer.adapters.pyaedt.maxwell3d import PyaedtMaxwell3dExporter
from inductor_designer.application.ports.maxwell_exporter import Maxwell3dExporter
from inductor_designer.application.services.maxwell_export import (
    MaxwellExportBlocked,
    export_maxwell3d,
    generation_manifest_json,
)
from tools.build_catalog import build

ROOT = Path(__file__).resolve().parents[1]


def main(
    argv: Sequence[str] | None = None, *, exporter: Maxwell3dExporter | None = None
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--graphical", action="store_true")
    args = parser.parse_args(argv)

    args.output_directory.mkdir(parents=True, exist_ok=True)
    index = args.output_directory / "catalog.sqlite"
    build(ROOT / "catalog", ROOT / "schemas" / "catalog", index)
    catalog = SqliteCatalogRepository(index)
    repository = ProjectRepository(SchemaRepository(ROOT / "schemas"))
    project = repository.load(args.project)

    try:
        outcome = export_maxwell3d(
            project,
            catalog,
            exporter if exporter is not None else PyaedtMaxwell3dExporter(),
            args.output_directory,
            non_graphical=not args.graphical,
        )
    except MaxwellExportBlocked as blocked:
        for issue in blocked.issues:
            print(f"BLOCKED: {issue}", file=sys.stderr)
        return 1

    args.evidence.parent.mkdir(parents=True, exist_ok=True)
    args.evidence.write_text(generation_manifest_json(outcome), encoding="utf-8")
    for stage in outcome.result.stages:
        status = "ok" if stage.succeeded else "FAILED"
        print(f"{stage.name}: {status} - {stage.message}")
    return 0 if outcome.result.succeeded() else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

Create `tools/run_aedt_maxwell3d.ps1` (mirror `tools/run_aedt_spike.ps1` conventions — same param validation pattern, venv python, artifacts path):

```powershell
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^(?:2024\.2|20(?:2[5-9]|[3-9][0-9])\.[12])$')]
    [string]$Release,

    [Parameter(Mandatory = $true)]
    [ValidateSet('commercial', 'student')]
    [string]$Edition,

    [string]$Project = "tests\fixtures\sample_geometry_project.inductor.json",

    [switch]$Graphical
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$outputDirectory = Join-Path $repoRoot "artifacts\maxwell3d\$Release-$Edition"
$evidence = Join-Path $outputDirectory 'generation-manifest.json'

$arguments = @(
    '-m', 'tools.generate_maxwell3d',
    '--project', $Project,
    '--output-directory', $outputDirectory,
    '--evidence', $evidence
)
if ($Graphical) { $arguments += '--graphical' }

& "$repoRoot\.venv\Scripts\python.exe" @arguments
exit $LASTEXITCODE
```

Note: the sample fixture pins `target.aedtRelease` 2025.2 commercial; the exporter uses the project's target, so `-Release`/`-Edition` select only the artifacts folder naming in the MVP. Document this in the runner header comment if desired.

- [ ] **Step 4: Write the AEDT integration test**

Create `tests/integration/aedt/test_maxwell3d_export.py`:

```python
from __future__ import annotations

import os
from pathlib import Path

import pytest

from inductor_designer.adapters.catalog.sqlite_repository import SqliteCatalogRepository
from inductor_designer.adapters.persistence.project_repository import ProjectRepository
from inductor_designer.adapters.persistence.schema_repository import SchemaRepository
from inductor_designer.adapters.pyaedt.maxwell3d import PyaedtMaxwell3dExporter
from inductor_designer.application.services.maxwell_export import export_maxwell3d
from tools.build_catalog import build

ROOT = Path(__file__).resolve().parents[3]

pytestmark = pytest.mark.aedt


def test_generated_project_is_ready_to_solve(tmp_path: Path) -> None:
    release = os.environ.get("INDUCTOR_AEDT_RELEASE")
    edition = os.environ.get("INDUCTOR_AEDT_EDITION")
    if not release or not edition:
        pytest.skip("Set INDUCTOR_AEDT_RELEASE and INDUCTOR_AEDT_EDITION to run AEDT tests")

    index = tmp_path / "catalog.sqlite"
    build(ROOT / "catalog", ROOT / "schemas" / "catalog", index)
    catalog = SqliteCatalogRepository(index)
    repository = ProjectRepository(SchemaRepository(ROOT / "schemas"))
    project = repository.load(ROOT / "tests" / "fixtures" / "sample_geometry_project.inductor.json")

    outcome = export_maxwell3d(project, catalog, PyaedtMaxwell3dExporter(), tmp_path / "out")

    failed = [stage for stage in outcome.result.stages if not stage.succeeded]
    assert outcome.result.succeeded(), failed
    assert outcome.result.project_path.exists()
```

Run non-AEDT gates; the `aedt`-marked test is deselected in CI and exercised in Task 12's human handoff.

- [ ] **Step 5: Run gates**

Run: `.venv\Scripts\python.exe -m pytest tests -q -m "not aedt and not ui"`, ruff, mypy, architecture check.
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add tools/generate_maxwell3d.py tools/run_aedt_maxwell3d.ps1 tests/unit/tools/test_generate_maxwell3d.py tests/integration/aedt/test_maxwell3d_export.py
git commit -m "feat(tools): Maxwell 3D generation CLI, runner, and AEDT test"
```

---

### Task 12: Docs, coverage, exit-criterion handoff

**Files:**
- Modify: `docs/development/ROADMAP.md` (Milestone 3 "Current state")
- Modify: `docs/architecture/README.md` (simulation/exporter line if the package description needs it)
- Create: `docs/development/maxwell3d-generation.md`
- Modify: `README.md` (milestone table row, if present)

**Interfaces:** none (documentation).

- [ ] **Step 1: Write the generation procedure doc**

Create `docs/development/maxwell3d-generation.md` following the structure of `docs/development/aedt-compatibility-testing.md`:

```markdown
# Maxwell 3D generation procedure

Milestone 3 generates a ready-to-solve Maxwell 3D project from an inductor
project file. Generation runs as named stages; the generation manifest
(`generation-manifest.json`) records every stage, and a partial design is
never reported as successful.

## Prerequisites

- Controlled Windows machine with a licensed AEDT installation (2025 R2
  Commercial is the accepted row).
- `pip install -e ".[dev,aedt]"` in the project venv.

## Procedure

1. Run the controlled runner (graphical first, per compatibility policy):

   ```powershell
   .\tools\run_aedt_maxwell3d.ps1 -Release 2025.2 -Edition commercial -Graphical
   ```

2. Review `artifacts\maxwell3d\2025.2-commercial\generation-manifest.json`:
   every stage `succeeded: true`, `succeeded: true` at top level.
3. Open the generated `.aedt` in AEDT. Confirm: core + turn solids present,
   one coil terminal per turn, windings grouped, material assigned, region,
   mesh operations, `Setup1` (Eddy Current) at the project frequency,
   `Matrix1`, report definitions. Validation (checkmark button) passes.
4. Optionally run the marked integration test on the same machine:

   ```powershell
   $env:INDUCTOR_AEDT_RELEASE = "2025.2"
   $env:INDUCTOR_AEDT_EDITION = "commercial"
   .venv\Scripts\python.exe -m pytest tests/integration/aedt/test_maxwell3d_export.py -v
   ```

## Milestone 3 scope notes

- Core material is a linear draft model derived from the powder grade
  (relative permeability = grade, conductivity 0). Real material records
  arrive with Material Studio (Milestone 5). Ferrite cores refuse to export.
- DC operating currents are recorded in the manifest but not applied
  (Milestone 4).
- Full model only; symmetry stays data-level (Milestone 2 plan output).
- Exact PyAEDT keyword names were verified against the installed pyaedt by
  the AEDT integration test; the recording fakes mirror the adapter's calls.
```

- [ ] **Step 2: Update the ROADMAP**

Add under `## Milestone 3: Maxwell 3D MVP` a `### Current state` section stating: implementation complete pending human AEDT verification; list the deliverables (design plan builder, staged exporter, CLI + runner, generation manifest, terminal-per-turn excitations, linear draft core material per D2, unique-name guard); exit criterion verified by `tools/run_aedt_maxwell3d.ps1` + manual open in AEDT 2025 R2 Commercial (evidence gitignored under `artifacts/maxwell3d/`). Mark the milestone **accepted only after** Fabio's run — mirror how M0–M2 sections read.

- [ ] **Step 3: Run the full gate set and record coverage**

Run:
- `.venv\Scripts\python.exe -m pytest tests -q -m "not aedt and not ui" --cov`
- `.venv\Scripts\python.exe -m ruff check .`
- `.venv\Scripts\python.exe -m mypy`
- `.venv\Scripts\python.exe tools/check_architecture.py`

Expected: all PASS, coverage ≥ 80 %.

- [ ] **Step 4: Commit**

```bash
git add docs/development/maxwell3d-generation.md docs/development/ROADMAP.md docs/architecture/README.md README.md
git commit -m "docs: Maxwell 3D generation procedure and M3 status"
```

- [ ] **Step 5: Human handoff (exit criterion)**

Not automatable — hand to Fabio Posser on the licensed machine:

1. `.\tools\run_aedt_maxwell3d.ps1 -Release 2025.2 -Edition commercial -Graphical`
2. Open the generated project in AEDT; run design validation; visually check turns, terminals, winding grouping, material, region, mesh ops, setup, matrix, reports.
3. Run the `aedt`-marked integration test (env vars per the doc).
4. If a PyAEDT kwarg mismatch surfaces, fix adapter + fakes to match the installed pyaedt (Global Constraints rule), re-run the non-AEDT gates, and repeat.
5. Accept Milestone 3 in the ROADMAP.

---

## Self-review notes

- ROADMAP M3 bullets → tasks: core+winding geometry (T2/T5/T9), solid/stranded (T5 `is_solid` + T10 eddy), materials (T4/T9), coils+groups+directions (T5 polarity + T10 excitations), region (T10), mesh intent (T5/T10), AC Magnetic setup (T10), standard reports (T5/T10), exit criterion (T11/T12).
- Names used across tasks were cross-checked: `unique_identifiers` (T1→T5), `build_core_profile` (T2→T5), `TerminalDisk`/`build_terminal_disk` (T3→T4/T5), plan dataclasses (T4→T5/T6/T7/T9/T10), `STAGE_NAMES` (T6→T9/T10), `build`/`make_definition` test helpers (T5→T6/T9), `MaxwellExportOutcome` (T7→T11).
- Known verification-at-AEDT risks (deliberate, arbiter = T11 aedt test): `create_polyline` string segment types + `cover_surface` on a pre-closed profile, `create_circle(orientation=...)` kwarg, `assign_winding`/`assign_coil` kwarg names, `assign_length_mesh(maximum_length=...)`, `validate_full_design` return shape.
