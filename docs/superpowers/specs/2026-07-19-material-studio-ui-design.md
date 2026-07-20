# Milestone 5b: Material Studio UI Design

> Superseded on 2026-07-20 by the [spreadsheet-only Material Studio design](2026-07-20-material-studio-spreadsheet-only-design.md). This file is retained as historical decision context; its image/PDF workflow is no longer implemented.

- Status: Approved 2026-07-19
- Date: 2026-07-19
- Owner: Codex
- Target platform: Windows desktop application
- Depends on: Milestone 5a material records pipeline and material import templates

## 1. Goal

Deliver the Guided Studio `Materials` step that lets a reviewer create, inspect,
edit, validate, review, approve, select, and export traceable magnetic-material
revisions without using Python directly. The UI consumes the completed M5a
application services and repositories; it does not duplicate material physics,
unit conversion, revision hashing, replay, or solver export logic.

M5b is usable without live AEDT or FEMM. A real-record reproduction check should
run before or early in M5b, and live solver handoff remains a release acceptance
gate rather than an implementation entry condition.

## 2. Scope split

### 2.1 Required M5b scope

- Integrate a real `Materials` page into the existing Guided Studio window.
- List material identities and every stored revision, including draft, reviewed,
  and approved revisions.
- Show the latest approved revision as a suggestion only; never silently select
  or pin it.
- Download the packaged CSV and XLSX templates.
- Import CSV/XLSX uploads as new draft revisions.
- Export the selected revision to an editable XLSX workbook.
- Reimport an edited workbook as a new draft without mutating its base revision.
- Import PNG, JPEG, or one selected PDF page as a source for manual curve
  digitization.
- Crop the displayed source, calibrate linear or logarithmic axes, add/move/delete
  points, edit canonical values, and attach curve conditions.
- Display source points, current points, supported fits, fit residuals, and
  validation issues together.
- Save drafts and perform explicit review and approval transitions.
- Require explicit B-H series selection when a pinned revision contains more
  than one B-H series.
- Persist the exact approved revision and selected B-H series in the project.
- Preserve existing M5a provenance, replay, validation, and immutable approval
  guarantees.

### 2.2 Optional later M5c scope

M5c is not required when spreadsheet and manual digitization workflows are
sufficient. It is planned only after M5b user acceptance demonstrates a real
need. Its candidate scope is:

- OCR proposals;
- automatic image curve tracing;
- the optional attributed GPL `materialdatabase` importer;
- material inspection/review/approval tools over MCP; and
- explicit-formula material representations not expressible as the supported
  tables or fitted coefficients.

No M5c component is bundled, scaffolded, or made an M5b dependency.

### 2.3 Other deferred work

- Global Guided Studio autosave/recovery and application-wide undo/redo remain
  Milestone 6 work.
- M5b keeps a local dirty flag and requires confirmation before discarding an
  unsaved draft.
- Live AEDT/FEMM validation remains the acceptance work documented under M5a.
- Cloud storage, collaborative review, and remote material databases remain out
  of scope.

## 3. Chosen UI approach

Material Studio is a page inside the existing Guided Studio window, implemented
with QML and a thin PySide6 controller. A separate application window was
rejected because it duplicates project context and navigation. An embedded web
editor was rejected because it adds a second UI stack and complicates Windows
packaging.

The existing persistent preview remains available outside the material editing
workspace. Selecting `Materials` changes the main content to the Material Studio
page; returning to `Core`, `Windings`, `Simulation`, or `Review` restores the
corresponding Guided Studio content.

## 4. Architecture and boundaries

Dependencies continue to point inward:

```text
QML Material Studio components
        |
MaterialStudioController (PySide6 UI adapter)
        |
Material Studio application services and repository port
        |
domain / materials / project model
        ^
filesystem overlay, XLSX, image/PDF and project persistence adapters
```

The following rules are mandatory:

- QML and PySide6 types do not enter `domain`, `materials`, `simulation`, or
  application-service interfaces.
