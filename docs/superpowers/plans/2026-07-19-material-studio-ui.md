# Milestone 5b: Material Studio UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** Approved 2026-07-19; implementation pending.

**Approved specification:** `docs/superpowers/specs/2026-07-19-material-studio-ui-design.md`

**Goal:** Add a Guided Studio `Materials` page that exposes the complete manual and spreadsheet material workflow, lists every revision, and pins one explicit approved revision and B-H series into project schema v4.

**Architecture:** Pure application services provide revision summaries, immutable draft editing, lifecycle actions, and project pinning. A thin PySide6 controller adapts those services to focused QML components; filesystem, XLSX, image, PDF, and Qt types remain in adapters/UI. Existing M5a canonicalization, validation, fitting, replay, provenance, and atomic overlay persistence remain authoritative.

**Tech Stack:** Python 3.10–3.13, PySide6/QML/QtPdf from the existing `ui` extra, stdlib, `openpyxl>=3.1,<4`, pytest, pytest-qt-free offscreen Qt tests, Ruff, strict mypy, JSON Schema 2020-12.

## Global Constraints

- Follow `docs/superpowers/specs/2026-07-19-material-studio-ui-design.md`, `AGENTS.md`, and `docs/architecture/README.md`.
- Code, schemas, QML copy, documentation, branches, commits, and logs use English; visible QML strings use `qsTr`.
- `domain`, `materials`, `geometry`, and solver-independent simulation recipes remain free of PySide6, QML, QtPdf, filesystem, PyAEDT, FEMM, and SQLite imports.
- The UI must call existing M5a conversion, validation, fitting, lifecycle, replay, template, and repository services; do not reproduce their rules in QML or the controller.
- Approved revisions are immutable. Editing reviewed/approved content always produces a distinct `DRAFT`.
- Every revision remains visible. `latest_approved` may produce a suggestion badge only and never changes the selected revision or project.
- A project stores one exact approved revision snapshot and an explicit `bh_series_id` when the revision has multiple B-H series. Export never chooses the latest revision or an arbitrary series.
- M5c is optional and out of scope: no OCR, automatic tracing, GPL importer, material MCP tools, or explicit-formula record scaffolding.
- Global autosave/recovery and application-wide undo/redo remain M6 scope. M5b only protects dirty draft navigation with Save/Discard/Cancel.
- Live AEDT/FEMM tests are acceptance gates, not implementation prerequisites. Keep their markers and never claim them from fake or non-live evidence.
- Every behavior change follows RED → GREEN → refactor. Run the focused tests plus Ruff, strict mypy, architecture check, and `git diff --check` before each task commit.

## File Structure

| File | Responsibility |
|---|---|
| `src/inductor_designer/application/services/material_library.py` | Revision summaries and deterministic library queries |
| `src/inductor_designer/application/services/material_drafts.py` | Draft sessions, table/image edits, save/review/approve coordination |
| `src/inductor_designer/application/services/material_selection.py` | Explicit approved revision/B-H series pinning |
| `src/inductor_designer/ui/material_source.py` | PNG/JPEG decoding and QtPdf page rendering |
| `src/inductor_designer/ui/material_studio_controller.py` | PySide6 state/actions exposed to QML |
| `src/inductor_designer/ui/qml/MaterialStudioPage.qml` | Page composition and lifecycle actions |
| `src/inductor_designer/ui/qml/MaterialLibraryPane.qml` | Identity/revision browser and suggestion badge |
| `src/inductor_designer/ui/qml/MaterialSourceView.qml` | Source image, crop, calibration and point overlays |
| `src/inductor_designer/ui/qml/MaterialCurveEditor.qml` | Series/condition controls, point table and curve plot |
| `src/inductor_designer/ui/qml/MaterialValidationPane.qml` | Fit, residual and validation display |
| `schemas/project/v4.schema.json` | Exact revision snapshot plus nullable `bhSeriesId` |

## Task Ownership and Acceptance Map

The owner for every task is **Codex** unless explicitly reassigned in the task
handoff. Each task's **Files** block is its allowed-file list; expanding that
list requires recording the reason in this plan before editing.

| Task | Dependency | Independently reviewable acceptance criterion |
|---|---|---|
| 1 | M5a repository port and overlay | Every material identity and every revision is returned once in deterministic order, with an advisory-only latest-approved flag |
| 2 | Task 1 | Project schema v4 round-trips an exact revision snapshot and validates an explicit B-H series selection without repository lookup |
| 3 | Task 2 | Maxwell 2D/3D and FEMM plans use only the pinned B-H series and record it in their manifests |
| 4 | Tasks 1–2 | Table edits, clones, saves, review, and approval create immutable, replayable draft revisions without changing approved bases |
| 5 | Task 4 | Manual PNG/JPEG/PDF calibration and point extraction create replayable drafts while Qt remains outside pure application/domain code |
| 6 | Tasks 1–5 | The QML controller exposes all library, file, lifecycle, and project-selection operations with stable state on failures |
| 7 | Task 6 | Guided Studio navigates to one embedded Material Studio page that displays every revision and accessible validation state |
| 8 | Tasks 5–7 | A user can complete table and manual-image editing, lifecycle, explicit selection, and dirty-navigation workflows through QML |
| 9 | Tasks 1–8 | A non-live integration proof persists, reloads, replays, and exports the exact revision and B-H series through recording solver adapters |
| 10 | Task 9 | Documentation, non-live verification, manual UI evidence, acceptance split, merge, and remote-main confirmation are complete |

---

### Task 1: Material identity listing and revision summaries

**Files:**
- Modify: `src/inductor_designer/application/ports/material_repository.py`
- Modify: `src/inductor_designer/adapters/materials/overlay_repository.py`
- Modify: `tests/fakes/material_repository.py`
- Create: `src/inductor_designer/application/services/material_library.py`
- Modify: `tests/contract/test_material_repository_contract.py`
- Create: `tests/unit/application/test_material_library.py`

**Interfaces:**
- Consumes: existing `MaterialRepository.get`, `list_revisions`, `latest_approved`, and `validate_record`.
- Produces:

```python
class MaterialRepository(Protocol):
    def list_materials(self) -> tuple[MaterialRef, ...]: ...

@dataclass(frozen=True, slots=True)
class MaterialRevisionSummary:
    ref: MaterialRef
    revision_id: str
    status: MaterialStatus
    created_at: str
    reviewed_by: str | None
    approved_by: str | None
    series_count: int
    validation_errors: int
    validation_warnings: int
    is_latest_approved: bool

def list_material_revision_summaries(
    repository: MaterialRepository,
    ref: MaterialRef,
) -> tuple[MaterialRevisionSummary, ...]: ...
```

- [ ] **Step 1: Add failing repository contract tests**

Save two distinct identities and one sanitized alias. Assert identities are
returned once, ordered by `(manufacturer.casefold(), name.casefold(),
grade.casefold(), original values)`, and the alias collision is still rejected.

```python
assert repository.list_materials() == (
    MaterialRef("ACME", "Ferrite", "N87"),
    MaterialRef("Magnetics", "Kool Mu", "60"),
)
```

- [ ] **Step 2: Run the contract RED**

Run: `.venv/bin/python -m pytest tests/contract/test_material_repository_contract.py -q`

Expected: FAIL because `MaterialRepository` implementations do not expose
`list_materials`.

- [ ] **Step 3: Implement deterministic identity discovery**

The file adapter must read verified `record.json` files, reject two different
identities with the same sanitized/case-folded physical path, de-duplicate exact
identities, and sort deterministically. The in-memory fake uses the same sort key.

```python
def _material_sort_key(ref: MaterialRef) -> tuple[str, str, str, str, str, str]:
    return (
        ref.manufacturer.casefold(), ref.name.casefold(), ref.grade.casefold(),
        ref.manufacturer, ref.name, ref.grade,
    )

def list_materials(self) -> tuple[MaterialRef, ...]:
    return tuple(sorted(discovered_refs, key=_material_sort_key))
```

- [ ] **Step 4: Add revision-summary RED tests**

Create draft, reviewed and approved revisions with different timestamps and one
validation warning. Assert newest-first ordering, exact status/actor/count fields,
and exactly one `is_latest_approved=True`. Assert calling the service does not
change repository content or choose a revision.

- [ ] **Step 5: Implement the pure summary service**

Count `IssueSeverity.ERROR` and `IssueSeverity.WARNING` from `validate_record`.
Use parsed timestamps plus revision ID as the ordering key; do not sort ISO text
lexically because offsets may differ.

```python
latest = repository.latest_approved(ref)
summaries = tuple(_summary(repository.get(ref, revision), latest) for revision in repository.list_revisions(ref))
return tuple(sorted(summaries, key=_summary_time_key, reverse=True))
```

- [ ] **Step 6: Run Task 1 gates and commit**

```console
.venv/bin/python -m pytest tests/contract/test_material_repository_contract.py tests/unit/application/test_material_library.py -q
.venv/bin/python -m ruff check src/inductor_designer/application/ports/material_repository.py src/inductor_designer/adapters/materials/overlay_repository.py src/inductor_designer/application/services/material_library.py tests/fakes/material_repository.py tests/contract/test_material_repository_contract.py tests/unit/application/test_material_library.py
.venv/bin/python -m mypy src tools
.venv/bin/python tools/check_architecture.py
git diff --check
git add src/inductor_designer/application/ports/material_repository.py src/inductor_designer/adapters/materials/overlay_repository.py src/inductor_designer/application/services/material_library.py tests/fakes/material_repository.py tests/contract/test_material_repository_contract.py tests/unit/application/test_material_library.py
git commit -m "feat(materials): list material revisions for Studio"
```

---

### Task 2: Project schema v4 and explicit material pinning

**Files:**
- Create: `schemas/project/v4.schema.json`
- Modify: `src/inductor_designer/adapters/persistence/schema_repository.py`
- Modify: `src/inductor_designer/adapters/persistence/project_repository.py`
- Modify: `src/inductor_designer/domain/project.py`
- Create: `src/inductor_designer/application/services/material_selection.py`
- Modify: `tests/unit/adapters/persistence/test_schema_repository.py`
- Modify: `tests/unit/adapters/persistence/test_project_repository.py`
- Modify: `tests/unit/domain/test_project.py`
- Create: `tests/unit/application/test_material_selection.py`

**Interfaces:**
- Consumes: `MaterialRecord`, `MaterialStatus`, `SeriesKind`, and immutable
  `InductorProject`.
- Produces:

```python
@dataclass(frozen=True, slots=True)
class MaterialRevisionSelection:
    ref: MaterialRef
    revision_id: str
    snapshot: MaterialRecord
    bh_series_id: str | None = None

class MaterialSelectionError(ValueError):
    issues: tuple[str, ...]

def pin_material_revision(
    project: InductorProject,
    record: MaterialRecord,
    *,
    bh_series_id: str | None,
) -> InductorProject: ...
```

- [ ] **Step 1: Write schema/domain RED tests**

Assert v4 requires `bhSeriesId` as a string or null, v3 migrates by adding null,
and a v4 save/load round trip preserves an explicit ID. Domain tests require a
present ID to name a `BH_CURVE`, reject loss/unknown IDs, and permit null for
zero/one B-H series and migrated multi-series records so export can issue the
actionable block.

- [ ] **Step 2: Run schema/domain RED**

Run: `.venv/bin/python -m pytest tests/unit/domain/test_project.py tests/unit/adapters/persistence/test_schema_repository.py tests/unit/adapters/persistence/test_project_repository.py -q`

Expected: FAIL because schema v4 and `bh_series_id` do not exist.

- [ ] **Step 3: Implement schema v4 and migration**

Set `LATEST_PROJECT_SCHEMA_VERSION = 4`, add `_migrate_v3_to_v4`, emit
`schemaVersion: 4`, and serialize every material with `bhSeriesId`. Migration
must copy every material mapping and set only the missing field:

```python
def _migrate_v3_to_v4(document: dict[str, object]) -> dict[str, object]:
    migrated = dict(document)
    migrated["schemaVersion"] = 4
    migrated["materials"] = [
        {**item, "bhSeriesId": None}
        for item in document.get("materials", [])
    ]
    return migrated
```

Validate mapping types before spreading; malformed v3 documents must fail their
v3 schema before migration.

- [ ] **Step 4: Write explicit pinning RED tests**

