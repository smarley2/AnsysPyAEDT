# M7c Guided Studio Flow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the five-screen Guided Studio flow — `Core & Material`,
`Windings`, `Preliminary`, `Simulation`, `Review` — with bidirectional
core/material filtering, a separate Material Studio window, native numeric
validators and enumerated selectors on every winding and operating-point input,
live read-only preliminary results in engineering units, and post-generation
`Open generated file` / `Open run folder` actions bound to the M7b ports.

**Architecture:** One session object (`ui/project_session.py`) owns the single
in-memory project, its dirty flag, and its document path; every controller reads
and writes the project through it, so no two controllers can hold divergent
copies. Two new solver-independent application services carry the logic that
must stay testable without Qt: `preliminary_inputs.py` assembles the M7a
`PreliminaryRequest` (including a computed magnetic path for Manual cores) and
`core_material_selection.py` performs the bidirectional filtering and the
never-substituting clear. Five thin Qt controllers convert immutable results
into QML rows; QML holds no physics and no unit conversion. Material Studio
moves out of the step rail into its own `ApplicationWindow`.

**Tech Stack:** Python 3.10–3.13, frozen dataclasses and enums, stdlib only in
the inner layers, PySide6 6.x (QML, `QtQuick.Controls`, `IntValidator` /
`DoubleValidator`), pytest with `QT_QPA_PLATFORM=offscreen`, Ruff, strict mypy.

## Global Constraints

- Owner: one executor per working tree. Do not run two agents in the same tree.
- Entry condition: M7b is accepted; `main` starts at `4881747`.
- Branch: `m7c/guided-studio-flow`. Squash-merge to `main` after the final
  whole-branch review.
- This plan implements sections 4.1–4.4, 9, 10, and 11 of
  `docs/superpowers/specs/2026-07-26-preliminary-calculations-and-guided-flow-design.md`
  and the two UI-facing rules of
  [ADR 0007](../../adr/0007-project-local-run-artifacts-and-solver-visibility.md)
  (`Show solver window`, `Open generated file` / `Open run folder`). Do not
  reopen their approved product or physics decisions.
- Scope is the Guided Studio flow. The M7a estimator physics is not
  re-derived: only its `PreliminaryRequest` input shape changes, in Task 1, and
  only to carry a magnetic path that is not a catalog record. The M7b run
  services (`start_project_run`, `run_directory`, `solver_visibility`,
  `PathOpener`) are consumed as they are, not modified. Solving and `results/`
  population remain M8.
- Screen order is exactly `Core & Material`, `Windings`, `Preliminary`,
  `Simulation`, `Review`. Material Studio is not a step.
- Plan-level decisions taken with Fabio Posser on 2026-07-30:
  - **Layout:** `Preliminary` (index 2) and `Review` (index 4) take the full
    workspace width; the geometry canvas is hidden on exactly those two screens.
    The other three keep the canvas plus the right-hand context panel.
  - **Run gate:** `Generate` is disabled while the project has unsaved edits or
    has no document path, with a visible reason. A run is never started from
    state that is not on disk, and generation never saves the project itself.
  - **Units:** preliminary numbers are displayed in engineering units (`mT`,
    `A/mm²`, `mΩ`, `mm`, `mm²`, `W`). The estimator keeps SI; every conversion
    happens in one pure module, `ui/preliminary_rows.py`.
  - **Windings:** adding and removing windings is in scope. A new winding
    allocates a winding id and its matching `WindingOperatingPoint` together;
    the last winding cannot be removed.
  - **Manual core magnetic path:** a Manual core's path length and volume are
    computed from its entered dimensions as
    `l_e = pi * (outer_diameter + inner_diameter) / 2`,
    `A_e = ((outer_diameter - inner_diameter) / 2) * height`,
    `V_e = A_e * l_e`, always reported with a visible assumption note.
    Manufacturer effective values are not invented.
- Physical constants stay exactly where M7a put them
  (`simulation/winding_estimate.py`, `simulation/core_loss_estimate.py`). Do not
  copy or re-derive them in UI code.
- Diagnostic codes are the existing `DiagnosticCode` strings. Never invent a
  user-facing reason in QML: every unavailable or invalid cell renders the code
  and the message the estimator produced.
- QML contains no physical formula, no unit conversion, and no diagnostic text
  of its own.
- Every new numeric QML editor uses a native validator (`IntValidator` for turn
  counts, `DoubleValidator` otherwise) AND still routes its committed value
  through the controller, which is authoritative for range, positivity,
  finiteness, and collision rules. A rejected commit restores the last valid
  value from the controller.
- Enumerated values (conductor name, conductor mode, winding direction, current
  direction, backend, run mode, mesh intent) use `ComboBox`. Only `label` and
  `terminal_intent` accept free text.
- Every new interactive QML item carries a unique `objectName` and an
  `Accessible.name`, and every new focusable item sets `activeFocusOnTab: true`.
- Python 3.10 is the floor: `datetime.timezone.utc`, never `datetime.UTC`; no
  `match` statement in new code paths that must run on 3.10 is required but
  `X | Y` annotations are fine because every module uses
  `from __future__ import annotations`.
- The quality CI job runs on `ubuntu-latest`: no test may call a Windows-only
  API, and Windows-only code stays behind `if sys.platform == "win32":`.
- UI tests are marked `pytest.mark.ui`, set `QT_QPA_PLATFORM=offscreen` and
  `QSG_RHI_BACKEND=software` before importing PySide6, and use
  `pytest.importorskip("PySide6")`.
- English for code, tests, docs, diagnostics, and commits.
- Run these gates before every commit:
  `.venv/Scripts/python.exe -m pytest tests -q -m "not aedt and not femm"`,
  `.venv/Scripts/python.exe -m pytest tests -q -m "ui"`,
  `.venv/Scripts/python.exe -m ruff check .`,
  `.venv/Scripts/python.exe -m mypy src tools`,
  `.venv/Scripts/python.exe tools/check_architecture.py`.
  All five must pass. The dev interpreter is `.venv\Scripts\python.exe`; the
  PATH `python` has no dev tools.
- Baseline to beat, measured on `4881747`: 940 passed / 7 deselected for the
  non-solver suite, 37 passed for `-m ui`. Re-measure yourself; do not trust a
  count reported by another agent.

## What already exists (do not rewrite it)

| Thing | Where | Use it for |
| --- | --- | --- |
| `estimate_preliminary`, `PreliminaryRequest`, `PreliminaryResult` | `simulation/preliminary.py` | every preliminary number |
| `PreliminaryValue`, `ResultState`, `DiagnosticCode` | `simulation/preliminary_contracts.py` | states, codes, messages |
| `build_geometry_model`, `GeometryModel`, `GeometryModelError` | `application/services/geometry_model.py` | packings, preview, edit validation |
| `validate_project`, `ValidationCategory` | `domain/validation.py` | Review findings |
| `pin_material_revision`, `MaterialSelectionError` | `application/services/material_selection.py` | pinning an exact revision |
| `select_core` | `application/services/catalog_revisions.py` | catalog core selection |
| `list_material_revision_summaries`, `MaterialRevisionSummary` | `application/services/material_library.py` | revision listing |
| `start_project_run`, `ProjectRunFailed` | `application/services/project_run.py` | the only run entry point |
| `visible_window_support`, `VisibilitySupport` | `application/services/solver_visibility.py` | `Show solver window` support + reason |
| `PathOpener` protocol / `DesktopPathOpener` | `application/ports/path_opener.py`, `adapters/system/path_opener.py` | Open file / Open folder |
| `GenerationController` (`busy`, `lines`, `last_run_directory`, `last_generated_file`, `failed_manifest`) | `ui/generation_controller.py` | threaded run + its evidence |
| `run_generation`, `GenerationBackend`, `GenerationResult` | `ui/generation_lines.py` | backend labels and display lines |
| `simulation_summary` | `application/services/simulation_summary.py` | Review operating-point lines |
| `MaterialStudioController`, `MaterialStudioPage.qml` | `ui/` | Material Studio, moved to its own window |
| `make_project`, `make_winding`, `make_operating_point` | `tests/unit/domain/test_project.py` | project fixtures |
| `CATALOG`, `FakeCatalog`, `make_conductor` | `tests/unit/application/test_geometry_model.py` | catalog fake |
| `make_core` | `tests/unit/domain/test_catalog_records.py` | core record fixture |
| `InMemoryMaterialRepository` | `tests/fakes/material_repository.py` | material repository fake |

`tools/check_architecture.py` forbids `PySide6`, `ansys`, `femm`, `mcp`,
`pyaedt`, `sqlite3` and `inductor_designer.adapters` inside `application`, and
forbids `pathlib`/`os` as well inside `domain`, `geometry`, `materials`, and
`simulation`. Keep it passing: the new services live in `application`, the new
controllers live in `ui`.

---

### Task 1: A magnetic path the estimator can take from a Manual core

The M7a estimator takes a `CoreRecord`, which only a catalog core has. A Manual
core has dimensions and no record, and fabricating a `CoreRecord` would invent
manufacturer provenance. Replace the input with the two magnetic properties the
estimator actually reads.

**Files:**
- Modify: `src/inductor_designer/simulation/preliminary_contracts.py`
- Modify: `src/inductor_designer/simulation/preliminary.py:39-50`, `:114-139`, `:268-311`
- Modify: `tests/unit/simulation/conftest.py:51`, `:132`
- Modify: `tests/unit/simulation/test_preliminary.py:25`, `:45`, `:81`
- Modify: `tests/integration/test_preliminary_estimator.py:57-60`, `:120-123`
- Test: `tests/unit/simulation/test_preliminary_contracts.py` (exists; extend)

**Interfaces:**
- Consumes: nothing new.
- Produces: `CoreMagneticProperties` (frozen, slots; fields `path_length_m: float`,
  `volume_m3: float`, `notes: tuple[str, ...] = ()`) in
  `simulation/preliminary_contracts.py`, and `PreliminaryRequest.core:
  CoreMagneticProperties | None` replacing `PreliminaryRequest.core_record`.
  `CorePreliminary` B values carry `densities.notes + request.core.notes`.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/simulation/test_preliminary_contracts.py`:

```python
def test_core_magnetic_properties_allow_every_number_including_non_finite() -> None:
    """Bad geometry is a diagnosed condition, never a constructor error.

    `flux_density.non_positive_path_length`, `flux_density.core_path_not_finite`,
    `core_loss.non_positive_volume`, and `core_loss.non_finite_volume` all report
    these, so raising here would replace a user-facing diagnostic with a crash
    inside the Preliminary controller's constructor.
    """
    zero = CoreMagneticProperties(path_length_m=0.0, volume_m3=0.0)
    overflowed = CoreMagneticProperties(
        path_length_m=float("inf"), volume_m3=float("inf")
    )

    assert zero.path_length_m == 0.0
    assert zero.notes == ()
    assert overflowed.volume_m3 == float("inf")
```

Add `CoreMagneticProperties` to that file's import block.

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/simulation/test_preliminary_contracts.py -q`
Expected: FAIL with `ImportError: cannot import name 'CoreMagneticProperties'`.

- [ ] **Step 3: Add the dataclass**

In `src/inductor_designer/simulation/preliminary_contracts.py`, after the
`DiagnosticCode` class:

```python
@dataclass(frozen=True, slots=True)
class CoreMagneticProperties:
    """The two core properties the estimator reads, and how they were obtained.

    A catalog core supplies the manufacturer's effective values. A Manual core
    has no record, so the caller computes them from the entered dimensions and
    says so in `notes`. Keeping this separate from `CoreRecord` means no caller
    ever has to fabricate manufacturer provenance to get an estimate.
    """

    path_length_m: float
    volume_m3: float
    notes: tuple[str, ...] = field(default_factory=tuple)
```

No validation at all. A non-positive path length is already a reported
condition (`flux_density.non_positive_path_length`), and a non-finite one has to
be too: dimensions that are each finite can still overflow when multiplied
(`A_e * l_e`), and a crash inside the Preliminary controller's constructor is
not an acceptable answer to a number the user typed. Both are diagnosed by the
estimator, in Task 1 Step 5 below.

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/simulation/test_preliminary_contracts.py -q`
Expected: PASS.

- [ ] **Step 5: Diagnose bad core geometry instead of crashing on it**

Add two codes to `DiagnosticCode` in
`src/inductor_designer/simulation/preliminary_contracts.py`, beside their
non-positive siblings:

```python
    FLUX_DENSITY_CORE_PATH_NOT_FINITE = "flux_density.core_path_not_finite"
```

```python
    CORE_LOSS_NON_FINITE_VOLUME = "core_loss.non_finite_volume"
```

Guard them where the existing non-positive guards live. In
`src/inductor_designer/simulation/magnetic_estimate.py::field_strengths`, before
the `not path_length_m > 0.0` check:

```python
    if not isfinite(path_length_m):
        return unavailable(
            DiagnosticCode.FLUX_DENSITY_CORE_PATH_NOT_FINITE,
            "Core effective magnetic path length is not a finite number, so "
            "the core dimensions are out of range.",
        )
```

and in `src/inductor_designer/simulation/core_loss_estimate.py::core_loss_w`,
before the `not core_volume_m3 > 0.0` check:

```python
    if not isfinite(core_volume_m3):
        return unavailable(
            DiagnosticCode.CORE_LOSS_NON_FINITE_VOLUME,
            "Core volume is not a finite number, so the core dimensions are "
            "out of range.",
        )
```

Import `isfinite` from `math` in both modules if it is not already there. Note
that `not path_length_m > 0.0` is already NaN-safe, so these guards exist for
the `inf` case that an overflowing `A_e * l_e` produces from finite dimensions.

Guard the computed OUTPUTS too, not just the inputs: a denormal-but-finite path
length divides a normal numerator into `inf`, and `estimated()` then refuses the
non-finite result. In `field_strengths`, after the four `h_*` values exist and
before `FieldStrengths(...)` is returned:

```python
    if not all(isfinite(value) for value in (h_ac_peak, h_dc)):
        return unavailable(
            DiagnosticCode.FLUX_DENSITY_CORE_PATH_NOT_FINITE,
            "Core effective magnetic path length is too small for the winding "
            "ampere-turns, so the field strength overflows; the core dimensions "
            "are out of range.",
        )
```

`h_min` and `h_max` derive from those two, so they cannot be non-finite once
these are checked.

- [ ] **Step 6: Switch the estimator to the new input**

In `src/inductor_designer/simulation/preliminary.py`:

- Replace the `CoreRecord` import with `CoreMagneticProperties` from
  `inductor_designer.simulation.preliminary_contracts` (keep the
  `ConductorRecord` import).
- In `PreliminaryRequest`, replace the field:

```python
    core: CoreMagneticProperties | None
```

- Change `_core_estimates` to take the properties and merge their notes:

```python
def _core_estimates(
    request: PreliminaryRequest,
    fields: FieldStrengths,
    densities: FluxDensities,
    core: CoreMagneticProperties,
) -> CorePreliminary:
    material = request.project.design.core_material
    if material is None:  # guarded by the caller
        raise AssertionError("_core_estimates requires a selected material")
    operating_point = request.project.operating_point
    loss = core_loss_w(
        material,
        b_ac_peak_t=densities.b_ac_peak_t,
        frequency_hz=operating_point.frequency_hz,
        core_temperature_c=operating_point.core_temperature_c,
        h_dc_a_per_m=fields.h_dc_a_per_m,
        core_volume_m3=core.volume_m3,
    )
    # The core's own notes describe how its path length and volume were
    # obtained, which is an assumption behind every B value below.
    notes = densities.notes + core.notes
    return CorePreliminary(
        b_dc=estimated(densities.b_dc_t, notes),
        b_min=estimated(densities.b_min_t, notes),
        b_max=estimated(densities.b_max_t, notes),
        b_ac_peak=estimated(densities.b_ac_peak_t, notes),
        b_peak_magnitude=estimated(densities.b_peak_magnitude_t, notes),
        core_loss=loss,
    )
```

- In `estimate_preliminary`, replace the three `request.core_record`
  references with `request.core`:

```python
    if request.core is None:
```

```python
        fields = field_strengths(
            request.project.operating_point,
            turns_by_winding,
            request.core.path_length_m,
        )
```

```python
                core = _core_estimates(request, fields, densities, request.core)
```

- [ ] **Step 7: Migrate the three existing test callers**

In `tests/unit/simulation/conftest.py`, keep the `CoreRecord` fixture (other
tests use it) and pass its magnetic properties instead:

```python
    return PreliminaryRequest(
        project=project,
        core=CoreMagneticProperties(
            path_length_m=core_record.path_length_m,
            volume_m3=core_record.volume_m3,
        ),
        conductors_by_winding=...,
        packings_by_winding=...,
    )
```

In `tests/unit/simulation/test_preliminary.py`, replace all three
`replace(sample_request, core_record=None)` with
`replace(sample_request, core=None)`.

In `tests/integration/test_preliminary_estimator.py`, keep the catalog lookup
and pass:

```python
        core=CoreMagneticProperties(
            path_length_m=core_record.path_length_m,
            volume_m3=core_record.volume_m3,
        ),
```

- [ ] **Step 8: Run the full non-solver suite and the gates**

Run: `.venv/Scripts/python.exe -m pytest tests -q -m "not aedt and not femm"`
Expected: PASS, same count as the 940 baseline.
Run: `.venv/Scripts/python.exe -m ruff check .`, then
`.venv/Scripts/python.exe -m mypy src tools`, then
`.venv/Scripts/python.exe tools/check_architecture.py`
Expected: clean.

- [ ] **Step 9: Commit**

```bash
git add src/inductor_designer/simulation tests/unit/simulation tests/integration/test_preliminary_estimator.py
git commit -m "refactor(simulation): take a magnetic path instead of a core record"
```

---

### Task 2: Assemble the preliminary request from a project

**Files:**
- Create: `src/inductor_designer/application/services/preliminary_inputs.py`
- Test: `tests/unit/application/test_preliminary_inputs.py`

**Interfaces:**
- Consumes: `CoreMagneticProperties`, `PreliminaryRequest` (Task 1),
  `GeometryModel`, `CatalogRepository`, `CatalogCoreSelection`,
  `ManualCoreSelection`.
- Produces: `MANUAL_CORE_PATH_NOTE`, `CATALOG_OVERRIDE_NOTE`,
  `core_magnetic_properties(core: CoreSelection | None) -> CoreMagneticProperties | None`,
  `build_preliminary_request(project, catalog, geometry) -> PreliminaryRequest`
  where `geometry: GeometryModel | None`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/application/test_preliminary_inputs.py`:

```python
from __future__ import annotations

import math
from dataclasses import replace

from inductor_designer.application.services.geometry_model import build_geometry_model
from inductor_designer.application.services.preliminary_inputs import (
    CATALOG_OVERRIDE_NOTE,
    MANUAL_CORE_PATH_NOTE,
    build_preliminary_request,
    core_magnetic_properties,
)
from inductor_designer.domain.project import (
    CatalogCoreSelection,
    CoreOverride,
    ManualCoreSelection,
)
from tests.unit.application.test_geometry_model import CATALOG
from tests.unit.domain.test_catalog_records import make_core
from tests.unit.domain.test_project import make_project


def test_no_core_has_no_magnetic_properties() -> None:
    assert core_magnetic_properties(None) is None


def test_catalog_core_uses_the_manufacturer_effective_values() -> None:
    record = make_core()
    selection = CatalogCoreSelection(record.part_number, record, ())

    properties = core_magnetic_properties(selection)

    assert properties is not None
    assert properties.path_length_m == record.path_length_m
    assert properties.volume_m3 == record.volume_m3
    assert properties.notes == ()


def test_catalog_core_with_dimension_overrides_says_so() -> None:
    record = make_core()
    selection = CatalogCoreSelection(
        record.part_number,
        record,
        (CoreOverride("outer_diameter_m", 0.03, "measured"),),
    )

    properties = core_magnetic_properties(selection)

    assert properties is not None
    assert properties.path_length_m == record.path_length_m
    assert properties.notes == (CATALOG_OVERRIDE_NOTE,)


def test_manual_core_computes_the_mean_path_length_and_volume() -> None:
    selection = ManualCoreSelection(
        outer_diameter_m=0.0272,
        inner_diameter_m=0.0138,
        height_m=0.0112,
        corner_radius_m=0.0,
    )

    properties = core_magnetic_properties(selection)

    expected_path = math.pi * (0.0272 + 0.0138) / 2.0
    expected_volume = ((0.0272 - 0.0138) / 2.0) * 0.0112 * expected_path
    assert properties is not None
    assert properties.path_length_m == expected_path
    assert properties.volume_m3 == expected_volume
    assert properties.notes == (MANUAL_CORE_PATH_NOTE,)


def test_request_carries_conductors_and_packings_from_the_geometry_model() -> None:
    project = make_project()
    geometry = build_geometry_model(project, CATALOG)

    request = build_preliminary_request(project, CATALOG, geometry)

    assert request.project is project
    assert request.core is not None
    assert set(request.conductors_by_winding) == {"w1"}
    assert request.conductors_by_winding["w1"].name == "AWG 18"
    assert set(request.packings_by_winding) == {"w1"}
    assert request.packings_by_winding["w1"].wire_length_m > 0.0


def test_request_without_geometry_keeps_conductors_and_drops_packings() -> None:
    """Specification section 9: geometry failure invalidates only geometry-dependent results."""
    project = make_project()

    request = build_preliminary_request(project, CATALOG, None)

    assert set(request.conductors_by_winding) == {"w1"}
    assert request.packings_by_winding == {}


def test_request_skips_a_winding_whose_conductor_is_not_in_the_catalog() -> None:
    project = make_project()
    unknown = replace(project.design.windings[0], conductor_name="AWG 99")
    project = replace(
        project, design=replace(project.design, windings=(unknown,))
    )

    request = build_preliminary_request(project, CATALOG, None)

    assert request.conductors_by_winding == {}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/application/test_preliminary_inputs.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named
'inductor_designer.application.services.preliminary_inputs'`.

- [ ] **Step 3: Write the service**

Create `src/inductor_designer/application/services/preliminary_inputs.py`:

```python
"""Assemble one `PreliminaryRequest` from a project (specification section 5).

The estimator takes records, never repositories. This service is the single
place that resolves them, so the Qt controller stays free of catalog lookups
and every resolution rule is testable without Qt.
"""

from __future__ import annotations

import math

from inductor_designer.application.ports.catalog import CatalogRepository
from inductor_designer.application.services.geometry_model import GeometryModel
from inductor_designer.domain.catalog_records import ConductorRecord
from inductor_designer.domain.project import (
    CatalogCoreSelection,
    CoreSelection,
    InductorProject,
    ManualCoreSelection,
)
from inductor_designer.geometry.packing import PackedWinding
from inductor_designer.simulation.preliminary import PreliminaryRequest
from inductor_designer.simulation.preliminary_contracts import CoreMagneticProperties

MANUAL_CORE_PATH_NOTE = (
    "Manual-core magnetic path length and volume are computed from the entered "
    "toroid dimensions as l_e = pi * (outer diameter + inner diameter) / 2, "
    "A_e = ((outer diameter - inner diameter) / 2) * height, and "
    "V_e = A_e * l_e. Manufacturer effective values are not available for a "
    "Manual core."
)
CATALOG_OVERRIDE_NOTE = (
    "Core dimension overrides change the modeled geometry but not the "
    "manufacturer's effective magnetic path length and volume, which are used "
    "here as recorded in the catalog."
)


def core_magnetic_properties(
    core: CoreSelection | None,
) -> CoreMagneticProperties | None:
    """The path length and volume the estimator needs, and their provenance."""
    if core is None:
        return None
    if isinstance(core, ManualCoreSelection):
        path_length_m = math.pi * (core.outer_diameter_m + core.inner_diameter_m) / 2.0
        effective_area_m2 = (
            (core.outer_diameter_m - core.inner_diameter_m) / 2.0
        ) * core.height_m
        return CoreMagneticProperties(
            path_length_m=path_length_m,
            volume_m3=effective_area_m2 * path_length_m,
            notes=(MANUAL_CORE_PATH_NOTE,),
        )
    assert isinstance(core, CatalogCoreSelection)
    return CoreMagneticProperties(
        path_length_m=core.snapshot.path_length_m,
        volume_m3=core.snapshot.volume_m3,
        notes=(CATALOG_OVERRIDE_NOTE,) if core.overrides else (),
    )


def build_preliminary_request(
    project: InductorProject,
    catalog: CatalogRepository,
    geometry: GeometryModel | None,
) -> PreliminaryRequest:
    """Resolve records for one estimate.

    `geometry` is None when the geometry model refused the current project. The
    request is still built: flux density, core loss, and current density do not
    depend on packing, so only wire length, resistance, and wire loss lose their
    input and the estimator reports exactly those as unavailable.
    """
    conductors: dict[str, ConductorRecord] = {}
    for winding in project.design.windings:
        record = catalog.get_conductor(winding.conductor_name)
        if record is not None:
            conductors[winding.winding_id] = record
    packings: dict[str, PackedWinding] = (
        {} if geometry is None else {item.winding_id: item for item in geometry.packings}
    )
    return PreliminaryRequest(
        project=project,
        core=core_magnetic_properties(project.design.core),
        conductors_by_winding=conductors,
        packings_by_winding=packings,
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/application/test_preliminary_inputs.py -q`
Expected: PASS, 7 tests.

- [ ] **Step 5: Run the gates and commit**

Run all five gate commands. Expected: clean.

```bash
git add src/inductor_designer/application/services/preliminary_inputs.py tests/unit/application/test_preliminary_inputs.py
git commit -m "feat(application): assemble preliminary estimator inputs from a project"
```

---

### Task 3: Bidirectional core/material selection

Selecting either side filters the other. An incompatible pairing clears the
incompatible side and explains why; it never substitutes a different core or
material (specification section 4.1).

**Files:**
- Create: `src/inductor_designer/application/services/core_material_selection.py`
- Test: `tests/unit/application/test_core_material_selection.py`

**Interfaces:**
- Consumes: `CatalogRepository`, `MaterialRepository`, `pin_material_revision`,
  `MaterialSelectionError`, `select_core`, `validate_record`.
- Produces: `CoreOption`, `MaterialOption`, `SelectionOutcome`,
  `ClearedSelection`, `required_material_ref(project)`,
  `core_options(catalog, material_ref=None)`,
  `material_options(repository, material_ref=None)`,
  `apply_catalog_core(project, catalog, part_number)`,
  `apply_manual_core(project, *, outer_diameter_m, inner_diameter_m, height_m, corner_radius_m)`,
  `apply_material_revision(project, repository, ref, revision_id, *, bh_series_id=None, acknowledge_manual_compatibility=False)`,
  `revalidate_pinned_material(project, repository)`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/application/test_core_material_selection.py`:

```python
from __future__ import annotations

from dataclasses import replace

import pytest

from inductor_designer.application.services.core_material_selection import (
    ClearedSelection,
    apply_catalog_core,
    apply_manual_core,
    apply_material_revision,
    clear_material_selection,
    core_options,
    material_options,
    required_material_ref,
    revalidate_pinned_material,
)
from inductor_designer.application.services.material_selection import (
    MaterialSelectionError,
)
from inductor_designer.domain.project import (
    CatalogCoreSelection,
    ManualCoreSelection,
)
from inductor_designer.materials.identity import MaterialRef
from inductor_designer.materials.records import MaterialStatus
from inductor_designer.materials.records import MaterialRecord
from tests.fakes.material_repository import InMemoryMaterialRepository
from tests.unit.application.test_geometry_model import CATALOG
from tests.unit.domain.test_catalog_records import make_core
from tests.unit.domain.test_project import make_material_record, make_project

# `make_material_record()` is Magnetics Kool Mu 60, which is exactly
# `make_core().material`, so the shipped fixtures are already a compatible pair.
# It carries no series and no sources, so `save(record, {})` passes the fake's
# sha256 check and `bh_series_id` must stay None.
OTHER_REF = MaterialRef("Magnetics", "High Flux", "60")


def repository_with(*records: MaterialRecord) -> InMemoryMaterialRepository:
    repository = InMemoryMaterialRepository()
    for record in records:
        repository.save(record, {})
    return repository


def test_catalog_core_declares_its_required_material() -> None:
    record = make_core()
    project = make_project(
        design=replace(
            make_project().design,
            core=CatalogCoreSelection(record.part_number, record, ()),
        )
    )

    assert required_material_ref(project) == record.material


def test_manual_core_requires_no_particular_material() -> None:
    project = make_project(
        design=replace(
            make_project().design,
            core=ManualCoreSelection(0.0272, 0.0138, 0.0112, 0.0),
        )
    )

    assert required_material_ref(project) is None


def test_core_options_filter_by_the_selected_material() -> None:
    record = make_core()

    assert [option.part_number for option in core_options(CATALOG, None)] == [
        record.part_number
    ]
    assert core_options(CATALOG, OTHER_REF) == ()
    assert len(core_options(CATALOG, record.material)) == 1


def test_material_options_list_only_selectable_revisions() -> None:
    approved = make_material_record()
    draft = replace(
        make_material_record(),
        revision_id="aaaaaaaaaaaa",
        status=MaterialStatus.DRAFT,
        reviewed_by=None,
        approved_by=None,
    )
    repository = repository_with(approved, draft)

    options = material_options(repository, None)

    assert [option.revision_id for option in options] == [approved.revision_id]
    assert options[0].bh_series_ids == ()


def test_material_options_filter_by_the_selected_core() -> None:
    approved = make_material_record()
    repository = repository_with(approved)

    assert material_options(repository, approved.ref) != ()
    assert material_options(repository, OTHER_REF) == ()


def test_selecting_an_incompatible_core_clears_the_material_and_explains() -> None:
    approved = make_material_record()
    repository = repository_with(approved)
    project = apply_material_revision(
        make_project(design=replace(make_project().design, core=None, core_material=None)),
        repository,
        approved.ref,
        approved.revision_id,
        bh_series_id=None,
    ).project
    incompatible = replace(make_core(), material=OTHER_REF)

    class OneCore:
        def get_core(self, part_number: str) -> object:
            return incompatible if part_number == incompatible.part_number else None

        def list_cores(self) -> tuple[object, ...]:
            return (incompatible,)

        def get_conductor(self, name: str) -> None:
            return None

        def list_conductor_names(self) -> tuple[str, ...]:
            return ()

    outcome = apply_catalog_core(project, OneCore(), incompatible.part_number)  # type: ignore[arg-type]

    assert outcome.cleared is ClearedSelection.MATERIAL
    assert outcome.project.design.core_material is None
    assert isinstance(outcome.project.design.core, CatalogCoreSelection)
    assert OTHER_REF.name in outcome.message
    assert "cleared" in outcome.message