- Filesystem paths, file dialogs, `QImage`, and `QPdfDocument` remain UI/adapter
  concerns.
- Material validation, fitting, canonicalization, state transitions, revision
  hashing, and replay continue to use the existing M5a functions.
- The controller coordinates use cases and exposes display DTOs; it does not
  implement material physics.
- Approved records remain immutable. Any edit of a reviewed or approved record
  starts a new draft.
- Project export consumes the stored snapshot and explicit series selection; it
  never queries the overlay for a newer revision.

## 5. Application services

### 5.1 Material library queries

The repository port gains a deterministic identity listing operation:

```python
class MaterialRepository(Protocol):
    def list_materials(self) -> tuple[MaterialRef, ...]: ...
```

The filesystem adapter discovers record paths, verifies stored identities, rejects
sanitized path aliases, and returns identities sorted by manufacturer, name, and
grade using case-insensitive keys with original values as deterministic tie
breakers.

The new pure application service exposes display-neutral summaries:

```python
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

All revisions are returned newest first. `is_latest_approved` is visual guidance
only and has no selection side effect.

### 5.2 Draft sessions

A Material Studio draft session is an application DTO containing a transient or
persisted draft record plus the exact source bytes required by the overlay:

```python
@dataclass(frozen=True, slots=True)
class MaterialDraftSession:
    record: MaterialRecord
    source_files: tuple[tuple[str, bytes], ...]
    base_revision_id: str | None
