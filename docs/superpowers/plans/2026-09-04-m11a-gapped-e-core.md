# M11a Gapped E Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A gapped manual E core can be designed, previewed and estimated, without touching the toroid implementation or needing AEDT.

**Architecture:** The physics first, as pure functions with no Qt and no seam (tasks 1-3), so the reluctance network is pinned to numbers before anything structural moves. Then the domain and schema (task 4), then the mechanical split of the toroid into a family component (task 5), the E-core geometry against that seam (task 6), the family-agnostic cut plane (task 7), and the manual-entry UI (task 8).

**Tech Stack:** Python 3.13, PySide6 (QtQml/QtQuick3D), jsonschema, pytest + pytest-xdist, ruff, mypy strict, `tools.check_architecture`.

## Global Constraints

- English everywhere. `domain`, `geometry`, `materials`, `simulation` import no PyAEDT, Qt, SQLite or OS APIs; `application` imports no `inductor_designer.adapters`.
- **Never change a physical assumption, schema, catalog value, unit or source reference silently.** Every formula in this plan is the spec's; a deviation needs the spec changed first.
- Tests before the implementation they cover; every existing toroid test must keep passing untouched.
- Per task: `.venv/Scripts/python.exe -m pytest -q <that task's tests>`. Final gate: `ruff check .`, `mypy src tools`, `python -m tools.check_architecture`, `pytest -q -n 8 -m "not aedt and not femm"`.
- Never run `aedt` or `femm` marked tests; never start an AEDT session.
- Spec: `docs/superpowers/specs/2026-09-04-m11a-gapped-e-core-design.md`.

---

## File Structure

- Create `src/inductor_designer/geometry/ecore/__init__.py`, `body.py` (`FinishedECore`, gap validation), `reluctance.py` (the network), `packing.py`, `turn_path.py`, `mesh.py`, `profile.py`.
- Create `src/inductor_designer/geometry/toroid/` and move the existing toroid modules into it unchanged (task 5).
- Modify `src/inductor_designer/simulation/preliminary_contracts.py` — `CoreMagneticProperties.gap_length_m`.
- Modify `src/inductor_designer/simulation/magnetic_estimate.py` — flux from the network when a gap is present.
- Modify `src/inductor_designer/domain/project.py` — `ManualECoreSelection`, the placement union.
- Modify `src/inductor_designer/domain/winding.py` — `WindingDefinition.placement`.
- Create `schemas/project/v6.schema.json`; delete `v5.schema.json`.
- Modify `src/inductor_designer/adapters/persistence/{project_repository,schema_repository}.py`.
- Modify `src/inductor_designer/application/services/{geometry_model,preliminary_inputs}.py`.
- Modify `src/inductor_designer/ui/cut_plane_view.py`, `src/inductor_designer/ui/qml/CutPlaneView.qml`, `src/inductor_designer/ui/qml/CoreMaterialPanel.qml`.

---

### Task 1: The E-core body and its gaps

**Files:** create `src/inductor_designer/geometry/ecore/body.py`; test `tests/unit/geometry/test_ecore_body.py`.

**Produces:** `FinishedECore(centre_leg_width_m, depth_m, window_width_m, window_height_m, outer_leg_width_m, yoke_thickness_m, gaps, gap_spacings_m, outer_legs_gapped)`, with `overall_width_m` / `overall_height_m` / `centre_leg_length_m` properties, raising `CoreGeometryError` (imported from `geometry.core_solid`, the existing type) on anything out of range.

- [ ] **Step 1: Write the failing tests** — the six dimensions and the derived two; a non-finite or non-positive dimension refused; a negative gap refused; gaps plus spacings longer than `2 * window_height_m` refused, naming the total; zero gaps legal; `outer_legs_gapped` defaulting to False.
- [ ] **Step 2: Run them, expect `ModuleNotFoundError`.**
- [ ] **Step 3: Implement.** A frozen slotted dataclass with `__post_init__` validation, matching `FinishedCore`'s existing refusal style and messages.
- [ ] **Step 4: Tests pass. Step 5: Commit** `feat(geometry): the E-core body, with its gap stack`.

---

### Task 2: The reluctance network

**Files:** create `src/inductor_designer/geometry/ecore/reluctance.py`; test `tests/unit/geometry/test_ecore_reluctance.py`.

**Produces:** `referred_lengths(core: FinishedECore) -> ReferredLengths` with fields `iron_m`, `gap_m`, `effective_area_m2`, `iron_volume_m3` — the exact separation from the spec, referred to `A_c = F*C`.

