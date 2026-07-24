# Milestone 5a Live Validation Closeout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close M5a by removing unsupported AEDT product paths and producing
reproducible live evidence that one exact real material revision reaches AEDT
2025 R2 Commercial and FEMM.

**Architecture:** Keep generic AEDT release/edition value objects only for
observing and rejecting unsupported environments. Put the single supported
target policy in the application layer, reduce compatibility data and current
schema v4 to AEDT 2025 R2 Commercial, and delete the unused DC fallback.
Prepare a local material-validation Project document through pure application
services, then use tagged adapters and sanitized manifests for live evidence;
never commit source workbook bytes or generated solver artifacts.

**Tech Stack:** Python 3.10–3.13, pytest, jsonschema, PyYAML, PyAEDT 1.2.x,
AEDT 2025 R2 Commercial, pyfemm/FEMM 4.2, PowerShell, Ruff, strict mypy.

## Global Constraints

- Work directly on `main`, as explicitly requested. Do not create or switch to
  a feature branch or worktree.
- Before each task, run `git pull --ff-only origin main`. After each accepted
  task commit, run `git push origin main` so another computer can continue from
  the same state.
- Use English for code, schemas, documentation, UI copy, logs, commits, and
  evidence summaries.
- Support exactly AEDT `2025.2` Commercial. AEDT 2024 R2, Student editions, and
  the magnetostatic-incremental fallback are unsupported.
- Keep `AedtRelease` and `AedtEdition.STUDENT` only where they are needed to
  describe and reject an observed unsupported session. Their presence is not a
  support claim.
- Do not remove historical project schemas v1–v3 in this milestone. Restrict
  only the current v4 schema; M6 owns the clean replacement project schema.
- Do not change `dimensionMode`, `acMagnitudeA`, or AC RMS/peak semantics in
  this milestone. Those are M6 responsibilities.
- Add or update tests before production code and observe each focused test fail.
- Keep domain, geometry, materials, and solver-independent simulation code free
  of PyAEDT, Qt, SQLite, and operating-system APIs.
- Never edit generated catalog indexes. Build them from canonical catalog
  sources.
- Never commit the real workbook, real overlay, generated `.aedt`/`.fem` files,
  raw solver logs, credentials, license details, or personal machine paths.
- Stage files explicitly. Do not stage `.DS_Store`, `materials-overlay/`,
  `outputs/`, or `artifacts/`.
- Existing MCP code is not part of this milestone.

## Starting Evidence and Acceptance Material

The local revision
`Magnetics / High Flux / 60u / f3c2856fbc8b` currently reproduces as `MATCH`.
It is diagnostic evidence only and must not be deleted or modified by this
plan. It cannot satisfy M5a because:

1. its grade `60u` does not equal the canonical catalog identity
   `Magnetics / High Flux / 60`; and
2. it contains one loss series at 100 kHz, so its stored Steinmetz fit is null.

The acceptance workbook must be reimported through the spreadsheet workflow
with:

- manufacturer `Magnetics`;
- material name `High Flux`;
- grade `60`;
- one usable B-H series named `bh-25c`;
- at least two loss-series frequencies;
- at least two positive flux-density values across the loss samples; and
- enough independent positive samples for a non-null Steinmetz fit.

Use reviewed catalog core `C058071A2`. It has the same physical core size as
the existing `0077071A7` sample, so the established two-winding geometry remains
comparable while the selected material identity becomes exactly High Flux 60.

---

### Task 1: Enforce the single supported AEDT target at the application boundary

**Owner:** Implementing agent working directly on `main`.

**Dependencies:** Approved roadmap realignment and the existing generic AEDT
target/capability value objects.

**Acceptance:** Both Maxwell export services reject every target other than
AEDT 2025 R2 Commercial before calling an adapter, and reject capability
evidence for a different environment.

**Allowed files:**

- Create: `src/inductor_designer/application/services/aedt_support.py`
- Create: `tests/unit/application/test_aedt_support.py`
- Modify: `src/inductor_designer/application/services/maxwell_export.py`
- Modify: `tests/unit/application/test_maxwell_export.py`
- Modify: `tests/integration/test_release_matrix.py`

**Interfaces:**

- Produces:
  `SUPPORTED_AEDT_RELEASE: AedtRelease`,
  `SUPPORTED_AEDT_EDITION: AedtEdition`, and
  `aedt_support_issues(release, edition, capabilities=None) -> tuple[str, ...]`.
- Consumes: `CapabilitySnapshot` when an export must prove that capability
  evidence matches the requested environment.
- Preserves: `export_maxwell3d(...)`, `export_maxwell2d(...)`, and
  `export_femm2d(...)` signatures.

- [ ] **Step 1: Write failing policy tests**

Create `tests/unit/application/test_aedt_support.py` with these cases:

```python
from inductor_designer.application.services.aedt_support import (
    SUPPORTED_AEDT_EDITION,
    SUPPORTED_AEDT_RELEASE,
    aedt_support_issues,
)
from inductor_designer.domain.aedt_target import AedtEdition, AedtRelease
from inductor_designer.simulation.capabilities import (
    CapabilityReviewStatus,
    CapabilitySnapshot,
)


def test_supported_target_is_exactly_2025_r2_commercial() -> None:
    assert SUPPORTED_AEDT_RELEASE == AedtRelease(2025, 2)
    assert SUPPORTED_AEDT_EDITION is AedtEdition.COMMERCIAL
    assert aedt_support_issues(
        SUPPORTED_AEDT_RELEASE,
        SUPPORTED_AEDT_EDITION,
    ) == ()


def test_unsupported_release_and_student_edition_are_rejected() -> None:
    assert aedt_support_issues(
        AedtRelease(2024, 2),
        AedtEdition.STUDENT,
    ) == (
        "Only AEDT 2025 R2 Commercial is supported; "
        "requested AEDT 2024.2 student.",
    )


def test_capability_evidence_must_match_the_project_target() -> None:
    capabilities = CapabilitySnapshot(
        release=AedtRelease(2026, 1),
        edition=AedtEdition.COMMERCIAL,
        include_dc_fields_3d=None,
        discovered_limits=(),
        evidence_source="test",
        review_status=CapabilityReviewStatus.UNREVIEWED,
    )
    assert aedt_support_issues(
        AedtRelease(2025, 2),
        AedtEdition.COMMERCIAL,
        capabilities,
    ) == (
        "Capability evidence for AEDT 2026.1 commercial does not match "
        "the requested AEDT 2025.2 commercial environment.",
    )
```

Add service-boundary tests to
`tests/unit/application/test_maxwell_export.py`:

```python
def test_maxwell_export_rejects_unsupported_aedt_target_before_adapter_call(
    tmp_path: Path,
) -> None:
    exporter = RecordingMaxwell3dExporter()
    project = replace(
        three_d_project(),
        target_release=AedtRelease(2024, 2),
    )

    with pytest.raises(MaxwellExportBlocked, match="Only AEDT 2025 R2 Commercial"):
        export_maxwell3d(
            project,
            CATALOG,
            exporter,
            tmp_path,
            capabilities=SNAPSHOT,
        )

    assert exporter.requests == []


def test_maxwell_export_rejects_mismatched_capability_evidence(
    tmp_path: Path,
) -> None:
    mismatched = replace(NATIVE_SNAPSHOT, release=AedtRelease(2026, 1))

    with pytest.raises(MaxwellExportBlocked, match="does not match"):
        export_maxwell3d(
            three_d_project(),
            CATALOG,
            RecordingMaxwell3dExporter(),
            tmp_path,
            capabilities=mismatched,
        )
```

In `tests/integration/test_release_matrix.py`, import `pytest` and
`MaxwellExportBlocked`, then replace the old 2024 fallback-success test with a
failing product-boundary expectation:

```python
def test_product_boundary_rejects_synthetic_2024_target(tmp_path: Path) -> None:
    matrix = tmp_path / "m.yml"
    matrix.write_text(SYNTHETIC, encoding="utf-8")

    with pytest.raises(
        MaxwellExportBlocked,
        match="Only AEDT 2025 R2 Commercial",
    ):
        manifest_3d(matrix, AedtRelease(2024, 2), tmp_path)
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest \
  tests/unit/application/test_aedt_support.py -q

PYTHONPATH=. .venv/bin/python -m pytest \
  tests/unit/application/test_maxwell_export.py \
  tests/integration/test_release_matrix.py -q
```

Expected: the first command fails collection because `aedt_support.py` does
not exist; the second command fails the new boundary expectations because
unsupported targets still reach the exporters.

- [ ] **Step 3: Implement the policy**

Create `src/inductor_designer/application/services/aedt_support.py`:

```python
from __future__ import annotations

from inductor_designer.domain.aedt_target import AedtEdition, AedtRelease
from inductor_designer.simulation.capabilities import CapabilitySnapshot

SUPPORTED_AEDT_RELEASE = AedtRelease(2025, 2)
SUPPORTED_AEDT_EDITION = AedtEdition.COMMERCIAL


def aedt_support_issues(
    release: AedtRelease,
    edition: AedtEdition,
    capabilities: CapabilitySnapshot | None = None,
) -> tuple[str, ...]:
    issues: list[str] = []
    if release != SUPPORTED_AEDT_RELEASE or edition is not SUPPORTED_AEDT_EDITION:
        issues.append(
            "Only AEDT 2025 R2 Commercial is supported; "
            f"requested AEDT {release} {edition.value}."
        )
    if capabilities is not None and (
        capabilities.release != release or capabilities.edition is not edition
    ):
        issues.append(
            f"Capability evidence for AEDT {capabilities.release} "
            f"{capabilities.edition.value} does not match the requested "
            f"AEDT {release} {edition.value} environment."
        )
    return tuple(issues)
```

In `maxwell_export.py`, add a focused helper:

```python
def _require_supported_aedt(
    project: InductorProject,
    capabilities: CapabilitySnapshot,
) -> None:
    issues = aedt_support_issues(
        project.target_release,
        project.target_edition,
        capabilities,
    )
    if issues:
        raise MaxwellExportBlocked(issues)
```

Call `_require_supported_aedt(project, capabilities)` as the first statement in
`export_maxwell3d` and `export_maxwell2d`. Do not call it from `export_femm2d`;
FEMM is not an AEDT environment.

- [ ] **Step 4: Run focused and dependent tests and verify GREEN**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest \
  tests/unit/application/test_aedt_support.py \
  tests/unit/application/test_maxwell_export.py \
  tests/integration/test_release_matrix.py -q
```

Expected: every selected test passes.

- [ ] **Step 5: Commit and publish Task 1**

```bash
git add \
  src/inductor_designer/application/services/aedt_support.py \
  src/inductor_designer/application/services/maxwell_export.py \
  tests/unit/application/test_aedt_support.py \
  tests/unit/application/test_maxwell_export.py \
  tests/integration/test_release_matrix.py
git commit -m "feat(aedt): enforce 2025 R2 Commercial target"
git push origin main
```

---

### Task 2: Delete the unsupported magnetostatic-incremental fallback

**Owner:** Implementing agent working directly on `main`.

**Dependencies:** Task 1.

**Acceptance:** No executable fallback symbol or branch remains, and reviewed
capability evidence without native DC support produces an explicit blocked
decision.

**Allowed files:**

- Modify: `src/inductor_designer/simulation/capabilities.py`
- Modify: `src/inductor_designer/simulation/maxwell_plan.py`
- Modify: `tests/unit/simulation/test_capabilities.py`
- Modify: `tests/unit/simulation/test_plan_builder.py`
- Modify: `tests/integration/test_release_matrix.py`

**Interfaces:**

- `DcBiasStrategy` retains only `NATIVE_INCLUDE_DC_FIELDS` and `BLOCKED`.
- `select_dc_bias_strategy(...)` returns native only for reviewed positive
  capability evidence in 3D; every other case is explicitly blocked.
- `DcBiasDecision.approximate` remains for manifest compatibility but is
  always false in the supported product.

- [ ] **Step 1: Replace fallback expectations with blocking expectations**

In `tests/unit/simulation/test_capabilities.py`, remove the
`MAGNETOSTATIC_INCREMENTAL_FALLBACK` assertion and add:

```python
def test_reviewed_environment_without_native_dc_is_blocked_without_fallback() -> None:
    decision = select_dc_bias_strategy(
        snapshot("2025.2", False),
        ModelDimension.THREE_D,
    )

    assert decision.strategy is DcBiasStrategy.BLOCKED
    assert decision.approximate is False
    assert "no fallback is supported" in decision.reason
```

In `tests/unit/simulation/test_plan_builder.py`, delete `FALLBACK` and its two
tests. Strengthen the blocked test:

```python
def test_blocked_decision_keeps_eddy_current_and_records_reason() -> None:
    plan = build((make_definition(dc_current_a=5.0),), dc_bias_decision=BLOCKED)

    assert plan.solution_type == "EddyCurrent"
    assert any("unreviewed" in note for note in plan.notes)
    assert not any("Magnetostatic" in note for note in plan.notes)
```

In `tests/integration/test_release_matrix.py`, delete the synthetic 2024 row
and the Task 1 negative 2024 product-boundary test. Keep one real-matrix native
test, one synthetic native test, and one 2D-blocked test; Task 1 already owns
the permanent unsupported-target tests.

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest \
  tests/unit/simulation/test_capabilities.py \
  tests/unit/simulation/test_plan_builder.py \
  tests/integration/test_release_matrix.py -q
```

Expected: the new capability expectation fails because the reviewed
non-native branch still selects the fallback.

- [ ] **Step 3: Remove the fallback enum and branches**

Reduce `DcBiasStrategy` to:

```python
class DcBiasStrategy(str, Enum):
    NATIVE_INCLUDE_DC_FIELDS = "native-include-dc-fields"
    BLOCKED = "blocked"
```

Replace the final capability branch with:

```python
return DcBiasDecision(
    DcBiasStrategy.BLOCKED,
    False,
    "Native 3D DC bias is unavailable in this reviewed environment; "
    "no fallback is supported.",
)
```

Delete the fallback branch from `dc_bias_notes`. Do not add another
approximation.

- [ ] **Step 4: Verify no fallback symbol remains in executable code**

Run:

```bash
rg -n \
  "MAGNETOSTATIC_INCREMENTAL_FALLBACK|magnetostatic-incremental-fallback" \
  src tests compatibility tools
```

Expected: no output and exit code 1 from `rg`.

- [ ] **Step 5: Run the focused tests and verify GREEN**

```bash
PYTHONPATH=. .venv/bin/python -m pytest \
  tests/unit/simulation/test_capabilities.py \
  tests/unit/simulation/test_plan_builder.py \
  tests/integration/test_release_matrix.py -q
```

Expected: every selected test passes.

- [ ] **Step 6: Commit and publish Task 2**

```bash
git add \
  src/inductor_designer/simulation/capabilities.py \
  src/inductor_designer/simulation/maxwell_plan.py \
  tests/unit/simulation/test_capabilities.py \
  tests/unit/simulation/test_plan_builder.py \
  tests/integration/test_release_matrix.py
git commit -m "refactor(aedt): remove unsupported DC fallback"
git push origin main
```

---

### Task 3: Collapse current support data, schema v4, and runners to one target

**Owner:** Implementing agent working directly on `main`.

