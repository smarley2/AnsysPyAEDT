# Fair-Rite Ferrite Toroid Catalog Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Import every resolvable Fair-Rite ferrite toroid into the canonical catalog, produce an explicit unresolved-review list, and repair the incomplete KDM MPP import before declaring the supplier catalogs complete.

**Architecture:** Keep supplier extraction isolated in focused tools with deterministic parser tests and saved HTML fixtures. Generated YAML remains canonical catalog data; unresolved Fair-Rite products are documented rather than represented with invented values. Supplier completeness checks fail closed when an expected family is missing.

**Tech Stack:** Python 3.10+, requests, BeautifulSoup, PyYAML, jsonschema, pytest, SQLite catalog builder.

## Global Constraints

- Work only on `agent/import-all-magnetics-powder-toroids`, never directly on `main`.
- Validate parser behavior locally before any GitHub Actions run.
- Do not infer missing nominal dimensions from limit-only values.
- New Fair-Rite and KDM records remain `reviewStatus: draft` and `reviewedBy: null`.
- Preserve SI units and the existing `core.v1.schema.json` shape.
- Record every excluded Fair-Rite part in `docs/catalog/fair-rite-ferrite-unresolved.md`.
- A supplier-family failure must fail the import; it may not silently generate a partial catalog.

---

### Task 1: Repair KDM MPP completeness

**Files:**
- Modify: `tools/scrape_kdm_powder_toroids.py`
- Create: `tests/unit/tools/test_scrape_kdm_powder_toroids.py`
- Test fixture: `tests/fixtures/catalog/kdm-mpp-duplicate-rows.html`
- Regenerate: `catalog/cores/kdm-powder.yaml`

**Interfaces:**
- Produces: `deduplicate_records(records: list[dict[str, object]]) -> list[dict[str, object]]`
- Produces: `require_all_families(summaries: list[dict[str, object]]) -> None`

- [ ] **Step 1: Write failing tests for MPP duplicate rows and missing-family failure**