```

Creation paths are:

- CSV/XLSX: reuse `import_material_file_as_draft`;
- editable selected revision: reuse `export_material_record_xlsx`, then
  `import_material_file_as_draft` after the user edits the workbook;
- image/PDF: build `SourceProvenance`, `ExtractionRecord`, and `PointSeries` from
  calibrated user points, then reuse `new_draft_record`; and
- existing reviewed/approved revision: copy its sources and curve definitions
  into a transient draft with blank lifecycle identities and a recomputed revision
  after the first edit. An unchanged clone cannot be saved over its approved base.

Saving calls `MaterialRepository.save` with the exact source mapping. Review and
approval call the existing `review_material` and `approve_material` services and
save the returned record. A failed transition leaves the stored and in-memory
record unchanged.

### 5.3 Series editing

Series editing is implemented as pure replacement functions over immutable
records. Operations include adding, moving, replacing, and deleting points;
changing units and conditions; and adding/removing a series. Every edit:

1. retains the original external upload as supplemental provenance;
2. regenerates the deterministic per-series CSV and its hash for direct table
   edits, while image edits retain the image/PDF source and update the extraction;
3. canonicalizes and rounds through the existing import/canonicalization path;
4. recomputes a supported Steinmetz fit when the loss data is sufficient;
5. clears reviewer and approver identities by producing a draft; and
6. returns current validation issues without implicitly saving.

Image point edits also update the `ExtractionRecord.pixel_points`. Direct table
edits have no extraction record and remain linked to their generated CSV source.

## 6. Image and PDF digitization

The UI accepts `.png`, `.jpg`, `.jpeg`, and `.pdf` files. PDF support uses
PySide6 QtPdf from the existing UI dependency; the user selects one page, which
is rendered for display while the original PDF bytes remain the provenance
source. No PDF text extraction or OCR occurs.

The workflow is explicit:

1. select the source file and, for PDF, a page;
2. set or adjust a rectangular crop;
3. place two calibration points and values on each axis;
4. select linear or logarithmic scaling and retained units;
5. add curve points by clicking, then move or delete them;
6. edit point values numerically when needed;
7. set series kind, identifier, frequency, temperature, and DC bias; and
8. create or update the draft and inspect validation/fitting results.

Display coordinates are converted to original rendered-image coordinates before
constructing `CropRegion`, `AxisCalibration`, and `PixelPoint`. Zoom, fit-to-view,
high-DPI scaling, and window resizing must not change stored pixel coordinates.

Automatic tracing and OCR are deliberately absent. The page describes point
extraction as manual so the UI never implies that the source curve was detected
automatically.

## 7. Material Studio page

The page has five stable regions:

1. **Library and revisions** — searchable material identities; all revisions;
   status, timestamp, reviewer/approver, and latest-approved suggestion badge.
2. **Import and export** — template download, CSV/XLSX upload, image/PDF import,
   selected-revision XLSX export, and edited-workbook reimport.
3. **Source and curve workspace** — source image, crop/calibration overlays,
   editable points, curve plot, unit/condition controls, and series selector.
4. **Fit and validation** — supported coefficients, residual metrics, and grouped
   Info/Warning/Error issues with actionable text.
5. **Lifecycle and project selection** — Save Draft, Review, Approve, and Use in
   Project actions; reviewer/approver identity fields; explicit B-H series choice.

Action rules:

- `Save Draft` is enabled only for a valid material identity with source bytes.
- `Review` is enabled only for a saved draft and requires a nonblank reviewer.
- `Approve` is enabled only for a saved reviewed revision and requires a nonblank
  approver.
- Validation errors disable Review and Approve. Warnings remain visible and do
  not block the lifecycle service.
- `Use in Project` is enabled only for approved revisions.
- Multiple B-H series require an explicit series choice before project selection.
- The latest-approved suggestion never changes the active revision or project.
- Navigating away from dirty edits requires Save, Discard, or Cancel.

All visible strings use `qsTr`. Keyboard navigation, focus indication, accessible
names, and non-color-only status cues are required.

## 8. Revision and condition selection

The revision browser always shows every stored revision for the selected identity.
Sorting is newest-first with revision ID as the deterministic tie breaker. Filters
may hide statuses temporarily but cannot delete or rewrite revisions.

When a selected approved revision contains:

- no B-H series, the scalar permeability path remains available;
- one B-H series, the UI displays it and persists its ID when the user selects the
  material for the project; or
- multiple B-H series, the UI requires the user to choose one by its series ID and
  displayed temperature/DC-bias conditions.

Loss-table selection is not added because the approved record stores one
record-level Steinmetz fit derived from its loss series. The UI displays which
loss series contribute to that fit.

## 9. Project schema v4

Project schema v4 extends the exact material selection with an optional explicit
B-H series identifier:

```json
{
  "ref": {"manufacturer": "...", "name": "...", "grade": "..."},
  "revisionId": "0123456789ab",
  "bhSeriesId": "bh-25c",
  "snapshot": {}
}
```

The domain type becomes:

```python
@dataclass(frozen=True, slots=True)
class MaterialRevisionSelection:
    ref: MaterialRef
    revision_id: str
    snapshot: MaterialRecord
    bh_series_id: str | None = None