def test_selecting_an_incompatible_material_clears_the_core_and_explains() -> None:
    record = make_core()
    approved = replace(make_material_record(), ref=OTHER_REF)
    repository = repository_with(approved)
    project = make_project(
        design=replace(
            make_project().design,
            core=CatalogCoreSelection(record.part_number, record, ()),
            core_material=None,
        )
    )

    outcome = apply_material_revision(
        project, repository, OTHER_REF, approved.revision_id, bh_series_id=None
    )

    assert outcome.cleared is ClearedSelection.CORE
    assert outcome.project.design.core is None
    assert outcome.project.design.core_material is not None
    assert record.part_number in outcome.message


def test_compatible_selection_clears_nothing() -> None:
    record = make_core()
    approved = make_material_record()
    repository = repository_with(approved)
    project = make_project(
        design=replace(
            make_project().design,
            core=CatalogCoreSelection(record.part_number, record, ()),
            core_material=None,
        )
    )

    outcome = apply_material_revision(
        project, repository, approved.ref, approved.revision_id, bh_series_id=None
    )

    assert outcome.cleared is None
    assert outcome.project.design.core is not None
    assert outcome.project.design.core_material is not None
    assert outcome.project.design.manual_material_compatibility_acknowledged is False


def test_manual_core_material_requires_acknowledgment() -> None:
    approved = make_material_record()
    repository = repository_with(approved)
    project = make_project(
        design=replace(
            make_project().design,
            core=ManualCoreSelection(0.0272, 0.0138, 0.0112, 0.0),
            core_material=None,
        )
    )

    acknowledged = apply_material_revision(
        project,
        repository,
        approved.ref,
        approved.revision_id,
        bh_series_id=None,
        acknowledge_manual_compatibility=True,
    )

    assert acknowledged.project.design.manual_material_compatibility_acknowledged is True


def test_manual_core_dimensions_replace_the_core_without_touching_the_material() -> None:
    approved = make_material_record()
    repository = repository_with(approved)
    project = apply_material_revision(
        make_project(design=replace(make_project().design, core=None, core_material=None)),
        repository,
        approved.ref,
        approved.revision_id,
        bh_series_id=None,
    ).project

    outcome = apply_manual_core(
        project,
        outer_diameter_m=0.0272,
        inner_diameter_m=0.0138,
        height_m=0.0112,
        corner_radius_m=0.0,
    )

    assert outcome.cleared is None
    assert isinstance(outcome.project.design.core, ManualCoreSelection)
    assert outcome.project.design.core_material is not None


def test_a_deleted_pinned_revision_becomes_unresolved_with_an_actionable_message() -> None:
    approved = make_material_record()
    repository = repository_with(approved)
    project = apply_material_revision(
        make_project(design=replace(make_project().design, core=None, core_material=None)),
        repository,
        approved.ref,
        approved.revision_id,
        bh_series_id=None,
    ).project
    repository.delete_revision(approved.ref, approved.revision_id)

    outcome = revalidate_pinned_material(project, repository)

    assert outcome.cleared is ClearedSelection.MATERIAL
    assert outcome.project.design.core_material is None
    assert approved.revision_id in outcome.message
    assert "no longer" in outcome.message


def test_resizing_a_manual_core_drops_the_recorded_acknowledgement() -> None:
    approved = make_material_record()
    repository = repository_with(approved)
    manual = make_project(
        design=replace(
            make_project().design,
            core=ManualCoreSelection(0.0272, 0.0138, 0.0112, 0.0),
            core_material=None,
        )
    )
    pinned = apply_material_revision(
        manual,
        repository,
        approved.ref,
        approved.revision_id,
        bh_series_id=None,
        acknowledge_manual_compatibility=True,
    ).project
    assert pinned.design.manual_material_compatibility_acknowledged is True

    outcome = apply_manual_core(
        pinned,
        outer_diameter_m=0.030,
        inner_diameter_m=0.015,
        height_m=0.012,
        corner_radius_m=0.0,
    )

    assert outcome.project.design.manual_material_compatibility_acknowledged is False
    assert outcome.project.design.core_material is not None
    assert "Confirm material compatibility again" in outcome.message


def test_clearing_the_material_unpins_it_and_leaves_the_core() -> None:
    approved = make_material_record()
    repository = repository_with(approved)
    project = apply_material_revision(
        make_project(),
        repository,
        approved.ref,
        approved.revision_id,
        bh_series_id=None,
    ).project

    outcome = clear_material_selection(project)

    assert outcome.cleared is ClearedSelection.MATERIAL
    assert outcome.project.design.core_material is None
    assert outcome.project.design.core is not None
    assert (
        outcome.project.design.manual_material_compatibility_acknowledged is False
    )

    assert clear_material_selection(outcome.project).cleared is None


def test_a_still_present_pinned_revision_survives_a_library_refresh() -> None:
    approved = make_material_record()
    repository = repository_with(approved)
    project = apply_material_revision(
        make_project(design=replace(make_project().design, core=None, core_material=None)),
        repository,
        approved.ref,
        approved.revision_id,
        bh_series_id=None,
    ).project

    outcome = revalidate_pinned_material(project, repository)

    assert outcome.cleared is None
    assert outcome.project.design.core_material == project.design.core_material


def test_an_unselectable_revision_is_refused_without_changing_the_project() -> None:
    draft = replace(
        make_material_record(),
        revision_id="aaaaaaaaaaaa",
        status=MaterialStatus.DRAFT,
        reviewed_by=None,
        approved_by=None,
    )
    repository = repository_with(draft)
    project = make_project(design=replace(make_project().design, core=None, core_material=None))

    with pytest.raises(MaterialSelectionError):
        apply_material_revision(
            project, repository, draft.ref, draft.revision_id, bh_series_id=None
        )
```

`MaterialRecord.__post_init__` requires `revision_id` to be 12 lowercase
hexadecimal characters (or empty for a transient draft) and forbids a reviewer or
approver on a DRAFT record, so a DRAFT fixture uses a valid hex placeholder and
clears both names — all three values are incidental to what these tests assert.

Every fixture this test uses already exists — do not write new ones.
`make_material_record()` takes no arguments; vary it with
`dataclasses.replace`. `make_project()` already carries
`CatalogCoreSelection("0077071A7", make_core(), ())` and
`core_material=None`, which is why the tests that need an unset core replace
`design.core` explicitly.

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/application/test_core_material_selection.py -q`
Expected: FAIL with `ModuleNotFoundError` for
`inductor_designer.application.services.core_material_selection`.

- [ ] **Step 3: Write the service**

Create `src/inductor_designer/application/services/core_material_selection.py`:

```python
"""Bidirectional core/material selection (specification section 4.1).

Each side filters the other. When a new choice makes the existing paired
selection incompatible, the incompatible side is cleared and the caller is told
why. Nothing is ever substituted: the user picks the replacement.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum

from inductor_designer.application.ports.catalog import CatalogRepository
from inductor_designer.application.ports.material_repository import MaterialRepository
from inductor_designer.application.services.catalog_revisions import select_core
from inductor_designer.application.services.material_selection import (
    pin_material_revision,
)
from inductor_designer.domain.catalog_records import CoreFamily
from inductor_designer.domain.project import (
    CatalogCoreSelection,
    InductorProject,
    ManualCoreSelection,
)
from inductor_designer.materials.identity import MaterialRef
from inductor_designer.materials.records import (
    MaterialRecord,
    MaterialStatus,
    SeriesKind,
)
from inductor_designer.materials.validation import IssueSeverity, validate_record

_SELECTABLE_STATUSES = (MaterialStatus.IMPORTED, MaterialStatus.APPROVED)


class ClearedSelection(str, Enum):
    CORE = "core"
    MATERIAL = "material"


@dataclass(frozen=True, slots=True)
class CoreOption:
    part_number: str
    manufacturer: str
    family: CoreFamily
    material_ref: MaterialRef
    outer_diameter_m: float
    inner_diameter_m: float
    height_m: float


@dataclass(frozen=True, slots=True)
class MaterialOption:
    ref: MaterialRef
    revision_id: str
    status: MaterialStatus
    created_at: str
    bh_series_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SelectionOutcome:
    project: InductorProject
    cleared: ClearedSelection | None
    message: str


def required_material_ref(project: InductorProject) -> MaterialRef | None:
    """The material identity a catalog core demands; None for Manual or no core."""
    core = project.design.core
    return core.snapshot.material if isinstance(core, CatalogCoreSelection) else None


def core_options(
    catalog: CatalogRepository, material_ref: MaterialRef | None
) -> tuple[CoreOption, ...]:
    return tuple(
        CoreOption(
            part_number=record.part_number,
            manufacturer=record.manufacturer,
            family=record.family,
            material_ref=record.material,
            outer_diameter_m=record.outer_diameter.nominal_m,
            inner_diameter_m=record.inner_diameter.nominal_m,
            height_m=record.height.nominal_m,
        )
        for record in catalog.list_cores()
        if material_ref is None or record.material == material_ref
    )


def _is_selectable(record: MaterialRecord) -> bool:
    if record.status not in _SELECTABLE_STATUSES:
        return False
    return not any(
        issue.severity is IssueSeverity.ERROR for issue in validate_record(record)
    )


def material_options(
    repository: MaterialRepository, material_ref: MaterialRef | None
) -> tuple[MaterialOption, ...]:
    options: list[MaterialOption] = []
    for ref in repository.list_materials():
        if material_ref is not None and ref != material_ref:
            continue
        for revision_id in repository.list_revisions(ref):
            record = repository.get(ref, revision_id)
            if not _is_selectable(record):
                continue
            options.append(
                MaterialOption(
                    ref=ref,
                    revision_id=revision_id,
                    status=record.status,
                    created_at=record.created_at,
                    bh_series_ids=tuple(
                        series.series_id
                        for series in record.series
                        if series.kind is SeriesKind.BH_CURVE
                    ),
                )
            )
    return tuple(options)


def apply_catalog_core(
    project: InductorProject, catalog: CatalogRepository, part_number: str
) -> SelectionOutcome:
    """Select a catalog core, clearing a material it cannot carry."""
    selected = select_core(project, catalog, part_number)
    core = selected.design.core
    assert isinstance(core, CatalogCoreSelection)
    # A catalog core declares its own material identity, so a Manual-core
    # compatibility acknowledgment can never apply to it. Dropping it here
    # covers the compatible case too: switching Manual -> Catalog must not
    # leave a stale acknowledgment on a design that never needed one, or the
    # run manifest reports an assumption the user never made.
    selected = replace(
        selected,
        design=replace(
            selected.design, manual_material_compatibility_acknowledged=False
        ),
    )
    material = selected.design.core_material
    if material is not None and material.ref != core.snapshot.material:
        cleared = replace(
            selected,
            design=replace(selected.design, core_material=None),
        )
        return SelectionOutcome(
            project=cleared,
            cleared=ClearedSelection.MATERIAL,
            message=(
                f"Core {part_number} requires material "
                f"{core.snapshot.material.manufacturer} "
                f"{core.snapshot.material.name} {core.snapshot.material.grade}, so the "
                f"pinned {material.ref.manufacturer} {material.ref.name} "
                f"{material.ref.grade} revision {material.revision_id} was cleared. "
                "Select a compatible material revision."
            ),
        )
    return SelectionOutcome(
        project=selected,
        cleared=None,
        message=f"Selected catalog core {part_number}.",
    )


def apply_manual_core(
    project: InductorProject,
    *,
    outer_diameter_m: float,
    inner_diameter_m: float,
    height_m: float,
    corner_radius_m: float,
) -> SelectionOutcome:
    """A Manual core carries no material identity, so nothing is ever cleared.

    New dimensions are new geometry, so any recorded compatibility attestation
    is dropped: the user attested to the pair they saw, and every consumer of
    the project -- exports, run manifests, other screens -- reads that flag.
    """
    core = ManualCoreSelection(
        outer_diameter_m=outer_diameter_m,
        inner_diameter_m=inner_diameter_m,
        height_m=height_m,
        corner_radius_m=corner_radius_m,
    )
    reconfirm = (
        " Confirm material compatibility again for the new dimensions."
        if project.design.manual_material_compatibility_acknowledged
        else ""
    )
    return SelectionOutcome(
        project=replace(
            project,
            design=replace(
                project.design,
                core=core,
                manual_material_compatibility_acknowledged=False,
            ),
        ),
        cleared=None,
        message=f"Applied manual core dimensions.{reconfirm}",
    )


def apply_material_revision(
    project: InductorProject,
    repository: MaterialRepository,
    ref: MaterialRef,
    revision_id: str,
    *,
    bh_series_id: str | None = None,
    acknowledge_manual_compatibility: bool = False,
) -> SelectionOutcome:
    """Pin an exact revision, clearing a catalog core it does not belong to.

    `pin_material_revision` refuses a mismatched catalog core outright; clearing
    the core first is what turns that refusal into the visible, unresolved state
    the specification asks for.
    """
    record = repository.get(ref, revision_id)
    core = project.design.core
    cleared: ClearedSelection | None = None
    message_prefix = ""
    target = project
    if isinstance(core, CatalogCoreSelection) and core.snapshot.material != ref:
        target = replace(project, design=replace(project.design, core=None))
        cleared = ClearedSelection.CORE
        message_prefix = (
            f"Catalog core {core.part_number} requires material "
            f"{core.snapshot.material.manufacturer} {core.snapshot.material.name} "
            f"{core.snapshot.material.grade}, so it was cleared. Select a core that "
            "uses the pinned material. "
        )
    pinned = pin_material_revision(
        target,
        record,
        bh_series_id=bh_series_id,
        manual_compatibility_acknowledged=(
            acknowledge_manual_compatibility
            if isinstance(target.design.core, ManualCoreSelection)
            else False
        ),
    )
    return SelectionOutcome(
        project=pinned,
        cleared=cleared,
        message=(
            f"{message_prefix}Pinned {ref.manufacturer} {ref.name} {ref.grade} "
            f"revision {revision_id}."
        ),
    )


def clear_material_selection(project: InductorProject) -> SelectionOutcome:
    """Unpin the material revision, leaving the core alone.

    Clearing carries no compatibility rule, but it still happens here so the
    controller never mutates project state itself.
    """
    if project.design.core_material is None:
        return SelectionOutcome(project, None, "No material revision is pinned.")
    return SelectionOutcome(
        project=replace(
            project,
            design=replace(
                project.design,
                core_material=None,
                manual_material_compatibility_acknowledged=False,
            ),
        ),
        cleared=ClearedSelection.MATERIAL,
        message="Cleared the pinned material revision.",
    )


def revalidate_pinned_material(
    project: InductorProject, repository: MaterialRepository
) -> SelectionOutcome:
    """Re-check the pinned revision after the material library changed.

    Called when the Material Studio window closes. An exact revision that still
    exists and is still selectable survives untouched; anything else becomes
    unresolved with a message that names it.
    """
    material = project.design.core_material
    if material is None:
        return SelectionOutcome(project, None, "No material revision is pinned.")
    still_present = material.revision_id in repository.list_revisions(material.ref)
    if still_present and _is_selectable(
        repository.get(material.ref, material.revision_id)
    ):
        return SelectionOutcome(
            project,
            None,
            f"Pinned revision {material.revision_id} is unchanged.",
        )
    reason = (
        "no longer exists in the material library"
        if not still_present
        else "is no longer selectable"
    )
    return SelectionOutcome(
        project=replace(
            project,
            design=replace(
                project.design,
                core_material=None,
                manual_material_compatibility_acknowledged=False,
            ),
        ),
        cleared=ClearedSelection.MATERIAL,
        message=(
            f"Pinned {material.ref.manufacturer} {material.ref.name} "
            f"{material.ref.grade} revision {material.revision_id} {reason}, so the "
            "material selection was cleared. Select a revision that exists."
        ),
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/application/test_core_material_selection.py -q`
Expected: PASS, 16 tests.

- [ ] **Step 5: Run the gates and commit**

```bash
git add src/inductor_designer/application/services/core_material_selection.py tests/unit/application/test_core_material_selection.py
git commit -m "feat(application): filter cores and materials bidirectionally"
```

---

### Task 4: One session owner for the project

Five controllers will read and write the same project. Without a single owner
they each keep a snapshot and silently overwrite each other's edits. This task
introduces the owner and moves the existing controllers onto it without changing
any user-visible behavior.

**Files:**
- Create: `src/inductor_designer/ui/project_session.py`
- Modify: `src/inductor_designer/ui/guided_studio_controller.py:43-66`, `:114-132`,
  `:200-272`
- Modify: `src/inductor_designer/ui/main.py:131-139`, `:192-253`
- Modify: `tests/ui/test_guided_studio_controller.py:25`, `:50`
- Modify: `tests/ui/test_guided_studio_qml.py:27`
- Test: `tests/ui/test_project_session.py`

**Interfaces:**
- Consumes: `CurrentProjectProvider` (`ui/generation_controller.py:19`) for the
  thread-safe hand-off to the generation worker thread.
- Produces: `ProjectSession(QObject)` with `project` (property, thread-safe
  read), `document_path: Path | None`, `apply(project)`, `set_status(message)`,
  QML properties `dirty: bool`, `documentPath: str`, `statusMessage: str`, slot
  `saveProject() -> bool`, signals `projectChanged`, `dirtyChanged`,
  `statusMessageChanged`.
  `GuidedStudioController(session: ProjectSession, catalog: CatalogRepository,
  parent=None)`. `MaterialStudioController` is deliberately left alone here: Task
  8 deletes its project writer once the Core & Material screen exists to replace
  it, so wiring it to the session now would be work thrown away.

- [ ] **Step 1: Write the failing test**

Create `tests/ui/test_project_session.py`:

```python
from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtGui import QGuiApplication  # noqa: E402

from inductor_designer.domain.project import InductorProject  # noqa: E402
from inductor_designer.ui.project_session import ProjectSession  # noqa: E402
from tests.unit.domain.test_project import make_project  # noqa: E402

pytestmark = pytest.mark.ui


def test_session_starts_clean_and_publishes_edits() -> None:
    QGuiApplication.instance() or QGuiApplication([])
    session = ProjectSession(make_project())
    changes: list[int] = []
    session.projectChanged.connect(lambda: changes.append(1))

    assert session.dirty is False
    assert session.documentPath == ""

    session.apply(replace(session.project, description="edited"))

    assert session.project.description == "edited"
    assert session.dirty is True
    assert changes == [1]


def test_saving_persists_once_and_clears_dirty(tmp_path: Path) -> None:
    QGuiApplication.instance() or QGuiApplication([])
    saved: list[InductorProject] = []
    session = ProjectSession(
        make_project(),
        document_path=tmp_path / "boost.inductor.json",
        save_callback=saved.append,
    )
    session.apply(replace(session.project, description="edited"))

    assert session.saveProject() is True

    assert [item.description for item in saved] == ["edited"]
    assert session.dirty is False
    assert session.statusMessage == "Saved"
    assert session.documentPath == str(tmp_path / "boost.inductor.json")


def test_a_failed_save_keeps_the_session_dirty() -> None:
    QGuiApplication.instance() or QGuiApplication([])

    def explode(project: InductorProject) -> None:
        raise OSError("disk full")

    session = ProjectSession(
        make_project(), Path("boost.inductor.json"), save_callback=explode
    )
    session.apply(replace(session.project, description="edited"))

    assert session.saveProject() is False

    assert session.dirty is True
    assert "disk full" in session.statusMessage


def test_a_session_without_a_document_path_cannot_save() -> None:
    QGuiApplication.instance() or QGuiApplication([])
    session = ProjectSession(make_project())

    assert session.saveProject() is False
    assert "no project document" in session.statusMessage.casefold()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/ui/test_project_session.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named
'inductor_designer.ui.project_session'`.

- [ ] **Step 3: Write the session**

Create `src/inductor_designer/ui/project_session.py`:

```python
"""The single in-memory project every Guided Studio controller shares.

Five controllers edit one project. Each keeping its own snapshot is how two
screens end up disagreeing about the same design, so they all read and write
here instead. The generation worker runs on another thread, so the actual
storage is the existing lock-protected `CurrentProjectProvider`.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Property, QObject, Signal, Slot

from inductor_designer.domain.project import InductorProject
from inductor_designer.ui.generation_controller import CurrentProjectProvider


class ProjectSession(QObject):
    projectChanged = Signal()
    dirtyChanged = Signal()
    statusMessageChanged = Signal()

    def __init__(
        self,
        project: InductorProject,
        document_path: Path | None = None,
        save_callback: Callable[[InductorProject], None] | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._provider = CurrentProjectProvider(project)
        self._document_path = document_path
        self._save_callback = save_callback
        self._dirty = False
        self._status_message = "Ready"

    @property
    def project(self) -> InductorProject:
        return self._provider.current()

    @property
    def document_path(self) -> Path | None:
        return self._document_path

    def apply(self, project: InductorProject) -> None:
        """Accept an already-validated edit as the current session project."""
        self._provider.replace(project)
        self._set_dirty(True)
        self.projectChanged.emit()

    def _get_dirty(self) -> bool:
        return self._dirty

    dirty = Property(bool, _get_dirty, notify=dirtyChanged)

    def _get_document_path(self) -> str:
        return "" if self._document_path is None else str(self._document_path)

    documentPath = Property(str, _get_document_path, constant=True)

    def _get_status_message(self) -> str:
        return self._status_message

    statusMessage = Property(str, _get_status_message, notify=statusMessageChanged)

    def _set_dirty(self, value: bool) -> None:
        if value == self._dirty:
            return
        self._dirty = value
        self.dirtyChanged.emit()

    def set_status(self, message: str) -> None:
        self._status_message = message
        self.statusMessageChanged.emit()

    @Slot(result=bool)
    def saveProject(self) -> bool:
        # Guard on the persister, not on the path: production always sets both
        # together, and the message must describe the condition actually tested.
        if self._save_callback is None:
            self.set_status(
                "Unable to save: this session has no project document to save "
                "into. Start the application with --project."
            )
            return False
        try:
            self._save_callback(self.project)
        except Exception as error:  # noqa: BLE001 - QML needs a safe failure path
            self.set_status(f"Unable to save project: {error}")
            return False
        self._set_dirty(False)
        self.set_status("Saved")
        return True
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/ui/test_project_session.py -q`
Expected: PASS, 4 tests.

- [ ] **Step 5: Move `GuidedStudioController` onto the session**

In `src/inductor_designer/ui/guided_studio_controller.py`:

- Constructor becomes:

```python
    def __init__(
        self,
        session: ProjectSession,
        catalog: CatalogRepository,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._session = session
        self._catalog = catalog
        project = session.project
        self._selected_winding_id = (
            project.design.windings[0].winding_id if project.design.windings else ""
        )
        self._windings = self._winding_rows(
            project.design.windings, project.operating_point.windings
        )
        self._preview_entries = self._build_preview(project)
```

- Delete `self._project`, `self._save_callback`, `self._dirty`,
  `self._status_message`, and `_set_dirty`. Keep the controller's own
  `dirtyChanged` and `statusMessageChanged` signals — a `Property` cannot notify
  off another object's signal — and make them relays of the session's:

```python
        session.dirtyChanged.connect(self.dirtyChanged)
        session.statusMessageChanged.connect(self.statusMessageChanged)
```

  with the two properties reading through the session:

```python
    def _get_dirty(self) -> bool:
        # PySide6's stubs do not type `Property` as a descriptor, so a
        # cross-object read needs an explicit coercion under strict mypy.
        return bool(self._session.dirty)

    dirty = Property(bool, _get_dirty, notify=dirtyChanged)

    def _get_status_message(self) -> str:
        return str(self._session.statusMessage)

    statusMessage = Property(str, _get_status_message, notify=statusMessageChanged)
```

- Everywhere `self._project` was read, read `self._session.project`. In
  `setWindingField`, the accepted edit ends with `self._session.apply(updated_project)`
  and `self._session.set_status(f"Updated {winding_id}")`; a rejected edit calls
  `self._session.set_status(f"Unable to apply change: {error}")` and returns
  False without applying.
- `saveDraft` becomes a one-line delegate so `Main.qml` keeps working:

```python
    @Slot(result=bool)
    def saveDraft(self) -> bool:
        return self._session.saveProject()
```

- Add a `refresh()` slot that rebuilds rows and preview from the session, so
  another controller's edit (a core change, for example) shows up here:

```python
    @Slot()
    def refresh(self) -> None:
        project = self._session.project
        # Keep the last valid preview: a core edit that breaks geometry is
        # reported by its own controller, and a blank canvas would hide the
        # windings the user is about to fix. Use `contextlib.suppress`, not
        # `try/except: pass`, which this repo's ruff SIM105 rule rejects.
        with contextlib.suppress(GeometryModelError):
            self._preview_entries = self._build_preview(project)
        self._windings = self._winding_rows(
            project.design.windings, project.operating_point.windings
        )
        self.windingsChanged.emit()
        self.previewEntriesChanged.emit()
```

- [ ] **Step 6: Wire `main.py`**

In `src/inductor_designer/ui/main.py`, build the session once, before the
controllers, and let everything else read it:

```python
    session: ProjectSession | None = None
    if project is not None:
        session = ProjectSession(project, args.project, project_save_callback)
```

- `_build_generation_controller` takes the session instead of
  `CurrentProjectProvider` and its `runner` closure calls `session.project`.
- `save_project` keeps persisting through `ProjectRepository.save` and no longer
  needs `_persist_and_publish_project` or the provider: delete
  `_persist_and_publish_project` and the `project_provider` local.
- `GuidedStudioController(session, SqliteCatalogRepository(args.catalog))`.
- `MaterialStudioController(...)` keeps its current `project=` and
  `project_save_callback=` arguments until Task 8 removes them.
- `create_engine` gains a `project_session: ProjectSession | None = None`
  parameter and exposes it as the `projectSession` context property.

- [ ] **Step 7: Update the two existing controller tests**

`tests/ui/test_guided_studio_controller.py` builds the session explicitly:

```python
    saved: list[object] = []
    session = ProjectSession(make_project(), Path("boost.inductor.json"), saved.append)
    controller = GuidedStudioController(session, CATALOG)
```

and the second test uses `ProjectSession(make_project())`.
`tests/ui/test_guided_studio_qml.py` becomes
`GuidedStudioController(ProjectSession(make_project()), CATALOG)`.

Two existing modules outside this list also reference `_persist_and_publish_project`
and must be updated: `tests/ui/test_generation_controller.py` and
`tests/integration/test_material_studio_exit.py`. The one test that exists only to
prove "publish to same-session consumers only after persistence succeeds" is
deleted, not rewritten: `ProjectSession.apply` publishes in-session edits
immediately and `saveProject` persists separately, so that invariant no longer
exists by design. Note the consequence — the generation worker now reads live
unsaved edits, which is exactly why the run gate blocks a dirty project.

Cover `refresh()` while you are here, since Tasks 5, 7, and 10 all depend on its
keep-the-last-valid-preview behavior:

```python
def test_refresh_keeps_the_last_valid_preview_when_geometry_breaks() -> None:
    QGuiApplication.instance() or QGuiApplication([])
    session = ProjectSession(make_project())
    controller = GuidedStudioController(session, CATALOG)
    before = controller.previewEntries

    session.apply(
        replace(
            session.project,
            design=replace(
                session.project.design,
                windings=(replace(session.project.design.windings[0], turns=100000),),
            ),
        )
    )
    controller.refresh()

    assert controller.previewEntries is before
    assert controller.windings[0]["turns"] == 100000
```

- [ ] **Step 8: Run every gate**

Run: `.venv/Scripts/python.exe -m pytest tests -q -m "not aedt and not femm"`,
then `-m "ui"`, then ruff, mypy, and `check_architecture`.
Expected: all clean; the `-m ui` count rises to 41.

- [ ] **Step 9: Commit**

```bash
git add src/inductor_designer/ui tests/ui
git commit -m "refactor(ui): give Guided Studio one project session owner"
```

---

### Task 5: Shared operating point and the complete winding field set

**Files:**
- Modify: `src/inductor_designer/ui/guided_studio_controller.py`
- Test: `tests/ui/test_guided_studio_controller.py`

**Interfaces:**
- Consumes: `ProjectSession`, `ConductorMode`, `CurrentDirection`,
  `WindingDirection`, `CatalogRepository.list_conductor_names`.
- Produces on `GuidedStudioController`: properties `operatingPoint: dict`,
  `conductorNames: list`, `conductorModes: list`, `windingDirections: list`,
  `currentDirections: list`; signal `operatingPointChanged`; slot
  `setOperatingPointField(field: str, value: str) -> bool` accepting
  `frequencyHz`, `windingTemperatureC`, `coreTemperatureC`; extended
  `setWindingField` accepting `label`, `mode`, `clearanceMm`, `terminalIntent`,
  `dcCurrentA`, `currentDirection` on top of today's fields; winding rows gain
  `mode`, `dcCurrentA`, `currentDirection`, `clearanceMm`, `terminalIntent`.

- [ ] **Step 1: Write the failing test**

Append to `tests/ui/test_guided_studio_controller.py`:

