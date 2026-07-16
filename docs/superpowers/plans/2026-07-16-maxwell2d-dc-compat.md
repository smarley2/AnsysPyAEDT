# Milestone 4: Maxwell 2D and DC Operating Point Compatibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate the documented approximate Maxwell 2D XY cross-sectional model from the existing `PlanarModel`, wire `select_dc_bias_strategy` into both exports (native 3D Include DC Fields where the reviewed matrix confirms it; every other strategy identified and recorded, not applied), and make every approximation and capability decision visible in the generation manifest and the Guided Studio UI.

**Architecture:** A `CapabilityRepository` port with a YAML adapter turns `compatibility/aedt-matrix.yml` rows into `CapabilitySnapshot`s — the missing link that today leaves `select_dc_bias_strategy` permanently blocked. Both export services take a snapshot, compute a `DcBiasDecision`, and stamp it into the plan; the 3D adapter applies native DC (setup flag + per-winding DC value), and a new Maxwell 2D plan/port/adapter stack mirrors the M3 pattern (frozen plan dataclasses → staged exporter → recording fakes). Generation manifest bumps to schemaVersion 2 with `dimension`, `dcBias`, and `capabilities` blocks; the UI shows the simulation summary.

**Tech Stack:** Python stdlib + PyYAML (promoted to runtime), PyAEDT `Maxwell2d`/`Maxwell3d` (lazy, `adapters/pyaedt` only), pytest `aedt`/`ui` markers.

## Global Constraints

- Python `>=3.10,<3.14`; mypy `strict` over `src` and `tools`; Ruff line length 100 with `E,F,I,B,UP,ANN,SIM`; branch coverage `fail_under = 80`.
- Architecture rules (`tools/check_architecture.py`): `domain`, `geometry`, `materials`, `simulation` stay pure (no PySide6/ansys/pyaedt/sqlite3/os/pathlib/yaml); `application` never imports PySide6/ansys/pyaedt/sqlite3. YAML parsing lives in `adapters/compatibility` only. Run the checker after every task touching inner packages.
- Every file starts with `from __future__ import annotations`; frozen slots dataclasses with `__post_init__` invariants.
- Units meters/degrees/amperes/hertz; floats reaching plans/manifests rounded `round(x, 9)`; deterministic manifests (path strings excluded).
- One `Dimension` of truth for DC bias: **`select_dc_bias_strategy` is the only place that decides**; services pass its `DcBiasDecision` down, adapters and manifests only consume it.
- AEDT-touching tests carry `@pytest.mark.aedt` (skip without `INDUCTOR_AEDT_RELEASE`/`INDUCTOR_AEDT_EDITION`); CI runs `-m "not aedt and not ui"`. The installed pyaedt (1.2.0) is the arbiter for exact kwarg/prop names — fix adapter + fakes to match reality (M3 precedent: `assign_matrix` schema API, `validate_simple`).
- Environment: `.venv\Scripts\python.exe`. Gates after every task: `-m pytest tests -q -m "not aedt and not ui"`, `-m ruff check .`, `-m mypy`, `python tools/check_architecture.py`.
- Conventional commits; don't stage unrelated files.

## Design decisions (reviewed with Fabio Posser, 2026-07-16: D3 confirmed — he reviews Include DC Fields on 2025.2; D4 VETOED — 2024 R2 work deferred, identification only; D8 accepted)

- **D1 — PyYAML becomes a runtime dependency.** The matrix loader adapter needs it; today it sits in the `dev` extra only. `types-PyYAML` stays dev.
- **D2 — Capability source = `compatibility/aedt-matrix.yml` via a `CapabilityRepository` port.** Row → snapshot mapping: `review_status = REVIEWED` iff `status == "passed"` **and** `evidenceReviewedBy` set; `include_dc_fields_3d` straight from `includeDcFields3d` (`null` stays `None`); missing row → `UNREVIEWED` snapshot (so the strategy selector blocks naturally, no new error path).
- **D3 — Native DC application (3D):** when the decision is `NATIVE_INCLUDE_DC_FIELDS` and any winding has nonzero `dc_current_a`, the Eddy Current setup gets `props["IncludeDcFields"] = True` and each winding boundary gets `props["DCValue"] = f"{dc:g}A"`. Exact AEDT prop names are a flagged verify-at-AEDT risk. **Today's matrix has `includeDcFields3d: null` for 2025.2 — the native path stays blocked on the real machine until Fabio reviews the capability and flips the row** (handoff step in Task 14).
- **D4 (VETOED 2026-07-16) — 2024 R2 fallback deferred entirely.** No companion Magnetostatic design is generated. `select_dc_bias_strategy` still *identifies* the 2024 R2 fallback strategy (the selector is untouched and the release-matrix test proves the identification), but the exporter treats it like blocked: DC recorded, not applied, with an explicit "deferred — no 2024 R2 installation" note. Milestone 4 targets AEDT 2025.2 Commercial only. Generation work for 2024 R2 returns when an installation exists.
- **D5 — 2D model per design spec §163:** XY cross-section from `PlanarModel` — annular core (outer circle minus inner circle), one circle per `PlanarConductor`, coil per conductor, winding per `WindingDefinition`, `model_depth` = `planar.depth_m` (= 2·half-height). Solution type `EddyCurrent`. Conductor coil polarity = winding D6 polarity, **inverted when `PlanarConductor.polarity == -1`** (the return conductor).
- **D6 — 2D always carries an explicit approximation note** in plan notes and manifest; 2D DC bias stays BLOCKED (existing `select_dc_bias_strategy` policy), reason surfaced.
- **D7 — Manifest schemaVersion 2** for both dimensions: adds `dimension`, `dcBias {strategy, approximate, reason, appliedCurrentsA|null}`, `capabilities {release, edition, includeDcFields3d, reviewStatus, evidenceSource}`.
- **D8 — Services take `capabilities: CapabilitySnapshot`** (required keyword); callers (CLI, UI, tests) resolve it via the repository. `export_maxwell3d`'s signature changes — M3 call sites updated in the same task.
- **D9 — `succeeded()` rule relaxed** to "non-empty ∧ all succeeded ∧ last stage is `save`" (the fixed-length check compares against the 3D 15-stage tuple and would make every 14-stage 2D result fail). Alias `MaxwellExportResult = Maxwell3dExportResult` lets the 2D port reuse the class without a misleading name.
- **D10 — Exit criterion test:** a non-AEDT integration test parametrized over release-matrix rows (real file + a synthetic matrix covering native/fallback cases) proves the manifest identifies native vs approximate vs blocked treatment per row and dimension.
- **D11 — UI visibility = simulation summary lines** (target, strategy, approximate badge, reason, 2D approximation note) computed by a pure application service and rendered under the existing `Simulation` label in `Main.qml`. No new UI framework work.
- **D12 — New sibling CLI `tools/generate_maxwell2d.py` + runner**, and both CLIs gain `--matrix` (default `compatibility/aedt-matrix.yml`).

## File structure

| File | Responsibility |
|---|---|
| `src/inductor_designer/application/ports/capability_repository.py` (new) | Port: snapshot lookup by release/edition |
| `src/inductor_designer/adapters/compatibility/matrix_repository.py` (new) | YAML matrix → `CapabilitySnapshot` |
| `src/inductor_designer/simulation/maxwell_plan.py` (modify) | + `dc_bias` field, shared `dc_bias_notes` helper |
| `src/inductor_designer/simulation/plan_builder.py` (modify) | + `dc_bias_decision` param, strategy notes |
| `src/inductor_designer/simulation/maxwell2d_plan.py` (new) | 2D plan dataclasses |
| `src/inductor_designer/simulation/plan_builder2d.py` (new) | `build_maxwell2d_plan` from `PlanarModel` |
| `src/inductor_designer/application/ports/maxwell_exporter.py` (modify) | relaxed `succeeded()`, `MaxwellExportResult` alias |
| `src/inductor_designer/application/ports/maxwell2d_exporter.py` (new) | 2D port, `STAGE_NAMES_2D` |
| `src/inductor_designer/application/services/maxwell_export.py` (modify) | capabilities param, `export_maxwell2d`, manifest v2 |
| `src/inductor_designer/application/services/simulation_summary.py` (new) | UI-facing summary lines |
| `src/inductor_designer/adapters/pyaedt/maxwell3d.py` (modify) | native Include-DC-Fields application |
| `src/inductor_designer/adapters/pyaedt/maxwell2d.py` (new) | staged 2D exporter |
| `tools/generate_maxwell2d.py`, `tools/run_aedt_maxwell2d.ps1` (new); `tools/generate_maxwell3d.py` (modify) | CLIs + runner |
| `src/inductor_designer/ui/main.py`, `ui/qml/Main.qml` (modify) | summary display |
| `tests/fakes/{capability_repository,maxwell2d_exporter,maxwell2d_app}.py` (new); `tests/fakes/maxwell3d_app.py` (modify) | fakes |

---

### Task 1: Capability port + matrix adapter (PyYAML to runtime)

**Files:**
- Modify: `pyproject.toml` (move `PyYAML>=6.0,<7` from `dev` to `dependencies`; `types-PyYAML` stays dev)
- Create: `src/inductor_designer/application/ports/capability_repository.py`
- Create: `src/inductor_designer/adapters/compatibility/__init__.py` (empty docstring module)
- Create: `src/inductor_designer/adapters/compatibility/matrix_repository.py`
- Create: `tests/fakes/capability_repository.py`
- Test: `tests/unit/adapters/test_matrix_repository.py`

**Interfaces:**
- Produces: `CapabilityRepository(Protocol)` with `snapshot_for(release: AedtRelease, edition: AedtEdition) -> CapabilitySnapshot`.
- Produces: `MatrixCapabilityRepository(matrix_path: Path)` implementing it per D2.
- Produces: fake `StaticCapabilityRepository(snapshot)` returning the given snapshot for any key.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/adapters/test_matrix_repository.py`:

```python
from __future__ import annotations

from pathlib import Path

from inductor_designer.adapters.compatibility.matrix_repository import (
    MatrixCapabilityRepository,
)
from inductor_designer.domain.aedt_target import AedtEdition, AedtRelease
from inductor_designer.simulation.capabilities import CapabilityReviewStatus

ROOT = Path(__file__).resolve().parents[3]
REAL_MATRIX = ROOT / "compatibility" / "aedt-matrix.yml"

SYNTHETIC = """\
schemaVersion: 1
rows:
  - release: "2025.2"
    edition: commercial
    status: passed
    includeDcFields3d: true
    discoveredLimits: ["no-hpc"]
    evidenceReviewedAt: "2026-07-17T00:00:00Z"
    evidenceReviewedBy: fabio
  - release: "2024.2"
    edition: commercial
    status: passed
    includeDcFields3d: false
    discoveredLimits: []
    evidenceReviewedAt: "2026-07-17T00:00:00Z"
    evidenceReviewedBy: fabio
"""


def test_real_matrix_reviewed_row_maps_to_snapshot() -> None:
    repo = MatrixCapabilityRepository(REAL_MATRIX)
    snapshot = repo.snapshot_for(AedtRelease(2025, 2), AedtEdition.COMMERCIAL)
    assert snapshot.review_status is CapabilityReviewStatus.REVIEWED
    assert snapshot.include_dc_fields_3d is None
    assert snapshot.evidence_source == "aedt-matrix:aedt-matrix.yml"


def test_out_of_scope_row_is_unreviewed() -> None:
    repo = MatrixCapabilityRepository(REAL_MATRIX)
    snapshot = repo.snapshot_for(AedtRelease(2024, 2), AedtEdition.COMMERCIAL)
    assert snapshot.review_status is CapabilityReviewStatus.UNREVIEWED


def test_missing_row_is_unreviewed_with_marker(tmp_path: Path) -> None:
    path = tmp_path / "m.yml"
    path.write_text(SYNTHETIC, encoding="utf-8")
    snapshot = MatrixCapabilityRepository(path).snapshot_for(
        AedtRelease(2026, 1), AedtEdition.STUDENT
    )
    assert snapshot.review_status is CapabilityReviewStatus.UNREVIEWED
    assert snapshot.evidence_source.endswith("missing-row")