**Dependencies:** Tasks 1 and 2.

**Acceptance:** The current matrix, schema v4, Python spike CLI, and controlled
PowerShell runners expose only AEDT 2025 R2 Commercial while generic adapter
types can still describe an observed unsupported session.

**Allowed files:**

- Modify: `compatibility/aedt-matrix.yml`
- Modify: `schemas/project/v4.schema.json`
- Modify: `tools/aedt_spike.py`
- Modify: `tools/run_aedt_spike.ps1`
- Modify: `tools/run_aedt_maxwell2d.ps1`
- Modify: `tools/run_aedt_maxwell3d.ps1`
- Modify: `tests/unit/adapters/test_matrix_repository.py`
- Modify: `tests/unit/adapters/persistence/test_schema_repository.py`
- Modify: `tests/unit/tools/test_aedt_spike.py`
- Modify: `tests/unit/tools/test_run_aedt_spike_script.py`
- Modify: `tests/contract/test_aedt_gateway_contract.py`

**Interfaces:**

- `compatibility/aedt-matrix.yml` contains exactly one
  `2025.2/commercial` row.
- Current project schema v4 accepts only `aedtRelease: "2025.2"` and
  `edition: "commercial"`.
- Controlled runner arguments remain explicit but accept only the supported
  values.
- Historical schemas v1–v3 and generic observation types remain unchanged.

- [ ] **Step 1: Write failing one-row and v4-schema tests**

Add to `tests/unit/adapters/test_matrix_repository.py`:

```python
import yaml


def test_real_matrix_contains_only_the_supported_environment() -> None:
    data = yaml.safe_load(REAL_MATRIX.read_text(encoding="utf-8"))
    assert [
        (row["release"], row["edition"])
        for row in data["rows"]
    ] == [("2025.2", "commercial")]
```

Add to `tests/unit/adapters/persistence/test_schema_repository.py`:

```python
@pytest.mark.parametrize(
    ("release", "edition"),
    [
        ("2024.2", "commercial"),
        ("2025.2", "student"),
        ("2026.1", "commercial"),
    ],
)
def test_v4_rejects_every_unsupported_aedt_target(
    schema_repository: SchemaRepository,
    release: str,
    edition: str,
) -> None:
    document = schema_repository.migrate_project(_v1_document())
    document["target"]["aedtRelease"] = release
    document["target"]["edition"] = edition

    with pytest.raises(ValidationError):
        schema_repository.validate_project(document)
```

Replace the release-regex tests in
`tests/unit/tools/test_run_aedt_spike_script.py` with:

```python
@pytest.mark.parametrize(
    "filename",
    [
        "run_aedt_spike.ps1",
        "run_aedt_maxwell2d.ps1",
        "run_aedt_maxwell3d.ps1",
    ],
)
def test_controlled_runner_accepts_only_2025_r2_commercial(filename: str) -> None:
    script = (Path("tools") / filename).read_text(encoding="utf-8")
    assert "[ValidateSet('2025.2')]" in script
    assert "[ValidateSet('commercial')]" in script
    assert "student" not in script.casefold()
    assert "2024\\.2" not in script
```

- [ ] **Step 2: Run the focused tests and verify RED**

```bash
PYTHONPATH=. .venv/bin/python -m pytest \
  tests/unit/adapters/test_matrix_repository.py \
  tests/unit/adapters/persistence/test_schema_repository.py \
  tests/unit/tools/test_aedt_spike.py \
  tests/unit/tools/test_run_aedt_spike_script.py -q
```

Expected: one-row, v4 restriction, and runner assertions fail.

- [ ] **Step 3: Reduce the matrix and current schema**

Retain only the reviewed `2025.2/commercial` row in
`compatibility/aedt-matrix.yml`. Preserve its exact observed PyAEDT version,
limits, reviewer, and review date.

In `schemas/project/v4.schema.json`, replace the two target properties with:

```json
"aedtRelease": {"const": "2025.2"},
"edition": {"const": "commercial"},
"dimensionMode": {"enum": ["2d", "3d"]}
```

Do not edit schemas v1–v3.

- [ ] **Step 4: Restrict Python and PowerShell entry points**

In `tools/aedt_spike.py`, import the Task 1 constants and define:

```python
parser.add_argument(
    "--release",
    required=True,
    choices=[str(SUPPORTED_AEDT_RELEASE)],
)
parser.add_argument(
    "--edition",
    required=True,
    choices=[SUPPORTED_AEDT_EDITION.value],
)
```

In each controlled PowerShell runner, replace the release and edition
validators with:

```powershell
[Parameter(Mandatory = $true)]
[ValidateSet('2025.2')]
[string]$Release,

[Parameter(Mandatory = $true)]
[ValidateSet('commercial')]
[string]$Edition,
```

Update `tests/unit/tools/test_aedt_spike.py` and
`tests/contract/test_aedt_gateway_contract.py` product-facing examples to
`2025.2/commercial`. Keep one negative policy test for Student in Task 1; do not
erase the ability to identify an unsupported observed Student session.

- [ ] **Step 5: Run the complete target-policy slice**

```bash
PYTHONPATH=. .venv/bin/python -m pytest \
  tests/unit/application/test_aedt_support.py \
  tests/unit/adapters/test_matrix_repository.py \
  tests/unit/adapters/persistence/test_schema_repository.py \
  tests/unit/tools/test_aedt_spike.py \
  tests/unit/tools/test_run_aedt_spike_script.py \
  tests/contract/test_aedt_gateway_contract.py \
  tests/integration/test_release_matrix.py -q
```

Expected: every selected test passes.

- [ ] **Step 6: Audit product-facing target files**

```bash
rg -n -i \
  "2024\\.2|student|magnetostatic-incremental" \
  compatibility/aedt-matrix.yml \
  schemas/project/v4.schema.json \
  tools/aedt_spike.py \
  tools/run_aedt_spike.ps1 \
  tools/run_aedt_maxwell2d.ps1 \
  tools/run_aedt_maxwell3d.ps1
```

Expected: no output and exit code 1 from `rg`.

- [ ] **Step 7: Commit and publish Task 3**

```bash
git add \
  compatibility/aedt-matrix.yml \
  schemas/project/v4.schema.json \
  tools/aedt_spike.py \
  tools/run_aedt_spike.ps1 \
  tools/run_aedt_maxwell2d.ps1 \
  tools/run_aedt_maxwell3d.ps1 \
  tests/unit/adapters/test_matrix_repository.py \
  tests/unit/adapters/persistence/test_schema_repository.py \
  tests/unit/tools/test_aedt_spike.py \
  tests/unit/tools/test_run_aedt_spike_script.py \
  tests/contract/test_aedt_gateway_contract.py
git commit -m "chore(aedt): narrow compatibility data to 2025 R2"
git push origin main
```

---

### Task 4: Build a reproducible local material-handoff Project document

**Owner:** Implementing agent working directly on `main`.

**Dependencies:** Tasks 1–3, the accepted spreadsheet import/replay services,
and canonical core `C058071A2`.

**Acceptance:** A pure application service and CLI reject mismatched or
non-reproducible material data and produce one deterministic schema-v4
validation Project plus a sanitized preflight manifest for the exact pinned
revision.

**Allowed files:**

- Create:
  `src/inductor_designer/application/services/material_handoff.py`
- Create: `tests/unit/application/test_material_handoff.py`
- Create: `tools/prepare_material_handoff.py`
- Create: `tests/unit/tools/test_prepare_material_handoff.py`

**Interfaces:**

- Produces:
  `prepare_material_handoff(project, catalog, record, sources, *,
  core_part_number, bh_series_id) -> MaterialHandoffPreparation`.
