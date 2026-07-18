# Material Import Templates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship self-describing CSV and Excel templates plus validated import paths that turn multi-series B-H and loss tables into canonical material-record inputs.

**Architecture:** A pure application service groups format-neutral rows and reuses the existing single-series importer. CSV/XLSX decoding and packaged-resource access live in `adapters/materials`; Excel parsing uses `openpyxl`, while the committed workbook is authored and visually verified with the bundled spreadsheet artifact workflow. Each uploaded series receives a deterministic generated CSV source for replay, and the original upload is retained and hashed as supplemental provenance.

**Tech Stack:** Python 3.10–3.13, stdlib `csv`/`io`/`importlib.resources`, `openpyxl>=3.1,<4`, bundled `@oai/artifact-tool` for workbook authoring, pytest, Ruff, strict mypy.

## Global Constraints

- Follow `docs/superpowers/specs/2026-07-18-material-import-templates-design.md` and `AGENTS.md`.
- Code, schemas, templates, workbook copy, documentation, commits, and errors use English.
- `domain`, `materials`, `geometry`, and solver-independent simulation recipes do not import `openpyxl`, filesystem, Qt, PyAEDT, FEMM, or SQLite APIs.
- The application service remains format-neutral; CSV/XLSX decoding stays in `adapters/materials`.
- Every behavior change follows RED → GREEN → refactor; tests must fail for the intended missing behavior before implementation.
- Spreadsheet dropdowns are guidance only. Python validation is authoritative.
- Uploaded points convert through `import_curve_csv`; do not duplicate unit conversion, sorting, rounding, or series physics checks.
- The uploaded file and every generated per-series CSV have SHA-256 provenance. Series link to generated CSV sources so existing replay remains deterministic.
- No upload creates a reviewed or approved record.
- The Material Studio UI buttons remain M5b scope; this plan provides stable import/template services for them.
- Gates: `.venv/bin/python -m pytest tests -q -m "not aedt and not femm" --cov=inductor_designer --cov-report=term-missing`, Ruff, strict mypy over `src tools`, architecture check, and `git diff --check`.

## File Structure

| File | Responsibility |
|---|---|
| `src/inductor_designer/application/services/material_table_import.py` | Format-neutral metadata/row DTOs, grouping, consistency checks, generated replay CSVs |
| `src/inductor_designer/adapters/materials/table_file.py` | Strict `.csv`/`.xlsx` decoding and formula rejection |
| `src/inductor_designer/adapters/materials/templates.py` | Packaged template lookup and immutable download bytes |
| `src/inductor_designer/resources/material_templates/material-import-template.csv` | Flat multi-series CSV template |
| `src/inductor_designer/resources/material_templates/material-import-template.xlsx` | Styled workbook with dropdown validation |
| `tests/unit/application/test_material_table_import.py` | Grouping, canonicalization, provenance, validation |
| `tests/unit/adapters/test_material_table_file.py` | CSV/XLSX equivalence and file-shape errors |
| `tests/unit/adapters/test_material_templates.py` | Resource and workbook contract |
| `docs/development/material-records.md` | User-facing template/import instructions |

---

### Task 1: Format-neutral multi-series import

**Files:**
- Modify: `src/inductor_designer/materials/records.py`
- Modify: `src/inductor_designer/materials/validation.py`
- Create: `src/inductor_designer/application/services/material_table_import.py`
- Create: `tests/unit/application/test_material_table_import.py`
- Modify: `tests/unit/materials/test_records.py`

**Interfaces:**

```python
class SourceKind(str, Enum):
    IMAGE = "image"
    CSV = "csv"
    SPREADSHEET = "spreadsheet"

@dataclass(frozen=True, slots=True)
class MaterialTableMetadata:
    ref: MaterialRef
    source_url: str
    source_page: int | None
    captured_at: str
    source_description: str

@dataclass(frozen=True, slots=True)
class MaterialTableRow:
    series_id: str
    kind: SeriesKind
    frequency_hz: float | None
    temperature_c: float | None
    dc_bias_a_per_m: float | None
    x_unit: str
    y_unit: str
    x: float
    y: float

@dataclass(frozen=True, slots=True)
class ImportedMaterialTable:
    ref: MaterialRef
    series: tuple[PointSeries, ...]
    sources: tuple[SourceProvenance, ...]
    source_files: tuple[tuple[str, bytes], ...]

def import_material_rows(
    metadata: MaterialTableMetadata,
    rows: tuple[MaterialTableRow, ...],
    *,
    upload_filename: str,
    upload_kind: SourceKind,
    upload_bytes: bytes,
) -> ImportedMaterialTable: ...
```

- [ ] **Step 1: Write failing tests for grouping and canonical output**

