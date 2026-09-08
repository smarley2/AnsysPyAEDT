# User Core Catalog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An installed user can add datasheet cores from a filled template and use them, with imported cores stored where an upgrade cannot delete them.

**Architecture:** One extra `CatalogRepository` implementation that layers a per-user overlay directory over the shipped SQLite index, so every screen and exporter reads more cores through the port they already use. A flat CSV/XLSX table is the entry surface, parsed by a new core-shaped reader, validated against the existing catalog schema, and written as one JSON file per core under `%LOCALAPPDATA%\InductorDesigner\catalog-overlay\cores`.

**Tech Stack:** Python 3.13, PySide6 (QtQml/QtQuick), openpyxl, jsonschema, pytest + pytest-xdist, ruff, mypy strict, `tools.check_architecture`.

## Global Constraints

- English for code, comments, docs, UI copy, logs, branches, commits.
- `domain`, `geometry`, `materials`, `simulation` import no PyAEDT, Qt, SQLite or OS APIs; `application` additionally imports no `inductor_designer.adapters`.
- Never change a physical assumption, schema, catalog value, unit or source reference silently.
- Tests come before the implementation they cover.
- Per task: `.venv/Scripts/python.exe -m pytest -q <that task's test files>`. Final gate: `ruff check .`, `mypy src tools`, `python -m tools.check_architecture`, `pytest -q -n 8 -m "not aedt and not femm"`.
- Never run tests marked `aedt` or `femm`; never start an AEDT session.
- Spec: `docs/superpowers/specs/2026-09-04-user-core-catalog-design.md`.

---

## File Structure

- Create `src/inductor_designer/adapters/catalog/overlay_repository.py` — the layered repository plus the overlay writer.
- Create `src/inductor_designer/adapters/catalog/core_table.py` — template bytes, and CSV/XLSX parsing into `CoreRecord`s with a per-row report.
- Modify `src/inductor_designer/adapters/system/environment.py` — `catalog_overlay_directory()`, `material_overlay_directory()`, and the one-time seed copy.
- Modify `src/inductor_designer/ui/main.py` — build the layered repository; seed the material overlay once.
- Modify `src/inductor_designer/application/services/core_material_selection.py` — `CoreOption` gains `review_status` and `origin`.
- Modify `src/inductor_designer/ui/core_material_controller.py` — the two slots and the import report.
- Modify `src/inductor_designer/ui/qml/CoreMaterialPanel.qml` — two buttons, two dialogs, status/origin on each row.
- Modify `packaging/release_notes.md`, `catalog/README.md` — how a user adds a core.
- Tests: `tests/unit/adapters/catalog/test_overlay_repository.py`, `tests/unit/adapters/catalog/test_core_table.py`, `tests/unit/adapters/system/test_environment.py`, `tests/ui/test_core_material_controller.py`, `tests/ui/test_flow_screens_qml.py`.

---

### Task 1: The per-user overlay locations

**Files:**
- Modify: `src/inductor_designer/adapters/system/environment.py`
- Test: `tests/unit/adapters/system/test_environment.py`

**Interfaces:**
- Produces: `catalog_overlay_directory() -> Path` (`<data>/catalog-overlay`), `user_material_overlay_directory() -> Path` (`<data>/materials-overlay`), and `seed_material_overlay(seed_root: Path) -> bool` (True when it copied).

- [ ] **Step 1: Write the failing tests**

```python
def test_the_overlay_directories_live_beside_logs_and_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Not beside the bundle: an upgrade rewrites the bundle, and the
    uninstaller cannot reach the per-user data directory at all."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert catalog_overlay_directory().parent == application_data_directory()
    assert user_material_overlay_directory().parent == application_data_directory()


def test_the_material_seed_is_copied_once_and_never_over_user_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A second copy would overwrite an imported material with the shipped
    seed -- the one-time guard is the whole safety of this shortcut."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "data"))
    seed = tmp_path / "seed"
    (seed / "Magnetics" / "High_Flux").mkdir(parents=True)
    (seed / "Magnetics" / "High_Flux" / "record.json").write_text("{}", encoding="utf-8")

    assert seed_material_overlay(seed) is True
    copied = user_material_overlay_directory() / "Magnetics" / "High_Flux" / "record.json"
    assert copied.is_file()

    copied.write_text('{"mine": true}', encoding="utf-8")
    assert seed_material_overlay(seed) is False
    assert copied.read_text(encoding="utf-8") == '{"mine": true}'


def test_seeding_tolerates_a_missing_seed_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A source checkout or a stripped bundle has no seed; that is not a
    startup failure."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "data"))
    assert seed_material_overlay(tmp_path / "absent") is False
```

- [ ] **Step 2: Run them and confirm they fail**

Run: `.venv/Scripts/python.exe -m pytest -q tests/unit/adapters/system/test_environment.py`
Expected: `ImportError` for the three new names.

