# Material Studio Spreadsheet-Only Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove image/PDF material ingestion and provide a spreadsheet-only Material Studio with clear plots for selected material revisions and series.

**Status:** Implemented and verified on 2026-07-20. The complete non-solver suite,
UI suite, Ruff, strict mypy, architecture check, and diff gate are green.

**Architecture:** Keep CSV/XLSX parsing, immutable draft services, repository persistence, validation, fitting, and project pinning as the authoritative path. Simplify the PySide6 controller to table state and let a focused QML curve editor render canonical points for the selected revision and series.

**Tech Stack:** Python 3.10–3.13, PySide6/QML, stdlib, openpyxl, pytest, Ruff, strict mypy, JSON Schema 2020-12.

## Global Constraints

- Code, schemas, QML copy, documentation, branches, commits, and logs use English; visible QML strings use `qsTr`.
- `domain`, `geometry`, `materials`, and solver-independent simulation recipes remain free of PySide6, QML, QtPdf, filesystem, PyAEDT, FEMM, and SQLite imports.
- CSV/XLSX are the only material ingestion formats; PNG/JPEG/PDF, OCR, crop, calibration, and image point extraction are removed.
- Approved revisions remain immutable; editing creates a distinct draft.
- The controller delegates import, validation, fitting, persistence, and project pinning to existing services.
- Existing responsive layout behavior for compact, 2K, and 4K widths remains covered by UI tests.
- Run focused tests, the full non-solver suite, UI suite, Ruff, strict mypy, architecture checks, and `git diff --check` before commit and push.

---

### Task 1: Remove image extraction from the material data path

**Files:**
- Modify: `src/inductor_designer/materials/records.py`
- Delete: `src/inductor_designer/materials/calibration.py`
- Modify: `src/inductor_designer/materials/serde.py`
- Modify: `src/inductor_designer/materials/validation.py`
- Modify: `src/inductor_designer/materials/replay.py`
- Modify: `src/inductor_designer/application/services/material_drafts.py`
- Delete: `src/inductor_designer/ui/material_source.py`
- Delete: `tests/ui/test_material_source.py`
- Modify: matching unit and integration material tests under `tests/unit/materials`, `tests/unit/application`, and `tests/integration`

**Interfaces:**
- `SourceKind` contains only `CSV` and `SPREADSHEET`.
- `PointSeries` has `series_id`, `kind`, units, conditions, points, and
  `source_filename`; it has no extraction field.
- `reproduce_record()` parses CSV source bytes for every series and rejects any
  unsupported persisted source kind with an actionable mismatch.
- `replace_table_series()` is the only point-series replacement path.

- [x] **Step 1: Write the failing table-only contract tests**

Add assertions that a `PointSeries` constructor has no extraction argument,
that `SourceKind("image")` is rejected, and that replay uses only CSV bytes:

```python
def test_material_record_model_has_no_image_extraction_path() -> None:
    assert not hasattr(PointSeries, "extraction")
    with pytest.raises(ValueError):
        SourceKind("image")

def test_material_serde_rejects_non_table_source_kind() -> None:
    document = _record_json_with_source_kind("image")
    with pytest.raises(ValueError, match="source kind"):
        material_record_from_json(document)
```

- [x] **Step 2: Run the RED tests**

Run:

```console
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/unit/materials/test_records.py tests/unit/materials/test_material_serde.py tests/unit/materials/test_replay.py -q
```

Expected: FAIL because `PointSeries` still exposes extraction and replay still
contains an image branch.

- [x] **Step 3: Implement the minimal table-only model**

Remove `SourceKind.IMAGE`, the `PointSeries.extraction` field, calibration
serialization/deserialization, image replay branches, and image-only draft
constructors/replacements. Keep generated per-series CSV provenance and the
existing `replace_table_series()` path. Delete the unused image renderer and
its tests.

- [x] **Step 4: Run focused material tests**

Run:

```console
.venv/bin/python -m pytest tests/unit/materials tests/unit/application/test_material_drafts.py tests/integration/test_material_reproducibility.py -q
```

Expected: all table import, validation, replay, fitting, draft, and repository
tests pass with no image extraction symbols remaining.

### Task 2: Simplify the controller to CSV/XLSX workflows

**Files:**
- Modify: `src/inductor_designer/ui/material_studio_controller.py`
- Modify: `tests/ui/test_material_studio_controller.py`
- Modify: `tests/ui/test_material_studio_workflow.py`
- Modify: `tests/ui/test_qml_smoke.py`

**Interfaces:**
- Retain `selectMaterial`, `selectRevision`, `selectSeries`, `importTable`,
  `exportSelectedWorkbook`, `importEditedWorkbook`, `addTableSeries`,
  `setSeriesMetadata`, `setCanonicalPoint`, `deletePoint`, lifecycle slots, and
  `useInProject`.
- Remove `importSourceImage`, `createImageDraft`, `addImageSeries`, `setCrop`,
  `setXAxis`, `setYAxis`, `addPixelPoint`, `movePixelPoint`, and `imageEditing`.
- Expose `tableEditing` with only the active series metadata and expose
  `series`, `points`, `sourcePoints`, `issues`, `fit`, `selectedMaterial`,
  `selectedRevision`, and `statusMessage`.

- [x] **Step 1: Write failing controller tests for the new public surface**

Add a spreadsheet-only test that imports the CSV template, selects its first
series, and asserts plot data is canonical and no image actions exist:

```python
def test_controller_exposes_only_table_material_workflow(tmp_path: Path) -> None:
    controller, _ = _controller(InMemoryMaterialRepository())
    source = tmp_path / "material.csv"
    source.write_bytes(material_import_template("csv").data)
    controller.importTable(_file_url(source))

    assert controller.points[0]["x"] == 0.0
    assert controller.series[0]["sourceKind"] in ("csv", "spreadsheet")
    assert not hasattr(controller, "importSourceImage")
    assert not hasattr(controller, "createImageDraft")
```