Create tests with two B-H series and two loss series. Assert one returned
`PointSeries` per `series_id`, canonical SI points, sorted x values, conditions
copied once per group, one original-upload provenance entry, and one generated
CSV provenance/source entry per series.

```python
result = import_material_rows(
    metadata,
    rows,
    upload_filename="material.xlsx",
    upload_kind=SourceKind.SPREADSHEET,
    upload_bytes=b"workbook",
)
assert tuple(series.series_id for series in result.series) == (
    "bh-25c",
    "bh-100c",
    "loss-100khz",
    "loss-200khz",
)
assert result.series[0].points[1] == CurvePoint(79.577471546, 0.1)
assert result.sources[0].filename == "material.xlsx"
assert dict(result.source_files)["material.xlsx"] == b"workbook"
```

- [ ] **Step 2: Run the grouping test and verify RED**

Run: `.venv/bin/python -m pytest tests/unit/application/test_material_table_import.py -q`

Expected: collection fails because `material_table_import` and
`SourceKind.SPREADSHEET` do not exist.

- [ ] **Step 3: Add source kind and minimal grouping implementation**

Group rows by first-seen `series_id`. For each group, require identical kind,
conditions, and units. Render its raw points as deterministic `x,y\n` CSV,
create a sanitized source filename `series-<series_id>.csv`, hash it, then call
the existing `import_curve_csv` with that generated source.

Use `sanitize_identifier` only at the filename boundary. Reject a generated
name collision before importing.

- [ ] **Step 4: Add failing validation tests**

Cover empty rows, blank series IDs, mixed metadata in one series, filename
collision after sanitization, unsupported upload kind, and `SPREADSHEET`
provenance referenced directly by a `PointSeries`. Assert actionable
`MaterialImportError.issues` strings.

- [ ] **Step 5: Verify validation RED, then implement minimal checks**

Run the focused test file after adding tests. Confirm each new case fails for
missing validation, then add only the required checks. Extend record validation
so spreadsheet provenance is allowed as supplemental provenance but cannot be
the direct source of a series.

- [ ] **Step 6: Run focused GREEN and static checks**

Run:

```console
.venv/bin/python -m pytest tests/unit/application/test_material_table_import.py tests/unit/materials/test_records.py tests/unit/materials/test_material_validation.py -q
.venv/bin/python -m ruff check src/inductor_designer/application/services/material_table_import.py src/inductor_designer/materials/records.py tests/unit/application/test_material_table_import.py
.venv/bin/python -m mypy src tools
.venv/bin/python tools/check_architecture.py
```

Expected: all exit 0.

- [ ] **Step 7: Commit Task 1**

```console
git add src/inductor_designer/materials/records.py src/inductor_designer/materials/validation.py src/inductor_designer/application/services/material_table_import.py tests/unit/application/test_material_table_import.py tests/unit/materials/test_records.py tests/unit/materials/test_material_validation.py
git commit -m "feat(materials): import multi-series material tables"
```

---

### Task 2: CSV and Excel file readers

**Files:**
- Modify: `pyproject.toml`
- Create: `src/inductor_designer/adapters/materials/table_file.py`
- Modify: `src/inductor_designer/adapters/materials/__init__.py`
- Create: `tests/unit/adapters/test_material_table_file.py`

**Interfaces:**

```python
def import_material_file(filename: str, data: bytes) -> ImportedMaterialTable:
    """Decode a .csv or .xlsx upload and import all contained series."""
```

- [ ] **Step 1: Add failing CSV acceptance tests**

Build an in-memory flat CSV using the exact 16-column schema from the design.
Assert B-H and loss rows group correctly, optional blank numeric fields become
`None`, and source metadata creates the expected `MaterialRef` and provenance.

- [ ] **Step 2: Run CSV tests and verify RED**

Run: `.venv/bin/python -m pytest tests/unit/adapters/test_material_table_file.py -q`

Expected: collection fails because `table_file` does not exist.

- [ ] **Step 3: Implement the CSV reader**

Use `csv.DictReader(io.StringIO(data.decode("utf-8-sig")), strict=True)`.
Require the exact documented header set, parse finite floats with row-numbered
errors, require repeated material/source metadata to be identical, convert
`curve_kind` through `SeriesKind`, and call `import_material_rows` with
`SourceKind.CSV`.

- [ ] **Step 4: Add failing XLSX equivalence and formula tests**

Create workbooks in memory with `openpyxl.Workbook`. Use the four exact sheet
names and columns. Assert an equivalent CSV/XLSX pair produces equal `ref` and
`series`. Put `=1+1` in each metadata/data region in parametrized cases and
assert the import is rejected with sheet and cell coordinates.

- [ ] **Step 5: Add the dependency and implement XLSX decoding**

