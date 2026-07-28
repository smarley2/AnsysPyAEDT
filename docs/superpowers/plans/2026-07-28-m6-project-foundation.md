# M6 Project Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace project schema v4 with one backend-independent Project
document and produce validated Maxwell 3D, Maxwell 2D, and FEMM run plans from
identical persisted physical inputs.

**Architecture:** The Project aggregate owns Design, one Operating Point, and
one Simulation Recipe. A separate Run Request selects backend and run mode.
Solver-independent run planning validates material state, converts AC RMS
current to AC peak exactly once, and hands native peak amplitudes to existing
Maxwell/FEMM plans. Existing adapters remain infrastructure; Qt, MCP, and CLI
surfaces only translate their inputs into shared application services.

**Tech Stack:** Python 3.10–3.13, frozen dataclasses and enums, JSON Schema
2020-12, existing geometry/material/simulation modules, pytest, Ruff, strict
mypy.

## Global Constraints

- Owner: Codex on branch `codex/m6-project-foundation`; do not run Claude in
  the same working tree.
- Entry condition: M5a and M5b are accepted; `main` starts at `c32d2b8`.
- Preserve unrelated untracked `.DS_Store` files and `outputs/`; never stage
  them.
- Product UI remains the standalone Windows application. UI workflow changes
  belong to M7.
- Supported AEDT target remains exactly AEDT 2025 R2 Commercial.
- Project documents are backend-independent and contain only Design, Operating
  Point, and Simulation Recipe plus project identity/metadata.
- Schema v5 is a deliberate clean break. Do not add v1–v4 migration code.
- `frequency_hz` is shared by the Operating Point. Winding definitions contain
  no frequency or excitation values.
- Project/UI current is AC RMS. `I_peak = I_rms * sqrt(2)` occurs once in
  solver-independent planning. Adapters receive AC peak and never convert it.
- Winding and core temperatures default to exactly `20.0 °C` and `25.0 °C`.
- A normal run pins exactly one imported or approved core-material revision and
  optional exact B-H series.
- A Manual core with selected material requires explicit compatibility
  acknowledgment.
- Unresolved material permits only confirmed Maxwell 3D Generate Only as a
  Geometry-Only AEDT Project. It contains core/winding geometry and no material
  assignment, excitation, region, mesh, setup, matrix, report, or solve-ready
  claim.
- Maxwell 2D and FEMM remain explicitly approximate equivalent
  cross-sectional models. Full geometry remains the default; symmetry is
  informational only.
- `domain`, `geometry`, `materials`, and solver-independent `simulation` stay
  free of PyAEDT, Qt, FEMM, SQLite, and operating-system APIs.
- No new dependency, compatibility fallback, legacy migration, sweep, result
  extraction, autosave, recovery, or UI redesign belongs to M6.
- Add/update tests before implementation. Every task ends with its focused
  tests, Ruff on touched files, strict mypy, architecture check, and a small
  commit.

## Authoritative Requirements

- `docs/superpowers/specs/2026-07-24-mvp-roadmap-realignment-design.md`
- `docs/superpowers/specs/2026-07-26-preliminary-calculations-and-guided-flow-design.md`
- `docs/adr/0005-backend-independent-projects.md`
- `docs/adr/0006-rms-project-current-and-peak-solver-excitation.md`
- `docs/architecture/README.md`
- `CONTEXT.md`

## File Map

| File | Responsibility after M6 |
| --- | --- |
| `src/inductor_designer/domain/project.py` | Design, Operating Point, Simulation Recipe, Project aggregate, exact material state |
| `src/inductor_designer/domain/winding.py` | Geometry/conductor-only winding definition |
| `src/inductor_designer/domain/validation.py` | Backend-independent Project validation |
| `src/inductor_designer/simulation/run_contracts.py` | Run Request, effective excitation, manifest, and normalized-result contracts |
| `src/inductor_designer/simulation/plan_builder.py` | Maxwell 3D plan from geometry plus already-converted effective inputs |
| `src/inductor_designer/simulation/plan_builder2d.py` | Shared Maxwell 2D/FEMM plan from the same effective inputs |
| `src/inductor_designer/application/services/run_planning.py` | Operation-specific validation and backend plan selection |
| `src/inductor_designer/application/services/maxwell_export.py` | Execute planned Generate Only operations and serialize Run Manifests |
| `schemas/project/v5.schema.json` | Only supported Project document schema |
| `src/inductor_designer/adapters/persistence/project_repository.py` | Deterministic v5 serialization |
| `src/inductor_designer/adapters/persistence/schema_repository.py` | v5-only validation; no legacy migration |
| Existing PyAEDT/FEMM adapters | Consume native peak-amplitude solver plans; no project semantics |

---

### Task 1: Replace the Project aggregate

**Owner:** M6 implementer

**Dependencies:** None

**Allowed files:**

- Modify: `src/inductor_designer/domain/project.py`
- Modify: `src/inductor_designer/domain/winding.py`
- Modify: `tests/unit/domain/test_project.py`

**Interfaces:**

- Produces:
  `Design(core, windings, core_material, manual_material_compatibility_acknowledged)`.
- Produces:
  `WindingOperatingPoint(winding_id, ac_rms_current_a, ac_phase_deg, dc_current_a, current_direction)`.
- Produces:
  `OperatingPoint(frequency_hz, winding_temperature_c, core_temperature_c, windings)`.
- Produces:
  `SimulationRecipe(mesh_intent, maximum_passes, percent_error, requested_outputs)`.
- Produces:
  `InductorProject(project_id, name, description, design, operating_point, simulation_recipe)`.
- Removes `target_release`, `target_edition`, `dimension_mode`, `materials`,
  `WindingDefinition.ac_magnitude_a`, `WindingDefinition.ac_phase_deg`,
  `WindingDefinition.frequency_hz`, `WindingDefinition.dc_current_a`, and
  `WindingDefinition.current_direction`.

- [ ] **Step 1: Write failing aggregate tests.**

Replace the old constructor helpers with this exact shape:

```python
def make_operating_point(
    *windings: WindingOperatingPoint,
    frequency_hz: float = 100_000.0,
) -> OperatingPoint:
    return OperatingPoint(
        frequency_hz=frequency_hz,
        winding_temperature_c=20.0,
        core_temperature_c=25.0,
        windings=windings
        or (
            WindingOperatingPoint(
                winding_id="w1",
                ac_rms_current_a=2.0,
                ac_phase_deg=0.0,
                dc_current_a=5.0,
                current_direction=CurrentDirection.FORWARD,
            ),
        ),
    )


def make_project(**overrides: object) -> InductorProject:
    values: dict[str, object] = {
        "project_id": "3f0e8f5e-8f4e-4a5e-9d5b-6c4f2b1a0d9c",
        "name": "Boost inductor",
        "description": "",
        "design": Design(
            core=CatalogCoreSelection("0077071A7", make_core(), ()),
            windings=(make_winding(),),
            core_material=None,
            manual_material_compatibility_acknowledged=False,
        ),
        "operating_point": make_operating_point(),
        "simulation_recipe": SimulationRecipe(
            mesh_intent=MeshIntent.STANDARD,
            maximum_passes=10,
            percent_error=1.0,
            requested_outputs=(
                RequestedOutput.RESISTANCE,
                RequestedOutput.INDUCTANCE,
            ),
        ),
    }
    values.update(overrides)
    return InductorProject(**values)  # type: ignore[arg-type]
```