- [ ] **Step 3: Implement**

```python
def catalog_overlay_directory() -> Path:
    return application_data_directory() / "catalog-overlay"


def user_material_overlay_directory() -> Path:
    return application_data_directory() / "materials-overlay"


def seed_material_overlay(seed_root: Path) -> bool:
    """Copy the shipped seed materials into the per-user overlay, once.

    Returns True only when the copy actually ran. The per-user directory
    existing at all is the guard: copying a second time would overwrite a
    material the user imported with the shipped seed.

    ponytail: one-time seeding, not read-both layering. The cost is that a
    later release shipping a CORRECTED seed material never reaches a user who
    already has the copy; the upgrade path, if that ever has to ship, is
    layering the seed read-only under the writable root -- six methods of
    `FileOverlayMaterialRepository`, which is why it is not the first move.
    """
    destination = user_material_overlay_directory()
    if destination.exists() or not seed_root.is_dir():
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(seed_root, destination)
    return True
```

- [ ] **Step 4: Run the tests, expect 3 passed. Then commit.**

```bash
git add src/inductor_designer/adapters/system/environment.py tests/unit/adapters/system/test_environment.py
git commit -m "feat(system): put the user overlays where an upgrade cannot reach them"
```

---

### Task 2: The layered catalog repository and its writer

**Files:**
- Create: `src/inductor_designer/adapters/catalog/overlay_repository.py`
- Test: `tests/unit/adapters/catalog/test_overlay_repository.py`

**Interfaces:**
- Produces:
  - `OverlayCatalogRepository(shipped: CatalogRepository, overlay_root: Path)` satisfying `CatalogRepository`; `list_cores()` returns shipped cores plus non-shadowed overlay cores sorted by part number; `shadowed_part_numbers() -> tuple[str, ...]`.
  - `write_overlay_core(overlay_root: Path, record: CoreRecord) -> Path`.
  - `CoreOverlayError(ValueError)` for a refused write.

- [ ] **Step 1: Write the failing tests**

Cover, one test each: an overlay core appears in `list_cores()` and `get_core()`; conductors still come from the shipped repository unchanged; a part number already shipped is refused by `write_overlay_core` naming it, and the shipped record still reads back unchanged; a file whose part number is later shipped does not win `get_core` and is listed by `shadowed_part_numbers()`; an unparseable overlay file is skipped rather than crashing the whole list (mirroring `FileOverlayMaterialRepository._parse_or_skip`); `write_overlay_core` forces `review_status` to draft.

- [ ] **Step 2: Confirm they fail with `ModuleNotFoundError`.**

- [ ] **Step 3: Implement**

One class, delegating everything it does not own. Cores read through `core_record_from_json`; writes go through `core_record_to_json` with `replace(record, review_status=ReviewStatus.DRAFT, reviewed_by=None)`.

- [ ] **Step 4: Tests pass. Commit.**

```bash
git commit -m "feat(catalog): read user cores from a per-user overlay beside the shipped index"
```

---

### Task 3: The core table — template and import

**Files:**
- Create: `src/inductor_designer/adapters/catalog/core_table.py`
- Test: `tests/unit/adapters/catalog/test_core_table.py`

**Interfaces:**
- Produces:
  - `CORE_TEMPLATE_COLUMNS: tuple[str, ...]` — the schema's field names in schema order, with the `material` object flattened to `materialManufacturer`, `materialName`, `materialGrade`, and each dimension to `<name>NominalM`, `<name>MinM`, `<name>MaxM`.
  - `core_import_template(file_format: str) -> CoreTemplateDownload` (`filename`, `data`), for `"csv"` and `"xlsx"`.
  - `import_core_file(filename: str, data: bytes) -> CoreImportResult` with `records: tuple[CoreRecord, ...]` and `rejections: tuple[CoreRowRejection, ...]` (`row: int`, `reason: str`).

- [ ] **Step 1: Write the failing tests**

One test each: a filled template round-trips to a `CoreRecord` with the exact values typed; a ten-row file with one bad row yields nine records and one rejection naming that row number and the field; a formula cell is rejected rather than evaluated; a missing or reordered header is refused naming the column; a row whose `reviewStatus` says `reviewed` still parses (the demotion happens at write time, Task 2) ; and a value that fails `schemas/catalog/core.v1.schema.json` (e.g. a negative `alValueNh`) is rejected with the validator's message rather than written.

- [ ] **Step 2: Confirm failure. Step 3: Implement.**

CSV via `csv.DictReader`; XLSX via `openpyxl.load_workbook(data_only=False)` so formulas are visible to reject them, mirroring `adapters/materials/table_file.py::_reject_formulas`. Validate each row's assembled mapping with `jsonschema.Draft202012Validator` against the catalog schema, then `core_record_from_json`.

- [ ] **Step 4: Tests pass. Commit.**