Formulas, verbatim from the spec (a deviation needs the spec changed):

```
A_c = F*C ;  A_y = H*C ;  A_o = G*C ;  yoke_run = E + F/2 + G/2
centre_iron = 2*D - g_total
outer_iron  = 2*D - g_outer_total          # g_outer_total = g_total when
                                           # outer_legs_gapped else 0
iron_m = A_c * ( centre_iron/A_c + 2*yoke_run/A_y + outer_iron/(2*A_o) )
gap_m  = A_c * ( g_total/A_c + g_outer_total/(2*A_o) )
iron_volume_m3 = A_c*centre_iron + 2*(A*H*C) + 2*(G*C*outer_iron)
```

- [ ] **Step 1: Write the failing tests**, the load-bearing ones first:
  - one fully specified geometry against a hand-computed `iron_m` and `gap_m` (compute both by hand in the test body as literals, with the arithmetic shown in a comment, so the test pins numbers rather than restating the implementation);
  - `gap_m` rises monotonically with total gap, and is `0.0` with no gaps;
  - **N gaps totalling L equal one gap of L** — the fringing assumption, so a future correction fails here deliberately;
  - `outer_legs_gapped=True` adds exactly `g_total*A_c/(2*A_o)` to `gap_m` and removes the same iron from `outer_iron`;
  - an ungapped pair's `iron_m` equals the plain centreline sum, so the referred form is not quietly rescaling anything.
- [ ] **Step 2: Confirm failure. Step 3: Implement. Step 4: Tests pass.**
- [ ] **Step 5: Commit** `feat(geometry): the E-core reluctance network, iron and gap separated exactly`.

---

### Task 3: One new term in the estimate

**Files:** modify `src/inductor_designer/simulation/preliminary_contracts.py`, `src/inductor_designer/simulation/magnetic_estimate.py`; test `tests/unit/simulation/test_magnetic_estimate.py` (append).

**Produces:** `CoreMagneticProperties.gap_length_m: float = 0.0`; `field_strengths`/flux computing `phi = N*I/R_total` when `gap_length_m > 0`.

- [ ] **Step 1: Write the failing tests**
  - every existing toroid estimate is numerically unchanged with the default — assert an exact equality against a value computed before the change, because the separation is exact and "close enough" would hide a rescale;
  - with a gap present, the iron field strength is **lower** than `NI/l_iron` would give, and flux density matches `phi/A_c` from the network;
  - a gap with a non-finite or negative referred length is refused with a diagnostic, like the existing non-finite path-length refusal.
- [ ] **Step 2: Confirm failure. Step 3: Implement** — one field with a default, and the flux branch. Do not touch the ungapped arithmetic. **Step 4: Tests pass.**
- [ ] **Step 5: Commit** `feat(simulation): flux from the reluctance network when the core is gapped`.

---

### Task 4: The domain and schema v6

**Files:** modify `src/inductor_designer/domain/project.py`, `domain/winding.py`, `domain/validation.py`, `adapters/persistence/record_serde.py`, `adapters/persistence/project_repository.py`, `adapters/persistence/schema_repository.py`; create `schemas/project/v6.schema.json`, delete `v5.schema.json`; update `tests/fixtures/*.inductor.json` and every affected test fixture.

**Produces:** `ManualECoreSelection` in the `CoreSelection` union; `ToroidPlacement` / `LegPlacement` and `WindingDefinition.placement`; `LATEST_PROJECT_SCHEMA_VERSION = 6`.

- [ ] **Step 1: Write the failing tests** — a v5 document refused naming 6; an E-core project round-tripping through save/load; `LegPlacement` refusing a non-positive span; a toroid project round-tripping with its placement unchanged in meaning.
- [ ] **Step 2: Confirm failure. Step 3: Implement**, including the mechanical fixture updates. **Step 4: The whole suite, not just these tests** — this task moves a field every screen reads.
- [ ] **Step 5: Commit** `feat(domain): schema v6, with winding placement per core family`.

---

### Task 5: Split the toroid into a family component

**Files:** create `src/inductor_designer/geometry/toroid/` and move `core_solid.py`, `core_profile.py`, `packing.py`, `turn_path.py`, `planar.py`, `tessellation.py`, `collisions.py`, `symmetry.py`, `terminals.py` into it; update every import.

**Produces:** the same public names, at `inductor_designer.geometry.toroid.*`. No behaviour change whatsoever.

- [ ] **Step 1:** Move with `git mv`, so history follows the files.
- [ ] **Step 2:** Update imports across `src/` and `tests/`.
- [ ] **Step 3:** Run the **entire** suite. The acceptance criterion is that no test changed except its import lines. **Step 4: Commit** `refactor(geometry): move the toroid under its own family package`.