```python
def test_operating_point_is_shared_and_editable() -> None:
    QGuiApplication.instance() or QGuiApplication([])
    session = ProjectSession(make_project())
    controller = GuidedStudioController(session, CATALOG)

    assert controller.operatingPoint["frequencyHz"] == 100000.0
    assert controller.operatingPoint["windingTemperatureC"] == 20.0
    assert controller.operatingPoint["coreTemperatureC"] == 25.0

    assert controller.setOperatingPointField("frequencyHz", "250e3") is True
    assert controller.setOperatingPointField("windingTemperatureC", "85") is True
    assert controller.setOperatingPointField("coreTemperatureC", "100") is True

    assert session.project.operating_point.frequency_hz == 250000.0
    assert session.project.operating_point.winding_temperature_c == 85.0
    assert session.project.operating_point.core_temperature_c == 100.0
    assert controller.dirty is True


def test_operating_point_rejects_a_nonpositive_frequency() -> None:
    QGuiApplication.instance() or QGuiApplication([])
    session = ProjectSession(make_project())
    controller = GuidedStudioController(session, CATALOG)

    assert controller.setOperatingPointField("frequencyHz", "0") is False

    assert session.project.operating_point.frequency_hz == 100000.0
    assert controller.dirty is False
    assert "Unable to apply" in controller.statusMessage


def test_operating_point_rejects_an_unknown_field() -> None:
    QGuiApplication.instance() or QGuiApplication([])
    controller = GuidedStudioController(ProjectSession(make_project()), CATALOG)

    assert controller.setOperatingPointField("temperature", "20") is False


def test_every_winding_input_the_specification_lists_is_editable() -> None:
    QGuiApplication.instance() or QGuiApplication([])
    session = ProjectSession(make_project())
    controller = GuidedStudioController(session, CATALOG)

    assert controller.setWindingField("w1", "label", "Primary side") is True
    assert controller.setWindingField("w1", "mode", "stranded") is True
    assert controller.setWindingField("w1", "clearanceMm", "1.5") is True
    assert controller.setWindingField("w1", "dcCurrentA", "5.5") is True
    assert controller.setWindingField("w1", "currentDirection", "reverse") is True
    assert controller.setWindingField("w1", "terminalIntent", "start out") is True

    winding = session.project.design.windings[0]
    excitation = session.project.operating_point.windings[0]
    assert winding.label == "Primary side"
    assert winding.mode is ConductorMode.STRANDED
    assert winding.min_clearance_m == 0.0015
    assert winding.terminal_intent == "start out"
    assert excitation.dc_current_a == 5.5
    assert excitation.current_direction is CurrentDirection.REVERSE
    assert controller.windings[0]["dcCurrentA"] == 5.5
    assert controller.windings[0]["currentDirection"] == "reverse"
    assert controller.windings[0]["clearanceMm"] == 1.5
    assert controller.windings[0]["mode"] == "stranded"


def test_a_negative_dc_current_is_refused_by_the_domain() -> None:
    QGuiApplication.instance() or QGuiApplication([])
    session = ProjectSession(make_project())
    controller = GuidedStudioController(session, CATALOG)

    assert controller.setWindingField("w1", "dcCurrentA", "-1") is False

    assert session.project.operating_point.windings[0].dc_current_a == 5.0
    assert "Unable to apply" in controller.statusMessage


def test_enumerated_choices_and_conductor_names_come_from_the_controller() -> None:
    QGuiApplication.instance() or QGuiApplication([])
    controller = GuidedStudioController(ProjectSession(make_project()), CATALOG)

    assert controller.conductorNames == ["AWG 18"]
    assert controller.conductorModes == ["solid", "stranded"]
    assert controller.windingDirections == ["cw", "ccw"]
    assert controller.currentDirections == ["forward", "reverse"]
```

Add the missing imports (`ConductorMode`, `CurrentDirection`, `ProjectSession`,
`Path`) at the top of the test module.

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/ui/test_guided_studio_controller.py -q`
Expected: FAIL with `AttributeError: 'GuidedStudioController' object has no
attribute 'operatingPoint'`.

- [ ] **Step 3: Extend the controller**

In `src/inductor_designer/ui/guided_studio_controller.py`:

```python
    operatingPointChanged = Signal()
```

```python
    def _get_operating_point(self) -> dict[str, object]:
        operating_point = self._session.project.operating_point
        return {
            "frequencyHz": operating_point.frequency_hz,
            "windingTemperatureC": operating_point.winding_temperature_c,
            "coreTemperatureC": operating_point.core_temperature_c,
        }

    operatingPoint = Property(dict, _get_operating_point, notify=operatingPointChanged)

    def _get_conductor_names(self) -> list[str]:
        return list(self._catalog.list_conductor_names())

    conductorNames = Property(list, _get_conductor_names, constant=True)

    def _get_conductor_modes(self) -> list[str]:
        return [item.value for item in ConductorMode]

    conductorModes = Property(list, _get_conductor_modes, constant=True)

    def _get_winding_directions(self) -> list[str]:
        return [item.value for item in WindingDirection]

    windingDirections = Property(list, _get_winding_directions, constant=True)

    def _get_current_directions(self) -> list[str]:
        return [item.value for item in CurrentDirection]

    currentDirections = Property(list, _get_current_directions, constant=True)
```

```python
    @Slot(str, str, result=bool)
    def setOperatingPointField(self, field: str, value: str) -> bool:
        """One shared frequency and two shared temperatures (specification 4.2).

        Explicit branches rather than a name-to-attribute mapping: a dynamic
        `replace(operating_point, **{attribute: number})` does not type-check
        under strict mypy, and `_updated_winding` and `_updated_operating_point`
        already dispatch this way.
        """
        project = self._session.project
        operating_point = project.operating_point
        try:
            if field == "frequencyHz":
                label = "Frequency"
                updated_point = replace(
                    operating_point, frequency_hz=self._number(value, label)
                )
            elif field == "windingTemperatureC":
                label = "Winding temperature"
                updated_point = replace(
                    operating_point,
                    winding_temperature_c=self._number(value, label),
                )
            elif field == "coreTemperatureC":
                label = "Core temperature"
                updated_point = replace(
                    operating_point, core_temperature_c=self._number(value, label)
                )
            else:
                self._session.set_status(
                    f"Unable to apply change: unsupported operating-point field: {field}"
                )
                return False
            updated_project = replace(project, operating_point=updated_point)
            preview_entries = self._build_preview(updated_project)
        except (GeometryModelError, ValueError) as error:
            self._session.set_status(f"Unable to apply change: {error}")
            return False
        self._preview_entries = preview_entries
        self._session.apply(updated_project)
        self._session.set_status(f"Updated {label.casefold()}")
        self.operatingPointChanged.emit()
        self.previewEntriesChanged.emit()
        return True
```

`OperatingPoint.__post_init__` already refuses a nonfinite or nonpositive
frequency, so the `ValueError` branch above is what turns that refusal into a
status message rather than a crash.

Extend `_winding_rows` with the five new keys:

```python
                "mode": winding.mode.value,
                "clearanceMm": winding.min_clearance_m * 1000.0,
                "terminalIntent": winding.terminal_intent,
                "dcCurrentA": points_by_id[winding.winding_id].dc_current_a,
                "currentDirection": points_by_id[
                    winding.winding_id
                ].current_direction.value,
```

Extend `_updated_winding`:

```python
        if field == "label":
            return replace(winding, label=value.strip())
        if field == "mode":
            return replace(winding, mode=ConductorMode(value))
        if field == "clearanceMm":
            return replace(
                winding, min_clearance_m=cls._number(value, "Clearance") / 1000.0
            )
        if field == "terminalIntent":
            return replace(winding, terminal_intent=value.strip())
```

Extend `_updated_operating_point`:

```python
        if field == "dcCurrentA":
            return replace(
                operating_point, dc_current_a=cls._number(value, "DC current")
            )
        if field == "currentDirection":
            return replace(operating_point, current_direction=CurrentDirection(value))
```

and widen the routing set in `setWindingField`:

```python
            if field in {"acRmsCurrentA", "acPhaseDeg", "dcCurrentA", "currentDirection"}:
```

`WindingOperatingPoint.__post_init__` refuses a negative DC current, and
`ConductorMode("bogus")` raises `ValueError`, so both land in the existing
`except (GeometryModelError, StopIteration, ValueError)` handler. Emit
`operatingPointChanged` from `refresh()` as well.

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/ui/test_guided_studio_controller.py -q`
Expected: PASS.

- [ ] **Step 5: Run the gates and commit**

```bash
git add src/inductor_designer/ui/guided_studio_controller.py tests/ui/test_guided_studio_controller.py
git commit -m "feat(ui): edit the shared operating point and every winding input"
```

---

### Task 6: Add and remove windings

**Files:**
- Modify: `src/inductor_designer/ui/guided_studio_controller.py`
- Test: `tests/ui/test_guided_studio_controller.py`

**Interfaces:**
- Produces on `GuidedStudioController`: slots `addWinding() -> bool` and
  `removeWinding(winding_id: str) -> bool`.

- [ ] **Step 1: Write the failing test**

Append to `tests/ui/test_guided_studio_controller.py`:

```python
def test_adding_a_winding_allocates_a_definition_and_an_excitation() -> None:
    QGuiApplication.instance() or QGuiApplication([])
    session = ProjectSession(make_project())
    controller = GuidedStudioController(session, CATALOG)

    assert controller.addWinding() is True

    design = session.project.design
    excitations = session.project.operating_point.windings
    assert [item.winding_id for item in design.windings] == ["w1", "w2"]
    assert [item.winding_id for item in excitations] == ["w1", "w2"]
    added = design.windings[1]
    assert added.conductor_name == design.windings[0].conductor_name
    assert added.mode is design.windings[0].mode
    assert added.turns == 1
    assert excitations[1].ac_rms_current_a == 0.0
    assert excitations[1].dc_current_a == 0.0
    assert controller.selectedWindingId == "w2"
    assert len(controller.previewEntries) == 3


def test_a_new_winding_does_not_overlap_an_existing_sector() -> None:
    QGuiApplication.instance() or QGuiApplication([])
    session = ProjectSession(make_project())
    controller = GuidedStudioController(session, CATALOG)

    assert controller.addWinding() is True

    first, second = session.project.design.windings
    assert second.start_angle_deg >= first.start_angle_deg + first.sector_deg
    assert second.start_angle_deg + second.sector_deg <= 360.0


def test_a_full_core_refuses_another_winding() -> None:
    QGuiApplication.instance() or QGuiApplication([])
    full = make_winding(start_angle_deg=0.0, sector_deg=360.0)
    project = make_project(design=replace(make_project().design, windings=(full,)))
    controller = GuidedStudioController(ProjectSession(project), CATALOG)

    assert controller.addWinding() is False

    assert "no free sector" in controller.statusMessage


def test_removing_a_winding_drops_its_excitation_too() -> None:
    QGuiApplication.instance() or QGuiApplication([])
    session = ProjectSession(make_project())
    controller = GuidedStudioController(session, CATALOG)
    assert controller.addWinding() is True

    assert controller.removeWinding("w2") is True

    assert [item.winding_id for item in session.project.design.windings] == ["w1"]
    assert [
        item.winding_id for item in session.project.operating_point.windings
    ] == ["w1"]
    assert controller.selectedWindingId == "w1"


def test_the_last_winding_cannot_be_removed() -> None:
    QGuiApplication.instance() or QGuiApplication([])
    session = ProjectSession(make_project())
    controller = GuidedStudioController(session, CATALOG)

    assert controller.removeWinding("w1") is False

    assert len(session.project.design.windings) == 1
    assert "last winding" in controller.statusMessage


def test_removing_an_unknown_winding_changes_nothing() -> None:
    QGuiApplication.instance() or QGuiApplication([])
    session = ProjectSession(make_project())
    controller = GuidedStudioController(session, CATALOG)

    assert controller.removeWinding("w9") is False
    assert len(session.project.design.windings) == 1
```

Add `make_winding` and `replace` to the test module's imports.

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/ui/test_guided_studio_controller.py -q -k winding`
Expected: FAIL with `AttributeError: ... 'addWinding'`.

- [ ] **Step 3: Implement both slots**

In `src/inductor_designer/ui/guided_studio_controller.py`:

```python
    _MINIMUM_NEW_SECTOR_DEG = 10.0
    _PREFERRED_NEW_SECTOR_DEG = 90.0

    def _next_winding_id(self) -> str:
        taken = {winding.winding_id for winding in self._session.project.design.windings}
        index = len(taken) + 1
        while f"w{index}" in taken:
            index += 1
        return f"w{index}"

    def _free_sector(self) -> tuple[float, float] | None:
        """The first gap after the last occupied sector, in degrees.

        Sectors must not overlap (`domain/validation.py`), so a new winding is
        placed after the existing ones rather than on top of them. Returns None
        when the remaining gap is too small to be useful.
        """
        windings = self._session.project.design.windings
        occupied_end = max(
            (winding.start_angle_deg + winding.sector_deg for winding in windings),
            default=0.0,
        )
        if occupied_end >= 360.0 - self._MINIMUM_NEW_SECTOR_DEG:
            return None
        return (occupied_end, min(self._PREFERRED_NEW_SECTOR_DEG, 360.0 - occupied_end))

    @Slot(result=bool)
    def addWinding(self) -> bool:
        project = self._session.project
        windings = project.design.windings
        if not windings:
            self._session.set_status(
                "Unable to add a winding: the project has no winding to copy "
                "placement defaults from."
            )
            return False
        placement = self._free_sector()
        if placement is None:
            self._session.set_status(
                "Unable to add a winding: no free sector remains on the core. "
                "Reduce an existing winding's sector first."
            )
            return False
        start_deg, sector_deg = placement
        template = windings[-1]
        winding_id = self._next_winding_id()
        definition = replace(
            template,
            winding_id=winding_id,
            label=f"Winding {len(windings) + 1}",
            turns=1,
            start_angle_deg=start_deg,
            sector_deg=sector_deg,
            terminal_intent="",
        )
        excitation = WindingOperatingPoint(
            winding_id=winding_id,
            ac_rms_current_a=0.0,
            ac_phase_deg=0.0,
            dc_current_a=0.0,
            current_direction=CurrentDirection.FORWARD,
        )
        updated_project = replace(
            project,
            design=replace(project.design, windings=(*windings, definition)),
            operating_point=replace(
                project.operating_point,
                windings=(*project.operating_point.windings, excitation),
            ),
        )
        try:
            preview_entries = self._build_preview(updated_project)
        except GeometryModelError as error:
            self._session.set_status(f"Unable to add a winding: {error}")
            return False
        self._preview_entries = preview_entries
        self._session.apply(updated_project)
        self._session.set_status(f"Added {winding_id}")
        self._windings = self._winding_rows(
            updated_project.design.windings, updated_project.operating_point.windings
        )
        self._selected_winding_id = winding_id
        self.windingsChanged.emit()
        self.previewEntriesChanged.emit()
        self.selectedWindingIdChanged.emit()
        return True

    @Slot(str, result=bool)
    def removeWinding(self, winding_id: str) -> bool:
        project = self._session.project
        windings = project.design.windings
        if winding_id not in {winding.winding_id for winding in windings}:
            self._session.set_status(
                f"Unable to remove: unknown winding {winding_id}"
            )
            return False
        if len(windings) == 1:
            self._session.set_status(
                "Unable to remove the last winding: a design needs at least one."
            )
            return False
        updated_project = replace(
            project,
            design=replace(
                project.design,
                windings=tuple(
                    winding for winding in windings if winding.winding_id != winding_id
                ),
            ),
            operating_point=replace(
                project.operating_point,
                windings=tuple(
                    item
                    for item in project.operating_point.windings
                    if item.winding_id != winding_id
                ),
            ),
        )
        try:
            preview_entries = self._build_preview(updated_project)
        except GeometryModelError as error:
            self._session.set_status(f"Unable to remove {winding_id}: {error}")
            return False
        self._preview_entries = preview_entries
        self._session.apply(updated_project)
        self._session.set_status(f"Removed {winding_id}")
        self._windings = self._winding_rows(
            updated_project.design.windings, updated_project.operating_point.windings
        )
        self._selected_winding_id = updated_project.design.windings[0].winding_id
        self.windingsChanged.emit()
        self.previewEntriesChanged.emit()
        self.selectedWindingIdChanged.emit()
        return True
```

Import `WindingOperatingPoint` and `CurrentDirection` at runtime (they are
currently under `TYPE_CHECKING`, and both are now constructed).

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/ui/test_guided_studio_controller.py -q`
Expected: PASS.

- [ ] **Step 5: Run the gates and commit**

```bash
git add src/inductor_designer/ui/guided_studio_controller.py tests/ui/test_guided_studio_controller.py
git commit -m "feat(ui): add and remove windings with their excitations"
```

---

### Task 7: The Core & Material controller

**Files:**
- Create: `src/inductor_designer/ui/core_material_controller.py`
- Test: `tests/ui/test_core_material_controller.py`

**Interfaces:**
- Consumes: `ProjectSession` (Task 4), every function from
  `core_material_selection.py` (Task 3), `CatalogRepository`,
  `MaterialRepository`, `MaterialSelectionError`.
- Produces: `CoreMaterialController(QObject)` with properties `coreOptions:
  list`, `materialOptions: list`, `selectedCore: dict`, `selectedMaterial:
  dict`, `acknowledgementRequired: bool`, `acknowledged: bool`, `message: str`;
  signals `optionsChanged`, `selectionChanged`, `messageChanged`,
  `materialStudioRequested`; slots `selectCatalogCore(part_number) -> bool`,
  `applyManualCore(outer_mm, inner_mm, height_mm, corner_mm) -> bool`,
  `selectMaterial(manufacturer, name, grade, revision_id, bh_series_id) -> bool`,
  `clearMaterial() -> bool`, `setAcknowledged(bool) -> bool`,
  `openMaterialStudio()`, `refreshLibrary()`.

Millimetres cross the QML boundary for manual dimensions because every other
length in the UI is millimetres; the controller converts to metres exactly once.

- [ ] **Step 1: Write the failing test**

Create `tests/ui/test_core_material_controller.py`:

```python
from __future__ import annotations

import os
from dataclasses import replace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtGui import QGuiApplication  # noqa: E402

from inductor_designer.domain.project import (  # noqa: E402
    CatalogCoreSelection,
    ManualCoreSelection,
)
from inductor_designer.ui.core_material_controller import (  # noqa: E402
    CoreMaterialController,
)
from inductor_designer.ui.project_session import ProjectSession  # noqa: E402
from tests.fakes.material_repository import InMemoryMaterialRepository  # noqa: E402
from tests.unit.application.test_geometry_model import CATALOG  # noqa: E402
from tests.unit.domain.test_catalog_records import make_core  # noqa: E402
from tests.unit.domain.test_project import (  # noqa: E402
    make_material_record,
    make_project,
)

pytestmark = pytest.mark.ui


def build(project=None) -> tuple[ProjectSession, CoreMaterialController]:
    QGuiApplication.instance() or QGuiApplication([])
    repository = InMemoryMaterialRepository()
    record = make_material_record()
    repository.save(record, {})
    base = project if project is not None else make_project(
        design=replace(make_project().design, core=None, core_material=None)
    )
    session = ProjectSession(base)
    return session, CoreMaterialController(session, CATALOG, repository)


def test_both_lists_start_unfiltered() -> None:
    _, controller = build()

    assert [row["partNumber"] for row in controller.coreOptions] == [
        make_core().part_number
    ]
    assert [row["revisionId"] for row in controller.materialOptions] == [
        make_material_record().revision_id
    ]
    assert controller.selectedCore == {}
    assert controller.selectedMaterial == {}


def test_selecting_a_core_filters_the_material_list_and_publishes_the_project() -> None:
    session, controller = build()
    record = make_core()

    assert controller.selectCatalogCore(record.part_number) is True

    assert isinstance(session.project.design.core, CatalogCoreSelection)
    assert controller.selectedCore["partNumber"] == record.part_number
    assert all(
        row["manufacturer"] == record.material.manufacturer
        for row in controller.materialOptions
    )
    assert session.dirty is True


def test_selecting_a_material_filters_the_core_list() -> None:
    _, controller = build()
    record = make_material_record()

    assert (
        controller.selectMaterial(
            record.ref.manufacturer,
            record.ref.name,
            record.ref.grade,
            record.revision_id,
            "",
        )
        is True
    )

    assert controller.selectedMaterial["revisionId"] == record.revision_id
    assert [row["partNumber"] for row in controller.coreOptions] == [
        make_core().part_number
    ]


def test_a_manual_core_requires_and_records_acknowledgement() -> None:
    session, controller = build()
    record = make_material_record()

    assert controller.applyManualCore(27.2, 13.8, 11.2, 0.0) is True
    assert isinstance(session.project.design.core, ManualCoreSelection)
    assert session.project.design.core.outer_diameter_m == 0.0272
    assert controller.acknowledgementRequired is True
    assert controller.acknowledged is False

    assert controller.setAcknowledged(True) is True
    assert (
        controller.selectMaterial(
            record.ref.manufacturer,
            record.ref.name,
            record.ref.grade,
            record.revision_id,
            "",
        )
        is True
    )

    assert session.project.design.manual_material_compatibility_acknowledged is True


def test_switching_from_a_manual_core_drops_the_acknowledgement() -> None:
    approved = make_material_record()
    repository = repository_with(approved)
    project = make_project(
        design=replace(
            make_project().design,
            core=ManualCoreSelection(0.0272, 0.0138, 0.0112, 0.0),
            core_material=None,
        )
    )
    acknowledged = apply_material_revision(
        project,
        repository,
        approved.ref,
        approved.revision_id,
        bh_series_id=None,
        acknowledge_manual_compatibility=True,
    ).project
    assert acknowledged.design.manual_material_compatibility_acknowledged is True

    # The catalog core is compatible with the pinned material, so nothing is
    # cleared -- but the acknowledgment still must not survive onto it.
    outcome = apply_catalog_core(acknowledged, CATALOG, make_core().part_number)

    assert outcome.cleared is None
    assert outcome.project.design.core_material is not None
    assert outcome.project.design.manual_material_compatibility_acknowledged is False


def test_a_catalog_core_needs_no_acknowledgement() -> None:
    _, controller = build()

    assert controller.selectCatalogCore(make_core().part_number) is True

    assert controller.acknowledgementRequired is False


def test_an_unselectable_revision_is_reported_not_raised() -> None:
    QGuiApplication.instance() or QGuiApplication([])
    repository = InMemoryMaterialRepository()
    record = make_material_record()
    repository.save(record, {})
    session = ProjectSession(
        make_project(design=replace(make_project().design, core=None, core_material=None))
    )
    controller = CoreMaterialController(session, CATALOG, repository)

    assert (
        controller.selectMaterial(
            record.ref.manufacturer, record.ref.name, record.ref.grade, "missing", ""
        )
        is False
    )

    assert session.project.design.core_material is None
    assert "missing" in controller.message


def test_clearing_the_material_leaves_the_core_alone() -> None:
    session, controller = build()
    record = make_material_record()
    controller.selectCatalogCore(make_core().part_number)
    controller.selectMaterial(
        record.ref.manufacturer,
        record.ref.name,
        record.ref.grade,
        record.revision_id,
        "",
    )

    assert controller.clearMaterial() is True

    assert session.project.design.core_material is None
    assert session.project.design.core is not None
    assert controller.selectedMaterial == {}


def test_a_library_refresh_keeps_a_still_valid_pinned_revision() -> None:
    session, controller = build()
    record = make_material_record()
    controller.selectMaterial(
        record.ref.manufacturer,
        record.ref.name,
        record.ref.grade,
        record.revision_id,
        "",
    )
    pinned = session.project.design.core_material

    controller.refreshLibrary()

    assert session.project.design.core_material == pinned
    assert "unchanged" in controller.message


def test_a_library_refresh_unresolves_a_deleted_pinned_revision() -> None:
    QGuiApplication.instance() or QGuiApplication([])
    repository = InMemoryMaterialRepository()
    record = make_material_record()
    repository.save(record, {})
    session = ProjectSession(
        make_project(design=replace(make_project().design, core=None, core_material=None))
    )
    controller = CoreMaterialController(session, CATALOG, repository)
    controller.selectMaterial(
        record.ref.manufacturer,
        record.ref.name,
        record.ref.grade,
        record.revision_id,
        "",
    )
    repository.delete_revision(record.ref, record.revision_id)

    controller.refreshLibrary()

    assert session.project.design.core_material is None
    assert record.revision_id in controller.message
    assert controller.materialOptions == []


def test_a_blank_material_identity_is_refused_without_raising() -> None:
    """An unset ComboBox sends blanks; a slot must report, never raise."""
    _, controller = build()

    assert controller.selectMaterial("", "", "", "0123456789ab", "") is False

    assert "Unable to select material revision" in controller.message


def test_resizing_a_manual_core_drops_the_acknowledgement() -> None:
    session, controller = build()
    record = make_material_record()
    controller.applyManualCore(27.2, 13.8, 11.2, 0.0)
    controller.setAcknowledged(True)
    controller.selectMaterial(
        record.ref.manufacturer,
        record.ref.name,
        record.ref.grade,
        record.revision_id,
        "",
    )
    assert session.project.design.manual_material_compatibility_acknowledged is True

    controller.applyManualCore(30.0, 15.0, 12.0, 0.0)

    assert controller.acknowledged is False
    # The project field is what exports and run manifests read.
    assert session.project.design.manual_material_compatibility_acknowledged is False
    assert "Confirm material compatibility again" in controller.message


def test_a_corrupt_material_library_is_reported_not_raised() -> None:
    """The overlay repository raises plain ValueError on a sha256 mismatch."""
    session, controller = build()
    record = make_material_record()
    controller.selectMaterial(
        record.ref.manufacturer,
        record.ref.name,
        record.ref.grade,
        record.revision_id,
        "",
    )

    class Corrupt:
        def list_materials(self) -> tuple[MaterialRef, ...]:
            return (record.ref,)

        def list_revisions(self, ref: MaterialRef) -> tuple[str, ...]:
            return (record.revision_id,)

        def get(self, ref: MaterialRef, revision_id: str) -> MaterialRecord:
            raise ValueError("sha256 mismatch for source curve.csv")

    controller._materials = Corrupt()  # type: ignore[assignment]

    controller.refreshLibrary()

    assert "Unable to reload the material library" in controller.message
    assert "sha256 mismatch" in controller.message
    assert session.project.design.core_material is not None


def test_opening_material_studio_only_emits_a_request() -> None:
    _, controller = build()
    requests: list[int] = []
    controller.materialStudioRequested.connect(lambda: requests.append(1))

    controller.openMaterialStudio()

    assert requests == [1]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/ui/test_core_material_controller.py -q`
Expected: FAIL with `ModuleNotFoundError` for
`inductor_designer.ui.core_material_controller`.

- [ ] **Step 3: Write the controller**

Create `src/inductor_designer/ui/core_material_controller.py`:

```python
"""The `Core & Material` screen (specification section 4.1).

The controller owns no rules: it converts the session project into QML rows and
routes every change through `core_material_selection`, so the filtering and the
never-substituting clear stay testable without Qt.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Property, QObject, Signal, Slot

from inductor_designer.application.services.core_material_selection import (
    SelectionOutcome,
    apply_catalog_core,
    apply_manual_core,
    apply_material_revision,
    clear_material_selection,
    core_options,
    material_options,
    required_material_ref,
    revalidate_pinned_material,
)
from inductor_designer.application.services.material_selection import (
    MaterialSelectionError,
)
from inductor_designer.domain.project import (
    CatalogCoreSelection,
    ManualCoreSelection,
)
from inductor_designer.materials.identity import MaterialRef

if TYPE_CHECKING:
    from inductor_designer.application.ports.catalog import CatalogRepository
    from inductor_designer.application.ports.material_repository import (
        MaterialRepository,
    )
    from inductor_designer.ui.project_session import ProjectSession


class CoreMaterialController(QObject):
    optionsChanged = Signal()
    selectionChanged = Signal()
    messageChanged = Signal()
    materialStudioRequested = Signal()

    def __init__(
        self,
        session: ProjectSession,
        catalog: CatalogRepository,
        materials: MaterialRepository,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._session = session
        self._catalog = catalog
        self._materials = materials
        self._message = ""
        self._acknowledged = (
            session.project.design.manual_material_compatibility_acknowledged
        )

    def _get_core_options(self) -> list[dict[str, object]]:
        pinned = self._session.project.design.core_material
        options = core_options(self._catalog, pinned.ref if pinned else None)
        return [
            {
                "partNumber": option.part_number,
                "manufacturer": option.manufacturer,
                "family": option.family.value,
                "materialLabel": (
                    f"{option.material_ref.manufacturer} {option.material_ref.name} "
                    f"{option.material_ref.grade}"
                ),
                "outerDiameterMm": option.outer_diameter_m * 1000.0,
                "innerDiameterMm": option.inner_diameter_m * 1000.0,
                "heightMm": option.height_m * 1000.0,
            }
            for option in options
        ]

    coreOptions = Property(list, _get_core_options, notify=optionsChanged)

    def _get_material_options(self) -> list[dict[str, object]]:
        options = material_options(
            self._materials, required_material_ref(self._session.project)
        )
        return [
            {
                "manufacturer": option.ref.manufacturer,
                "name": option.ref.name,
                "grade": option.ref.grade,
                "revisionId": option.revision_id,
                "status": option.status.value,
                "createdAt": option.created_at,
                "bhSeriesIds": list(option.bh_series_ids),
            }
            for option in options
        ]

    materialOptions = Property(list, _get_material_options, notify=optionsChanged)

    def _get_selected_core(self) -> dict[str, object]:
        core = self._session.project.design.core
        if isinstance(core, CatalogCoreSelection):
            return {
                "kind": "catalog",
                "partNumber": core.part_number,
                "manufacturer": core.snapshot.manufacturer,
                "materialLabel": (
                    f"{core.snapshot.material.manufacturer} "
                    f"{core.snapshot.material.name} {core.snapshot.material.grade}"
                ),
                "outerDiameterMm": core.snapshot.outer_diameter.nominal_m * 1000.0,
                "innerDiameterMm": core.snapshot.inner_diameter.nominal_m * 1000.0,
                "heightMm": core.snapshot.height.nominal_m * 1000.0,
                "pathLengthMm": core.snapshot.path_length_m * 1000.0,
            }
        if isinstance(core, ManualCoreSelection):
            return {
                "kind": "manual",
                "outerDiameterMm": core.outer_diameter_m * 1000.0,
                "innerDiameterMm": core.inner_diameter_m * 1000.0,
                "heightMm": core.height_m * 1000.0,
                "cornerRadiusMm": core.corner_radius_m * 1000.0,
            }
        return {}

    selectedCore = Property(dict, _get_selected_core, notify=selectionChanged)

    def _get_selected_material(self) -> dict[str, object]:
        material = self._session.project.design.core_material
        if material is None:
            return {}
        return {
            "manufacturer": material.ref.manufacturer,
            "name": material.ref.name,
            "grade": material.ref.grade,
            "revisionId": material.revision_id,
            "status": material.snapshot.status.value,
            "bhSeriesId": material.bh_series_id or "",
        }

    selectedMaterial = Property(dict, _get_selected_material, notify=selectionChanged)

    def _get_acknowledgement_required(self) -> bool:
        return isinstance(self._session.project.design.core, ManualCoreSelection)

    acknowledgementRequired = Property(
        bool, _get_acknowledgement_required, notify=selectionChanged
    )

    def _get_acknowledged(self) -> bool:
        return self._acknowledged

    acknowledged = Property(bool, _get_acknowledged, notify=selectionChanged)

    def _get_message(self) -> str:
        return self._message

    message = Property(str, _get_message, notify=messageChanged)

    def _set_message(self, message: str) -> None:
        self._message = message
        self.messageChanged.emit()

    def _publish(self, outcome: SelectionOutcome) -> bool:
        self._session.apply(outcome.project)
        self._session.set_status(outcome.message)
        if outcome.cleared is ClearedSelection.MATERIAL:
            self._acknowledged = False
        self._set_message(outcome.message)
        self.optionsChanged.emit()
        self.selectionChanged.emit()
        return True

    @Slot(str, result=bool)
    def selectCatalogCore(self, part_number: str) -> bool:
        try:
            outcome = apply_catalog_core(
                self._session.project, self._catalog, part_number
            )
        except Exception as error:  # noqa: BLE001 - a QML slot must never raise
            # The catalog is a SQLite file: a locked or corrupt index raises
            # from the driver, not as a LookupError.
            self._set_message(f"Unable to select core: {error}")
            return False
        self._acknowledged = False
        return self._publish(outcome)

    @Slot(float, float, float, float, result=bool)
    def applyManualCore(
        self,
        outer_diameter_mm: float,
        inner_diameter_mm: float,
        height_mm: float,
        corner_radius_mm: float,
    ) -> bool:
        # New dimensions are new geometry, so a compatibility attestation the
        # user made about the previous shape must not carry over.
        self._acknowledged = False
        try:
            outcome = apply_manual_core(
                self._session.project,
                outer_diameter_m=outer_diameter_mm / 1000.0,
                inner_diameter_m=inner_diameter_mm / 1000.0,
                height_m=height_mm / 1000.0,
                corner_radius_m=corner_radius_mm / 1000.0,
            )
        except ValueError as error:
            # `ManualCoreSelection` refuses non-finite and non-positive
            # dimensions, and QML `Number("")` yields NaN.
            self._set_message(f"Unable to apply manual core dimensions: {error}")
            return False
        return self._publish(outcome)

    @Slot(str, str, str, str, str, result=bool)
    def selectMaterial(
        self,
        manufacturer: str,
        name: str,
        grade: str,
        revision_id: str,
        bh_series_id: str,
    ) -> bool:
        try:
            # MaterialRef refuses a blank field, and an unset ComboBox sends
            # blanks: construct it inside the guard so no slot ever raises.
            ref = MaterialRef(manufacturer, name, grade)
            outcome = apply_material_revision(
                self._session.project,
                self._materials,
                ref,
                revision_id,
                bh_series_id=bh_series_id.strip() or None,
                acknowledge_manual_compatibility=self._acknowledged,
            )
        except (KeyError, MaterialSelectionError, ValueError) as error:
            # KeyError covers MaterialLookupError, ValueError a blank identity;
            # a missing or unselectable revision is reported, never
            # auto-substituted.
            issues = getattr(error, "issues", None)
            detail = "; ".join(issues) if issues else str(error)
            self._set_message(
                f"Unable to select material revision {revision_id}: {detail}"
            )
            return False
        return self._publish(outcome)

    @Slot(result=bool)
    def clearMaterial(self) -> bool:
        outcome = clear_material_selection(self._session.project)
        if outcome.cleared is None:
            self._set_message(outcome.message)
            return False
        self._acknowledged = False
        return self._publish(outcome)

    @Slot(bool, result=bool)
    def setAcknowledged(self, acknowledged: bool) -> bool:
        """Record the Manual-core compatibility assumption before it is used.

        The value only reaches the project when a material is pinned, because
        `Design.manual_material_compatibility_acknowledged` describes exactly
        that pairing.
        """
        self._acknowledged = acknowledged
        self.selectionChanged.emit()
        return True

    @Slot()
    def openMaterialStudio(self) -> None:
        self.materialStudioRequested.emit()

    @Slot()
    def refreshLibrary(self) -> None:
        """Re-read the library after the Material Studio window closed."""
        try:
            outcome = revalidate_pinned_material(
                self._session.project, self._materials
            )
        except Exception as error:  # noqa: BLE001 - a QML slot must never raise
            # The overlay repository verifies sha256 and re-parses sources, so a
            # corrupt or half-written record raises a plain ValueError.
            self._set_message(f"Unable to reload the material library: {error}")
            return
        if outcome.cleared is None:
            self._session.set_status(outcome.message)
            self._set_message(outcome.message)
            self.optionsChanged.emit()
            self.selectionChanged.emit()
            return
        self._publish(outcome)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/ui/test_core_material_controller.py -q`
