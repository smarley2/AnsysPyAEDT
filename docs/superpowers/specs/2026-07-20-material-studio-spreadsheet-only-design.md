# Material Studio Spreadsheet-Only Design

- Status: Approved 2026-07-20
- Date: 2026-07-20
- Owner: Codex
- Supersedes: image/PDF ingestion portions of `2026-07-19-material-studio-ui-design.md`
- Depends on: Milestone 5a material records pipeline and CSV/XLSX import templates

## 1. Decision

Material Studio accepts material data only through CSV or XLSX spreadsheets.
The application does not import PNG, JPEG, or PDF material sources, does not
perform OCR, and does not create curve points from an image.

Because no user materials have been imported yet, the obsolete image/PDF
material workflow and its supporting creation/editing code will be removed
rather than retained behind a compatibility path.

## 2. Scope

The Materials page continues to support:

- CSV and XLSX template download;
- CSV/XLSX upload as a new draft revision;
- populated XLSX export and edited-workbook reimport;
- material identity and revision selection;
- table-series metadata and numeric point editing;
- validation, fitting, draft/reviewed/approved lifecycle transitions;
- explicit approved B-H series selection for project use; and
- visual plotting of the selected revision's active B-H or loss series.

The following are removed:

- image and PDF file dialogs and source rendering;
- OCR or any image-processing extraction path;
- crop regions, pixel coordinates, axis calibration, and pixel-point editing;
- image-backed draft creation and image-backed series creation;
- source-image overlays and the `MaterialSourceView` component; and
- extraction metadata from the material record model.

## 3. Material selection and plot behavior

The user selects a material identity, then explicitly selects one of its
stored revisions. The UI never silently chooses the latest approved revision.
After a revision is selected, the series selector lists every B-H and loss
series in that record. Selecting a series updates the plot and its metadata.

The plot reads the canonical points already present in the selected
`MaterialRecord`; it does not reread or transform images. It displays:

- the series identifier and kind;
- X and Y units;
- frequency, temperature, and DC-bias conditions when present;
- a line joining the points and visible point markers;
- labeled X/Y axes with the selected units; and
- an empty-state message when the selected revision has no plotted series.

The numeric point table remains available for table-backed draft edits. A
selected reviewed or approved revision becomes a new draft through the existing
immutable replacement service before a point is changed.

## 4. Data and architecture

`SourceKind` is limited to `CSV` and `SPREADSHEET`. `PointSeries` stores
canonical `CurvePoint` values and its table source filename; it no longer stores
an extraction record. Material import, validation, replay, and repository
verification operate only on CSV/XLSX source bytes and generated per-series
CSV files.

The UI controller remains a thin adapter. It exposes table/revision/series
state and delegates import, canonicalization, validation, fitting, persistence,
and lifecycle transitions to the existing application services. QML owns only
layout and plot rendering.

## 5. Error handling

- Any non-CSV/XLSX upload is rejected before draft creation.
- Malformed rows, unsupported units, inconsistent series metadata, and physical
  validation errors use the existing import/validation diagnostics.
- A failed import, point edit, save, review, approval, or project selection
  leaves the previous selected state unchanged.
- Plotting never blocks lifecycle actions and never changes material data.

## 6. Testing and acceptance

Automated coverage must prove:

- image/PDF imports and extraction APIs are absent from the Material Studio
  controller and QML tree;
- CSV/XLSX import, export, reimport, lifecycle, and explicit project selection
  still work;
- selected material/revision/series state reaches the plot;
- plot labels show the active units and conditions and markers are drawn for
  canonical points;
- numeric edits update the table plot without image conversion messages; and
- responsive layouts keep the library, plot, validation, and lifecycle regions
  visible at compact, 2K, and 4K widths.

The complete non-solver test suite, UI suite, Ruff, strict mypy, architecture
check, and `git diff --check` are required before commit and push.