def test_synthetic_rows_carry_flags(tmp_path: Path) -> None:
    path = tmp_path / "m.yml"
    path.write_text(SYNTHETIC, encoding="utf-8")
    repo = MatrixCapabilityRepository(path)
    native = repo.snapshot_for(AedtRelease(2025, 2), AedtEdition.COMMERCIAL)
    assert native.include_dc_fields_3d is True
    assert native.discovered_limits == ("no-hpc",)
    assert native.review_status is CapabilityReviewStatus.REVIEWED
    fallback = repo.snapshot_for(AedtRelease(2024, 2), AedtEdition.COMMERCIAL)
    assert fallback.include_dc_fields_3d is False
    assert fallback.review_status is CapabilityReviewStatus.REVIEWED
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/adapters/test_matrix_repository.py -q`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

`pyproject.toml`: add `"PyYAML>=6.0,<7",` to `[project] dependencies`; delete that line from the `dev` extra (keep `types-PyYAML`). Re-run `pip install -e ".[dev,ui]"` in the venv.

Create `src/inductor_designer/application/ports/capability_repository.py`:

```python
from __future__ import annotations

from typing import Protocol

from inductor_designer.domain.aedt_target import AedtEdition, AedtRelease
from inductor_designer.simulation.capabilities import CapabilitySnapshot


class CapabilityRepository(Protocol):
    def snapshot_for(self, release: AedtRelease, edition: AedtEdition) -> CapabilitySnapshot: ...
```

Create `src/inductor_designer/adapters/compatibility/__init__.py`:

```python
"""Adapters for the controlled AEDT compatibility evidence."""
```

Create `src/inductor_designer/adapters/compatibility/matrix_repository.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from inductor_designer.domain.aedt_target import AedtEdition, AedtRelease
from inductor_designer.simulation.capabilities import (
    CapabilityReviewStatus,
    CapabilitySnapshot,
)


class MatrixCapabilityRepository:
    """CapabilitySnapshot source backed by compatibility/aedt-matrix.yml.

    A row is REVIEWED only when its status is "passed" and a reviewer is
    recorded; unknown release/edition pairs map to an UNREVIEWED snapshot so
    select_dc_bias_strategy blocks them naturally.
    """

    def __init__(self, matrix_path: Path) -> None:
        self._path = matrix_path

    def snapshot_for(self, release: AedtRelease, edition: AedtEdition) -> CapabilitySnapshot:
        data = yaml.safe_load(self._path.read_text(encoding="utf-8"))
        rows: list[dict[str, Any]] = data.get("rows", []) if isinstance(data, dict) else []
        for row in rows:
            if str(row.get("release")) == str(release) and row.get("edition") == edition.value:
                reviewed = row.get("status") == "passed" and bool(row.get("evidenceReviewedBy"))
                return CapabilitySnapshot(
                    release=release,
                    edition=edition,
                    include_dc_fields_3d=row.get("includeDcFields3d"),
                    discovered_limits=tuple(row.get("discoveredLimits") or ()),
                    evidence_source=f"aedt-matrix:{self._path.name}",
                    review_status=(
                        CapabilityReviewStatus.REVIEWED
                        if reviewed
                        else CapabilityReviewStatus.UNREVIEWED
                    ),
                )
        return CapabilitySnapshot(
            release=release,
            edition=edition,
            include_dc_fields_3d=None,
            discovered_limits=(),
            evidence_source=f"aedt-matrix:{self._path.name}:missing-row",
            review_status=CapabilityReviewStatus.UNREVIEWED,
        )
```

Create `tests/fakes/capability_repository.py`:

```python
from __future__ import annotations

from inductor_designer.domain.aedt_target import AedtEdition, AedtRelease
from inductor_designer.simulation.capabilities import CapabilitySnapshot


class StaticCapabilityRepository:
    """Port fake: returns one snapshot for any lookup."""

    def __init__(self, snapshot: CapabilitySnapshot) -> None:
        self.snapshot = snapshot

    def snapshot_for(self, release: AedtRelease, edition: AedtEdition) -> CapabilitySnapshot:
        return self.snapshot
```

- [ ] **Step 4: Run gates.** Expected: PASS (architecture check: yaml import only in `adapters/compatibility`).

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/inductor_designer/application/ports/capability_repository.py src/inductor_designer/adapters/compatibility tests/fakes/capability_repository.py tests/unit/adapters/test_matrix_repository.py
git commit -m "feat(adapters): capability repository backed by the AEDT matrix"
```

---

### Task 2: Relax export-result success rule

The fixed-length check compares against the 3D `STAGE_NAMES` (15 entries); the 2D port (Task 7) reuses the result class with 14 stages, so every 2D result would report failure.

**Files:**
- Modify: `src/inductor_designer/application/ports/maxwell_exporter.py`
- Test: `tests/contract/test_maxwell_exporter_contract.py` (extend)

**Interfaces:**
- Produces: `Maxwell3dExportResult.succeeded()` = non-empty ∧ all succeeded ∧ `stages[-1].name == "save"`; alias `MaxwellExportResult = Maxwell3dExportResult` (consumed by the 2D port in Task 8).

- [ ] **Step 1: Write the failing tests**

Append to `tests/contract/test_maxwell_exporter_contract.py`:

```python
def test_extra_stage_before_save_still_succeeds(tmp_path: Path) -> None:
    from dataclasses import replace

    from inductor_designer.application.ports.maxwell_exporter import StageRecord

    full = RecordingMaxwell3dExporter().export(make_request(tmp_path))
    extra = StageRecord(name="extra", succeeded=True, message="stage counts may vary")
    augmented = replace(full, stages=full.stages[:-1] + (extra, full.stages[-1]))
    assert augmented.succeeded()


def test_failed_stage_never_succeeds(tmp_path: Path) -> None:
    from dataclasses import replace

    from inductor_designer.application.ports.maxwell_exporter import StageRecord

    full = RecordingMaxwell3dExporter().export(make_request(tmp_path))
    broken = replace(
        full,
        stages=full.stages[:-1]
        + (StageRecord(name="save", succeeded=False, message="disk full"),),
    )
    assert not broken.succeeded()
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/contract/test_maxwell_exporter_contract.py -q`
Expected: FAIL — `test_extra_stage_before_save_still_succeeds` (length check rejects 16 stages).

- [ ] **Step 3: Implement**

In `maxwell_exporter.py`, replace the `succeeded` method body and add the alias after the class:

```python
    def succeeded(self) -> bool:
        """A partial design is never successful (design spec §12).

        Success = every recorded stage succeeded and the run reached "save".
        Stage counts differ between the 3D and 2D exporters.
        """
        return (
            bool(self.stages)
            and all(stage.succeeded for stage in self.stages)
            and self.stages[-1].name == "save"
        )
```

```python
MaxwellExportResult = Maxwell3dExportResult
```

Existing truncation test (`stages[:3]`) still passes — last stage is not `save`.

- [ ] **Step 4: Run gates.** Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/inductor_designer/application/ports/maxwell_exporter.py tests/contract/test_maxwell_exporter_contract.py
git commit -m "feat(application): success rule tolerates conditional export stages"
```

---

### Task 3: DC-bias decision in the 3D plan

**Files:**
- Modify: `src/inductor_designer/simulation/maxwell_plan.py`
- Modify: `src/inductor_designer/simulation/plan_builder.py`
- Test: `tests/unit/simulation/test_plan_builder.py` (extend)

**Interfaces:**
- Produces: `Maxwell3dDesignPlan.dc_bias: DcBiasDecision | None = None` (new last field, default keeps M3 constructors valid).
- Produces: `dc_bias_notes(decision: DcBiasDecision | None, dc_requested: bool) -> tuple[str, ...]` in `maxwell_plan.py` (shared with the 2D builder in Task 7).
- Produces: `build_maxwell3d_plan(..., dc_bias_decision: DcBiasDecision | None = None)`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/simulation/test_plan_builder.py` (extend the module imports with `from inductor_designer.simulation.capabilities import DcBiasDecision, DcBiasStrategy`; give the local `build` helper a pass-through `dc_bias_decision=None` keyword forwarded to `build_maxwell3d_plan`):

```python
NATIVE = DcBiasDecision(DcBiasStrategy.NATIVE_INCLUDE_DC_FIELDS, False, "native ok")
FALLBACK = DcBiasDecision(
    DcBiasStrategy.MAGNETOSTATIC_INCREMENTAL_FALLBACK, True, "2024 R2 fallback"
)
BLOCKED = DcBiasDecision(DcBiasStrategy.BLOCKED, False, "unreviewed")


def test_native_decision_lands_in_plan_and_notes() -> None:
    plan = build((make_definition(dc_current_a=5.0),), dc_bias_decision=NATIVE)
    assert plan.dc_bias is NATIVE
    assert any("Include DC Fields" in note for note in plan.notes)
    assert any("linear" in note for note in plan.notes)


def test_fallback_decision_notes_deferral() -> None:
    plan = build((make_definition(dc_current_a=5.0),), dc_bias_decision=FALLBACK)
    assert any("deferred" in note and "2024 R2" in note for note in plan.notes)


def test_blocked_decision_notes_reason() -> None:
    plan = build((make_definition(dc_current_a=5.0),), dc_bias_decision=BLOCKED)
    assert any("unreviewed" in note for note in plan.notes)


def test_zero_dc_current_emits_no_dc_notes() -> None:
    plan = build((make_definition(dc_current_a=0.0),), dc_bias_decision=NATIVE)
    assert not any("DC" in note for note in plan.notes)
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/simulation/test_plan_builder.py -q`
Expected: FAIL — unexpected keyword `dc_bias_decision`.

- [ ] **Step 3: Implement**

In `maxwell_plan.py`: import `DcBiasDecision`, `DcBiasStrategy` from `inductor_designer.simulation.capabilities`; add to `Maxwell3dDesignPlan` after `notes`:

```python
    dc_bias: DcBiasDecision | None = None
```

Append the shared helper:

```python
def dc_bias_notes(decision: DcBiasDecision | None, dc_requested: bool) -> tuple[str, ...]:
    """Human-visible DC-bias treatment notes for plans and manifests."""
    if not dc_requested:
        return ()
    if decision is None:
        return ("DC operating currents are recorded but not applied; no capability decision.",)
    if decision.strategy is DcBiasStrategy.NATIVE_INCLUDE_DC_FIELDS:
        return (
            "DC operating point applied natively via 3D Include DC Fields.",
            "Core material is linear until Milestone 5; DC bias has no incremental "
            "effect on a linear material.",
        )
    if decision.strategy is DcBiasStrategy.MAGNETOSTATIC_INCREMENTAL_FALLBACK:
        return (
            "DC operating currents are recorded but not applied; the 2024 R2 "
            "Magnetostatic fallback is deferred until a 2024 R2 installation exists.",
        )
    return (f"DC operating currents are recorded but not applied: {decision.reason}",)
```

In `plan_builder.py`: add `dc_bias_decision: DcBiasDecision | None = None` as the last parameter of `build_maxwell3d_plan`; import `dc_bias_notes` and `DcBiasDecision`; replace the existing DC note block

```python
    if any(group.dc_current_a != 0.0 for group in groups):
        notes.append(
            "DC operating currents are recorded but not applied; DC bias is Milestone 4 work."
        )
```

with

```python
    dc_requested = any(group.dc_current_a != 0.0 for group in groups)
    notes.extend(dc_bias_notes(dc_bias_decision, dc_requested))
```

and pass `dc_bias=dc_bias_decision` into the returned `Maxwell3dDesignPlan`.

Update the existing `test_setup_mesh_reports_and_notes` expectation: with `dc_bias_decision=None` (default) and `dc_current_a=5.0` the note text is now `"DC operating currents are recorded but not applied; no capability decision."` — adjust its `"Milestone 4"` assertion to `"no capability decision"`.

- [ ] **Step 4: Run gates.** Expected: PASS (M3 constructor calls unaffected — new field has a default).

- [ ] **Step 5: Commit**

```bash
git add src/inductor_designer/simulation/maxwell_plan.py src/inductor_designer/simulation/plan_builder.py tests/unit/simulation/test_plan_builder.py
git commit -m "feat(simulation): carry DC-bias decision and notes in the 3D plan"
```

---

### Task 4: 3D adapter — native Include DC Fields

**Files:**
- Modify: `src/inductor_designer/adapters/pyaedt/maxwell3d.py` (`_stage_setup`, `_stage_excitations`)
- Modify: `tests/fakes/maxwell3d_app.py` (winding boundary fake)
- Test: `tests/unit/adapters/test_maxwell3d_exporter.py` (extend)