Add assertions that:

```python
assert make_project().operating_point.frequency_hz == 100_000.0
assert make_project().operating_point.winding_temperature_c == 20.0
assert make_project().operating_point.core_temperature_c == 25.0
assert not hasattr(make_winding(), "frequency_hz")
assert not hasattr(make_winding(), "ac_magnitude_a")
assert not hasattr(make_project(), "dimension_mode")
```

Add rejection tests for blank Project name/id, blank
`WindingOperatingPoint.winding_id`, non-finite numeric values, non-positive
frequency, negative AC RMS/DC currents, non-positive maximum passes, and
non-positive percent error. Duplicate/cross-object winding checks remain
path-addressed validation findings in Task 3.

- [ ] **Step 2: Run the domain test and verify it fails.**

Run:

```bash
.venv/bin/python -m pytest tests/unit/domain/test_project.py -q
```

Expected: collection or constructor failures because the M6 contracts do not
exist.

- [ ] **Step 3: Implement the minimal aggregate.**

Use these exact enums and fields:

```python
class MeshIntent(str, Enum):
    STANDARD = "standard"


class RequestedOutput(str, Enum):
    RESISTANCE = "resistance"
    INDUCTANCE = "inductance"
    IMPEDANCE = "impedance"
    MATRICES = "matrices"
    COPPER_LOSS = "copper-loss"
    CORE_LOSS = "core-loss"
    TOTAL_LOSS = "total-loss"
    MAGNETIC_ENERGY = "magnetic-energy"
    CONVERGENCE = "convergence"
    FLUX_DENSITY = "flux-density"
    CURRENT_DENSITY = "current-density"


@dataclass(frozen=True, slots=True)
class Design:
    core: CoreSelection | None
    windings: tuple[WindingDefinition, ...]
    core_material: MaterialRevisionSelection | None
    manual_material_compatibility_acknowledged: bool


@dataclass(frozen=True, slots=True)
class WindingOperatingPoint:
    winding_id: str
    ac_rms_current_a: float
    ac_phase_deg: float
    dc_current_a: float
    current_direction: CurrentDirection


@dataclass(frozen=True, slots=True)
class OperatingPoint:
    frequency_hz: float
    winding_temperature_c: float = 20.0
    core_temperature_c: float = 25.0
    windings: tuple[WindingOperatingPoint, ...] = ()


@dataclass(frozen=True, slots=True)
class SimulationRecipe:
    mesh_intent: MeshIntent
    maximum_passes: int
    percent_error: float
    requested_outputs: tuple[RequestedOutput, ...]


@dataclass(frozen=True, slots=True)
class InductorProject:
    project_id: str
    name: str
    description: str
    design: Design
    operating_point: OperatingPoint
    simulation_recipe: SimulationRecipe
```

Use `math.isfinite` for numeric invariants. Keep physical cross-object checks
out of `__post_init__`; Task 3 reports them as path-addressed validation issues.

- [ ] **Step 4: Run focused checks.**

```bash
.venv/bin/python -m pytest tests/unit/domain/test_project.py -q
.venv/bin/python -m ruff check src/inductor_designer/domain/project.py \
  src/inductor_designer/domain/winding.py tests/unit/domain/test_project.py
.venv/bin/python -m mypy src/inductor_designer/domain/project.py \
  src/inductor_designer/domain/winding.py
.venv/bin/python -m tools.check_architecture
```

Expected: all pass.

- [ ] **Step 5: Commit.**

```bash
git add src/inductor_designer/domain/project.py \
  src/inductor_designer/domain/winding.py tests/unit/domain/test_project.py
git commit -m "refactor(domain): introduce backend-independent project"
```

**Acceptance criteria:** Project aggregate has no backend, AEDT target,
dimensional mode, per-winding frequency, or ambiguous AC magnitude.

---

### Task 2: Introduce schema v5 and deterministic persistence

**Owner:** M6 implementer

**Dependencies:** Task 1

**Allowed files:**

- Create: `schemas/project/v5.schema.json`
- Delete: `schemas/project/v1.schema.json`
- Delete: `schemas/project/v2.schema.json`
- Delete: `schemas/project/v3.schema.json`
- Delete: `schemas/project/v4.schema.json`
- Modify: `src/inductor_designer/adapters/persistence/project_repository.py`
- Modify: `src/inductor_designer/adapters/persistence/schema_repository.py`
- Modify: `tests/unit/adapters/persistence/test_project_repository.py`
- Modify: `tests/unit/adapters/persistence/test_schema_repository.py`
- Modify: `tests/fixtures/sample_geometry_project.inductor.json`
- Delete: `tests/fixtures/project.v2.json`
- Delete: `tests/fixtures/projects/minimal-v1.inductor.json`

**Interfaces:**

- Consumes Task 1 aggregate.
- Produces `project_to_document(project) -> dict[str, object]`.
- Produces `project_from_document(document) -> InductorProject`.
- `SchemaRepository.validate_project` accepts only `schemaVersion == 5`.
- `ProjectRepository.load` rejects v1–v4 explicitly; it never migrates them.

- [ ] **Step 1: Write failing v5 schema and round-trip tests.**

The canonical document must have this top-level shape:

```json
{
  "schemaVersion": 5,
  "projectId": "3f0e8f5e-8f4e-4a5e-9d5b-6c4f2b1a0d9c",
  "metadata": {"name": "Boost inductor", "description": ""},
  "design": {
    "core": {},
    "windings": [],
    "coreMaterial": null,
    "manualMaterialCompatibilityAcknowledged": false
  },
  "operatingPoint": {
    "frequencyHz": 100000.0,
    "windingTemperatureC": 20.0,
    "coreTemperatureC": 25.0,
    "windings": []
  },
  "simulationRecipe": {
    "meshIntent": "standard",
    "maximumPasses": 10,
    "percentError": 1.0,
    "requestedOutputs": ["resistance", "inductance"]
  }
}
```

Add tests that `target`, `dimensionMode`, `materials`, `acMagnitudeA`, and
per-winding `frequencyHz` are absent. Add a byte-identical save-load-save test
with an exact pinned material snapshot and B-H series. Add:

```python
@pytest.mark.parametrize("version", [1, 2, 3, 4])
def test_legacy_project_versions_are_rejected(version: int) -> None:
    with pytest.raises(
        ValueError,
        match=rf"Unsupported project schema version: {version}; expected 5",
    ):
        SchemaRepository(SCHEMAS).validate_project({"schemaVersion": version})
```

- [ ] **Step 2: Run and verify failure.**

```bash
.venv/bin/python -m pytest tests/unit/adapters/persistence -q
```

Expected: failures on schema version, old serialization keys, and constructors.

- [ ] **Step 3: Write `v5.schema.json`.**

