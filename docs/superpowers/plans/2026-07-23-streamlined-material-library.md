# Streamlined Material Library Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Load the newest saved material revision with one click, remove review/fit UI, and let users download the selected material as an editable XLSX workbook.

**Architecture:** Keep revision identity inside the existing repository and controller, but remove revision selection from the user-facing workflow. Reuse the existing XLSX exporter and file-writing controller slot; the QML change only restores a save dialog and button. Import-time validation remains unchanged while its dedicated display pane is removed.

**Tech Stack:** Python 3.10–3.13, PySide6/QML, existing CSV/XLSX material adapters, pytest, Ruff, strict mypy.

## Global Constraints

- Use English for code, documentation, UI copy, logs, branches, commits, and pull requests.
- Keep `domain`, `geometry`, `materials`, and solver-independent simulation recipes free of PyAEDT, Qt, SQLite, and operating-system APIs.
- Preserve stored canonical values, source hashes, units, and material identity.
- Add or update tests before implementation and observe every focused test fail before changing production code.
- Do not stage `.DS_Store`, generated outputs, or the local `materials-overlay/`.

---

### Task 1: Load the newest revision when a material is selected

**Files:**
- Modify: `tests/ui/test_material_studio_controller.py`
- Modify: `src/inductor_designer/ui/material_studio_controller.py`

**Interfaces:**
- Consumes: `list_material_revision_summaries(repository, ref)`, whose first result is the newest revision.
- Produces: unchanged `selectMaterial(manufacturer, name, grade) -> bool`, now with `selectedRevision`, series, points, and source data loaded on success.

- [x] **Step 1: Write the failing controller test**

```python
assert controller.selectMaterial(
    approved.record.ref.manufacturer,
    approved.record.ref.name,
    approved.record.ref.grade,
)
assert controller.selectedRevision["revisionId"] == approved.record.revision_id
assert controller.tableEditing["metadata"]["seriesId"] == "bh-25c"
```

Remove the explicit `selectRevision(...)` call from the existing library-selection test so the failure proves that material selection alone does not yet load a revision.

- [x] **Step 2: Run the focused test and verify RED**

Run:

```bash
QT_QPA_PLATFORM=offscreen QSG_RHI_BACKEND=software PYTHONPATH=. \
  .venv/bin/python -m pytest \
  tests/ui/test_material_studio_controller.py::test_library_refresh_and_revision_selection_expose_table_provenance -q
```

Expected: failure because `selectedRevision` is empty after `selectMaterial`.

- [x] **Step 3: Implement automatic newest-revision loading**

After `selectMaterial` refreshes the sorted summaries, load the first revision through the existing slot:

```python
self._run_action(action)
if selected and self._revisions:
    return self.selectRevision(str(self._revisions[0]["revisionId"]))
return selected
```

When there are no revisions, keep the material selected, leave the curve empty, and report:

```python
self._set_status("The selected material has no stored revisions.")
```

- [x] **Step 4: Run controller tests and verify GREEN**

Run:

```bash
QT_QPA_PLATFORM=offscreen QSG_RHI_BACKEND=software PYTHONPATH=. \
  .venv/bin/python -m pytest tests/ui/test_material_studio_controller.py -q
```

Expected: all controller tests pass.

---

### Task 2: Remove revision/review/fit UI and expose material XLSX download

**Files:**
- Modify: `tests/ui/test_material_studio_workflow.py`
- Modify: `src/inductor_designer/ui/qml/MaterialLibraryPane.qml`
- Modify: `src/inductor_designer/ui/qml/MaterialStudioPage.qml`

**Interfaces:**
- Consumes: `MaterialStudioController.exportSelectedWorkbook(destination_url)`.
- Produces: QML objects `downloadSelectedMaterialButton` and `materialWorkbookDownloadDialog`.
- Removes from the rendered page: `revisionList`, `materialValidationPane`, and all reviewer/approver/fit content.

- [x] **Step 1: Write failing UI structure tests**

Add these required controls:

```python
for name in ("downloadSelectedMaterialButton", "materialWorkbookDownloadDialog"):
    assert root.findChild(QObject, name) is not None
```

Add these absence checks:

```python
for name in ("revisionList", "materialValidationPane", "fitLossSeriesIds"):
    assert root.findChild(QObject, name) is None
```

Strengthen the restart workflow:

```python
assert controller.selectedRevision["status"] == "imported"
assert controller.points
download = root.findChild(QObject, "downloadSelectedMaterialButton")
assert download.property("enabled") is True
```

- [x] **Step 2: Run the focused UI tests and verify RED**

Run:

```bash
QT_QPA_PLATFORM=offscreen QSG_RHI_BACKEND=software PYTHONPATH=. \
  .venv/bin/python -m pytest tests/ui/test_material_studio_workflow.py -q
```

Expected: failures because the revision/validation widgets still exist and the download controls are absent.

- [x] **Step 3: Simplify `MaterialLibraryPane.qml`**

Keep only the material list. Change the heading to:

```qml
Label {
    text: qsTr("Material library")
    font.bold: true
}
```

Delete `revisionDescription`, the `revisionListView` alias, the Revisions label, and the complete `revisionList`. The material button continues to call:

```qml
materialLibraryPane.controller.selectMaterial(
    modelData.manufacturer,
    modelData.name,
    modelData.grade
)
```

- [x] **Step 4: Add the XLSX save dialog and button**

Add:

```qml
FileDialog {
    id: materialWorkbookDownloadDialog
    objectName: "materialWorkbookDownloadDialog"
    title: qsTr("Save selected material XLSX")
    fileMode: FileDialog.SaveFile
    nameFilters: [qsTr("Excel workbooks (*.xlsx)")]
    defaultSuffix: "xlsx"
    onAccepted: controller.exportSelectedWorkbook(selectedFile.toString())
}
```

Add under Import:

```qml
Button {
    objectName: "downloadSelectedMaterialButton"
    Layout.fillWidth: true
    text: qsTr("Download selected material XLSX")
    enabled: controller !== null
        && Object.keys(controller.selectedRevision).length > 0
    onClicked: materialWorkbookDownloadDialog.open()
}
```

- [x] **Step 5: Remove revision selection and fit/validation rendering**

Reduce `libraryController` to materials and `selectMaterial(...)`. Remove revision branches and state from the selection helper functions. Keep the existing transaction-host call for material selection:

```qml
function performLibrarySelection(values) {
    const selected = controller.selectMaterial(values[0], values[1], values[2])
    if (selected) {
        confirmedMaterialSelection = values
    }
    restoreMaterialSelection(selected ? values : confirmedMaterialSelection)
}
```

Remove `MaterialValidationPane` from `materialWorkspaceGrid`; retain the curve workspace as the only child so existing responsive layout behavior remains stable.

- [x] **Step 6: Run UI tests and verify GREEN**

Run:

```bash
QT_QPA_PLATFORM=offscreen QSG_RHI_BACKEND=software PYTHONPATH=. \
  .venv/bin/python -m pytest tests/ui/test_material_studio_workflow.py tests/ui/test_qml_smoke.py -q
```

Expected: all selected UI tests pass with no QML reference errors.

---

### Task 3: Verify XLSX round-trip and publish the completed material workflow

**Files:**
- Modify: `tests/ui/test_material_studio_controller.py`
- Modify: `docs/superpowers/plans/2026-07-23-streamlined-material-library.md`
- Include all intended material-workflow source, test, ADR, specification, plan, README, and roadmap changes already present on `codex/materials-spreadsheet-only`.

**Interfaces:**
- Consumes: `exportSelectedWorkbook(destination_url)` and `import_material_file_as_imported(filename, data, created_at=...)`.
- Produces: a regression test proving the exported workbook preserves every stored series and can be imported again.

- [x] **Step 1: Write the XLSX round-trip test**

```python
controller.importTable(_file_url(source_path))
expected_ids = [item["seriesId"] for item in controller.series]
destination = tmp_path / "downloaded-material.xlsx"
controller.exportSelectedWorkbook(_file_url(destination))

imported = import_material_file_as_imported(
    destination.name,
    destination.read_bytes(),
    created_at="2026-07-23T12:00:00+00:00",
)
assert [item.series_id for item in imported.record.series] == expected_ids
```

- [x] **Step 2: Run the focused test and verify its behavior**

Run:

```bash
QT_QPA_PLATFORM=offscreen QSG_RHI_BACKEND=software PYTHONPATH=. \
  .venv/bin/python -m pytest \
  tests/ui/test_material_studio_controller.py::test_exported_material_workbook_round_trips_all_series -q
```

If it passes immediately, document that the existing exporter already satisfies the requirement; do not change production export code.

- [x] **Step 3: Run full verification**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests -q -m "not aedt and not femm"
QT_QPA_PLATFORM=offscreen QSG_RHI_BACKEND=software PYTHONPATH=. \
  .venv/bin/python -m pytest tests -q -m ui
.venv/bin/python -m ruff check .
.venv/bin/python -m mypy src tools
PYTHONPATH=. .venv/bin/python tools/check_architecture.py
git diff --check
```

Expected: every command exits zero.

- [x] **Step 4: Run the live UI workflow**

Open the program without importing a new file, select `Magnetics — High Flux — 60u`, and verify:

```text
one material click -> curve visible
X axis -> 0..500 Oe
Y axis -> 0..1.417 T, increasing upward
Download selected material XLSX -> enabled
Delete selected material -> confirmation opens; cancel without deleting
```

- [x] **Step 5: Stage and commit only intended files**

Exclude `.DS_Store`, `materials-overlay/`, and `outputs/`. Stage the material workflow, tests, documentation, ADR, plans, and generated template explicitly, then commit:

```bash
git commit -m "feat(materials): streamline spreadsheet library workflow"
```

- [x] **Step 6: Push the current branch**

Run:

```bash
git push -u origin codex/materials-spreadsheet-only
```

Expected: the remote branch advances to the new commits.
