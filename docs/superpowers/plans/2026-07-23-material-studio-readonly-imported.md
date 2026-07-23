# Material Studio Read-Only Imported Materials Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make spreadsheet-imported materials immediately persisted as immutable `Imported` revisions, usable in simulation, replaceable/deletable through guarded actions, and visualized through a read-only curve preview with linear/log axes.

**Architecture:** Keep the domain and solver-independent material model free of UI and filesystem dependencies. Extend the material repository port for exact-revision/material deletion, normalize loss origins in the existing table-import path before persistence and fitting, and keep project pinning as an application service. Replace the current editor-oriented QML surface with read-only library, provenance, plot, validation, import/replace/delete, and project-selection controls.

**Tech Stack:** Python 3.10–3.13, dataclasses/enums, existing CSV/XLSX adapters, PySide6/QML, pytest, Ruff, strict mypy.

## Global Constraints

- Use English for code, schemas, documentation, UI copy, logs, branches, commits, and pull requests.
- Keep `domain`, `geometry`, `materials`, and solver-independent simulation recipes free of PyAEDT, Qt, SQLite, or operating-system APIs.
- Preserve unrelated uncommitted changes, including the user’s `materials-overlay/` and spreadsheet-template edits.
- Add tests before implementation and run each focused red/green cycle.
- Preserve source bytes, hashes, canonical points, and deterministic revision IDs; never silently mutate the uploaded workbook.
- Imported and approved revisions are read-only in Material Studio; direct point/series/lifecycle editing controls are removed.

---

### Task 1: Imported status and loss-origin normalization

**Files:**
- Modify: `src/inductor_designer/materials/records.py`
- Modify: `src/inductor_designer/materials/validation.py`
- Modify: `src/inductor_designer/application/services/material_import.py`
- Modify: `src/inductor_designer/application/services/material_table_import.py`
- Modify: `src/inductor_designer/adapters/materials/table_file.py`
- Test: `tests/unit/materials/test_records.py`, `tests/unit/materials/test_material_validation.py`, `tests/unit/application/test_material_import.py`, `tests/unit/application/test_material_table_import.py`, `tests/unit/adapters/test_material_table_file.py`

**Interfaces:**
- Add `MaterialStatus.IMPORTED`.
- Add `new_imported_record(...) -> MaterialRecord` and `import_material_file_as_imported(...) -> ImportedMaterialDraft`.
- Preserve `import_material_file_as_draft` for legacy/API compatibility.

- [x] Write failing tests for imported records, automatic loss `(0,0)` insertion, source-description provenance, invalid zero-B/nonzero-loss rejection, duplicate/increasing loss B validation, and a Steinmetz fit that ignores the origin.
- [x] Run the focused tests and confirm they fail for the missing status/normalization behavior.
- [x] Add the status, validate imported lifecycle fields, prepend `(0,0)` only when all loss B values are positive, reject invalid zero-B loss, and append the normalization note to generated source descriptions.
- [x] Make the imported adapter path validate before returning; retain the old draft path for legacy workflows.
- [x] Run focused tests, Ruff, and mypy for the touched modules.

### Task 2: Repository deletion and simulation acceptance

**Files:**
- Modify: `src/inductor_designer/application/ports/material_repository.py`
- Modify: `src/inductor_designer/adapters/materials/overlay_repository.py`
- Modify: `tests/fakes/material_repository.py`
- Modify: `src/inductor_designer/application/services/material_selection.py`
- Modify: `src/inductor_designer/simulation/maxwell_plan.py`
- Test: `tests/unit/adapters/test_overlay_repository.py`, `tests/unit/application/test_material_selection.py`, `tests/unit/simulation/test_maxwell_plan.py`

**Interfaces:**
- Add exact `delete_revision(ref, revision_id)` and `delete_material(ref, protected_revision_ids=())` repository operations.
- Project pinning continues to use immutable `MaterialRevisionSelection` snapshots.

- [x] Write failing tests for deletion, protected project revisions, imported project selection, and imported solver-plan construction.
- [x] Run those tests to verify the expected red failures.
- [x] Implement deletion atomically at the repository boundary, keep protected revisions, and accept `IMPORTED` alongside legacy `APPROVED` in project selection and solver export.
- [x] Run repository-contract, selection, and solver focused tests.

### Task 3: Read-only controller and import lifecycle

**Files:**
- Modify: `src/inductor_designer/ui/material_studio_controller.py`
- Modify: `src/inductor_designer/adapters/materials/__init__.py`
- Test: `tests/ui/test_material_studio_controller.py`, `tests/integration/test_material_table_upload.py`, `tests/integration/test_material_studio_exit.py`

**Interfaces:**
- Add controller slots `replaceSelectedMaterial(source_url)` and `deleteSelectedMaterial()`.
- Add `hasProject`/read-only capability properties as needed by QML.
- `importTable` immediately saves an `Imported` record and leaves the selection clean; replacement saves the new record before removing an unpinned previous imported revision.

- [x] Write failing controller tests for immediate persistence/status, replacement identity mismatch and success, project-reference protection, deletion, and rejection of direct editor mutations on imported records.
- [x] Run the focused controller/integration tests to verify red failures.
- [x] Implement import/replace/delete using the repository port and active project snapshots; keep legacy records readable and make project selection accept imported records.
- [x] Run all controller and material-upload integration tests.

### Task 4: Read-only plot and QML surface

**Files:**
- Modify: `src/inductor_designer/ui/qml/MaterialStudioPage.qml`
- Modify: `src/inductor_designer/ui/qml/MaterialCurveEditor.qml`
- Modify: `src/inductor_designer/ui/qml/MaterialLibraryPane.qml`
- Test: `tests/ui/test_material_studio_workflow.py`

**Interfaces:**
- Keep the material library and automatically load its newest revision.
- Expose template and selected-material XLSX download, import, replace, delete-confirmation, read-only series selection, `Log X`, `Log Y`, numeric tick labels, source/condition labels, and `Select for simulation`.
- Remove the visible revision list and Fit and Validation pane.
- Remove lifecycle fields/buttons, Series Management, Series Metadata editing, point dumps, editable point list, export/reimport controls.

- [x] Write failing QML-tree and controller-backed UI tests for the new controls, imported status, numeric axis labels, independent log toggles, non-positive-point notice, and absence of editor controls.
- [x] Run the UI tests to verify red failures.
- [x] Replace the editor-oriented QML sections with the read-only surface and implement linear/log transforms that omit non-positive points only from log rendering.
- [x] Run focused offscreen UI tests and inspect QML load output for errors.

### Task 5: Documentation, status, and full verification

**Files:**
- Modify: `docs/superpowers/specs/2026-07-23-material-studio-readonly-imported-design.md`
- Modify: `docs/development/material-records.md`
- Modify: `README.md`
- Test: any affected existing tests required by the final verification output

- [x] Update the approved spec status and document imported storage, replacement/deletion, loss-origin insertion, simulation selection, and read-only UI behavior.
- [x] Run the complete non-solver tests, UI tests, Ruff, mypy, architecture check, and `git diff --check` from the approved spec.
- [x] Review the diff and `git status` to confirm the user’s unrelated changes and imported overlay remain intact.