Assert only approved records are pinnable; multiple B-H series require an ID;
zero/one series accept null; explicit IDs are persisted; pinning replaces the
same `MaterialRef` while preserving unrelated selections; and neither
`latest_approved` nor repository access occurs.

- [ ] **Step 5: Implement `pin_material_revision`**

Return `replace(project, materials=...)`. Reject blank/unknown/wrong-kind IDs and
validation-error records through `MaterialSelectionError.issues`. Snapshot the
exact record passed by the caller and never look up a newer record.

```python
selection = MaterialRevisionSelection(record.ref, record.revision_id, record, bh_series_id)
kept = tuple(item for item in project.materials if item.ref != record.ref)
return replace(project, materials=(*kept, selection))
```

- [ ] **Step 6: Run Task 2 gates and commit**

```console
.venv/bin/python -m pytest tests/unit/domain/test_project.py tests/unit/adapters/persistence/test_schema_repository.py tests/unit/adapters/persistence/test_project_repository.py tests/unit/application/test_material_selection.py -q
.venv/bin/python -m ruff check src/inductor_designer/domain/project.py src/inductor_designer/adapters/persistence src/inductor_designer/application/services/material_selection.py tests/unit/domain/test_project.py tests/unit/adapters/persistence tests/unit/application/test_material_selection.py
.venv/bin/python -m mypy src tools
.venv/bin/python tools/check_architecture.py
git diff --check
git add schemas/project/v4.schema.json src/inductor_designer/domain/project.py src/inductor_designer/adapters/persistence src/inductor_designer/application/services/material_selection.py tests/unit/domain/test_project.py tests/unit/adapters/persistence tests/unit/application/test_material_selection.py
git commit -m "feat(project): pin material B-H series in schema v4"
```

---

### Task 3: Selected B-H series in Maxwell and FEMM plans

**Files:**
- Modify: `src/inductor_designer/simulation/maxwell_plan.py`
- Modify: `src/inductor_designer/simulation/plan_builder.py`
- Modify: `src/inductor_designer/simulation/plan_builder2d.py`
- Modify: `src/inductor_designer/application/services/maxwell_export.py`
- Modify: `tests/unit/simulation/test_maxwell_plan.py`
- Modify: `tests/unit/simulation/test_plan_builder.py`
- Modify: `tests/unit/simulation/test_plan_builder2d.py`
- Modify: `tests/unit/application/test_maxwell_export.py`
- Modify: `tests/integration/test_material_reproducibility.py`

**Interfaces:**
- Consumes: Task 2 `MaterialRevisionSelection.bh_series_id`.
- Changes:

```python
@dataclass(frozen=True, slots=True)
class MaterialSpec:
    ...
    material_revision: str | None = None
    bh_series_id: str | None = None

def material_spec_from_material_record(
    core_record: CoreRecord,
    material: MaterialRecord,
    *,
    bh_series_id: str | None = None,
) -> MaterialSpec: ...
```

- [ ] **Step 1: Write selected-series RED tests**

Build an approved record with `bh-25c` and `bh-100c`. Assert selecting `bh-100c`
exports only its converted `(B, H)` pairs, records `bh_series_id`, and leaves the
record unchanged. Assert null blocks multiple series and unknown/loss IDs fail
with actionable `PlanBuildError` messages.

- [ ] **Step 2: Run solver-plan RED**

Run: `.venv/bin/python -m pytest tests/unit/simulation/test_maxwell_plan.py tests/unit/simulation/test_plan_builder.py tests/unit/simulation/test_plan_builder2d.py -q`

Expected: FAIL because the material helper cannot receive a selected ID.

- [ ] **Step 3: Thread the selected ID through both plan builders**

Add a keyword-only `material_bh_series_id: str | None = None` beside
`material_record` in both builders. Forward it only to
`material_spec_from_material_record`. Preserve grade fallback when no approved
record is selected.

```python
material = (
    core_material_spec(core_record)
    if material_record is None
    else material_spec_from_material_record(
        core_record, material_record, bh_series_id=material_bh_series_id
    )
)
```

- [ ] **Step 4: Write export/manifest RED tests**

Assert `_selected_material` returns the full `MaterialRevisionSelection`, all
three backends receive its record and ID, and AEDT/FEMM manifests include both:

```python
assert manifest["coreMaterial"]["materialRevision"] == revision_id
assert manifest["coreMaterial"]["bhSeriesId"] == "bh-100c"
```

- [ ] **Step 5: Implement export selection and manifest fields**

Rename the private helper to `_selected_material_selection`. Preserve the
multiple-revision block. Add `bhSeriesId` to `_core_material_block`; the FEMM
manifest path must use the same block rather than a separate selection rule.

```python
selection = _selected_material_selection(project, core_selection)
record = selection.snapshot if selection is not None else None
series_id = selection.bh_series_id if selection is not None else None
```

- [ ] **Step 6: Run Task 3 gates and commit**

```console
.venv/bin/python -m pytest tests/unit/simulation/test_maxwell_plan.py tests/unit/simulation/test_plan_builder.py tests/unit/simulation/test_plan_builder2d.py tests/unit/application/test_maxwell_export.py tests/integration/test_material_reproducibility.py -q
.venv/bin/python -m ruff check src/inductor_designer/simulation src/inductor_designer/application/services/maxwell_export.py tests/unit/simulation tests/unit/application/test_maxwell_export.py tests/integration/test_material_reproducibility.py
.venv/bin/python -m mypy src tools
.venv/bin/python tools/check_architecture.py
git diff --check
git add src/inductor_designer/simulation src/inductor_designer/application/services/maxwell_export.py tests/unit/simulation tests/unit/application/test_maxwell_export.py tests/integration/test_material_reproducibility.py
git commit -m "feat(simulation): export the selected B-H series"
```

---

### Task 4: Immutable Material Studio draft sessions

**Files:**
- Create: `src/inductor_designer/application/services/material_drafts.py`
- Create: `tests/unit/application/test_material_drafts.py`
- Modify: `src/inductor_designer/adapters/materials/__init__.py`

**Interfaces:**
- Consumes: `import_material_file_as_draft`, `new_draft_record`,
  `import_curve_csv`, `review_material`, `approve_material`, `from_canonical`,
  `MaterialRepository`, and `revision_id_for`.