**Interfaces:**
- Consumes: `plan.dc_bias`, `DcBiasStrategy`.
- Produces: with native strategy + nonzero DC — setup `props["IncludeDcFields"] = True`; each `assign_winding` return gets `props["DCValue"] = f"{dc:g}A"` then `.update()`. **Verify-at-AEDT risk: both prop names.**

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/adapters/test_maxwell3d_exporter.py` (imports: `DcBiasDecision`, `DcBiasStrategy` from capabilities; `dataclasses.replace`):

```python
def native_request(tmp_path: Path) -> Maxwell3dExportRequest:
    from dataclasses import replace

    base = make_request(tmp_path)
    decision = DcBiasDecision(DcBiasStrategy.NATIVE_INCLUDE_DC_FIELDS, False, "native ok")
    windings = tuple(replace(g, dc_current_a=5.0) for g in base.plan.windings)
    return replace(base, plan=replace(base.plan, windings=windings, dc_bias=decision))


def test_native_dc_sets_setup_flag_and_winding_dc(tmp_path: Path) -> None:
    app = FakeMaxwell3dApp()
    exporter = PyaedtMaxwell3dExporter(app_factory=FakeMaxwell3dAppFactory(app))
    result = exporter.export(native_request(tmp_path))
    assert result.succeeded()
    setup_updates = [k for n, k in app.calls if n == "setup.update"]
    assert setup_updates[0]["props"]["IncludeDcFields"] is True
    dc_sets = [k for n, k in app.calls if n == "winding.set_prop"]
    assert dc_sets == [{"name": "w1", "key": "DCValue", "value": "5A"}]
    winding_updates = [k for n, k in app.calls if n == "winding.update"]
    assert len(winding_updates) == 1


def test_no_dc_flag_without_native_decision(tmp_path: Path) -> None:
    app = FakeMaxwell3dApp()
    exporter = PyaedtMaxwell3dExporter(app_factory=FakeMaxwell3dAppFactory(app))
    exporter.export(make_request(tmp_path))
    setup_updates = [k for n, k in app.calls if n == "setup.update"]
    assert "IncludeDcFields" not in setup_updates[0]["props"]
    assert not [k for n, k in app.calls if n == "winding.set_prop"]
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/adapters/test_maxwell3d_exporter.py -q`
Expected: FAIL — no `winding.set_prop` records, no `IncludeDcFields` prop.

- [ ] **Step 3: Implement**

In `tests/fakes/maxwell3d_app.py`, add a boundary fake and return it from `assign_winding`:

```python
class _FakeWinding:
    def __init__(self, log: list[tuple[str, dict[str, Any]]], name: str) -> None:
        self._log = log
        self._name = name
        self.props = _PropsProxy(log, name)

    def update(self) -> bool:
        self._log.append(("winding.update", {"name": self._name}))
        return True


class _PropsProxy(dict[str, Any]):
    def __init__(self, log: list[tuple[str, dict[str, Any]]], name: str) -> None:
        super().__init__()
        self._log = log
        self._name = name

    def __setitem__(self, key: str, value: Any) -> None:
        self._log.append(("winding.set_prop", {"name": self._name, "key": key, "value": value}))
        super().__setitem__(key, value)
```

and change `assign_winding` to:

```python
    def assign_winding(self, assignment: Any = None, **kwargs: Any) -> Any:
        if self.raise_on == "assign_winding":
            raise RuntimeError("boom in assign_winding")
        self.calls.append(("assign_winding", {"assignment": assignment, **kwargs}))
        return _FakeWinding(self.calls, str(kwargs.get("name")))
```

In `maxwell3d.py`, add imports `from inductor_designer.simulation.capabilities import DcBiasStrategy` and a helper:

```python
def _native_dc_active(plan: Maxwell3dDesignPlan) -> bool:
    return (
        plan.dc_bias is not None
        and plan.dc_bias.strategy is DcBiasStrategy.NATIVE_INCLUDE_DC_FIELDS
        and any(group.dc_current_a != 0.0 for group in plan.windings)
    )
```

In `_stage_excitations`, capture the winding boundary and set DC when native:

```python
        winding = app.assign_winding(
            assignment=None,
            winding_type="Current",
            is_solid=group.is_solid,
            current=group.current_peak_a,
            phase=group.phase_deg,
            name=group.name,
        )
        if _native_dc_active(plan) and group.dc_current_a != 0.0:
            winding.props["DCValue"] = f"{group.dc_current_a:g}A"
            winding.update()
        app.add_winding_coils(assignment=group.name, coils=coil_names)
```

In `_stage_setup`, before `setup.update()`:

```python
    if _native_dc_active(plan):
        setup.props["IncludeDcFields"] = True
```

Extend both stage messages to mention DC when applied (e.g. `f"... DC applied to {n} windings."`).

- [ ] **Step 4: Run gates.** Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/inductor_designer/adapters/pyaedt/maxwell3d.py tests/fakes/maxwell3d_app.py tests/unit/adapters/test_maxwell3d_exporter.py
git commit -m "feat(adapters): apply native Include DC Fields in the 3D export"
```

---

### Task 5: Maxwell 2D plan types

**Files:**
- Create: `src/inductor_designer/simulation/maxwell2d_plan.py`
- Test: `tests/unit/simulation/test_maxwell2d_plan.py`

**Interfaces (all frozen slots dataclasses):**
- `DESIGN_NAME_2D = "Inductor2D"`.
- `Conductor2dPlan(name: str, x_m: float, y_m: float, radius_m: float, polarity: Polarity)`.
- `Winding2dGroupPlan(name: str, winding_id: str, is_solid: bool, current_peak_a: float, phase_deg: float, dc_current_a: float, conductors: tuple[Conductor2dPlan, ...])`.
- `Core2dPlan(name: str, r_inner_m: float, r_outer_m: float, material: MaterialSpec)` — `__post_init__` requires `0 < r_inner_m < r_outer_m`.
- `Maxwell2dDesignPlan(design_name, solution_type, model_depth_m, core: Core2dPlan, windings: tuple[Winding2dGroupPlan, ...], region: RegionPlan, mesh: MeshPlan, setup: SetupPlan, matrix_name: str, reports: tuple[ReportPlan, ...], notes: tuple[str, ...], dc_bias: DcBiasDecision | None = None)` — `__post_init__` requires `model_depth_m > 0`.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/simulation/test_maxwell2d_plan.py`:

```python
from __future__ import annotations

import pytest

from inductor_designer.simulation.maxwell2d_plan import Core2dPlan, Maxwell2dDesignPlan
from inductor_designer.simulation.maxwell_plan import (
    MATRIX_NAME,
    MaterialSpec,
    MeshPlan,
    RegionPlan,
    SetupPlan,
)

MATERIAL = MaterialSpec(
    name="Magnetics_Kool_Mu_60", relative_permeability=60.0, conductivity_s_per_m=0.0, draft=False
)


def test_core_plan_validates_radii() -> None:
    with pytest.raises(ValueError, match="r_inner"):
        Core2dPlan(name="Core", r_inner_m=0.02, r_outer_m=0.01, material=MATERIAL)


def test_design_plan_validates_depth() -> None:
    with pytest.raises(ValueError, match="model_depth"):
        Maxwell2dDesignPlan(
            design_name="Inductor2D",
            solution_type="EddyCurrent",
            model_depth_m=0.0,
            core=Core2dPlan(name="Core", r_inner_m=0.01, r_outer_m=0.02, material=MATERIAL),
            windings=(),
            region=RegionPlan(padding_percent=100.0),
            mesh=MeshPlan(conductor_max_length_m=0.001, core_max_length_m=0.003),
            setup=SetupPlan(name="Setup1", frequency_hz=1e5, maximum_passes=10, percent_error=1.0),
            matrix_name=MATRIX_NAME,
            reports=(),
            notes=(),
        )
```

- [ ] **Step 2: Run to verify failure.** `pytest tests/unit/simulation/test_maxwell2d_plan.py -q` → module not found.

- [ ] **Step 3: Implement**

Create `src/inductor_designer/simulation/maxwell2d_plan.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

from inductor_designer.simulation.capabilities import DcBiasDecision
from inductor_designer.simulation.maxwell_plan import (
    MaterialSpec,
    MeshPlan,
    Polarity,
    RegionPlan,
    ReportPlan,
    SetupPlan,
)

DESIGN_NAME_2D = "Inductor2D"


@dataclass(frozen=True, slots=True)
class Conductor2dPlan:
    """One circular conductor region of the XY cross-section (go or return)."""

    name: str
    x_m: float
    y_m: float
    radius_m: float
    polarity: Polarity


@dataclass(frozen=True, slots=True)
class Winding2dGroupPlan:
    name: str
    winding_id: str
    is_solid: bool
    current_peak_a: float
    phase_deg: float
    dc_current_a: float
    conductors: tuple[Conductor2dPlan, ...]


@dataclass(frozen=True, slots=True)
class Core2dPlan:
    name: str
    r_inner_m: float
    r_outer_m: float
    material: MaterialSpec

    def __post_init__(self) -> None:
        if not 0.0 < self.r_inner_m < self.r_outer_m:
            raise ValueError("Core2dPlan requires 0 < r_inner_m < r_outer_m")


@dataclass(frozen=True, slots=True)
class Maxwell2dDesignPlan:
    design_name: str
    solution_type: str
    model_depth_m: float
    core: Core2dPlan
    windings: tuple[Winding2dGroupPlan, ...]
    region: RegionPlan
    mesh: MeshPlan
    setup: SetupPlan
    matrix_name: str
    reports: tuple[ReportPlan, ...]
    notes: tuple[str, ...]
    dc_bias: DcBiasDecision | None = None

    def __post_init__(self) -> None:
        if not self.model_depth_m > 0.0:
            raise ValueError("Maxwell2dDesignPlan model_depth_m must be positive")
```

- [ ] **Step 4: Run gates.** Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/inductor_designer/simulation/maxwell2d_plan.py tests/unit/simulation/test_maxwell2d_plan.py
git commit -m "feat(simulation): Maxwell 2D design-plan types"
```

---

### Task 6: 2D plan builder

**Files:**
- Create: `src/inductor_designer/simulation/plan_builder2d.py`
- Test: `tests/unit/simulation/test_plan_builder2d.py`