- `MaterialHandoffPreparation` exposes the exact updated Project document,
  source hashes, selected B-H point count, loss frequencies, and material
  revision.
- The CLI writes a schema-v4 Project document and sanitized preflight JSON
  under `artifacts/material-validation/`.
- No raw point values or source bytes enter the preflight JSON.

- [ ] **Step 1: Write failing application-service tests**

Create `tests/unit/application/test_material_handoff.py`. Build all material
fixtures through the same table-import and record-construction services used by
Material Studio. Add these local helpers; do not construct a record and then
mutate its identity, revision, or fit with `dataclasses.replace`:

```python
def _loss(frequency_hz: float, flux_density_t: float) -> float:
    return 2.5 * frequency_hz**1.4 * flux_density_t**2.3


def make_reproducible_material(
    *,
    ref: MaterialRef,
    include_multi_frequency_loss: bool,
) -> tuple[MaterialRecord, dict[str, bytes]]:
    rows = [
        MaterialTableRow(
            "bh-25c",
            SeriesKind.BH_CURVE,
            None,
            25.0,
            None,
            "A/m",
            "T",
            field_strength,
            flux_density,
        )
        for field_strength, flux_density in (
            (0.0, 0.0),
            (100.0, 0.02),
            (250.0, 0.05),
        )
    ]
    frequencies = (
        (10_000.0, 50_000.0)
        if include_multi_frequency_loss
        else (10_000.0,)
    )
    rows.extend(
        MaterialTableRow(
            f"loss-{int(frequency)}hz",
            SeriesKind.LOSS_TABLE,
            frequency,
            25.0,
            None,
            "T",
            "W/m3",
            flux_density,
            _loss(frequency, flux_density),
        )
        for frequency in frequencies
        for flux_density in (0.05, 0.10)
    )
    imported = import_material_rows(
        MaterialTableMetadata(
            ref=ref,
            source_url="https://example.invalid/synthetic-material",
            source_page=1,
            captured_at="2026-07-24T00:00:00+00:00",
            source_description="Synthetic handoff fixture",
        ),
        tuple(rows),
        upload_filename="synthetic-material.xlsx",
        upload_kind=SourceKind.SPREADSHEET,
        upload_bytes=b"synthetic spreadsheet provenance",
    )
    record = new_imported_record(
        imported.ref,
        series=imported.series,
        sources=imported.sources,
        created_at="2026-07-24T00:00:00+00:00",
        notes="Synthetic handoff fixture only.",
    )
    sources = dict(imported.source_files)
    assert reproduce_record(record, sources).matches
    return record, sources


class OneCoreCatalog:
    def __init__(self, core: CoreRecord) -> None:
        self.core = core

    def get_core(self, part_number: str) -> CoreRecord | None:
        return self.core if part_number == self.core.part_number else None

    def list_cores(self) -> tuple[CoreRecord, ...]:
        return (self.core,)

    def get_conductor(self, name: str) -> ConductorRecord | None:
        return None

    def list_conductor_names(self) -> tuple[str, ...]:
        return ()


HIGH_FLUX_REF = MaterialRef("Magnetics", "High Flux", "60")
HIGH_FLUX_CORE = replace(
    make_core(),
    part_number="C058071A2",
    material=HIGH_FLUX_REF,
    review_status=ReviewStatus.REVIEWED,
    reviewed_by="test",
)
HIGH_FLUX_CATALOG = OneCoreCatalog(HIGH_FLUX_CORE)
```

Import each referenced type/function from its existing production module;
import only `make_core` and `make_project` from existing test helpers. Then add
these three scenarios:

```python
def test_handoff_rejects_material_identity_that_does_not_match_core() -> None:
    preparation_record, sources = make_reproducible_material(
        ref=MaterialRef("Magnetics", "High Flux", "60u"),
        include_multi_frequency_loss=True,
    )

    with pytest.raises(MaterialHandoffError, match="does not match"):
        prepare_material_handoff(
            make_project(),
            HIGH_FLUX_CATALOG,
            preparation_record,
            sources,
            core_part_number="C058071A2",
            bh_series_id="bh-25c",
        )


def test_handoff_rejects_record_without_reproducible_core_loss_fit() -> None:
    record, sources = make_reproducible_material(
        ref=MaterialRef("Magnetics", "High Flux", "60"),
        include_multi_frequency_loss=False,
    )

    with pytest.raises(MaterialHandoffError, match="Steinmetz"):
        prepare_material_handoff(
            make_project(),
            HIGH_FLUX_CATALOG,
            record,
            sources,
            core_part_number="C058071A2",
            bh_series_id="bh-25c",
        )


def test_handoff_pins_exact_reproduced_revision_and_supported_target() -> None:
    record, sources = make_reproducible_material(
        ref=MaterialRef("Magnetics", "High Flux", "60"),
        include_multi_frequency_loss=True,
    )

    prepared = prepare_material_handoff(
        make_project(),
        HIGH_FLUX_CATALOG,
        record,
        sources,
        core_part_number="C058071A2",
        bh_series_id="bh-25c",
    )

    assert prepared.project.target_release == AedtRelease(2025, 2)
    assert prepared.project.target_edition is AedtEdition.COMMERCIAL
    assert prepared.project.dimension_mode is ModelDimension.THREE_D
    assert prepared.project.materials[0].revision_id == record.revision_id
    assert prepared.project.materials[0].bh_series_id == "bh-25c"
    assert prepared.bh_point_count > 0
    assert len(prepared.loss_frequencies_hz) >= 2
    assert prepared.source_hashes == tuple(
        (source.filename, source.sha256) for source in record.sources
    )
```

Add a fourth case proving that a validation project cannot inherit unrelated
material state:

```python
def test_handoff_rejects_base_project_with_existing_material_selection() -> None:
    record, sources = make_reproducible_material(
        ref=HIGH_FLUX_REF,
        include_multi_frequency_loss=True,
    )
    base = replace(
        make_project(),
        materials=(
            MaterialRevisionSelection(
                record.ref,
                record.revision_id,
                record,
                "bh-25c",
            ),
        ),
    )

    with pytest.raises(
        MaterialHandoffError,
        match="must not already contain material revisions",
    ):
        prepare_material_handoff(
            base,
            HIGH_FLUX_CATALOG,
            record,
            sources,
            core_part_number="C058071A2",
            bh_series_id="bh-25c",
        )
```

This guarantees the prepared validation Project contains exactly the one
revision under test.

- [ ] **Step 2: Run the service tests and verify RED**

```bash
PYTHONPATH=. .venv/bin/python -m pytest \
  tests/unit/application/test_material_handoff.py -q
```

Expected: collection fails because `material_handoff.py` does not exist.

- [ ] **Step 3: Implement the pure preparation service**

Create a frozen result type and error:

```python
@dataclass(frozen=True, slots=True)
class MaterialHandoffPreparation:
    project: InductorProject
    record: MaterialRecord
    bh_series_id: str
    bh_point_count: int
    loss_frequencies_hz: tuple[float, ...]
    source_hashes: tuple[tuple[str, str], ...]


class MaterialHandoffError(ValueError):
    def __init__(self, issues: tuple[str, ...]) -> None:
        self.issues = issues
        super().__init__("; ".join(issues))
```

Implement `prepare_material_handoff` with this order:

```python
def prepare_material_handoff(
    project: InductorProject,
    catalog: CatalogRepository,
    record: MaterialRecord,
    sources: Mapping[str, bytes],
    *,
    core_part_number: str,
    bh_series_id: str,
) -> MaterialHandoffPreparation:
    issues = list(reproduce_record(record, sources).mismatches)
    if project.materials:
        issues.append(
            "Base validation project must not already contain material revisions."
        )
    core = catalog.get_core(core_part_number)
    if core is None:
        issues.append(f"Core not found in catalog: {core_part_number}")
    elif core.material != record.ref:
        issues.append(
            f"Material {record.ref!r} does not match core material {core.material!r}."
        )

    selected_bh = next(
        (
            series
            for series in record.series
            if series.series_id == bh_series_id
            and series.kind is SeriesKind.BH_CURVE
        ),
        None,
    )
    if selected_bh is None:
        issues.append(f"B-H series {bh_series_id!r} is missing or not a B-H curve.")

    loss_frequencies = tuple(
        sorted(
            {
                frequency
                for series in record.series
                if series.kind is SeriesKind.LOSS_TABLE
                if (frequency := series.conditions.frequency_hz) is not None
            }
        )
    )
    if len(loss_frequencies) < 2 or record.steinmetz is None:
        issues.append(
            "Material handoff requires at least two loss frequencies and "
            "a reproducible Steinmetz fit."
        )
    if issues:
        raise MaterialHandoffError(tuple(issues))

    assert selected_bh is not None
    selected = select_core(project, catalog, core_part_number)
    selected = pin_material_revision(
        selected,
        record,
        bh_series_id=bh_series_id,
    )
    selected = replace(
        selected,
        target_release=SUPPORTED_AEDT_RELEASE,
        target_edition=SUPPORTED_AEDT_EDITION,
        dimension_mode=ModelDimension.THREE_D,
    )
    return MaterialHandoffPreparation(
        project=selected,
        record=record,
        bh_series_id=bh_series_id,
        bh_point_count=len(selected_bh.points),
        loss_frequencies_hz=loss_frequencies,
        source_hashes=tuple(
            (source.filename, source.sha256) for source in record.sources
        ),
    )
```

The assertion after the issue gate exists only to narrow the type for strict
mypy; all user-visible validation remains in the issue collection.

- [ ] **Step 4: Run service tests and verify GREEN**

```bash
PYTHONPATH=. .venv/bin/python -m pytest \
  tests/unit/application/test_material_handoff.py -q
```

Expected: all four scenarios pass.

- [ ] **Step 5: Write failing CLI tests**

Create `tests/unit/tools/test_prepare_material_handoff.py`. Use temporary
catalog and overlay repositories, then call `main(...)`. Assert:

```python
assert exit_code == 0
assert saved_project.exists()
evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
assert evidence["supportedEnvironment"] == {
    "aedtRelease": "2025.2",
    "edition": "commercial",
}
assert evidence["corePartNumber"] == "C058071A2"
assert evidence["material"]["grade"] == "60"
assert evidence["materialRevision"] == record.revision_id
assert evidence["bhSeriesId"] == "bh-25c"
assert evidence["bhPointCount"] == len(bh_series.points)
assert len(evidence["lossFrequenciesHz"]) >= 2
assert evidence["steinmetz"] is not None
assert "points" not in json.dumps(evidence).casefold()
assert str(tmp_path) not in json.dumps(evidence)
```

Add a failure case proving that no project/evidence file survives a preflight
error.

- [ ] **Step 6: Run CLI tests and verify RED**

```bash
PYTHONPATH=. .venv/bin/python -m pytest \
  tests/unit/tools/test_prepare_material_handoff.py -q
```

Expected: collection fails because `tools.prepare_material_handoff` does not
exist.

- [ ] **Step 7: Implement the CLI**

The CLI arguments are:

```python
parser.add_argument("--base-project", required=True, type=Path)
parser.add_argument("--catalog", required=True, type=Path)
parser.add_argument("--schemas", type=Path, default=Path("schemas"))
parser.add_argument("--overlay-root", type=Path, default=Path("materials-overlay"))
parser.add_argument("--manufacturer", required=True)
parser.add_argument("--name", required=True)
parser.add_argument("--grade", required=True)
parser.add_argument("--revision", required=True)
parser.add_argument("--core-part-number", required=True)
parser.add_argument("--bh-series-id", required=True)
parser.add_argument("--output-project", required=True, type=Path)
parser.add_argument("--evidence", required=True, type=Path)
```

`main` must:

1. unlink stale output/evidence files;
2. load the exact record and source bytes from
   `FileOverlayMaterialRepository`;
3. load the base Project document and SQLite catalog;
4. call `prepare_material_handoff`;
5. create the two output parent directories;
6. save the prepared Project document through `ProjectRepository`;
7. write deterministic sanitized JSON containing only identity, hashes, counts,
   frequencies, fit coefficients, and output filename; and
8. print `MATCH` followed by the two output paths and return 0.

The preflight document has this exact shape and uses `sort_keys=True`:

```python
{
    "schemaVersion": 1,
    "supportedEnvironment": {
        "aedtRelease": str(SUPPORTED_AEDT_RELEASE),
        "edition": SUPPORTED_AEDT_EDITION.value,
    },
    "corePartNumber": args.core_part_number,
    "material": {
        "manufacturer": preparation.record.ref.manufacturer,
        "name": preparation.record.ref.name,
        "grade": preparation.record.ref.grade,
    },
    "materialRevision": preparation.record.revision_id,
    "bhSeriesId": preparation.bh_series_id,
    "bhPointCount": preparation.bh_point_count,
    "lossFrequenciesHz": list(preparation.loss_frequencies_hz),
    "steinmetz": {
        "k": fit.k,
        "alpha": fit.alpha,
        "beta": fit.beta,
        "rmsRelativeResidual": fit.rms_relative_residual,
        "maxRelativeResidual": fit.max_relative_residual,
    },
    "sources": [
        {"filename": filename, "sha256": sha256}
        for filename, sha256 in preparation.source_hashes
    ],
    "projectFile": args.output_project.name,
}
```

Assign `fit = preparation.record.steinmetz` and assert it is non-null after the
service returns; the service is the user-visible validation boundary.

Catch `MaterialLookupError`, `MaterialHandoffError`, `OSError`, and
`ValueError`; print `ERROR: ...` to stderr and return 1. Never include source
bytes or absolute paths in the evidence document.

- [ ] **Step 8: Run the complete preflight slice**

```bash
PYTHONPATH=. .venv/bin/python -m pytest \
  tests/unit/application/test_material_handoff.py \
  tests/unit/tools/test_prepare_material_handoff.py \
  tests/integration/test_material_reproducibility.py -q
```

Expected: every selected test passes.

- [ ] **Step 9: Commit and publish Task 4**

```bash
git add \
  src/inductor_designer/application/services/material_handoff.py \
  tests/unit/application/test_material_handoff.py \
  tools/prepare_material_handoff.py \
  tests/unit/tools/test_prepare_material_handoff.py
git commit -m "feat(materials): prepare reproducible solver handoff"
git push origin main
```

---

### Task 5: Add exact live AEDT/FEMM material evidence

**Owner:** Implementing agent working directly on `main`.

**Dependencies:** Tasks 1–4, PyAEDT/AEDT 2025 R2 Commercial, and pyfemm/FEMM
4.2 on the controlled Windows machine.

**Acceptance:** Tagged live tests prove the pinned nonlinear material reaches
Maxwell 3D and reaches the persisted FEMM file point-for-point; a single
PowerShell command performs the controlled run.

**Allowed files:**

- Create: `tools/femm_material_evidence.py`
- Create: `tests/unit/tools/test_femm_material_evidence.py`
- Create: `tests/integration/aedt/test_material_handoff.py`
- Create: `tests/integration/femm/test_material_handoff.py`
- Create: `tools/run_m5a_material_validation.ps1`
- Create: `tests/unit/tools/test_run_m5a_material_validation_script.py`

**Interfaces:**

- Produces:
  `read_material_bh_points(path, material_name) ->
  tuple[tuple[float, float], ...]`, returning persisted `(B, H)` pairs from a
  FEMM block.