- Produces:

```python
@dataclass(frozen=True, slots=True)
class MaterialDraftSession:
    record: MaterialRecord
    source_files: tuple[tuple[str, bytes], ...]
    base_revision_id: str | None

def session_from_upload(filename: str, data: bytes, *, created_at: str, notes: str = "") -> MaterialDraftSession: ...
def clone_revision_as_draft(repository: MaterialRepository, ref: MaterialRef, revision_id: str) -> MaterialDraftSession: ...
def replace_table_series(
    session: MaterialDraftSession,
    target_series_id: str,
    *,
    series_id: str,
    kind: SeriesKind,
    x_unit: str,
    y_unit: str,
    conditions: CurveConditions,
    points: tuple[CurvePoint, ...],
) -> MaterialDraftSession: ...
def save_material_session(repository: MaterialRepository, session: MaterialDraftSession) -> MaterialDraftSession: ...
def review_material_session(repository: MaterialRepository, session: MaterialDraftSession, reviewer: str) -> MaterialDraftSession: ...
def approve_material_session(repository: MaterialRepository, session: MaterialDraftSession, approver: str) -> MaterialDraftSession: ...
```

- [ ] **Step 1: Write upload/clone RED tests**

Assert upload wraps the existing imported draft and exact source files. Cloning
a reviewed/approved record clears lifecycle actors, records
`base_revision_id`, retains external source bytes, and remains unsavable in the
controller until an edit marks the session dirty. Repository immutability still
rejects any attempted overwrite of the approved base.

- [ ] **Step 2: Run upload/clone RED**

Run: `.venv/bin/python -m pytest tests/unit/application/test_material_drafts.py -q`

Expected: collection FAIL because `material_drafts` does not exist.

- [ ] **Step 3: Implement session construction**

Use `repository.source_bytes` for cloning. `replace` is permitted only to create
the transient, unsaved lifecycle-reset clone because it has no content changes;
every content edit must rebuild through `new_draft_record` so fit and revision
identity are recomputed. Require nonblank reviewer/approver strings before
calling the M5a lifecycle functions.

```python
stored = repository.get(ref, revision_id)
draft = replace(stored, status=MaterialStatus.DRAFT, reviewed_by=None, approved_by=None)
return MaterialDraftSession(draft, tuple(repository.source_bytes(ref, revision_id).items()), revision_id)
```

- [ ] **Step 4: Write table-edit and lifecycle RED tests**

Replace or rename one B-H or loss series using canonical edited points. Assert retained
units are reconstructed through `from_canonical`, deterministic
`series-{sanitized_id}.csv` bytes and SHA are replaced, the original upload stays
as supplemental provenance, fit/revision change, base is unchanged, and failed
save/review/approval leaves repository/session unchanged.

- [ ] **Step 5: Implement table replacement and lifecycle coordination**

Render retained-unit `x,y\n` text, pass it through `import_curve_csv`, replace
only `target_series_id` and its generated provenance/source file, and rebuild the
whole draft through `new_draft_record`. Reject a missing target or a replacement
ID that duplicates another series through `MaterialImportError`.

```python
raw_rows = tuple(
    (from_canonical(point.x, x_unit), from_canonical(point.y, y_unit))
    for point in points
)
source_text = "x,y\n" + "".join(f"{x!r},{y!r}\n" for x, y in raw_rows)
replacement = import_curve_csv(source_text, series_id=series_id, kind=kind,
                               x_unit=x_unit, y_unit=y_unit,
                               conditions=conditions, source=provenance)
```

- [ ] **Step 6: Run Task 4 gates and commit**

```console
.venv/bin/python -m pytest tests/unit/application/test_material_drafts.py tests/unit/application/test_material_import.py tests/unit/adapters/test_material_table_file.py -q
.venv/bin/python -m ruff check src/inductor_designer/application/services/material_drafts.py src/inductor_designer/adapters/materials/__init__.py tests/unit/application/test_material_drafts.py
.venv/bin/python -m mypy src tools
.venv/bin/python tools/check_architecture.py
git diff --check
git add src/inductor_designer/application/services/material_drafts.py src/inductor_designer/adapters/materials/__init__.py tests/unit/application/test_material_drafts.py
git commit -m "feat(materials): edit immutable Material Studio drafts"
```

---

### Task 5: Manual image and PDF digitization

**Files:**
- Modify: `src/inductor_designer/application/services/material_drafts.py`
- Create: `src/inductor_designer/ui/material_source.py`
- Modify: `tests/unit/application/test_material_drafts.py`
- Create: `tests/ui/test_material_source.py`
- Create: `tests/fixtures/materials/manual-bh.png`

**Interfaces:**
- Produces:

```python
@dataclass(frozen=True, slots=True)
class ImageSeriesInput:
    ref: MaterialRef
    source_filename: str
    source_data: bytes
    source_url: str
    source_page: int | None
    captured_at: str
    source_description: str
    series_id: str
    kind: SeriesKind
    x_unit: str
    y_unit: str
    conditions: CurveConditions
    extraction: ExtractionRecord
    created_at: str
    notes: str = ""

def image_draft_session(input_data: ImageSeriesInput) -> MaterialDraftSession: ...
def replace_image_extraction(session: MaterialDraftSession, series_id: str, extraction: ExtractionRecord) -> MaterialDraftSession: ...

@dataclass(frozen=True, slots=True)
class RenderedMaterialSource:
    png_data: bytes
    width_px: int
    height_px: int
    page_count: int
    page_index: int

def render_material_source(filename: str, data: bytes, *, page_index: int = 0) -> RenderedMaterialSource: ...
```

- [ ] **Step 1: Write image-draft RED tests**

Use a two-point linear extraction and a log-axis case. Assert extracted raw
coordinates are canonicalized with existing units, the `IMAGE` provenance hashes
the original bytes, the extraction is stored, replay matches, and moving a pixel
point creates a new draft revision while retaining source bytes.

- [ ] **Step 2: Run image-draft RED**

Run: `.venv/bin/python -m pytest tests/unit/application/test_material_drafts.py -q -k image`

Expected: FAIL because the image session functions do not exist.

- [ ] **Step 3: Implement pure image draft construction**

