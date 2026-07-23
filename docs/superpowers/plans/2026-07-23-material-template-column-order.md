# Material Template Value-Unit Column Order Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the packaged XLSX material template place each numeric value beside its unit while keeping download, upload, draft creation, and curve plotting compatible.

**Architecture:** Keep the canonical material-record model unchanged. Update the XLSX presentation contract, parser column mapping, editable-workbook exporter, and user guidance together. The controller and QML curve editor continue consuming canonical `PointSeries` values produced by the existing table import service.

**Tech Stack:** Python 3.10–3.13, `openpyxl` runtime XLSX parser/exporter, `@oai/artifact-tool` XLSX authoring and rendering, pytest, PySide6/QML.

## Global Constraints

- Code, schemas, QML copy, documentation, branches, commits, and logs use English.
- Preserve `MaterialRef` identity fields and solver-independent material records.
- `dc_bias_a_per_m` remains optional curve-condition metadata; it is not a new calculation input.
- Use `@oai/artifact-tool` for packaged workbook authoring and visual verification.
- Keep Excel values typed as numbers; do not encode decimal separators as text.
- Run focused tests, round-trip UI/integration tests, full non-solver tests, Ruff, strict mypy, architecture checks, and `git diff --check` before claiming completion.

---

### Task 1: Lock the new XLSX column contract in tests

**Files:**
- Modify: `tests/unit/adapters/test_material_templates.py`
- Modify: `tests/unit/adapters/test_material_table_file.py`
- Modify: `tests/integration/test_material_table_upload.py`
- Modify: `tests/integration/test_material_studio_exit.py`

**Interfaces:**
- B-H sheet header becomes `series_id`, `temperature_c`, `dc_bias_a_per_m`, `h`, `h_unit`, `b`, `b_unit`.
- Loss sheet header becomes `series_id`, `frequency_hz`, `temperature_c`, `dc_bias_a_per_m`, `b`, `b_unit`, `loss`, `loss_unit`.
- Unit dropdown ranges move to B-H `E`/`G` and Loss `F`/`H`.

- [x] **Step 1: Write failing assertions**

Change existing header, dropdown, direct-cell edit, and formula-cell assertions to the new coordinates. Keep the expected canonical `PointSeries` values unchanged.

- [x] **Step 2: Run focused tests and confirm failure**

```console
PYTHONPATH=. .venv/bin/python -m pytest tests/unit/adapters/test_material_templates.py tests/unit/adapters/test_material_table_file.py tests/integration/test_material_table_upload.py tests/integration/test_material_studio_exit.py -q
```

Expected: failures identify old packaged headers, old dropdown ranges, or old exporter row positions.

### Task 2: Update parser and exporter mapping

**Files:**
- Modify: `src/inductor_designer/adapters/materials/table_file.py`
- Modify: `src/inductor_designer/adapters/materials/templates.py`

**Interfaces:**
- `_BH_COLUMNS` and `_LOSS_COLUMNS` describe the new headers.
- `_table_rows()` continues mapping workbook fields to `MaterialTableRow(x, y, x_unit, y_unit)` by field name.
- `_bh_rows()` and `_loss_rows()` emit value-then-unit tuples matching the workbook contract.

- [x] **Step 1: Change header constants and exporter tuple order**

Use field-name mapping for import and emit `(h, h_unit, b, b_unit)` / `(b, b_unit, loss, loss_unit)` for export.

- [x] **Step 2: Run focused tests to green**

```console
PYTHONPATH=. .venv/bin/python -m pytest tests/unit/adapters/test_material_templates.py tests/unit/adapters/test_material_table_file.py tests/integration/test_material_table_upload.py tests/integration/test_material_studio_exit.py -q
```

Expected: all parser/exporter round-trip assertions pass once the workbook resource is updated in Task 3.

### Task 3: Rebuild packaged XLSX with artifact-tool

**Files:**
- Modify: `src/inductor_designer/resources/material_templates/material-import-template.xlsx`

**Interfaces:**
- Keep four visible sheets, table names, typed example values, styling, filters, and unit validation semantics.
- Update Instructions text: grade is a catalog/material designation; DC bias is optional measurement condition; blank means not supplied; `0` means explicit zero bias.
- Move numeric columns adjacent to their unit columns and move dropdown validation ranges with the unit headers.

- [x] **Step 1: Import and render current workbook**

Use `@oai/artifact-tool` to inspect all sheets and styles. Preserve existing fills, fonts, borders, number formats, tables, and validations.

- [x] **Step 2: Apply targeted value/style/validation changes**

Reorder only B-H and Loss data columns, update Instructions wording, and keep cells numeric. Export exactly the packaged XLSX path.

- [x] **Step 3: Render all sheets and inspect**

Verify no header or value is clipped, unit dropdown columns remain identifiable, and the workbook remains compact.

### Task 4: Verify download → fill → upload → curve plot

**Files:**
- Modify: `docs/development/material-records.md`
- Modify: `docs/superpowers/specs/2026-07-18-material-import-templates-design.md`

- [x] **Step 1: Document final XLSX contract and semantics**

Record the value-unit adjacency, grade identity meaning, optional DC-bias condition, locale-controlled decimal input, and canonical curve plotting flow.

- [x] **Step 2: Run complete verification**

```console
PYTHONPATH=. .venv/bin/python -m pytest tests -q -m "not aedt and not femm"
QT_QPA_PLATFORM=offscreen QSG_RHI_BACKEND=software PYTHONPATH=. .venv/bin/python -m pytest tests -q -m ui
.venv/bin/python -m ruff check .
.venv/bin/python -m mypy src tools
PYTHONPATH=. .venv/bin/python tools/check_architecture.py
git diff --check
```

Expected: all applicable tests and static/architecture checks pass; the uploaded workbook produces a draft whose selected series drives the existing QML curve plot.