Expected: PASS, 14 tests.

- [ ] **Step 5: Run the gates and commit**

```bash
git add src/inductor_designer/ui/core_material_controller.py tests/ui/test_core_material_controller.py
git commit -m "feat(ui): pair a core and an exact material revision"
```

---

### Task 8: Retire Material Studio's project writer

`Core & Material` now owns pinning, so `MaterialStudioController.useInProject`
is a second writer for the same field. Two writers is exactly the divergence
Task 4 exists to prevent, and Material Studio's copy of the project goes stale
the moment the Core & Material screen edits it. Delete the writer and move its
coverage onto the owner.

This task must run after Task 7 (the replacement exists) and before Task 12 (the
window moves), and it changes one behavior deliberately: pinning a revision no
longer writes `*.inductor.json` on the spot. It updates the session, and the
user saves — the same rule the run gate depends on.

**Files:**
- Modify: `src/inductor_designer/ui/material_studio_controller.py:85-98`, `:227-240`,
  `:1331-1351`
- Modify: `src/inductor_designer/ui/qml/MaterialStudioPage.qml:351-383`
- Modify: `src/inductor_designer/ui/main.py` (`MaterialStudioController(...)` call)
- Modify: `tests/integration/test_material_studio_exit.py`
- Modify: `tests/ui/test_material_studio_controller.py:203`, `:346`
- Modify: `tests/ui/test_qml_smoke.py:113-114`, `:183-184`

**Interfaces:**
- Removes: `MaterialStudioController.__init__` parameters `project` and
  `project_save_callback`; properties `canUseInProject` and `hasProject`; slot
  `useInProject`.
- Adds in their place ONE read-only awareness parameter,
  `pinned_revision: Callable[[], MaterialRevisionSelection | None] | None = None`,
  so the signature becomes
  `MaterialStudioController(repository, *, pinned_revision=None, now=..., parent=...)`.
  Material Studio still must not delete or replace away a revision the project
  pins (specification section 9), and `replaceSelectedMaterial` and
  `deleteSelectedMaterial` are the only readers. A live callable, not a
  snapshot: it reads the session on every call, so it can never go stale.
- Removes from QML: `projectBhSeriesChoice`, `selectForSimulationButton`, and the
  "Load a project to select this revision for simulation." label.
- Unchanged: every import, export, replace, download, and delete path in
  Material Studio.

- [ ] **Step 1: Move the exit-criterion coverage onto the owner**

`tests/integration/test_material_studio_exit.py` is an accepted M5 exit
criterion and its assertions must all survive — pinning an imported revision,
refusing a revision with multiple B-H series, leaving the document untouched when
persistence fails, and generating from the pinned revision in the same session.
Rewrite only the mechanism.

Replace the controller construction and the `CurrentProjectProvider` with the
session plus the new controller:

```python
    session = ProjectSession(
        projects.load(project_path),
        project_path,
        lambda project: projects.save(project, project_path),
    )
    controller = MaterialStudioController(
        materials,
        pinned_revision=lambda: session.project.design.core_material,
        now=lambda: "2026-07-19T12:00:00+00:00",
    )
    core_material = CoreMaterialController(session, CATALOG, materials)
```

The `pinned_revision` provider is what keeps this test's

```python
    assert materials.get(base_record.ref, base_revision) == base_record
```

assertion alive: `replaceSelectedMaterial` must not prune the revision the
project currently pins.

Then replace each `controller.useInProject(<series>)` with a pin through the
owner followed by an explicit save, keeping the surrounding assertions:

```python
    assert core_material.selectMaterial(
        ref.manufacturer, ref.name, ref.grade, base_revision, "bh-25c"
    )
    assert session.saveProject() is True
```

The three behavior checks map as follows, and each keeps its original assertion:

- multiple B-H series without an explicit choice:

```python
    before_pin = project_path.read_bytes()

    assert (
        core_material.selectMaterial(
            ref.manufacturer, ref.name, ref.grade, edited_revision, ""
        )
        is False
    )

    assert "multiple B-H series" in core_material.message
    assert project_path.read_bytes() == before_pin
    assert session.project.design.core_material is None or (
        session.project.design.core_material.revision_id != edited_revision
    )
```

- persistence failure leaves the document and the session's saved state alone
  (the `monkeypatch` of `project_module.os.replace` is unchanged; only the call
  that triggers the write moves):

```python
    assert core_material.selectMaterial(
        ref.manufacturer, ref.name, ref.grade, edited_revision, "bh-100c"
    )

    assert session.saveProject() is False
    assert "replace failed" in session.statusMessage
    assert project_path.read_bytes() == before_pin
    assert session.dirty is True
```

- the successful pin persists schema v5 with the chosen series (unchanged
  assertions, now after an explicit `saveProject()`), and the same-session
  `run_generation` call reads `session.project`.

Do not delete an assertion to make the rewrite easier. If one cannot be
expressed through the owner, stop and report it — that is a real coverage loss
and Fabio Posser decides, not the implementer.