Call `extract_points`, then `canonicalize_points`; construct `PointSeries` with
the `ExtractionRecord` and the original image/PDF source filename. Rebuild edits
through `new_draft_record` so validation, fit and revision behavior remain shared.

```python
points = canonicalize_points(extract_points(input_data.extraction),
                             input_data.x_unit, input_data.y_unit)
series = PointSeries(input_data.series_id, input_data.kind,
                     input_data.x_unit, input_data.y_unit,
                     input_data.conditions, points,
                     input_data.source_filename, input_data.extraction)
```

- [ ] **Step 4: Write source-renderer RED tests**

Under `@pytest.mark.ui`, assert a synthetic, repository-owned PNG fixture and an
in-memory JPEG render to PNG bytes at original dimensions. Build a two-page PDF
inside the test with `QPdfWriter`; assert `page_count == 2` and the requested page
renders. Invalid/empty/out-of-range inputs raise `MaterialSourceError`, and no
OCR/text extraction API is called.

- [ ] **Step 5: Implement Qt image/PDF rendering**

Use `QImage.fromData` for raster sources and `QPdfDocument` for PDF. Keep the
`QBuffer` that owns PDF source bytes alive until synchronous rendering completes,
render the requested page to `QImage`, serialize through a separate `QBuffer` as
PNG, and return plain Python DTO fields. Reject unsupported suffixes before
decoding.

```python
image = QImage.fromData(data) if suffix != ".pdf" else _render_pdf_page(data, page_index)
if image.isNull():
    raise MaterialSourceError(f"Cannot decode material source: {filename}")
png_data = _image_to_png(image)
return RenderedMaterialSource(png_data, image.width(), image.height(), page_count, page_index)
```

- [ ] **Step 6: Run Task 5 gates and commit**

```console
QT_QPA_PLATFORM=offscreen QSG_RHI_BACKEND=software .venv/bin/python -m pytest tests/unit/application/test_material_drafts.py tests/ui/test_material_source.py -q
.venv/bin/python -m ruff check src/inductor_designer/application/services/material_drafts.py src/inductor_designer/ui/material_source.py tests/unit/application/test_material_drafts.py tests/ui/test_material_source.py
.venv/bin/python -m mypy src tools
.venv/bin/python tools/check_architecture.py
git diff --check
git add src/inductor_designer/application/services/material_drafts.py src/inductor_designer/ui/material_source.py tests/unit/application/test_material_drafts.py tests/ui/test_material_source.py tests/fixtures/materials/manual-bh.png
git commit -m "feat(materials): digitize image and PDF curves manually"
```

---

### Task 6: Material Studio controller

**Files:**
- Create: `src/inductor_designer/ui/material_studio_controller.py`
- Create: `tests/ui/test_material_studio_controller.py`
- Modify: `src/inductor_designer/ui/main.py`
- Modify: `src/inductor_designer/adapters/persistence/project_repository.py`
- Modify: `tests/unit/adapters/persistence/test_project_repository.py`

The persistence adapter/test were added to the Task 6 allowlist after review
identified that the controller's production callback cannot meet the approved
failure-atomic project-save contract while `ProjectRepository.save` writes
directly to the destination file.

**Interfaces:**
- Consumes: Tasks 1–5 services, existing template/export adapters, a loaded
  `InductorProject`, and project-save callback.
- Produces `MaterialStudioController(QObject)` with QML properties for
  `materials`, `revisions`, `selectedMaterial`, `selectedRevision`, `series`, `points`, `issues`,
  `fit`, `dirty`, `statusMessage`, `canSave`, `canReview`, `canApprove`, and
  `canUseInProject`.
- Produces slots:

```python
@Slot(str, str, str, result=bool)
def selectMaterial(self, manufacturer: str, name: str, grade: str) -> bool: ...
@Slot(str, result=bool)
def selectRevision(self, revision_id: str) -> bool: ...
@Slot(str, str)
def downloadTemplate(self, file_format: str, destination_url: str) -> None: ...
@Slot(str)
def importTable(self, source_url: str) -> None: ...
@Slot(str)
def exportSelectedWorkbook(self, destination_url: str) -> None: ...
@Slot(str)
def importEditedWorkbook(self, source_url: str) -> None: ...
@Slot(str, int)
def importSourceImage(self, source_url: str, page_index: int) -> None: ...
@Slot()
def saveDraft(self) -> None: ...
@Slot(str)
def reviewDraft(self, reviewer: str) -> None: ...
@Slot(str)
def approveRevision(self, approver: str) -> None: ...
@Slot(str)
def useInProject(self, bh_series_id: str) -> None: ...
```

- [ ] **Step 1: Write controller library/lifecycle RED tests**

Instantiate the controller with an in-memory repository and project callback.
Assert identity/revision refresh, latest-approved badge without selection,
selected record details, correct action flags, nonblank actor requirements,
successful save/review/approve refresh, and error messages without state loss.

- [ ] **Step 2: Run controller RED**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ui/test_material_studio_controller.py -q`

Expected: collection FAIL because the controller does not exist.

- [ ] **Step 3: Implement controller state and lifecycle slots**

Follow `GenerationController` property/signal style but keep Material Studio
operations synchronous and small. Catch only expected `ValueError`,
`MaterialImportError`, `MaterialLookupError`, `MaterialSelectionError`, and
`OSError`; report a stable message and leave state unchanged.

```python
def _run_action(self, action: Callable[[], None]) -> None:
    try:
        action()
    except (MaterialImportError, MaterialLookupError,
            MaterialSelectionError, OSError, ValueError) as error:
        self._set_status(str(error))