**Interfaces:**
- Consumes: `PlanarModel`/`PlanarWinding`/`PlanarConductor` (`geometry/planar.py`: conductor fields `x_m, y_m, radius_m, polarity:int` where +1 = inner/go, -1 = outer/return; `depth_m = 2·half_height`), `WindingDefinition`, `core_material_spec`, `unique_identifiers`, `core_name`, `_polarity` convention (reimplemented locally as `base_polarity`), `dc_bias_notes`.
- Produces: `build_maxwell2d_plan(planar: PlanarModel, core_record: CoreRecord, windings: Sequence[WindingDefinition], bare_diameter_m: Mapping[str, float], dc_bias_decision: DcBiasDecision | None = None) -> Maxwell2dDesignPlan`; raises `PlanBuildError`.
- Conductor names `f"{base}_C{index:03d}"` (index over the winding's conductors, 1-based). Effective polarity = base D6 polarity, inverted when `PlanarConductor.polarity < 0`.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/simulation/test_plan_builder2d.py`:

```python
from __future__ import annotations

import pytest

from inductor_designer.geometry.core_solid import FinishedCore
from inductor_designer.geometry.packing import WindingSpec, pack_winding
from inductor_designer.geometry.planar import build_planar_model
from inductor_designer.simulation.maxwell_plan import PlanBuildError, Polarity
from inductor_designer.simulation.plan_builder2d import build_maxwell2d_plan
from tests.unit.simulation.test_maxwell_plan import make_core_record
from tests.unit.simulation.test_plan_builder import BARE, CORE, make_definition


def planar_for(definitions: tuple[object, ...]) -> object:
    packings = tuple(
        pack_winding(
            CORE,
            WindingSpec(
                winding_id=d.winding_id,
                turns=d.turns,
                insulated_diameter_m=0.0011,
                start_deg=d.start_angle_deg,
                sector_deg=d.sector_deg,
                min_spacing_m=d.min_spacing_m,
                min_clearance_m=d.min_clearance_m,
            ),
        )
        for d in definitions
    )
    return build_planar_model(CORE, packings, {d.winding_id: BARE / 2.0 for d in definitions})


def build2d(definitions: tuple[object, ...], **kwargs: object) -> object:
    return build_maxwell2d_plan(
        planar_for(definitions),
        make_core_record(),
        definitions,
        {d.winding_id: BARE for d in definitions},
        **kwargs,
    )


def test_plan_shape_names_and_depth() -> None:
    plan = build2d((make_definition(),))
    assert plan.design_name == "Inductor2D"
    assert plan.solution_type == "EddyCurrent"
    assert plan.model_depth_m == round(2.0 * CORE.half_height_m, 9)
    assert plan.core.r_inner_m == CORE.r_inner_m
    assert plan.core.r_outer_m == CORE.r_outer_m
    group = plan.windings[0]
    assert group.name == "w1"
    # 4 turns -> 8 conductors (go/return pairs)
    assert len(group.conductors) == 8
    assert group.conductors[0].name == "w1_C001"
    assert group.conductors[0].radius_m == BARE / 2.0


def test_return_conductor_polarity_inverts() -> None:
    plan = build2d((make_definition(),))  # FORWARD + CCW -> base Positive
    polarities = {c.polarity for c in plan.windings[0].conductors}
    assert polarities == {Polarity.POSITIVE, Polarity.NEGATIVE}
    positives = [c for c in plan.windings[0].conductors if c.polarity is Polarity.POSITIVE]
    negatives = [c for c in plan.windings[0].conductors if c.polarity is Polarity.NEGATIVE]
    assert len(positives) == len(negatives) == 4


def test_two_d_approximation_note_always_present() -> None:
    plan = build2d((make_definition(dc_current_a=0.0),))
    assert any("approximate" in note and "cross-section" in note for note in plan.notes)


def test_mixed_frequencies_refused() -> None:
    with pytest.raises(PlanBuildError, match="frequency"):
        build2d(
            (
                make_definition(winding_id="w1", sector_deg=100.0),
                make_definition(
                    winding_id="w2", start_angle_deg=180.0, sector_deg=100.0,
                    frequency_hz=50_000.0,
                ),
            )
        )
```

- [ ] **Step 2: Run to verify failure.** Module not found.

- [ ] **Step 3: Implement**

Create `src/inductor_designer/simulation/plan_builder2d.py`:

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
from inductor_designer.geometry.naming import core_name, unique_identifiers
from inductor_designer.geometry.planar import PlanarModel
from inductor_designer.simulation.capabilities import DcBiasDecision
from inductor_designer.simulation.maxwell2d_plan import (
    DESIGN_NAME_2D,
    Conductor2dPlan,
    Core2dPlan,
    Maxwell2dDesignPlan,
    Winding2dGroupPlan,
)
from inductor_designer.simulation.maxwell_plan import (
    MATRIX_NAME,
    REGION_PADDING_PERCENT,
    SETUP_NAME,
    SOLUTION_TYPE,
    MeshPlan,
    PlanBuildError,
    Polarity,
    RegionPlan,
    ReportPlan,
    SetupPlan,
    core_material_spec,
    dc_bias_notes,
)

_TWO_D_NOTE = (
    "The 2D model is a documented approximate XY cross-section equivalent; turns and "
    "polarity are represented through coil and winding assignments, and model depth "
    "derives from the core height."
)


def _base_polarity(definition: WindingDefinition) -> Polarity:
    positive = (definition.current_direction is CurrentDirection.FORWARD) == (
        definition.winding_direction is WindingDirection.COUNTERCLOCKWISE
    )
    return Polarity.POSITIVE if positive else Polarity.NEGATIVE


def _invert(polarity: Polarity) -> Polarity:
    return Polarity.NEGATIVE if polarity is Polarity.POSITIVE else Polarity.POSITIVE


def build_maxwell2d_plan(
    planar: PlanarModel,
    core_record: CoreRecord,
    windings: Sequence[WindingDefinition],
    bare_diameter_m: Mapping[str, float],
    dc_bias_decision: DcBiasDecision | None = None,
) -> Maxwell2dDesignPlan:
    issues: list[str] = []
    by_id = {definition.winding_id: definition for definition in windings}
    if not planar.windings:
        issues.append("No planar windings; nothing to export.")
    missing = [w.winding_id for w in planar.windings if w.winding_id not in by_id]
    if missing:
        issues.append(f"Planar windings without definitions: {missing}.")
    frequencies = sorted({definition.frequency_hz for definition in windings})
    if len(frequencies) > 1:
        issues.append(f"All windings must share one frequency; got {frequencies}.")
    if issues:
        raise PlanBuildError(tuple(issues))
    material = core_material_spec(core_record)

    identifiers = unique_identifiers([w.winding_id for w in planar.windings])
    groups: list[Winding2dGroupPlan] = []
    max_bare = 0.0
    for planar_winding in planar.windings:
        definition = by_id[planar_winding.winding_id]
        base = identifiers[planar_winding.winding_id]
        bare = bare_diameter_m[planar_winding.winding_id]
        max_bare = max(max_bare, bare)
        base_polarity = _base_polarity(definition)
        conductors = tuple(
            Conductor2dPlan(
                name=f"{base}_C{index:03d}",
                x_m=conductor.x_m,
                y_m=conductor.y_m,
                radius_m=conductor.radius_m,
                polarity=(
                    base_polarity if conductor.polarity > 0 else _invert(base_polarity)
                ),
            )
            for index, conductor in enumerate(planar_winding.conductors, start=1)
        )
        groups.append(
            Winding2dGroupPlan(
                name=base,
                winding_id=planar_winding.winding_id,
                is_solid=definition.mode is ConductorMode.SOLID,
                current_peak_a=definition.ac_magnitude_a,
                phase_deg=definition.ac_phase_deg,
                dc_current_a=definition.dc_current_a,
                conductors=conductors,
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

    notes: list[str] = [_TWO_D_NOTE]
    if material.draft:
        notes.append(
            f"Core material {material.name} derives from a draft catalog record; "
            "verify against the manufacturer catalog before trusting results."
        )
    dc_requested = any(group.dc_current_a != 0.0 for group in groups)
    notes.extend(dc_bias_notes(dc_bias_decision, dc_requested))

    return Maxwell2dDesignPlan(
        design_name=DESIGN_NAME_2D,
        solution_type=SOLUTION_TYPE,
        model_depth_m=planar.depth_m,
        core=Core2dPlan(
            name=core_name(),
            r_inner_m=planar.r_inner_m,
            r_outer_m=planar.r_outer_m,
            material=material,
        ),
        windings=tuple(groups),
        region=RegionPlan(padding_percent=REGION_PADDING_PERCENT),
        mesh=MeshPlan(
            conductor_max_length_m=round(1.5 * max_bare, 9),
            core_max_length_m=round((planar.r_outer_m - planar.r_inner_m) / 3.0, 9),
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
        dc_bias=dc_bias_decision,
    )
```

- [ ] **Step 4: Run gates.** Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/inductor_designer/simulation/plan_builder2d.py tests/unit/simulation/test_plan_builder2d.py
git commit -m "feat(simulation): build Maxwell 2D plan from the planar model"
```

---

### Task 7: 2D exporter port, fake, contract test

**Files:**
- Create: `src/inductor_designer/application/ports/maxwell2d_exporter.py`
- Create: `tests/fakes/maxwell2d_exporter.py`
- Test: `tests/contract/test_maxwell2d_exporter_contract.py`

**Interfaces:**
- `STAGE_NAMES_2D: tuple[str, ...] = ("launch", "units", "materials", "core", "conductors", "excitations", "eddy", "region", "mesh", "setup", "matrix", "reports", "validate", "save")` (no terminals stage — coils attach to the conductor regions directly).
- `Maxwell2dExportRequest(plan: Maxwell2dDesignPlan, release, edition, non_graphical, output_directory: Path, project_name: str)`.
- `class Maxwell2dExporter(Protocol): def export(self, request: Maxwell2dExportRequest) -> MaxwellExportResult: ...` — result class reused via the Task 2 alias (`StageRecord` too).
- Fake `RecordingMaxwell2dExporter` mirroring the 3D fake.

- [ ] **Step 1: Write the failing contract test**

Create `tests/contract/test_maxwell2d_exporter_contract.py`:

```python
from __future__ import annotations

from pathlib import Path

from inductor_designer.application.ports.maxwell2d_exporter import (
    STAGE_NAMES_2D,
    Maxwell2dExportRequest,
)
from inductor_designer.domain.aedt_target import AedtEdition, AedtRelease
from tests.fakes.maxwell2d_exporter import RecordingMaxwell2dExporter
from tests.unit.simulation.test_plan_builder2d import build2d
from tests.unit.simulation.test_plan_builder import make_definition


def make_request(tmp_path: Path) -> Maxwell2dExportRequest:
    return Maxwell2dExportRequest(
        plan=build2d((make_definition(),)),  # type: ignore[arg-type]
        release=AedtRelease(2025, 2),
        edition=AedtEdition.COMMERCIAL,
        non_graphical=True,
        output_directory=tmp_path,
        project_name="Boost_inductor_2d",
    )


def test_fake_records_and_reports_full_stage_sequence(tmp_path: Path) -> None:
    exporter = RecordingMaxwell2dExporter()
    request = make_request(tmp_path)
    result = exporter.export(request)
    assert exporter.requests == [request]
    assert tuple(stage.name for stage in result.stages) == STAGE_NAMES_2D
    assert result.succeeded()
    assert result.project_path == tmp_path / "Boost_inductor_2d.aedt"
    assert result.design_name == "Inductor2D"
```

- [ ] **Step 2: Run to verify failure.** Module not found.

- [ ] **Step 3: Implement**

Create `src/inductor_designer/application/ports/maxwell2d_exporter.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from inductor_designer.application.ports.maxwell_exporter import MaxwellExportResult
from inductor_designer.domain.aedt_target import AedtEdition, AedtRelease
from inductor_designer.simulation.maxwell2d_plan import Maxwell2dDesignPlan

STAGE_NAMES_2D: tuple[str, ...] = (
    "launch",
    "units",
    "materials",
    "core",
    "conductors",
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
class Maxwell2dExportRequest:
    plan: Maxwell2dDesignPlan
    release: AedtRelease
    edition: AedtEdition
    non_graphical: bool
    output_directory: Path
    project_name: str


class Maxwell2dExporter(Protocol):
    def export(self, request: Maxwell2dExportRequest) -> MaxwellExportResult: ...
```

Create `tests/fakes/maxwell2d_exporter.py`:

```python
from __future__ import annotations

from inductor_designer.application.ports.maxwell2d_exporter import (
    STAGE_NAMES_2D,
    Maxwell2dExportRequest,
)
from inductor_designer.application.ports.maxwell_exporter import (
    MaxwellExportResult,
    StageRecord,
)


class RecordingMaxwell2dExporter:
    """Port fake: records requests, never launches AEDT."""

    def __init__(self) -> None:
        self.requests: list[Maxwell2dExportRequest] = []

    def export(self, request: Maxwell2dExportRequest) -> MaxwellExportResult:
        self.requests.append(request)
        return MaxwellExportResult(
            project_path=request.output_directory / f"{request.project_name}.aedt",
            design_name=request.plan.design_name,
            pyaedt_version="recording-fake",
            stages=tuple(
                StageRecord(name=name, succeeded=True, message="recorded")
                for name in STAGE_NAMES_2D
            ),
        )
```

- [ ] **Step 4: Run gates.** Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/inductor_designer/application/ports/maxwell2d_exporter.py tests/fakes/maxwell2d_exporter.py tests/contract/test_maxwell2d_exporter_contract.py
git commit -m "feat(application): Maxwell 2D exporter port with recording fake"
```

---

### Task 8: Services — capabilities wiring, `export_maxwell2d`, manifest v2

**Files:**
- Modify: `src/inductor_designer/application/services/maxwell_export.py`
- Modify: `tools/generate_maxwell3d.py` (pass capabilities; `--matrix` arg)
- Test: `tests/unit/application/test_maxwell_export.py` (extend/update), `tests/unit/tools/test_generate_maxwell3d.py` (update)

**Interfaces:**
- `export_maxwell3d(project, catalog, exporter, output_directory, *, capabilities: CapabilitySnapshot, non_graphical=True) -> MaxwellExportOutcome` — **breaking keyword addition**; computes `decision = select_dc_bias_strategy(capabilities, ModelDimension.THREE_D)`, forwards to the builder.
- `export_maxwell2d(project, catalog, exporter: Maxwell2dExporter, output_directory, *, capabilities, non_graphical=True) -> MaxwellExportOutcome` — requires `dimension_mode is TWO_D`, catalog core, no collisions; builds `build_maxwell2d_plan(model.planar, snapshot, project.windings, model.bare_diameter_m, decision)` with `decision = select_dc_bias_strategy(capabilities, ModelDimension.TWO_D)`.
- `MaxwellExportOutcome(plan: Maxwell3dDesignPlan | Maxwell2dDesignPlan, result: MaxwellExportResult, capabilities: CapabilitySnapshot, decision: DcBiasDecision, dimension: ModelDimension)`.
- `generation_manifest_json(outcome) -> str` — schemaVersion **2**; adds `dimension`, `dcBias`, `capabilities`; winding entries carry `turnCount` (3D) or `conductorCount` (2D).

- [ ] **Step 1: Write the failing tests**

In `tests/unit/application/test_maxwell_export.py` add imports and a default snapshot, update existing calls to pass `capabilities=SNAPSHOT`, and append:

```python
from inductor_designer.simulation.capabilities import (
    CapabilityReviewStatus,
    CapabilitySnapshot,
)
from inductor_designer.domain.aedt_target import AedtEdition, AedtRelease
from tests.fakes.maxwell2d_exporter import RecordingMaxwell2dExporter
from inductor_designer.application.services.maxwell_export import export_maxwell2d

SNAPSHOT = CapabilitySnapshot(
    release=AedtRelease(2025, 2),
    edition=AedtEdition.COMMERCIAL,
    include_dc_fields_3d=None,
    discovered_limits=(),
    evidence_source="test",
    review_status=CapabilityReviewStatus.REVIEWED,
)

NATIVE_SNAPSHOT = CapabilitySnapshot(
    release=AedtRelease(2025, 2),
    edition=AedtEdition.COMMERCIAL,
    include_dc_fields_3d=True,
    discovered_limits=(),
    evidence_source="test",
    review_status=CapabilityReviewStatus.REVIEWED,
)


def test_3d_manifest_v2_identifies_blocked_dc(tmp_path: Path) -> None:
    outcome = export_maxwell3d(
        three_d_project(), CATALOG, RecordingMaxwell3dExporter(), tmp_path,  # type: ignore[arg-type]
        capabilities=SNAPSHOT,
    )
    payload = json.loads(generation_manifest_json(outcome))
    assert payload["schemaVersion"] == 2
    assert payload["dimension"] == "3d"
    assert payload["dcBias"]["strategy"] == "blocked"
    assert payload["dcBias"]["appliedCurrentsA"] is None
    assert payload["capabilities"]["includeDcFields3d"] is None
    assert payload["capabilities"]["reviewStatus"] == "reviewed"


def test_3d_native_dc_applied_currents_in_manifest(tmp_path: Path) -> None:
    outcome = export_maxwell3d(
        three_d_project(), CATALOG, RecordingMaxwell3dExporter(), tmp_path,  # type: ignore[arg-type]
        capabilities=NATIVE_SNAPSHOT,
    )
    payload = json.loads(generation_manifest_json(outcome))
    assert payload["dcBias"]["strategy"] == "native-include-dc-fields"
    assert payload["dcBias"]["appliedCurrentsA"] == {"w1": 5.0, "w2": 5.0}
    assert outcome.plan.dc_bias is outcome.decision


def test_2d_export_blocked_dc_and_conductor_count(tmp_path: Path) -> None:
    project = replace(three_d_project(), dimension_mode=ModelDimension.TWO_D)  # type: ignore[type-var]
    outcome = export_maxwell2d(
        project, CATALOG, RecordingMaxwell2dExporter(), tmp_path,  # type: ignore[arg-type]
        capabilities=NATIVE_SNAPSHOT,
    )
    payload = json.loads(generation_manifest_json(outcome))
    assert payload["dimension"] == "2d"
    assert payload["dcBias"]["strategy"] == "blocked"
    assert "Maxwell 2D" in payload["dcBias"]["reason"]
    assert payload["windings"][0]["conductorCount"] == 20
    assert any("approximate" in note for note in payload["notes"])


def test_2d_refuses_3d_project(tmp_path: Path) -> None:
    with pytest.raises(MaxwellExportBlocked, match="2d"):
        export_maxwell2d(
            three_d_project(), CATALOG, RecordingMaxwell2dExporter(), tmp_path,  # type: ignore[arg-type]
            capabilities=SNAPSHOT,
        )
```

(`make_winding` defaults `dc_current_a=5.0` — that is what `appliedCurrentsA` picks up. 10 turns → 20 planar conductors.)

- [ ] **Step 2: Run to verify failure.** Unexpected keyword `capabilities` / missing `export_maxwell2d`.

- [ ] **Step 3: Implement**

Rewrite `maxwell_export.py` (full replacement — current content is small):

```python
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from inductor_designer.application.ports.catalog import CatalogRepository
from inductor_designer.application.ports.maxwell2d_exporter import (
    Maxwell2dExporter,
    Maxwell2dExportRequest,
)
from inductor_designer.application.ports.maxwell_exporter import (
    Maxwell3dExporter,
    Maxwell3dExportRequest,
    MaxwellExportResult,
)
from inductor_designer.application.services.geometry_model import build_geometry_model
from inductor_designer.domain.aedt_target import ModelDimension
from inductor_designer.domain.project import CatalogCoreSelection, InductorProject
from inductor_designer.geometry.naming import sanitize_identifier
from inductor_designer.simulation.capabilities import (
    CapabilitySnapshot,
    DcBiasDecision,
    DcBiasStrategy,
    select_dc_bias_strategy,
)
from inductor_designer.simulation.maxwell2d_plan import Maxwell2dDesignPlan
from inductor_designer.simulation.maxwell_plan import Maxwell3dDesignPlan, PlanBuildError
from inductor_designer.simulation.plan_builder import build_maxwell3d_plan
from inductor_designer.simulation.plan_builder2d import build_maxwell2d_plan


class MaxwellExportBlocked(ValueError):
    def __init__(self, issues: tuple[str, ...]) -> None:
        super().__init__("; ".join(issues))
        self.issues = issues


@dataclass(frozen=True, slots=True)
class MaxwellExportOutcome:
    plan: Maxwell3dDesignPlan | Maxwell2dDesignPlan
    result: MaxwellExportResult
    capabilities: CapabilitySnapshot
    decision: DcBiasDecision
    dimension: ModelDimension


def _validated_model(
    project: InductorProject,
    catalog: CatalogRepository,
    expected: ModelDimension,
) -> tuple[CatalogCoreSelection, object]:
    if project.dimension_mode is not expected:
        raise MaxwellExportBlocked(
            (f"Project dimension mode must be {expected.value} for this export.",)
        )
    core_selection = project.core
    if not isinstance(core_selection, CatalogCoreSelection):
        raise MaxwellExportBlocked(
            ("Catalog cores only; manual cores carry no material identity.",)
        )
    model = build_geometry_model(project, catalog)
    if model.collisions:
        raise MaxwellExportBlocked(tuple(issue.message for issue in model.collisions))
    return core_selection, model


def export_maxwell3d(
    project: InductorProject,
    catalog: CatalogRepository,
    exporter: Maxwell3dExporter,
    output_directory: Path,
    *,
    capabilities: CapabilitySnapshot,
    non_graphical: bool = True,
) -> MaxwellExportOutcome:
    core_selection, model = _validated_model(project, catalog, ModelDimension.THREE_D)
    decision = select_dc_bias_strategy(capabilities, ModelDimension.THREE_D)
    try:
        plan = build_maxwell3d_plan(
            model.core,  # type: ignore[attr-defined]
            core_selection.snapshot,
            model.packings,  # type: ignore[attr-defined]
            project.windings,
            model.bare_diameter_m,  # type: ignore[attr-defined]
            dc_bias_decision=decision,
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
    return MaxwellExportOutcome(
        plan=plan,
        result=exporter.export(request),
        capabilities=capabilities,
        decision=decision,
        dimension=ModelDimension.THREE_D,
    )


def export_maxwell2d(
    project: InductorProject,
    catalog: CatalogRepository,
    exporter: Maxwell2dExporter,
    output_directory: Path,
    *,
    capabilities: CapabilitySnapshot,
    non_graphical: bool = True,
) -> MaxwellExportOutcome:
    core_selection, model = _validated_model(project, catalog, ModelDimension.TWO_D)
    decision = select_dc_bias_strategy(capabilities, ModelDimension.TWO_D)
    try:
        plan = build_maxwell2d_plan(
            model.planar,  # type: ignore[attr-defined]
            core_selection.snapshot,
            project.windings,
            model.bare_diameter_m,  # type: ignore[attr-defined]
            dc_bias_decision=decision,
        )
    except PlanBuildError as error:
        raise MaxwellExportBlocked(error.issues) from error
    request = Maxwell2dExportRequest(
        plan=plan,
        release=project.target_release,
        edition=project.target_edition,
        non_graphical=non_graphical,
        output_directory=output_directory,
        project_name=f"{sanitize_identifier(project.name)}_2d",
    )
    return MaxwellExportOutcome(
        plan=plan,
        result=exporter.export(request),
        capabilities=capabilities,
        decision=decision,
        dimension=ModelDimension.TWO_D,
    )
```

Typing note: `_validated_model` returns the `GeometryModel` as `object` to avoid a circular-import-free precise type; if mypy strict complains at the `# type: ignore[attr-defined]` call sites, instead annotate the return as `tuple[CatalogCoreSelection, GeometryModel]` importing `GeometryModel` from `geometry_model` (no cycle exists — prefer the precise type and drop the ignores).

Manifest v2 (same file):

```python
def _winding_entries(plan: Maxwell3dDesignPlan | Maxwell2dDesignPlan) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for group in plan.windings:
        entry: dict[str, object] = {
            "name": group.name,
            "windingId": group.winding_id,
            "isSolid": group.is_solid,
            "currentPeakA": group.current_peak_a,
            "phaseDeg": group.phase_deg,
            "dcCurrentA": group.dc_current_a,
        }
        if isinstance(plan, Maxwell3dDesignPlan):
            entry["turnCount"] = len(group.turns)  # type: ignore[attr-defined]
        else:
            entry["conductorCount"] = len(group.conductors)  # type: ignore[attr-defined]
        entries.append(entry)
    return entries


def generation_manifest_json(outcome: MaxwellExportOutcome) -> str:
    plan = outcome.plan
    result = outcome.result
    decision = outcome.decision
    capabilities = outcome.capabilities
    dc_requested = any(group.dc_current_a != 0.0 for group in plan.windings)
    applied = (
        {group.name: group.dc_current_a for group in plan.windings if group.dc_current_a != 0.0}
        if dc_requested and decision.strategy is DcBiasStrategy.NATIVE_INCLUDE_DC_FIELDS
        else None
    )
    payload: dict[str, object] = {
        "schemaVersion": 2,
        "dimension": outcome.dimension.value,
        "designName": result.design_name,
        "projectPath": str(result.project_path),
        "pyaedtVersion": result.pyaedt_version,
        "succeeded": result.succeeded(),
        "solutionType": plan.solution_type,
        "frequencyHz": plan.setup.frequency_hz,
        "dcBias": {
            "strategy": decision.strategy.value,
            "approximate": decision.approximate,
            "reason": decision.reason,
            "appliedCurrentsA": applied,
        },
        "capabilities": {
            "release": str(capabilities.release),
            "edition": capabilities.edition.value,
            "includeDcFields3d": capabilities.include_dc_fields_3d,
            "reviewStatus": capabilities.review_status.value,
            "evidenceSource": capabilities.evidence_source,
        },
        "coreMaterial": {
            "name": plan.core.material.name,
            "relativePermeability": plan.core.material.relative_permeability,
            "conductivitySPerM": plan.core.material.conductivity_s_per_m,
            "draft": plan.core.material.draft,
        },
        "windings": _winding_entries(plan),
        "notes": list(plan.notes),
        "stages": [
            {"name": stage.name, "succeeded": stage.succeeded, "message": stage.message}
            for stage in result.stages
        ],
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"
```

`tools/generate_maxwell3d.py`: add

```python
parser.add_argument("--matrix", type=Path, default=ROOT / "compatibility" / "aedt-matrix.yml")
```

plus

```python
from inductor_designer.adapters.compatibility.matrix_repository import MatrixCapabilityRepository
...
capabilities = MatrixCapabilityRepository(args.matrix).snapshot_for(
    project.target_release, project.target_edition
)
```

and pass `capabilities=capabilities` into `export_maxwell3d`. Update `tests/unit/tools/test_generate_maxwell3d.py` expectations: evidence payload now has `schemaVersion == 2` and `payload["dcBias"]["strategy"] == "blocked"` (real matrix row has `includeDcFields3d: null`).

Update every other existing `export_maxwell3d` call site (existing service tests, `tests/integration/aedt/test_maxwell3d_export.py`) to pass `capabilities` (the AEDT test loads it via `MatrixCapabilityRepository(ROOT / "compatibility" / "aedt-matrix.yml")`).

- [ ] **Step 4: Run gates.** Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/inductor_designer/application/services/maxwell_export.py tools/generate_maxwell3d.py tests/unit/application/test_maxwell_export.py tests/unit/tools/test_generate_maxwell3d.py tests/integration/aedt/test_maxwell3d_export.py
git commit -m "feat(application): capability-aware exports and manifest v2 with DC-bias visibility"
```

---

### Task 9: PyAEDT Maxwell 2D exporter

**Files:**
- Create: `src/inductor_designer/adapters/pyaedt/maxwell2d.py`
- Create: `tests/fakes/maxwell2d_app.py`
- Test: `tests/unit/adapters/test_maxwell2d_exporter.py`

**Interfaces:**
- `Maxwell2dApp(Protocol)`: attrs `modeler, mesh, post, materials, model_depth: Any`; methods as 3D (`assign_material, assign_coil, assign_winding, add_winding_coils, eddy_effects_on, create_setup, assign_matrix, validate_simple, save_project, release_desktop`).
- `DefaultMaxwell2dAppFactory` (lazy `from ansys.aedt.core import Maxwell2d`), `PyaedtMaxwell2dExporter(app_factory=None)` implementing the 2D port. Same stage-record plumbing as 3D (launch inline, `_STAGES_2D` list, save inline, `release_desktop` in `finally`, stale-file unlink).
- Stage behavior: `units` — `model_units="meter"`, `app.model_depth = f"{plan.model_depth_m:g}meter"`; `core` — outer circle + bore circle, `subtract`, `assign_material`; `conductors` — one covered circle per `Conductor2dPlan` with `material=COPPER_MATERIAL`; `excitations` — `assign_coil(conductor.name, conductors_number=1, polarity=..., name=f"{conductor.name}_Coil")` then `assign_winding` + `add_winding_coils` per group; `eddy/region/mesh/setup/matrix/reports/validate` mirror 3D (region uses the 4-argument 2D `create_air_region(pad, pad, pad, pad)`).
- **Verify-at-AEDT risks:** 2D `create_circle` kwarg (`origin` vs `position`), 4-arg `create_air_region`, `model_depth` unit-string assignment, `MatrixACMagnetic` applicability to 2D AC Magnetic.

- [ ] **Step 1: Write the failing tests**

Create `tests/fakes/maxwell2d_app.py`:

```python
from __future__ import annotations

from typing import Any

from tests.fakes.maxwell3d_app import (  # reuse recorder pieces
    FakeMaxwell3dApp,
)


class FakeMaxwell2dApp(FakeMaxwell3dApp):
    """2D recorder: same duck-typed surface plus model_depth capture."""

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "model_depth":
            self.calls.append(("set.model_depth", {"value": value}))
        super().__setattr__(name, value)


class FakeMaxwell2dAppFactory:
    pyaedt_version = "fake-pyaedt"

    def __init__(self, app: FakeMaxwell2dApp) -> None:
        self.app = app
        self.create_kwargs: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> FakeMaxwell2dApp:
        self.create_kwargs.append(kwargs)
        return self.app
```

(If `FakeMaxwell3dApp.__init__` sets attributes before `calls` exists, guard: in `FakeMaxwell2dApp.__setattr__`, only record when `hasattr(self, "calls")`.)

Create `tests/unit/adapters/test_maxwell2d_exporter.py`:

```python
from __future__ import annotations

from pathlib import Path

from inductor_designer.adapters.pyaedt.maxwell2d import PyaedtMaxwell2dExporter
from inductor_designer.application.ports.maxwell2d_exporter import STAGE_NAMES_2D
from tests.contract.test_maxwell2d_exporter_contract import make_request
from tests.fakes.maxwell2d_app import FakeMaxwell2dApp, FakeMaxwell2dAppFactory


def run(tmp_path: Path, app: FakeMaxwell2dApp) -> object:
    exporter = PyaedtMaxwell2dExporter(app_factory=FakeMaxwell2dAppFactory(app))
    return exporter.export(make_request(tmp_path))


def test_full_stage_sequence_and_release(tmp_path: Path) -> None:
    app = FakeMaxwell2dApp()
    result = run(tmp_path, app)
    assert tuple(stage.name for stage in result.stages) == STAGE_NAMES_2D
    assert result.succeeded()
    assert app.released == [(True, True)]


def test_geometry_and_depth_calls(tmp_path: Path) -> None:
    app = FakeMaxwell2dApp()
    run(tmp_path, app)
    names = [name for name, _ in app.calls]
    depth_sets = [k for n, k in app.calls if n == "set.model_depth"]
    assert depth_sets and depth_sets[0]["value"].endswith("meter")
    # core outer + bore + 8 conductors
    assert names.count("modeler.create_circle") == 2 + 8
    assert names.count("modeler.subtract") == 1
    coil_calls = [k for n, k in app.calls if n == "assign_coil"]
    assert len(coil_calls) == 8
    polarities = {k["polarity"] for k in coil_calls}
    assert polarities == {"Positive", "Negative"}
    winding_calls = [k for n, k in app.calls if n == "assign_winding"]
    assert len(winding_calls) == 1


def test_failing_stage_truncates_and_releases(tmp_path: Path) -> None:
    app = FakeMaxwell2dApp(raise_on="assign_matrix")
    result = run(tmp_path, app)
    assert not result.succeeded()
    assert result.stages[-1].name == "matrix"
    assert app.released == [(True, True)]
```

- [ ] **Step 2: Run to verify failure.** Module not found.

- [ ] **Step 3: Implement**

Create `src/inductor_designer/adapters/pyaedt/maxwell2d.py` (mirror `maxwell3d.py` structure exactly — protocol, factory, stage functions, exporter class with inline launch/save, `finally: release_desktop`, stale-file unlink):

```python
from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from typing import Any, Protocol, cast

from inductor_designer.application.ports.maxwell2d_exporter import Maxwell2dExportRequest
from inductor_designer.application.ports.maxwell_exporter import (
    MaxwellExportResult,
    StageRecord,
)
from inductor_designer.simulation.maxwell2d_plan import Maxwell2dDesignPlan
from inductor_designer.simulation.maxwell_plan import COPPER_MATERIAL


class Maxwell2dApp(Protocol):
    modeler: Any
    mesh: Any
    post: Any
    materials: Any
    model_depth: Any

    def assign_material(self, assignment: Any, material: str) -> Any: ...

    def assign_coil(self, assignment: Any, **kwargs: Any) -> Any: ...

    def assign_winding(self, assignment: Any = ..., **kwargs: Any) -> Any: ...

    def add_winding_coils(self, assignment: Any, coils: Any) -> Any: ...

    def eddy_effects_on(self, assignment: Any, **kwargs: Any) -> Any: ...

    def create_setup(self, name: str) -> Any: ...

    def assign_matrix(self, assignment: Any, **kwargs: Any) -> Any: ...

    def validate_simple(self, log_file: str | None = None) -> int: ...

    def save_project(self, path: str) -> bool: ...

    def release_desktop(self, close_projects: bool, close_desktop: bool) -> None: ...


class Maxwell2dAppFactory(Protocol):
    pyaedt_version: str

    def create(self, **kwargs: object) -> Maxwell2dApp: ...


class DefaultMaxwell2dAppFactory:
    @property
    def pyaedt_version(self) -> str:
        try:
            return version("pyaedt")
        except PackageNotFoundError:
            return "not-installed"

    def create(self, **kwargs: object) -> Maxwell2dApp:
        from ansys.aedt.core import Maxwell2d

        return cast(Maxwell2dApp, Maxwell2d(**kwargs))


def _stage_units(app: Maxwell2dApp, plan: Maxwell2dDesignPlan) -> str:
    app.modeler.model_units = "meter"
    app.model_depth = f"{plan.model_depth_m:g}meter"
    return f"Units meter; model depth {plan.model_depth_m:g} m."


def _stage_materials(app: Maxwell2dApp, plan: Maxwell2dDesignPlan) -> str:
    spec = plan.core.material
    material = app.materials.add_material(spec.name)
    material.permeability = spec.relative_permeability
    material.conductivity = spec.conductivity_s_per_m
    return f"Material {spec.name} created (draft={spec.draft})."


def _stage_core(app: Maxwell2dApp, plan: Maxwell2dDesignPlan) -> str:
    bore = f"{plan.core.name}_Bore"
    app.modeler.create_circle(
        origin=[0.0, 0.0, 0.0], radius=plan.core.r_outer_m, name=plan.core.name
    )
    app.modeler.create_circle(origin=[0.0, 0.0, 0.0], radius=plan.core.r_inner_m, name=bore)
    app.modeler.subtract(plan.core.name, bore, keep_originals=False)
    app.assign_material(plan.core.name, plan.core.material.name)
    return f"Annular core {plan.core.name} created."


def _stage_conductors(app: Maxwell2dApp, plan: Maxwell2dDesignPlan) -> str:
    count = 0
    for group in plan.windings:
        for conductor in group.conductors:
            app.modeler.create_circle(
                origin=[conductor.x_m, conductor.y_m, 0.0],
                radius=conductor.radius_m,
                name=conductor.name,
                material=COPPER_MATERIAL,
            )
            count += 1
    return f"{count} conductor regions created."


def _stage_excitations(app: Maxwell2dApp, plan: Maxwell2dDesignPlan) -> str:
    for group in plan.windings:
        coil_names: list[str] = []
        for conductor in group.conductors:
            coil = f"{conductor.name}_Coil"
            app.assign_coil(
                conductor.name,
                conductors_number=1,
                polarity=conductor.polarity.value,
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


def _stage_eddy(app: Maxwell2dApp, plan: Maxwell2dDesignPlan) -> str:
    solid = [c.name for g in plan.windings if g.is_solid for c in g.conductors]
    stranded = [c.name for g in plan.windings if not g.is_solid for c in g.conductors]
    if solid:
        app.eddy_effects_on(solid, enable_eddy_effects=True)
    if stranded:
        app.eddy_effects_on(stranded, enable_eddy_effects=False)
    return f"Eddy effects: {len(solid)} solid on, {len(stranded)} stranded off."


def _stage_region(app: Maxwell2dApp, plan: Maxwell2dDesignPlan) -> str:
    pad = plan.region.padding_percent
    app.modeler.create_air_region(pad, pad, pad, pad)
    return f"Air region with {pad:g}% padding."


def _stage_mesh(app: Maxwell2dApp, plan: Maxwell2dDesignPlan) -> str:
    conductors = [c.name for g in plan.windings for c in g.conductors]
    app.mesh.assign_length_mesh(
        conductors, maximum_length=plan.mesh.conductor_max_length_m, name="ConductorLength"
    )
    app.mesh.assign_length_mesh(
        [plan.core.name], maximum_length=plan.mesh.core_max_length_m, name="CoreLength"
    )
    return "Length-based mesh restrictions assigned."


def _stage_setup(app: Maxwell2dApp, plan: Maxwell2dDesignPlan) -> str:
    setup = app.create_setup(name=plan.setup.name)
    setup.props["Frequency"] = f"{plan.setup.frequency_hz:g}Hz"
    setup.props["MaximumPasses"] = plan.setup.maximum_passes
    setup.props["PercentError"] = plan.setup.percent_error
    setup.update()
    return f"Setup {plan.setup.name} at {plan.setup.frequency_hz:g} Hz."


def _stage_matrix(app: Maxwell2dApp, plan: Maxwell2dDesignPlan) -> str:
    from ansys.aedt.core.modules.boundary.maxwell_boundary import (
        MatrixACMagnetic,
        SourceACMagnetic,
    )

    sources = [SourceACMagnetic(name=g.name) for g in plan.windings]
    schema = MatrixACMagnetic(signal_sources=sources, matrix_name=plan.matrix_name)
    app.assign_matrix(schema)
    return f"Matrix {plan.matrix_name} over {len(plan.windings)} windings."


def _stage_reports(app: Maxwell2dApp, plan: Maxwell2dDesignPlan) -> str:
    for report in plan.reports:
        app.post.create_report(expressions=[report.expression], plot_name=report.name)
    return f"{len(plan.reports)} reports requested."


def _stage_validate(app: Maxwell2dApp, plan: Maxwell2dDesignPlan) -> str:
    if app.validate_simple() != 1:
        raise RuntimeError("Design validation failed.")
    return "Design validation passed."


_STAGES_2D: tuple[tuple[str, Any], ...] = (
    ("units", _stage_units),
    ("materials", _stage_materials),
    ("core", _stage_core),
    ("conductors", _stage_conductors),
    ("excitations", _stage_excitations),
    ("eddy", _stage_eddy),
    ("region", _stage_region),
    ("mesh", _stage_mesh),
    ("setup", _stage_setup),
    ("matrix", _stage_matrix),
    ("reports", _stage_reports),
    ("validate", _stage_validate),
)


class PyaedtMaxwell2dExporter:
    """Executes a Maxwell2dDesignPlan as named stages; never reports a partial design."""

    def __init__(self, app_factory: Maxwell2dAppFactory | None = None) -> None:
        self._factory = DefaultMaxwell2dAppFactory() if app_factory is None else app_factory

    def export(self, request: Maxwell2dExportRequest) -> MaxwellExportResult:
        request.output_directory.mkdir(parents=True, exist_ok=True)
        project_path = request.output_directory / f"{request.project_name}.aedt"
        project_path.unlink(missing_ok=True)
        plan = request.plan
        stages: list[StageRecord] = []

        def result() -> MaxwellExportResult:
            return MaxwellExportResult(
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
                message=f"Maxwell 2D design {plan.design_name!r} opened.",
            )
        )
        try:
            for name, stage in _STAGES_2D:
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

- [ ] **Step 4: Run gates.** Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/inductor_designer/adapters/pyaedt/maxwell2d.py tests/fakes/maxwell2d_app.py tests/unit/adapters/test_maxwell2d_exporter.py
git commit -m "feat(adapters): staged Maxwell 2D exporter"
```

---

### Task 10: Exit-criterion release-matrix test

**Files:**
- Test: `tests/integration/test_release_matrix.py`

**Interfaces:** consumes everything above; no production code.

- [ ] **Step 1: Write the test (it should pass immediately — it is the exit-criterion proof; if it fails, that is a real defect in Tasks 1–10)**

Create `tests/integration/test_release_matrix.py`:

```python
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from inductor_designer.adapters.compatibility.matrix_repository import (
    MatrixCapabilityRepository,
)
from inductor_designer.application.services.maxwell_export import (
    export_maxwell2d,
    export_maxwell3d,
    generation_manifest_json,
)
from inductor_designer.domain.aedt_target import AedtEdition, AedtRelease, ModelDimension
from tests.fakes.maxwell2d_exporter import RecordingMaxwell2dExporter
from tests.fakes.maxwell_exporter import RecordingMaxwell3dExporter
from tests.unit.application.test_maxwell_export import three_d_project
from tests.unit.application.test_geometry_model import CATALOG

ROOT = Path(__file__).resolve().parents[2]
REAL_MATRIX = ROOT / "compatibility" / "aedt-matrix.yml"

SYNTHETIC = """\
schemaVersion: 1
rows:
  - release: "2025.2"
    edition: commercial
    status: passed
    includeDcFields3d: true
    discoveredLimits: []
    evidenceReviewedAt: "2026-07-17T00:00:00Z"
    evidenceReviewedBy: fabio
  - release: "2024.2"
    edition: commercial
    status: passed
    includeDcFields3d: false
    discoveredLimits: []
    evidenceReviewedAt: "2026-07-17T00:00:00Z"
    evidenceReviewedBy: fabio
"""


def manifest_3d(matrix: Path, release: AedtRelease, tmp_path: Path) -> dict[str, object]:
    capabilities = MatrixCapabilityRepository(matrix).snapshot_for(
        release, AedtEdition.COMMERCIAL
    )
    project = replace(three_d_project(), target_release=release)  # type: ignore[type-var]
    outcome = export_maxwell3d(
        project, CATALOG, RecordingMaxwell3dExporter(), tmp_path,  # type: ignore[arg-type]
        capabilities=capabilities,
    )
    return json.loads(generation_manifest_json(outcome))


def test_real_matrix_2025_2_is_blocked_until_reviewed(tmp_path: Path) -> None:
    payload = manifest_3d(REAL_MATRIX, AedtRelease(2025, 2), tmp_path)
    assert payload["succeeded"] is True
    assert payload["dcBias"]["strategy"] == "blocked"
    assert payload["dcBias"]["approximate"] is False


def test_synthetic_native_row_identifies_native(tmp_path: Path) -> None:
    matrix = tmp_path / "m.yml"
    matrix.write_text(SYNTHETIC, encoding="utf-8")
    payload = manifest_3d(matrix, AedtRelease(2025, 2), tmp_path)
    assert payload["dcBias"]["strategy"] == "native-include-dc-fields"
    assert payload["dcBias"]["approximate"] is False
    assert payload["dcBias"]["appliedCurrentsA"] is not None


def test_synthetic_2024_2_identifies_approximate_fallback(tmp_path: Path) -> None:
    matrix = tmp_path / "m.yml"
    matrix.write_text(SYNTHETIC, encoding="utf-8")
    payload = manifest_3d(matrix, AedtRelease(2024, 2), tmp_path)
    assert payload["dcBias"]["strategy"] == "magnetostatic-incremental-fallback"
    assert payload["dcBias"]["approximate"] is True


def test_two_d_is_always_blocked_and_marked_approximate_model(tmp_path: Path) -> None:
    matrix = tmp_path / "m.yml"
    matrix.write_text(SYNTHETIC, encoding="utf-8")
    capabilities = MatrixCapabilityRepository(matrix).snapshot_for(
        AedtRelease(2025, 2), AedtEdition.COMMERCIAL
    )
    project = replace(three_d_project(), dimension_mode=ModelDimension.TWO_D)  # type: ignore[type-var]
    outcome = export_maxwell2d(
        project, CATALOG, RecordingMaxwell2dExporter(), tmp_path,  # type: ignore[arg-type]
        capabilities=capabilities,
    )
    payload = json.loads(generation_manifest_json(outcome))
    assert payload["succeeded"] is True
    assert payload["dimension"] == "2d"
    assert payload["dcBias"]["strategy"] == "blocked"
    assert any("approximate" in note for note in payload["notes"])
```

Note: `test_synthetic_2024_2` builds a project with `target_release=AedtRelease(2024, 2)`; `AedtRelease` accepts 2024.2 (min). The fallback strategy is **identified only** (D4 veto): the manifest names it, `appliedCurrentsA` stays null, and no companion design is generated.

- [ ] **Step 2: Run** `.venv\Scripts\python.exe -m pytest tests/integration/test_release_matrix.py -q` — expected PASS. Investigate any failure as a Task 1–10 defect (do not weaken assertions).

- [ ] **Step 3: Run gates.** Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_release_matrix.py
git commit -m "test: release-matrix fixtures identify native vs approximate DC treatment"
```

---

### Task 11: 2D CLI, runner, AEDT integration test

**Files:**
- Create: `tools/generate_maxwell2d.py`
- Create: `tools/run_aedt_maxwell2d.ps1`
- Test: `tests/unit/tools/test_generate_maxwell2d.py`
- Test: `tests/integration/aedt/test_maxwell2d_export.py` (`@pytest.mark.aedt`)

**Interfaces:**
- `main(argv=None, *, exporter: Maxwell2dExporter | None = None) -> int` — args identical to the 3D CLI (`--project --output-directory --evidence --matrix [--graphical]`); loads the project, **forces nothing** — the project must already be `dimensionMode: "2d"`, except the CLI accepts `--force-2d` to `dataclasses.replace` the loaded project's dimension (the sample fixture is 3d; this keeps one fixture for both CLIs).

- [ ] **Step 1: Write the failing CLI test**

Create `tests/unit/tools/test_generate_maxwell2d.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from tests.fakes.maxwell2d_exporter import RecordingMaxwell2dExporter
from tools.generate_maxwell2d import main

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "tests" / "fixtures" / "sample_geometry_project.inductor.json"


def test_main_exports_sample_project_forced_2d(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence.json"
    exit_code = main(
        [
            "--project", str(FIXTURE),
            "--output-directory", str(tmp_path / "out"),
            "--evidence", str(evidence),
            "--force-2d",
        ],
        exporter=RecordingMaxwell2dExporter(),
    )
    assert exit_code == 0
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    assert payload["succeeded"] is True
    assert payload["dimension"] == "2d"
    assert payload["designName"] == "Inductor2D"
    assert payload["dcBias"]["strategy"] == "blocked"


def test_main_blocks_3d_project_without_force(tmp_path: Path) -> None:
    exit_code = main(
        [
            "--project", str(FIXTURE),
            "--output-directory", str(tmp_path / "out"),
            "--evidence", str(tmp_path / "evidence.json"),
        ],
        exporter=RecordingMaxwell2dExporter(),
    )
    assert exit_code == 1
```

- [ ] **Step 2: Run to verify failure.** Module not found.

- [ ] **Step 3: Implement**

Create `tools/generate_maxwell2d.py` (mirror `tools/generate_maxwell3d.py`; differences shown in full):

```python
"""Generate a ready-to-solve approximate Maxwell 2D project from an inductor project file."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from inductor_designer.adapters.catalog.sqlite_repository import SqliteCatalogRepository
from inductor_designer.adapters.compatibility.matrix_repository import (
    MatrixCapabilityRepository,
)
from inductor_designer.adapters.persistence.project_repository import ProjectRepository
from inductor_designer.adapters.persistence.schema_repository import SchemaRepository
from inductor_designer.adapters.pyaedt.maxwell2d import PyaedtMaxwell2dExporter
from inductor_designer.application.ports.maxwell2d_exporter import Maxwell2dExporter
from inductor_designer.application.services.maxwell_export import (
    MaxwellExportBlocked,
    export_maxwell2d,
    generation_manifest_json,
)
from inductor_designer.domain.aedt_target import ModelDimension
from tools.build_catalog import build

ROOT = Path(__file__).resolve().parents[1]


def main(
    argv: Sequence[str] | None = None, *, exporter: Maxwell2dExporter | None = None
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument(
        "--matrix", type=Path, default=ROOT / "compatibility" / "aedt-matrix.yml"
    )
    parser.add_argument("--graphical", action="store_true")
    parser.add_argument(
        "--force-2d",
        action="store_true",
        help="Override the project's dimension mode to 2d for this export.",
    )
    args = parser.parse_args(argv)

    args.output_directory.mkdir(parents=True, exist_ok=True)
    index = args.output_directory / "catalog.sqlite"
    build(ROOT / "catalog", ROOT / "schemas" / "catalog", index)
    catalog = SqliteCatalogRepository(index)
    repository = ProjectRepository(SchemaRepository(ROOT / "schemas"))
    project = repository.load(args.project)
    if args.force_2d:
        project = replace(project, dimension_mode=ModelDimension.TWO_D)
    capabilities = MatrixCapabilityRepository(args.matrix).snapshot_for(
        project.target_release, project.target_edition
    )

    try:
        outcome = export_maxwell2d(
            project,
            catalog,
            exporter if exporter is not None else PyaedtMaxwell2dExporter(),
            args.output_directory,
            capabilities=capabilities,
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

Create `tools/run_aedt_maxwell2d.ps1` — copy of `tools/run_aedt_maxwell3d.ps1` with `tools.generate_maxwell2d`, output dir `artifacts\maxwell2d\$Release-$Edition`, and `--force-2d` appended to `$arguments`.

Create `tests/integration/aedt/test_maxwell2d_export.py`:

```python
from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

import pytest

from inductor_designer.adapters.catalog.sqlite_repository import SqliteCatalogRepository
from inductor_designer.adapters.compatibility.matrix_repository import (
    MatrixCapabilityRepository,
)
from inductor_designer.adapters.persistence.project_repository import ProjectRepository
from inductor_designer.adapters.persistence.schema_repository import SchemaRepository
from inductor_designer.adapters.pyaedt.maxwell2d import PyaedtMaxwell2dExporter
from inductor_designer.application.services.maxwell_export import export_maxwell2d
from inductor_designer.domain.aedt_target import ModelDimension
from tools.build_catalog import build

ROOT = Path(__file__).resolve().parents[3]

pytestmark = pytest.mark.aedt


def test_generated_2d_project_is_ready_to_solve(tmp_path: Path) -> None:
    release = os.environ.get("INDUCTOR_AEDT_RELEASE")
    edition = os.environ.get("INDUCTOR_AEDT_EDITION")
    if not release or not edition:
        pytest.skip("Set INDUCTOR_AEDT_RELEASE and INDUCTOR_AEDT_EDITION to run AEDT tests")

    index = tmp_path / "catalog.sqlite"
    build(ROOT / "catalog", ROOT / "schemas" / "catalog", index)
    catalog = SqliteCatalogRepository(index)
    repository = ProjectRepository(SchemaRepository(ROOT / "schemas"))
    project = replace(
        repository.load(ROOT / "tests" / "fixtures" / "sample_geometry_project.inductor.json"),
        dimension_mode=ModelDimension.TWO_D,
    )
    capabilities = MatrixCapabilityRepository(
        ROOT / "compatibility" / "aedt-matrix.yml"
    ).snapshot_for(project.target_release, project.target_edition)

    outcome = export_maxwell2d(
        project, catalog, PyaedtMaxwell2dExporter(), tmp_path / "out",
        capabilities=capabilities,
    )

    failed = [stage for stage in outcome.result.stages if not stage.succeeded]
    assert outcome.result.succeeded(), failed
    assert outcome.result.project_path.exists()
```

- [ ] **Step 4: Run gates** (non-AEDT). Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/generate_maxwell2d.py tools/run_aedt_maxwell2d.ps1 tests/unit/tools/test_generate_maxwell2d.py tests/integration/aedt/test_maxwell2d_export.py
git commit -m "feat(tools): Maxwell 2D generation CLI, runner, and AEDT test"
```

---

### Task 12: Simulation summary in the UI

**Files:**
- Create: `src/inductor_designer/application/services/simulation_summary.py`
- Modify: `src/inductor_designer/ui/main.py` (`--matrix` arg, expose `simulationSummary` to QML)
- Modify: `src/inductor_designer/ui/qml/Main.qml` (render the lines under the `Simulation` label)
- Test: `tests/unit/application/test_simulation_summary.py`

**Interfaces:**
- `simulation_summary(project: InductorProject, capabilities: CapabilitySnapshot) -> tuple[str, ...]` — pure; lines: target row, DC-bias strategy (+" (approximate)"), reason, and the 2D-approximation sentence when `dimension_mode is TWO_D`.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/application/test_simulation_summary.py`:

```python
from __future__ import annotations

from dataclasses import replace

from inductor_designer.application.services.simulation_summary import simulation_summary
from inductor_designer.domain.aedt_target import ModelDimension
from tests.unit.application.test_maxwell_export import NATIVE_SNAPSHOT, SNAPSHOT
from tests.unit.domain.test_project import make_project


def test_blocked_summary_carries_reason() -> None:
    lines = simulation_summary(make_project(), SNAPSHOT)
    assert lines[0] == "Target: AEDT 2025.2 commercial (3d)"
    assert lines[1] == "DC bias: blocked"
    assert "Include DC Fields" in lines[2]


def test_native_summary() -> None:
    lines = simulation_summary(make_project(), NATIVE_SNAPSHOT)
    assert lines[1] == "DC bias: native-include-dc-fields"


def test_two_d_summary_adds_approximation_line() -> None:
    project = replace(make_project(), dimension_mode=ModelDimension.TWO_D)
    lines = simulation_summary(project, SNAPSHOT)
    assert lines[-1].startswith("2D model is a documented approximate")
```

- [ ] **Step 2: Run to verify failure.** Module not found.

- [ ] **Step 3: Implement**

Create `src/inductor_designer/application/services/simulation_summary.py`:

```python
from __future__ import annotations

from inductor_designer.domain.aedt_target import ModelDimension
from inductor_designer.domain.project import InductorProject
from inductor_designer.simulation.capabilities import (
    CapabilitySnapshot,
    select_dc_bias_strategy,
)


def simulation_summary(
    project: InductorProject, capabilities: CapabilitySnapshot
) -> tuple[str, ...]:
    """Human-readable simulation/compatibility lines for the Guided Studio UI."""
    decision = select_dc_bias_strategy(capabilities, project.dimension_mode)
    approximate = " (approximate)" if decision.approximate else ""
    lines = [
        f"Target: AEDT {project.target_release} {project.target_edition.value} "
        f"({project.dimension_mode.value})",
        f"DC bias: {decision.strategy.value}{approximate}",
        decision.reason,
    ]
    if project.dimension_mode is ModelDimension.TWO_D:
        lines.append(
            "2D model is a documented approximate XY cross-section equivalent."
        )
    return tuple(lines)
```

`ui/main.py`: add `--matrix` argument (default `Path("compatibility/aedt-matrix.yml")` resolved against the repo root the same way the existing `--catalog`/schema defaults are handled); after loading the project, compute

```python
capabilities = MatrixCapabilityRepository(matrix_path).snapshot_for(
    project.target_release, project.target_edition
)
summary = list(simulation_summary(project, capabilities))
```

and expose `summary` to QML alongside `previewEntries` via `setContextProperty("simulationSummary", summary)` (match however `previewEntries` is exposed in the current file).

`ui/qml/Main.qml`: under the existing `Simulation` label add

```qml
Repeater {
    model: simulationSummary
    delegate: Text {
        text: modelData
        wrapMode: Text.WordWrap
        font.pixelSize: 12
    }
}
```

wrapped in the same `Column`/layout the labels use (match surrounding structure).

- [ ] **Step 4: Run gates plus the ui-marked tests** (`-m pytest tests -q -m ui` — PySide6 is in the venv). Expected: PASS (existing UI smoke tests must still pass with the new context property; give `simulationSummary` a default empty list when no project is loaded).

- [ ] **Step 5: Commit**

```bash
git add src/inductor_designer/application/services/simulation_summary.py src/inductor_designer/ui/main.py src/inductor_designer/ui/qml/Main.qml tests/unit/application/test_simulation_summary.py
git commit -m "feat(ui): show DC-bias strategy and approximation notes in Guided Studio"
```

---

### Task 13: Docs, gates, exit-criterion handoff

**Files:**
- Create: `docs/development/dc-bias-compatibility.md`
- Create: `docs/development/maxwell2d-generation.md`
- Modify: `docs/development/ROADMAP.md` (M4 "Current state"), `docs/development/maxwell3d-generation.md` (DC-bias cross-reference), `README.md` (row), `docs/architecture/README.md` (adapters/compatibility line)

- [ ] **Step 1: Write `docs/development/dc-bias-compatibility.md`**

```markdown
# DC operating-point compatibility

`select_dc_bias_strategy` is the single decision point. Its inputs come from
`compatibility/aedt-matrix.yml` through `MatrixCapabilityRepository`; the
decision lands in the generation manifest (`dcBias` block) and the Guided
Studio Simulation summary.

| Situation | Strategy | Approximate |
|---|---|---|
| 2D project | blocked | – |
| Row unreviewed / missing | blocked | – |
| `includeDcFields3d: true` (2025 R1+) | native-include-dc-fields | no |
| `includeDcFields3d: false`, release 2024 R2 | magnetostatic-incremental-fallback | yes |
| otherwise | blocked | – |

## Reviewing Include DC Fields on 2025 R2 (required to unlock native)

1. Open the M0 probe project (or any Eddy Current design) in AEDT 2025 R2.
2. Confirm the solve setup exposes the "Include DC fields" option and that a
   winding accepts a DC value alongside the AC excitation.
3. Set `includeDcFields3d: true` on the 2025.2/commercial row of
   `compatibility/aedt-matrix.yml`, update `evidenceReviewedAt`/`evidenceReviewedBy`.
4. Re-run `tools/run_aedt_maxwell3d.ps1` with a project carrying nonzero
   `dcCurrentA`; verify the manifest reports `native-include-dc-fields`, the
   setup flag and per-winding DC values exist in AEDT, and validation passes.
   The adapter's `IncludeDcFields`/`DCValue` prop names are best-effort — fix
   adapter + fakes to match the installed pyaedt if AEDT rejects them.

## 2024 R2 fallback

Deferred (decision D4, 2026-07-16). The strategy is identified and recorded
in the manifest, but nothing is generated for it: no 2024 R2 installation
exists, and the incremental linearization is physically a no-op until
Milestone 5 delivers nonlinear B-H material data (today's material model is
linear μr). Generation work returns when a 2024 R2 installation is available.
```

- [ ] **Step 2: Write `docs/development/maxwell2d-generation.md`** — mirror `maxwell3d-generation.md`: prerequisites, runner command (`.\tools\run_aedt_maxwell2d.ps1 -Release 2025.2 -Edition commercial -Graphical`), manifest review, what to check in AEDT (annular core, 2·turns conductor circles, coils with go/return polarity, winding groups, model depth = core height, region, mesh ops, Setup1, Matrix1, reports, validation), scope notes (documented approximate XY equivalent per design spec §6/§163; DC bias blocked in 2D; linear draft material).

- [ ] **Step 3: Update ROADMAP** M4 section with a `### Current state` mirroring M0–M3 style: deliverables list (capability matrix loader, DC-bias wiring with native applied and fallback/blocked identified-only, Maxwell 2D plan/port/adapter/CLI, manifest v2, UI summary, release-matrix exit test), exit-criterion status (proven by `tests/integration/test_release_matrix.py` + the 2D AEDT run), and the two live-verification items pending Fabio: 2025.2 Include-DC-Fields review (flips native on) and 2024 R2 row (stays out-of-scope, no installation). Mark **accepted only after** Fabio's run.

- [ ] **Step 4: Run the full gate set**

- `.venv\Scripts\python.exe -m pytest tests -q -m "not aedt and not ui" --cov`
- `.venv\Scripts\python.exe -m pytest tests -q -m ui`
- `.venv\Scripts\python.exe -m ruff check .`
- `.venv\Scripts\python.exe -m mypy`
- `.venv\Scripts\python.exe tools/check_architecture.py`

Expected: all PASS, coverage ≥ 80 %.

- [ ] **Step 5: Commit**

```bash
git add docs/development/dc-bias-compatibility.md docs/development/maxwell2d-generation.md docs/development/ROADMAP.md docs/development/maxwell3d-generation.md docs/architecture/README.md README.md
git commit -m "docs: Maxwell 2D generation and DC-bias compatibility procedures"
```

- [ ] **Step 6: Human handoff (exit criterion)**

Hand to Fabio Posser on the licensed machine:

1. `.\tools\run_aedt_maxwell2d.ps1 -Release 2025.2 -Edition commercial -Graphical` — open the generated 2D project; check core annulus, conductor pairs, polarities, model depth, setup, matrix, reports; run design validation.
2. Run the `aedt`-marked 2D integration test (env vars per the doc).
3. Review Include DC Fields on 2025.2 per `dc-bias-compatibility.md`; flip the matrix row; re-run the 3D runner with a DC project and confirm native application in AEDT (fix `IncludeDcFields`/`DCValue` prop names in adapter + fakes if needed).
4. Confirm the Guided Studio Simulation summary shows the expected strategy lines for a 3d and a 2d project.
5. Accept Milestone 4 in the ROADMAP.

---

## Self-review notes

- ROADMAP M4 bullets → tasks: 2D equivalent model (T5/T6/T7/T9/T11), native Include DC Fields (T1/T3/T4), 2024 R2 fallback identified-only per D4 veto (T3 notes + T10), manifest+UI visibility (T8/T12), exit criterion (T10 + T13 handoff).
- Cross-task name checks: `CapabilityRepository`/`MatrixCapabilityRepository` (T1→T8/T11/T12), `dc_bias_notes` + `Maxwell3dDesignPlan.dc_bias` (T3→T4/T6/T8), `MaxwellExportResult` alias (T2→T7/T9), `STAGE_NAMES_2D` (T7→T9), `build2d` test helper (T6→T7/T9), `SNAPSHOT`/`NATIVE_SNAPSHOT` (T8→T12), `three_d_project` (existing→T10).
- Verify-at-AEDT risks (arbiter = T11 aedt test + T13 step 3): `IncludeDcFields` setup prop, winding `DCValue` prop, 2D `create_circle(origin=...)`, 4-arg `create_air_region`, `model_depth` unit string, `MatrixACMagnetic` on 2D.
- Breaking changes contained: `export_maxwell3d` capabilities kwarg (all call sites updated in T9), manifest schemaVersion 2 (evidence consumers = tests + humans), M3 note text change (T3 updates its test).
