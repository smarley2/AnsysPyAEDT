# Excel Identity Value Coercion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax.

**Goal:** Accept numeric Excel identity values such as grade `60` without
requiring the user to pre-format the cell as text.

**Architecture:** Coerce finite numeric values only at material identity
boundaries (`manufacturer`, `material_name`, and `grade`) in the existing
spreadsheet import path. Keep units, series IDs, source descriptions, and
revision identifiers strict text fields.

**Tech Stack:** Python 3.10–3.13, openpyxl, pytest, Ruff, mypy.

## Global Constraints

- Use English for code, tests, documentation, and commits.
- Preserve current CSV/XLSX metadata and series validation behavior.
- Do not add dependencies or modify material overlays, generated artifacts, or
  solver integration code.
- Add the regression test before production code.

---

### Task 1: Coerce numeric material identity values

**Files:**

- Modify: `src/inductor_designer/adapters/materials/table_file.py`
- Test: `tests/unit/adapters/test_material_table_file.py`

**Interfaces:**

- Consumes: Excel metadata values from the visible `Material` sheet and hidden
  `_MaterialStudio` lineage sheet.
- Produces: `MaterialRef` fields as non-empty strings; integral `60` and
  `60.0` both become `"60"`.

- [ ] **Step 1: Add the failing regression test**

  Extend `_workbook_bytes` usage with a numeric `Material!B4` value and assert
  that `import_material_file("numeric-grade.xlsx", ...)` returns:

  ```python
  MaterialRef("Example", "Ferrite", "60")
  ```

- [ ] **Step 2: Run the focused test and verify RED**

  ```bash
  PYTHONPATH=. .venv/bin/python -m pytest \
    tests/unit/adapters/test_material_table_file.py::test_xlsx_coerces_numeric_grade_to_text -q
  ```

  Expected: the import fails because `_required_text` currently rejects the
  numeric Excel value.

- [ ] **Step 3: Implement the minimal coercion**

  Add one identity-text helper that accepts strings and finite `int`/`float`
  values, formats integral numbers without `.0`, and retains strict rejection
  for booleans, empty values, and non-finite numbers. Use it only for
  manufacturer, material name, and grade in both metadata paths.

- [ ] **Step 4: Run focused tests and static checks**

  ```bash
  PYTHONPATH=. .venv/bin/python -m pytest \
    tests/unit/adapters/test_material_table_file.py \
    tests/integration/test_material_table_upload.py -q
  .venv/bin/python -m ruff check src/inductor_designer/adapters/materials/table_file.py \
    tests/unit/adapters/test_material_table_file.py
  PYTHONPATH=. .venv/bin/python -m mypy src tools
  ```

- [ ] **Step 5: Commit and publish**

  ```bash
  git add src/inductor_designer/adapters/materials/table_file.py \
    tests/unit/adapters/test_material_table_file.py \
    docs/superpowers/plans/2026-07-24-xlsx-identity-coercion.md
  git diff --cached --check
  git commit -m "fix(materials): coerce numeric spreadsheet identities"
  git push origin main
  ```