Replace image workflow tests with table lifecycle, numeric edit, failed import,
selected revision, and selected series assertions.

- [x] **Step 2: Run the RED controller tests**

Run:

```console
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ui/test_material_studio_controller.py tests/ui/test_material_studio_workflow.py -q
```

Expected: FAIL because the controller still exposes image state/actions and the
QML test doubles still model image controls.

- [x] **Step 3: Implement the simplified controller**

Remove image imports, source rendering state, extraction state, image actions,
and image-specific dirty groups. Replace `imageEditing` with `tableEditing` and
make `_replacement_editor_series()` always call `replace_table_series()`.
Rename status/comparison text from image/source terminology to imported/current
table terminology. Preserve atomic failure behavior and explicit revision
selection.

- [x] **Step 4: Run controller tests to GREEN**

Run the focused command from Step 2. Expected: all retained spreadsheet
workflow tests pass and no removed image method is callable.

### Task 3: Replace the image workspace with a visible canonical curve plot

**Files:**
- Modify: `src/inductor_designer/ui/qml/MaterialStudioPage.qml`
- Modify: `src/inductor_designer/ui/qml/MaterialCurveEditor.qml`
- Delete: `src/inductor_designer/ui/qml/MaterialSourceView.qml`
- Modify: `tests/ui/test_qml_smoke.py`
- Modify: `tests/ui/test_material_studio_workflow.py`

**Interfaces:**
- QML retains object names for library/revision/lifecycle controls and adds
  `materialCurveCanvas`, `curvePlotTitle`, `curvePlotDetails`,
  `curvePlotXAxisLabel`, `curvePlotYAxisLabel`, and `curvePlotEmptyState`.
- The curve editor reads `controller.series`, `controller.points`, and the
  active table metadata; it never reads an image data URL or pixel coordinates.

- [x] **Step 1: Write failing QML plot assertions**

Assert the image dialog/source view/crop controls are absent and the selected
table revision updates the plot labels:

```python
assert root.findChild(QObject, "imageSourceDialog") is None
assert root.findChild(QObject, "materialSourceView") is None
plot = root.findChild(QObject, "materialCurveCanvas")
assert plot is not None
assert "A/m" in root.findChild(QObject, "curvePlotXAxisLabel").property("text")
assert "T" in root.findChild(QObject, "curvePlotYAxisLabel").property("text")
```

- [x] **Step 2: Run the QML RED tests**

Run:

```console
QT_QPA_PLATFORM=offscreen QSG_RHI_BACKEND=software .venv/bin/python -m pytest tests/ui/test_qml_smoke.py tests/ui/test_material_studio_workflow.py -q -m ui
```

Expected: FAIL because the image workspace still exists and the named plot
labels do not exist.

- [x] **Step 3: Implement the table-only QML page and plot**

Remove the image/PDF dialog, PDF page control, source identity form, image
series button, crop section, both calibration sections, and `MaterialSourceView`.
Keep CSV/XLSX import/export, table-series management, series metadata, lifecycle,
validation, and project selection. In `MaterialCurveEditor.qml`, draw a border,
line, circular markers, and simple axis labels from canonical point ranges;
display selected series units and conditions; and show an empty-state label when
there is no active series.

- [x] **Step 4: Run QML tests to GREEN**

Run the focused command from Step 2. Expected: all responsive, accessibility,
library selection, lifecycle, and plot tests pass.

### Task 4: Update documentation, plan index, and verification gates

**Files:**
- Modify: `docs/superpowers/plans/README.md`
- Modify: `docs/development/material-records.md`
- Modify: `docs/development/ROADMAP.md`
- Modify: `docs/superpowers/plans/2026-07-20-material-studio-spreadsheet-only.md`
- Create: `docs/superpowers/specs/2026-07-20-material-studio-spreadsheet-only-design.md`
- Create: `docs/adr/0002-spreadsheet-only-material-ingestion.md`

- [x] **Step 1: Update the written workflow**

Replace image/PDF/manual-digitization instructions with CSV/XLSX import,
revision selection, series selection, canonical plot inspection, numeric table
editing, and lifecycle/project-pinning steps. Mark the prior image workflow as
superseded and link the new spec and ADR.

- [x] **Step 2: Run repository-wide text checks**

Run:

```console
rg -n "importSourceImage|createImageDraft|addImageSeries|materialSourceView|Crop source plot|Calibrate X axis|Calibrate Y axis|OCR|automatic image curve" src tests docs/development README.md
```

Expected: no production/UI references to the removed workflow; historical
superseded specs may mention the decision only where explicitly marked.

- [x] **Step 3: Run complete verification**

Run:

```console
PYTHONPATH=. .venv/bin/python -m pytest tests -q -m "not aedt and not femm" --cov=inductor_designer --cov-report=term-missing
QT_QPA_PLATFORM=offscreen QSG_RHI_BACKEND=software PYTHONPATH=. .venv/bin/python -m pytest tests -q -m ui
.venv/bin/python -m ruff check .
.venv/bin/python -m mypy src tools
PYTHONPATH=. .venv/bin/python tools/check_architecture.py
git diff --check
```

Result: 672 tests passed, 4 solver tests deselected, 89.84% coverage; 22 UI
tests passed; all static, architecture, and diff gates exited 0.

- [x] **Step 4: Commit and push**

```console
git add src tests docs
git commit -m "feat(materials): make Material Studio spreadsheet-only"
git push -u origin codex/materials-spreadsheet-only
```

The three pre-existing `.DS_Store` files remain untracked and are not staged.