- [ ] **Step 2: Run the rewritten test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/integration/test_material_studio_exit.py -q`
Expected: FAIL with `TypeError: __init__() got an unexpected keyword argument`
only after Step 4; before that it fails on the still-present `project=` keyword
being required by the old assertions. Either failure is the red state — read the
message and continue.

- [ ] **Step 3: Delete the two other test callers**

In `tests/ui/test_material_studio_controller.py`, the two `useInProject` calls
(and any `canUseInProject` / `hasProject` assertion around them) are now covered
by `tests/ui/test_core_material_controller.py`. Delete those assertions and, if a
test exists only to exercise them, delete the test. In `tests/ui/test_qml_smoke.py`,
delete `canUseInProject`, `hasProject`, and the `useInProject` stub from the fake
controller.

- [ ] **Step 4: Delete the writer**

In `src/inductor_designer/ui/material_studio_controller.py`:

```python
    def __init__(
        self,
        repository: MaterialRepository,
        *,
        pinned_revision: Callable[[], MaterialRevisionSelection | None] | None = None,
        now: Callable[[], str] = _utc_now,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._repository = repository
        self._pinned_revision = pinned_revision
        self._now = now
```

Delete `self._project`, `self._project_save_callback`, `_get_can_use_in_project`,
`canUseInProject`, `_get_has_project`, `hasProject`, and the whole
`useInProject` slot. Then delete the now-unused imports (`InductorProject`,
`pin_material_revision`) — Ruff will name them. `MaterialStatus` and
`MaterialRevisionSelection` both stay.

Keep both pinned-revision guards, reading through the callable instead of the
deleted project copy. In `replaceSelectedMaterial` and in
`deleteSelectedMaterial`, replace

```python
            selection = (
                None if self._project is None else self._project.design.core_material
            )
```

with

```python
            selection = (
                None if self._pinned_revision is None else self._pinned_revision()
            )
```

and leave the `pinned` computation and everything after it untouched. This is
specification section 9: material deletion or replacement cannot silently alter
a pinned revision. Deleting these guards would drop an accepted M5 exit
criterion, so they are not optional.

- [ ] **Step 5: Delete the QML controls**

In `src/inductor_designer/ui/qml/MaterialStudioPage.qml`, delete the
`projectBhSeriesChoice` `ComboBox`, the `selectForSimulationButton` `Button`, and
the "Load a project to select this revision for simulation." `Label`. Leave
`bhSeriesOptions` in place only if another control still reads it; otherwise
delete that property too.

In `src/inductor_designer/ui/main.py`, the call becomes

```python
    material_studio_controller = MaterialStudioController(
        material_repository,
        pinned_revision=(
            lambda: session.project.design.core_material if session is not None else None
        ),
    )
```

using the same repository instance the `CoreMaterialController` gets, so a
material imported in the window is visible to the selector without a restart.

- [ ] **Step 6: Run every gate**

Run: `.venv/Scripts/python.exe -m pytest tests -q -m "not aedt and not femm"`,
then `-m "ui"`, then ruff, mypy, and `check_architecture`.
Expected: all clean, with the material-studio test count lower by however many
tests Step 3 removed. Record the numbers.

- [ ] **Step 7: Commit**

```bash
git add src/inductor_designer/ui tests
git commit -m "refactor(ui): let only the Core & Material screen pin a material revision"
```

---

### Task 9: Preliminary rows in engineering units

**Files:**
- Create: `src/inductor_designer/ui/preliminary_rows.py`
- Test: `tests/unit/ui/test_preliminary_rows.py`

`tests/unit/ui/` does not exist yet. Create it with an empty `__init__.py`, like
every other package under `tests/unit/`.

**Interfaces:**
- Consumes: `PreliminaryResult`, `PreliminaryValue`, `ResultState`.
- Produces: `DisplayUnit` (fields `suffix: str`, `scale: float`,
  `decimals: int`), the constants `MILLITESLA`, `AMPERE_PER_SQUARE_MILLIMETRE`,
  `MILLIOHM`, `MILLIMETRE`, `SQUARE_MILLIMETRE`, `WATT`, and the functions
  `cell(value, unit) -> dict[str, object]`,
  `core_rows(result) -> list[dict[str, object]]`,
  `winding_rows(result) -> list[dict[str, object]]`,
  `total_rows(result) -> list[dict[str, object]]`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/ui/test_preliminary_rows.py`:

```python
"""No Qt import: every conversion and label is testable without a QGuiApplication."""

from __future__ import annotations

from inductor_designer.simulation.preliminary import (
    CorePreliminary,
    PreliminaryResult,
    PreliminaryTotals,
    WindingPreliminary,
)
from inductor_designer.simulation.preliminary_contracts import (
    DiagnosticCode,
    ResultState,
    estimated,
    unavailable,
)
from inductor_designer.ui.preliminary_rows import (
    MILLITESLA,
    cell,
    core_rows,
    total_rows,
    winding_rows,
)

REFUSED = unavailable(
    DiagnosticCode.CORE_LOSS_NO_LOSS_DATA_FOR_DC_BIAS,
    "Loss data does not cover the requested DC bias.",
)


def make_result() -> PreliminaryResult:
    return PreliminaryResult(
        core=CorePreliminary(
            b_dc=estimated(0.0847, ("odd symmetry assumed",)),
            b_min=estimated(-0.01),
            b_max=estimated(0.18),
            b_ac_peak=estimated(0.095),
            b_peak_magnitude=estimated(0.18),
            core_loss=REFUSED,
        ),
        windings=(
            WindingPreliminary(
                winding_id="w1",
                conductor_area=estimated(8.2258e-7),
                j_ac_rms=estimated(2.4313e6),
                j_ac_peak=estimated(3.4384e6),
                j_dc=estimated(6.0784e6),
                wire_length=estimated(0.4),
                resistance=estimated(0.008379),
                wire_loss=estimated(0.243),
            ),
        ),
        totals=PreliminaryTotals(
            total_wire_loss=estimated(0.243), core_loss=REFUSED, total_loss=REFUSED
        ),
        material_revision_id="rev-1",
        bh_series_id=None,
        notes=("odd symmetry assumed",),
    )


def test_an_estimated_cell_is_scaled_rounded_and_suffixed() -> None:
    row = cell(estimated(0.0847), MILLITESLA)

    assert row["state"] == ResultState.ESTIMATED.value
    assert row["text"] == "84.700 mT"
    assert row["code"] == ""
    assert row["message"] == ""


def test_a_negative_estimate_keeps_its_sign() -> None:
    assert cell(estimated(-0.01), MILLITESLA)["text"] == "-10.000 mT"


def test_an_unavailable_cell_shows_the_state_with_its_code_and_message() -> None:
    row = cell(REFUSED, MILLITESLA)

    assert row["state"] == ResultState.UNAVAILABLE.value
    assert row["text"] == "Unavailable"
    assert row["code"] == DiagnosticCode.CORE_LOSS_NO_LOSS_DATA_FOR_DC_BIAS
    assert row["message"] == "Loss data does not cover the requested DC bias."


def test_notes_travel_with_the_cell() -> None:
    assert cell(estimated(0.1, ("linear permeability approximation",)), MILLITESLA)[
        "notes"
    ] == ["linear permeability approximation"]


def test_core_rows_cover_the_specified_core_summary() -> None:
    rows = core_rows(make_result())

    assert [row["label"] for row in rows] == [
        "DC flux density",
        "AC flux-density swing",
        "Minimum flux density",
        "Maximum flux density",
        "Peak flux-density magnitude",
        "Core loss",
    ]
    assert rows[0]["text"] == "84.700 mT"
    assert rows[5]["state"] == ResultState.UNAVAILABLE.value


def test_winding_rows_cover_every_specified_winding_quantity() -> None:
    rows = winding_rows(make_result())

    assert len(rows) == 1
    row = rows[0]
    assert row["windingId"] == "w1"
    assert row["conductorArea"]["text"] == "0.8226 mm²"
    assert row["jAcRms"]["text"] == "2.431 A/mm²"
    assert row["jAcPeak"]["text"] == "3.438 A/mm²"
    assert row["jDc"]["text"] == "6.078 A/mm²"
    assert row["wireLength"]["text"] == "400.00 mm"
    assert row["resistance"]["text"] == "8.3790 mΩ"
    assert row["wireLoss"]["text"] == "0.2430 W"


def test_totals_report_the_refusal_instead_of_a_partial_sum() -> None:
    rows = total_rows(make_result())

    assert [row["label"] for row in rows] == [
        "Total wire loss",
        "Core loss",
        "Total preliminary loss",
    ]
    assert rows[0]["text"] == "0.2430 W"
    assert rows[2]["state"] == ResultState.UNAVAILABLE.value
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/ui/test_preliminary_rows.py -q`
Expected: FAIL with `ModuleNotFoundError` for
`inductor_designer.ui.preliminary_rows`.

- [ ] **Step 3: Write the module**

Create `src/inductor_designer/ui/preliminary_rows.py`:

```python
"""Engineering-unit rows for the Preliminary screen (specification section 4.3).

The estimator reports SI. Every conversion the user sees happens here, once, in
pure functions with no Qt import, so the numbers can be checked against a
datasheet in a plain unit test. QML renders these dicts and computes nothing.
"""

from __future__ import annotations

from dataclasses import dataclass

from inductor_designer.simulation.preliminary import PreliminaryResult
from inductor_designer.simulation.preliminary_contracts import (
    PreliminaryValue,
    ResultState,
)


@dataclass(frozen=True, slots=True)
class DisplayUnit:
    suffix: str
    scale: float
    decimals: int


MILLITESLA = DisplayUnit("mT", 1000.0, 3)
AMPERE_PER_SQUARE_MILLIMETRE = DisplayUnit("A/mm²", 1e-6, 3)
MILLIOHM = DisplayUnit("mΩ", 1000.0, 4)
MILLIMETRE = DisplayUnit("mm", 1000.0, 2)
SQUARE_MILLIMETRE = DisplayUnit("mm²", 1e6, 4)
WATT = DisplayUnit("W", 1.0, 4)

_STATE_TEXT = {
    ResultState.UNAVAILABLE: "Unavailable",
    ResultState.INVALID: "Invalid",
}


def cell(value: PreliminaryValue, unit: DisplayUnit) -> dict[str, object]:
    """One displayed quantity: its state, its text, and why if it has no number."""
    if value.state is ResultState.ESTIMATED and value.value is not None:
        text = f"{value.value * unit.scale:.{unit.decimals}f} {unit.suffix}"
    else:
        text = _STATE_TEXT[value.state]
    return {
        "state": value.state.value,
        "text": text,
        "code": value.code or "",
        "message": value.message or "",
        "notes": list(value.notes),
    }


def _labelled(
    label: str, value: PreliminaryValue, unit: DisplayUnit
) -> dict[str, object]:
    return {"label": label, **cell(value, unit)}


def core_rows(result: PreliminaryResult) -> list[dict[str, object]]:
    core = result.core
    return [
        _labelled("DC flux density", core.b_dc, MILLITESLA),
        _labelled("AC flux-density swing", core.b_ac_peak, MILLITESLA),
        _labelled("Minimum flux density", core.b_min, MILLITESLA),
        _labelled("Maximum flux density", core.b_max, MILLITESLA),
        _labelled("Peak flux-density magnitude", core.b_peak_magnitude, MILLITESLA),
        _labelled("Core loss", core.core_loss, WATT),
    ]


def winding_rows(result: PreliminaryResult) -> list[dict[str, object]]:
    return [
        {
            "windingId": row.winding_id,
            "conductorArea": cell(row.conductor_area, SQUARE_MILLIMETRE),
            "jAcRms": cell(row.j_ac_rms, AMPERE_PER_SQUARE_MILLIMETRE),
            "jAcPeak": cell(row.j_ac_peak, AMPERE_PER_SQUARE_MILLIMETRE),
            "jDc": cell(row.j_dc, AMPERE_PER_SQUARE_MILLIMETRE),
            "wireLength": cell(row.wire_length, MILLIMETRE),
            "resistance": cell(row.resistance, MILLIOHM),
            "wireLoss": cell(row.wire_loss, WATT),
        }
        for row in result.windings
    ]


def total_rows(result: PreliminaryResult) -> list[dict[str, object]]:
    totals = result.totals
    return [
        _labelled("Total wire loss", totals.total_wire_loss, WATT),
        _labelled("Core loss", totals.core_loss, WATT),
        _labelled("Total preliminary loss", totals.total_loss, WATT),
    ]
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/ui/test_preliminary_rows.py -q`
Expected: PASS, 7 tests. If a `text` assertion is off by a digit, fix the
expected string only after checking the arithmetic by hand — the AC RMS current
density for AWG 18 at 2 A is 2.43 A/mm², and the DC value at 5 A is 6.07 A/mm².

- [ ] **Step 5: Run the gates and commit**

The test lives under `tests/unit/` and imports from `inductor_designer.ui`,
which imports PySide6 in its other modules but not in this one. Confirm the
non-solver suite still passes without a display:
`.venv/Scripts/python.exe -m pytest tests/unit -q`.

```bash
git add src/inductor_designer/ui/preliminary_rows.py tests/unit/ui
git commit -m "feat(ui): format preliminary results in engineering units"
```

---

### Task 10: The Preliminary controller

Before the controller itself, close one trust-boundary hole this screen exposes.
`ManualCoreSelection` has no validation, and `domain/validation.py::_validate_core`
only compares dimensions with `>` and `<=`, which are all `False` for `NaN` — so a
non-finite manual dimension passes validation and then raises inside
`CoreMagneticProperties.__post_init__`, which this controller reaches on every
refresh. QML `Number("")` is `NaN`, so this is reachable from an empty field.

Validate FINITENESS ONLY. Ordering and positivity already have owners that
report them as user-facing diagnostics rather than crashes —
`domain/validation.py::_validate_core` emits `core.manual.dimensions` and
`geometry/core_solid.py::resolve_finished_core` raises `CoreGeometryError`, both
covered by existing tests. Duplicating those rules in the constructor would
preempt and un-cover them. Non-finite is different: it is never a meaningful
dimension, and it silently defeats every `>` and `<=` comparison those two owners
rely on.

Add to `src/inductor_designer/domain/project.py`, on `ManualCoreSelection`:

```python
    def __post_init__(self) -> None:
        # Finiteness only: ordering and positivity are reported as diagnostics by
        # `_validate_core` and `resolve_finished_core`. NaN is what those checks
        # cannot see, because every comparison against it is False.
        for name, value in (
            ("outer_diameter_m", self.outer_diameter_m),
            ("inner_diameter_m", self.inner_diameter_m),
            ("height_m", self.height_m),
            ("corner_radius_m", self.corner_radius_m),
        ):
            if not isfinite(value):
                raise ValueError(f"ManualCoreSelection {name} must be finite")
```

and pin it:

```python
def test_manual_core_refuses_non_finite_dimensions() -> None:
    with pytest.raises(ValueError, match="outer_diameter_m must be finite"):
        ManualCoreSelection(float("nan"), 0.0138, 0.0112, 0.0)
    with pytest.raises(ValueError, match="height_m must be finite"):
        ManualCoreSelection(0.0272, 0.0138, float("inf"), 0.0)


def test_manual_core_still_accepts_dimensions_its_diagnostics_own() -> None:
    """Inverted or zero dimensions are reported downstream, not refused here."""
    inverted = ManualCoreSelection(0.010, 0.020, 0.005, 0.0)

    assert inverted.inner_diameter_m > inverted.outer_diameter_m
```

`Task 7`'s `applyManualCore` gains the matching guard so the refusal reaches the
user as a message instead of an exception out of a QML slot.

**Files:**
- Create: `src/inductor_designer/ui/preliminary_controller.py`
- Test: `tests/ui/test_preliminary_controller.py`

**Interfaces:**
- Consumes: `ProjectSession`, `build_geometry_model`, `GeometryModelError`,
  `build_preliminary_request`, `estimate_preliminary`, every function from
  `preliminary_rows.py`.
- Produces: `PreliminaryController(QObject)` with properties `coreRows: list`,
  `windingRows: list`, `totalRows: list`, `assumptions: list`,
  `geometryIssues: list`, `materialRevisionId: str`, `bhSeriesId: str`; signal
  `resultChanged`; slot `refresh()`.

- [ ] **Step 1: Write the failing test**

Create `tests/ui/test_preliminary_controller.py`:

```python
from __future__ import annotations

import os
from dataclasses import replace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtGui import QGuiApplication  # noqa: E402

from inductor_designer.simulation.preliminary_contracts import (  # noqa: E402
    DiagnosticCode,
    ResultState,
)
from inductor_designer.ui.preliminary_controller import (  # noqa: E402
    PreliminaryController,
)
from inductor_designer.ui.project_session import ProjectSession  # noqa: E402
from tests.unit.application.test_geometry_model import CATALOG  # noqa: E402
from tests.unit.domain.test_project import (  # noqa: E402
    make_material_record,
    make_project,
    make_project_with_material,
)

pytestmark = pytest.mark.ui


def test_a_complete_project_reports_estimated_rows() -> None:
    QGuiApplication.instance() or QGuiApplication([])
    session = ProjectSession(make_project_with_material())
    controller = PreliminaryController(session, CATALOG)

    assert len(controller.coreRows) == 6
    assert len(controller.windingRows) == 1
    assert len(controller.totalRows) == 3
    assert controller.windingRows[0]["jAcRms"]["state"] == ResultState.ESTIMATED.value
    assert controller.windingRows[0]["wireLength"]["state"] == ResultState.ESTIMATED.value
    assert controller.materialRevisionId == make_material_record().revision_id
    # The fixture record carries no B-H series, so flux density comes from its
    # relative permeability and no series id is pinned.
    assert controller.bhSeriesId == ""
    assert any("linear permeability" in note for note in controller.assumptions)
    assert controller.geometryIssues == []


def test_editing_the_project_refreshes_the_rows() -> None:
    QGuiApplication.instance() or QGuiApplication([])
    session = ProjectSession(make_project_with_material())
    controller = PreliminaryController(session, CATALOG)
    session.projectChanged.connect(controller.refresh)
    before = controller.windingRows[0]["jAcRms"]["text"]

    session.apply(
        replace(
            session.project,
            operating_point=replace(
                session.project.operating_point,
                windings=(
                    replace(
                        session.project.operating_point.windings[0],
                        ac_rms_current_a=4.0,
                    ),
                ),
            ),
        )
    )

    assert controller.windingRows[0]["jAcRms"]["text"] != before


def test_a_missing_material_leaves_current_density_estimated() -> None:
    """Specification section 4.3: one missing input affects only its dependents."""
    QGuiApplication.instance() or QGuiApplication([])
    # `make_project()` already ships with `core_material=None`.
    controller = PreliminaryController(ProjectSession(make_project()), CATALOG)

    assert controller.coreRows[0]["state"] == ResultState.UNAVAILABLE.value
    assert (
        controller.coreRows[0]["code"]
        == DiagnosticCode.FLUX_DENSITY_NO_MATERIAL_SELECTED
    )
    assert controller.windingRows[0]["jAcRms"]["state"] == ResultState.ESTIMATED.value


def test_broken_geometry_invalidates_only_geometry_dependent_rows() -> None:
    """Specification section 9."""
    QGuiApplication.instance() or QGuiApplication([])
    base = make_project_with_material()
    project = replace(
        base,
        design=replace(
            base.design,
            windings=(replace(base.design.windings[0], turns=100000),),
        ),
    )
    controller = PreliminaryController(ProjectSession(project), CATALOG)

    assert controller.geometryIssues != []
    assert (
        controller.windingRows[0]["wireLength"]["code"]
        == DiagnosticCode.WIRE_LOSS_NO_GEOMETRY
    )
    assert controller.windingRows[0]["jAcRms"]["state"] == ResultState.ESTIMATED.value
    assert controller.coreRows[0]["state"] == ResultState.ESTIMATED.value


def test_assumptions_are_always_visible() -> None:
    QGuiApplication.instance() or QGuiApplication([])
    controller = PreliminaryController(
        ProjectSession(make_project_with_material()), CATALOG
    )

    assert any("connector" in note or "lead" in note for note in controller.assumptions)
```

`build_geometry_model` wraps both domain-validation errors and packing refusals
in `GeometryModelError`, so the 100000-turn project reaches the same branch
either way; the flux-density path stays valid because it needs only turns,
currents, and the core's magnetic path.

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/ui/test_preliminary_controller.py -q`
Expected: FAIL with `ImportError: cannot import name 'make_project_with_material'`.

- [ ] **Step 3: Add the shared material-bearing project fixture**

`make_project()` ships with `core_material=None`, and four test modules in this
plan need the paired case. Add one factory next to the existing ones in
`tests/unit/domain/test_project.py` — do not duplicate it per module:

```python
def make_project_with_material(**overrides: object) -> InductorProject:
    """`make_project()` with its catalog core's own material revision pinned.

    `make_material_record()` is Magnetics Kool Mu 60, exactly
    `make_core().material`, so this pair is compatible. The record carries no
    series, so flux density comes from its relative permeability and
    `bh_series_id` stays None.
    """
    record = make_material_record()
    project = make_project(**overrides)
    return replace(
        project,
        design=replace(
            project.design,
            core_material=MaterialRevisionSelection(
                ref=record.ref,
                revision_id=record.revision_id,
                snapshot=record,
                bh_series_id=None,
            ),
        ),
    )
```

Run `.venv/Scripts/python.exe -m pytest tests/unit/domain/test_project.py -q`
and confirm it still passes before continuing.

- [ ] **Step 4: Write the controller**

Create `src/inductor_designer/ui/preliminary_controller.py`:

```python
"""The read-only Preliminary screen (specification sections 4.3 and 5).

The controller asks for one immutable `PreliminaryResult` and converts it to
rows. It never computes a quantity, never invents a reason, and never starts a
solver.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Property, QObject, Signal, Slot

from inductor_designer.application.services.geometry_model import (
    GeometryModelError,
    build_geometry_model,
)
from inductor_designer.application.services.preliminary_inputs import (
    build_preliminary_request,
)
from inductor_designer.simulation.preliminary import estimate_preliminary
from inductor_designer.ui.preliminary_rows import core_rows, total_rows, winding_rows

if TYPE_CHECKING:
    from inductor_designer.application.ports.catalog import CatalogRepository
    from inductor_designer.ui.project_session import ProjectSession


class PreliminaryController(QObject):
    resultChanged = Signal()

    def __init__(
        self,
        session: ProjectSession,
        catalog: CatalogRepository,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._session = session
        self._catalog = catalog
        self._core_rows: list[dict[str, object]] = []
        self._winding_rows: list[dict[str, object]] = []
        self._total_rows: list[dict[str, object]] = []
        self._assumptions: list[str] = []
        self._geometry_issues: list[str] = []
        self._material_revision_id = ""
        self._bh_series_id = ""
        self.refresh()

    def _get_core_rows(self) -> list[dict[str, object]]:
        return self._core_rows

    coreRows = Property(list, _get_core_rows, notify=resultChanged)

    def _get_winding_rows(self) -> list[dict[str, object]]:
        return self._winding_rows

    windingRows = Property(list, _get_winding_rows, notify=resultChanged)

    def _get_total_rows(self) -> list[dict[str, object]]:
        return self._total_rows

    totalRows = Property(list, _get_total_rows, notify=resultChanged)

    def _get_assumptions(self) -> list[str]:
        return self._assumptions

    assumptions = Property(list, _get_assumptions, notify=resultChanged)

    def _get_geometry_issues(self) -> list[str]:
        return self._geometry_issues

    geometryIssues = Property(list, _get_geometry_issues, notify=resultChanged)

    def _get_material_revision_id(self) -> str:
        return self._material_revision_id

    materialRevisionId = Property(str, _get_material_revision_id, notify=resultChanged)

    def _get_bh_series_id(self) -> str:
        return self._bh_series_id

    bhSeriesId = Property(str, _get_bh_series_id, notify=resultChanged)

    @Slot()
    def refresh(self) -> None:
        """Re-estimate after any valid project edit (specification section 2)."""
        project = self._session.project
        try:
            geometry = build_geometry_model(project, self._catalog)
            issues: list[str] = []
        except GeometryModelError as error:
            # Only packing-derived quantities lose their input; the estimator
            # reports exactly those as unavailable, so nothing else is disturbed.
            geometry = None
            issues = list(error.issues)
        try:
            result = estimate_preliminary(
                build_preliminary_request(project, self._catalog, geometry)
            )
        except Exception as error:  # noqa: BLE001 - the screen must never crash
            # An estimator invariant violation is a defect to report, not a
            # crash: numbers the user typed can still overflow the model, and
            # this screen refreshes on every edit.
            self._geometry_issues = [*issues, f"Preliminary estimate failed: {error}"]
            self.resultChanged.emit()
            return
        self._core_rows = core_rows(result)
        self._winding_rows = winding_rows(result)
        self._total_rows = total_rows(result)
        self._assumptions = list(result.notes)
        self._geometry_issues = issues
        self._material_revision_id = result.material_revision_id or ""
        self._bh_series_id = result.bh_series_id or ""
        self.resultChanged.emit()
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/ui/test_preliminary_controller.py -q`
Expected: PASS, 5 tests.

- [ ] **Step 6: Run the gates and commit**

```bash
git add src/inductor_designer/ui/preliminary_controller.py tests/ui/test_preliminary_controller.py tests/unit/domain/test_project.py
git commit -m "feat(ui): show live preliminary estimates per quantity"
```

---

### Task 11: The Simulation controller

**Files:**
- Modify: `src/inductor_designer/ui/generation_lines.py:44-48`
- Modify: `src/inductor_designer/ui/generation_controller.py:46-58`, `:81-93`
- Modify: `tests/ui/test_generation_controller.py:60-67` (move the wait helper),
  `:72`, `:88-94`, `:105-110`, `:150`, `:180-188`, `:220-224`
- Create: `tests/ui/conftest.py` (the shared `wait_until_idle` helper)
- Create: `src/inductor_designer/ui/simulation_controller.py`
- Test: `tests/ui/test_simulation_controller.py`

**Interfaces:**
- Consumes: `ProjectSession`, `GenerationController`, `GenerationBackend`,
  `run_backend_for`, `visible_window_support`, `CapabilitySnapshot`,
  `MeshIntent`, `RequestedOutput`, `RunMode`.
- Produces: `run_backend_for(backend: GenerationBackend) -> RunBackend` in
  `generation_lines.py`; `GenerationController.generate(backend_label: str,
  show_solver_window: bool = False)` with runner type
  `Callable[[str, bool], GenerationResult | Sequence[str]]`;
  `GenerationController.record_run_evidence(run_directory: Path | None,
  generated_file: Path | None) -> None`;
  `SimulationController(QObject)` with properties `backendOptions: list`,
  `backend: str`, `modeLabel: str`, `modeNote: str`, `meshIntentOptions: list`,
  `meshIntent: str`, `maximumPasses: int`, `percentError: float`,
  `requestedOutputs: list`, `showSolverWindow: bool`,
  `visibleWindowSupported: bool`, `visibleWindowReason: str`,
  `canGenerate: bool`, `blockedReason: str`; signals `configurationChanged`,
  `visibilityChanged`, `gateChanged`; slots `setBackend(str) -> bool`,
  `setMeshIntent(str) -> bool`, `setMaximumPasses(str) -> bool`,
  `setPercentError(str) -> bool`, `toggleRequestedOutput(str, bool) -> bool`,
  `setShowSolverWindow(bool) -> bool`, `generate() -> bool`.

- [ ] **Step 1: Write the failing test**

Create `tests/ui/test_simulation_controller.py`:

```python
from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtGui import QGuiApplication  # noqa: E402

from inductor_designer.domain.project import RequestedOutput  # noqa: E402
from inductor_designer.simulation.capabilities import (  # noqa: E402
    AedtEdition,
    AedtRelease,
    CapabilityReviewStatus,
    CapabilitySnapshot,
)
from inductor_designer.ui.generation_controller import GenerationController  # noqa: E402
from inductor_designer.ui.project_session import ProjectSession  # noqa: E402
from inductor_designer.ui.simulation_controller import (  # noqa: E402
    SimulationController,
)
from tests.unit.domain.test_project import make_project  # noqa: E402

pytestmark = pytest.mark.ui

SUPPORTED = CapabilitySnapshot(
    release=AedtRelease(2025, 2),
    edition=AedtEdition.COMMERCIAL,
    include_dc_fields_3d=True,
    discovered_limits=(),
    evidence_source="test",
    review_status=CapabilityReviewStatus.REVIEWED,
)


def build(
    *, dirty: bool = False, document: Path | None = Path("boost.inductor.json")
) -> tuple[
    ProjectSession,
    list[tuple[str, bool]],
    GenerationController,
    SimulationController,
]:
    QGuiApplication.instance() or QGuiApplication([])
    calls: list[tuple[str, bool]] = []

    def runner(backend_label: str, show_solver_window: bool) -> tuple[str, ...]:
        calls.append((backend_label, show_solver_window))
        return ("done",)

    session = ProjectSession(make_project(), document, lambda project: None)
    generation = GenerationController(runner)
    controller = SimulationController(session, generation, SUPPORTED)
    if dirty:
        session.apply(replace(session.project, description="edited"))
    return session, calls, generation, controller


def test_the_recipe_is_exposed_and_editable() -> None:
    session, _, _, controller = build()

    assert controller.backend == "Maxwell 3D"
    assert controller.backendOptions == ["Maxwell 3D", "Maxwell 2D (Ansys)", "FEMM 2D"]
    assert controller.meshIntentOptions == ["standard"]
    assert controller.maximumPasses == session.project.simulation_recipe.maximum_passes

    assert controller.setMaximumPasses("12") is True
    assert controller.setPercentError("0.5") is True

    assert session.project.simulation_recipe.maximum_passes == 12
    assert session.project.simulation_recipe.percent_error == 0.5


def test_an_invalid_recipe_value_is_refused_without_changing_the_project() -> None:
    session, _, _, controller = build()

    assert controller.setMaximumPasses("0") is False
    assert controller.setPercentError("-1") is False

    assert session.project.simulation_recipe.maximum_passes == 10
    assert session.project.simulation_recipe.percent_error == 1.0


def test_requested_outputs_toggle_into_the_recipe() -> None:
    session, _, _, controller = build()

    assert controller.toggleRequestedOutput(RequestedOutput.INDUCTANCE.value, True) is True

    assert RequestedOutput.INDUCTANCE in session.project.simulation_recipe.requested_outputs
    assert any(
        row["value"] == RequestedOutput.INDUCTANCE.value and row["selected"]
        for row in controller.requestedOutputs
    )

    assert controller.toggleRequestedOutput(RequestedOutput.INDUCTANCE.value, False) is True
    assert session.project.simulation_recipe.requested_outputs == ()


def test_the_run_mode_is_generate_only_with_a_stated_reason() -> None:
    _, _, _, controller = build()

    assert controller.modeLabel == "generate-only"
    assert "M8" in controller.modeNote or "solve" in controller.modeNote.casefold()


def test_visible_window_support_follows_the_backend() -> None:
    _, _, _, controller = build()

    assert controller.visibleWindowSupported is True
    assert controller.visibleWindowReason == ""

    assert controller.setBackend("FEMM 2D") is True
    assert controller.visibleWindowSupported is True


def test_an_unsupported_visible_window_is_disabled_with_a_reason() -> None:
    QGuiApplication.instance() or QGuiApplication([])
    unsupported = replace(SUPPORTED, release=AedtRelease(2024, 2))
    session = ProjectSession(make_project(), Path("boost.inductor.json"), lambda p: None)
    controller = SimulationController(
        session, GenerationController(lambda label, show: ("done",)), unsupported
    )

    assert controller.setBackend("Maxwell 3D") is True

    assert controller.visibleWindowSupported is False
    assert controller.visibleWindowReason != ""
    assert controller.setShowSolverWindow(True) is False
    assert controller.showSolverWindow is False


def test_generation_is_blocked_while_the_project_has_unsaved_edits() -> None:
    session, calls, _, controller = build(dirty=True)

    assert controller.canGenerate is False
    assert "save" in controller.blockedReason.casefold()
    assert controller.generate() is False
    assert calls == []

    assert session.saveProject() is True

    assert controller.canGenerate is True
    assert controller.blockedReason == ""


def test_generation_is_blocked_without_a_document_path() -> None:
    QGuiApplication.instance() or QGuiApplication([])
    session = ProjectSession(make_project())
    controller = SimulationController(
        session, GenerationController(lambda label, show: ("done",)), SUPPORTED
    )

    assert controller.canGenerate is False
    assert "document path" in controller.blockedReason.casefold()


def test_generating_passes_the_backend_and_the_visibility_choice() -> None:
    app = QGuiApplication.instance() or QGuiApplication([])
    _, calls, generation, controller = build()
    controller.setBackend("FEMM 2D")
    controller.setShowSolverWindow(True)

    assert controller.generate() is True
    wait_until_idle(app, generation)

    assert calls == [("FEMM 2D", True)]
```

`generate()` starts a worker thread, so the assertion must wait for it. Move the
existing `_wait_until_idle` helper out of
`tests/ui/test_generation_controller.py` into `tests/ui/conftest.py` as
`wait_until_idle(app, controller)`, import it in both modules, and do not
duplicate the loop.

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/ui/test_simulation_controller.py -q`
Expected: FAIL with `ModuleNotFoundError` for
`inductor_designer.ui.simulation_controller`.

- [ ] **Step 3: Widen the generation runner to carry the visibility choice**

In `src/inductor_designer/ui/generation_lines.py`, publish the mapping the new
controller needs instead of re-deriving it:

```python
def run_backend_for(backend: GenerationBackend) -> RunBackend:
    """The run-contract backend behind a UI backend label."""
    return _RUN_BACKENDS[backend]
```

In `src/inductor_designer/ui/generation_controller.py`:

```python
    def __init__(
        self,
        runner: Callable[[str, bool], GenerationResult | Sequence[str]],
        parent: QObject | None = None,
    ) -> None:
```

```python
    @Slot(str, bool)
    def generate(self, backend_label: str, show_solver_window: bool = False) -> None:
```

and inside `worker`, call `self._runner(backend_label, show_solver_window)`. The
choice is passed as an argument rather than read from controller state because
the worker runs on another thread and must not race a later UI change.

Add one public writer for the run evidence and use it from `worker`, so the
Review screen's tests do not have to reach into private attributes:

```python
    def record_run_evidence(
        self, run_directory: Path | None, generated_file: Path | None
    ) -> None:
        """Publish where the last run landed. Called by the worker, and by tests."""
        self._last_run_directory = run_directory
        self._last_generated_file = generated_file
        self.linesChanged.emit()
```

In `worker`'s `finally` block, replace the two direct assignments with
`self.record_run_evidence(result.run_directory, result.generated_file)` and keep
the remaining assignments as they are. `Path` moves out of `TYPE_CHECKING` into a
runtime import.

Update the six runners in `tests/ui/test_generation_controller.py` to take
`(backend_label, show_solver_window)`, and add one assertion that the flag
arrives:

```python
def test_generate_forwards_the_visible_window_choice() -> None:
    app = QGuiApplication.instance() or QGuiApplication([])
    seen: list[bool] = []

    def runner(backend_label: str, show_solver_window: bool) -> tuple[str, ...]:
        seen.append(show_solver_window)
        return ("done",)

    controller = GenerationController(runner)
    controller.generate("Maxwell 3D", True)
    _wait_until_idle(app, controller)

    assert seen == [True]
```

- [ ] **Step 4: Write the controller**

Create `src/inductor_designer/ui/simulation_controller.py`:

```python
"""The Simulation screen (specification section 4.4, ADR 0007).

Backend, mesh intent, convergence intent, and requested outputs live in the
Project document, so every edit here goes through the session. Frequency and
temperature are deliberately absent: they are shared operating-point inputs
owned by the Windings screen.
"""

from __future__ import annotations

import math
from dataclasses import replace
from typing import TYPE_CHECKING

from PySide6.QtCore import Property, QObject, Signal, Slot

from inductor_designer.application.services.solver_visibility import (
    visible_window_support,
)
from inductor_designer.domain.project import MeshIntent, RequestedOutput
from inductor_designer.simulation.run_contracts import RunMode
from inductor_designer.ui.generation_lines import GenerationBackend, run_backend_for

if TYPE_CHECKING:
    from inductor_designer.simulation.capabilities import CapabilitySnapshot
    from inductor_designer.ui.generation_controller import GenerationController
    from inductor_designer.ui.project_session import ProjectSession

_MODE_NOTE = (
    "Guided Studio generates the solver project without solving it. Generate "
    "and Solve arrives with the M8 result artifacts."
)


class SimulationController(QObject):
    configurationChanged = Signal()
    visibilityChanged = Signal()
    gateChanged = Signal()

    def __init__(
        self,
        session: ProjectSession,
        generation: GenerationController,
        capabilities: CapabilitySnapshot,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._session = session
        self._generation = generation
        self._capabilities = capabilities
        self._backend = GenerationBackend.MAXWELL_3D
        self._show_solver_window = False
        session.dirtyChanged.connect(self.gateChanged)
        generation.busyChanged.connect(self.gateChanged)

    def _get_backend_options(self) -> list[str]:
        return [item.value for item in GenerationBackend]

    backendOptions = Property(list, _get_backend_options, constant=True)

    def _get_backend(self) -> str:
        return self._backend.value

    backend = Property(str, _get_backend, notify=configurationChanged)

    def _get_mode_label(self) -> str:
        return RunMode.GENERATE_ONLY.value

    modeLabel = Property(str, _get_mode_label, constant=True)

    def _get_mode_note(self) -> str:
        return _MODE_NOTE

    modeNote = Property(str, _get_mode_note, constant=True)

    def _get_mesh_intent_options(self) -> list[str]:
        return [item.value for item in MeshIntent]

    meshIntentOptions = Property(list, _get_mesh_intent_options, constant=True)

    def _get_mesh_intent(self) -> str:
        return self._session.project.simulation_recipe.mesh_intent.value

    meshIntent = Property(str, _get_mesh_intent, notify=configurationChanged)

    def _get_maximum_passes(self) -> int:
        return self._session.project.simulation_recipe.maximum_passes

    maximumPasses = Property(int, _get_maximum_passes, notify=configurationChanged)

    def _get_percent_error(self) -> float:
        return self._session.project.simulation_recipe.percent_error

    percentError = Property(float, _get_percent_error, notify=configurationChanged)

    def _get_requested_outputs(self) -> list[dict[str, object]]:
        selected = set(self._session.project.simulation_recipe.requested_outputs)
        return [
            {
                "value": item.value,
                "label": item.value.replace("-", " "),
                "selected": item in selected,
            }
            for item in RequestedOutput
        ]

    requestedOutputs = Property(list, _get_requested_outputs, notify=configurationChanged)

    def _get_show_solver_window(self) -> bool:
        return self._show_solver_window

    showSolverWindow = Property(bool, _get_show_solver_window, notify=visibilityChanged)

    def _support(self) -> tuple[bool, str]:
        support = visible_window_support(
            run_backend_for(self._backend), self._capabilities
        )
        return support.supported, support.reason or ""

    def _get_visible_window_supported(self) -> bool:
        return self._support()[0]

    visibleWindowSupported = Property(
        bool, _get_visible_window_supported, notify=visibilityChanged
    )

    def _get_visible_window_reason(self) -> str:
        return self._support()[1]

    visibleWindowReason = Property(
        str, _get_visible_window_reason, notify=visibilityChanged
    )

    def _gate(self) -> str:
        """Why a run cannot start, or an empty string when it can."""
        if self._generation.busy:
            return "A generation run is already in progress."
        if not self._session.documentPath:
            return (
                "The project has no document path. Save the project to a file "
                "before running."
            )
        if self._session.dirty:
            return (
                "The project has unsaved edits. Save the project before running "
                "so the run matches what is on disk."
            )
        return ""

    def _get_can_generate(self) -> bool:
        return self._gate() == ""

    canGenerate = Property(bool, _get_can_generate, notify=gateChanged)

    def _get_blocked_reason(self) -> str:
        return self._gate()

    blockedReason = Property(str, _get_blocked_reason, notify=gateChanged)

    def _apply_recipe(self, **changes: object) -> None:
        project = self._session.project
        self._session.apply(
            replace(
                project,
                simulation_recipe=replace(project.simulation_recipe, **changes),
            )
        )
        self.configurationChanged.emit()

    @Slot(str, result=bool)
    def setBackend(self, backend_label: str) -> bool:
        try:
            backend = GenerationBackend(backend_label)
        except ValueError:
            self._session.set_status(f"Unknown backend: {backend_label}")
            return False
        self._backend = backend
        if not self._support()[0]:
            self._show_solver_window = False
        self.configurationChanged.emit()
        self.visibilityChanged.emit()
        return True

    @Slot(str, result=bool)
    def setMeshIntent(self, mesh_intent: str) -> bool:
        try:
            intent = MeshIntent(mesh_intent)
        except ValueError:
            self._session.set_status(f"Unknown mesh intent: {mesh_intent}")
            return False
        self._apply_recipe(mesh_intent=intent)
        return True

    @Slot(str, result=bool)
    def setMaximumPasses(self, value: str) -> bool:
        try:
            number = int(value.strip())
            self._apply_recipe(maximum_passes=number)
        except ValueError as error:
            # SimulationRecipe refuses a nonpositive count; report, never crash.
            self._session.set_status(f"Unable to apply maximum passes: {error}")
            return False
        return True

    @Slot(str, result=bool)
    def setPercentError(self, value: str) -> bool:
        try:
            number = float(value.strip().replace(",", "."))
            if not math.isfinite(number):
                raise ValueError("Percent error must be finite")
            self._apply_recipe(percent_error=number)
        except ValueError as error:
            self._session.set_status(f"Unable to apply percent error: {error}")
            return False
        return True

    @Slot(str, bool, result=bool)
    def toggleRequestedOutput(self, value: str, selected: bool) -> bool:
        try:
            output = RequestedOutput(value)
        except ValueError:
            self._session.set_status(f"Unknown requested output: {value}")
            return False
        current = list(self._session.project.simulation_recipe.requested_outputs)
        if selected and output not in current:
            current.append(output)
        elif not selected and output in current:
            current.remove(output)
        self._apply_recipe(requested_outputs=tuple(current))
        return True

    @Slot(bool, result=bool)
    def setShowSolverWindow(self, show: bool) -> bool:
        """An unsupported visible mode is refused with its reason, never ignored."""
        if show and not self._support()[0]:
            self._session.set_status(
                f"Show solver window is unavailable: {self._support()[1]}"
            )
            return False
        self._show_solver_window = show
        self.visibilityChanged.emit()
        return True

    @Slot(result=bool)
    def generate(self) -> bool:
        blocked = self._gate()
        if blocked:
            self._session.set_status(blocked)
            return False
        self._generation.generate(self._backend.value, self._show_solver_window)
        return True
```

`SimulationRecipe.__post_init__` raises `ValueError` for a nonpositive pass count
or percent error, which is why both setters wrap `_apply_recipe` in the `try`
rather than validating the number themselves.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/ui/test_simulation_controller.py tests/ui/test_generation_controller.py -q`
Expected: PASS.

- [ ] **Step 6: Run the gates and commit**

```bash
git add src/inductor_designer/ui tests/ui
git commit -m "feat(ui): configure a run and gate it on a saved project"
```

---

### Task 12: The Review controller

**Files:**
- Create: `src/inductor_designer/ui/review_controller.py`
- Test: `tests/ui/test_review_controller.py`

**Interfaces:**
- Consumes: `ProjectSession`, `PreliminaryController`, `GenerationController`
  (including `record_run_evidence` from Task 11), `CatalogRepository`,
  `PathOpener`, `validate_project`, `ValidationCategory`, `simulation_summary`.
- Produces: `ReviewController(QObject)` with properties `sections: list`
  (each `{"title": str, "rows": [{"label": str, "text": str}]}`),
  `findings: list` (each `{"category": str, "code": str, "message": str}`),
  `canOpenGeneratedFile: bool`, `canOpenRunFolder: bool`, `message: str`;
  signal `reviewChanged`; slots `refresh()`, `openGeneratedFile() -> bool`,
  `openRunFolder() -> bool`.

- [ ] **Step 1: Write the failing test**

Create `tests/ui/test_review_controller.py`:

```python
from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtGui import QGuiApplication  # noqa: E402

from inductor_designer.ui.generation_controller import GenerationController  # noqa: E402
from inductor_designer.ui.preliminary_controller import (  # noqa: E402
    PreliminaryController,
)
from inductor_designer.ui.project_session import ProjectSession  # noqa: E402
from inductor_designer.ui.review_controller import ReviewController  # noqa: E402
from tests.unit.application.test_geometry_model import CATALOG  # noqa: E402
from tests.unit.domain.test_project import (  # noqa: E402
    make_material_record,
    make_project_with_material,
)

pytestmark = pytest.mark.ui


class RecordingOpener:
    def __init__(self) -> None:
        self.opened: list[Path] = []

    def open_path(self, path: Path) -> None:
        self.opened.append(path)


def build() -> tuple[RecordingOpener, GenerationController, ReviewController]:
    QGuiApplication.instance() or QGuiApplication([])
    session = ProjectSession(make_project_with_material(), Path("boost.inductor.json"))
    generation = GenerationController(lambda label, show: ("done",))
    opener = RecordingOpener()
    controller = ReviewController(
        session,
        PreliminaryController(session, CATALOG),
        generation,
        CATALOG,
        opener,
    )
    return opener, generation, controller


def test_review_shows_the_paired_core_material_operating_point_and_estimates() -> None:
    _, _, controller = build()

    titles = [section["title"] for section in controller.sections]
    assert titles == [
        "Core and material",
        "Shared operating point",
        "Winding excitations",
        "Preliminary estimates",
        "Run request",
    ]
    assert any(
        make_material_record().revision_id in row["text"]
        for section in controller.sections
        for row in section["rows"]
    )
    assert any(
        row["label"] == "Total wire loss"
        for section in controller.sections
        for row in section["rows"]
    )


def test_review_lists_validation_findings() -> None:
    _, _, controller = build()

    assert all(
        set(finding) == {"category", "code", "message"} for finding in controller.findings
    )


def test_open_actions_are_disabled_before_a_run() -> None:
    opener, _, controller = build()

    assert controller.canOpenGeneratedFile is False
    assert controller.canOpenRunFolder is False
    assert controller.openGeneratedFile() is False
    assert controller.openRunFolder() is False
    assert opener.opened == []
    assert "no generated" in controller.message.casefold()


def test_open_actions_use_the_last_run_evidence(tmp_path: Path) -> None:
    opener, generation, controller = build()
    run_directory = tmp_path / "runs" / "20260730-101500-femm"
    run_directory.mkdir(parents=True)
    generated = run_directory / "inductor.fem"
    generated.write_text("", encoding="utf-8")
    generation.record_run_evidence(run_directory, generated)
    controller.refresh()

    assert controller.canOpenGeneratedFile is True
    assert controller.canOpenRunFolder is True
    assert controller.openGeneratedFile() is True
    assert controller.openRunFolder() is True

    assert opener.opened == [generated, run_directory]


def test_an_opener_failure_is_reported_not_raised(tmp_path: Path) -> None:
    QGuiApplication.instance() or QGuiApplication([])
    session = ProjectSession(make_project_with_material(), Path("boost.inductor.json"))
    generation = GenerationController(lambda label, show: ("done",))

    class Failing:
        def open_path(self, path: Path) -> None:
            raise OSError("no association")

    controller = ReviewController(
        session,
        PreliminaryController(session, CATALOG),
        generation,
        CATALOG,
        Failing(),
    )
    run_directory = tmp_path / "runs" / "20260730-101500-femm"
    run_directory.mkdir(parents=True)
    generation.record_run_evidence(run_directory, None)

    assert controller.openRunFolder() is False
    assert "no association" in controller.message
```

`record_run_evidence` (Task 11) is the seam: the worker thread calls it after a
real run, and the tests call it directly, so no test touches a private attribute
and driving a real solver is unnecessary. The failing-opener case injects its
opener through the constructor for the same reason.

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/ui/test_review_controller.py -q`
Expected: FAIL with `ModuleNotFoundError` for
`inductor_designer.ui.review_controller`.

- [ ] **Step 3: Write the controller**

Create `src/inductor_designer/ui/review_controller.py`:

```python
"""The Review screen (specification section 4.4).

Everything shown here is already computed elsewhere: the session project, the
preliminary controller's rows, the domain validator, and the last run's
evidence. Review composes them and binds the two ADR 0007 open actions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Property, QObject, Signal, Slot

from inductor_designer.application.services.simulation_summary import (
    simulation_summary,
)
from inductor_designer.domain.project import (
    CatalogCoreSelection,
    ManualCoreSelection,
)
from inductor_designer.domain.validation import validate_project

if TYPE_CHECKING:
    from inductor_designer.application.ports.catalog import CatalogRepository
    from inductor_designer.application.ports.path_opener import PathOpener
    from inductor_designer.ui.generation_controller import GenerationController
    from inductor_designer.ui.preliminary_controller import PreliminaryController
    from inductor_designer.ui.project_session import ProjectSession


class ReviewController(QObject):
    reviewChanged = Signal()

    def __init__(
        self,
        session: ProjectSession,
        preliminary: PreliminaryController,
        generation: GenerationController,
        catalog: CatalogRepository,
        opener: PathOpener,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._session = session
        self._preliminary = preliminary
        self._generation = generation
        self._catalog = catalog
        self._opener = opener
        self._message = ""
        generation.linesChanged.connect(self.refresh)
        session.projectChanged.connect(self.refresh)

    def _core_rows(self) -> list[dict[str, str]]:
        design = self._session.project.design
        core = design.core
        rows: list[dict[str, str]] = []
        if isinstance(core, CatalogCoreSelection):
            rows.append({"label": "Core", "text": f"Catalog {core.part_number}"})
            rows.append(
                {
                    "label": "Core material identity",
                    "text": (
                        f"{core.snapshot.material.manufacturer} "
                        f"{core.snapshot.material.name} {core.snapshot.material.grade}"
                    ),
                }
            )
        elif isinstance(core, ManualCoreSelection):
            rows.append(
                {
                    "label": "Core",
                    "text": (
                        f"Manual toroid {core.outer_diameter_m * 1000.0:g} x "
                        f"{core.inner_diameter_m * 1000.0:g} x "
                        f"{core.height_m * 1000.0:g} mm"
                    ),
                }
            )
            rows.append(
                {
                    "label": "Manual compatibility acknowledged",
                    "text": (
                        "yes"
                        if design.manual_material_compatibility_acknowledged
                        else "no"
                    ),
                }
            )
        else:
            rows.append({"label": "Core", "text": "not selected"})
        material = design.core_material
        rows.append(
            {
                "label": "Pinned material revision",
                "text": (
                    "not selected"
                    if material is None
                    else (
                        f"{material.ref.manufacturer} {material.ref.name} "
                        f"{material.ref.grade} revision {material.revision_id}"
                        f" ({material.snapshot.status.value})"
                    )
                ),
            }
        )
        rows.append(
            {
                "label": "B-H series",
                "text": (
                    material.bh_series_id or "not selected"
                    if material is not None
                    else "not selected"
                ),
            }
        )
        return rows

    def _winding_rows(self) -> list[dict[str, str]]:
        project = self._session.project
        excitations = {
            item.winding_id: item for item in project.operating_point.windings
        }
        rows: list[dict[str, str]] = []
        for winding in project.design.windings:
            excitation = excitations.get(winding.winding_id)
            if excitation is None:
                rows.append(
                    {"label": winding.winding_id, "text": "no excitation recorded"}
                )
                continue
            rows.append(
                {
                    "label": f"{winding.winding_id} ({winding.label})",
                    "text": (
                        f"{winding.turns} turns of {winding.conductor_name}; "
                        f"AC {excitation.ac_rms_current_a:g} A RMS at "
                        f"{excitation.ac_phase_deg:g} deg; DC "
                        f"{excitation.dc_current_a:g} A; "
                        f"{excitation.current_direction.value}; "
                        f"wound {winding.winding_direction.value}"
                    ),
                }
            )
        return rows

    def _preliminary_rows(self) -> list[dict[str, str]]:
        rows = [
            {"label": str(row["label"]), "text": str(row["text"])}
            for row in self._preliminary.coreRows + self._preliminary.totalRows
        ]
        rows.extend(
            {
                "label": f"{row['windingId']} current density (AC RMS)",
                "text": str(row["jAcRms"]["text"]),  # type: ignore[index]
            }
            for row in self._preliminary.windingRows
        )
        rows.extend(
            {"label": "Limitation", "text": note}
            for note in self._preliminary.assumptions
        )
        rows.extend(
            {"label": "Geometry issue", "text": issue}
            for issue in self._preliminary.geometryIssues
        )
        return rows

    def _run_rows(self) -> list[dict[str, str]]:
        rows = [
            {"label": "Project document", "text": self._session.documentPath or "unsaved"},
        ]
        rows.extend(
            {"label": "Run log", "text": line} for line in self._generation.lines
        )
        manifest = self._generation.failed_manifest
        if manifest is not None:
            rows.extend(
                {"label": "Solver notice", "text": warning}
                for warning in manifest.warnings
            )
        return rows

    def _get_sections(self) -> list[dict[str, object]]:
        return [
            {"title": "Core and material", "rows": self._core_rows()},
            {
                "title": "Shared operating point",
                "rows": [
                    {"label": "Summary", "text": line}
                    for line in simulation_summary(self._session.project)
                ],
            },
            {"title": "Winding excitations", "rows": self._winding_rows()},
            {"title": "Preliminary estimates", "rows": self._preliminary_rows()},
            {"title": "Run request", "rows": self._run_rows()},
        ]

    sections = Property(list, _get_sections, notify=reviewChanged)

    def _get_findings(self) -> list[dict[str, str]]:
        issues = validate_project(
            self._session.project,
            known_conductors=self._catalog.list_conductor_names(),
        )
        return [
            {
                "category": issue.category.value,
                "code": issue.code,
                "message": issue.message,
            }
            for issue in issues
        ]

    findings = Property(list, _get_findings, notify=reviewChanged)

    def _get_can_open_generated_file(self) -> bool:
        path = self._generation.last_generated_file
        return path is not None and path.exists()

    canOpenGeneratedFile = Property(
        bool, _get_can_open_generated_file, notify=reviewChanged
    )

    def _get_can_open_run_folder(self) -> bool:
        path = self._generation.last_run_directory
        return path is not None and path.is_dir()

    canOpenRunFolder = Property(bool, _get_can_open_run_folder, notify=reviewChanged)

    def _get_message(self) -> str:
        return self._message

    message = Property(str, _get_message, notify=reviewChanged)

    @Slot()
    def refresh(self) -> None:
        self.reviewChanged.emit()

    def _open(self, path: object, what: str) -> bool:
        if path is None:
            self._message = (
                f"There is no {what} to open yet. Generate a run from the "
                "Simulation screen first."
            )
            self.reviewChanged.emit()
            return False
        try:
            self._opener.open_path(path)  # type: ignore[arg-type]
        except OSError as error:
            self._message = f"Unable to open the {what}: {error}"
            self.reviewChanged.emit()
            return False
        self._message = f"Opened the {what}."
        self.reviewChanged.emit()
        return True

    @Slot(result=bool)
    def openGeneratedFile(self) -> bool:
        return self._open(self._generation.last_generated_file, "generated solver file")

    @Slot(result=bool)
    def openRunFolder(self) -> bool:
        return self._open(self._generation.last_run_directory, "run folder")
```

`DesktopPathOpener.open_path` raises `OSError` for a missing path (see
`tests/unit/adapters/system/test_path_opener.py`), which is why only `OSError` is
caught: any other exception is a programming error and must not be swallowed.

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/ui/test_review_controller.py -q`
Expected: PASS, 5 tests.

- [ ] **Step 5: Run the gates and commit**

```bash
git add src/inductor_designer/ui/review_controller.py tests/ui/test_review_controller.py
git commit -m "feat(ui): review the run request and open its artifacts"
```

---

### Task 13: The step rail, the Core & Material screen, and the Material Studio window

**Files:**
- Create: `src/inductor_designer/ui/qml/CoreMaterialPanel.qml`
- Create: `src/inductor_designer/ui/qml/MaterialStudioWindow.qml`
- Modify: `src/inductor_designer/ui/qml/Main.qml`
- Modify: `src/inductor_designer/ui/main.py` (`create_engine` context properties)
- Modify: `tests/ui/test_material_studio_workflow.py:52`, `:218`
- Modify: `tests/ui/test_qml_smoke.py:193`
- Test: `tests/ui/test_guided_studio_qml.py`

**Interfaces:**
- Consumes: context properties `guidedStudioController`, `coreMaterialController`,
  `materialStudioController`, `preliminaryController`, `simulationController`,
  `reviewController`, `projectSession`.
- Produces: step objectNames `coreMaterialStep`, `windingsStep`,
  `preliminaryStep`, `simulationStep`, `reviewStep`; `CoreMaterialPanel` with
  `coreMaterialPanel`, `coreOptionList`, `materialOptionList`,
  `manualCoreOuterField`, `manualCoreInnerField`, `manualCoreHeightField`,
  `manualCoreCornerField`, `applyManualCoreButton`,
  `manualCompatibilityCheckBox`, `clearMaterialButton`,
  `openMaterialStudioButton`, `coreMaterialMessage`; window objectName
  `materialStudioWindow`.

- [ ] **Step 1: Write the failing test**

Append to `tests/ui/test_guided_studio_qml.py`:

```python
def test_the_step_rail_carries_the_five_specified_screens() -> None:
    app = QGuiApplication.instance() or QGuiApplication([])
    session = ProjectSession(make_project())
    engine = create_engine(
        guided_studio_controller=GuidedStudioController(session, CATALOG)
    )
    root = engine.rootObjects()[0]
    app.processEvents()

    for name in (
        "coreMaterialStep",
        "windingsStep",
        "preliminaryStep",
        "simulationStep",
        "reviewStep",
    ):
        assert root.findChild(QObject, name) is not None, name
    assert root.findChild(QObject, "materialsStep") is None


def test_material_studio_is_a_separate_window_not_a_step() -> None:
    app = QGuiApplication.instance() or QGuiApplication([])
    engine = create_engine()
    root = engine.rootObjects()[0]
    app.processEvents()

    window = root.findChild(QObject, "materialStudioWindow")
    assert window is not None
    assert window.property("visible") is False
    assert root.findChild(QObject, "openMaterialStudioButton") is not None


def test_preliminary_and_review_hide_the_geometry_canvas() -> None:
    app = QGuiApplication.instance() or QGuiApplication([])
    engine = create_engine()
    root = engine.rootObjects()[0]
    steps = root.findChild(QObject, "guidedStepList")
    canvas = root.findChild(QObject, "canvasCard")
    app.processEvents()

    steps.setProperty("currentIndex", 1)
    app.processEvents()
    assert canvas.property("visible") is True

    steps.setProperty("currentIndex", 2)
    app.processEvents()
    assert canvas.property("visible") is False

    steps.setProperty("currentIndex", 4)
    app.processEvents()
    assert canvas.property("visible") is False


def test_core_material_panel_exposes_both_selectors_and_manual_dimensions() -> None:
    app = QGuiApplication.instance() or QGuiApplication([])
    engine = create_engine()
    root = engine.rootObjects()[0]
    app.processEvents()

    for name in (
        "coreMaterialPanel",
        "coreOptionList",
        "materialOptionList",
        "manualCoreOuterField",
        "manualCoreInnerField",
        "manualCoreHeightField",
        "manualCoreCornerField",
        "applyManualCoreButton",
        "manualCompatibilityCheckBox",
        "clearMaterialButton",
        "coreMaterialMessage",
    ):
        assert root.findChild(QObject, name) is not None, name


def test_manual_core_fields_reject_letters_natively() -> None:
    app = QGuiApplication.instance() or QGuiApplication([])
    engine = create_engine()
    root = engine.rootObjects()[0]
    field = root.findChild(QObject, "manualCoreOuterField")
    app.processEvents()

    field.setProperty("text", "27.2")
    assert field.property("acceptableInput") is True
    assert field.property("validator") is not None
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/ui/test_guided_studio_qml.py -q`
Expected: FAIL — `coreMaterialStep` is not found.

- [ ] **Step 3: Write `CoreMaterialPanel.qml`**

Create `src/inductor_designer/ui/qml/CoreMaterialPanel.qml`:

```qml
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Pane {
    id: coreMaterialPanel
    objectName: "coreMaterialPanel"
    property var controller: null

    function selectedManualCore() {
        return controller !== null && controller.selectedCore.kind === "manual"
            ? controller.selectedCore : ({})
    }

    function refreshManualFields() {
        const core = selectedManualCore()
        outerField.text = core.outerDiameterMm === undefined ? "" : String(core.outerDiameterMm)
        innerField.text = core.innerDiameterMm === undefined ? "" : String(core.innerDiameterMm)
        heightField.text = core.heightMm === undefined ? "" : String(core.heightMm)
        cornerField.text = core.cornerRadiusMm === undefined ? "" : String(core.cornerRadiusMm)
    }

    Connections {
        target: coreMaterialPanel.controller
        function onSelectionChanged() { coreMaterialPanel.refreshManualFields() }
    }

    Component.onCompleted: refreshManualFields()

    ScrollView {
        anchors.fill: parent
        clip: true
        contentWidth: availableWidth

        ColumnLayout {
            width: coreMaterialPanel.width - 24
            spacing: 12

            Label {
                text: qsTr("Design / Core & Material")
                font.pixelSize: 11
                font.letterSpacing: 1.2
                color: "#6d7a7e"
            }
            Label {
                text: qsTr("Pair a core with an exact material revision")
                font.pixelSize: 24
                font.bold: true
                color: "#1e2b32"
            }
            Label {
                Layout.fillWidth: true
                text: qsTr("Each selection filters the other list. An incompatible pairing is cleared and explained; nothing is substituted for you.")
                wrapMode: Text.WordWrap
                color: "#6d7a7e"
            }

            Label { text: qsTr("Catalog cores"); font.bold: true; color: "#1e2b32" }

            ListView {
                id: coreOptionList
                objectName: "coreOptionList"
                Layout.fillWidth: true
                Layout.preferredHeight: Math.min(180, Math.max(52, count * 52))
                clip: true
                spacing: 6
                model: coreMaterialPanel.controller !== null
                    ? coreMaterialPanel.controller.coreOptions : []
                Accessible.name: qsTr("Catalog core list")

                delegate: ItemDelegate {
                    required property var modelData
                    width: ListView.view.width
                    height: 46
                    activeFocusOnTab: true
                    highlighted: coreMaterialPanel.controller !== null
                        && coreMaterialPanel.controller.selectedCore.partNumber === modelData.partNumber
                    text: qsTr("%1  ·  %2  ·  %3")
                        .arg(modelData.partNumber)
                        .arg(modelData.manufacturer)
                        .arg(modelData.materialLabel)
                    Accessible.name: qsTr("Select core %1").arg(modelData.partNumber)
                    onClicked: coreMaterialPanel.controller.selectCatalogCore(modelData.partNumber)
                    Keys.onReturnPressed: coreMaterialPanel.controller.selectCatalogCore(modelData.partNumber)
                }
            }

            Label { text: qsTr("Manual core"); font.bold: true; color: "#1e2b32" }

            GridLayout {
                Layout.fillWidth: true
                columns: 2
                columnSpacing: 10
                rowSpacing: 8

                Label { text: qsTr("Outer diameter (mm)") }
                TextField {
                    id: outerField
                    objectName: "manualCoreOuterField"
                    Layout.fillWidth: true
                    selectByMouse: true
                    activeFocusOnTab: true
                    inputMethodHints: Qt.ImhFormattedNumbersOnly
                    validator: DoubleValidator { bottom: 0.0; notation: DoubleValidator.StandardNotation }
                    Accessible.name: qsTr("Manual core outer diameter in millimetres")
                }
                Label { text: qsTr("Inner diameter (mm)") }
                TextField {
                    id: innerField
                    objectName: "manualCoreInnerField"
                    Layout.fillWidth: true
                    selectByMouse: true
                    activeFocusOnTab: true
                    inputMethodHints: Qt.ImhFormattedNumbersOnly
                    validator: DoubleValidator { bottom: 0.0; notation: DoubleValidator.StandardNotation }
                    Accessible.name: qsTr("Manual core inner diameter in millimetres")
                }
                Label { text: qsTr("Height (mm)") }
                TextField {
                    id: heightField
                    objectName: "manualCoreHeightField"
                    Layout.fillWidth: true
                    selectByMouse: true
                    activeFocusOnTab: true
                    inputMethodHints: Qt.ImhFormattedNumbersOnly
                    validator: DoubleValidator { bottom: 0.0; notation: DoubleValidator.StandardNotation }
                    Accessible.name: qsTr("Manual core height in millimetres")
                }
                Label { text: qsTr("Corner radius (mm)") }
                TextField {
                    id: cornerField
                    objectName: "manualCoreCornerField"
                    Layout.fillWidth: true
                    selectByMouse: true
                    activeFocusOnTab: true
                    inputMethodHints: Qt.ImhFormattedNumbersOnly
                    validator: DoubleValidator { bottom: 0.0; notation: DoubleValidator.StandardNotation }
                    Accessible.name: qsTr("Manual core corner radius in millimetres")
                }
            }

            Button {
                id: applyManualCoreButton
                objectName: "applyManualCoreButton"
                Layout.fillWidth: true
                text: qsTr("Use these manual dimensions")
                activeFocusOnTab: true
                enabled: coreMaterialPanel.controller !== null
                    && outerField.acceptableInput && innerField.acceptableInput
                    && heightField.acceptableInput && cornerField.acceptableInput
                    && outerField.text !== "" && innerField.text !== "" && heightField.text !== ""
                Accessible.name: text
                onClicked: coreMaterialPanel.controller.applyManualCore(
                    Number(outerField.text),
                    Number(innerField.text),
                    Number(heightField.text),
                    cornerField.text === "" ? 0.0 : Number(cornerField.text))
            }

            Rectangle { Layout.fillWidth: true; height: 1; color: "#d8d4cd" }

            Label { text: qsTr("Material revisions"); font.bold: true; color: "#1e2b32" }

            ListView {
                id: materialOptionList
                objectName: "materialOptionList"
                Layout.fillWidth: true
                Layout.preferredHeight: Math.min(180, Math.max(52, count * 52))
                clip: true
                spacing: 6
                model: coreMaterialPanel.controller !== null
                    ? coreMaterialPanel.controller.materialOptions : []
                Accessible.name: qsTr("Material revision list")

                delegate: ItemDelegate {
                    required property var modelData
                    width: ListView.view.width
                    height: 46
                    activeFocusOnTab: true
                    highlighted: coreMaterialPanel.controller !== null
                        && coreMaterialPanel.controller.selectedMaterial.revisionId === modelData.revisionId
                    text: qsTr("%1 %2 %3  ·  %4  ·  %5")
                        .arg(modelData.manufacturer)
                        .arg(modelData.name)
                        .arg(modelData.grade)
                        .arg(modelData.revisionId)
                        .arg(modelData.status)
                    Accessible.name: qsTr("Select material revision %1").arg(modelData.revisionId)
                    onClicked: coreMaterialPanel.controller.selectMaterial(
                        modelData.manufacturer,
                        modelData.name,
                        modelData.grade,
                        modelData.revisionId,
                        modelData.bhSeriesIds.length === 1 ? modelData.bhSeriesIds[0] : "")
                }
            }

            CheckBox {
                id: manualCompatibilityCheckBox
                objectName: "manualCompatibilityCheckBox"
                Layout.fillWidth: true
                visible: coreMaterialPanel.controller !== null
                    && coreMaterialPanel.controller.acknowledgementRequired
                checked: coreMaterialPanel.controller !== null
                    && coreMaterialPanel.controller.acknowledged
                activeFocusOnTab: true
                text: qsTr("I accept that core and material compatibility is my assumption for this manual core")
                Accessible.name: text
                onToggled: coreMaterialPanel.controller.setAcknowledged(checked)
            }

            Button {
                id: clearMaterialButton
                objectName: "clearMaterialButton"
                Layout.fillWidth: true
                text: qsTr("Clear pinned material")
                activeFocusOnTab: true
                enabled: coreMaterialPanel.controller !== null
                    && coreMaterialPanel.controller.selectedMaterial.revisionId !== undefined
                Accessible.name: text
                onClicked: coreMaterialPanel.controller.clearMaterial()
            }

            Button {
                id: openMaterialStudioButton
                objectName: "openMaterialStudioButton"
                Layout.fillWidth: true
                text: qsTr("Open Material Studio")
                activeFocusOnTab: true
                enabled: coreMaterialPanel.controller !== null
                Accessible.name: qsTr("Open Material Studio in a separate window")
                onClicked: coreMaterialPanel.controller.openMaterialStudio()
            }

            Rectangle {
                Layout.fillWidth: true
                color: "#fff4ec"
                radius: 6
                visible: messageLabel.text !== ""
                implicitHeight: messageLabel.implicitHeight + 20

                Label {
                    id: messageLabel
                    objectName: "coreMaterialMessage"
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.margins: 10
                    anchors.verticalCenter: parent.verticalCenter
                    text: coreMaterialPanel.controller !== null
                        ? coreMaterialPanel.controller.message : ""
                    wrapMode: Text.WordWrap
                    color: "#a45528"
                    Accessible.name: text
                }
            }
        }
    }
}
```

The `coreMaterialMessage` label must exist even when empty for the test above,
so keep the `objectName` on the `Label` and let only the surrounding rectangle
hide.

- [ ] **Step 4: Write `MaterialStudioWindow.qml`**

Create `src/inductor_designer/ui/qml/MaterialStudioWindow.qml`, moving the
transaction machinery out of `Main.qml` unchanged in behavior:

```qml
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window

ApplicationWindow {
    id: materialStudioWindow
    objectName: "materialStudioWindow"
    property var controller: null
    property string pendingMaterialAction: ""
    property var pendingMaterialArguments: []
    property bool allowCloseOnce: false
    signal closedAfterEditing()

    width: Math.min(1600, Math.max(1100, Math.round(Screen.width * 0.72)))
    height: Math.min(1000, Math.max(700, Math.round(Screen.height * 0.78)))
    minimumWidth: 900
    minimumHeight: 640
    visible: false
    color: "#f3f1ed"
    title: qsTr("Material Studio")

    function requestMaterialAction(action, arguments_) {
        if (controller !== null && controller.dirty) {
            pendingMaterialAction = action
            pendingMaterialArguments = arguments_
            dirtyMaterialTransactionDialog.open()
            return
        }
        executeMaterialAction(action, arguments_)
    }

    function executeMaterialAction(action, arguments_) {
        if (action === "closeWindow") {
            allowCloseOnce = true
            materialStudioWindow.close()
        } else {
            materialStudioPage.performTransactionAction(action, arguments_)
        }
    }

    function completePendingMaterialAction() {
        const action = pendingMaterialAction
        const arguments_ = pendingMaterialArguments
        pendingMaterialAction = ""
        pendingMaterialArguments = []
        dirtyMaterialTransactionDialog.close()
        executeMaterialAction(action, arguments_)
    }

    function requestClose() {
        requestMaterialAction("closeWindow", [])
    }

    onClosing: function(close) {
        if (allowCloseOnce) {
            allowCloseOnce = false
            close.accepted = true
            materialStudioWindow.closedAfterEditing()
        } else if (controller !== null && controller.dirty) {
            close.accepted = false
            requestMaterialAction("closeWindow", [])
        } else {
            close.accepted = true
            materialStudioWindow.closedAfterEditing()
        }
    }

    Item {
        id: materialStudioHost
        anchors.fill: parent
        anchors.margins: 8

        MaterialStudioPage {
            id: materialStudioPage
            objectName: "materialStudioPage"
            width: materialStudioHost.width
            height: materialStudioHost.height
            controller: materialStudioWindow.controller
            transactionHost: materialStudioWindow
        }
    }

    Dialog {
        id: dirtyMaterialTransactionDialog
        objectName: "dirtyMaterialTransactionDialog"
        anchors.centerIn: parent
        modal: true
        closePolicy: Popup.NoAutoClose
        title: qsTr("Unsaved material changes")

        ColumnLayout {
            Label {
                Layout.preferredWidth: 420
                text: qsTr(
                    "Save the material draft, discard unsaved changes, or cancel the pending action."
                )
                wrapMode: Text.WordWrap
                Accessible.name: text
            }
            RowLayout {
                Layout.alignment: Qt.AlignRight
                Button {
                    objectName: "dirtyMaterialTransactionSaveButton"
                    text: qsTr("Save")
                    enabled: materialStudioWindow.controller !== null
                        && materialStudioWindow.controller.canSave
                    activeFocusOnTab: true
                    Accessible.name: qsTr("Save material changes and continue")
                    onClicked: {
                        materialStudioWindow.controller.saveDraft()
                        if (!materialStudioWindow.controller.dirty) {
                            materialStudioWindow.completePendingMaterialAction()
                        }
                    }
                }
                Button {
                    objectName: "dirtyMaterialTransactionDiscardButton"
                    text: qsTr("Discard")
                    activeFocusOnTab: true
                    Accessible.name: qsTr("Discard material changes and continue")
                    onClicked: {
                        if (materialStudioWindow.controller.discardChanges()) {
                            materialStudioWindow.completePendingMaterialAction()
                        }
                    }
                }
                Button {
                    objectName: "dirtyMaterialTransactionCancelButton"
                    text: qsTr("Cancel")
                    activeFocusOnTab: true
                    Accessible.name: qsTr("Cancel action and keep editing")
                    onClicked: {
                        materialStudioWindow.pendingMaterialAction = ""
                        materialStudioWindow.pendingMaterialArguments = []
                        dirtyMaterialTransactionDialog.close()
                    }
                }
            }
        }
    }
}
```

Late correction: `MaterialStudioPage` is sized by plain `width`/`height`
bindings on the wrapping `materialStudioHost` `Item`, not `anchors.fill:
parent` on the page itself — anchors (and `Layout.fillWidth`/
`Layout.fillHeight`) keep re-imposing this window's geometry on every
`processEvents()` once a previously-hidden window is shown, which
permanently defeats the explicit width override that
`test_material_page_reflows_for_compact_and_wide_windows` relies on.

- [ ] **Step 5: Restructure `Main.qml`**

In `src/inductor_designer/ui/qml/Main.qml`:

- Delete `pendingMaterialAction`, `pendingMaterialArguments`,
  `requestMaterialAction`, `executeMaterialAction`,
  `completePendingMaterialAction`, and the `dirtyMaterialTransactionDialog`
  block: they now live in `MaterialStudioWindow.qml`.
- `requestStep` becomes plain navigation, because Material Studio is no longer a
  step and cannot hold navigation hostage:

```qml
    property bool wideStep: guidedStepList.currentIndex === 2
        || guidedStepList.currentIndex === 4

    function requestStep(index) {
        guidedStepList.currentIndex = index
    }
```

- Rename the eyebrow and title text and the five `ItemDelegate` ids/objectNames:

```qml
    function stepEyebrow() {
        switch (guidedStepList.currentIndex) {
        case 0: return qsTr("Design / Core & Material")
        case 1: return qsTr("Design / Windings")
        case 2: return qsTr("Design / Preliminary")
        case 3: return qsTr("Design / Simulation")
        default: return qsTr("Design / Review")
        }
    }

    function stepTitle() {
        switch (guidedStepList.currentIndex) {
        case 0: return qsTr("Pair a core and material")
        case 1: return qsTr("Define windings")
        case 2: return qsTr("Preliminary estimates")
        case 3: return qsTr("Configure a run")
        default: return qsTr("Review before generation")
        }
    }
```

  Step 0 becomes `id: coreMaterialStep`, `objectName: "coreMaterialStep"`,
  `text: qsTr("Core & Material")`; step 2 becomes `id: preliminaryStep`,
  `objectName: "preliminaryStep"`, `text: qsTr("Preliminary")`. The
  `materialsStep` delegate is deleted, and steps 3 and 4 keep their names.
- Hide the canvas and let the panel take the width on the two wide screens:

```qml
            Rectangle {
                id: canvasCard
                objectName: "canvasCard"
                visible: !window.wideStep
                Layout.fillWidth: true
                Layout.fillHeight: true
```

```qml
            Rectangle {
                id: contextPanel
                objectName: "contextPanel"
                Layout.fillWidth: window.wideStep
                Layout.preferredWidth: window.wideStep
                    ? window.width
                    : Math.max(330, Math.min(410, window.width * 0.29))
                Layout.minimumWidth: 300
```

- Replace the first two `StackLayout` children and leave indexes 2–4 as
  placeholders until Task 15, keeping the
  `currentIndex: guidedStepList.currentIndex` binding and the child order:

```qml
                    CoreMaterialPanel {
                        controller: coreMaterialController
                    }

                    WindingPanel {
                        controller: guidedStudioController
                    }
```

  Late correction: do not set `objectName` at this instantiation site — a QML
  instance-site property assignment overrides the component's own root-level
  assignment, so `objectName: "coreMaterialPanelHost"` here would shadow
  `CoreMaterialPanel.qml`'s own `objectName: "coreMaterialPanel"` and break
  `test_core_material_panel_exposes_both_selectors_and_manual_dimensions`,
  which finds the panel by that name.

  Index 2 is a new placeholder `ScrollView` (the deleted `MaterialStudioPage`
  child sat there), and indexes 3 and 4 keep the existing Simulation and Review
  placeholder blocks. `Main.qml` must load with five children after this task or
  the step rail and the `StackLayout` fall out of step; Task 15 swaps all three
  placeholders for the real pages.
- Add the window and the guard, and wire the refresh:

```qml
    MaterialStudioWindow {
        id: materialStudioWindow
        controller: materialStudioController
        onClosedAfterEditing: {
            if (coreMaterialController !== null) {
                coreMaterialController.refreshLibrary()
            }
        }
    }

    Connections {
        target: coreMaterialController
        function onMaterialStudioRequested() {
            materialStudioWindow.show()
            materialStudioWindow.raise()
            materialStudioWindow.requestActivate()
        }
    }

    onClosing: function(close) {
        if (materialStudioController !== null && materialStudioController.dirty) {
            // Never lose a material draft to an application close: surface the
            // window that owns the unsaved edit and let its dialog decide.
            close.accepted = false
            materialStudioWindow.show()
            materialStudioWindow.requestClose()
        }
    }
```

- Keep the top-bar `Save` button bound to `guidedStudioController.saveDraft()`
  and the status dock bound to `guidedStudioController.statusMessage`.

In `src/inductor_designer/ui/main.py`, extend `create_engine` with
`core_material_controller`, `preliminary_controller`, `simulation_controller`,
`review_controller`, and `project_session` parameters, each set as a context
property under the camelCase name QML uses. Every one defaults to `None` so the
existing tests that call `create_engine()` keep working.

- [ ] **Step 6: Update the two Material Studio test helpers**

In `tests/ui/test_material_studio_workflow.py` and `tests/ui/test_qml_smoke.py`,
replace `root.findChild(QObject, "guidedStepList").setProperty("currentIndex", 2)`
with:

```python
    root.findChild(QObject, "materialStudioWindow").setProperty("visible", True)
```

`findChild` reaches the window because it is a child object of the main window,
so every existing objectName assertion still resolves.

- [ ] **Step 7: Run the UI suite**

Run: `.venv/Scripts/python.exe -m pytest tests -q -m "ui"`
Expected: PASS. A QML error prints as `[qml] ...` on stderr — read it, do not
silence it.

- [ ] **Step 8: Run the gates and commit**

```bash
git add src/inductor_designer/ui tests/ui
git commit -m "feat(ui): pair core and material on step one with Material Studio in its own window"
```

---

### Task 14: Windings screen with native validators and selectors

**Files:**
- Modify: `src/inductor_designer/ui/qml/WindingPanel.qml`
- Test: `tests/ui/test_winding_panel_qml.py`

**Interfaces:**
- Consumes: `GuidedStudioController` properties `windings`, `operatingPoint`,
  `conductorNames`, `conductorModes`, `windingDirections`, `currentDirections`,
  `selectedWindingId`, and slots `setWindingField`, `setOperatingPointField`,
  `addWinding`, `removeWinding`, `selectWinding`.
- Produces objectNames: `operatingFrequencyField`, `windingTemperatureField`,
  `coreTemperatureField`, `windingTurnsField`, `windingLabelField`,
  `windingConductorCombo`, `windingModeCombo`, `windingCurrentField`,
  `windingPhaseField`, `windingDcCurrentField`, `windingCurrentDirectionCombo`,
  `windingStartAngleField`, `windingSectorField`, `windingSpacingField`,
  `windingClearanceField`, `windingDirectionField`, `windingTerminalIntentField`,
  `addWindingButton`, `removeWindingButton`.

- [ ] **Step 1: Write the failing test**

Create `tests/ui/test_winding_panel_qml.py`:

```python
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QSG_RHI_BACKEND", "software")

pytest.importorskip("PySide6")

from PySide6.QtCore import QObject  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

from inductor_designer.ui.guided_studio_controller import (  # noqa: E402
    GuidedStudioController,
)
from inductor_designer.ui.main import create_engine  # noqa: E402
from inductor_designer.ui.project_session import ProjectSession  # noqa: E402
from tests.unit.application.test_geometry_model import CATALOG  # noqa: E402
from tests.unit.domain.test_project import make_project  # noqa: E402

pytestmark = pytest.mark.ui

NUMERIC_FIELDS = (
    "operatingFrequencyField",
    "windingTemperatureField",
    "coreTemperatureField",
    "windingTurnsField",
    "windingCurrentField",
    "windingPhaseField",
    "windingDcCurrentField",
    "windingStartAngleField",
    "windingSectorField",
    "windingSpacingField",
    "windingClearanceField",
)
SELECTORS = (
    "windingConductorCombo",
    "windingModeCombo",
    "windingCurrentDirectionCombo",
    "windingDirectionField",
)


def open_windings() -> tuple[QGuiApplication, QObject, ProjectSession]:
    app = QGuiApplication.instance() or QGuiApplication([])
    session = ProjectSession(make_project())
    engine = create_engine(
        guided_studio_controller=GuidedStudioController(session, CATALOG)
    )
    root = engine.rootObjects()[0]
    root.findChild(QObject, "guidedStepList").setProperty("currentIndex", 1)
    app.processEvents()
    return app, root, session


def test_every_specified_winding_and_operating_point_input_is_present() -> None:
    _, root, _ = open_windings()

    for name in (
        *NUMERIC_FIELDS,
        *SELECTORS,
        "windingLabelField",
        "windingTerminalIntentField",
        "addWindingButton",
        "removeWindingButton",
    ):
        assert root.findChild(QObject, name) is not None, name


def test_numeric_fields_carry_a_native_validator_and_an_accessible_name() -> None:
    _, root, _ = open_windings()

    for name in NUMERIC_FIELDS:
        field = root.findChild(QObject, name)
        assert field.property("validator") is not None, name
        assert field.property("Accessible.name") or field.property("text") is not None


def test_turns_accept_only_integers() -> None:
    _, root, _ = open_windings()
    turns = root.findChild(QObject, "windingTurnsField")

    turns.setProperty("text", "24")
    assert turns.property("acceptableInput") is True

    turns.setProperty("text", "24.5")
    assert turns.property("acceptableInput") is False


def test_negative_values_are_accepted_where_they_are_valid() -> None:
    _, root, _ = open_windings()
    phase = root.findChild(QObject, "windingPhaseField")

    phase.setProperty("text", "-90")

    assert phase.property("acceptableInput") is True


def test_a_negative_dc_current_is_rejected_by_the_editor() -> None:
    _, root, _ = open_windings()
    dc = root.findChild(QObject, "windingDcCurrentField")

    dc.setProperty("text", "-1")

    assert dc.property("acceptableInput") is False


def test_selectors_offer_exactly_the_controller_values() -> None:
    _, root, _ = open_windings()

    assert list(root.findChild(QObject, "windingConductorCombo").property("model")) == [
        "AWG 18"
    ]
    assert list(root.findChild(QObject, "windingModeCombo").property("model")) == [
        "solid",
        "stranded",
    ]
    assert list(
        root.findChild(QObject, "windingCurrentDirectionCombo").property("model")
    ) == ["forward", "reverse"]


def test_the_operating_point_shows_the_shared_project_values() -> None:
    _, root, session = open_windings()

    assert root.findChild(QObject, "operatingFrequencyField").property("text") == str(
        session.project.operating_point.frequency_hz
    )
    assert root.findChild(QObject, "coreTemperatureField").property("text") == str(
        session.project.operating_point.core_temperature_c
    )


def test_remove_is_disabled_for_the_last_winding() -> None:
    _, root, _ = open_windings()

    assert root.findChild(QObject, "removeWindingButton").property("enabled") is False
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/ui/test_winding_panel_qml.py -q`
Expected: FAIL — `operatingFrequencyField` is not found.

- [ ] **Step 3: Rewrite `WindingPanel.qml`**

Replace the body of `src/inductor_designer/ui/qml/WindingPanel.qml`. Keep the
existing `currentWinding`, `refreshFields`, `applyField`, and `Connections`
shape, extend them, and add the shared operating-point section, the two
enumerated selectors that did not exist, and the add/remove buttons:

```qml
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Pane {
    id: windingsPanel
    objectName: "windingsPanel"
    property var controller: null

    function currentWinding() {
        if (controller === null) {
            return ({})
        }
        for (let index = 0; index < controller.windings.length; ++index) {
            if (controller.windings[index].windingId === controller.selectedWindingId) {
                return controller.windings[index]
            }
        }
        return controller.windings.length > 0 ? controller.windings[0] : ({})
    }

    function textOf(value) {
        return value === undefined || value === null ? "" : String(value)
    }

    // Python's str(float) always keeps a decimal point ("25.0"); JS's
    // String(Number) drops it for whole values ("25"). The winding row and
    // operating-point dicts marshal Python floats into plain JS numbers with
    // no type tag, so a whole-valued field (e.g. a 25 C temperature) would
    // otherwise render as "25" and mismatch anything comparing against the
    // domain's own str() formatting. Turns is the only integer-typed field
    // and stays on textOf().
    function numberText(value) {
        if (value === undefined || value === null) {
            return ""
        }
        return Number.isInteger(value) ? value.toFixed(1) : String(value)
    }

    function indexIn(values, value) {
        const position = values.indexOf(value)
        return position < 0 ? 0 : position
    }

    function refreshFields() {
        const item = currentWinding()
        const point = controller === null ? ({}) : controller.operatingPoint
        frequencyField.text = numberText(point.frequencyHz)
        windingTemperatureField.text = numberText(point.windingTemperatureC)
        coreTemperatureField.text = numberText(point.coreTemperatureC)
        turnsField.text = textOf(item.turns)
        labelField.text = textOf(item.label)
        currentField.text = numberText(item.acRmsCurrentA)
        phaseField.text = numberText(item.acPhaseDeg)
        dcCurrentField.text = numberText(item.dcCurrentA)
        startAngleField.text = numberText(item.startAngleDeg)
        sectorField.text = numberText(item.sectorDeg)
        spacingField.text = numberText(item.spacingMm)
        clearanceField.text = numberText(item.clearanceMm)
        terminalIntentField.text = textOf(item.terminalIntent)
        if (controller !== null) {
            conductorCombo.currentIndex = indexIn(controller.conductorNames, item.conductor)
            modeCombo.currentIndex = indexIn(controller.conductorModes, item.mode)
            currentDirectionCombo.currentIndex = indexIn(
                controller.currentDirections, item.currentDirection)
            directionField.currentIndex = indexIn(controller.windingDirections, item.direction)
            windingList.currentIndex = Math.max(0, controller.windings.findIndex(function(row) {
                return row.windingId === controller.selectedWindingId
            }))
        }
    }

    function applyField(field, editor) {
        if (controller !== null
                && !controller.setWindingField(controller.selectedWindingId, field, editor.text)) {
            refreshFields()
        }
    }

    function applyChoice(field, value) {
        if (controller !== null
                && !controller.setWindingField(controller.selectedWindingId, field, value)) {
            refreshFields()
        }
    }

    function applyOperatingPoint(field, editor) {
        if (controller !== null && !controller.setOperatingPointField(field, editor.text)) {
            refreshFields()
        }
    }

    Connections {
        target: windingsPanel.controller
        function onWindingsChanged() { windingsPanel.refreshFields() }
        function onSelectedWindingIdChanged() { windingsPanel.refreshFields() }
        function onOperatingPointChanged() { windingsPanel.refreshFields() }
    }

    Component.onCompleted: refreshFields()

    ScrollView {
        anchors.fill: parent
        clip: true
        contentWidth: availableWidth

        ColumnLayout {
            width: windingsPanel.width - 24
            spacing: 12

            Label {
                text: qsTr("Design / Windings")
                font.pixelSize: 11
                font.letterSpacing: 1.2
                color: "#6d7a7e"
            }
            Label {
                text: qsTr("Define windings")
                font.pixelSize: 24
                font.bold: true
                color: "#1e2b32"
            }
            Label {
                Layout.fillWidth: true
                text: qsTr("One frequency and two temperatures are shared by every winding. Editors block invalid characters; the domain still validates the committed value.")
                wrapMode: Text.WordWrap
                color: "#6d7a7e"
            }

            Label { text: qsTr("Shared operating point"); font.bold: true; color: "#1e2b32" }

            GridLayout {
                Layout.fillWidth: true
                columns: 2
                columnSpacing: 10
                rowSpacing: 8

                Label { text: qsTr("Frequency (Hz)") }
                TextField {
                    id: frequencyField
                    objectName: "operatingFrequencyField"
                    Layout.fillWidth: true
                    selectByMouse: true
                    activeFocusOnTab: true
                    inputMethodHints: Qt.ImhFormattedNumbersOnly
                    validator: DoubleValidator { bottom: 0.0 }
                    Accessible.name: qsTr("Shared frequency in hertz")
                    onEditingFinished: windingsPanel.applyOperatingPoint("frequencyHz", frequencyField)
                }
                Label { text: qsTr("Winding temperature (°C)") }
                TextField {
                    id: windingTemperatureField
                    objectName: "windingTemperatureField"
                    Layout.fillWidth: true
                    selectByMouse: true
                    activeFocusOnTab: true
                    inputMethodHints: Qt.ImhFormattedNumbersOnly
                    validator: DoubleValidator { notation: DoubleValidator.StandardNotation }
                    Accessible.name: qsTr("Winding temperature in degrees Celsius")
                    onEditingFinished: windingsPanel.applyOperatingPoint(
                        "windingTemperatureC", windingTemperatureField)
                }
                Label { text: qsTr("Core temperature (°C)") }
                TextField {
                    id: coreTemperatureField
                    objectName: "coreTemperatureField"
                    Layout.fillWidth: true
                    selectByMouse: true
                    activeFocusOnTab: true
                    inputMethodHints: Qt.ImhFormattedNumbersOnly
                    validator: DoubleValidator { notation: DoubleValidator.StandardNotation }
                    Accessible.name: qsTr("Core temperature in degrees Celsius")
                    onEditingFinished: windingsPanel.applyOperatingPoint(
                        "coreTemperatureC", coreTemperatureField)
                }
            }

            Rectangle { Layout.fillWidth: true; height: 1; color: "#d8d4cd" }

            ListView {
                id: windingList
                objectName: "windingList"
                Layout.fillWidth: true
                Layout.preferredHeight: Math.min(160, Math.max(52, count * 52))
                clip: true
                spacing: 6
                currentIndex: 0
                model: windingsPanel.controller !== null ? windingsPanel.controller.windings : []
                Accessible.name: qsTr("Winding list")

                delegate: ItemDelegate {
                    required property var modelData
                    required property int index
                    width: ListView.view.width
                    height: 46
                    activeFocusOnTab: true
                    highlighted: ListView.isCurrentItem
                    text: qsTr("%1  ·  %2 turns  ·  %3")
                        .arg(modelData.windingId)
                        .arg(modelData.turns)
                        .arg(modelData.conductor)
                    Accessible.name: qsTr("Select winding %1").arg(modelData.windingId)
                    onClicked: {
                        windingList.currentIndex = index
                        windingsPanel.controller.selectWinding(modelData.windingId)
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 8

                Button {
                    id: addWindingButton
                    objectName: "addWindingButton"
                    Layout.fillWidth: true
                    text: qsTr("Add winding")
                    activeFocusOnTab: true
                    enabled: windingsPanel.controller !== null
                    Accessible.name: text
                    onClicked: windingsPanel.controller.addWinding()
                }
                Button {
                    id: removeWindingButton
                    objectName: "removeWindingButton"
                    Layout.fillWidth: true
                    text: qsTr("Remove winding")
                    activeFocusOnTab: true
                    enabled: windingsPanel.controller !== null
                        && windingsPanel.controller.windings.length > 1
                    Accessible.name: qsTr("Remove the selected winding")
                    onClicked: windingsPanel.controller.removeWinding(
                        windingsPanel.controller.selectedWindingId)
                }
            }

            Label {
                Layout.fillWidth: true
                text: {
                    const item = windingsPanel.currentWinding()
                    return item.windingId === undefined
                        ? qsTr("No winding selected")
                        : qsTr("Selected · %1").arg(item.label)
                }
                font.bold: true
                color: "#1e2b32"
            }

            GridLayout {
                Layout.fillWidth: true
                columns: 2
                columnSpacing: 10
                rowSpacing: 8

                Label { text: qsTr("Label") }
                TextField {
                    id: labelField
                    objectName: "windingLabelField"
                    Layout.fillWidth: true
                    selectByMouse: true
                    activeFocusOnTab: true
                    Accessible.name: qsTr("Winding label")
                    onEditingFinished: windingsPanel.applyField("label", labelField)
                }
                Label { text: qsTr("Turns") }
                TextField {
                    id: turnsField
                    objectName: "windingTurnsField"
                    Layout.fillWidth: true
                    selectByMouse: true
                    activeFocusOnTab: true
                    inputMethodHints: Qt.ImhDigitsOnly
                    validator: IntValidator { bottom: 1; top: 100000 }
                    Accessible.name: qsTr("Turn count, integers only")
                    onEditingFinished: windingsPanel.applyField("turns", turnsField)
                }
                Label { text: qsTr("Conductor") }
                ComboBox {
                    id: conductorCombo
                    objectName: "windingConductorCombo"
                    Layout.fillWidth: true
                    activeFocusOnTab: true
                    model: windingsPanel.controller !== null
                        ? windingsPanel.controller.conductorNames : []
                    Accessible.name: qsTr("Conductor")
                    onActivated: windingsPanel.applyChoice("conductor", currentText)
                }
                Label { text: qsTr("Conductor mode") }
                ComboBox {
                    id: modeCombo
                    objectName: "windingModeCombo"
                    Layout.fillWidth: true
                    activeFocusOnTab: true
                    model: windingsPanel.controller !== null
                        ? windingsPanel.controller.conductorModes : []
                    Accessible.name: qsTr("Conductor mode")
                    onActivated: windingsPanel.applyChoice("mode", currentText)
                }
                Label { text: qsTr("AC RMS current (A)") }
                TextField {
                    id: currentField
                    objectName: "windingCurrentField"
                    Layout.fillWidth: true
                    selectByMouse: true
                    activeFocusOnTab: true
                    inputMethodHints: Qt.ImhFormattedNumbersOnly
                    validator: DoubleValidator { bottom: 0.0; notation: DoubleValidator.StandardNotation }
                    Accessible.name: qsTr("AC RMS current in amperes")
                    onEditingFinished: windingsPanel.applyField("acRmsCurrentA", currentField)
                }
                Label { text: qsTr("AC phase (deg)") }
                TextField {
                    id: phaseField
                    objectName: "windingPhaseField"
                    Layout.fillWidth: true
                    selectByMouse: true
                    activeFocusOnTab: true
                    inputMethodHints: Qt.ImhFormattedNumbersOnly
                    validator: DoubleValidator { bottom: -360.0; top: 360.0; notation: DoubleValidator.StandardNotation }
                    Accessible.name: qsTr("AC phase in degrees")
                    onEditingFinished: windingsPanel.applyField("acPhaseDeg", phaseField)
                }
                Label { text: qsTr("DC current (A)") }
                TextField {
                    id: dcCurrentField
                    objectName: "windingDcCurrentField"
                    Layout.fillWidth: true
                    selectByMouse: true
                    activeFocusOnTab: true
                    inputMethodHints: Qt.ImhFormattedNumbersOnly
                    validator: DoubleValidator { bottom: 0.0; notation: DoubleValidator.StandardNotation }
                    Accessible.name: qsTr("DC current in amperes")
                    onEditingFinished: windingsPanel.applyField("dcCurrentA", dcCurrentField)
                }
                Label { text: qsTr("Current direction") }
                ComboBox {
                    id: currentDirectionCombo
                    objectName: "windingCurrentDirectionCombo"
                    Layout.fillWidth: true
                    activeFocusOnTab: true
                    model: windingsPanel.controller !== null
                        ? windingsPanel.controller.currentDirections : []
                    Accessible.name: qsTr("Current direction")
                    onActivated: windingsPanel.applyChoice("currentDirection", currentText)
                }
                Label { text: qsTr("Start angle (deg)") }
                TextField {
                    id: startAngleField
                    objectName: "windingStartAngleField"
                    Layout.fillWidth: true
                    selectByMouse: true
                    activeFocusOnTab: true
                    inputMethodHints: Qt.ImhFormattedNumbersOnly
                    validator: DoubleValidator { bottom: 0.0; top: 359.999; notation: DoubleValidator.StandardNotation }
                    Accessible.name: qsTr("Start angle in degrees")
                    onEditingFinished: windingsPanel.applyField("startAngleDeg", startAngleField)
                }
                Label { text: qsTr("Sector (deg)") }
                TextField {
                    id: sectorField
                    objectName: "windingSectorField"
                    Layout.fillWidth: true
                    selectByMouse: true
                    activeFocusOnTab: true
                    inputMethodHints: Qt.ImhFormattedNumbersOnly
                    validator: DoubleValidator { bottom: 0.0; top: 360.0; notation: DoubleValidator.StandardNotation }
                    Accessible.name: qsTr("Sector span in degrees")
                    onEditingFinished: windingsPanel.applyField("sectorDeg", sectorField)
                }
                Label { text: qsTr("Spacing (mm)") }
                TextField {
                    id: spacingField
                    objectName: "windingSpacingField"
                    Layout.fillWidth: true
                    selectByMouse: true
                    activeFocusOnTab: true
                    inputMethodHints: Qt.ImhFormattedNumbersOnly
                    validator: DoubleValidator { bottom: 0.0; notation: DoubleValidator.StandardNotation }
                    Accessible.name: qsTr("Minimum turn spacing in millimetres")
                    onEditingFinished: windingsPanel.applyField("spacingMm", spacingField)
                }
                Label { text: qsTr("Clearance (mm)") }
                TextField {
                    id: clearanceField
                    objectName: "windingClearanceField"
                    Layout.fillWidth: true
                    selectByMouse: true
                    activeFocusOnTab: true
                    inputMethodHints: Qt.ImhFormattedNumbersOnly
                    validator: DoubleValidator { bottom: 0.0; notation: DoubleValidator.StandardNotation }
                    Accessible.name: qsTr("Minimum clearance in millimetres")
                    onEditingFinished: windingsPanel.applyField("clearanceMm", clearanceField)
                }
                Label { text: qsTr("Winding direction") }
                ComboBox {
                    id: directionField
                    objectName: "windingDirectionField"
                    Layout.fillWidth: true
                    activeFocusOnTab: true
                    model: windingsPanel.controller !== null
                        ? windingsPanel.controller.windingDirections : []
                    Accessible.name: qsTr("Winding direction")
                    onActivated: windingsPanel.applyChoice("direction", currentText)
                }
                Label { text: qsTr("Terminal intent") }
                TextField {
                    id: terminalIntentField
                    objectName: "windingTerminalIntentField"
                    Layout.fillWidth: true
                    selectByMouse: true
                    activeFocusOnTab: true
                    Accessible.name: qsTr("Terminal intent, free text")
                    onEditingFinished: windingsPanel.applyField("terminalIntent", terminalIntentField)
                }
            }

            Rectangle {
                Layout.fillWidth: true
                color: "#fff4ec"
                radius: 6
                implicitHeight: clearanceText.implicitHeight + 20

                Label {
                    id: clearanceText
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.margins: 10
                    anchors.verticalCenter: parent.verticalCenter
                    text: qsTr("Clearance and spacing are checked against the real core and conductor geometry before an edit is accepted.")
                    wrapMode: Text.WordWrap
                    color: "#a45528"
                    Accessible.name: text
                }
            }
        }
    }
}
```

Each editor declares its validator inline; there is no shared component to keep
in sync. The `IntValidator` on turns is what makes `24.5` unacceptable, and the
`bottom: 0.0` `DoubleValidator` on the DC current is what rejects `-1` before it
reaches the controller.

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/ui/test_winding_panel_qml.py -q`
Expected: PASS, 8 tests.

- [ ] **Step 5: Run the gates and commit**

```bash
git add src/inductor_designer/ui/qml/WindingPanel.qml tests/ui/test_winding_panel_qml.py
git commit -m "feat(ui): validate winding inputs natively and edit the shared operating point"
```

---

### Task 15: The Preliminary, Simulation, and Review screens

**Files:**
- Create: `src/inductor_designer/ui/qml/PreliminaryPage.qml`
- Create: `src/inductor_designer/ui/qml/SimulationPanel.qml`
- Create: `src/inductor_designer/ui/qml/ReviewPage.qml`
- Modify: `src/inductor_designer/ui/qml/Main.qml` (replace the three placeholders)
- Test: `tests/ui/test_flow_screens_qml.py`

**Interfaces:**
- Consumes: `PreliminaryController`, `SimulationController`,
  `GenerationController`, `ReviewController`.
- Produces objectNames: `preliminaryPage`, `preliminaryCoreTable`,
  `preliminaryWindingTable`, `preliminaryTotalsTable`, `preliminaryAssumptions`,
  `preliminaryMaterialLabel`, `preliminaryGeometryIssues`;
  `simulationPanel`, `simulationBackendCombo`, `simulationModeLabel`,
  `simulationMeshIntentCombo`, `simulationMaximumPassesField`,
  `simulationPercentErrorField`, `simulationRequestedOutputs`,
  `showSolverWindowCheckBox`, `showSolverWindowReason`,
  `simulationGenerateButton`, `simulationBlockedReason`;
  `reviewPage`, `reviewSections`, `reviewFindings`, `openGeneratedFileButton`,
  `openRunFolderButton`, `reviewMessage`.

- [ ] **Step 1: Write the failing test**

Create `tests/ui/test_flow_screens_qml.py`:

```python
from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QSG_RHI_BACKEND", "software")

pytest.importorskip("PySide6")

from PySide6.QtCore import QObject  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

from inductor_designer.simulation.capabilities import (  # noqa: E402
    AedtEdition,
    AedtRelease,
    CapabilityReviewStatus,
    CapabilitySnapshot,
)
from inductor_designer.ui.generation_controller import GenerationController  # noqa: E402
from inductor_designer.ui.main import create_engine  # noqa: E402
from inductor_designer.ui.preliminary_controller import (  # noqa: E402
    PreliminaryController,
)
from inductor_designer.ui.project_session import ProjectSession  # noqa: E402
from inductor_designer.ui.review_controller import ReviewController  # noqa: E402
from inductor_designer.ui.simulation_controller import (  # noqa: E402
    SimulationController,
)
from tests.unit.application.test_geometry_model import CATALOG  # noqa: E402
from tests.unit.domain.test_project import (  # noqa: E402
    make_material_record,
    make_project_with_material,
)

pytestmark = pytest.mark.ui

SUPPORTED = CapabilitySnapshot(
    release=AedtRelease(2025, 2),
    edition=AedtEdition.COMMERCIAL,
    include_dc_fields_3d=True,
    discovered_limits=(),
    evidence_source="test",
    review_status=CapabilityReviewStatus.REVIEWED,
)


class RecordingOpener:
    def __init__(self) -> None:
        self.opened: list[Path] = []

    def open_path(self, path: Path) -> None:
        self.opened.append(path)


# QQmlApplicationEngine owns the window it loads: once the Python wrapper for
# the engine is garbage collected, the root window (and everything under it)
# is destroyed too, even though `root` is still referenced by the caller.
# Pin the engine and every controller passed to it for the test process
# lifetime instead of letting them drop the moment the helper returns.
_ENGINES: list[object] = []


def open_flow(step: int, *, dirty: bool = False):
    app = QGuiApplication.instance() or QGuiApplication([])
    session = ProjectSession(
        make_project_with_material(), Path("boost.inductor.json"), lambda project: None
    )
    preliminary = PreliminaryController(session, CATALOG)
    generation = GenerationController(lambda label, show: ("done",))
    simulation = SimulationController(session, generation, SUPPORTED)
    review = ReviewController(
        session, preliminary, generation, CATALOG, RecordingOpener()
    )
    if dirty:
        session.apply(replace(session.project, description="edited"))
    engine = create_engine(
        preliminary_controller=preliminary,
        simulation_controller=simulation,
        review_controller=review,
        generation_controller=generation,
        project_session=session,
    )
    _ENGINES.append((engine, preliminary, generation, simulation, review))
    root = engine.rootObjects()[0]
    root.findChild(QObject, "guidedStepList").setProperty("currentIndex", step)
    app.processEvents()
    return app, root, session


def test_preliminary_page_shows_core_winding_totals_and_assumptions() -> None:
    _, root, _ = open_flow(2)

    for name in (
        "preliminaryPage",
        "preliminaryCoreTable",
        "preliminaryWindingTable",
        "preliminaryTotalsTable",
        "preliminaryAssumptions",
        "preliminaryMaterialLabel",
    ):
        assert root.findChild(QObject, name) is not None, name
    assert root.findChild(QObject, "preliminaryCoreTable").property("count") == 6
    assert root.findChild(QObject, "preliminaryTotalsTable").property("count") == 3
    assert (
        make_material_record().revision_id
        in root.findChild(QObject, "preliminaryMaterialLabel").property("text")
    )


def test_simulation_panel_exposes_every_run_choice() -> None:
    _, root, _ = open_flow(3)

    for name in (
        "simulationPanel",
        "simulationBackendCombo",
        "simulationModeLabel",
        "simulationMeshIntentCombo",
        "simulationMaximumPassesField",
        "simulationPercentErrorField",
        "simulationRequestedOutputs",
        "showSolverWindowCheckBox",
        "simulationGenerateButton",
    ):
        assert root.findChild(QObject, name) is not None, name
    assert root.findChild(QObject, "showSolverWindowCheckBox").property("enabled") is True


def test_generate_is_disabled_and_explained_while_the_project_is_dirty() -> None:
    _, root, _ = open_flow(3, dirty=True)

    assert root.findChild(QObject, "simulationGenerateButton").property("enabled") is False
    reason = root.findChild(QObject, "simulationBlockedReason")
    assert reason is not None
    assert "save" in reason.property("text").casefold()


def test_review_page_lists_sections_and_disabled_open_actions() -> None:
    _, root, _ = open_flow(4)

    for name in (
        "reviewPage",
        "reviewSections",
        "reviewFindings",
        "openGeneratedFileButton",
        "openRunFolderButton",
        "reviewMessage",
    ):
        assert root.findChild(QObject, name) is not None, name
    assert root.findChild(QObject, "reviewSections").property("count") == 5
    assert root.findChild(QObject, "openGeneratedFileButton").property("enabled") is False
    assert root.findChild(QObject, "openRunFolderButton").property("enabled") is False
```

Late correction: `open_flow` must keep a module-level reference to each
`engine` it creates (the `_ENGINES` list above), not just to `root` — a
`QQmlApplicationEngine` owns the root window it loads, so once the Python
wrapper for the engine is garbage collected the window is destroyed too,
even though the test still holds `root`.

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/ui/test_flow_screens_qml.py -q`
Expected: FAIL — `preliminaryPage` is not found.

- [ ] **Step 3: Write `PreliminaryPage.qml`**

Create `src/inductor_designer/ui/qml/PreliminaryPage.qml`:

```qml
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Pane {
    id: preliminaryPage
    objectName: "preliminaryPage"
    property var controller: null

    function stateColor(state) {
        return state === "estimated" ? "#157a61" : state === "invalid" ? "#a4282d" : "#a45528"
    }

    ScrollView {
        anchors.fill: parent
        clip: true
        contentWidth: availableWidth

        ColumnLayout {
            width: preliminaryPage.width - 24
            spacing: 12

            Label {
                text: qsTr("Design / Preliminary")
                font.pixelSize: 11
                font.letterSpacing: 1.2
                color: "#6d7a7e"
            }
            Label {
                text: qsTr("Preliminary estimates")
                font.pixelSize: 24
                font.bold: true
                color: "#1e2b32"
            }
            Label {
                Layout.fillWidth: true
                text: qsTr("Read-only, solver-independent estimates. No Maxwell or FEMM run is started. These values never claim solver accuracy.")
                wrapMode: Text.WordWrap
                color: "#6d7a7e"
            }
            Label {
                objectName: "preliminaryMaterialLabel"
                Layout.fillWidth: true
                text: controller === null
                    ? qsTr("No material revision selected")
                    : qsTr("Material revision %1 · B-H series %2")
                        .arg(controller.materialRevisionId === "" ? qsTr("not selected") : controller.materialRevisionId)
                        .arg(controller.bhSeriesId === "" ? qsTr("not selected") : controller.bhSeriesId)
                wrapMode: Text.WordWrap
                color: "#1e2b32"
                Accessible.name: text
            }

            Label { text: qsTr("Core summary"); font.bold: true; color: "#1e2b32" }

            ListView {
                id: coreTable
                objectName: "preliminaryCoreTable"
                Layout.fillWidth: true
                Layout.preferredHeight: Math.max(40, count * 40)
                interactive: false
                model: preliminaryPage.controller !== null ? preliminaryPage.controller.coreRows : []
                Accessible.name: qsTr("Core preliminary results")

                delegate: RowLayout {
                    required property var modelData
                    width: ListView.view.width
                    height: 40
                    spacing: 8
                    Label {
                        Layout.preferredWidth: 220
                        text: modelData.label
                        color: "#6d7a7e"
                    }
                    Label {
                        Layout.preferredWidth: 140
                        text: modelData.text
                        font.bold: true
                        color: preliminaryPage.stateColor(modelData.state)
                        Accessible.name: qsTr("%1 is %2").arg(modelData.label).arg(modelData.text)
                    }
                    Label {
                        Layout.fillWidth: true
                        text: modelData.code === "" ? "" : qsTr("%1 — %2").arg(modelData.code).arg(modelData.message)
                        wrapMode: Text.WordWrap
                        elide: Text.ElideRight
                        color: "#a45528"
                        Accessible.name: text
                    }
                }
            }

            Label { text: qsTr("Windings"); font.bold: true; color: "#1e2b32" }

            RowLayout {
                Layout.fillWidth: true
                spacing: 8
                Label { Layout.preferredWidth: 70; text: qsTr("Winding"); color: "#6d7a7e" }
                Label { Layout.preferredWidth: 110; text: qsTr("Copper area"); color: "#6d7a7e" }
                Label { Layout.preferredWidth: 110; text: qsTr("Wire length"); color: "#6d7a7e" }
                Label { Layout.preferredWidth: 110; text: qsTr("Resistance"); color: "#6d7a7e" }
                Label { Layout.preferredWidth: 110; text: qsTr("J AC RMS"); color: "#6d7a7e" }
                Label { Layout.preferredWidth: 110; text: qsTr("J AC peak"); color: "#6d7a7e" }
                Label { Layout.preferredWidth: 110; text: qsTr("J DC"); color: "#6d7a7e" }
                Label { Layout.fillWidth: true; text: qsTr("Wire loss"); color: "#6d7a7e" }
            }

            ListView {
                id: windingTable
                objectName: "preliminaryWindingTable"
                Layout.fillWidth: true
                Layout.preferredHeight: Math.max(40, count * 64)
                interactive: false
                model: preliminaryPage.controller !== null ? preliminaryPage.controller.windingRows : []
                Accessible.name: qsTr("Per-winding preliminary results")

                delegate: ColumnLayout {
                    required property var modelData
                    width: ListView.view.width
                    spacing: 2

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        Label { Layout.preferredWidth: 70; text: modelData.windingId; font.bold: true }
                        Label {
                            Layout.preferredWidth: 110
                            text: modelData.conductorArea.text
                            color: preliminaryPage.stateColor(modelData.conductorArea.state)
                        }
                        Label {
                            Layout.preferredWidth: 110
                            text: modelData.wireLength.text
                            color: preliminaryPage.stateColor(modelData.wireLength.state)
                        }
                        Label {
                            Layout.preferredWidth: 110
                            text: modelData.resistance.text
                            color: preliminaryPage.stateColor(modelData.resistance.state)
                        }
                        Label {
                            Layout.preferredWidth: 110
                            text: modelData.jAcRms.text
                            color: preliminaryPage.stateColor(modelData.jAcRms.state)
                        }
                        Label {
                            Layout.preferredWidth: 110
                            text: modelData.jAcPeak.text
                            color: preliminaryPage.stateColor(modelData.jAcPeak.state)
                        }
                        Label {
                            Layout.preferredWidth: 110
                            text: modelData.jDc.text
                            color: preliminaryPage.stateColor(modelData.jDc.state)
                        }
                        Label {
                            Layout.fillWidth: true
                            text: modelData.wireLoss.text
                            color: preliminaryPage.stateColor(modelData.wireLoss.state)
                        }
                    }
                    Label {
                        Layout.fillWidth: true
                        visible: modelData.wireLoss.message !== "" || modelData.jAcRms.message !== ""
                        text: modelData.wireLoss.message !== ""
                            ? qsTr("%1 — %2").arg(modelData.wireLoss.code).arg(modelData.wireLoss.message)
                            : qsTr("%1 — %2").arg(modelData.jAcRms.code).arg(modelData.jAcRms.message)
                        wrapMode: Text.WordWrap
                        color: "#a45528"
                        font.pixelSize: 11
                        Accessible.name: text
                    }
                }
            }

            Label { text: qsTr("Totals"); font.bold: true; color: "#1e2b32" }

            ListView {
                id: totalsTable
                objectName: "preliminaryTotalsTable"
                Layout.fillWidth: true
                Layout.preferredHeight: Math.max(40, count * 40)
                interactive: false
                model: preliminaryPage.controller !== null ? preliminaryPage.controller.totalRows : []
                Accessible.name: qsTr("Preliminary loss totals")

                delegate: RowLayout {
                    required property var modelData
                    width: ListView.view.width
                    height: 40
                    spacing: 8
                    Label { Layout.preferredWidth: 220; text: modelData.label; color: "#6d7a7e" }
                    Label {
                        Layout.preferredWidth: 140
                        text: modelData.text
                        font.bold: true
                        color: preliminaryPage.stateColor(modelData.state)
                    }
                    Label {
                        Layout.fillWidth: true
                        text: modelData.code === "" ? "" : qsTr("%1 — %2").arg(modelData.code).arg(modelData.message)
                        wrapMode: Text.WordWrap
                        color: "#a45528"
                    }
                }
            }

            Rectangle {
                Layout.fillWidth: true
                color: "#fff4ec"
                radius: 6
                visible: geometryIssues.count > 0
                implicitHeight: geometryIssues.contentHeight + 20

                ListView {
                    id: geometryIssues
                    objectName: "preliminaryGeometryIssues"
                    anchors.fill: parent
                    anchors.margins: 10
                    interactive: false
                    model: preliminaryPage.controller !== null ? preliminaryPage.controller.geometryIssues : []
                    Accessible.name: qsTr("Geometry issues")
                    delegate: Label {
                        required property string modelData
                        width: ListView.view.width
                        text: qsTr("Geometry: %1").arg(modelData)
                        wrapMode: Text.WordWrap
                        color: "#a45528"
                    }
                }
            }

            Label { text: qsTr("Assumptions and excluded effects"); font.bold: true; color: "#1e2b32" }

            ListView {
                id: assumptions
                objectName: "preliminaryAssumptions"
                Layout.fillWidth: true
                Layout.preferredHeight: Math.max(24, contentHeight)
                interactive: false
                model: preliminaryPage.controller !== null ? preliminaryPage.controller.assumptions : []
                Accessible.name: qsTr("Preliminary assumptions")
                delegate: Label {
                    required property string modelData
                    width: ListView.view.width
                    text: qsTr("• %1").arg(modelData)
                    wrapMode: Text.WordWrap
                    color: "#6d7a7e"
                }
            }
        }
    }
}
```

- [ ] **Step 4: Write `SimulationPanel.qml`**

Create `src/inductor_designer/ui/qml/SimulationPanel.qml`:

```qml
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Pane {
    id: simulationPanel
    objectName: "simulationPanel"
    property var controller: null
    property var generation: null

    function floatText(value) {
        // JS String() drops the trailing .0 that Python's str(float) keeps, so a
        // percent error of 1.0 would render as "1".
        return Number.isInteger(value) ? value.toFixed(1) : String(value)
    }

    function refreshFields() {
        if (controller === null) {
            return
        }
        passesField.text = String(controller.maximumPasses)
        percentErrorField.text = floatText(controller.percentError)
        backendCombo.currentIndex = Math.max(0, controller.backendOptions.indexOf(controller.backend))
        meshCombo.currentIndex = Math.max(0, controller.meshIntentOptions.indexOf(controller.meshIntent))
    }

    Connections {
        target: simulationPanel.controller
        function onConfigurationChanged() { simulationPanel.refreshFields() }
    }

    Component.onCompleted: refreshFields()

    ScrollView {
        anchors.fill: parent
        clip: true
        contentWidth: availableWidth

        ColumnLayout {
            width: simulationPanel.width - 24
            spacing: 12

            Label {
                text: qsTr("Design / Simulation")
                font.pixelSize: 11
                font.letterSpacing: 1.2
                color: "#6d7a7e"
            }
            Label {
                text: qsTr("Configure a run")
                font.pixelSize: 24
                font.bold: true
                color: "#1e2b32"
            }
            Label {
                Layout.fillWidth: true
                text: qsTr("Frequency and temperature belong to the shared operating point on the Windings screen and are not repeated here.")
                wrapMode: Text.WordWrap
                color: "#6d7a7e"
            }

            Label { text: qsTr("Backend") }
            ComboBox {
                id: backendCombo
                objectName: "simulationBackendCombo"
                Layout.fillWidth: true
                activeFocusOnTab: true
                model: simulationPanel.controller !== null ? simulationPanel.controller.backendOptions : []
                Accessible.name: qsTr("Solver backend")
                onActivated: simulationPanel.controller.setBackend(currentText)
            }

            Label {
                objectName: "simulationModeLabel"
                Layout.fillWidth: true
                text: simulationPanel.controller === null
                    ? ""
                    : qsTr("Run mode: %1 — %2")
                        .arg(simulationPanel.controller.modeLabel)
                        .arg(simulationPanel.controller.modeNote)
                wrapMode: Text.WordWrap
                color: "#6d7a7e"
                Accessible.name: text
            }

            Label { text: qsTr("Mesh intent") }
            ComboBox {
                id: meshCombo
                objectName: "simulationMeshIntentCombo"
                Layout.fillWidth: true
                activeFocusOnTab: true
                model: simulationPanel.controller !== null ? simulationPanel.controller.meshIntentOptions : []
                Accessible.name: qsTr("Mesh intent")
                onActivated: simulationPanel.controller.setMeshIntent(currentText)
            }

            GridLayout {
                Layout.fillWidth: true
                columns: 2
                columnSpacing: 10
                rowSpacing: 8

                Label { text: qsTr("Maximum passes") }
                TextField {
                    id: passesField
                    objectName: "simulationMaximumPassesField"
                    Layout.fillWidth: true
                    selectByMouse: true
                    activeFocusOnTab: true
                    inputMethodHints: Qt.ImhDigitsOnly
                    validator: IntValidator { bottom: 1; top: 1000 }
                    Accessible.name: qsTr("Maximum adaptive passes")
                    onEditingFinished: {
                        if (!simulationPanel.controller.setMaximumPasses(text)) {
                            simulationPanel.refreshFields()
                        }
                    }
                }
                Label { text: qsTr("Percent error") }
                TextField {
                    id: percentErrorField
                    objectName: "simulationPercentErrorField"
                    Layout.fillWidth: true
                    selectByMouse: true
                    activeFocusOnTab: true
                    inputMethodHints: Qt.ImhFormattedNumbersOnly
                    validator: DoubleValidator { bottom: 0.0; notation: DoubleValidator.StandardNotation }
                    Accessible.name: qsTr("Convergence percent error")
                    onEditingFinished: {
                        if (!simulationPanel.controller.setPercentError(text)) {
                            simulationPanel.refreshFields()
                        }
                    }
                }
            }

            Label { text: qsTr("Requested outputs"); font.bold: true; color: "#1e2b32" }

            ListView {
                id: requestedOutputs
                objectName: "simulationRequestedOutputs"
                Layout.fillWidth: true
                Layout.preferredHeight: Math.max(32, count * 32)
                interactive: false
                model: simulationPanel.controller !== null ? simulationPanel.controller.requestedOutputs : []
                Accessible.name: qsTr("Requested solver outputs")

                delegate: CheckBox {
                    required property var modelData
                    width: ListView.view.width
                    height: 32
                    activeFocusOnTab: true
                    text: modelData.label
                    checked: modelData.selected
                    Accessible.name: qsTr("Request %1").arg(modelData.label)
                    onToggled: simulationPanel.controller.toggleRequestedOutput(modelData.value, checked)
                }
            }

            CheckBox {
                id: showSolverWindowCheckBox
                objectName: "showSolverWindowCheckBox"
                Layout.fillWidth: true
                activeFocusOnTab: true
                text: qsTr("Show solver window")
                enabled: simulationPanel.controller !== null
                    && simulationPanel.controller.visibleWindowSupported
                checked: simulationPanel.controller !== null
                    && simulationPanel.controller.showSolverWindow
                Accessible.name: qsTr("Show the solver window for this run")
                onToggled: {
                    if (!simulationPanel.controller.setShowSolverWindow(checked)) {
                        checked = simulationPanel.controller.showSolverWindow
                    }
                }
            }

            Label {
                objectName: "showSolverWindowReason"
                Layout.fillWidth: true
                visible: text !== ""
                text: simulationPanel.controller === null
                    ? ""
                    : simulationPanel.controller.visibleWindowReason
                wrapMode: Text.WordWrap
                color: "#a45528"
                Accessible.name: text
            }

            Button {
                objectName: "simulationGenerateButton"
                Layout.fillWidth: true
                activeFocusOnTab: true
                text: simulationPanel.generation !== null && simulationPanel.generation.busy
                    ? qsTr("Generating…") : qsTr("Generate project")
                enabled: simulationPanel.controller !== null && simulationPanel.controller.canGenerate
                Accessible.name: qsTr("Generate the solver project")
                onClicked: simulationPanel.controller.generate()
            }

            Label {
                objectName: "simulationBlockedReason"
                Layout.fillWidth: true
                visible: text !== ""
                text: simulationPanel.controller === null ? "" : simulationPanel.controller.blockedReason
                wrapMode: Text.WordWrap
                color: "#a45528"
                Accessible.name: text
            }

            ListView {
                objectName: "simulationRunLog"
                Layout.fillWidth: true
                Layout.preferredHeight: Math.min(180, Math.max(0, count * 22))
                clip: true
                model: simulationPanel.generation !== null ? simulationPanel.generation.lines : []
                Accessible.name: qsTr("Generation log")
                delegate: Label {
                    required property string modelData
                    width: ListView.view.width
                    text: modelData
                    elide: Text.ElideRight
                    font.pixelSize: 11
                    color: "#1e2b32"
                }
            }
        }
    }
}
```

- [ ] **Step 5: Write `ReviewPage.qml`**

Create `src/inductor_designer/ui/qml/ReviewPage.qml`:

```qml
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Pane {
    id: reviewPage
    objectName: "reviewPage"
    property var controller: null

    ScrollView {
        anchors.fill: parent
        clip: true
        contentWidth: availableWidth

        ColumnLayout {
            width: reviewPage.width - 24
            spacing: 12

            Label {
                text: qsTr("Design / Review")
                font.pixelSize: 11
                font.letterSpacing: 1.2
                color: "#6d7a7e"
            }
            Label {
                text: qsTr("Review before generation")
                font.pixelSize: 24
                font.bold: true
                color: "#1e2b32"
            }
            Label {
                Layout.fillWidth: true
                text: qsTr("The generated solver project is an independent output. Edits made inside Maxwell or FEMM are never imported back into the project document.")
                wrapMode: Text.WordWrap
                color: "#6d7a7e"
            }

            ListView {
                id: sections
                objectName: "reviewSections"
                Layout.fillWidth: true
                Layout.preferredHeight: contentHeight
                interactive: false
                model: reviewPage.controller !== null ? reviewPage.controller.sections : []
                Accessible.name: qsTr("Review sections")

                delegate: ColumnLayout {
                    required property var modelData
                    width: ListView.view.width
                    spacing: 4

                    Label {
                        text: modelData.title
                        font.bold: true
                        color: "#1e2b32"
                        Accessible.name: text
                    }
                    Repeater {
                        model: modelData.rows
                        delegate: RowLayout {
                            required property var modelData
                            width: parent.width
                            spacing: 8
                            Label {
                                Layout.preferredWidth: 240
                                text: modelData.label
                                color: "#6d7a7e"
                                wrapMode: Text.WordWrap
                            }
                            Label {
                                Layout.fillWidth: true
                                text: modelData.text
                                color: "#1e2b32"
                                wrapMode: Text.WordWrap
                                Accessible.name: qsTr("%1: %2").arg(modelData.label).arg(modelData.text)
                            }
                        }
                    }
                    Rectangle { Layout.fillWidth: true; height: 1; color: "#d8d4cd" }
                }
            }

            Label { text: qsTr("Validation findings"); font.bold: true; color: "#1e2b32" }

            ListView {
                id: findings
                objectName: "reviewFindings"
                Layout.fillWidth: true
                Layout.preferredHeight: Math.max(24, contentHeight)
                interactive: false
                model: reviewPage.controller !== null ? reviewPage.controller.findings : []
                Accessible.name: qsTr("Validation findings")
                delegate: Label {
                    required property var modelData
                    width: ListView.view.width
                    text: qsTr("%1 · %2 — %3")
                        .arg(modelData.category)
                        .arg(modelData.code)
                        .arg(modelData.message)
                    wrapMode: Text.WordWrap
                    color: modelData.category === "error" ? "#a4282d" : "#6d7a7e"
                    Accessible.name: text
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 8

                Button {
                    objectName: "openGeneratedFileButton"
                    Layout.fillWidth: true
                    activeFocusOnTab: true
                    text: qsTr("Open generated file")
                    enabled: reviewPage.controller !== null && reviewPage.controller.canOpenGeneratedFile
                    Accessible.name: qsTr("Open the generated solver project")
                    onClicked: reviewPage.controller.openGeneratedFile()
                }
                Button {
                    objectName: "openRunFolderButton"
                    Layout.fillWidth: true
                    activeFocusOnTab: true
                    text: qsTr("Open run folder")
                    enabled: reviewPage.controller !== null && reviewPage.controller.canOpenRunFolder
                    Accessible.name: qsTr("Open the run folder")
                    onClicked: reviewPage.controller.openRunFolder()
                }
            }

            Label {
                objectName: "reviewMessage"
                Layout.fillWidth: true
                text: reviewPage.controller === null ? "" : reviewPage.controller.message
                wrapMode: Text.WordWrap
                color: "#a45528"
                Accessible.name: text
            }
        }
    }
}
```

- [ ] **Step 6: Replace the three placeholders in `Main.qml`**

Swap the placeholder `ScrollView` blocks for `PreliminaryPage { controller:
preliminaryController }`, `SimulationPanel { controller: simulationController;
generation: generationController }`, and `ReviewPage { controller:
reviewController }`, in that order, so `StackLayout` index still matches the step
index.

- [ ] **Step 7: Run the UI suite**

Run: `.venv/Scripts/python.exe -m pytest tests -q -m "ui"`
Expected: PASS. Read every `[qml]` line on stderr; a binding error there is a
real defect even when the assertions pass.

- [ ] **Step 8: Run the gates and commit**

```bash
git add src/inductor_designer/ui/qml tests/ui/test_flow_screens_qml.py
git commit -m "feat(ui): add the Preliminary, Simulation, and Review screens"
```

---

### Task 16: Wire the application, prove the flow, and update the docs

**Files:**
- Modify: `src/inductor_designer/ui/main.py`
- Create: `tests/integration/test_guided_studio_flow.py`
- Modify: `docs/superpowers/plans/README.md:57-61`
- Modify: `docs/development/ROADMAP.md`
- Modify: `README.md` (Guided Studio description, if it names the old steps)

**Interfaces:**
- Consumes: every controller from Tasks 4–12, `DesktopPathOpener`,
  `MatrixCapabilityRepository`, `SqliteCatalogRepository`,
  `FileOverlayMaterialRepository`.
- Produces: a fully wired `main()`; no new public interface.

- [ ] **Step 1: Write the failing integration test**

Create `tests/integration/test_guided_studio_flow.py`:

```python
"""Specification section 11: the acceptance walk, without Qt, Maxwell, or FEMM.

The controllers are Qt objects, so this test needs an offscreen QGuiApplication,
but it starts no solver: it proves the flow's state transitions end to end
against the real catalog and the real material overlay.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtGui import QGuiApplication  # noqa: E402

from inductor_designer.adapters.catalog.sqlite_repository import (  # noqa: E402
    SqliteCatalogRepository,
)
from inductor_designer.adapters.materials.overlay_repository import (  # noqa: E402
    FileOverlayMaterialRepository,
)
from inductor_designer.materials.identity import MaterialRef  # noqa: E402
from inductor_designer.materials.records import MaterialRecord, SeriesKind  # noqa: E402
from inductor_designer.simulation.preliminary_contracts import ResultState  # noqa: E402
from inductor_designer.ui.core_material_controller import (  # noqa: E402
    CoreMaterialController,
)
from inductor_designer.ui.guided_studio_controller import (  # noqa: E402
    GuidedStudioController,
)
from inductor_designer.ui.preliminary_controller import (  # noqa: E402
    PreliminaryController,
)
from inductor_designer.ui.project_session import ProjectSession  # noqa: E402
from tests.unit.domain.test_project import make_project  # noqa: E402
from tools.build_catalog import build  # noqa: E402

pytestmark = pytest.mark.ui

ROOT = Path(__file__).resolve().parents[2]
REF = MaterialRef("Magnetics", "High Flux", "60")


def bh_series_id(record: MaterialRecord) -> str:
    """Read the shipped series id; never predict one (it depends on the import)."""
    return next(
        series.series_id
        for series in record.series
        if series.kind is SeriesKind.BH_CURVE
    )


def test_the_acceptance_walk_produces_live_estimates(tmp_path: Path) -> None:
    QGuiApplication.instance() or QGuiApplication([])
    index = tmp_path / "catalog.sqlite"
    build(ROOT / "catalog", ROOT / "schemas" / "catalog", index)
    catalog = SqliteCatalogRepository(index)
    materials = FileOverlayMaterialRepository(ROOT / "materials-overlay")
    revision_id = materials.list_revisions(REF)[0]
    series_id = bh_series_id(materials.get(REF, revision_id))

    session = ProjectSession(make_project(), tmp_path / "walk.inductor.json", lambda p: None)
    core_material = CoreMaterialController(session, catalog, materials)
    windings = GuidedStudioController(session, catalog)
    preliminary = PreliminaryController(session, catalog)
    session.projectChanged.connect(preliminary.refresh)

    # 1. choose a material first, then a compatible core (either order).
    assert core_material.selectMaterial(
        REF.manufacturer, REF.name, REF.grade, revision_id, series_id
    )
    compatible = [row["partNumber"] for row in core_material.coreOptions]
    assert compatible, "the shipped catalog has no core for the shipped material"
    assert core_material.selectCatalogCore(str(compatible[0]))
    assert core_material.selectedMaterial["revisionId"] == revision_id

    # 3. one shared frequency plus both temperatures.
    assert windings.setOperatingPointField("frequencyHz", "100e3")
    assert windings.setOperatingPointField("windingTemperatureC", "20")
    assert windings.setOperatingPointField("coreTemperatureC", "25")

    # 4-5. numeric edits, then live preliminary results.
    assert windings.setWindingField("w1", "turns", "10")
    assert windings.setWindingField("w1", "dcCurrentA", "0")
    preliminary.refresh()

    assert preliminary.coreRows[0]["state"] == ResultState.ESTIMATED.value
    assert preliminary.windingRows[0]["jAcRms"]["state"] == ResultState.ESTIMATED.value
    assert preliminary.windingRows[0]["wireLoss"]["state"] == ResultState.ESTIMATED.value
    # 6. assumptions are always visible.
    assert preliminary.assumptions


def test_a_manual_core_estimates_flux_density_from_its_dimensions(tmp_path: Path) -> None:
    QGuiApplication.instance() or QGuiApplication([])
    index = tmp_path / "catalog.sqlite"
    build(ROOT / "catalog", ROOT / "schemas" / "catalog", index)
    catalog = SqliteCatalogRepository(index)
    materials = FileOverlayMaterialRepository(ROOT / "materials-overlay")
    revision_id = materials.list_revisions(REF)[0]
    series_id = bh_series_id(materials.get(REF, revision_id))

    session = ProjectSession(make_project())
    core_material = CoreMaterialController(session, catalog, materials)
    preliminary = PreliminaryController(session, catalog)

    assert core_material.applyManualCore(27.2, 13.8, 11.2, 0.0)
    assert core_material.setAcknowledged(True)
    assert core_material.selectMaterial(
        REF.manufacturer, REF.name, REF.grade, revision_id, series_id
    )
    preliminary.refresh()

    assert preliminary.coreRows[0]["state"] == ResultState.ESTIMATED.value
    assert any("Manual-core" in note for note in preliminary.assumptions)
```

Both tests read the revision id and the B-H series id out of the repository
because both depend on the import (`created_at` plus the workbook sha256).
Never hard-code either one.

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/integration/test_guided_studio_flow.py -q`
Expected: FAIL until `main.py` and the controllers agree; fix real defects, do
not weaken the assertions.

- [ ] **Step 3: Finish the `main.py` wiring**

In `src/inductor_designer/ui/main.py`, after the session exists, build and pass
every controller:

```python
    from inductor_designer.adapters.system.path_opener import DesktopPathOpener
    from inductor_designer.application.services.aedt_support import (
        SUPPORTED_AEDT_EDITION,
        SUPPORTED_AEDT_RELEASE,
    )
    from inductor_designer.ui.core_material_controller import CoreMaterialController
    from inductor_designer.ui.preliminary_controller import PreliminaryController
    from inductor_designer.ui.review_controller import ReviewController
    from inductor_designer.ui.simulation_controller import SimulationController

    core_material_controller: CoreMaterialController | None = None
    preliminary_controller: PreliminaryController | None = None
    simulation_controller: SimulationController | None = None
    review_controller: ReviewController | None = None
    if session is not None and generation_controller is not None:
        catalog_repository = SqliteCatalogRepository(args.catalog)
        material_repository = FileOverlayMaterialRepository(_DEFAULT_MATERIAL_OVERLAY)
        capabilities = MatrixCapabilityRepository(args.matrix).snapshot_for(
            SUPPORTED_AEDT_RELEASE, SUPPORTED_AEDT_EDITION
        )
        core_material_controller = CoreMaterialController(
            session, catalog_repository, material_repository
        )
        preliminary_controller = PreliminaryController(session, catalog_repository)
        simulation_controller = SimulationController(
            session, generation_controller, capabilities
        )
        review_controller = ReviewController(
            session,
            preliminary_controller,
            generation_controller,
            catalog_repository,
            DesktopPathOpener(),
        )
        # One project, one recompute path: every edit lands on the session, and
        # the dependent screens refresh from it.
        session.projectChanged.connect(preliminary_controller.refresh)
        session.projectChanged.connect(guided_studio_controller.refresh)
        session.projectChanged.connect(review_controller.refresh)
```

Reuse the same `FileOverlayMaterialRepository` instance for
`MaterialStudioController` and `CoreMaterialController` so a material imported in
the window is visible to the selector without a process restart. Pass all four
controllers plus the session to `create_engine`.

- [ ] **Step 4: Run every gate, including the full suites**

Run, and record the numbers in the commit body:

```bash
.venv/Scripts/python.exe -m pytest tests -q -m "not aedt and not femm"
```

```bash
.venv/Scripts/python.exe -m pytest tests -q -m "ui"
```

```bash
.venv/Scripts/python.exe -m ruff check .
```

```bash
.venv/Scripts/python.exe -m mypy src tools
```

```bash
.venv/Scripts/python.exe tools/check_architecture.py
```

Expected: all clean. Count the tests yourself; do not report a number you did not
see.

- [ ] **Step 5: Launch the application once and look at it**

```bash
.venv/Scripts/python.exe -m inductor_designer.ui.main --project artifacts/material-validation/m5a-high-flux-60.inductor.json
```

Confirm by eye: the rail reads `Core & Material`, `Windings`, `Preliminary`,
`Simulation`, `Review`; `Open Material Studio` opens a second window and closing
it leaves the pinned revision selected; `Preliminary` and `Review` fill the width;
`Generate project` is disabled with a reason until the project is saved. If the
artifact project is missing or on an older schema, regenerate it with
`python -m tools.prepare_material_handoff` — never reuse a project across a schema
bump. Do not run a solver here; this is a UI check only.

- [ ] **Step 6: Update the docs**

- `docs/superpowers/plans/README.md`: move M7c from "not yet written" to the
  active entry, linking this plan and naming its five screens, the separate
  Material Studio window, the engineering-unit display, the save-before-run
  gate, and the computed Manual-core magnetic path.
- `docs/development/ROADMAP.md`: mark M7c as planned/implemented as appropriate
  and record the five decisions from this plan's Global Constraints.
- `README.md`: if it lists the Guided Studio steps, correct the order and say
  that Material Studio opens in its own window.

- [ ] **Step 7: Commit**

```bash
git add src/inductor_designer/ui/main.py tests/integration/test_guided_studio_flow.py docs README.md
git commit -m "feat(ui): wire the Guided Studio flow end to end"
```

- [ ] **Step 8: Request the final whole-branch review**

Use `superpowers:requesting-code-review` for the whole branch against
`main`. Then hand the branch to Fabio Posser for acceptance with:

- the five gate outputs, pasted, with their real counts;
- what the eyeball check in Step 5 showed;
- the one deliberate behavior change to call out: pinning a material revision no
  longer writes `*.inductor.json` on the spot. Task 8 deleted Material Studio's
  `Select for simulation` writer, so the Core & Material screen pins into the
  session and the top-bar `Save` persists it — which is also what the run gate
  requires. Every assertion of the M5 exit-criterion test survived the move.
- the one thing still out of reach by specification, not by omission:
  `RunMode.GENERATE_AND_SOLVE`. Specification section 12 gives solving and
  `results/` population to M8, so exposing the mode now would start solves whose
  results nothing normalizes.

---

## Self-review against the specification

| Specification | Task |
| --- | --- |
| 4.1 two searchable selectors, bidirectional filtering | 3, 7, 13 |
| 4.1 clear the incompatible side, never substitute | 3, 7 |
| 4.1 Manual-core dimensions on this screen | 7, 13 |
| 4.1 Manual-core compatibility acknowledgment | 3, 7, 13 |
| 4.1 one writer for the pinned revision | 4, 8 |
| 4.1 `Open Material Studio` in a separate window, library refresh on close | 7, 13 |
| 4.2 shared frequency and both temperatures | 5, 14 |
| 4.2 every listed winding input | 5, 14 |
| 4.2 native validators plus authoritative domain validation | 5, 14 |
| 4.2 selectors for enumerated values, free text only where textual | 5, 14 |
| 4.3 core summary, winding table, totals | 9, 10, 15 |
| 4.3 three states with codes and messages | 9, 10, 15 |
| 4.3 assumptions, exclusions, units, revision always visible | 9, 10, 15 |
| 4.4 Simulation without duplicated frequency or temperature | 11, 15 |
| 4.4 Review content | 12, 15 |
| 4.4 saved project required before a run | 11, 15 |
| 4.4 `Show solver window` with a reason when unsupported | 11, 15 |
| 4.4 `Open generated file` / `Open run folder` | 12, 15 |
| 5 estimator stays solver-independent, UI holds no formula | 1, 2, 9 |
| 6 Manual-core magnetic path (plan decision) | 1, 2 |
| 9 partial availability, geometry failure scoping, stable codes | 2, 10 |
| 10 test coverage of each listed behavior | every task |
| 11 acceptance walk | 16 |

Not covered on purpose, and why:

- `RunMode.GENERATE_AND_SOLVE` is not selectable: specification section 12
  assigns solving to M8, and the Guided Studio exit criterion is Generate Only.
  `SimulationController.modeNote` says so on screen rather than leaving the user
  to guess.
- `results/` stays empty: M8 owns result artifacts.
- Core dimension overrides (`CoreOverride`) have no editor: nothing in
  specification section 4.1 asks for one, and the value is still read and
  reported (Task 2's `CATALOG_OVERRIDE_NOTE`).
- Interrupted-run recovery is M9.

## Execution

Plan complete and saved to
`docs/superpowers/plans/2026-07-30-m7c-guided-studio-flow.md`. Two execution
options:

1. **Subagent-Driven (recommended)** — a fresh subagent per task, review between
   tasks, fast iteration.
2. **Inline Execution** — execute tasks in this session using
   `superpowers:executing-plans`, batch execution with checkpoints.