---

### Task 6: E-core geometry against the seam

**Files:** create `geometry/ecore/{packing,turn_path,mesh,profile}.py`; modify `application/services/geometry_model.py`, `application/services/preliminary_inputs.py`; tests `tests/unit/geometry/test_ecore_packing.py`, `tests/unit/application/test_geometry_model_ecore.py`.

**Produces:** `pack_leg_winding(core, spec) -> PackedWinding` (the existing `PackedWinding` shape, reused); an E-core mesh builder; `build_geometry_model` dispatching on the core selection type; `core_magnetic_properties` returning the E core's referred lengths and `gap_length_m`.

- [ ] **Step 1: Write the failing tests** — capacity from `floor(span/(d+spacing))` and `floor(window_width/(d+spacing))`; the refusal when one turn does not fit, in the toroid's message shape; two windings taking different spans without colliding; `build_geometry_model` producing a model for an E-core project; `core_magnetic_properties` on a gapped E core returning `al_value_nh=None` and the gap note.
- [ ] **Step 2: Confirm failure. Step 3: Implement. Step 4: Full suite. Step 5: Commit** `feat(geometry): wind and place turns on an E core's centre leg`.

---

### Task 7: A family-agnostic cut plane

**Files:** modify `src/inductor_designer/ui/cut_plane_view.py`, `src/inductor_designer/ui/qml/CutPlaneView.qml`; tests `tests/ui/test_cut_plane_qml.py`, `tests/ui/test_cut_plane_ecore.py`.

**Produces:** `CutPlaneDrawing.outline: tuple[CutPlaneShape, ...]` replacing `r_inner_mm`/`r_outer_mm`, where `CutPlaneShape` is `CutPlaneCircleOutline | CutPlaneRect`; the QML canvas drawing both.

- [ ] **Step 1: Write the failing tests** — a toroid drawing emitting exactly two circle outlines with its old radii; an E-core drawing emitting the legs and yokes as rectangles and one break per gap; the QML rendering both without a QML error (asserted on the drawing the QML receives and on a rendered grab, as `tests/ui/test_cut_plane_qml.py` already does).
- [ ] **Step 2: Confirm failure. Step 3: Implement. Step 4: Full UI suite. Step 5: Commit** `feat(ui): draw the cut plane from an outline, not a pair of radii`.

---

### Task 8: Manual E-core entry

**Files:** modify `src/inductor_designer/ui/core_material_controller.py`, `src/inductor_designer/ui/qml/CoreMaterialPanel.qml`, `src/inductor_designer/application/services/core_material_selection.py`; tests `tests/ui/test_core_material_controller.py`, `tests/ui/test_panel_layout_containment.py`.

**Produces:** `applyManualECore(...)` on the controller and the fields for it, alongside the existing manual toroid; the panel's layout still containing itself at the narrowest supported window.

- [ ] **Step 1: Write the failing tests** — applying six dimensions and a gap list selects a manual E core into the project; a refused dimension reports and leaves the previous selection; the gap list parses from the text the field carries; the containment test at 1000 px (which caught the last panel addition, so it will catch this one).
- [ ] **Step 2: Confirm failure. Step 3: Implement**, laying controls out with `Flow` as the core-import buttons already are. **Step 4: Full suite plus the gate. Step 5: Commit** `feat(ui): enter a manual gapped E core`.

---

### Task 9: Documentation and the walk

- [ ] Release notes gain the E-core family and the fringing statement; `docs/development/ROADMAP.md` records 11a as implemented and 11b as the live half.
- [ ] Run the full gate, then walk it in the real application: launch with no project, enter a gapped E core, add a winding, see the cut plane and the preliminary estimate, save.
- [ ] Commit.

---

## Self-Review

- Spec coverage: body and gaps (1), network (2), estimate (3), domain and schema (4), seam (5), E geometry and dispatch (6), cut plane (7), UI (8), docs and walk (9). The spec's ten tests map onto tasks 1-8; its four out-of-scope items appear in no task.
- Names consistent across tasks: `FinishedECore`, `referred_lengths`, `ReferredLengths`, `gap_length_m`, `ManualECoreSelection`, `ToroidPlacement`, `LegPlacement`, `pack_leg_winding`, `CutPlaneShape`, `applyManualECore`.
- Ordering rationale: the physics is pinned to numbers (1-3) before the seam moves (5), so a numeric regression can never be blamed on the move.