```

- [ ] **Step 4: Write file/project workflow RED tests**

Use `QTemporaryDir`/`tmp_path` URLs. Assert template and selected-revision
downloads write exact bytes only after a destination is supplied; uploads create
drafts; image/PDF page import exposes a PNG data URL and original dimensions;
multi-B-H project use requires an ID; pinning invokes the project callback once;
and cancelled/invalid paths write nothing.

- [ ] **Step 5: Implement file/project slots and `create_engine` wiring**

Convert only local `file:` URLs with `QUrl.toLocalFile`. Perform all source reads
before mutating controller state. Inject `materialStudioController` into QML;
when no project is loaded, expose a controller that can manage the material
library but has `canUseInProject == False`.

```python
path = Path(QUrl(source_url).toLocalFile())
data = path.read_bytes()
session = session_from_upload(path.name, data, created_at=self._now())
self._set_session(session)
```

- [ ] **Step 6: Run Task 6 gates and commit**

```console
QT_QPA_PLATFORM=offscreen QSG_RHI_BACKEND=software .venv/bin/python -m pytest tests/ui/test_material_studio_controller.py tests/ui/test_qml_smoke.py tests/unit/adapters/persistence/test_project_repository.py -q
.venv/bin/python -m ruff check src/inductor_designer/ui/material_studio_controller.py src/inductor_designer/ui/main.py src/inductor_designer/adapters/persistence/project_repository.py tests/ui/test_material_studio_controller.py tests/unit/adapters/persistence/test_project_repository.py
.venv/bin/python -m mypy src tools
.venv/bin/python tools/check_architecture.py
git diff --check
git add src/inductor_designer/ui/material_studio_controller.py src/inductor_designer/ui/main.py src/inductor_designer/adapters/persistence/project_repository.py tests/ui/test_material_studio_controller.py tests/unit/adapters/persistence/test_project_repository.py
git commit -m "feat(ui): expose Material Studio controller"
```

---

### Task 7: Guided Studio navigation and material library page

**Files:**
- Modify: `src/inductor_designer/ui/qml/Main.qml`
- Create: `src/inductor_designer/ui/qml/MaterialStudioPage.qml`
- Create: `src/inductor_designer/ui/qml/MaterialLibraryPane.qml`
- Create: `src/inductor_designer/ui/qml/MaterialValidationPane.qml`
- Modify: `tests/ui/test_qml_smoke.py`

**Interfaces:**
- Consumes: Task 6 controller properties/slots.
- Produces QML object names `guidedStepList`, `materialsStep`,
  `materialStudioPage`, `materialLibraryPane`, `revisionList`,
  `validationIssueList`, and `materialStatusText` for stable UI tests.

- [ ] **Step 1: Write QML shell RED tests**

Load QML offscreen with a recording controller. Find the object names, select
`Materials`, assert `MaterialStudioPage.visible`, and return to another step.
Assert no second window is created and the controller is not re-instantiated.

- [ ] **Step 2: Run QML shell RED**

Run: `QT_QPA_PLATFORM=offscreen QSG_RHI_BACKEND=software .venv/bin/python -m pytest tests/ui/test_qml_smoke.py -q`

Expected: FAIL because the named Guided Studio controls/components are absent.

- [ ] **Step 3: Implement navigation and page composition**

Replace static step labels with a keyboard-navigable `ListView` and
`StackLayout`. Keep Preview as the default non-Materials content. Compose the
Material page with library, import/export panels, main workspace,
validation, and lifecycle regions; every visible string uses `qsTr`.

```qml
ListView { id: guidedStepList; model: [qsTr("Core"), qsTr("Windings"), qsTr("Materials"), qsTr("Simulation"), qsTr("Review")] }
StackLayout {
    currentIndex: guidedStepList.currentIndex
    Item { objectName: "corePage" }
    Item { objectName: "windingsPage" }
    MaterialStudioPage { objectName: "materialStudioPage"; controller: materialStudioController }
    Item { objectName: "simulationPage" }
    Item { objectName: "reviewPage" }
}
```

- [ ] **Step 4: Add library/accessibility RED tests**

Feed three revisions and assert all appear with revision ID, textual status,
actors, timestamp, issue counts, and a non-color `Suggested latest approved`
label on only one entry. Verify accessible names, Tab focus order, and that
clicking the badge alone does not call `selectRevision`.

- [ ] **Step 5: Implement library and validation panes**

Use controller lists as read-only models. Selection occurs only through the
revision row action. Group validation entries by textual severity and expose fit
coefficients/residuals without rounding beyond their controller display values.

```qml
Button {
    text: qsTr("Select revision %1").arg(modelData.revisionId)
    Accessible.name: text
    onClicked: controller.selectRevision(modelData.revisionId)
}
```

- [ ] **Step 6: Run Task 7 gates and commit**

```console
QT_QPA_PLATFORM=offscreen QSG_RHI_BACKEND=software .venv/bin/python -m pytest tests/ui/test_qml_smoke.py tests/ui/test_material_studio_controller.py -q
.venv/bin/python -m ruff check tests/ui/test_qml_smoke.py
.venv/bin/python -m mypy src tools
.venv/bin/python tools/check_architecture.py
git diff --check
git add src/inductor_designer/ui/qml/Main.qml src/inductor_designer/ui/qml/MaterialStudioPage.qml src/inductor_designer/ui/qml/MaterialLibraryPane.qml src/inductor_designer/ui/qml/MaterialValidationPane.qml tests/ui/test_qml_smoke.py
git commit -m "feat(ui): add Material Studio library page"
```

---

### Task 8: Import/export, curve editor, and lifecycle UI

**Files:**
- Create: `src/inductor_designer/ui/qml/MaterialSourceView.qml`
- Create: `src/inductor_designer/ui/qml/MaterialCurveEditor.qml`
- Modify: `src/inductor_designer/ui/qml/MaterialStudioPage.qml`
- Modify: `src/inductor_designer/ui/qml/Main.qml`
- Modify: `src/inductor_designer/ui/material_studio_controller.py`
- Modify: `src/inductor_designer/application/services/material_drafts.py`
- Modify: `tests/ui/test_material_studio_controller.py`
- Modify: `tests/ui/test_qml_smoke.py`
- Create: `tests/ui/test_material_studio_workflow.py`
- Modify: `tests/unit/application/test_material_drafts.py`
- Modify: this plan to record the reviewed interface/allowlist clarification

`Main.qml` and its smoke test were added to the Task 8 allowlist because the
approved Save/Discard/Cancel rule must intercept the existing Guided Studio
step navigation. The controller interfaces below also make initial image-draft
creation and numeric point editing explicit instead of leaving those approved
workflows implicit in QML.

The pure draft service/test were added after implementation review identified
that changing image-series metadata through table replacement would silently
discard extraction semantics, while reconstructing a one-series image session
could discard sibling series. Task 8 therefore adds one focused immutable image
series replacement service.

The library-selection slots return `True` only after a successful controller
selection. Material Studio uses that result with the stable material tuple or
revision ID to resolve the highlighted row from a refreshed/reordered model;
failed selection restores the previously confirmed identity.

**Interfaces:**
- Adds controller slots for crop/calibration/point edits:

```python
@Slot(int, int, int, int)
def setCrop(self, left: int, top: int, width: int, height: int) -> None: ...
@Slot(str, float, float, float, float)
def setXAxis(self, scale: str, pixel_a: float, value_a: float, pixel_b: float, value_b: float) -> None: ...
@Slot(str, float, float, float, float)
def setYAxis(self, scale: str, pixel_a: float, value_a: float, pixel_b: float, value_b: float) -> None: ...
@Slot(float, float)
def addPixelPoint(self, x_px: float, y_px: float) -> None: ...
@Slot(int, float, float)
def movePixelPoint(self, index: int, x_px: float, y_px: float) -> None: ...
@Slot(int)
def deletePoint(self, index: int) -> None: ...
@Slot(str, str, str, str, float, float, float)
def setSeriesMetadata(self, series_id: str, kind: str, x_unit: str, y_unit: str, frequency_hz: float, temperature_c: float, dc_bias_a_per_m: float) -> None: ...
@Slot(str, str, str, str)
def createImageDraft(self, manufacturer: str, name: str, grade: str, source_description: str) -> None: ...
@Slot(str, int, float, float)
def setCanonicalPoint(self, series_id: str, index: int, x: float, y: float) -> None: ...