```

If `bh_series_id` is present, it must name a B-H series in the snapshot. Project
schema v3 migrates to v4 by adding `bhSeriesId: null`; old projects containing
zero or one B-H series retain their previous behavior. Export blocks an old or
manually authored selection with multiple B-H series and no explicit ID.

The selection service replaces the existing selection for the same `MaterialRef`
instead of appending a duplicate. It snapshots the approved record and chosen
series into the project. It never resolves or persists `latest_approved` without
an explicit user action.

Maxwell 2D, Maxwell 3D, and FEMM material planning use only the selected B-H
series. The manifest records both `materialRevision` and `bhSeriesId`.

## 10. Controller and QML integration

`MaterialStudioController` is a `QObject` in `ui`. It receives a
`MaterialRepository`, the loaded project, and callbacks for project persistence.
It exposes immutable list/map values suitable for QML and slots for the actions
defined above. It emits focused change signals rather than reloading the QML
engine.

The controller translates known application errors into stable user-facing
messages and retains the technical exception for logs. It never catches
`BaseException`, never reports a failed save as successful, and never modifies a
project until repository persistence and selection validation succeed.

`create_engine` receives the controller as a new context property. The existing
generation and preview controllers remain independent.

## 11. Error handling and safety

- Unsupported files, malformed workbooks, formulas, missing metadata, invalid
  units, and inconsistent series surface the existing row/sheet/cell diagnostics.
- Image/PDF load failures identify the file and selected page without exposing
  unrelated paths.
- Source files are read before draft construction; partial reads do not create a
  record.
- Repository save remains atomic and approved revisions remain immutable.
- Export writes only after the user chooses a destination; cancellation writes
  nothing.
- Reimport never overwrites the selected base revision.
- Review and approval failures leave the previous revision selected and stored.
- Project schema migration is deterministic and never chooses a B-H series.
- The UI shows source URL, page, capture time, description, hashes, and lifecycle
  identities so approval is traceable.

## 12. Testing strategy

### 12.1 Pure and adapter tests

- Repository contract tests cover `list_materials`, ordering, path aliases, and
  corrupted records.
- Application tests cover summaries, latest-approved suggestion without
  selection, draft cloning, point editing, fit recomputation, validation, and
  lifecycle failures.
- Project schema tests cover v3-to-v4 migration, serialization, explicit series
  validation, and deterministic round trips.
- Maxwell/FEMM plan tests prove that only the chosen B-H series is exported and
  that manifests contain the revision and series ID.
- Image/PDF adapter tests cover page rendering, coordinate transforms, crop and
  axis calibration, zoom independence, and file errors without OCR.

### 12.2 Controller and UI tests

- Controller tests use a temporary overlay and verify enabled actions, dirty
  protection, list refreshes, error messages, review/approval identities, and
  explicit project selection.
- Offscreen QML tests load every Material Studio component, exercise keyboard
  focus, and verify translated action labels and non-color status text.
- Interaction tests cover template download, CSV/XLSX import, selected-revision
  export, edited-workbook reimport, image clicks, multi-series selection, and
  discard confirmation.

### 12.3 End-to-end exit proof

One non-live integration test performs this sequence through the controller and
real filesystem adapters:

1. download and import the packaged XLSX template;
2. save, review, and approve the resulting revision;
3. export it, edit a point, and reimport it as a distinct draft;
4. verify the approved base is unchanged and every revision remains visible;
5. approve the edited revision;
6. explicitly select one B-H series for a project;
7. save and reload schema v4; and
8. generate recording-fake Maxwell 3D and FEMM manifests containing the exact
   revision and B-H series ID.

A second UI integration test digitizes a synthetic image manually and proves
that replay reproduces the stored points from the original image bytes and
extraction record.

## 13. Completion and acceptance criteria

M5b implementation is complete when:

- the Material Studio page supports every required M5b workflow without Python;
- all stored revisions are inspectable and approved revisions are immutable;
- templates and selected revisions download successfully;
- every upload/edit produces a draft rather than overwriting its base;
- image/PDF manual digitization is replayable and traceable;
- validation, fit and residual information are visible before review/approval;
- reviewer and approver actions are explicit and persisted;
- the project records the exact approved revision and B-H series ID;
- multiple B-H series cannot reach export without explicit selection;
- the automated exit proof, UI tests, static gates, and architecture checks pass;
  and
- any uncompleted M5a real-record or live-solver checks remain explicitly
  recorded as blockers rather than being reported as passed.

M5c is not an M5b acceptance criterion.

M5b implementation may be declared complete with the automated and UI evidence
above. Formal acceptance of M5a and M5b, and any claim of validated live solver
handoff, additionally require the real-record reproduction and AEDT/FEMM checks
listed in the M5a plan.

## 14. Documentation and handoff

The implementation updates the material procedure, roadmap, plan index, README,
project schema documentation, and UI instructions. The handoff records:

- exact automated test and coverage results;
- the selected-revision and multi-condition behavior;
- the manual image/PDF digitization workflow;
- the unchanged M5a live-validation blockers;
- any accessibility or Windows-specific manual checks; and
- an explicit decision on whether the optional M5c is needed after spreadsheet
  and manual workflow acceptance.