- Live tests consume the prepared Project path from
  `INDUCTOR_M5A_PROJECT` and write inspectable output beneath
  `INDUCTOR_M5A_ARTIFACT_ROOT`.
- The PowerShell runner fixes AEDT release/edition, core part, material
  identity, and B-H series while taking only the content-derived revision ID.

- [ ] **Step 1: Write the failing FEMM-file evidence test**

Create `tests/unit/tools/test_femm_material_evidence.py`:

```python
def test_reads_exact_bh_points_for_named_material(tmp_path: Path) -> None:
    fem = tmp_path / "material.fem"
    fem.write_text(
        """\
[BlockProps] = 2
<BeginBlock>
<BlockName> = "Air"
<BHPoints> = 0
<EndBlock>
<BeginBlock>
<BlockName> = "Magnetics_High_Flux_60_rabc123"
<BHPoints> = 3
0 0
0.05 100
0.10 250
<d_lam> = 0
<EndBlock>
""",
        encoding="utf-8",
    )

    assert read_material_bh_points(
        fem,
        "Magnetics_High_Flux_60_rabc123",
    ) == ((0.0, 0.0), (0.05, 100.0), (0.10, 250.0))
```

Add missing-material and malformed-count cases that raise `ValueError` with
the material name.

- [ ] **Step 2: Run the parser tests and verify RED**

```bash
PYTHONPATH=. .venv/bin/python -m pytest \
  tests/unit/tools/test_femm_material_evidence.py -q
```

Expected: collection fails because `tools.femm_material_evidence` does not
exist.

- [ ] **Step 3: Implement the documented FEMM parser**

Use the official FEMM `.fem` block format:

```python
_BLOCK = re.compile(r"<BeginBlock>(.*?)<EndBlock>", re.DOTALL)


def read_material_bh_points(
    path: Path,
    material_name: str,
) -> tuple[tuple[float, float], ...]:
    text = path.read_text(encoding="utf-8", errors="strict")
    block = next(
        (
            body
            for body in _BLOCK.findall(text)
            if re.search(
                rf'<BlockName>\s*=\s*"{re.escape(material_name)}"',
                body,
            )
        ),
        None,
    )
    if block is None:
        raise ValueError(f"FEMM material not found: {material_name}")
    count_match = re.search(r"<BHPoints>\s*=\s*(\d+)", block)
    if count_match is None:
        raise ValueError(f"FEMM material has no BHPoints field: {material_name}")
    count = int(count_match.group(1))
    rows: list[tuple[float, float]] = []
    for line in block[count_match.end() :].splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("<"):
            break
        values = stripped.split()
        if len(values) != 2:
            raise ValueError(f"Malformed FEMM B-H row for {material_name}")
        rows.append((float(values[0]), float(values[1])))
    if len(rows) != count:
        raise ValueError(
            f"FEMM material {material_name} declares {count} B-H points "
            f"but stores {len(rows)}."
        )
    return tuple(rows)
```

Reference the official format specification in the module docstring:
`https://www.femm.info/Archives/contrib/FEMM_file_format.docx`.

- [ ] **Step 4: Run parser tests and verify GREEN**

```bash
PYTHONPATH=. .venv/bin/python -m pytest \
  tests/unit/tools/test_femm_material_evidence.py -q
```

Expected: all parser cases pass.

- [ ] **Step 5: Add tagged live handoff tests**

Both live tests skip when `INDUCTOR_M5A_PROJECT` is absent. Once that variable
is set, a missing `INDUCTOR_M5A_ARTIFACT_ROOT` is a test failure, not a skip.
They build the canonical catalog in their assigned output directory, load the
prepared Project through `ProjectRepository`, and write their generated
manifest beside the solver artifact.

The AEDT test must:

1. skip only when `INDUCTOR_M5A_PROJECT` is absent;
2. fail if `INDUCTOR_AEDT_RELEASE != "2025.2"` or
   `INDUCTOR_AEDT_EDITION != "commercial"`;
3. load the prepared Project document;
4. require exactly one pinned material with a B-H selection and non-null
   Steinmetz fit;
5. run `PyaedtMaxwell3dExporter` into
   `$INDUCTOR_M5A_ARTIFACT_ROOT/aedt`;
6. assert every stage succeeds and `materials`, `validate`, and `save` are
   successful; and
7. assert the manifest revision, B-H series, exact point count, and fit equal
   the pinned snapshot, then save `generation-manifest.json`.

Core assertions:

```python
payload = json.loads(generation_manifest_json(outcome))
selection = project.materials[0]
selected_bh = next(
    series
    for series in selection.snapshot.series
    if series.series_id == selection.bh_series_id
)
assert outcome.result.succeeded()
assert payload["coreMaterial"]["materialRevision"] == selection.revision_id
assert payload["coreMaterial"]["bhSeriesId"] == selection.bh_series_id
assert payload["coreMaterial"]["bhPointCount"] == len(selected_bh.points) > 0
fit = selection.snapshot.steinmetz
assert fit is not None
assert payload["coreMaterial"]["steinmetz"] == {
    "k": fit.k,
    "alpha": fit.alpha,
    "beta": fit.beta,
}
assert {
    stage["name"]
    for stage in payload["stages"]
    if stage["succeeded"]
} >= {"materials", "validate", "save"}
```

The FEMM test must require `INDUCTOR_FEMM_LIVE=1`, run `PyfemmSolver` with
`analyze=False` into `$INDUCTOR_M5A_ARTIFACT_ROOT/femm`, write
`femm-manifest.json`, read the generated file, and compare every persisted
`(B, H)` pair:

```python
expected = outcome.plan.core.material.bh_curve
actual = read_material_bh_points(
    outcome.result.fem_path,
    outcome.plan.core.material.name,
)
assert len(actual) == len(expected) > 0
for actual_pair, expected_pair in zip(actual, expected, strict=True):
    assert actual_pair == pytest.approx(expected_pair)
```

Also assert the FEMM manifest carries the same material revision and B-H series.

- [ ] **Step 6: Write the failing runner contract test**

Create `tests/unit/tools/test_run_m5a_material_validation_script.py`:

```python
def test_runner_fixes_material_and_supported_solver_environment() -> None:
    script = Path("tools/run_m5a_material_validation.ps1").read_text(
        encoding="utf-8"
    )
    for expected in (
        "'2025.2'",
        "'commercial'",
        "'Magnetics'",
        "'High Flux'",
        "'60'",
        "'C058071A2'",
        "'bh-25c'",
        "INDUCTOR_M5A_PROJECT",
        "INDUCTOR_M5A_ARTIFACT_ROOT",
        "INDUCTOR_FEMM_LIVE",
    ):
        assert expected in script
    assert "git add" not in script
    assert "git commit" not in script
```

- [ ] **Step 7: Run the runner test and verify RED**

```bash
PYTHONPATH=. .venv/bin/python -m pytest \
  tests/unit/tools/test_run_m5a_material_validation_script.py -q
```

Expected: the test fails because
`tools/run_m5a_material_validation.ps1` does not exist.

- [ ] **Step 8: Add the controlled PowerShell runner**

`tools/run_m5a_material_validation.ps1` takes one mandatory argument:

```powershell
[Parameter(Mandatory = $true)]
[ValidatePattern('^[0-9a-f]{12}$')]
[string]$Revision
```

It must use these fixed values:

```powershell
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot
$release = '2025.2'
$edition = 'commercial'
$manufacturer = 'Magnetics'
$materialName = 'High Flux'
$grade = '60'
$corePartNumber = 'C058071A2'
$bhSeriesId = 'bh-25c'
$validationRoot = Join-Path $repoRoot 'artifacts\material-validation'
$projectPath = Join-Path $validationRoot 'm5a-high-flux-60.inductor.json'
$evidencePath = Join-Path $validationRoot 'preflight.json'
$liveRoot = Join-Path $validationRoot 'live'
```