Reuse the existing core/material snapshot definitions verbatim. Define:

- `design.windings` as geometry/conductor fields only;
- `operatingPoint.windings` with required `windingId`, `acRmsCurrentA`,
  `acPhaseDeg`, `dcCurrentA`, and `currentDirection`;
- temperatures as finite JSON numbers;
- `meshIntent` constant `standard`;
- requested outputs as unique enum values from Task 1;
- `coreMaterial` as null or one exact material selection;
- `manualMaterialCompatibilityAcknowledged` as a required boolean.

JSON Schema cannot reject IEEE non-finite values because valid JSON cannot
encode them; domain constructors remain the second boundary.

- [ ] **Step 4: Replace migration with v5-only validation.**

Use:

```python
LATEST_PROJECT_SCHEMA_VERSION = 5


def validate_project(self, document: Mapping[str, object]) -> None:
    version = document.get("schemaVersion")
    if version != LATEST_PROJECT_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported project schema version: {version}; "
            f"expected {LATEST_PROJECT_SCHEMA_VERSION}"
        )
    schema = self.load_project_schema(LATEST_PROJECT_SCHEMA_VERSION)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(document)
```

Delete `_MIGRATIONS`, all migration functions, and `migrate_project`.
`ProjectRepository.load` validates the loaded mapping, then calls
`project_from_document`.

- [ ] **Step 5: Implement v5 serialization and remove legacy fixtures.**

Serialize `Design`, Operating Point, and Simulation Recipe in their own helper
functions. Preserve atomic save and `sort_keys=True`. The single material
selection is serialized under `design.coreMaterial`; no list remains.
Convert `sample_geometry_project.inductor.json` to the canonical v5 shape in
the same step so persistence tests never depend on an unsupported fixture.

- [ ] **Step 6: Run focused checks.**

```bash
.venv/bin/python -m pytest tests/unit/adapters/persistence -q
.venv/bin/python -m ruff check src/inductor_designer/adapters/persistence \
  tests/unit/adapters/persistence
.venv/bin/python -m mypy src/inductor_designer/adapters/persistence
.venv/bin/python -m tools.check_architecture
```

Expected: all pass.

- [ ] **Step 7: Commit.**

```bash
git add schemas/project src/inductor_designer/adapters/persistence \
  tests/unit/adapters/persistence tests/fixtures
git commit -m "feat(persistence): replace project schema with v5"
```

**Acceptance criteria:** v5 round-trips deterministically; every legacy schema
version fails with one actionable clean-break error.

---

### Task 3: Enforce Project invariants across services and geometry

**Owner:** M6 implementer

**Dependencies:** Tasks 1–2

**Allowed files:**

- Modify: `src/inductor_designer/domain/validation.py`
- Modify: `src/inductor_designer/geometry/symmetry.py`
- Modify: `src/inductor_designer/application/services/geometry_model.py`
- Modify: `src/inductor_designer/application/services/catalog_revisions.py`
- Modify: `src/inductor_designer/application/services/material_selection.py`
- Modify: `src/inductor_designer/application/services/material_handoff.py`
- Modify: corresponding tests under `tests/unit/domain`,
  `tests/unit/geometry`, and `tests/unit/application`

**Interfaces:**

- `validate_project(project, known_conductors=...)` reports Design/Operating
  Point consistency.
- `propose_symmetry_plan(windings, operating_points)` compares geometry and
  excitation separately.
- `pin_material_revision(project, record, *, bh_series_id,
  manual_compatibility_acknowledged=False)` writes one exact
  `design.core_material`.

- [ ] **Step 1: Add failing validation tests.**

Test exact issue codes and paths:

| Condition | Code | Path |
| --- | --- | --- |
| Missing Operating Point entry | `operating-point.winding.missing` | `operatingPoint.windings` |
| Unknown Operating Point entry | `operating-point.winding.unknown` | `operatingPoint.windings[i]` |
| Duplicate Operating Point entry | `operating-point.winding.duplicate` | `operatingPoint.windings[i]` |
| Catalog core/material identity mismatch | `core-material.incompatible` | `design.coreMaterial` |
| Manual core, material, no acknowledgment | `core-material.manual-unacknowledged` | `design.manualMaterialCompatibilityAcknowledged` |
| Acknowledgment without Manual core/material pair | `core-material.acknowledgment-unused` | `design.manualMaterialCompatibilityAcknowledged` |

`acknowledgment-unused` is `INFO`; missing/incompatible pair conditions are
`ERROR`. A Project may save with no core or no material; operation-specific
blocking belongs to Task 4.

- [ ] **Step 2: Run and verify failures.**

```bash
.venv/bin/python -m pytest tests/unit/domain/test_validation.py \
  tests/unit/geometry/test_symmetry.py \
  tests/unit/application/test_geometry_model.py \
  tests/unit/application/test_material_selection.py -q
```

- [ ] **Step 3: Implement validation and nested replacements.**

Use `project.design.windings`, `project.design.core`, and
`project.design.core_material` everywhere. `select_core` and
`adopt_core_revision` replace `project.design`, not the Project root.

`pin_material_revision` must:

1. retain imported/approved and B-H checks;
2. reject catalog material identity mismatch immediately;
3. set the Manual compatibility boolean only from its explicit argument;
4. replace the previous single selection rather than append to a tuple.

- [ ] **Step 4: Split symmetry geometry/excitation inputs.**

Use:

```python
def propose_symmetry_plan(
    windings: Sequence[WindingDefinition],
    operating_points: Sequence[WindingOperatingPoint],
) -> SymmetryPlan | SymmetryRefusal:
```

Geometry keys include `winding_direction` but not `current_direction`.
Excitation keys include AC RMS, phase, DC current, and `current_direction`.
Shared frequency is already common by construction and does not need
per-winding comparison.

- [ ] **Step 5: Update M5a handoff preparation.**

The handoff selects the catalog core and exact material in `Design`; it sets
the Operating Point but never writes AEDT target or dimension. Preserve all
reproduction evidence behavior.

- [ ] **Step 6: Run focused checks.**

```bash
.venv/bin/python -m pytest tests/unit/domain tests/unit/geometry \
  tests/unit/application/test_geometry_model.py \
  tests/unit/application/test_catalog_revisions.py \
  tests/unit/application/test_material_selection.py \
  tests/unit/application/test_material_handoff.py -q
.venv/bin/python -m ruff check src/inductor_designer/domain \
  src/inductor_designer/geometry \
  src/inductor_designer/application/services tests/unit
.venv/bin/python -m mypy src/inductor_designer/domain \
  src/inductor_designer/geometry \
  src/inductor_designer/application/services/catalog_revisions.py \
  src/inductor_designer/application/services/geometry_model.py \
  src/inductor_designer/application/services/material_handoff.py \
  src/inductor_designer/application/services/material_selection.py
.venv/bin/python -m tools.check_architecture
```

- [ ] **Step 7: Commit.**