```bash
git commit -m "feat(catalog): parse a datasheet core table, one row per part number"
```

---

### Task 4: Review status and origin on every core option

**Files:**
- Modify: `src/inductor_designer/application/services/core_material_selection.py`
- Modify: `src/inductor_designer/ui/core_material_controller.py`
- Test: `tests/unit/application/test_core_material_selection.py`, `tests/ui/test_core_material_controller.py`

**Interfaces:**
- Produces: `CoreOption` with `review_status: ReviewStatus` and `origin: CoreOrigin` (`SHIPPED` / `IMPORTED`); `coreOptions` rows gain `"reviewStatus"` and `"origin"` strings.

- [ ] **Step 1: Write the failing tests** — a shipped draft ferrite core reports `draft`/`shipped`; an overlay core reports `draft`/`imported`; the reviewed powder cores report `reviewed`.
- [ ] **Step 2: Confirm failure. Step 3: Implement** — `core_options` reads `record.review_status`, and asks the repository whether the part number is an overlay one (`isinstance` check against `OverlayCatalogRepository` is NOT how: pass origin in from the repository via a new `overlay_part_numbers()` accessor on the layered repository, so the service stays adapter-free).
- [ ] **Step 4: Tests pass. Commit.**

```bash
git commit -m "feat(ui): say which cores are datasheet-reviewed and which were imported"
```

---

### Task 5: Wire it into the running application

**Files:**
- Modify: `src/inductor_designer/ui/main.py`
- Modify: `src/inductor_designer/ui/core_material_controller.py`
- Test: `tests/ui/test_main_wiring.py`

**Interfaces:**
- Produces: `CoreMaterialController.downloadCoreTemplate(file_format: str, destination_url: str)`, `.importCores(source_url: str)`, and the `coreImportReport` string property.

- [ ] **Step 1: Write the failing test** — a launch imports a two-core file through the controller and both appear in `coreOptions`, with the report naming two imported and zero rejected; the file lands under `application_data_directory()` and nothing is written under the resource root.
- [ ] **Step 2: Confirm failure. Step 3: Implement** — `main()` builds `OverlayCatalogRepository(SqliteCatalogRepository(args.catalog), catalog_overlay_directory())` and calls `seed_material_overlay(resources.material_overlay_directory())` before constructing the material repository against `user_material_overlay_directory()`.
- [ ] **Step 4: Tests pass. Commit.**

```bash
git commit -m "feat(ui): import cores from the Core & Material screen"
```

---

### Task 6: The buttons

**Files:**
- Modify: `src/inductor_designer/ui/qml/CoreMaterialPanel.qml`
- Test: `tests/ui/test_flow_screens_qml.py`

- [ ] **Step 1: Write the failing test** — `coreTemplateButton` and `importCoresButton` exist and are enabled with a controller bound; accepting `importCoresDialog` with a filled file adds the core to the rendered list; each row shows its status.
- [ ] **Step 2: Confirm failure. Step 3: Implement** — two `Button`s and two `FileDialog`s, following `saveProjectAsDialog`'s existing `onAccepted` shape.
- [ ] **Step 4: Tests pass. Commit.**

```bash
git commit -m "feat(ui): add core template and import controls to Core & Material"
```

---

### Task 7: Documentation and the full gate

**Files:**
- Modify: `packaging/release_notes.md`, `catalog/README.md`

- [ ] **Step 1** — release notes gain a section on adding cores: download the template, fill one row per part number, import, and the note that imported cores are `draft` until a reviewer checks them against the cited page. `catalog/README.md` gains the distinction between canonical shipped YAML and a user's per-user overlay.
- [ ] **Step 2: Full gate**

```bash
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m mypy src tools
.venv/Scripts/python.exe -m tools.check_architecture
.venv/Scripts/python.exe -m pytest -q -n 8 -m "not aedt and not femm"
```

- [ ] **Step 3: Walk it in the real application** — launch with no arguments, download a template, fill two cores, import, select one, save the project.
- [ ] **Step 4: Commit.**

---

## Self-Review

- Spec coverage: storage and the materials hazard (Task 1), layered read plus conflict refusal, shadowing and draft demotion (Task 2), template/import/formula rejection/per-row report (Task 3), review status and origin (Task 4), wiring and the write location assertion (Task 5), the surface (Task 6), docs and the walk (Task 7).
- Names are consistent across tasks: `catalog_overlay_directory`, `user_material_overlay_directory`, `seed_material_overlay`, `OverlayCatalogRepository`, `write_overlay_core`, `CORE_TEMPLATE_COLUMNS`, `core_import_template`, `import_core_file`, `CoreImportResult`, `CoreRowRejection`, `downloadCoreTemplate`, `importCores`, `coreImportReport`.
- Task 4 deliberately keeps the origin decision out of `application`: the layered repository exposes `overlay_part_numbers()` rather than the service type-checking an adapter.