def replace_image_series(
    session: MaterialDraftSession,
    target_series_id: str,
    *,
    series_id: str,
    kind: SeriesKind,
    x_unit: str,
    y_unit: str,
    conditions: CurveConditions,
    extraction: ExtractionRecord,
) -> MaterialDraftSession: ...
```

QML must pass `Number.NaN` for each blank optional condition. The controller
converts a value to `None` only when `math.isnan(value)`; physical zero remains a
real condition value.

`createImageDraft` uses the currently loaded source bytes/page, current crop,
axis calibrations, pixel points, series metadata, and controller clock. Numeric
editing rebuilds the target through `replace_table_series`; for an image-backed
series this deliberately becomes a direct table edit while retaining the
original image/PDF as supplemental provenance, and the UI must state that
transformation rather than performing it silently.
`replace_image_series` replaces only the target image-backed series, retains
every sibling series plus all source provenance/bytes, supports a validated
series-ID rename, and rebuilds through `new_draft_record`.

- [ ] **Step 1: Write controller edit-coordinate RED tests**

Assert QML display coordinates are converted through current source scale and
offset to original pixels; zoom/resize changes do not alter stored points. Assert
linear/log calibration, add/move/delete, numeric point edits, metadata/unit
changes, validation refresh, dirty state, and Save/Discard/Cancel behavior.

- [ ] **Step 2: Run controller edit RED**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ui/test_material_studio_controller.py -q -k edit`

Expected: FAIL because edit slots/state do not exist.

- [ ] **Step 3: Implement edit slots through Task 4/5 services**

The controller builds immutable `CropRegion`, `AxisCalibration`, `PixelPoint`,
and `CurveConditions` values, then calls service replacements. It must not
calculate canonical physics in Qt code. Invalid intermediate calibration remains
editable and visible as a status error without overwriting the last valid draft.

```python
extraction = ExtractionRecord(self._crop, self._x_axis, self._y_axis,
                              tuple(self._pixel_points))
updated = replace_image_extraction(self._session, self._series_id, extraction)
self._set_session(updated, dirty=True)
```

- [ ] **Step 4: Write QML workflow RED tests**

Exercise with offscreen mouse/keyboard events: template download format choice,
table upload, revision export/reimport, image page selection, crop handles, two
axis anchors, point add/move/delete, series/condition controls, Save, Review,
Approve, explicit B-H selection, Use in Project, and dirty navigation dialog.
Assert action enablement matches the spec and all buttons have accessible names.

- [ ] **Step 5: Implement source view, curve editor and lifecycle controls**

`MaterialSourceView` uses an `Image` with overlay coordinates expressed in
original-pixel space via explicit scale/offset properties. `MaterialCurveEditor`
uses `Canvas` only for drawing; point/series state remains in the controller.
Use `FileDialog` destination/source URLs and a modal three-action discard dialog.

```qml
property real sourceScale: Math.min(width / sourceWidth, height / sourceHeight)
function originalX(displayX) { return (displayX - sourceOffsetX) / sourceScale }
function originalY(displayY) { return (displayY - sourceOffsetY) / sourceScale }
TapHandler { onTapped: controller.addPixelPoint(originalX(point.position.x), originalY(point.position.y)) }
```

- [ ] **Step 6: Run Task 8 gates and commit**

```console
QT_QPA_PLATFORM=offscreen QSG_RHI_BACKEND=software .venv/bin/python -m pytest tests/ui/test_material_studio_controller.py tests/ui/test_material_studio_workflow.py tests/ui/test_qml_smoke.py tests/unit/application/test_material_drafts.py -q
.venv/bin/python -m ruff check src/inductor_designer/ui/material_studio_controller.py src/inductor_designer/application/services/material_drafts.py tests/ui/test_material_studio_controller.py tests/ui/test_material_studio_workflow.py tests/ui/test_qml_smoke.py tests/unit/application/test_material_drafts.py
.venv/bin/python -m mypy src tools
.venv/bin/python tools/check_architecture.py
git diff --check
git add src/inductor_designer/ui/material_studio_controller.py src/inductor_designer/application/services/material_drafts.py src/inductor_designer/ui/qml/Main.qml src/inductor_designer/ui/qml/MaterialStudioPage.qml src/inductor_designer/ui/qml/MaterialSourceView.qml src/inductor_designer/ui/qml/MaterialCurveEditor.qml tests/ui/test_material_studio_controller.py tests/ui/test_material_studio_workflow.py tests/ui/test_qml_smoke.py tests/unit/application/test_material_drafts.py docs/superpowers/plans/2026-07-19-material-studio-ui.md
git commit -m "feat(ui): complete Material Studio editing workflow"
```