```bash
git add src/inductor_designer/domain/validation.py \
  src/inductor_designer/geometry/symmetry.py \
  src/inductor_designer/application/services/geometry_model.py \
  src/inductor_designer/application/services/catalog_revisions.py \
  src/inductor_designer/application/services/material_selection.py \
  src/inductor_designer/application/services/material_handoff.py tests/unit
git commit -m "refactor(application): consume m6 project contracts"
```

**Acceptance criteria:** Project validation proves one-to-one winding operating
points and exact material compatibility without blocking incomplete editable
Projects.

---

### Task 4: Define Run Request, Run Manifest, and result contracts

**Owner:** M6 implementer

**Dependencies:** Tasks 1–3

**Allowed files:**

- Create: `src/inductor_designer/simulation/run_contracts.py`
- Create: `tests/unit/simulation/test_run_contracts.py`
- Modify: `src/inductor_designer/simulation/__init__.py`

**Interfaces:**

- Produces `RunRequest`, `EffectiveWindingInput`, `RunManifest`, and
  `NormalizedResultSet`.
- No filesystem path object, PyAEDT/FEMM/Qt type, or adapter object crosses
  these contracts.

- [ ] **Step 1: Write failing contract tests.**

Cover enum values, RMS/peak evidence, manifest construction, and result
availability invariants. Include:

```python
def test_effective_input_records_rms_and_peak() -> None:
    item = effective_winding_inputs(make_project().operating_point)[0]
    assert item.ac_rms_current_a == 2.0
    assert item.ac_peak_current_a == pytest.approx(2.0 * math.sqrt(2.0))


def test_available_result_requires_value_unit_and_provenance() -> None:
    with pytest.raises(ValueError, match="available result"):
        NormalizedQuantity(
            quantity=ResultQuantity.RESISTANCE,
            scope="w1",
            availability=ResultAvailability.AVAILABLE,
            value=None,
            unit="ohm",
            current_convention=CurrentConvention.AC_RMS,
            approximation=None,
            reason=None,
            provenance="",
        )
```

- [ ] **Step 2: Run and verify module-not-found failure.**

```bash
.venv/bin/python -m pytest tests/unit/simulation/test_run_contracts.py -q
```

- [ ] **Step 3: Implement exact run enums.**

```python
class RunBackend(str, Enum):
    MAXWELL_3D = "maxwell-3d"
    MAXWELL_2D = "maxwell-2d"
    FEMM = "femm"


class RunMode(str, Enum):
    GENERATE_ONLY = "generate-only"
    GENERATE_AND_SOLVE = "generate-and-solve"


class RunStatus(str, Enum):
    PLANNED = "planned"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StageStatus(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class DimensionalRepresentation(str, Enum):
    THREE_DIMENSIONAL = "three-dimensional"
    EQUIVALENT_CROSS_SECTION = "equivalent-cross-section"


@dataclass(frozen=True, slots=True)
class RunRequest:
    backend: RunBackend
    mode: RunMode
    confirm_geometry_only: bool = False
```

Add `EffectiveWindingInput` with winding id, AC RMS, AC peak, phase, DC current,
and current direction. Implement the sole conversion in:

```python
def effective_winding_inputs(
    operating_point: OperatingPoint,
) -> tuple[EffectiveWindingInput, ...]:
    return tuple(
        EffectiveWindingInput(
            winding_id=item.winding_id,
            ac_rms_current_a=item.ac_rms_current_a,
            ac_peak_current_a=item.ac_rms_current_a * math.sqrt(2.0),
            phase_deg=item.ac_phase_deg,
            dc_current_a=item.dc_current_a,
            current_direction=item.current_direction,
        )
        for item in operating_point.windings
    )
```

- [ ] **Step 4: Implement immutable evidence contracts.**

Define:

- `ManifestMaterialState(resolved, ref, revision_id, bh_series_id,
  manual_compatibility_acknowledged)`;
- `ManifestStage(name, status, diagnostic)`;
- `ManifestArtifact(kind, path)`, with path stored as a portable string;
- `ResultAvailability(AVAILABLE, UNAVAILABLE)`;
- `CurrentConvention(NOT_APPLICABLE, AC_RMS, AC_PEAK, DC, COMBINED)`;
- `ResultQuantity = RequestedOutput`, avoiding a second vocabulary for the
  exact same quantities;
- `NormalizedQuantity(quantity, scope, availability, value, unit,
  current_convention, approximation, reason, provenance)`;
- `NormalizedResultSet(run_id, backend, quantities)`;
- `RunManifest(run_id, project_id, backend, mode,
  project_schema_version, dimensional_representation, frequency_hz,
  winding_temperature_c,
  core_temperature_c, windings, material, mesh_intent, maximum_passes,
  percent_error, requested_outputs, geometry_only, application_version,
  solver_version, adapter_version, warnings, stages, status, diagnostics,
  artifacts, results)`.

Use these exact field types:

```python
@dataclass(frozen=True, slots=True)
class ManifestMaterialState:
    resolved: bool
    ref: MaterialRef | None
    revision_id: str | None
    bh_series_id: str | None
    manual_compatibility_acknowledged: bool


@dataclass(frozen=True, slots=True)
class ManifestStage:
    name: str
    status: StageStatus
    diagnostic: str


@dataclass(frozen=True, slots=True)
class ManifestArtifact:
    kind: str
    path: str


@dataclass(frozen=True, slots=True)
class ComplexValue:
    real: float
    imaginary: float


@dataclass(frozen=True, slots=True)
class MatrixValue:
    row_labels: tuple[str, ...]
    column_labels: tuple[str, ...]
    values: tuple[tuple[float | ComplexValue, ...], ...]


NormalizedValue = float | ComplexValue | MatrixValue


@dataclass(frozen=True, slots=True)
class NormalizedQuantity:
    quantity: ResultQuantity
    scope: str
    availability: ResultAvailability
    value: NormalizedValue | None
    unit: str | None
    current_convention: CurrentConvention
    approximation: str | None
    reason: str | None
    provenance: str | None


@dataclass(frozen=True, slots=True)
class NormalizedResultSet:
    run_id: str
    backend: RunBackend
    quantities: tuple[NormalizedQuantity, ...]


@dataclass(frozen=True, slots=True)
class RunManifest:
    run_id: str
    project_id: str
    project_schema_version: int
    backend: RunBackend
    mode: RunMode
    dimensional_representation: DimensionalRepresentation
    frequency_hz: float
    winding_temperature_c: float
    core_temperature_c: float
    windings: tuple[EffectiveWindingInput, ...]
    material: ManifestMaterialState
    mesh_intent: MeshIntent
    maximum_passes: int
    percent_error: float
    requested_outputs: tuple[RequestedOutput, ...]
    geometry_only: bool
    application_version: str
    solver_version: str | None
    adapter_version: str | None
    warnings: tuple[str, ...]
    stages: tuple[ManifestStage, ...]
    status: RunStatus
    diagnostics: tuple[str, ...]
    artifacts: tuple[ManifestArtifact, ...]
    results: NormalizedResultSet | None
```

Use `None` only where evidence is genuinely unavailable. Enforce:

- available quantity: value, unit, provenance present; reason absent;
- unavailable quantity: value absent; nonblank reason present;
- Geometry-Only manifest: backend Maxwell 3D, Generate Only, unresolved
  material, no result set;