Add `openpyxl>=3.1,<4` to `[project].dependencies`. Load with:

```python
load_workbook(BytesIO(data), read_only=False, data_only=False)
```

Require exactly the four documented visible sheets while permitting a hidden
`_Lists` sheet. Reject formula cells before reading values. Read `Material`
labels by exact key, read table headers by exact name, skip fully blank rows,
map B-H columns to `(x_unit=h_unit, y_unit=b_unit, x=h, y=b)`, map loss columns
to `(x_unit=b_unit, y_unit=loss_unit, x=b, y=loss)`, and call
`import_material_rows` with `SourceKind.SPREADSHEET`.

- [ ] **Step 6: Add failing boundary tests, then make them GREEN**

Cover unsupported extension, invalid UTF-8, malformed CSV, missing/extra
columns, missing sheets, bad enum values, booleans where numbers are expected,
nonfinite numbers, inconsistent metadata, and an empty workbook/table. Errors
must identify filename plus row or sheet/cell.

- [ ] **Step 7: Run Task 2 gates**

Run:

```console
uv sync --python 3.13 --extra dev --extra ui
.venv/bin/python -m pytest tests/unit/adapters/test_material_table_file.py tests/unit/application/test_material_table_import.py -q
.venv/bin/python -m ruff check pyproject.toml src/inductor_designer/adapters/materials tests/unit/adapters/test_material_table_file.py
.venv/bin/python -m mypy src tools
.venv/bin/python tools/check_architecture.py
```

Expected: all exit 0.

- [ ] **Step 8: Commit Task 2**

```console
git add pyproject.toml src/inductor_designer/adapters/materials tests/unit/adapters/test_material_table_file.py
git commit -m "feat(adapters): read CSV and Excel material uploads"
```

---

### Task 3: Downloadable packaged templates

**Files:**
- Create: `src/inductor_designer/resources/__init__.py`
- Create: `src/inductor_designer/resources/material_templates/__init__.py`
- Create: `src/inductor_designer/resources/material_templates/material-import-template.csv`
- Create: `src/inductor_designer/resources/material_templates/material-import-template.xlsx`
- Create: `src/inductor_designer/adapters/materials/templates.py`
- Create: `tests/unit/adapters/test_material_templates.py`

**Interfaces:**

```python
@dataclass(frozen=True, slots=True)
class MaterialTemplateDownload:
    filename: str
    content_type: str
    data: bytes

def material_import_template(file_format: str) -> MaterialTemplateDownload: ...
```

- [ ] **Step 1: Read the spreadsheet authoring instructions before generation**

Read completely:

- the active `spreadsheets:Spreadsheets` skill;
- its `style_guidelines.md`; and
- its `artifact_tool_docs/API_QUICK_START.md`.

Call `codex_app__load_workspace_dependencies` and use only the returned bundled
Node runtime and `@oai/artifact-tool` paths for workbook authoring.

- [ ] **Step 2: Write failing packaged-resource tests**

Assert `material_import_template("csv")` and `("xlsx")` return the exact
filenames/content types, nonempty immutable bytes, and reject other formats.
Open the returned CSV through `import_material_file`. Open the XLSX with
`openpyxl` and assert visible sheets, exact headers, frozen panes, filters,
hidden `_Lists`, and dropdown validations covering populated input rows.

- [ ] **Step 3: Run resource tests and verify RED**

Run: `.venv/bin/python -m pytest tests/unit/adapters/test_material_templates.py -q`

Expected: collection fails because `templates.py` and packaged resources do not
exist.

- [ ] **Step 4: Create the CSV template and resource service**

The CSV header is the exact 16-column schema. Include synthetic rows for one
B-H series in `Oe`/`kG` and two loss series in `kG`/`mW/cm3`, with repeated
material/source metadata. Use `importlib.resources.files` to load bytes and
return:

```python
{"csv": ("material-import-template.csv", "text/csv"),
 "xlsx": ("material-import-template.xlsx",
          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
```

- [ ] **Step 5: Author the XLSX workbook with the artifact workflow**

Create one auditable `.mjs` builder in a temporary/output directory, not in the
package. Produce `Instructions`, `Material`, `B-H Curves`, `Loss Curves`, and
hidden `_Lists`. Apply readable title/header styles, frozen panes, filters,
input fills, number formats, explanatory notes, and data validations:

- B-H `h_unit`: `A/m`, `kA/m`, `Oe`;
- B-H/loss `b_unit`: `T`, `mT`, `G`, `kG`;
- loss `loss_unit`: `W/m3`, `kW/m3`, `mW/cm3`.

Use synthetic examples equivalent to the CSV. Export first under the required
conversation `outputs/<thread-id>/` location, then copy the verified workbook
to the package resource path.

