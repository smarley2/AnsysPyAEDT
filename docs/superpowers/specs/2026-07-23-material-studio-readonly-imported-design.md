# Material Studio Read-Only Imported Materials Design

**Status:** Approved 2026-07-23
**Date:** 2026-07-23

## 1. Decision

Material Studio is an Excel/CSV-backed material library and visualization page.
After a file passes import validation, the application stores the normalized
material data and exposes it as `Imported`. The Materials page does not edit
points, series metadata, or lifecycle fields. A changed material must arrive
through a replacement spreadsheet.

Existing approved material records remain readable and usable. The old draft,
review, and approve actions are removed from the Material Studio UI. Imported
records are usable by simulation after validation; project selection remains an
explicit action because the project must pin both a material revision and, when
needed, a B-H series.

## 2. Scope

### In scope

- read-only material browsing with automatic newest-revision loading;
- CSV/XLSX import with immediate persistence as an `Imported` revision;
- replacement of the selected material from a new CSV/XLSX file;
- deletion of a material with confirmation and project-reference protection;
- read-only series selection and source inspection;
- generated XLSX download of the selected material for offline editing;
- curve preview with numeric axis ticks and independent linear/log X and Y
  controls;
- explicit `Select for simulation` behavior when a project is loaded;
- solver-compatible loss-origin normalization and reproducible storage.

### Out of scope

- editing individual points in QML;
- adding/removing series in QML;
- editing series ID, units, temperature, frequency, or DC-bias metadata in QML;
- manual lifecycle identities or approval buttons;
- automatic digitization from PDF/image sources;
- arbitrary formula evaluation in spreadsheets.

## 3. Material lifecycle and persistence

### Imported status

Add `MaterialStatus.IMPORTED`. A valid import creates a persisted revision with
status `imported`, no reviewer or approver, a content-addressed revision ID,
the original uploaded file as provenance, and generated per-series CSV sources
containing the normalized canonical points. Validation errors block persistence;
warnings remain visible.

Simulation material selection accepts `imported` and legacy `approved` records.
The simulation plan still validates the selected record before export. Reviewed
records remain readable for compatibility but are not exposed as an editable
lifecycle workflow.

### Replace selected material

`Replace selected material` opens a CSV/XLSX file picker. The imported material
identity must match the selected `manufacturer`, `material_name`, and `grade`.
The replacement is validated and persisted atomically before the previous
current revision is removed. A revision pinned by the active project is kept so
the project snapshot remains traceable; otherwise the previous current imported
revision is removed. The new revision becomes selected after success.

### Delete selected material

`Delete selected material` requires confirmation. Deletion removes the selected
material's stored revisions and sources unless an active project pins one of
them; in that case deletion is blocked with an actionable message. The action
never deletes the user's original workbook outside the application overlay.

## 4. Material Studio UI

### Library and import actions

The library is selectable by material identity. Selecting a material
automatically loads its newest stored revision; revision lifecycle metadata and
manual revision selection are not shown.

The import area contains:

- `XLSX template` (and the existing CSV template, if retained);
- `Import CSV or XLSX` for a new material;
- `Download selected material XLSX` for an editable workbook containing all
  stored curves and metadata;
- `Replace selected material`;
- `Delete selected material`.

The following controls are removed from the page:

- `Save draft`, `Review`, and `Approve`;
- Series Management;
- Series Metadata fields and `Apply series`;
- direct point fields, `Apply`, and `Delete` point buttons;
- imported/current point dump labels;
- reviewer, approver, revision-list, fit, and validation panes;
- edited-workbook reimport controls that imply in-UI editing.

### Simulation selection

When a project is loaded, show one compact `Select for simulation` action. If
the selected revision contains multiple B-H series, the user must select one
explicitly. If no project is loaded, this action is hidden or disabled with a
clear explanation. This action only pins the selected immutable snapshot; it
does not edit the material.

### Curve preview

The preview contains:

- a read-only series selector;
- curve kind, conditions, source filename, and units;
- numeric X/Y axis labels and tick values;
- `Log X` and `Log Y` controls, independently selectable;
- the curve line and point markers.

The stored point table is not displayed as a long text box or editable list.

Logarithmic rendering uses only positive values. A stored zero or negative point
is never deleted or changed; it is omitted only from the log rendering and a
visible note reports that non-positive points are not shown on that axis. The
linear view always shows all valid points.

## 5. Solver-compatible loss origin

Maxwell's normal B-H curve starts at `(0,0)`, and Maxwell's B-P core-loss data
must also start at the origin. The current B-H origin rule remains. For every
loss series:

1. If the first point is exactly `(0,0)`, keep it.
2. If every existing B value is positive and no origin exists, prepend a
   canonical `(0,0)` point before storage and report the normalization.
3. If B equals zero with a nonzero loss, or the data cannot be ordered into a
   valid increasing-B curve, reject the series with an actionable error.
4. All non-origin loss points must have positive loss density and increasing B.

The original uploaded workbook remains byte-for-byte provenance. The generated
canonical per-series CSV, stored record, revision ID, and simulation snapshot
contain the inserted origin. The generated source description records that the
Maxwell-required origin was inserted during import.

The `(0,0)` loss point is excluded from the Steinmetz fit because the fit uses
logarithms and zero has no finite logarithm. All positive loss samples remain
unchanged in the fit.

FEMM receives only the selected B-H curve in the current adapter path. It does
not consume the loss table. The shared B-H origin rule is retained because it
is required by Maxwell and accepted by FEMM.

References:

- [Maxwell nonlinear B-H curves](https://ansyshelp.ansys.com/public/Views/Secured/Electronics/v251/en/Subsystems/Maxwell/Content/Maxwell/SpecifyingBHCurvesforNonlinearRelativePermeability.htm)
- [Maxwell temperature-dependent B-P curves](https://ansyshelp.ansys.com/public/Views/Secured/Electronics/v242/en/Subsystems/Maxwell/Content/CalculatingPropertiesforTemperaturedependentCoreLossCurvesinMaxwell.htm)
- [FEMM manual](https://www.femm.info/Archives/doc/manual34.pdf)

## 6. Testing and acceptance

Add tests before implementation for:

- imported status creation and immediate persistence;
- simulation selection of imported revisions and explicit B-H series;
- replacement identity checks, atomic replacement, project-reference protection,
  and deletion confirmation behavior;
- loss-origin insertion, invalid zero-B/nonzero-loss rejection, increasing-B
  validation, generated-source persistence, and revision determinism;
- Steinmetz fitting that ignores the inserted origin;
- linear/log axis transforms, numeric tick labels, and explicit non-positive
  point notices;
- absence of direct point/series/lifecycle editing controls in the QML tree;
- XLSX import of the packaged template and the user's workbook shape without
  storing the workbook in the repository.

Verification commands:

```text
PYTHONPATH=. .venv/bin/python -m pytest tests -q -m "not aedt and not femm"
QT_QPA_PLATFORM=offscreen QSG_RHI_BACKEND=software PYTHONPATH=. .venv/bin/python -m pytest tests -q -m ui
.venv/bin/python -m ruff check .
.venv/bin/python -m mypy src tools
PYTHONPATH=. .venv/bin/python tools/check_architecture.py
git diff --check
```