- succeeded manifest: at least one artifact;
- result backend equals manifest backend.

- [ ] **Step 5: Run focused checks.**

```bash
.venv/bin/python -m pytest tests/unit/simulation/test_run_contracts.py -q
.venv/bin/python -m ruff check \
  src/inductor_designer/simulation/run_contracts.py \
  tests/unit/simulation/test_run_contracts.py
.venv/bin/python -m mypy src/inductor_designer/simulation/run_contracts.py
.venv/bin/python -m tools.check_architecture
```

- [ ] **Step 6: Commit.**

```bash
git add src/inductor_designer/simulation/run_contracts.py \
  src/inductor_designer/simulation/__init__.py \
  tests/unit/simulation/test_run_contracts.py
git commit -m "feat(simulation): define run evidence contracts"
```

**Acceptance criteria:** contracts can represent every M6 run state and every
M8 result availability state without importing infrastructure.

---

### Task 5: Feed shared frequency and one-time peak current into solver plans

**Owner:** M6 implementer

**Dependencies:** Task 4

**Allowed files:**

- Modify: `src/inductor_designer/simulation/maxwell_plan.py`
- Modify: `src/inductor_designer/simulation/maxwell2d_plan.py`
- Modify: `src/inductor_designer/simulation/femm_problem.py`
- Modify: `src/inductor_designer/simulation/plan_builder.py`
- Modify: `src/inductor_designer/simulation/plan_builder2d.py`
- Modify: corresponding tests under `tests/unit/simulation`

**Interfaces:**

- Both builders consume `frequency_hz`, `SimulationRecipe`, and
  `Sequence[EffectiveWindingInput]`.
- Both builders write `EffectiveWindingInput.ac_peak_current_a` directly into
  solver plan winding groups.
- FEMM translation copies the peak value without conversion.
- Produces `GeometryOnlyMaxwell3dPlan` from the same finished geometry without
  material or solver configuration.

- [ ] **Step 1: Rewrite builder tests first.**

Construct Design windings and effective inputs separately. Add a regression:

```python
def test_all_plans_receive_one_converted_peak_amplitude() -> None:
    effective = (
        EffectiveWindingInput(
            winding_id="w1",
            ac_rms_current_a=2.0,
            ac_peak_current_a=2.0 * math.sqrt(2.0),
            phase_deg=30.0,
            dc_current_a=0.0,
            current_direction=CurrentDirection.FORWARD,
        ),
    )
    plan3d = build_3d(effective)
    plan2d = build_2d(effective)
    femm = femm_problem_from_plan(plan2d)
    assert plan3d.windings[0].current_peak_a == pytest.approx(2.0 * math.sqrt(2.0))
    assert plan2d.windings[0].current_peak_a == pytest.approx(2.0 * math.sqrt(2.0))
    assert femm.circuits[0].current_peak_a == pytest.approx(2.0 * math.sqrt(2.0))
```

Add tests that missing, duplicate, and unknown effective winding ids raise
`PlanBuildError`. Delete multi-frequency builder tests; per-winding frequency
no longer exists.

- [ ] **Step 2: Run and verify failures.**

```bash
.venv/bin/python -m pytest tests/unit/simulation/test_plan_builder.py \
  tests/unit/simulation/test_plan_builder2d.py \
  tests/unit/simulation/test_femm_problem.py -q
```

- [ ] **Step 3: Change builder signatures.**

Use:

```python
def build_maxwell3d_plan(
    core: FinishedCore,
    packings: Sequence[PackedWinding],
    windings: Sequence[WindingDefinition],
    effective_inputs: Sequence[EffectiveWindingInput],
    bare_diameter_m: Mapping[str, float],
    *,
    frequency_hz: float,
    recipe: SimulationRecipe,
    dc_bias_decision: DcBiasDecision | None = None,
    material_record: MaterialRecord,
    material_bh_series_id: str | None,
) -> Maxwell3dDesignPlan:
```

Use the equivalent signature for `build_maxwell2d_plan`. `material_record` is
required for solve-ready plans; delete the catalog scalar-permeability fallback
from both builders. Delete `core_material_spec` and its tests. Change
`material_spec_from_material_record` to accept
`expected_ref: MaterialRef | None`: catalog planning passes the catalog core's
required ref; acknowledged Manual-core planning passes `None`.

Add:

```python
@dataclass(frozen=True, slots=True)
class GeometryOnlyTurnPlan:
    name: str
    segments: tuple[PathSegment, ...]
    bare_diameter_m: float


@dataclass(frozen=True, slots=True)
class GeometryOnlyWindingPlan:
    name: str
    winding_id: str
    turns: tuple[GeometryOnlyTurnPlan, ...]


@dataclass(frozen=True, slots=True)
class GeometryOnlyMaxwell3dPlan:
    design_name: str
    core_name: str
    core_profile: tuple[PathSegment, ...]
    windings: tuple[GeometryOnlyWindingPlan, ...]
    notes: tuple[str, ...]

def build_geometry_only_maxwell3d_plan(
    core: FinishedCore,
    packings: Sequence[PackedWinding],
    windings: Sequence[WindingDefinition],
    bare_diameter_m: Mapping[str, float],
) -> GeometryOnlyMaxwell3dPlan:
```

Geometry-Only types above carry paths and diameters only. They must not gain
current, phase, terminals, material, mesh, setup, or report fields.

- [ ] **Step 4: Map recipe and effective inputs.**

- `SetupPlan.frequency_hz = frequency_hz`
- `SetupPlan.maximum_passes = recipe.maximum_passes`
- `SetupPlan.percent_error = recipe.percent_error`
- `WindingGroupPlan.current_peak_a = effective.ac_peak_current_a`
- `phase_deg`, `dc_current_a`, and polarity/current direction come from the
  matching effective input.
- Generate R/L reports only when the corresponding Requested Output is present.
- Preserve accepted mesh constants under `MeshIntent.STANDARD`; no second mesh
  mode is added.

- [ ] **Step 5: Prove adapters contain no RMS conversion.**

Run:

```bash
rg -n "sqrt\\(2|sqrt\\(2\\.0|2 \\* math\\.sqrt" \
  src/inductor_designer/adapters src/inductor_designer/simulation
```

Expected: the only RMS-to-peak match is
`simulation/run_contracts.py`. Other unrelated square-root formulas may remain;
inspect each match rather than weakening the assertion.

- [ ] **Step 6: Run focused checks.**

```bash
.venv/bin/python -m pytest tests/unit/simulation -q
.venv/bin/python -m ruff check src/inductor_designer/simulation \
  tests/unit/simulation
.venv/bin/python -m mypy src/inductor_designer/simulation
.venv/bin/python -m tools.check_architecture
```

- [ ] **Step 7: Commit.**

```bash
git add src/inductor_designer/simulation tests/unit/simulation
git commit -m "refactor(simulation): plan from shared operating point"
```

**Acceptance criteria:** all three backend plans carry identical physical
inputs and exactly one `sqrt(2)` conversion is present.

---

### Task 6: Add operation-specific run planning