- [ ] **Step 6: Inspect and render every sheet**

Use artifact-tool inspection to verify values and scan formula errors. Render
all four visible sheets and inspect the PNGs. Fix clipped headers, unreadable
instructions, oversized columns, validation ranges, or default blank sheets.
Do not proceed until the workbook is legible and formula-error free.

- [ ] **Step 7: Run template and import equivalence tests GREEN**

Run:

```console
.venv/bin/python -m pytest tests/unit/adapters/test_material_templates.py tests/unit/adapters/test_material_table_file.py -q
.venv/bin/python -m ruff check src/inductor_designer/adapters/materials/templates.py tests/unit/adapters/test_material_templates.py
.venv/bin/python -m mypy src tools
```

Expected: all exit 0.

- [ ] **Step 8: Commit Task 3**

```console
git add src/inductor_designer/resources src/inductor_designer/adapters/materials/templates.py tests/unit/adapters/test_material_templates.py
git commit -m "feat(materials): package CSV and Excel import templates"
```

---

### Task 4: Documentation and end-to-end proof

**Files:**
- Modify: `docs/development/material-records.md`
- Modify: `docs/development/ROADMAP.md`
- Modify: `README.md`
- Create: `tests/integration/test_material_table_upload.py`

**Interfaces:** Uses `material_import_template`, `import_material_file`,
`new_draft_record`, `review_material`, `approve_material`,
`FileOverlayMaterialRepository`, and `reproduce_record` without new production
interfaces.

- [ ] **Step 1: Write a failing end-to-end integration test**

For both template formats, load packaged bytes, import them, build a draft from
the returned series/sources, review and approve it, save all returned source
files to a fresh overlay, reload it, and assert `reproduce_record(...).matches`.
Also assert the CSV and XLSX paths produce equivalent canonical series.

- [ ] **Step 2: Run the integration test and verify RED**

Run: `.venv/bin/python -m pytest tests/integration/test_material_table_upload.py -q`

Expected: FAIL on the first missing or inconsistent end-to-end contract.

- [ ] **Step 3: Make the smallest production/template correction needed**

Fix the boundary revealed by the RED test without adding UI code or bypassing
the existing lifecycle/replay services.

- [ ] **Step 4: Document the exact user workflow**

Add links to both packaged templates, sheet/column tables, supported dropdown
units, the H/B and B/loss column meanings, multiple-series grouping rules,
Excel/CSV equivalence, formula rejection, and a short API example using
`material_import_template` and `import_material_file`. State clearly that M5b
will wire download/upload buttons and revision UI.

Update ROADMAP/README status to say template resources and upload parsers are
implemented while Material Studio UI remains pending.

- [ ] **Step 5: Run focused integration and documentation checks**

Run:

```console
.venv/bin/python -m pytest tests/integration/test_material_table_upload.py tests/unit/adapters/test_material_templates.py tests/unit/adapters/test_material_table_file.py -q
rg -n "material-import-template|A/m|Oe|mW/cm3|M5b" docs/development/material-records.md docs/development/ROADMAP.md README.md
git diff --check
```

Expected: tests and diff check exit 0; searches show the new documentation.

- [ ] **Step 6: Commit Task 4**

```console
git add docs/development/material-records.md docs/development/ROADMAP.md README.md tests/integration/test_material_table_upload.py
git commit -m "docs: explain material template upload workflow"
```

---

### Task 5: Whole-change review, verification, merge, and push

**Files:** Review all changes from base `587a416` to branch HEAD.

- [ ] **Step 1: Request whole-change code review**

Review against the design spec, this plan, `AGENTS.md`, architecture boundaries,
replay/provenance integrity, CSV/XLSX parity, template usability, error messages,
and package-resource behavior. Fix every Critical or Important finding with a
new RED test and focused commit, then re-review.

- [ ] **Step 2: Run fresh final verification**

```console
.venv/bin/python -m pytest tests -q -m "not aedt and not femm" --cov=inductor_designer --cov-report=term-missing
.venv/bin/python -m ruff check .
.venv/bin/python -m mypy src tools
.venv/bin/python tools/check_architecture.py
git diff --check 587a416..HEAD
git status --short --branch
```

Expected: zero failures, coverage at least 80%, all static gates exit 0, and
only the three pre-existing untracked `.DS_Store` files remain.

- [ ] **Step 3: Merge and verify `main`**

Fetch `origin/main`, require it still descends from base `587a416`, fast-forward
`main` to the feature branch, and rerun the non-live suite plus static gates in
the main checkout. Preserve `.DS_Store` files.

- [ ] **Step 4: Push and confirm remote**

Push `main` to `origin`, then confirm `git ls-remote origin refs/heads/main`
equals local HEAD. Do not push generated QA previews or authoring scripts.
