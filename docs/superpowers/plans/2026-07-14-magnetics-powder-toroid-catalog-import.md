# Magnetics Powder Toroid Catalog Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Import all complete toroidal powder-core data rows from the 2025 Magnetics catalog into the canonical YAML catalog and prove the resulting index is valid and queryable.

**Architecture:** Keep `catalog/cores/magnetics-powder.yaml` as the canonical human-review surface. Expand each non-empty material cell from catalog pages 154-196 into one schema-valid record, preserve the ten existing reviewed records, and rely on the existing `tools/build_catalog.py` pipeline to compile records into SQLite.

**Tech Stack:** YAML, JSON Schema draft 2020-12, Python 3.10+, pytest, sqlite3, existing catalog repository and build tooling.

## Global Constraints

- Import toroidal data pages 154-196 only.
- Keep `outerDiameter.minM`, `innerDiameter.maxM`, and `height.minM` equal to `null`.
- Do not infer records that are present only in the locator index and have no detailed data row.
- Preserve the ten existing reviewed records and reviewer.
- Mark every newly imported record as draft.
- Do not commit the supplier PDF or generated SQLite artifact.

---

### Task 1: Add catalog regression expectations

**Files:**
- Modify: `tests/unit/adapters/catalog/test_sqlite_repository.py`

**Interfaces:**
- Consumes: `tools.build_catalog.build(...)`, `SqliteCatalogRepository.list_cores()`, and `SqliteCatalogRepository.get_core(...)`.
- Produces: regression coverage for count, uniqueness, material coverage, page range, dimension-bound semantics, review preservation, and representative records.

- [ ] **Step 1: Write failing tests for the complete toroid set**

Add constants for the expected 1,923 powder records, nine material names, ten reviewed part numbers, and representative part numbers from the beginning, middle, and end of the data section.

- [ ] **Step 2: Assert count and uniqueness**

Filter `repository.list_cores()` to `CoreFamily.POWDER_TOROID`; assert length 1,923 and that all part numbers are unique.

- [ ] **Step 3: Assert dimension bounds**

For every powder toroid, assert:

```python
assert core.outer_diameter.min_m is None
assert core.outer_diameter.max_m is not None
assert core.inner_diameter.min_m is not None
assert core.inner_diameter.max_m is None
assert core.height.min_m is None
assert core.height.max_m is not None
```

- [ ] **Step 4: Assert review preservation and representative records**

Check the ten reviewed records remain reviewed by Fabio Posser. Query representative records including `0077141A7`, `C058031A2`, `0078050A7`, `0058443A2`, `0059534A2`, and a page-196 record, verifying material, source page, AL, and dimensions.

- [ ] **Step 5: Run the focused test and confirm RED**

Run:

```bash
pytest tests/unit/adapters/catalog/test_sqlite_repository.py -q
```

Expected before data replacement: failure because only the initial powder subset exists.

### Task 2: Replace the canonical powder-toroid data

**Files:**
- Replace: `catalog/cores/magnetics-powder.yaml`

**Interfaces:**
- Consumes: `schemas/catalog/core.v1.schema.json` and `tools/build_catalog.py`.
- Produces: 1,923 unique schema-valid records sorted by `partNumber`.

- [ ] **Step 1: Generate one record per non-empty material cell**

Use the detailed Toroid Data tables on printed pages 154-196. Convert mm/mm2/mm3 to meters/m2/m3 and store AL in nH/T2.

- [ ] **Step 2: Apply catalog part-number conventions**

Use material codes 77, 79, 76, 70, 78, 74, 59, 58, and 55 for the nine columns. Resolve `CO58031A2` to `C058031A2` and `078050A7` to `0078050A7` based on the data table and established code format.

- [ ] **Step 3: Apply review and coating policy**

Keep the ten existing reviewed records reviewed by Fabio Posser. Mark all other records draft. Apply catalog coating colors to new records and retain committed coating text for existing reviewed records.

- [ ] **Step 4: Record source discrepancies in file comments**

State that detailed data pages are authoritative and that the locator index contains known omissions/stale entries; do not synthesize `0055340A2` or `0055341A2` because no detailed AL rows exist.

- [ ] **Step 5: Validate YAML and JSON Schema**

Run a Python validation command that loads every record and calls `Draft202012Validator.validate(record)` against `schemas/catalog/core.v1.schema.json`.

Expected: 1,923 records, zero validation failures, zero duplicate part numbers.

- [ ] **Step 6: Build the SQLite catalog**

Run:

```bash
python tools/build_catalog.py --out /tmp/magnetics-catalog.sqlite
```

Expected: exit 0 and `meta.coreCount` equal to existing ferrite count plus 1,923 powder records.

### Task 3: Verify repository behavior and quality gates

**Files:**
- No additional production files.

**Interfaces:**
- Consumes: complete catalog data and Task 1 tests.
- Produces: verification evidence for PR review.

- [ ] **Step 1: Run focused catalog tests**

```bash
pytest tests/unit/adapters/catalog/test_sqlite_repository.py -q
```

Expected: PASS.

- [ ] **Step 2: Run the non-AEDT test suite**

```bash
pytest -m "not aedt" -q
```

Expected: PASS.

- [ ] **Step 3: Run static checks**

```bash
ruff check .
ruff format --check .
mypy src tools
```

Expected: all commands exit 0.

- [ ] **Step 4: Review the final diff**

Confirm only the design/plan documents, powder YAML, and focused catalog test changed. Confirm no PDF, SQLite database, or extraction scratch file is committed.

- [ ] **Step 5: Open a draft PR**

Create a draft PR from `agent/import-all-magnetics-powder-toroids` to `main`. Include counts, material breakdown, review policy, validation results, and the six known index/data discrepancies.
