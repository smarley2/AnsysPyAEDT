# Milestone 5a: Material Records Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Traceable, reproducible magnetic-material records: import curve data (CSV now, image-extraction data model now for the M5b UI), fit Steinmetz coefficients and permeability, run physics checks, store draft→reviewed→approved revisions in a local overlay with full provenance — and export only approved revisions to Maxwell (nonlinear B-H + core loss, both dims) and FEMM (B-H points). This is the milestone's exit-criterion half; the Material Studio UI (image crop/calibrate/click-extract editor) follows as plan M5b.

**Architecture:** The `materials` package grows from identity-only to the real domain: record/series/provenance dataclasses, axis-calibration + pixel-extraction transforms (pure — the M5b UI will only *produce* these records), stdlib least-squares Steinmetz fitting, declarative physics validation, deterministic JSON+CSV serde with SHA-256 source hashing, and a replay engine that recomputes every series and fit from stored sources and compares byte-rounded results — the exit criterion as code. A `MaterialRepository` port + filesystem overlay adapter stores revisions (approved = immutable). Project schema v3 snapshots approved material revisions; the export services resolve them and feed nonlinear data to all three backends.

**Tech Stack:** stdlib only (json, csv-free hand rendering, hashlib, math — Steinmetz is a 3×3 linear solve). No new dependencies.

## Global Constraints

- Python `>=3.10,<3.14`; mypy strict over `src` and `tools`; Ruff line 100 (`E,F,I,B,UP,ANN,SIM`); branch coverage `fail_under = 80`.
- Architecture (`tools/check_architecture.py`, now also forbidding `femm`/`mcp` in inner+application): `materials` stays pure — json/hashlib/math are stdlib-allowed; **no os/pathlib** (filesystem lives in `adapters/materials`). `application` may import `materials`.
- Every file starts with `from __future__ import annotations`; frozen slots dataclasses with `__post_init__` invariants.
- Canonical units: tesla (B), A/m (H), W/m³ (loss density), Hz, °C (temperature stored as plain float °C). Datasheet units (G, kG, Oe, kA/m, mW/cm³, kW/m³, mT) convert on import via `domain/units.py`.
- Determinism: every float in a record, fit, or manifest is `round(x, 9)`; identical inputs → byte-identical `record.json` and points CSV. Revision ids derive from content, not clocks.
- AEDT/FEMM-touching tests keep their markers (`aedt`, `femm`); CI filter unchanged (`-m "not aedt and not femm"`). pyaedt/pyfemm API facts below are verified against the installed libraries; live runs are still the arbiter (M4 convention).
- Environment: `.venv\Scripts\python.exe`. Gates after every task: `-m pytest tests -q -m "not aedt and not ui and not femm"`, `-m ruff check .`, `-m mypy`, `.venv\Scripts\python.exe tools/check_architecture.py` (+ `-m pytest tests -q -m ui` on UI-adjacent tasks — none here).
- Conventional commits.

## Design decisions (proposed — Fabio: veto before execution)