The runner must:

1. build `artifacts/catalog/catalog.sqlite`;
2. run `tools.reproduce_material` for the exact revision;
3. run `tools.prepare_material_handoff` with the fixed identity/core/series;
4. remove and recreate only the exact ignored `$liveRoot` directory so stale
   solver output cannot pass inspection;
5. set `INDUCTOR_M5A_PROJECT`, `INDUCTOR_M5A_ARTIFACT_ROOT`,
   `INDUCTOR_AEDT_RELEASE`, `INDUCTOR_AEDT_EDITION`, and
   `INDUCTOR_FEMM_LIVE=1`;
6. run the two tagged live tests with `-vv`; and
7. exit nonzero immediately if any command fails.

Use this exact command flow, with an exit-code check immediately after each
Python process:

```powershell
$python = Join-Path $repoRoot '.venv\Scripts\python.exe'
$catalogPath = Join-Path $repoRoot 'artifacts\catalog\catalog.sqlite'
$baseProject = Join-Path $repoRoot `
  'tests\fixtures\sample_geometry_project.inductor.json'

& $python -m tools.build_catalog --out $catalogPath
if ($LASTEXITCODE -ne 0) { throw 'Catalog build failed.' }

& $python -m tools.reproduce_material `
  --overlay-root (Join-Path $repoRoot 'materials-overlay') `
  --manufacturer $manufacturer `
  --name $materialName `
  --grade $grade `
  --revision $Revision
if ($LASTEXITCODE -ne 0) { throw 'Material reproduction failed.' }

& $python -m tools.prepare_material_handoff `
  --base-project $baseProject `
  --catalog $catalogPath `
  --schemas (Join-Path $repoRoot 'schemas') `
  --overlay-root (Join-Path $repoRoot 'materials-overlay') `
  --manufacturer $manufacturer `
  --name $materialName `
  --grade $grade `
  --revision $Revision `
  --core-part-number $corePartNumber `
  --bh-series-id $bhSeriesId `
  --output-project $projectPath `
  --evidence $evidencePath
if ($LASTEXITCODE -ne 0) { throw 'Material handoff preparation failed.' }

if (Test-Path -LiteralPath $liveRoot) {
  Remove-Item -LiteralPath $liveRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $liveRoot -Force | Out-Null
$env:INDUCTOR_M5A_PROJECT = $projectPath
$env:INDUCTOR_M5A_ARTIFACT_ROOT = $liveRoot
$env:INDUCTOR_AEDT_RELEASE = $release
$env:INDUCTOR_AEDT_EDITION = $edition
$env:INDUCTOR_FEMM_LIVE = '1'

& $python -m pytest `
  tests\integration\aedt\test_material_handoff.py `
  tests\integration\femm\test_material_handoff.py `
  -vv
if ($LASTEXITCODE -ne 0) { throw 'Live material handoff tests failed.' }
```

It must not copy or stage the overlay, workbook, generated project, or evidence.

- [ ] **Step 9: Run all non-live Task 5 tests**

```bash
PYTHONPATH=. .venv/bin/python -m pytest \
  tests/unit/tools/test_femm_material_evidence.py \
  tests/unit/tools/test_run_m5a_material_validation_script.py \
  tests/integration/aedt/test_material_handoff.py \
  tests/integration/femm/test_material_handoff.py \
  -q -m "not aedt and not femm"
```

Expected: parser and runner tests pass; live tests are deselected.

- [ ] **Step 10: Commit and publish Task 5**

```bash
git add \
  tools/femm_material_evidence.py \
  tools/run_m5a_material_validation.ps1 \
  tests/unit/tools/test_femm_material_evidence.py \
  tests/unit/tools/test_run_m5a_material_validation_script.py \
  tests/integration/aedt/test_material_handoff.py \
  tests/integration/femm/test_material_handoff.py
git commit -m "test(materials): add live solver handoff evidence"
git push origin main
```

---

### Task 6: Run the real material handoff and record reviewed evidence

**Owner:** Windows validation operator for the live run; implementing agent for
the sanitized documentation commit.

**Dependencies:** Tasks 1–5, a legally usable source workbook, and access to the
controlled licensed Windows solver machine.

**Acceptance:** Reproduction prints `MATCH`, both tagged live tests pass,
manual AEDT/FEMM inspection passes, and only concrete sanitized evidence is
committed before M5a is marked accepted.

**Allowed files:**

- Create after the live run:
  `docs/development/m5a-live-material-validation.md`
- Modify this plan only to check completed Task 6 steps.

**Interfaces:**

- Consumes the local workbook and content-derived revision ID.
- Produces reviewed, sanitized documentation only.
- Does not produce a committed material record or solver artifact.

- [ ] **Step 1: Prepare and import the acceptance workbook**

On the controlled Windows machine:

```powershell
python -m tools.build_catalog
inductor-designer `
  --project tests\fixtures\sample_geometry_project.inductor.json `
  --catalog artifacts\catalog\catalog.sqlite
```

Use Material Studio to import the workbook described under
`Starting Evidence and Acceptance Material`. Confirm the displayed identity is
exactly `Magnetics — High Flux — 60`, B-H selection is `bh-25c`, at least two
loss frequencies are present, and the imported revision has a non-null
Steinmetz fit. Copy only the displayed 12-character revision ID, then validate
the clipboard value:

```powershell
$env:INDUCTOR_M5A_REVISION = (Get-Clipboard).Trim()
if ($env:INDUCTOR_M5A_REVISION -notmatch '^[0-9a-f]{12}$') {
  throw 'Material Studio revision must be exactly 12 lowercase hexadecimal characters.'
}
```

This shell value is local execution state, not documentation. Do not edit
`record.json` to change `60u` into `60`.

- [ ] **Step 2: Obtain fresh reproduction evidence**

```powershell
python -m tools.reproduce_material `
  --overlay-root materials-overlay `
  --manufacturer "Magnetics" `
  --name "High Flux" `
  --grade "60" `
  --revision $env:INDUCTOR_M5A_REVISION
```

Expected: stdout is exactly `MATCH` and the process exits 0.

- [ ] **Step 3: Run both live handoff tests**

```powershell
.\tools\run_m5a_material_validation.ps1 `
  -Revision $env:INDUCTOR_M5A_REVISION