---

### Task 9: Non-live M5b exit proof

**Files:**
- Create: `tests/integration/test_material_studio_exit.py`
- Modify: `tests/fixtures/sample_geometry_project.inductor.json`

**Interfaces:**
- Consumes: all Tasks 1–8 public interfaces and existing recording Maxwell/FEMM
  fakes.
- Produces the automated M5b implementation exit evidence; no new production API.

- [ ] **Step 1: Write the end-to-end spreadsheet RED test**

Through `MaterialStudioController` and a real temporary
`FileOverlayMaterialRepository`: download/import XLSX, save/review/approve,
export/edit/reimport, prove base immutability and full revision visibility,
approve the edited revision, explicitly choose a B-H series, save/reload schema
v4, and generate recording-fake Maxwell 3D/FEMM manifests with exact revision and
series ID.

- [ ] **Step 2: Run spreadsheet exit RED**

Run: `QT_QPA_PLATFORM=offscreen QSG_RHI_BACKEND=software .venv/bin/python -m pytest tests/integration/test_material_studio_exit.py -q`

Expected: FAIL on the first incomplete controller/UI-to-service contract; fix the
owning Task 1–8 boundary without weakening the exit assertions.

- [ ] **Step 3: Add the manual-image replay flow**

Load `manual-bh.png`, set crop and axes, click points, save/review/approve, reload
the overlay, and require `reproduce_record(...).matches`. Assert source SHA/page,
pixel extraction, canonical points and revision are unchanged after reload.

- [ ] **Step 4: Add negative exit cases**

Assert latest-approved suggestion never pins, reviewed/approved edits create a
new draft, multiple B-H series without selection block project use/export, and a
failed project save leaves the previous project file byte-identical.

- [ ] **Step 5: Run Task 9 gates and commit**

```console
QT_QPA_PLATFORM=offscreen QSG_RHI_BACKEND=software .venv/bin/python -m pytest tests/integration/test_material_studio_exit.py tests/integration/test_material_table_upload.py tests/integration/test_material_reproducibility.py -q
.venv/bin/python -m ruff check tests/integration/test_material_studio_exit.py
.venv/bin/python -m mypy src tools
.venv/bin/python tools/check_architecture.py
git diff --check
git add tests/integration/test_material_studio_exit.py tests/fixtures/sample_geometry_project.inductor.json
git commit -m "test: prove Material Studio workflow end to end"
```

---

### Task 10: Documentation, whole review, gates, and handoff

**Files:**
- Modify: `docs/development/material-records.md`
- Modify: `docs/development/ROADMAP.md`
- Modify: `docs/superpowers/plans/README.md`
- Modify: `README.md`
- Modify: this plan's checkboxes/status during execution

**Interfaces:** No new production interfaces.

- [ ] **Step 1: Document the exact UI workflow**

Document template/current-revision downloads, table/image/PDF import, crop and
axis calibration, manual point editing, conditions, validation/fit display,
draft/review/approve, all-revision browser, latest-approved suggestion semantics,
explicit B-H selection, schema v4 migration, dirty-discard behavior, and the M5c
optional decision. Keep M5a live gates visibly pending until real evidence exists.

- [ ] **Step 2: Request whole-change review**

Review from the M5b base commit through HEAD against the approved spec,
architecture rules, provenance/replay integrity, immutable approval, project
schema migration, explicit selection, QML accessibility, error paths, and M5c
exclusion. Fix every Critical or Important finding with a new RED test and
focused commit, then re-review.

- [ ] **Step 3: Run fresh complete verification**

```console
.venv/bin/python -m pytest tests -q -m "not aedt and not femm" --cov=inductor_designer --cov-report=term-missing
QT_QPA_PLATFORM=offscreen QSG_RHI_BACKEND=software .venv/bin/python -m pytest tests -q -m ui
.venv/bin/python -m ruff check .
.venv/bin/python -m mypy src tools
.venv/bin/python tools/check_architecture.py
git diff --check "$(git merge-base HEAD origin/main)"..HEAD
git status --short --branch
```

Expected: zero failures; coverage at least 80%; all static gates exit 0; no
tracked `.superpowers`, generated renders, temporary PDFs, overlay data, or
`uv.lock`; only the three pre-existing `.DS_Store` files may remain untracked.

- [ ] **Step 4: Perform manual UI acceptance without solvers**

On Windows, open Guided Studio and record evidence that keyboard navigation,
focus, scaling, PNG/JPEG/PDF page rendering, template download, workbook edit and
reimport, all-revision visibility, lifecycle actions, and explicit B-H selection
work. This check needs Excel or a compatible workbook editor but not AEDT/FEMM.

- [ ] **Step 5: Record acceptance split**

Mark M5b **implementation complete** only when Steps 1–4 pass. Keep M5a/M5b
**formal acceptance pending** until the real approved material produces `MATCH`
and the exact pinned revision is verified live in AEDT and FEMM. Record whether
M5c is unnecessary, deferred, or separately approved; do not create an M5c plan
by default.

- [ ] **Step 6: Commit documentation and handoff**

```console
git add docs/development/material-records.md docs/development/ROADMAP.md docs/superpowers/plans/README.md README.md docs/superpowers/plans/2026-07-19-material-studio-ui.md
git commit -m "docs: record Material Studio implementation handoff"
```

- [ ] **Step 7: Merge, verify, push, and confirm remote**

Fetch `origin/main`, integrate the reviewed feature branch according to the
finishing workflow, rerun the non-live suite plus static gates on merged `main`,
push `main`, and confirm `git ls-remote --heads origin main` equals local HEAD.
Do not delete a host-managed worktree.

---

## Execution Order and Review Gates

Execute strictly in order: **1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10**.
Tasks 1–5 establish pure/adapter contracts before Qt coordination. Tasks 6–8
build the controller and UI. Task 9 is the automated exit proof. Task 10 closes
documentation, review, validation, and integration.

Each task requires:

1. an owner, allowed-file list, dependency commit, acceptance criteria, and exact
   verification commands;
2. a fresh implementer context when subagent-driven execution is used;
3. spec-compliance review followed by code-quality review;
4. fixes for all Critical/Important findings before the next task; and
5. a small conventional commit with no unrelated refactor.