- **D0 — Milestone split.** M5a (this plan) = records pipeline + solver export; satisfies the ROADMAP exit criterion ("a reviewer can reproduce a material record from its stored source metadata and transformation history"). M5b (next plan) = Material Studio UI: image load, crop, axis-calibration clicks, point extraction/editing, review/approve screens. OCR and the GPL `materialdatabase` importer stay deferred beyond M5b (spec allows: OCR only ever proposes).
- **D1 — Storage:** overlay lives at `materials-overlay/` in the repo root (NOT gitignored — committing reviewed materials to git is itself provenance; Fabio's choice per record). Layout: `materials-overlay/<manufacturer>/<name>/<grade>/<revision>/record.json + points-<series>.csv + sources/<original files>`. `record.json` is deterministic (sort_keys, indent 2, trailing newline) like project files; points as CSV per spec §5.1.
- **D2 — States:** new `MaterialStatus` enum `draft/reviewed/approved` in the materials package (catalog `ReviewStatus` stays two-state and untouched). Export accepts **approved only** — non-approved raises a typed error (stricter than the spec's "blocking confirmation"; the UI can add a confirm flow in M5b). Approved revisions are immutable in the repository (overwrite refused).
- **D3 — Representations in M5a:** B-H point table (monotone, canonical units), scalar relative permeability, loss table (P vs B per-frequency series) + Steinmetz fit (k, α, β with residuals). Explicit formula representation deferred to M5b+.
- **D4 — Fitting is stdlib:** Steinmetz `log10 P = log10 k + α·log10 f + β·log10 B` is a linear least-squares in 3 unknowns → normal equations solved by Cramer's rule. No numpy/scipy. B-H needs no fit (solvers take point tables). `mean_relative_permeability` derives μr from low-field B-H slope.
- **D5 — Image workflow in M5a = data model only.** `AxisCalibration` (linear/log), `CropRegion`, `PixelPoint`, `ExtractionRecord`, and `extract_points` are implemented and replayable now; the interactive screen that produces them is M5b. CSV import is fully usable today.
- **D6 — Physics checks (spec §9.9):** unit-family checks per series kind; range (0 ≤ B ≤ 5 T, 0 ≤ H ≤ 1e7 A/m, P > 0, 1 ≤ μr ≤ 1e6); strict monotonicity + duplicate-H rejection for B-H; B-H starts at (0, 0); dB/dH ≥ μ0 (warning below); loss series require a frequency condition. Errors block review/approval; warnings recorded.
- **D7 — Provenance:** every series links a `SourceProvenance` (kind image/csv, filename, sha256, url, page, captured_at ISO, description) and, for image series, an `ExtractionRecord`. Revision id = first 12 hex of sha256 over the canonical record JSON with the revision field blanked — content-addressed, clock-free.
- **D8 — Reproducibility engine (exit criterion):** `reproduce_record(record, sources)` re-hashes sources, re-parses CSVs / re-runs extractions, re-fits Steinmetz, and compares everything to the stored values after `round(9)`. `tools/reproduce_material.py` exits 0 only on a full match; the integration test proves match AND tamper-detection.
- **D9 — Project schema v3:** optional `materials` array of `{ref, revisionId, snapshot}` (snapshot = full record sans binary sources); `dataclasses`-level `InductorProject.materials: tuple[MaterialRevisionSelection, ...] = ()`; `_migrate_v2_to_v3` adds `[]`. Deterministic saves unchanged.
- **D10 — Export integration:** `MaterialSpec` gains `bh_curve: tuple[tuple[float, float], ...] = ()` (B, H pairs — pyaedt's order) and `steinmetz: SteinmetzFitSpec | None = None`. When the project carries an approved material matching the core's `MaterialRef`, `material_spec_from_material_record` builds the spec (name suffixed `_r<revision>`); otherwise the M3 grade fallback still applies (with a note). **Approved B-H records unblock ferrite cores.** Adapters — verified against installed libs: pyaedt nonlinear B-H = `material.permeability = [[b, h], ...]` (documented list-of-pairs setter); Steinmetz = `material.set_power_ferrite_coreloss(cm=k, x=alpha, y=beta)`; FEMM B-H = `mi_addbhpoints(name, b_h_pairs)` (verify-at-FEMM). DC-bias linear-material caveat note drops when a B-H record is applied.
- **D11 — CGS units:** `units.py` gains T/mT/G/kG (→T), A/m / kA/m / Oe (→A/m, Oe = 1000/4π), W/m³ / kW/m³ / mW/cm³ (→W/m³). Magnetics catalogs are CGS — Oe/G first-class.
- **D12 — MCP material tools deferred to M5b** (list/approve/inspect materials over MCP) — the pipeline lands first.

## File structure

| File | Responsibility |
|---|---|
| `src/inductor_designer/domain/units.py` (modify) | B/H/loss unit factors |
| `src/inductor_designer/materials/records.py` (new) | Status, provenance, series, record, transitions |
| `src/inductor_designer/materials/calibration.py` (new) | Axis calibration, crop, pixel→data extraction |
| `src/inductor_designer/materials/fitting.py` (new) | Steinmetz LSQ, μr derivation, residuals |
| `src/inductor_designer/materials/validation.py` (new) | Physics/unit/monotonicity checks |
| `src/inductor_designer/materials/serde.py` (new) | record↔json, points↔csv, sha256, revision id |
| `src/inductor_designer/materials/replay.py` (new) | Reproducibility engine |
| `src/inductor_designer/application/ports/material_repository.py` (new) | Overlay port |
| `src/inductor_designer/adapters/materials/overlay_repository.py` (new) | Filesystem overlay (approved immutable) |
| `src/inductor_designer/application/services/material_import.py` (new) | CSV import, draft creation |
| `schemas/project/v3.schema.json` (new); persistence serde/migration (modify) | Schema v3 |
| `src/inductor_designer/simulation/{maxwell_plan,plan_builder,plan_builder2d,femm_problem}.py`; both pyaedt adapters; `adapters/femm/solver.py`; export services (modify) | Approved-material export |
| `tools/reproduce_material.py` (new) | Exit-criterion CLI |
| `tests/fakes/material_repository.py` (new) | In-memory fake |

---

### Task 1: Magnetic units

**Files:** Modify `src/inductor_designer/domain/units.py`; extend `tests/unit/domain/test_units.py`.

**Interfaces:** `to_canonical` accepts the new units per D11. Exact factors: `"T": 1.0, "mT": 1e-3, "G": 1e-4, "kG": 0.1, "A/m": 1.0, "kA/m": 1e3, "Oe": 79.57747154594767, "W/m3": 1.0, "kW/m3": 1e3, "mW/cm3": 1e3`.

- [ ] **Step 1: failing tests**

```python
def test_flux_density_units() -> None:
    assert to_canonical(1.0, "T") == 1.0
    assert to_canonical(1000.0, "G") == pytest.approx(0.1)
    assert to_canonical(10.0, "kG") == pytest.approx(1.0)
    assert to_canonical(100.0, "mT") == pytest.approx(0.1)


def test_field_strength_units() -> None:
    assert to_canonical(1.0, "Oe") == pytest.approx(79.57747154594767)
    assert to_canonical(2.0, "kA/m") == pytest.approx(2000.0)


def test_loss_density_units() -> None:
    assert to_canonical(1.0, "mW/cm3") == pytest.approx(1000.0)
    assert to_canonical(1.0, "kW/m3") == pytest.approx(1000.0)
```

- [ ] **Step 2:** run → FAIL (unknown unit). **Step 3:** add the ten entries to `_CONVERSIONS`. **Step 4:** gates. **Step 5:** commit `feat(domain): flux-density, field, and loss-density units`.

---

### Task 2: Material record domain

**Files:** Create `src/inductor_designer/materials/records.py`; test `tests/unit/materials/test_records.py`.

**Interfaces (all frozen slots):**

```python
class MaterialStatus(str, Enum):
    DRAFT = "draft"; REVIEWED = "reviewed"; APPROVED = "approved"

class SourceKind(str, Enum):
    IMAGE = "image"; CSV = "csv"

class SeriesKind(str, Enum):
    BH_CURVE = "bh-curve"; LOSS_TABLE = "loss-table"

@dataclass(frozen=True, slots=True)
class SourceProvenance:
    kind: SourceKind
    filename: str            # stored under sources/
    sha256: str              # 64 lowercase hex
    url: str
    page: int | None
    captured_at: str         # ISO 8601
    description: str

@dataclass(frozen=True, slots=True)
class CurveConditions:
    frequency_hz: float | None
    temperature_c: float | None
    dc_bias_a_per_m: float | None

@dataclass(frozen=True, slots=True)
class CurvePoint:
    x: float
    y: float

@dataclass(frozen=True, slots=True)
class PointSeries:
    series_id: str           # sanitized, unique within record
    kind: SeriesKind
    x_unit: str              # raw unit as imported ("Oe", "T", ...)
    y_unit: str
    conditions: CurveConditions
    points: tuple[CurvePoint, ...]   # CANONICAL units, sorted by x, round(9)
    source_filename: str     # links a SourceProvenance
    extraction: ExtractionRecord | None   # image series only

@dataclass(frozen=True, slots=True)
class SteinmetzFit:
    k: float; alpha: float; beta: float
    rms_relative_residual: float
    max_relative_residual: float

@dataclass(frozen=True, slots=True)
class MaterialRecord:
    ref: MaterialRef
    revision_id: str         # 12 lowercase hex ("" only transiently pre-hash)
    status: MaterialStatus
    created_at: str
    reviewed_by: str | None
    approved_by: str | None
    sources: tuple[SourceProvenance, ...]
    series: tuple[PointSeries, ...]
    relative_permeability: float | None
    steinmetz: SteinmetzFit | None
    notes: str
```

Invariants: sha256 64 hex; REVIEWED requires `reviewed_by`; APPROVED requires both; series ids unique; every `source_filename` names a provenance entry. Transitions (pure functions): `review_record(record, reviewer) -> MaterialRecord` (draft→reviewed), `approve_record(record, approver) -> MaterialRecord` (reviewed→approved) — wrong-state raises `ValueError`. `ExtractionRecord` imported from `materials.calibration` (Task 3) — declare the field as `extraction: "ExtractionRecord | None"` and build Task 2 first with a stub import guarded by `TYPE_CHECKING` + the runtime import added in Task 3, **or simply order Task 3 before Task 2 in execution**. Controller note: dispatch Task 3 first, then Task 2 (both small); the plan lists them in dependency order below anyway — implementer of Task 2 may assume `calibration.py` exists.

Tests: status transitions happy + wrong-state; invariant violations (bad sha, approved without approver, duplicate series id, dangling source link).

Commit: `feat(materials): material record domain with review states`.

*(Execution order note: run Task 3 before Task 2.)*

---

### Task 3: Axis calibration and extraction (run before Task 2)

**Files:** Create `src/inductor_designer/materials/calibration.py`; test `tests/unit/materials/test_calibration.py`.

**Interfaces:**

```python
class AxisScale(str, Enum):
    LINEAR = "linear"; LOG = "log"

@dataclass(frozen=True, slots=True)
class AxisCalibration:
    scale: AxisScale
    pixel_a: float; value_a: float
    pixel_b: float; value_b: float
    # invariants: pixel_a != pixel_b; value_a != value_b; LOG → both values > 0

    def value_at(self, pixel: float) -> float:
        t = (pixel - self.pixel_a) / (self.pixel_b - self.pixel_a)
        if self.scale is AxisScale.LINEAR:
            return self.value_a + t * (self.value_b - self.value_a)
        la, lb = math.log10(self.value_a), math.log10(self.value_b)
        return 10.0 ** (la + t * (lb - la))

@dataclass(frozen=True, slots=True)
class CropRegion:
    left: int; top: int; width: int; height: int   # width/height > 0, left/top >= 0

@dataclass(frozen=True, slots=True)
class PixelPoint:
    x_px: float; y_px: float

@dataclass(frozen=True, slots=True)
class ExtractionRecord:
    crop: CropRegion
    x_axis: AxisCalibration
    y_axis: AxisCalibration
    pixel_points: tuple[PixelPoint, ...]

def extract_points(record: ExtractionRecord) -> tuple[tuple[float, float], ...]:
    """Map pixel points to RAW-unit (x, y) pairs, round(9), preserving order."""
```

Tests: linear interpolation (two anchors → known midpoint), log axis (decade mapping: pixels 0/100 ↔ 1/100 → pixel 50 = 10), inverted pixel direction (screen-y down) works because anchors carry sign, LOG with non-positive value raises, extract_points round-trips a 3-point set.

Commit: `feat(materials): axis calibration and pixel extraction transforms`.

---

### Task 4: Steinmetz fitting

**Files:** Create `src/inductor_designer/materials/fitting.py`; test `tests/unit/materials/test_fitting.py`.

**Interfaces:**

```python
MU0 = 4e-7 * math.pi

class MaterialFitError(ValueError): ...

@dataclass(frozen=True, slots=True)
class LossSample:
    frequency_hz: float; flux_density_t: float; loss_w_per_m3: float  # all > 0

def fit_steinmetz(samples: Sequence[LossSample]) -> SteinmetzFit:
    """Least-squares in log10 space via 3x3 normal equations (Cramer's rule).

    Requires >= 3 samples, >= 2 distinct frequencies, >= 2 distinct flux
    densities (else MaterialFitError). Residuals are relative errors on P.
    k/alpha/beta and residuals round(9).
    """

def mean_relative_permeability(bh_points: Sequence[tuple[float, float]]) -> float:
    """mu_r from the average B/(mu0*H) over points with H > 0 (round(9))."""
```

Tests: exact synthetic recovery — generate P = 2.5·f^1.4·B^2.3 on a 3×3 (f, B) grid → fit returns k≈2.5, α≈1.4, β≈2.3 within 1e-6 and residuals ≈ 0; degenerate inputs raise (single frequency, single B, < 3 samples); μr from a linear B-H (B = μ0·60·H) → 60.0.

Commit: `feat(materials): stdlib Steinmetz fit and permeability derivation`.

---

### Task 5: Physics validation

**Files:** Create `src/inductor_designer/materials/validation.py`; test `tests/unit/materials/test_material_validation.py`.

**Interfaces:**

```python
class IssueSeverity(str, Enum):
    ERROR = "error"; WARNING = "warning"

@dataclass(frozen=True, slots=True)
class MaterialIssue:
    code: str; severity: IssueSeverity; message: str

def validate_series(series: PointSeries) -> tuple[MaterialIssue, ...]
def validate_record(record: MaterialRecord) -> tuple[MaterialIssue, ...]
```

Rules (D6): unit family per kind (BH: x ∈ {A/m, kA/m, Oe}, y ∈ {T, mT, G, kG}; LOSS: x ∈ B-units, y ∈ {W/m3, kW/m3, mW/cm3}) — code `unit-family`; ranges (`range-b`, `range-h`, `loss-positive`, `permeability-range`); BH: strictly increasing H (`monotonic-h`, duplicates → `duplicate-h`), strictly increasing B (`monotonic-b`), first point (0, 0) (`origin`), slope dB/dH ≥ μ0 → WARNING `slope-below-mu0` when violated; loss series need `conditions.frequency_hz` (`loss-frequency-missing`); record-level: at least one series or a scalar μr (`empty-record`); Steinmetz fit present requires ≥1 loss series (`fit-without-data`). `review_record`/`approve_record` integration happens in Task 8 (service refuses transitions when ERROR issues exist) — validation itself stays pure here.

Tests per rule (one good, one violating case each; keep table-driven).

Commit: `feat(materials): physics and unit validation for material records`.

---

### Task 6: Deterministic serde

**Files:** Create `src/inductor_designer/materials/serde.py`; test `tests/unit/materials/test_material_serde.py`.

**Interfaces (pure — strings/dicts/bytes only):**

```python
def sha256_hex(data: bytes) -> str
def material_record_to_json(record: MaterialRecord, *, include_revision: bool = True) -> dict[str, object]   # camelCase keys like project serde
def material_record_from_json(document: Mapping[str, Any]) -> MaterialRecord
def material_record_json(record: MaterialRecord) -> str    # dumps(..., indent=2, sort_keys=True) + "\n"
def revision_id_for(record: MaterialRecord) -> str          # sha256_hex(json with revision blanked)[:12]
def points_csv(series: PointSeries) -> str                  # "x,y\r\n"-free: "x,y\n" + rows using repr(round(v,9)) — deterministic
def parse_points_csv(text: str) -> tuple[tuple[float, float], ...]
```

Round-trip fidelity: `material_record_from_json(material_record_to_json(r)) == r` (dataclass equality). Points CSV is authoritative for series points on disk; `record.json` also embeds them (single source read path = record.json; CSVs exist for human/Excel review — assert they agree at load in the adapter, Task 7).

Tests: round trip on a full record (2 sources, BH + loss series with extraction on one); byte-identical double render; revision id stable under re-render and CHANGES when a point changes; parse_points_csv rejects malformed rows.

Commit: `feat(materials): deterministic record and points serialization`.

---

### Task 7: Overlay repository (port + filesystem adapter + fake)

**Files:** Create `src/inductor_designer/application/ports/material_repository.py`, `src/inductor_designer/adapters/materials/__init__.py` + `overlay_repository.py`, `tests/fakes/material_repository.py`; tests `tests/unit/adapters/test_overlay_repository.py`, contract `tests/contract/test_material_repository_contract.py`.

**Interfaces:**

```python
class MaterialLookupError(KeyError): ...

class MaterialRepository(Protocol):
    def list_revisions(self, ref: MaterialRef) -> tuple[str, ...]: ...
    def get(self, ref: MaterialRef, revision_id: str) -> MaterialRecord: ...
    def latest_approved(self, ref: MaterialRef) -> MaterialRecord | None: ...
    def save(self, record: MaterialRecord, sources: Mapping[str, bytes]) -> None: ...
    def source_bytes(self, ref: MaterialRef, revision_id: str) -> Mapping[str, bytes]: ...
```

`FileOverlayMaterialRepository(root: Path)`: layout per D1 (`sanitize_identifier` on path segments); `save` writes `record.json`, `points-<series>.csv` per series, `sources/<filename>` bytes; **verifies each source's sha256 against its provenance before writing** (mismatch → ValueError); refuses `save` when the target revision directory exists AND its stored status is approved (immutability), plain overwrite allowed for draft/reviewed re-saves of the SAME revision id; `get` re-verifies source hashes and CSV/JSON point agreement on load (M4 lesson: verify persisted artifacts). `latest_approved` = lexicographically... revision ids are content hashes (unordered) — use the record's `created_at` for recency among approved revisions. In-memory `InMemoryMaterialRepository` fake mirrors semantics. Contract test runs the SAME assertions against both implementations (parametrized fixture): save→get round trip, approved immutability, hash-mismatch rejection, latest_approved picks newest created_at, unknown ref → MaterialLookupError.

Commit: `feat(adapters): filesystem material overlay with approved immutability`.

---

### Task 8: CSV import service and draft lifecycle

**Files:** Create `src/inductor_designer/application/services/material_import.py`; test `tests/unit/application/test_material_import.py`.

**Interfaces:**

```python
class MaterialImportError(ValueError):
    def __init__(self, issues: tuple[str, ...]) -> None: ...  # .issues, "; ".join message

def import_curve_csv(
    text: str, *, series_id: str, kind: SeriesKind, x_unit: str, y_unit: str,
    conditions: CurveConditions, source: SourceProvenance,
) -> PointSeries
    # parse via materials.serde.parse_points_csv, canonicalize via to_canonical,
    # sort by x, round(9); unit-family violations from validate_series raise MaterialImportError

def new_draft_record(
    ref: MaterialRef, *, series: tuple[PointSeries, ...],
    sources: tuple[SourceProvenance, ...], created_at: str,
    relative_permeability: float | None = None, fit_steinmetz_from_losses: bool = True,
    notes: str = "",
) -> MaterialRecord
    # optional auto-fit: collects LossSample(f from conditions, B=x, P=y) across
    # LOSS_TABLE series and attaches SteinmetzFit when >= the fit minimums;
    # revision_id = revision_id_for(...); status DRAFT

def review_material(record: MaterialRecord, reviewer: str) -> MaterialRecord
def approve_material(record: MaterialRecord, approver: str) -> MaterialRecord
    # both run validate_record first; any ERROR issue -> MaterialImportError
```

Tests: CSV in Oe/kG → canonical A/m//T points sorted; loss import + auto Steinmetz (reuse Task 4 synthetic grid via two CSV texts at two frequencies); review/approve blocked on an ERROR-carrying record (e.g. non-monotone BH), allowed on clean; revision id changes when a series changes.

Commit: `feat(application): CSV material import and review lifecycle`.

---

### Task 9: Reproducibility engine (exit criterion core)

**Files:** Create `src/inductor_designer/materials/replay.py`; test `tests/unit/materials/test_replay.py`.

**Interfaces:**

```python
@dataclass(frozen=True, slots=True)
class ReproductionReport:
    matches: bool
    mismatches: tuple[str, ...]   # human-readable, one per divergence

def reproduce_record(record: MaterialRecord, sources: Mapping[str, bytes]) -> ReproductionReport
```

Checks, in order, each divergence appended (never early-return): (1) every provenance sha256 matches `sha256_hex(sources[filename])` (missing file = mismatch); (2) per series — CSV kind: re-parse source bytes as text, re-canonicalize with the stored x_unit/y_unit (import logic shared: move the canonicalize+sort+round core into `materials/serde.py` or a small `materials/canonical.py` helper both this and Task 8 call — do NOT duplicate it), compare to stored points exactly; IMAGE kind: re-run `extract_points(series.extraction)`, canonicalize, compare; (3) when `record.steinmetz` present: re-collect loss samples, re-run `fit_steinmetz`, compare k/α/β/residuals exactly; (4) `revision_id_for(record) == record.revision_id`.

Tests: full match on a record built through Task 8 paths (CSV + synthetic image extraction whose "source" is arbitrary bytes hashed at build time); tamper each layer independently (flip a source byte → sha mismatch; edit a stored point → series mismatch; perturb stored k → fit mismatch; wrong revision id) and assert the specific mismatch string appears while others stay silent.

Commit: `feat(materials): reproduce records from sources and transformation history`.

---

### Task 10: Project schema v3

**Files:** Create `schemas/project/v3.schema.json` (copy v2, bump `schemaVersion` const to 3, add optional `materials` array — items `{ref: materialRef, revisionId: string, snapshot: object}`); modify `src/inductor_designer/domain/project.py` (`MaterialRevisionSelection(ref: MaterialRef, revision_id: str, snapshot: MaterialRecord)`; `InductorProject.materials: tuple[MaterialRevisionSelection, ...] = ()` as LAST field), `adapters/persistence/project_repository.py` (`project_to_document` writes schemaVersion 3 + materials via `material_record_to_json`; `project_from_document` reads them), `adapters/persistence/schema_repository.py` (`_migrate_v2_to_v3(document)` adds `"materials": []`; wire it following the existing `_migrate_v1_to_v2` registration — read the file), fixture/goldens as needed (sample project fixture gains `"schemaVersion": 3, "materials": []` — check which tests assert the literal version and update: round-trip test, any golden project bytes).

Tests: v2 document loads and migrates (materials == ()); v3 with one approved snapshot round-trips byte-identically; deterministic save unchanged for the sample fixture.

Commit: `feat(persistence): project schema v3 with material revision snapshots`.

---

### Task 11: Export integration — approved materials to AEDT and FEMM

**Files:** Modify `src/inductor_designer/simulation/maxwell_plan.py` (`MaterialSpec` + `SteinmetzFitSpec(k, alpha, beta)` frozen dataclass or reuse `SteinmetzFit` — REUSE `materials.SteinmetzFit` (simulation may import materials); fields `bh_curve: tuple[tuple[float, float], ...] = ()` (B, H order) and `steinmetz: SteinmetzFit | None = None` appended with defaults; new `material_spec_from_material_record(core_record: CoreRecord, material: MaterialRecord) -> MaterialSpec` — requires `status is APPROVED` else `PlanBuildError`; name `sanitize_identifier(f"{ref...}_r{revision_id}")`; μr from record scalar or `mean_relative_permeability(bh)`; bh_curve from the BH series (canonical (H,B) stored as x=H,y=B → emit (B, H) pairs for pyaedt); conductivity 0; draft=False), `plan_builder.py`/`plan_builder2d.py` (new optional `material_record: MaterialRecord | None = None` param → use `material_spec_from_material_record` when given — this BYPASSES the powder-family check, unblocking ferrites; note dropped linear caveat in `dc_bias_notes` call when bh present — add parameter or note variant), export services (resolve: project.materials entry whose `ref == core_selection.snapshot.material` → pass its snapshot; approved enforced in the spec builder), manifest `coreMaterial` block gains `bhPointCount`, `steinmetz` (k/alpha/beta or null), `materialRevision` (or null); `adapters/pyaedt/maxwell3d.py` + `maxwell2d.py` `_stage_materials`:

```python
    material = app.materials.add_material(spec.name)
    if spec.bh_curve:
        material.permeability = [[b, h] for b, h in spec.bh_curve]   # nonlinear setter (verified API)
    else:
        material.permeability = spec.relative_permeability
    material.conductivity = spec.conductivity_s_per_m
    if spec.steinmetz is not None:
        material.set_power_ferrite_coreloss(
            cm=spec.steinmetz.k, x=spec.steinmetz.alpha, y=spec.steinmetz.beta
        )
```

`simulation/femm_problem.py` `FemmMaterial` gains `bh_points: tuple[tuple[float, float], ...] = ()` ((B,H) pairs), populated from the plan's core MaterialSpec; `adapters/femm/solver.py` after `mi_addmaterial`: `if material.bh_points: femm.mi_addbhpoints(material.name, [[b, h] for b, h in material.bh_points])` (verify-at-FEMM; μ args in mi_addmaterial stay as the scalar for the linear fallback FEMM needs pre-BH). Fakes updated (fake pyaedt material records `permeability` assignments incl. list; fake femm module gains `mi_addbhpoints`).

Tests: spec-from-record approved happy + non-approved refused + ferrite CoreRecord with approved record passes; plan builders thread the record; adapter unit tests assert the nonlinear assignment shape and `set_power_ferrite_coreloss` args (3D + 2D), femm solver test asserts `mi_addbhpoints` call; manifest block extended assertions; existing grade-fallback tests stay green (default params).

Commit: `feat(simulation): approved material records drive nonlinear solver materials`.

---

### Task 12: Reproduce CLI and exit-criterion integration test

**Files:** Create `tools/reproduce_material.py`; tests `tests/unit/tools/test_reproduce_material.py`, `tests/integration/test_material_reproducibility.py`.

CLI: `main(argv=None) -> int` — `--overlay-root` (default `materials-overlay`), `--manufacturer --name --grade --revision`; loads via `FileOverlayMaterialRepository`, runs `reproduce_record`, prints `MATCH` or one line per mismatch; exit 0 iff match.

Integration test (the milestone exit-criterion proof): build a real record end-to-end — synthetic loss CSVs at two frequencies + a BH CSV + one image-extraction series over fake PNG bytes → `new_draft_record` → validate → review → approve → `save` to a tmp overlay → **fresh load** → `reproduce_record` matches; then tamper the stored `record.json` (edit one point) and a source byte in separate copies → CLI exits 1 naming the mismatch. Also: project schema v3 carries the approved snapshot → `export_femm2d`/`export_maxwell3d` (recording fakes) produce manifests with `materialRevision` and `bhPointCount > 0` — closing the loop from datasheet bytes to solver manifest.

Commit: `test: material records reproduce from sources end to end`.

---

### Task 13: Docs, gates, handoff

**Files:** Create `docs/development/material-records.md` (overlay layout, CSV import how-to with a worked Oe/mW-cm³ example, review/approve rules, reproduce CLI usage, solver export behavior incl. ferrite unblock + FEMM B-H, M5b scope note); ROADMAP M5 `### Current state` (M5a complete: list deliverables + exit-criterion evidence; explicitly: Material Studio UI, OCR, GPL importer, MCP material tools = M5b plan); README row; plans/README row.

Gates full set + coverage noted. Handoff to Fabio:

1. Import one REAL Magnetics datasheet: screenshot/CSV of the Kool Mu 60 core-loss + B-H curves → `import_curve_csv` (or hand-built CSV from catalog table), review + approve under your name, commit the overlay dir if wanted.
2. Attach it to a project (schema v3 materials entry), generate Maxwell 3D + FEMM, open both — check the nonlinear B-H curve and power-ferrite core-loss coefficients landed in AEDT (Material properties dialog), FEMM shows the B-H table (verify-at-FEMM arbitration for `mi_addbhpoints`).
3. `python -m tools.reproduce_material ...` on your record → MATCH.
4. Accept M5a in the ROADMAP; M5b (Studio UI) plan follows.

Commit: `docs: material records pipeline procedures and M5a status`.

---

## Self-review notes

- ROADMAP M5 bullets → coverage: CSV import (T8), image/axis-calibration model (T3, UI in M5b), fit models (T4: Steinmetz + μr; B-H point table needs no fit), unit/physics validation (T5), provenance (T2/T6/T7), approved-only export (T2/T8/T11), exit criterion (T9/T12).
- Execution order: **T1 → T3 → T2 → T4 → T5 → T6 → T7 → T8 → T9 → T10 → T11 → T12 → T13** (T3 before T2 for the ExtractionRecord import).
- Cross-task names: `MaterialStatus/MaterialRecord/PointSeries/SteinmetzFit` (T2→T4/T5/T6/T7/T8/T9/T11), `ExtractionRecord/extract_points` (T3→T2/T9), `fit_steinmetz/LossSample/mean_relative_permeability/MU0` (T4→T8/T9/T11), `validate_record/IssueSeverity` (T5→T8), serde fns + `revision_id_for` (T6→T7/T8/T9/T10), `MaterialRepository/FileOverlayMaterialRepository` (T7→T12), `import_curve_csv/new_draft_record/review_material/approve_material` (T8→T12), `reproduce_record/ReproductionReport` (T9→T12), `MaterialRevisionSelection` (T10→T11/T12), `material_spec_from_material_record` (T11→T12).
- Shared canonicalize helper (T8/T9) must live in ONE place — the T9 text names it; implementers must not duplicate.
- Verified-API facts baked in: pyaedt nonlinear `material.permeability = [[b, h], ...]` and `set_power_ferrite_coreloss(cm, x, y)` (read from installed pyaedt 1.2 source); FEMM `mi_addbhpoints` remains verify-at-FEMM (live test exists).
- M4/M4.5 lessons: overlay adapter verifies hashes + CSV/JSON agreement on load; solver-side changes get fake-call assertions AND ride the existing live-marked tests.