**Owner:** M6 implementer

**Dependencies:** Tasks 3–5

**Allowed files:**

- Create: `src/inductor_designer/application/services/run_planning.py`
- Create: `tests/unit/application/test_run_planning.py`
- Modify: `src/inductor_designer/application/services/__init__.py`

**Interfaces:**

- Produces:
  `plan_run(project, request, catalog, capabilities) -> PlannedRun`.
- Produces `SolveReadyRunPlan` for resolved material and
  `GeometryOnlyRunPlan` for the confirmed exception.
- Does not launch Qt, PyAEDT, or FEMM and does not write files.

- [ ] **Step 1: Write the run-planning matrix as failing parametrized tests.**

Cover:

| Backend | Mode | Material | Confirmation | Expected |
| --- | --- | --- | --- | --- |
| Maxwell 3D | Generate Only | resolved | false | solve-ready 3D plan |
| Maxwell 2D | Generate Only | resolved | false | solve-ready 2D plan |
| FEMM | Generate Only | resolved | false | FEMM problem |
| Maxwell 3D | Generate Only | unresolved | true | Geometry-Only plan + warning |
| Maxwell 3D | Generate Only | unresolved | false | blocked |
| Maxwell 3D | Generate and Solve | unresolved | true | blocked |
| Maxwell 2D | either | unresolved | either | blocked |
| FEMM | either | unresolved | either | blocked |
| any | either | Manual material unacknowledged | either | blocked |

Also assert:

```python
assert plan3d.effective_inputs == plan2d.effective_inputs == femm.effective_inputs
assert plan3d.effective_inputs[0].ac_rms_current_a == 2.0
assert plan3d.effective_inputs[0].ac_peak_current_a == pytest.approx(2.0 * math.sqrt(2.0))
```

Add DC cases: nonzero DC blocks Maxwell 2D and FEMM; reviewed native capability
permits Maxwell 3D; unreviewed/unavailable native capability blocks it.

- [ ] **Step 2: Run and verify module-not-found failure.**

```bash
.venv/bin/python -m pytest tests/unit/application/test_run_planning.py -q
```

- [ ] **Step 3: Implement result types and errors.**

```python
class RunPlanningError(ValueError):
    def __init__(self, issues: tuple[str, ...]) -> None:
        self.issues = issues
        super().__init__("; ".join(issues))


@dataclass(frozen=True, slots=True)
class SolveReadyRunPlan:
    request: RunRequest
    effective_inputs: tuple[EffectiveWindingInput, ...]
    solver_plan: Maxwell3dDesignPlan | Maxwell2dDesignPlan | FemmProblem
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GeometryOnlyRunPlan:
    request: RunRequest
    effective_inputs: tuple[EffectiveWindingInput, ...]
    solver_plan: GeometryOnlyMaxwell3dPlan
    warnings: tuple[str, ...]


PlannedRun = SolveReadyRunPlan | GeometryOnlyRunPlan
```

- [ ] **Step 4: Implement validation in this order.**

1. Run backend-independent `validate_project`; collect `ERROR` findings.
2. Require core and at least one winding.
3. Build geometry and reject collisions.
4. Resolve one exact `design.core_material`.
5. If unresolved, allow only the confirmed Geometry-Only matrix row.
6. For a resolved catalog core, recheck exact material identity.
7. For a resolved Manual core, require compatibility acknowledgment.
8. Select DC capability by Run backend dimensional representation.
9. Call `effective_winding_inputs` exactly once.
10. Build the selected native solver plan from those effective inputs, or call
    `build_geometry_only_maxwell3d_plan` for the confirmed exception.

The Geometry-Only warning text must be:

```text
Core material is unresolved. This confirmed Maxwell 3D Generate Only run
creates geometry only; it has no material assignments, excitations, setup,
mesh, reports, or solve-ready claim.
```

- [ ] **Step 5: Run focused checks.**

```bash
.venv/bin/python -m pytest tests/unit/application/test_run_planning.py -q
.venv/bin/python -m ruff check \
  src/inductor_designer/application/services/run_planning.py \
  tests/unit/application/test_run_planning.py
.venv/bin/python -m mypy \
  src/inductor_designer/application/services/run_planning.py
.venv/bin/python -m tools.check_architecture
```

- [ ] **Step 6: Commit.**

```bash
git add src/inductor_designer/application/services/run_planning.py \
  src/inductor_designer/application/services/__init__.py \
  tests/unit/application/test_run_planning.py
git commit -m "feat(application): plan backend-independent runs"
```

**Acceptance criteria:** one Project produces validated plans for all three
backends with identical inputs; invalid operation/material combinations are
blocked before adapter calls.

---

### Task 7: Route Generate Only and Run Manifests through the new plan

**Owner:** M6 implementer

**Dependencies:** Task 6

**Allowed files:**

- Modify: `src/inductor_designer/application/services/maxwell_export.py`
- Modify: `src/inductor_designer/application/ports/maxwell_exporter.py`
- Modify: `src/inductor_designer/application/ports/femm_solver.py`
- Modify: `src/inductor_designer/adapters/pyaedt/maxwell3d.py`
- Modify: `src/inductor_designer/adapters/femm/solver.py`
- Modify: `tests/contract/test_maxwell_exporter_contract.py`
- Modify: `tests/contract/test_femm_solver_contract.py`
- Modify: `tests/unit/application/test_maxwell_export.py`
- Modify: `tests/unit/adapters/test_maxwell3d_exporter.py`
- Modify: `tests/unit/adapters/test_femm_solver.py`
- Modify: `tests/fakes/maxwell_exporter.py`
- Modify: `tests/fakes/maxwell3d_app.py`
- Modify: `tests/fakes/femm_solver.py`
- Create: `tests/golden/m6-maxwell3d-run-manifest.json`
- Create: `tests/golden/m6-maxwell2d-run-manifest.json`
- Create: `tests/golden/m6-femm-run-manifest.json`

**Interfaces:**

- Produces one shared `generate_run(...) -> RunOutcome`.
- `RunOutcome` contains the planned run, adapter result, and immutable
  `RunManifest`.
- Rename existing backend executors to `_export_maxwell3d_plan`,
  `_export_maxwell2d_plan`, and `_export_femm_plan`; only `generate_run` calls
  them.
- Generate and Solve returns an explicit M8-not-implemented block before any
  adapter call.

- [ ] **Step 1: Write failing application and golden-manifest tests.**

For the same Project, generate recording outcomes for all three backends and
assert each manifest records:

- same Project id, frequency, temperatures, winding ids, RMS current, peak
  current, phase, DC current, exact material revision, and B-H series;
- backend-specific dimensional representation and approximation warning;
- requested outputs and recipe;
- adapter stage/artifact evidence;
- no Normalized Result Set for Generate Only.

Assert `generate_run` with `RunMode.GENERATE_AND_SOLVE` raises:

```text
Generate and Solve execution belongs to M8; M6 only validates its Run Request.
```

and makes zero adapter calls.

- [ ] **Step 2: Add failing Geometry-Only adapter contract tests.**

The recording/fake Maxwell 3D adapter must produce these stages:

```python
GEOMETRY_ONLY_STAGE_NAMES = ("launch", "units", "core", "windings", "save")
```

Assert no calls to material creation/assignment, terminals, excitations, eddy,
region, mesh, setup, matrix, reports, or design validation.

- [ ] **Step 3: Run and verify failures.**

```bash
.venv/bin/python -m pytest tests/unit/application/test_maxwell_export.py \
  tests/contract/test_maxwell_exporter_contract.py \
  tests/contract/test_femm_solver_contract.py \
  tests/unit/adapters/test_maxwell3d_exporter.py \
  tests/unit/adapters/test_femm_solver.py -q
```

- [ ] **Step 4: Add the minimal Geometry-Only adapter request.**

Define a separate port DTO:

```python
@dataclass(frozen=True, slots=True)
class Maxwell3dGeometryOnlyRequest:
    plan: GeometryOnlyMaxwell3dPlan
    release: AedtRelease
    edition: AedtEdition
    non_graphical: bool
    output_directory: Path
    project_name: str
    design_name: str = "Inductor3D_GeometryOnly"
```

Do not weaken `Maxwell3dDesignPlan` with optional materials/setup fields.
Extend `Maxwell3dExporter` with:

```python
def export_geometry_only(
    self, request: Maxwell3dGeometryOnlyRequest
) -> Maxwell3dExportResult: ...
```

The adapter reuses its existing core profile and winding path creation helpers,
but omits every prohibited stage and creates winding solids without a material
argument.

- [ ] **Step 5: Implement `generate_run` and manifest serialization.**

Use the fixed support constants from `application.services.aedt_support` when
building Maxwell requests; Project no longer stores AEDT target. Capability
lookup remains an injected snapshot.

Use this public signature:

```python
AdapterResult = MaxwellExportResult | FemmSolveResult


@dataclass(frozen=True, slots=True)
class RunOutcome:
    planned_run: PlannedRun
    adapter_result: AdapterResult
    manifest: RunManifest


def generate_run(
    project: InductorProject,
    request: RunRequest,
    catalog: CatalogRepository,
    capabilities: CapabilitySnapshot,
    output_directory: Path,
    *,
    maxwell3d_exporter: Maxwell3dExporter,
    maxwell2d_exporter: Maxwell2dExporter,
    femm_solver: FemmSolver,
    run_id: str,
    application_version: str,
    non_graphical: bool = True,
) -> RunOutcome:
```

For FEMM Generate Only, call the existing solver port with `analyze=False`.
Add `adapter_version: str | None` and `solver_version: str | None` to
`FemmSolveResult`; populate observed values when the adapter exposes them and
leave them `None` otherwise. Maxwell manifests use the export result's
`pyaedt_version` as adapter version and the fixed requested `2025.2` release as
solver version. Never infer an unobserved FEMM executable version.

Keep JSON conversion in application code:

```python
def run_manifest_to_document(manifest: RunManifest) -> dict[str, object]: ...


def run_manifest_json(manifest: RunManifest) -> str:
    return json.dumps(
        run_manifest_to_document(manifest),
        indent=2,
        sort_keys=True,
    ) + "\n"
```

- [ ] **Step 6: Match golden manifests.**

Normalize only nondeterministic fields in test setup: inject fixed `run_id`,
application version, adapter version, and artifact paths. Do not scrub physical
inputs, warnings, stages, or status.

- [ ] **Step 7: Run focused checks.**

```bash
.venv/bin/python -m pytest tests/unit/application/test_maxwell_export.py \
  tests/contract/test_maxwell_exporter_contract.py \
  tests/contract/test_femm_solver_contract.py \
  tests/unit/adapters/test_maxwell3d_exporter.py \
  tests/unit/adapters/test_femm_solver.py -q
.venv/bin/python -m ruff check \
  src/inductor_designer/application/services/maxwell_export.py \
  src/inductor_designer/application/ports/maxwell_exporter.py \
  src/inductor_designer/application/ports/femm_solver.py \
  src/inductor_designer/adapters/pyaedt/maxwell3d.py \
  src/inductor_designer/adapters/femm/solver.py \
  tests/contract/test_maxwell_exporter_contract.py \
  tests/contract/test_femm_solver_contract.py \
  tests/unit/application/test_maxwell_export.py \
  tests/unit/adapters/test_maxwell3d_exporter.py \
  tests/unit/adapters/test_femm_solver.py
.venv/bin/python -m mypy \
  src/inductor_designer/application/services/maxwell_export.py \
  src/inductor_designer/application/ports/maxwell_exporter.py \
  src/inductor_designer/application/ports/femm_solver.py \
  src/inductor_designer/adapters/pyaedt/maxwell3d.py \
  src/inductor_designer/adapters/femm/solver.py
.venv/bin/python -m tools.check_architecture
```

- [ ] **Step 8: Commit.**

```bash
git add src/inductor_designer/application/services/maxwell_export.py \
  src/inductor_designer/application/ports/maxwell_exporter.py \
  src/inductor_designer/application/ports/femm_solver.py \
  src/inductor_designer/adapters/pyaedt/maxwell3d.py \
  src/inductor_designer/adapters/femm/solver.py \
  tests/contract/test_maxwell_exporter_contract.py \
  tests/contract/test_femm_solver_contract.py \
  tests/unit/application/test_maxwell_export.py \
  tests/unit/adapters/test_maxwell3d_exporter.py \
  tests/unit/adapters/test_femm_solver.py \
  tests/fakes/maxwell_exporter.py tests/fakes/maxwell3d_app.py \
  tests/fakes/femm_solver.py \
  tests/golden/m6-*-run-manifest.json
git commit -m "feat(application): generate runs with traceable manifests"
```

**Acceptance criteria:** all Generate Only paths use Run Request/Run Manifest;
Geometry-Only output cannot accidentally contain solve-ready configuration.

---

### Task 8: Move existing entry points to M6 contracts

**Owner:** M6 implementer

**Dependencies:** Task 7

**Allowed files:**

- Modify: all source/tests/tools that still reference removed Project fields
- Modify: `src/inductor_designer/ui/generation_lines.py`
- Modify: `src/inductor_designer/ui/main.py`
- Modify: `src/inductor_designer/application/services/simulation_summary.py`
- Modify: `src/inductor_designer/mcp_server/tools.py`
- Modify: `tools/generate_maxwell3d.py`
- Modify: `tools/generate_maxwell2d.py`
- Modify: `tools/prepare_material_handoff.py`
- Modify: matching tests

**Interfaces:**

- Existing UI/CLI/MCP surfaces construct `RunRequest`; they do not duplicate
  planning rules.
- Existing MCP tool count and names stay unchanged; this is compatibility
  maintenance, not MCP expansion.
- `tools/generate_maxwell2d.py --force-2d` is removed because dimensional mode
  no longer exists.

- [ ] **Step 1: Find every stale contract reference.**

Run:

```bash
rg -n "dimension_mode|dimensionMode|ac_magnitude_a|acMagnitudeA|target_release|\
target_edition|frequency_hz" src tests tools schemas \
  --glob '!src/inductor_designer/materials/**' \
  --glob '!src/inductor_designer/adapters/materials/**' \
  --glob '!tests/unit/materials/**' \
  --glob '!tests/unit/adapters/test_material_*'
```

Classify each `frequency_hz`: material curve conditions, solver setup, and FEMM
problem fields remain valid; only per-winding Project usage is removed.

- [ ] **Step 2: Update all test factories before production callers.**

Replace root-level `dataclasses.replace(project, dimension_mode=...)` with
different `RunRequest` values. Replace excitation mutations with nested
Operating Point replacements. Update recording adapter assertions from `2.0`
peak to `2.0 * sqrt(2.0)`.

- [ ] **Step 3: Update CLI, UI plumbing, and MCP.**

- Maxwell 3D CLI creates `RunRequest(MAXWELL_3D, GENERATE_ONLY)`.
- Maxwell 2D CLI maps `--backend aedt|femm` to
  `MAXWELL_2D|FEMM`; delete `--force-2d`.
- Existing UI backend labels map to RunBackend and Generate Only.
- Existing MCP generation tools create Run Requests and return the shared Run
  Manifest document.
- Capability lookup always uses the fixed AEDT 2025 R2 Commercial constants.
- `simulation_summary` says the Project is backend-independent and reports
  shared Operating Point data; it does not select a dimension.
- Delete `generation_manifest_json`, `femm_manifest_json`, `Backend2d`, and
  their separate schema-v2 payloads after the last caller moves to
  `run_manifest_json`.

- [ ] **Step 4: Run all non-live tests.**

```bash
QT_QPA_PLATFORM=offscreen QSG_RHI_BACKEND=software \
  .venv/bin/python -m pytest -m "not aedt and not femm" -q
```

Expected: all unit, contract, integration, property, MCP, and UI tests pass.

- [ ] **Step 5: Run stale-symbol guard.**

```bash
rg -n "dimensionMode|dimension_mode|acMagnitudeA|ac_magnitude_a|\
WindingDefinition\\([^)]*frequency" src tests tools schemas
```

Expected: no matches. Material curve `frequency_hz`, Operating Point
`frequency_hz`, solver setup `frequency_hz`, and FEMM problem `frequency_hz`
remain.

- [ ] **Step 6: Run focused quality gates.**

```bash
.venv/bin/python -m ruff check .
.venv/bin/python -m mypy src tools
.venv/bin/python -m tools.check_architecture
git diff --check
```

- [ ] **Step 7: Commit.**

```bash
git add src tests tools schemas/project
git commit -m "refactor: move entry points to m6 run requests"
```

**Acceptance criteria:** repository has no runtime dependency on v4 Project
semantics; current optional surfaces still work through shared M6 services.

---

### Task 9: Prove M6 acceptance and hand off M7

**Owner:** M6 implementer

**Dependencies:** Tasks 1–8

**Allowed files:**

- Modify: `docs/architecture/README.md`
- Modify: `docs/development/ROADMAP.md`
- Modify: `docs/development/automation-mcp-femm.md`
- Modify: `docs/development/maxwell2d-generation.md`
- Modify: `docs/development/maxwell3d-generation.md`
- Modify: `docs/superpowers/plans/README.md`
- Modify: this plan only to check completed boxes and record exact evidence

**Interfaces:**

- Produces accepted M6 contracts for the already-approved M7 implementation
  plan.
- Does not write the M7 plan in this task.

- [ ] **Step 1: Run the complete M6 gate from a clean process.**

```bash
.venv/bin/python -m ruff check .
.venv/bin/python -m mypy src tools
.venv/bin/python -m tools.check_architecture
QT_QPA_PLATFORM=offscreen QSG_RHI_BACKEND=software \
  .venv/bin/python -m pytest -m "not aedt and not femm" \
  --cov=inductor_designer --cov-report=term-missing
git diff --check
```

Expected: every command exits 0 and branch coverage is at least 80%.

- [ ] **Step 2: Run the M6 acceptance test explicitly.**

Add or update `tests/integration/test_project_round_trip.py` so one v5 Project:

1. saves, loads, and saves byte-identically;
2. preserves shared frequency, both temperatures, exact material revision and
   B-H series, Manual acknowledgment state, RMS current, phase, DC current, and
   direction;
3. produces Maxwell 3D, Maxwell 2D, and FEMM recording plans;
4. records identical effective inputs and the one RMS/peak conversion in all
   three golden manifests.

Run:

```bash
.venv/bin/python -m pytest tests/integration/test_project_round_trip.py -q
```

- [ ] **Step 3: Review physical and compatibility assumptions.**

Confirm in the diff:

- accepted 16-facet conductor and initial Maxwell mesh settings are unchanged;
- no material/catalog value or B-H/core-loss data changed;
- no 2024/Student/fallback support returned;
- no adapter multiplies RMS current;
- 2D approximation warnings remain explicit;
- unresolved material never reaches normal generation;
- Geometry-Only has no solve-ready stages.

- [ ] **Step 4: Update documentation.**

Record M6 as accepted only after Steps 1–3 pass. Update architecture from
“target” to implemented v5 contracts. Update CLI/MCP docs for Run Request and
remove `dimensionMode`/`--force-2d` guidance. In the plan index, record exact
commands, test counts, coverage, commit, and any unresolved risk.

- [ ] **Step 5: Commit the acceptance record.**

```bash
git add docs tests/integration/test_project_round_trip.py
git commit -m "docs: accept m6 project foundation"
```

- [ ] **Step 6: Verify clean handoff.**

```bash
git status --short --branch
git log -10 --oneline --decorate
```

Expected: only the pre-existing untracked `.DS_Store` files and `outputs/`
remain. The next task is the detailed M7 implementation plan derived from
`docs/superpowers/specs/2026-07-26-preliminary-calculations-and-guided-flow-design.md`;
do not reopen approved M7 physics or product behavior unless M6 exposed a
documented contradiction.

**Acceptance criteria:** M6 exit criterion is evidenced, documented, and
committed; M7 can target stable Project/Run interfaces.

## Final Acceptance Checklist

- [ ] One v5 Project round-trips byte-identically.
- [ ] Project contains Design, one Operating Point, and Simulation Recipe.
- [ ] Project stores no backend, dimension, AEDT target, or generated artifact.
- [ ] Frequency and temperatures are shared Operating Point fields.
- [ ] Each Design winding has exactly one Operating Point entry.
- [ ] AC RMS and AC peak are explicit; conversion exists once.
- [ ] One exact compatible material revision and B-H series are pinned.
- [ ] Manual material compatibility acknowledgment persists and validates.
- [ ] Confirmed Maxwell 3D Geometry-Only is the sole unresolved-material run.
- [ ] Maxwell 3D, Maxwell 2D, and FEMM plans share identical effective inputs.
- [ ] Run Manifest and Normalized Result Set contracts are immutable and
  backend-labeled.
- [ ] All non-live tests, Ruff, strict mypy, architecture checks, coverage, and
  diff hygiene pass.
- [ ] M6 acceptance evidence and M7 handoff are recorded.