```

Expected: one AEDT-tagged and one FEMM-tagged material handoff test pass. The
runner writes only ignored files beneath `artifacts/material-validation/`.

- [ ] **Step 4: Manually inspect the generated AEDT project**

Open the generated `.aedt` project and verify all of the following against the
local `preflight.json` and pinned Project snapshot:

```powershell
$expectedMaterial = "Magnetics_High_Flux_60_r$env:INDUCTOR_M5A_REVISION"
```

- exactly one `.aedt` file exists beneath
  `artifacts\material-validation\live\aedt`;
- the core object uses `$expectedMaterial`;
- nonlinear permeability is enabled;
- the B-H table contains exactly `bhPointCount` rows;
- the first and last B-H values match the local source workbook after unit
  conversion;
- power-ferrite core-loss `cm`, `x`, and `y` equal the stored `k`, `alpha`, and
  `beta`;
- the design uses `AC Magnetic with DC`;
- both winding `DC Current` values persist;
- design validation passes; and
- save, close, and reopen produces no repair warning.

Do not copy screenshots or the generated project into Git.

- [ ] **Step 5: Manually inspect the FEMM artifact**

Open the generated `.fem` file and verify:

- exactly one `.fem` file exists beneath
  `artifacts\material-validation\live\femm`;
- `$expectedMaterial` is assigned to the annulus;
- the nonlinear B-H curve is present;
- the displayed B-H point count equals `bhPointCount`; and
- saving/reopening retains the material.

The automated `.fem` parser is the exact point-by-point evidence. The manual
inspection confirms FEMM presents the persisted material correctly.

- [ ] **Step 6: Write the sanitized evidence document**

Create `docs/development/m5a-live-material-validation.md` only after all checks
above pass. Record concrete observed values for:

- review date and reviewer;
- source URL, source filename, SHA-256, capture date, and the decision that
  source bytes are not redistributed;
- material identity, exact revision ID, B-H series, B-H point count, loss
  frequencies, and fit residuals;
- application commit, Python, PyAEDT, AEDT, pyfemm, and FEMM versions;
- preflight `MATCH`;
- AEDT stage results and each manual AEDT check;
- FEMM exact point comparison and each manual FEMM check; and
- ignored artifact filenames without absolute machine paths.

Do not leave unresolved or blank fields and do not copy raw material points.
If any observed value is unavailable, leave M5a open and do not create an
acceptance commit.

- [ ] **Step 7: Review the evidence document before acceptance**

Confirm every required field contains a concrete observation, every live and
manual check says pass, the recorded commit is the code revision that was
tested, and no source points, absolute paths, credentials, or license details
appear. Check completed boxes in this plan through Task 6, but do not mark M5a
accepted yet; Task 7 owns the final quality gate.

- [ ] **Step 8: Verify that only sanitized documentation is staged**

```bash
git status --short
git diff --check
git add \
  docs/development/m5a-live-material-validation.md \
  docs/superpowers/plans/2026-07-24-m5a-live-validation-closeout.md
git diff --cached --name-only
git diff --cached --check
```

Expected: source workbook, overlay, and solver artifacts are untracked or
ignored; the staged-name list contains only the evidence document and this
plan.

- [ ] **Step 9: Commit and publish the live evidence**

```bash
git commit -m "docs: record M5a live material evidence"
git push origin main
```

---

### Task 7: Run full gates and hand off M6 planning

**Owner:** Implementing agent, with the Windows validation operator rerunning
the controlled solver gate.

**Dependencies:** Tasks 1–6 accepted and published.

**Acceptance:** All non-live, UI, static, architecture, and controlled live
gates pass; M5a is then marked accepted; `main` matches `origin/main`; M6
implementation has not begun.

**Allowed files:**

- Modify: `docs/development/material-records.md`
- Modify: `docs/development/ROADMAP.md`
- Modify: `docs/superpowers/plans/README.md`
- Modify: `docs/superpowers/plans/2026-07-24-m5a-live-validation-closeout.md`
- Modify: `README.md`

**Interfaces:**

- Consumes all M5a commits and live evidence.
- Produces a verified `main` state ready for the separately planned M6 Project
  Foundation.

- [ ] **Step 1: Run all non-solver tests**

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests -q -m "not aedt and not femm"
```

Expected: exit 0 with no failures.

- [ ] **Step 2: Run the complete UI suite**

```bash
QT_QPA_PLATFORM=offscreen QSG_RHI_BACKEND=software PYTHONPATH=. \
  .venv/bin/python -m pytest tests -q -m ui
```

Expected: exit 0 with no failures or QML warnings.

- [ ] **Step 3: Run static and architecture gates**

```bash
.venv/bin/python -m ruff check .
.venv/bin/python -m mypy src tools
PYTHONPATH=. .venv/bin/python tools/check_architecture.py
git diff --check
```

Expected: all four commands exit 0.

- [ ] **Step 4: Re-run the controlled material validation**

On the Windows solver machine:

```powershell
$preflight = Get-Content `
  artifacts\material-validation\preflight.json -Raw | ConvertFrom-Json
$revision = [string]$preflight.materialRevision
if ($revision -notmatch '^[0-9a-f]{12}$') {
  throw 'Preflight material revision is invalid.'
}
.\tools\run_m5a_material_validation.ps1 `
  -Revision $revision
```

Expected: both live material handoff tests pass against AEDT 2025 R2 Commercial
and FEMM 4.2.

- [ ] **Step 5: Audit removed support paths**

```bash
rg -n \
  "MAGNETOSTATIC_INCREMENTAL_FALLBACK|magnetostatic-incremental-fallback" \
  src tests compatibility tools
```

Expected: no output.

```bash
rg -n -i \
  "2024\\.2|student" \
  compatibility/aedt-matrix.yml \
  schemas/project/v4.schema.json \
  tools/aedt_spike.py \
  tools/run_aedt_spike.ps1 \
  tools/run_aedt_maxwell2d.ps1 \
  tools/run_aedt_maxwell3d.ps1
```

Expected: no output.

- [ ] **Step 6: Mark M5a accepted only after every gate passes**

After Steps 1–5 pass:

- mark M5a accepted in `docs/development/ROADMAP.md`;
- mark M5a accepted and M6 as next in
  `docs/superpowers/plans/README.md`;
- update `README.md` project status;
- replace the old “before accepting M5a or M5b” wording in
  `docs/development/material-records.md` with the accepted evidence link.

- [ ] **Step 7: Commit, publish, and confirm repository hygiene**

Check every completed box in this plan, including this final acceptance step,
then stage exactly:

```bash
git add \
  docs/development/material-records.md \
  docs/development/ROADMAP.md \
  docs/superpowers/plans/README.md \
  docs/superpowers/plans/2026-07-24-m5a-live-validation-closeout.md \
  README.md
git diff --cached --check
git commit -m "docs: accept M5a live material handoff"
git push origin main
```

```bash
git status --short --branch
git log -7 --oneline --decorate
```

Expected: `main` matches `origin/main`; only pre-existing local
`.DS_Store`, `materials-overlay/`, `outputs/`, or ignored `artifacts/` may
remain outside Git.

**Handoff boundary:** Stop at the M6 design/plan gate.

Do not implement M6 from the roadmap prose. The next worker must use the
approved roadmap realignment and create the detailed M6 Project Foundation
implementation plan before changing its schema or runtime contracts.

---

## Requirement Coverage

| Approved M5a requirement | Plan coverage |
| --- | --- |
| AEDT 2025 R2 Commercial only | Tasks 1 and 3 |
| Remove 2024 R2, Student product paths, and DC fallback | Tasks 1–3 and Task 7 audit |
| Legally usable real material without redistributing unapproved source bytes | Global constraints and Task 6 |
| Reproduction `MATCH` | Tasks 4 and 6 |
| Exact material identity and pinned revision | Task 4 |
| Nonlinear B-H and core-loss model reach AEDT | Tasks 5 and 6 |
| Every B-H point reaches FEMM | Task 5 parser/live test and Task 6 inspection |
| Controlled, sanitized evidence | Tasks 4–6 |
| M5b remains accepted independently | Task 6 documentation update |
| Main is continuously available to another computer | Global constraints and every task commit |

## Self-Review Notes

- The plan intentionally leaves generic release/edition parsing in place so an
  unsupported observed session can be identified and rejected. Product-facing
  policy, schema v4, matrix data, and runners are single-target.
- The project schema, dimensional mode, and AC current convention are not
  redesigned here; that avoids duplicating M6.
- The local `60u` revision is preserved as user data but cannot be mistaken for
  acceptance evidence because the preflight rejects both identity mismatch and
  missing Steinmetz fit.
- Real material bytes remain local. The committed evidence contains hashes,
  counts, conditions, fit summaries, versions, and pass/fail observations only.
- Live AEDT persistence is confirmed by successful adapter stages plus explicit
  human inspection. FEMM persistence is additionally checked point-by-point
  against the documented `.fem` format.