```python
def test_mpp_duplicate_rows_with_different_pdf_links_are_one_record():
    records = parse_fixture_for_family("KM", "kdm-mpp-duplicate-rows.html")
    assert [r["partNumber"] for r in records].count("KM401-026A") == 1


def test_import_fails_when_any_requested_family_is_missing():
    with pytest.raises(RuntimeError, match="KM"):
        require_all_families([{"code": "KM", "records": 0, "error": "conflict"}])
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `pytest tests/unit/tools/test_scrape_kdm_powder_toroids.py -q`

Expected: failures because duplicate comparison includes `sourceUrl` and no fail-closed family check exists.

- [ ] **Step 3: Implement technical-data deduplication and fail-closed completeness**

Duplicate rows are identical when all fields except `sourceUrl` are equal. Keep the first valid source URL. Raise on any other difference. After processing all families, raise when any summary has an error or zero records.

- [ ] **Step 4: Run focused tests and regenerate KDM locally**

Run:

```bash
pytest tests/unit/tools/test_scrape_kdm_powder_toroids.py -q
python tools/scrape_kdm_powder_toroids.py
python tools/build_catalog.py --out /tmp/catalog.sqlite
```

Expected: all 16 KDM families represented; `KM050-026A`, `KM401-026A`, and `KM400-125A` exist exactly once.

- [ ] **Step 5: Commit the KDM repair**

```bash
git add tools/scrape_kdm_powder_toroids.py tests/unit/tools/test_scrape_kdm_powder_toroids.py tests/fixtures/catalog/kdm-mpp-duplicate-rows.html catalog/cores/kdm-powder.yaml
git commit -m "fix: include KDM MPP toroids"
```

### Task 2: Build deterministic Fair-Rite dimension parsing

**Files:**
- Create: `tools/scrape_fair_rite_ferrite_toroids.py`
- Create: `tests/unit/tools/test_scrape_fair_rite_ferrite_toroids.py`
- Create: `tests/fixtures/catalog/fair-rite-toroids-sample.html`

**Interfaces:**
- Produces: `parse_dimension(text: str) -> PublishedDimension`
- Produces: `parse_category_records(html: str, source_url: str) -> list[RawFairRiteRecord]`

- [ ] **Step 1: Write failing tests for published dimension forms**

Cover:

```text
22.10 ±0.40
03.30 -0.25
75.85 Max
37.60 Min
```

Expected mappings:

- symmetric: nominal/min/max;
- minus-only: nominal, `nominal - tolerance`, `maxM: null`;
- max-only/min-only: no nominal and one explicit limit.

- [ ] **Step 2: Verify RED**

Run: `pytest tests/unit/tools/test_scrape_fair_rite_ferrite_toroids.py -q`

- [ ] **Step 3: Implement the minimal parser**

Use decimal-safe parsing and convert millimeters to meters only when constructing catalog records. Reject malformed values with a descriptive exception containing the source text.

- [ ] **Step 4: Add category-row tests**

The fixture must include one uncoated nominal part, one coated limit-only part, one negative-only tolerance part, and magnetic fields `AL`, `Ae`, `le`, and `Ve`.

- [ ] **Step 5: Run tests and commit**

```bash
pytest tests/unit/tools/test_scrape_fair_rite_ferrite_toroids.py -q
git add tools/scrape_fair_rite_ferrite_toroids.py tests/unit/tools/test_scrape_fair_rite_ferrite_toroids.py tests/fixtures/catalog/fair-rite-toroids-sample.html
git commit -m "test: define Fair-Rite toroid parsing"
```

### Task 3: Resolve coated/uncoated pairs and unresolved records

**Files:**
- Modify: `tools/scrape_fair_rite_ferrite_toroids.py`
- Modify: `tests/unit/tools/test_scrape_fair_rite_ferrite_toroids.py`
- Create: `docs/catalog/fair-rite-ferrite-unresolved.md`

**Interfaces:**
- Produces: `resolve_records(raw: list[RawFairRiteRecord]) -> ResolutionResult`
- `ResolutionResult` contains `records` and `unresolved`.

- [ ] **Step 1: Write failing tests for unambiguous and ambiguous pairing**

An unambiguous pair must share material, `Ae`, `le`, `Ve`, `AL`, and published product relationship. Similar dimensions alone must not qualify.

- [ ] **Step 2: Verify RED**

Run the two pairing tests directly with `pytest ...::test_name -q`.

- [ ] **Step 3: Implement resolution**

For a resolved coated part, use uncoated nominal dimensions and coated OD max, ID min, and height max. Exclude ambiguous parts and create an unresolved entry with exact reason and review action.

- [ ] **Step 4: Test unresolved Markdown rendering**

Assert each row includes part number, material, URL, available dimensions, reason, attempted match, and recommended action.

- [ ] **Step 5: Commit**

```bash
git add tools/scrape_fair_rite_ferrite_toroids.py tests/unit/tools/test_scrape_fair_rite_ferrite_toroids.py docs/catalog/fair-rite-ferrite-unresolved.md
git commit -m "feat: resolve Fair-Rite coated toroids"
```

### Task 4: Extract and generate the Fair-Rite catalog

**Files:**
- Modify: `tools/scrape_fair_rite_ferrite_toroids.py`
- Create: `catalog/cores/fair-rite-ferrite.yaml`
- Update: `docs/catalog/fair-rite-ferrite-unresolved.md`

**Interfaces:**
- CLI: `python tools/scrape_fair_rite_ferrite_toroids.py`
- Outputs canonical YAML and unresolved Markdown atomically.

- [ ] **Step 1: Add failing integration tests using saved category HTML**

Assert unique part numbers, all imported records have required magnetic parameters, all are `ferrite-toroid`, and unresolved products do not appear in YAML.

- [ ] **Step 2: Implement category discovery and product-page enrichment**

Parse the full category table as the authoritative dimensional/magnetic source. Fetch product pages only for finish/coating and explicit pairing evidence. Retry transient requests, but report inaccessible pages as unresolved.

- [ ] **Step 3: Run the extractor locally against Fair-Rite**

```bash
python tools/scrape_fair_rite_ferrite_toroids.py
```

Expected: nonzero YAML records and a deterministic unresolved list.

- [ ] **Step 4: Validate generated outputs locally**

```bash
python tools/build_catalog.py --out /tmp/catalog.sqlite
pytest tests/unit/tools/test_scrape_fair_rite_ferrite_toroids.py -q
```

- [ ] **Step 5: Commit generated data**

```bash
git add catalog/cores/fair-rite-ferrite.yaml docs/catalog/fair-rite-ferrite-unresolved.md tools/scrape_fair_rite_ferrite_toroids.py
git commit -m "data: import Fair-Rite ferrite toroids"
```

### Task 5: Catalog-level regression and final verification

**Files:**
- Modify: `tests/unit/adapters/catalog/test_sqlite_repository.py`
- Update: PR description and supplier design documentation as needed.

**Interfaces:**
- Produces catalog-wide assertions for supplier counts, uniqueness, materials, dimension semantics, and representative records.

- [ ] **Step 1: Write failing catalog assertions**

Add representative Fair-Rite records for symmetric tolerance, negative-only tolerance, and resolved coated limits. Add explicit KDM MPP assertions.

- [ ] **Step 2: Run focused catalog tests**

```bash
pytest tests/unit/adapters/catalog/test_sqlite_repository.py -q
```

- [ ] **Step 3: Run complete local verification**

```bash
python -m compileall tools src tests
ruff check .
mypy src tools
pytest -q
python tools/build_catalog.py --out /tmp/catalog.sqlite
```

Expected: all commands pass, zero duplicate part numbers, and no generated SQLite file in the diff.

- [ ] **Step 4: Inspect final diff**

Confirm no temporary workflow, downloaded HTML, PDF, logs, credentials, or artifacts are committed.

- [ ] **Step 5: Commit and update draft PR #2**

Update the PR with KDM MPP count, Fair-Rite imported count/materials, unresolved count, local validation evidence, and the unresolved-review path.
