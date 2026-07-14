# Milestone 1: Toroid Domain and Catalogs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A versioned project document selects a commercial Magnetics toroid, defines multiple declaratively valid round-wire windings, and survives schema round trips, backed by a canonical-files-to-SQLite catalog pipeline.

**Architecture:** Pure-Python frozen dataclasses in `domain`/`materials` hold SI-canonical values; a schema-versioned v2 project document with a v1→v2 migration lives behind the existing `SchemaRepository`; canonical YAML/CSV catalog files compile through a build tool into a gitignored SQLite index that the application reads only through a `CatalogRepository` port implemented by a `sqlite3` adapter.

**Tech Stack:** Python 3.10–3.13, stdlib `sqlite3`, `jsonschema` (runtime), `PyYAML` (tools/tests only), pytest, mypy strict, Ruff.

## Global Constraints

- Python `>=3.10,<3.14`; mypy `strict = true`; Ruff line length 100 with `E,F,I,B,UP,ANN,SIM`.
- Branch-aware coverage `fail_under = 80` must hold after every task.
- Inner modules (`domain`, `geometry`, `materials`, `simulation`, `application`) never import PyAEDT, Qt, `sqlite3`, or OS-specific APIs; run `python tools/check_architecture.py` after each task that adds inner-module code.
- No new runtime dependencies. `PyYAML` stays in the `dev` extra and is imported only from `tools/` and `tests/`.
- Canonical units: lengths in meters (`*M` JSON suffix), angles in degrees (`*Deg`), current in amperes (`*A`), frequency in hertz (`*Hz`), AL value in nanohenry per turn squared (`alValueNh`). Canonical catalog YAML uses the same camelCase field names and units as the JSON schemas.
- Every file uses `from __future__ import annotations`. Dataclasses are `frozen=True, slots=True` following `src/inductor_designer/simulation/capabilities.py`.
- All text in English. Conventional commits.
- Catalog data transcribed in this plan carries `reviewStatus: draft`. Draft numeric values MUST NOT be treated as verified; flipping to `reviewed` is a human step against the linked Magnetics catalog sources and is NOT part of this plan's automated tasks.
- Verification commands available in every task: `python -m pytest tests/unit -q`, `python -m ruff check .`, `python -m mypy`, `python tools/check_architecture.py`.

---

### Task 1: Move AEDT target types into the domain

The project aggregate needs `AedtRelease`, `AedtEdition`, and `ModelDimension`. They currently live in `simulation/capabilities.py`, which would force `domain` to import `simulation`. These are domain vocabulary; move them and re-export for compatibility.

**Files:**
- Create: `src/inductor_designer/domain/aedt_target.py`
- Modify: `src/inductor_designer/simulation/capabilities.py`
- Test: `tests/unit/domain/test_aedt_target.py`, `tests/unit/domain/__init__.py`

**Interfaces:**
- Produces: `inductor_designer.domain.aedt_target.AedtRelease` (frozen dataclass, `parse(str)`, `__str__`), `AedtEdition` (str Enum `COMMERCIAL/STUDENT`), `ModelDimension` (str Enum `TWO_D/THREE_D`). Same classes remain importable from `inductor_designer.simulation.capabilities`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/domain/__init__.py` (empty) and `tests/unit/domain/test_aedt_target.py`:

```python
from __future__ import annotations

from inductor_designer.domain.aedt_target import AedtEdition, AedtRelease, ModelDimension


def test_release_parse_round_trip() -> None:
    release = AedtRelease.parse("2025.2")
    assert release == AedtRelease(2025, 2)
    assert str(release) == "2025.2"


def test_domain_and_simulation_expose_the_same_types() -> None:
    from inductor_designer.simulation import capabilities

    assert capabilities.AedtRelease is AedtRelease
    assert capabilities.AedtEdition is AedtEdition
    assert capabilities.ModelDimension is ModelDimension
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/domain/test_aedt_target.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'inductor_designer.domain.aedt_target'`

- [ ] **Step 3: Move the types**

Create `src/inductor_designer/domain/aedt_target.py` containing `AedtRelease`, `AedtEdition`, and `ModelDimension` moved verbatim from `simulation/capabilities.py` (lines 1–46 of the current file: the imports they need, `AedtRelease` with its `__post_init__`, `parse`, `__str__`, and the two enums).

In `src/inductor_designer/simulation/capabilities.py`, delete those three definitions and replace with a re-export so existing imports keep working:

```python
from inductor_designer.domain.aedt_target import AedtEdition, AedtRelease, ModelDimension

__all__ = [
    "AedtEdition",
    "AedtRelease",
    "CapabilityReviewStatus",
    "CapabilitySnapshot",
    "DcBiasDecision",
    "DcBiasStrategy",
    "ModelDimension",
    "select_dc_bias_strategy",
]
```

Keep the remaining `capabilities.py` content unchanged.

- [ ] **Step 4: Run the full unit suite and gates**

Run: `python -m pytest tests/unit -q && python -m ruff check . && python -m mypy && python tools/check_architecture.py`
Expected: all pass; existing `tests/unit/simulation/test_capabilities.py` still green via the re-export.

- [ ] **Step 5: Commit**

```bash
git add src/inductor_designer/domain/aedt_target.py src/inductor_designer/simulation/capabilities.py tests/unit/domain
git commit -m "refactor(domain): move AEDT target types into domain vocabulary"
```

---

### Task 2: Domain units module

SI floats live in the domain; this module is the single conversion boundary (Q1 decision A).

**Files:**
- Create: `src/inductor_designer/domain/units.py`
- Test: `tests/unit/domain/test_units.py`

**Interfaces:**
- Produces: `to_canonical(value: float, unit: str) -> float` (converts to the canonical unit of the unit's dimension; raises `ValueError` on unknown unit or non-finite value), `awg_bare_diameter_m(gauge: int) -> float` (raises `ValueError` outside 1–40).

- [ ] **Step 1: Write the failing test**

Create `tests/unit/domain/test_units.py`:

```python
from __future__ import annotations

import math

import pytest

from inductor_designer.domain.units import awg_bare_diameter_m, to_canonical


@pytest.mark.parametrize(
    ("value", "unit", "expected"),
    [
        (1.0, "m", 1.0),
        (25.4, "mm", 0.0254),
        (2.0, "cm", 0.02),
        (500.0, "um", 0.0005),
        (1.5, "A", 1.5),
        (250.0, "mA", 0.25),
        (100.0, "kHz", 100_000.0),
        (1.0, "MHz", 1_000_000.0),
        (90.0, "deg", 90.0),
    ],
)
def test_to_canonical(value: float, unit: str, expected: float) -> None:
    assert to_canonical(value, unit) == pytest.approx(expected)


def test_to_canonical_rejects_unknown_unit() -> None:
    with pytest.raises(ValueError, match="Unknown unit"):
        to_canonical(1.0, "furlong")


def test_to_canonical_rejects_non_finite() -> None:
    with pytest.raises(ValueError, match="finite"):
        to_canonical(math.nan, "mm")


def test_awg_formula() -> None:
    assert awg_bare_diameter_m(36) == pytest.approx(0.000127, rel=1e-6)
    assert awg_bare_diameter_m(18) == pytest.approx(0.00102362, rel=1e-3)


def test_awg_rejects_out_of_range() -> None:
    with pytest.raises(ValueError, match="AWG gauge"):
        awg_bare_diameter_m(0)
    with pytest.raises(ValueError, match="AWG gauge"):
        awg_bare_diameter_m(41)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/domain/test_units.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

Create `src/inductor_designer/domain/units.py`:

```python
from __future__ import annotations

import math

_CONVERSIONS: dict[str, float] = {
    # length -> meters
    "m": 1.0,
    "mm": 1e-3,
    "cm": 1e-2,
    "um": 1e-6,
    # current -> amperes
    "A": 1.0,
    "mA": 1e-3,
    # frequency -> hertz
    "Hz": 1.0,
    "kHz": 1e3,
    "MHz": 1e6,
    # angle -> degrees (canonical angle unit is the degree)
    "deg": 1.0,
}


def to_canonical(value: float, unit: str) -> float:
    """Convert a value to the canonical unit of its dimension (m, A, Hz, deg)."""
    factor = _CONVERSIONS.get(unit)
    if factor is None:
        raise ValueError(f"Unknown unit: {unit!r}")
    if not math.isfinite(value):
        raise ValueError(f"Value must be finite, got {value!r}")
    return value * factor


def awg_bare_diameter_m(gauge: int) -> float:
    """Bare copper diameter for an AWG gauge: d = 0.127 mm * 92**((36 - n) / 39)."""
    if type(gauge) is not int or not 1 <= gauge <= 40:
        raise ValueError(f"AWG gauge must be an integer in [1, 40], got {gauge!r}")
    return 0.000127 * 92.0 ** ((36 - gauge) / 39)
```

- [ ] **Step 4: Run tests and gates**

Run: `python -m pytest tests/unit/domain -q && python -m ruff check . && python -m mypy && python tools/check_architecture.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/inductor_designer/domain/units.py tests/unit/domain/test_units.py
git commit -m "feat(domain): add canonical unit conversions and AWG formula"
```

---

### Task 3: Material identity and catalog record types

Material is identity-only in M1 (Q8 decision A). Core and conductor records are frozen domain types with hard structural invariants.

**Files:**
- Create: `src/inductor_designer/materials/identity.py`
- Create: `src/inductor_designer/domain/catalog_records.py`
- Test: `tests/unit/domain/test_catalog_records.py`, `tests/unit/materials/__init__.py`, `tests/unit/materials/test_identity.py`

**Interfaces:**
- Produces:
  - `materials.identity.MaterialRef(manufacturer: str, name: str, grade: str)` — frozen; all fields non-empty.
  - `domain.catalog_records.ReviewStatus` (str Enum: `DRAFT = "draft"`, `REVIEWED = "reviewed"`).
  - `domain.catalog_records.Dimension(nominal_m: float, min_m: float | None, max_m: float | None)` — frozen; `nominal_m > 0`; when present, `min_m <= nominal_m <= max_m`.
  - `domain.catalog_records.CoreFamily` (str Enum: `POWDER_TOROID = "powder-toroid"`, `FERRITE_TOROID = "ferrite-toroid"`).
  - `domain.catalog_records.CoreRecord(manufacturer: str, family: CoreFamily, part_number: str, material: MaterialRef, coating: str, catalog_revision: str, source_url: str, source_page: int, outer_diameter: Dimension, inner_diameter: Dimension, height: Dimension, effective_area_m2: float, path_length_m: float, volume_m3: float, al_value_nh: float, review_status: ReviewStatus, reviewed_by: str | None)` — frozen; positive effective values; `inner_diameter.nominal_m < outer_diameter.nominal_m`; `source_page >= 1`; non-empty identity strings.
  - `domain.catalog_records.ConductorStandard` (str Enum: `AWG = "awg"`, `IEC_60317 = "iec-60317"`).
  - `domain.catalog_records.ConductorRecord(name: str, standard: ConductorStandard, bare_diameter_m: float, grade1_diameter_m: float | None, grade2_diameter_m: float | None, source: str, catalog_revision: str, review_status: ReviewStatus, reviewed_by: str | None)` — frozen; `bare_diameter_m > 0`; insulated diameters, when present, strictly greater than bare.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/materials/__init__.py` (empty) and `tests/unit/materials/test_identity.py`:

```python
from __future__ import annotations

import pytest

from inductor_designer.materials.identity import MaterialRef


def test_material_ref_holds_identity() -> None:
    ref = MaterialRef(manufacturer="Magnetics", name="Kool Mu", grade="60")
    assert ref.grade == "60"


@pytest.mark.parametrize("field", ["manufacturer", "name", "grade"])
def test_material_ref_rejects_blank_fields(field: str) -> None:
    values = {"manufacturer": "Magnetics", "name": "Kool Mu", "grade": "60"}
    values[field] = "  "
    with pytest.raises(ValueError, match=field):
        MaterialRef(**values)
```

Create `tests/unit/domain/test_catalog_records.py`:

```python
from __future__ import annotations

import pytest

from inductor_designer.domain.catalog_records import (
    ConductorRecord,
    ConductorStandard,
    CoreFamily,
    CoreRecord,
    Dimension,
    ReviewStatus,
)
from inductor_designer.materials.identity import MaterialRef


def make_core(**overrides: object) -> CoreRecord:
    values: dict[str, object] = {
        "manufacturer": "Magnetics",
        "family": CoreFamily.POWDER_TOROID,
        "part_number": "0077071A7",
        "material": MaterialRef("Magnetics", "Kool Mu", "60"),
        "coating": "black epoxy",
        "catalog_revision": "powder-core-2024",
        "source_url": "https://www.mag-inc.com/example",
        "source_page": 10,
        "outer_diameter": Dimension(0.02692, 0.0264, 0.0274),
        "inner_diameter": Dimension(0.01473, 0.0144, 0.0151),
        "height": Dimension(0.01118, 0.0109, 0.0115),
        "effective_area_m2": 65.4e-6,
        "path_length_m": 0.0635,
        "volume_m3": 4.15e-6,
        "al_value_nh": 61.0,
        "review_status": ReviewStatus.DRAFT,
        "reviewed_by": None,
    }
    values.update(overrides)
    return CoreRecord(**values)  # type: ignore[arg-type]


def test_core_record_valid() -> None:
    core = make_core()
    assert core.part_number == "0077071A7"


def test_dimension_rejects_inverted_bounds() -> None:
    with pytest.raises(ValueError, match="min_m <= nominal_m <= max_m"):
        Dimension(0.02, 0.021, 0.022)


def test_dimension_rejects_non_positive_nominal() -> None:
    with pytest.raises(ValueError, match="nominal_m"):
        Dimension(0.0, None, None)


def test_core_rejects_inner_not_smaller_than_outer() -> None:
    with pytest.raises(ValueError, match="inner_diameter"):
        make_core(inner_diameter=Dimension(0.03, None, None))


def test_core_rejects_non_positive_effective_values() -> None:
    with pytest.raises(ValueError, match="effective_area_m2"):
        make_core(effective_area_m2=0.0)


def test_conductor_record_valid() -> None:
    wire = ConductorRecord(
        name="AWG 18",
        standard=ConductorStandard.AWG,
        bare_diameter_m=0.00102362,
        grade1_diameter_m=None,
        grade2_diameter_m=None,
        source="ASTM B258 formula",
        catalog_revision="round-wire-1",
        review_status=ReviewStatus.DRAFT,
        reviewed_by=None,
    )
    assert wire.standard is ConductorStandard.AWG


def test_conductor_rejects_insulation_not_larger_than_bare() -> None:
    with pytest.raises(ValueError, match="grade1_diameter_m"):
        ConductorRecord(
            name="AWG 18",
            standard=ConductorStandard.AWG,
            bare_diameter_m=0.001,
            grade1_diameter_m=0.001,
            grade2_diameter_m=None,
            source="test",
            catalog_revision="round-wire-1",
            review_status=ReviewStatus.DRAFT,
            reviewed_by=None,
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/domain/test_catalog_records.py tests/unit/materials -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

Create `src/inductor_designer/materials/identity.py`:

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MaterialRef:
    """Identity-only reference to a magnetic material; property data arrives in Milestone 5."""

    manufacturer: str
    name: str
    grade: str

    def __post_init__(self) -> None:
        for field_name in ("manufacturer", "name", "grade"):
            if not getattr(self, field_name).strip():
                raise ValueError(f"MaterialRef {field_name} cannot be blank")
```

Create `src/inductor_designer/domain/catalog_records.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from inductor_designer.materials.identity import MaterialRef


class ReviewStatus(str, Enum):
    DRAFT = "draft"
    REVIEWED = "reviewed"


class CoreFamily(str, Enum):
    POWDER_TOROID = "powder-toroid"
    FERRITE_TOROID = "ferrite-toroid"


class ConductorStandard(str, Enum):
    AWG = "awg"
    IEC_60317 = "iec-60317"


@dataclass(frozen=True, slots=True)
class Dimension:
    """A nominal dimension in meters with optional tolerance bounds."""

    nominal_m: float
    min_m: float | None
    max_m: float | None

    def __post_init__(self) -> None:
        if not self.nominal_m > 0:
            raise ValueError(f"Dimension nominal_m must be positive, got {self.nominal_m!r}")
        low = self.min_m if self.min_m is not None else self.nominal_m
        high = self.max_m if self.max_m is not None else self.nominal_m
        if not low <= self.nominal_m <= high:
            raise ValueError("Dimension requires min_m <= nominal_m <= max_m")


@dataclass(frozen=True, slots=True)
class CoreRecord:
    manufacturer: str
    family: CoreFamily
    part_number: str
    material: MaterialRef
    coating: str
    catalog_revision: str
    source_url: str
    source_page: int
    outer_diameter: Dimension
    inner_diameter: Dimension
    height: Dimension
    effective_area_m2: float
    path_length_m: float
    volume_m3: float
    al_value_nh: float
    review_status: ReviewStatus
    reviewed_by: str | None

    def __post_init__(self) -> None:
        for field_name in ("manufacturer", "part_number", "catalog_revision", "source_url"):
            if not getattr(self, field_name).strip():
                raise ValueError(f"CoreRecord {field_name} cannot be blank")
        if self.source_page < 1:
            raise ValueError(f"CoreRecord source_page must be >= 1, got {self.source_page!r}")
        if self.inner_diameter.nominal_m >= self.outer_diameter.nominal_m:
            raise ValueError("CoreRecord inner_diameter must be smaller than outer_diameter")
        for field_name in ("effective_area_m2", "path_length_m", "volume_m3", "al_value_nh"):
            if not getattr(self, field_name) > 0:
                raise ValueError(f"CoreRecord {field_name} must be positive")


@dataclass(frozen=True, slots=True)
class ConductorRecord:
    name: str
    standard: ConductorStandard
    bare_diameter_m: float
    grade1_diameter_m: float | None
    grade2_diameter_m: float | None
    source: str
    catalog_revision: str
    review_status: ReviewStatus
    reviewed_by: str | None

    def __post_init__(self) -> None:
        for field_name in ("name", "source", "catalog_revision"):
            if not getattr(self, field_name).strip():
                raise ValueError(f"ConductorRecord {field_name} cannot be blank")
        if not self.bare_diameter_m > 0:
            raise ValueError("ConductorRecord bare_diameter_m must be positive")
        for field_name in ("grade1_diameter_m", "grade2_diameter_m"):
            value: float | None = getattr(self, field_name)
            if value is not None and value <= self.bare_diameter_m:
                raise ValueError(
                    f"ConductorRecord {field_name} must exceed bare_diameter_m when present"
                )
```

- [ ] **Step 4: Run tests and gates**

Run: `python -m pytest tests/unit -q && python -m ruff check . && python -m mypy && python tools/check_architecture.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/inductor_designer/materials/identity.py src/inductor_designer/domain/catalog_records.py tests/unit/materials tests/unit/domain/test_catalog_records.py
git commit -m "feat(domain): add material identity and catalog record types"
```

---

### Task 4: Winding definition, core selection, and project aggregate

**Files:**
- Create: `src/inductor_designer/domain/winding.py`
- Create: `src/inductor_designer/domain/project.py`
- Test: `tests/unit/domain/test_project.py`

**Interfaces:**
- Consumes: `CoreRecord`, `AedtRelease`, `AedtEdition`, `ModelDimension` from Tasks 1 and 3.
- Produces:
  - `domain.winding.ConductorMode` (str Enum: `SOLID = "solid"`, `STRANDED = "stranded"`).
  - `domain.winding.WindingDirection` (str Enum: `CLOCKWISE = "cw"`, `COUNTERCLOCKWISE = "ccw"`).
  - `domain.winding.CurrentDirection` (str Enum: `FORWARD = "forward"`, `REVERSE = "reverse"`).
  - `domain.winding.WindingDefinition(winding_id: str, label: str, turns: int, conductor_name: str, mode: ConductorMode, start_angle_deg: float, sector_deg: float, min_spacing_m: float, min_clearance_m: float, winding_direction: WindingDirection, current_direction: CurrentDirection, terminal_intent: str, ac_magnitude_a: float, ac_phase_deg: float, frequency_hz: float, dc_current_a: float)` — frozen; hard invariant: non-blank `winding_id`. Range rules live in Task 5 validation, not here.
  - `domain.project.CoreOverride(field: str, value: float, reason: str)` — frozen.
  - `domain.project.CatalogCoreSelection(part_number: str, snapshot: CoreRecord, overrides: tuple[CoreOverride, ...])` — frozen; `part_number` must equal `snapshot.part_number`.
  - `domain.project.ManualCoreSelection(outer_diameter_m: float, inner_diameter_m: float, height_m: float, corner_radius_m: float)` — frozen.
  - `domain.project.CoreSelection = CatalogCoreSelection | ManualCoreSelection` (type alias).
  - `domain.project.InductorProject(project_id: str, name: str, description: str, target_release: AedtRelease, target_edition: AedtEdition, dimension_mode: ModelDimension, core: CoreSelection | None, windings: tuple[WindingDefinition, ...])` — frozen; non-blank `project_id` and `name`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/domain/test_project.py`:

```python
from __future__ import annotations

import pytest

from inductor_designer.domain.aedt_target import AedtEdition, AedtRelease, ModelDimension
from inductor_designer.domain.catalog_records import CoreFamily, Dimension, ReviewStatus
from inductor_designer.domain.project import (
    CatalogCoreSelection,
    CoreOverride,
    InductorProject,
    ManualCoreSelection,
)
from inductor_designer.domain.winding import (
    ConductorMode,
    CurrentDirection,
    WindingDefinition,
    WindingDirection,
)
from inductor_designer.materials.identity import MaterialRef
from tests.unit.domain.test_catalog_records import make_core


def make_winding(**overrides: object) -> WindingDefinition:
    values: dict[str, object] = {
        "winding_id": "w1",
        "label": "Primary",
        "turns": 20,
        "conductor_name": "AWG 18",
        "mode": ConductorMode.SOLID,
        "start_angle_deg": 0.0,
        "sector_deg": 150.0,
        "min_spacing_m": 0.0002,
        "min_clearance_m": 0.001,
        "winding_direction": WindingDirection.CLOCKWISE,
        "current_direction": CurrentDirection.FORWARD,
        "terminal_intent": "",
        "ac_magnitude_a": 2.0,
        "ac_phase_deg": 0.0,
        "frequency_hz": 100_000.0,
        "dc_current_a": 5.0,
    }
    values.update(overrides)
    return WindingDefinition(**values)  # type: ignore[arg-type]


def make_project(**overrides: object) -> InductorProject:
    values: dict[str, object] = {
        "project_id": "3f0e8f5e-8f4e-4a5e-9d5b-6c4f2b1a0d9c",
        "name": "Boost inductor",
        "description": "",
        "target_release": AedtRelease(2025, 2),
        "target_edition": AedtEdition.COMMERCIAL,
        "dimension_mode": ModelDimension.THREE_D,
        "core": CatalogCoreSelection("0077071A7", make_core(), ()),
        "windings": (make_winding(),),
    }
    values.update(overrides)
    return InductorProject(**values)  # type: ignore[arg-type]


def test_project_aggregate_holds_selection_and_windings() -> None:
    project = make_project()
    assert isinstance(project.core, CatalogCoreSelection)
    assert project.windings[0].turns == 20


def test_catalog_selection_rejects_part_number_mismatch() -> None:
    with pytest.raises(ValueError, match="part_number"):
        CatalogCoreSelection("9999", make_core(), ())


def test_manual_selection_and_empty_core_allowed() -> None:
    manual = ManualCoreSelection(0.0269, 0.0147, 0.0112, 0.0)
    assert make_project(core=manual).core is manual
    assert make_project(core=None).core is None


def test_winding_rejects_blank_id() -> None:
    with pytest.raises(ValueError, match="winding_id"):
        make_winding(winding_id="  ")


def test_project_rejects_blank_name() -> None:
    with pytest.raises(ValueError, match="name"):
        make_project(name=" ")


def test_override_carries_reason() -> None:
    override = CoreOverride(field="outer_diameter_m", value=0.027, reason="measured sample")
    assert override.reason == "measured sample"
```

Note: `make_core` is imported from Task 3's test module and `MaterialRef`/`Dimension`/`CoreFamily`/`ReviewStatus` imports keep Ruff's unused-import check honest — remove any import the final test file does not use.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/domain/test_project.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

Create `src/inductor_designer/domain/winding.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ConductorMode(str, Enum):
    SOLID = "solid"
    STRANDED = "stranded"


class WindingDirection(str, Enum):
    CLOCKWISE = "cw"
    COUNTERCLOCKWISE = "ccw"


class CurrentDirection(str, Enum):
    FORWARD = "forward"
    REVERSE = "reverse"


@dataclass(frozen=True, slots=True)
class WindingDefinition:
    """Declarative winding description; geometric feasibility is Milestone 2 work."""

    winding_id: str
    label: str
    turns: int
    conductor_name: str
    mode: ConductorMode
    start_angle_deg: float
    sector_deg: float
    min_spacing_m: float
    min_clearance_m: float
    winding_direction: WindingDirection
    current_direction: CurrentDirection
    terminal_intent: str
    ac_magnitude_a: float
    ac_phase_deg: float
    frequency_hz: float
    dc_current_a: float

    def __post_init__(self) -> None:
        if not self.winding_id.strip():
            raise ValueError("WindingDefinition winding_id cannot be blank")
```

Create `src/inductor_designer/domain/project.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

from inductor_designer.domain.aedt_target import AedtEdition, AedtRelease, ModelDimension
from inductor_designer.domain.catalog_records import CoreRecord
from inductor_designer.domain.winding import WindingDefinition


@dataclass(frozen=True, slots=True)
class CoreOverride:
    field: str
    value: float
    reason: str


@dataclass(frozen=True, slots=True)
class CatalogCoreSelection:
    part_number: str
    snapshot: CoreRecord
    overrides: tuple[CoreOverride, ...]

    def __post_init__(self) -> None:
        if self.part_number != self.snapshot.part_number:
            raise ValueError(
                "CatalogCoreSelection part_number must match snapshot.part_number"
            )


@dataclass(frozen=True, slots=True)
class ManualCoreSelection:
    outer_diameter_m: float
    inner_diameter_m: float
    height_m: float
    corner_radius_m: float


CoreSelection = CatalogCoreSelection | ManualCoreSelection


@dataclass(frozen=True, slots=True)
class InductorProject:
    project_id: str
    name: str
    description: str
    target_release: AedtRelease
    target_edition: AedtEdition
    dimension_mode: ModelDimension
    core: CoreSelection | None
    windings: tuple[WindingDefinition, ...]

    def __post_init__(self) -> None:
        if not self.project_id.strip():
            raise ValueError("InductorProject project_id cannot be blank")
        if not self.name.strip():
            raise ValueError("InductorProject name cannot be blank")
```

- [ ] **Step 4: Run tests and gates**

Run: `python -m pytest tests/unit -q && python -m ruff check . && python -m mypy && python tools/check_architecture.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/inductor_designer/domain/winding.py src/inductor_designer/domain/project.py tests/unit/domain/test_project.py
git commit -m "feat(domain): add winding definition, core selection, and project aggregate"
```

---

### Task 5: Declarative validation

Q3 decision A: declarative rules only, four spec categories, sector-interval overlap is the single cross-winding check. Manual core sanity checks belong here (not in dataclass invariants) so the UI can later present them as issues.

**Files:**
- Create: `src/inductor_designer/domain/validation.py`
- Test: `tests/unit/domain/test_validation.py`

**Interfaces:**
- Consumes: `InductorProject`, selections, and `WindingDefinition` from Task 4.
- Produces:
  - `ValidationCategory` (str Enum: `INFO = "info"`, `WARNING = "warning"`, `ERROR = "error"`, `COMPATIBILITY = "compatibility"`).
  - `ValidationIssue(category: ValidationCategory, code: str, message: str, path: str)` — frozen.
  - `validate_project(project: InductorProject, *, known_conductors: Collection[str] | None = None) -> tuple[ValidationIssue, ...]`.

Rules (code → category):
- `core.missing` → INFO when `core is None`.
- `core.manual.dimensions` → ERROR when manual core has `inner >= outer`, or any of outer/inner/height `<= 0`, or `corner_radius_m < 0`.
- `core.override.reason` → ERROR for any override with blank reason.
- `core.override.field` → ERROR for override fields outside `{"outer_diameter_m", "inner_diameter_m", "height_m"}`.
- `core.snapshot.draft` → WARNING when catalog snapshot `review_status` is `DRAFT`.
- `winding.id.duplicate` → ERROR on duplicated `winding_id`.
- `winding.turns` → ERROR when `turns < 1`.
- `winding.start_angle` → ERROR unless `0 <= start_angle_deg < 360`.
- `winding.sector` → ERROR unless `0 < sector_deg <= 360`.
- `winding.spacing` → ERROR when `min_spacing_m < 0` or `min_clearance_m < 0`.
- `winding.excitation` → ERROR when `ac_magnitude_a < 0`, `frequency_hz <= 0`, or `dc_current_a < 0`.
- `winding.conductor.unknown` → ERROR when `known_conductors` is provided and `conductor_name` is not in it.
- `winding.conductor.unchecked` → INFO once when `known_conductors is None` and the project has windings.
- `winding.sector.overlap` → ERROR for each pair of windings whose angular intervals (mod 360, wraparound split) intersect with positive measure. Skip windings whose start/sector already failed their range rules.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/domain/test_validation.py`:

```python
from __future__ import annotations

from inductor_designer.domain.project import CatalogCoreSelection, CoreOverride, ManualCoreSelection
from inductor_designer.domain.validation import ValidationCategory, validate_project
from tests.unit.domain.test_catalog_records import make_core
from tests.unit.domain.test_project import make_project, make_winding


def codes(project: object, **kwargs: object) -> set[str]:
    return {issue.code for issue in validate_project(project, **kwargs)}  # type: ignore[arg-type]


def test_valid_project_has_no_errors() -> None:
    project = make_project(
        windings=(
            make_winding(winding_id="w1", start_angle_deg=0.0, sector_deg=150.0),
            make_winding(winding_id="w2", start_angle_deg=180.0, sector_deg=150.0),
        )
    )
    issues = validate_project(project, known_conductors={"AWG 18"})
    assert not [i for i in issues if i.category is ValidationCategory.ERROR]


def test_draft_snapshot_yields_warning() -> None:
    assert "core.snapshot.draft" in codes(make_project(), known_conductors={"AWG 18"})


def test_missing_core_is_info() -> None:
    issues = validate_project(make_project(core=None), known_conductors={"AWG 18"})
    issue = next(i for i in issues if i.code == "core.missing")
    assert issue.category is ValidationCategory.INFO


def test_manual_core_dimension_error() -> None:
    manual = ManualCoreSelection(0.010, 0.020, 0.005, 0.0)
    assert "core.manual.dimensions" in codes(make_project(core=manual))


def test_override_requires_reason_and_known_field() -> None:
    selection = CatalogCoreSelection(
        "0077071A7",
        make_core(),
        (
            CoreOverride("outer_diameter_m", 0.027, "  "),
            CoreOverride("bogus_field", 1.0, "why"),
        ),
    )
    result = codes(make_project(core=selection))
    assert {"core.override.reason", "core.override.field"} <= result


def test_winding_range_rules() -> None:
    bad = make_winding(turns=0, start_angle_deg=400.0, sector_deg=0.0, min_spacing_m=-1.0)
    result = codes(make_project(windings=(bad,)))
    assert {"winding.turns", "winding.start_angle", "winding.sector", "winding.spacing"} <= result


def test_excitation_rules() -> None:
    bad = make_winding(frequency_hz=0.0, dc_current_a=-1.0)
    assert "winding.excitation" in codes(make_project(windings=(bad,)))


def test_duplicate_ids() -> None:
    windings = (make_winding(winding_id="w1"), make_winding(winding_id="w1", start_angle_deg=200.0))
    assert "winding.id.duplicate" in codes(make_project(windings=windings))


def test_unknown_conductor_error_and_unchecked_info() -> None:
    project = make_project()
    assert "winding.conductor.unknown" in codes(project, known_conductors=set())
    issues = validate_project(project)
    info = next(i for i in issues if i.code == "winding.conductor.unchecked")
    assert info.category is ValidationCategory.INFO


def test_sector_overlap_detected_with_wraparound() -> None:
    windings = (
        make_winding(winding_id="w1", start_angle_deg=300.0, sector_deg=120.0),
        make_winding(winding_id="w2", start_angle_deg=30.0, sector_deg=60.0),
    )
    assert "winding.sector.overlap" in codes(make_project(windings=windings))


def test_adjacent_sectors_do_not_overlap() -> None:
    windings = (
        make_winding(winding_id="w1", start_angle_deg=0.0, sector_deg=180.0),
        make_winding(winding_id="w2", start_angle_deg=180.0, sector_deg=180.0),
    )
    assert "winding.sector.overlap" not in codes(make_project(windings=windings))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/domain/test_validation.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

Create `src/inductor_designer/domain/validation.py`:

```python
from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from enum import Enum

from inductor_designer.domain.catalog_records import ReviewStatus
from inductor_designer.domain.project import (
    CatalogCoreSelection,
    InductorProject,
    ManualCoreSelection,
)
from inductor_designer.domain.winding import WindingDefinition


class ValidationCategory(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    COMPATIBILITY = "compatibility"


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    category: ValidationCategory
    code: str
    message: str
    path: str


_OVERRIDE_FIELDS = frozenset({"outer_diameter_m", "inner_diameter_m", "height_m"})


def _segments(start_deg: float, sector_deg: float) -> tuple[tuple[float, float], ...]:
    end = start_deg + sector_deg
    if end <= 360.0:
        return ((start_deg, end),)
    return ((start_deg, 360.0), (0.0, end - 360.0))


def _sectors_overlap(first: WindingDefinition, second: WindingDefinition) -> bool:
    return any(
        a_start < b_end and b_start < a_end
        for a_start, a_end in _segments(first.start_angle_deg, first.sector_deg)
        for b_start, b_end in _segments(second.start_angle_deg, second.sector_deg)
    )


def _sector_fields_valid(winding: WindingDefinition) -> bool:
    return 0.0 <= winding.start_angle_deg < 360.0 and 0.0 < winding.sector_deg <= 360.0


def _validate_core(project: InductorProject) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    core = project.core
    if core is None:
        issues.append(
            ValidationIssue(
                ValidationCategory.INFO, "core.missing", "No core is selected yet.", "core"
            )
        )
    elif isinstance(core, ManualCoreSelection):
        if (
            core.inner_diameter_m >= core.outer_diameter_m
            or core.outer_diameter_m <= 0
            or core.inner_diameter_m <= 0
            or core.height_m <= 0
            or core.corner_radius_m < 0
        ):
            issues.append(
                ValidationIssue(
                    ValidationCategory.ERROR,
                    "core.manual.dimensions",
                    "Manual core dimensions must be positive with inner < outer diameter.",
                    "core",
                )
            )
    elif isinstance(core, CatalogCoreSelection):
        if core.snapshot.review_status is ReviewStatus.DRAFT:
            issues.append(
                ValidationIssue(
                    ValidationCategory.WARNING,
                    "core.snapshot.draft",
                    f"Catalog record {core.part_number} is a draft pending review.",
                    "core.snapshot",
                )
            )
        for index, override in enumerate(core.overrides):
            if not override.reason.strip():
                issues.append(
                    ValidationIssue(
                        ValidationCategory.ERROR,
                        "core.override.reason",
                        "Every manual override requires a non-empty reason.",
                        f"core.overrides[{index}]",
                    )
                )
            if override.field not in _OVERRIDE_FIELDS:
                issues.append(
                    ValidationIssue(
                        ValidationCategory.ERROR,
                        "core.override.field",
                        f"Unknown override field: {override.field!r}.",
                        f"core.overrides[{index}]",
                    )
                )
    return issues


def _validate_winding(winding: WindingDefinition, path: str) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    def error(code: str, message: str) -> None:
        issues.append(ValidationIssue(ValidationCategory.ERROR, code, message, path))

    if winding.turns < 1:
        error("winding.turns", "Turn count must be at least 1.")
    if not 0.0 <= winding.start_angle_deg < 360.0:
        error("winding.start_angle", "Start angle must satisfy 0 <= angle < 360 degrees.")
    if not 0.0 < winding.sector_deg <= 360.0:
        error("winding.sector", "Sector must satisfy 0 < sector <= 360 degrees.")
    if winding.min_spacing_m < 0 or winding.min_clearance_m < 0:
        error("winding.spacing", "Spacing and clearance must be non-negative.")
    if winding.ac_magnitude_a < 0 or winding.frequency_hz <= 0 or winding.dc_current_a < 0:
        error(
            "winding.excitation",
            "AC magnitude and DC current must be non-negative and frequency positive.",
        )
    return issues


def validate_project(
    project: InductorProject,
    *,
    known_conductors: Collection[str] | None = None,
) -> tuple[ValidationIssue, ...]:
    issues = _validate_core(project)

    seen_ids: set[str] = set()
    for index, winding in enumerate(project.windings):
        path = f"windings[{index}]"
        issues.extend(_validate_winding(winding, path))
        if winding.winding_id in seen_ids:
            issues.append(
                ValidationIssue(
                    ValidationCategory.ERROR,
                    "winding.id.duplicate",
                    f"Duplicate winding_id: {winding.winding_id!r}.",
                    path,
                )
            )
        seen_ids.add(winding.winding_id)
        if known_conductors is not None and winding.conductor_name not in known_conductors:
            issues.append(
                ValidationIssue(
                    ValidationCategory.ERROR,
                    "winding.conductor.unknown",
                    f"Conductor {winding.conductor_name!r} is not in the catalog.",
                    path,
                )
            )

    if known_conductors is None and project.windings:
        issues.append(
            ValidationIssue(
                ValidationCategory.INFO,
                "winding.conductor.unchecked",
                "Conductor references were not checked against a catalog.",
                "windings",
            )
        )

    checkable = [w for w in project.windings if _sector_fields_valid(w)]
    for i, first in enumerate(checkable):
        for second in checkable[i + 1 :]:
            if _sectors_overlap(first, second):
                issues.append(
                    ValidationIssue(
                        ValidationCategory.ERROR,
                        "winding.sector.overlap",
                        f"Windings {first.winding_id!r} and {second.winding_id!r} "
                        "declare overlapping angular sectors.",
                        "windings",
                    )
                )
    return tuple(issues)
```

- [ ] **Step 4: Run tests and gates**

Run: `python -m pytest tests/unit -q && python -m ruff check . && python -m mypy && python tools/check_architecture.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/inductor_designer/domain/validation.py tests/unit/domain/test_validation.py
git commit -m "feat(domain): add declarative project validation with sector overlap check"
```

---

### Task 6: Project schema v2 and v1→v2 migration

Q2 decision A. v2 adds `core` (nullable) and `windings` (array). A v1 document migrates by gaining an empty selection.

**Files:**
- Create: `schemas/project/v2.schema.json`
- Create: `tests/fixtures/project.v2.json`
- Modify: `src/inductor_designer/adapters/persistence/schema_repository.py`
- Test: extend `tests/unit/adapters/persistence/test_schema_repository.py`

**Interfaces:**
- Produces: `SchemaRepository.migrate_project(document: Mapping[str, object]) -> dict[str, object]` (validates input, applies stepwise migrations to `LATEST_PROJECT_SCHEMA_VERSION`, validates output, returns a new dict); module constant `LATEST_PROJECT_SCHEMA_VERSION = 2`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/adapters/persistence/test_schema_repository.py` (keep existing tests; adjust imports at the top of the file to include the new constant):

```python
import json
from pathlib import Path

from inductor_designer.adapters.persistence.schema_repository import (
    LATEST_PROJECT_SCHEMA_VERSION,
    SchemaRepository,
)

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures"


def _v1_document() -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "projectId": "3f0e8f5e-8f4e-4a5e-9d5b-6c4f2b1a0d9c",
        "metadata": {"name": "Legacy project"},
        "target": {"aedtRelease": "2025.2", "edition": "commercial"},
    }


def test_latest_version_is_two() -> None:
    assert LATEST_PROJECT_SCHEMA_VERSION == 2


def test_v2_fixture_validates(schema_repository: SchemaRepository) -> None:
    document = json.loads((FIXTURES / "project.v2.json").read_text(encoding="utf-8"))
    schema_repository.validate_project(document)


def test_migrate_v1_to_v2(schema_repository: SchemaRepository) -> None:
    migrated = schema_repository.migrate_project(_v1_document())
    assert migrated["schemaVersion"] == 2
    assert migrated["core"] is None
    assert migrated["windings"] == []
    schema_repository.validate_project(migrated)


def test_migrate_latest_is_identity(schema_repository: SchemaRepository) -> None:
    document = json.loads((FIXTURES / "project.v2.json").read_text(encoding="utf-8"))
    assert schema_repository.migrate_project(document) == document
```

If the existing test module has no `schema_repository` fixture, add one:

```python
import pytest


@pytest.fixture
def schema_repository() -> SchemaRepository:
    return SchemaRepository(Path(__file__).resolve().parents[4] / "schemas")
```

(Adopt whatever construction pattern the existing tests in that file already use — reuse it rather than duplicating path logic.)

- [ ] **Step 2: Create the v2 fixture**

Create `tests/fixtures/project.v2.json`:

```json
{
  "schemaVersion": 2,
  "projectId": "3f0e8f5e-8f4e-4a5e-9d5b-6c4f2b1a0d9c",
  "metadata": {"name": "Boost inductor", "description": "Fixture project"},
  "target": {"aedtRelease": "2025.2", "edition": "commercial", "dimensionMode": "3d"},
  "core": {
    "kind": "catalog",
    "partNumber": "0077071A7",
    "snapshot": {
      "manufacturer": "Magnetics",
      "family": "powder-toroid",
      "partNumber": "0077071A7",
      "material": {"manufacturer": "Magnetics", "name": "Kool Mu", "grade": "60"},
      "coating": "black epoxy",
      "catalogRevision": "magnetics-powder-2024",
      "sourceUrl": "https://www.mag-inc.com/example",
      "sourcePage": 10,
      "outerDiameter": {"nominalM": 0.02692, "minM": 0.0264, "maxM": 0.0274},
      "innerDiameter": {"nominalM": 0.01473, "minM": 0.0144, "maxM": 0.0151},
      "height": {"nominalM": 0.01118, "minM": 0.0109, "maxM": 0.0115},
      "effectiveAreaM2": 6.54e-5,
      "pathLengthM": 0.0635,
      "volumeM3": 4.15e-6,
      "alValueNh": 61.0,
      "reviewStatus": "draft",
      "reviewedBy": null
    },
    "overrides": []
  },
  "windings": [
    {
      "windingId": "w1",
      "label": "Primary",
      "turns": 20,
      "conductor": "AWG 18",
      "mode": "solid",
      "startAngleDeg": 0.0,
      "sectorDeg": 150.0,
      "minSpacingM": 0.0002,
      "minClearanceM": 0.001,
      "windingDirection": "cw",
      "currentDirection": "forward",
      "terminalIntent": "",
      "acMagnitudeA": 2.0,
      "acPhaseDeg": 0.0,
      "frequencyHz": 100000.0,
      "dcCurrentA": 5.0
    }
  ]
}
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/unit/adapters/persistence -q`
Expected: FAIL — `LATEST_PROJECT_SCHEMA_VERSION` missing and v2 schema absent.

- [ ] **Step 4: Add the v2 schema**

Create `schemas/project/v2.schema.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://github.com/smarley2/AnsysPyAEDT/schemas/project/v2.schema.json",
  "title": "PyAEDT Inductor Designer project document v2",
  "description": "Canonical units: meters (M), degrees (Deg), amperes (A), hertz (Hz), nanohenry per squared turn (Nh).",
  "type": "object",
  "additionalProperties": false,
  "required": ["schemaVersion", "projectId", "metadata", "target", "core", "windings"],
  "$defs": {
    "dimension": {
      "type": "object",
      "additionalProperties": false,
      "required": ["nominalM", "minM", "maxM"],
      "properties": {
        "nominalM": {"type": "number", "exclusiveMinimum": 0},
        "minM": {"type": ["number", "null"]},
        "maxM": {"type": ["number", "null"]}
      }
    },
    "materialRef": {
      "type": "object",
      "additionalProperties": false,
      "required": ["manufacturer", "name", "grade"],
      "properties": {
        "manufacturer": {"type": "string", "minLength": 1},
        "name": {"type": "string", "minLength": 1},
        "grade": {"type": "string", "minLength": 1}
      }
    },
    "coreSnapshot": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "manufacturer", "family", "partNumber", "material", "coating",
        "catalogRevision", "sourceUrl", "sourcePage",
        "outerDiameter", "innerDiameter", "height",
        "effectiveAreaM2", "pathLengthM", "volumeM3", "alValueNh",
        "reviewStatus", "reviewedBy"
      ],
      "properties": {
        "manufacturer": {"type": "string", "minLength": 1},
        "family": {"enum": ["powder-toroid", "ferrite-toroid"]},
        "partNumber": {"type": "string", "minLength": 1},
        "material": {"$ref": "#/$defs/materialRef"},
        "coating": {"type": "string"},
        "catalogRevision": {"type": "string", "minLength": 1},
        "sourceUrl": {"type": "string", "minLength": 1},
        "sourcePage": {"type": "integer", "minimum": 1},
        "outerDiameter": {"$ref": "#/$defs/dimension"},
        "innerDiameter": {"$ref": "#/$defs/dimension"},
        "height": {"$ref": "#/$defs/dimension"},
        "effectiveAreaM2": {"type": "number", "exclusiveMinimum": 0},
        "pathLengthM": {"type": "number", "exclusiveMinimum": 0},
        "volumeM3": {"type": "number", "exclusiveMinimum": 0},
        "alValueNh": {"type": "number", "exclusiveMinimum": 0},
        "reviewStatus": {"enum": ["draft", "reviewed"]},
        "reviewedBy": {"type": ["string", "null"]}
      }
    },
    "winding": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "windingId", "label", "turns", "conductor", "mode",
        "startAngleDeg", "sectorDeg", "minSpacingM", "minClearanceM",
        "windingDirection", "currentDirection", "terminalIntent",
        "acMagnitudeA", "acPhaseDeg", "frequencyHz", "dcCurrentA"
      ],
      "properties": {
        "windingId": {"type": "string", "minLength": 1},
        "label": {"type": "string"},
        "turns": {"type": "integer", "minimum": 1},
        "conductor": {"type": "string", "minLength": 1},
        "mode": {"enum": ["solid", "stranded"]},
        "startAngleDeg": {"type": "number", "minimum": 0, "exclusiveMaximum": 360},
        "sectorDeg": {"type": "number", "exclusiveMinimum": 0, "maximum": 360},
        "minSpacingM": {"type": "number", "minimum": 0},
        "minClearanceM": {"type": "number", "minimum": 0},
        "windingDirection": {"enum": ["cw", "ccw"]},
        "currentDirection": {"enum": ["forward", "reverse"]},
        "terminalIntent": {"type": "string"},
        "acMagnitudeA": {"type": "number", "minimum": 0},
        "acPhaseDeg": {"type": "number"},
        "frequencyHz": {"type": "number", "exclusiveMinimum": 0},
        "dcCurrentA": {"type": "number", "minimum": 0}
      }
    }
  },
  "properties": {
    "schemaVersion": {"const": 2},
    "projectId": {"type": "string", "format": "uuid"},
    "metadata": {
      "type": "object",
      "additionalProperties": false,
      "required": ["name"],
      "properties": {
        "name": {"type": "string", "minLength": 1},
        "description": {"type": "string", "default": ""}
      }
    },
    "target": {
      "type": "object",
      "additionalProperties": false,
      "required": ["aedtRelease", "edition", "dimensionMode"],
      "properties": {
        "aedtRelease": {
          "type": "string",
          "pattern": "^(?:2024\\.2|20(?:2[5-9]|[3-9][0-9])\\.[12])$"
        },
        "edition": {"enum": ["commercial", "student"]},
        "dimensionMode": {"enum": ["2d", "3d"]}
      }
    },
    "core": {
      "oneOf": [
        {"type": "null"},
        {
          "type": "object",
          "additionalProperties": false,
          "required": ["kind", "partNumber", "snapshot", "overrides"],
          "properties": {
            "kind": {"const": "catalog"},
            "partNumber": {"type": "string", "minLength": 1},
            "snapshot": {"$ref": "#/$defs/coreSnapshot"},
            "overrides": {
              "type": "array",
              "items": {
                "type": "object",
                "additionalProperties": false,
                "required": ["field", "value", "reason"],
                "properties": {
                  "field": {"enum": ["outer_diameter_m", "inner_diameter_m", "height_m"]},
                  "value": {"type": "number", "exclusiveMinimum": 0},
                  "reason": {"type": "string", "minLength": 1}
                }
              }
            }
          }
        },
        {
          "type": "object",
          "additionalProperties": false,
          "required": ["kind", "outerDiameterM", "innerDiameterM", "heightM", "cornerRadiusM"],
          "properties": {
            "kind": {"const": "manual"},
            "outerDiameterM": {"type": "number", "exclusiveMinimum": 0},
            "innerDiameterM": {"type": "number", "exclusiveMinimum": 0},
            "heightM": {"type": "number", "exclusiveMinimum": 0},
            "cornerRadiusM": {"type": "number", "minimum": 0}
          }
        }
      ]
    },
    "windings": {"type": "array", "items": {"$ref": "#/$defs/winding"}}
  }
}
```

Note: the v1 document has no `dimensionMode`; the migration must add a default (`"3d"`, the spec's authoritative model).

- [ ] **Step 5: Implement migration**

Modify `src/inductor_designer/adapters/persistence/schema_repository.py` — add after the imports:

```python
from collections.abc import Callable

LATEST_PROJECT_SCHEMA_VERSION = 2


def _migrate_v1_to_v2(document: dict[str, object]) -> dict[str, object]:
    migrated = dict(document)
    migrated["schemaVersion"] = 2
    target = dict(migrated["target"])  # type: ignore[arg-type]
    target.setdefault("dimensionMode", "3d")
    migrated["target"] = target
    migrated["core"] = None
    migrated["windings"] = []
    return migrated


_MIGRATIONS: dict[int, Callable[[dict[str, object]], dict[str, object]]] = {
    1: _migrate_v1_to_v2,
}
```

Add this method to `SchemaRepository`:

```python
    def migrate_project(self, document: Mapping[str, object]) -> dict[str, object]:
        self.validate_project(document)
        current: dict[str, object] = dict(document)
        version = current["schemaVersion"]
        assert isinstance(version, int)
        while version < LATEST_PROJECT_SCHEMA_VERSION:
            current = _MIGRATIONS[version](current)
            version = int(current["schemaVersion"])  # type: ignore[call-overload]
        self.validate_project(current)
        return current
```

(If mypy strict complains about the `int(...)` cast, use `version = current["schemaVersion"]; assert isinstance(version, int)` instead — match the repository's existing style of explicit isinstance checks.)

- [ ] **Step 6: Run tests and gates**

Run: `python -m pytest tests/unit -q && python -m ruff check . && python -m mypy`
Expected: PASS, including the pre-existing v1 schema tests.

- [ ] **Step 7: Commit**

```bash
git add schemas/project/v2.schema.json tests/fixtures/project.v2.json src/inductor_designer/adapters/persistence/schema_repository.py tests/unit/adapters/persistence/test_schema_repository.py
git commit -m "feat(persistence): add project schema v2 with v1 to v2 migration"
```

---

### Task 7: Record serde and the project repository

JSON mapping is a persistence concern. One shared serde module keeps the project repository, the SQLite adapter (Task 10), and the catalog builder (Task 9) writing identical shapes.

**Files:**
- Create: `src/inductor_designer/adapters/persistence/record_serde.py`
- Create: `src/inductor_designer/adapters/persistence/project_repository.py`
- Test: `tests/unit/adapters/persistence/test_project_repository.py`

**Interfaces:**
- Consumes: domain types from Tasks 1–4, `SchemaRepository.migrate_project` from Task 6.
- Produces (in `record_serde`):
  - `core_record_to_json(record: CoreRecord) -> dict[str, object]` / `core_record_from_json(data: Mapping[str, object]) -> CoreRecord`
  - `conductor_record_to_json(record: ConductorRecord) -> dict[str, object]` / `conductor_record_from_json(data: Mapping[str, object]) -> ConductorRecord`
- Produces (in `project_repository`):
  - `project_to_document(project: InductorProject) -> dict[str, object]`
  - `project_from_document(document: Mapping[str, object]) -> InductorProject`
  - `class ProjectRepository: __init__(self, schemas: SchemaRepository)`, `load(self, path: Path) -> InductorProject` (read → validate → migrate → map), `save(self, project: InductorProject, path: Path) -> None` (map → validate → write deterministic JSON: `json.dumps(document, indent=2, sort_keys=True) + "\n"`, UTF-8).

- [ ] **Step 1: Write the failing test**

Create `tests/unit/adapters/persistence/test_project_repository.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from inductor_designer.adapters.persistence.project_repository import (
    ProjectRepository,
    project_from_document,
    project_to_document,
)
from inductor_designer.adapters.persistence.schema_repository import SchemaRepository
from tests.unit.domain.test_project import make_project, make_winding

SCHEMAS = Path(__file__).resolve().parents[4] / "schemas"
FIXTURES = Path(__file__).resolve().parents[3] / "fixtures"


def repository() -> ProjectRepository:
    return ProjectRepository(SchemaRepository(SCHEMAS))


def test_document_round_trip_preserves_project() -> None:
    project = make_project(
        windings=(
            make_winding(winding_id="w1"),
            make_winding(winding_id="w2", start_angle_deg=180.0),
        )
    )
    assert project_from_document(project_to_document(project)) == project


def test_fixture_maps_to_domain() -> None:
    document = json.loads((FIXTURES / "project.v2.json").read_text(encoding="utf-8"))
    project = project_from_document(document)
    assert project.windings[0].conductor_name == "AWG 18"


def test_save_and_load_round_trip(tmp_path: Path) -> None:
    repo = repository()
    project = make_project()
    path = tmp_path / "boost.inductor.json"
    repo.save(project, path)
    assert repo.load(path) == project


def test_save_is_deterministic(tmp_path: Path) -> None:
    repo = repository()
    project = make_project()
    first, second = tmp_path / "a.inductor.json", tmp_path / "b.inductor.json"
    repo.save(project, first)
    repo.save(project, second)
    assert first.read_bytes() == second.read_bytes()


def test_load_migrates_v1_documents(tmp_path: Path) -> None:
    v1 = {
        "schemaVersion": 1,
        "projectId": "3f0e8f5e-8f4e-4a5e-9d5b-6c4f2b1a0d9c",
        "metadata": {"name": "Legacy"},
        "target": {"aedtRelease": "2025.2", "edition": "commercial"},
    }
    path = tmp_path / "legacy.inductor.json"
    path.write_text(json.dumps(v1), encoding="utf-8")
    project = repository().load(path)
    assert project.core is None
    assert project.windings == ()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/adapters/persistence/test_project_repository.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement record serde**

Create `src/inductor_designer/adapters/persistence/record_serde.py`:

```python
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from inductor_designer.domain.catalog_records import (
    ConductorRecord,
    ConductorStandard,
    CoreFamily,
    CoreRecord,
    Dimension,
    ReviewStatus,
)
from inductor_designer.materials.identity import MaterialRef


def _dimension_to_json(dimension: Dimension) -> dict[str, object]:
    return {"nominalM": dimension.nominal_m, "minM": dimension.min_m, "maxM": dimension.max_m}


def _dimension_from_json(data: Mapping[str, Any]) -> Dimension:
    return Dimension(nominal_m=data["nominalM"], min_m=data["minM"], max_m=data["maxM"])


def core_record_to_json(record: CoreRecord) -> dict[str, object]:
    return {
        "manufacturer": record.manufacturer,
        "family": record.family.value,
        "partNumber": record.part_number,
        "material": {
            "manufacturer": record.material.manufacturer,
            "name": record.material.name,
            "grade": record.material.grade,
        },
        "coating": record.coating,
        "catalogRevision": record.catalog_revision,
        "sourceUrl": record.source_url,
        "sourcePage": record.source_page,
        "outerDiameter": _dimension_to_json(record.outer_diameter),
        "innerDiameter": _dimension_to_json(record.inner_diameter),
        "height": _dimension_to_json(record.height),
        "effectiveAreaM2": record.effective_area_m2,
        "pathLengthM": record.path_length_m,
        "volumeM3": record.volume_m3,
        "alValueNh": record.al_value_nh,
        "reviewStatus": record.review_status.value,
        "reviewedBy": record.reviewed_by,
    }


def core_record_from_json(data: Mapping[str, Any]) -> CoreRecord:
    material = data["material"]
    return CoreRecord(
        manufacturer=data["manufacturer"],
        family=CoreFamily(data["family"]),
        part_number=data["partNumber"],
        material=MaterialRef(material["manufacturer"], material["name"], material["grade"]),
        coating=data["coating"],
        catalog_revision=data["catalogRevision"],
        source_url=data["sourceUrl"],
        source_page=data["sourcePage"],
        outer_diameter=_dimension_from_json(data["outerDiameter"]),
        inner_diameter=_dimension_from_json(data["innerDiameter"]),
        height=_dimension_from_json(data["height"]),
        effective_area_m2=data["effectiveAreaM2"],
        path_length_m=data["pathLengthM"],
        volume_m3=data["volumeM3"],
        al_value_nh=data["alValueNh"],
        review_status=ReviewStatus(data["reviewStatus"]),
        reviewed_by=data["reviewedBy"],
    )


def conductor_record_to_json(record: ConductorRecord) -> dict[str, object]:
    return {
        "name": record.name,
        "standard": record.standard.value,
        "bareDiameterM": record.bare_diameter_m,
        "grade1DiameterM": record.grade1_diameter_m,
        "grade2DiameterM": record.grade2_diameter_m,
        "source": record.source,
        "catalogRevision": record.catalog_revision,
        "reviewStatus": record.review_status.value,
        "reviewedBy": record.reviewed_by,
    }


def conductor_record_from_json(data: Mapping[str, Any]) -> ConductorRecord:
    return ConductorRecord(
        name=data["name"],
        standard=ConductorStandard(data["standard"]),
        bare_diameter_m=data["bareDiameterM"],
        grade1_diameter_m=data["grade1DiameterM"],
        grade2_diameter_m=data["grade2DiameterM"],
        source=data["source"],
        catalog_revision=data["catalogRevision"],
        review_status=ReviewStatus(data["reviewStatus"]),
        reviewed_by=data["reviewedBy"],
    )
```

- [ ] **Step 4: Implement the project repository**

Create `src/inductor_designer/adapters/persistence/project_repository.py`:

```python
from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from inductor_designer.adapters.persistence.record_serde import (
    core_record_from_json,
    core_record_to_json,
)
from inductor_designer.adapters.persistence.schema_repository import SchemaRepository
from inductor_designer.domain.aedt_target import AedtEdition, AedtRelease, ModelDimension
from inductor_designer.domain.project import (
    CatalogCoreSelection,
    CoreOverride,
    CoreSelection,
    InductorProject,
    ManualCoreSelection,
)
from inductor_designer.domain.winding import (
    ConductorMode,
    CurrentDirection,
    WindingDefinition,
    WindingDirection,
)


def _winding_to_json(winding: WindingDefinition) -> dict[str, object]:
    return {
        "windingId": winding.winding_id,
        "label": winding.label,
        "turns": winding.turns,
        "conductor": winding.conductor_name,
        "mode": winding.mode.value,
        "startAngleDeg": winding.start_angle_deg,
        "sectorDeg": winding.sector_deg,
        "minSpacingM": winding.min_spacing_m,
        "minClearanceM": winding.min_clearance_m,
        "windingDirection": winding.winding_direction.value,
        "currentDirection": winding.current_direction.value,
        "terminalIntent": winding.terminal_intent,
        "acMagnitudeA": winding.ac_magnitude_a,
        "acPhaseDeg": winding.ac_phase_deg,
        "frequencyHz": winding.frequency_hz,
        "dcCurrentA": winding.dc_current_a,
    }


def _winding_from_json(data: Mapping[str, Any]) -> WindingDefinition:
    return WindingDefinition(
        winding_id=data["windingId"],
        label=data["label"],
        turns=data["turns"],
        conductor_name=data["conductor"],
        mode=ConductorMode(data["mode"]),
        start_angle_deg=data["startAngleDeg"],
        sector_deg=data["sectorDeg"],
        min_spacing_m=data["minSpacingM"],
        min_clearance_m=data["minClearanceM"],
        winding_direction=WindingDirection(data["windingDirection"]),
        current_direction=CurrentDirection(data["currentDirection"]),
        terminal_intent=data["terminalIntent"],
        ac_magnitude_a=data["acMagnitudeA"],
        ac_phase_deg=data["acPhaseDeg"],
        frequency_hz=data["frequencyHz"],
        dc_current_a=data["dcCurrentA"],
    )


def _core_to_json(core: CoreSelection | None) -> dict[str, object] | None:
    if core is None:
        return None
    if isinstance(core, ManualCoreSelection):
        return {
            "kind": "manual",
            "outerDiameterM": core.outer_diameter_m,
            "innerDiameterM": core.inner_diameter_m,
            "heightM": core.height_m,
            "cornerRadiusM": core.corner_radius_m,
        }
    return {
        "kind": "catalog",
        "partNumber": core.part_number,
        "snapshot": core_record_to_json(core.snapshot),
        "overrides": [
            {"field": o.field, "value": o.value, "reason": o.reason} for o in core.overrides
        ],
    }


def _core_from_json(data: Mapping[str, Any] | None) -> CoreSelection | None:
    if data is None:
        return None
    if data["kind"] == "manual":
        return ManualCoreSelection(
            outer_diameter_m=data["outerDiameterM"],
            inner_diameter_m=data["innerDiameterM"],
            height_m=data["heightM"],
            corner_radius_m=data["cornerRadiusM"],
        )
    return CatalogCoreSelection(
        part_number=data["partNumber"],
        snapshot=core_record_from_json(data["snapshot"]),
        overrides=tuple(
            CoreOverride(o["field"], o["value"], o["reason"]) for o in data["overrides"]
        ),
    )


def project_to_document(project: InductorProject) -> dict[str, object]:
    return {
        "schemaVersion": 2,
        "projectId": project.project_id,
        "metadata": {"name": project.name, "description": project.description},
        "target": {
            "aedtRelease": str(project.target_release),
            "edition": project.target_edition.value,
            "dimensionMode": project.dimension_mode.value,
        },
        "core": _core_to_json(project.core),
        "windings": [_winding_to_json(w) for w in project.windings],
    }


def project_from_document(document: Mapping[str, Any]) -> InductorProject:
    metadata = document["metadata"]
    target = document["target"]
    return InductorProject(
        project_id=document["projectId"],
        name=metadata["name"],
        description=metadata.get("description", ""),
        target_release=AedtRelease.parse(target["aedtRelease"]),
        target_edition=AedtEdition(target["edition"]),
        dimension_mode=ModelDimension(target["dimensionMode"]),
        core=_core_from_json(document["core"]),
        windings=tuple(_winding_from_json(w) for w in document["windings"]),
    )


class ProjectRepository:
    def __init__(self, schemas: SchemaRepository) -> None:
        self._schemas = schemas

    def load(self, path: Path) -> InductorProject:
        loaded: Any = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError(f"Project document is not a JSON object: {path}")
        migrated = self._schemas.migrate_project(loaded)
        return project_from_document(migrated)

    def save(self, project: InductorProject, path: Path) -> None:
        document = project_to_document(project)
        self._schemas.validate_project(document)
        path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
```

- [ ] **Step 5: Run tests and gates**

Run: `python -m pytest tests/unit -q && python -m ruff check . && python -m mypy && python tools/check_architecture.py`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/inductor_designer/adapters/persistence/record_serde.py src/inductor_designer/adapters/persistence/project_repository.py tests/unit/adapters/persistence/test_project_repository.py
git commit -m "feat(persistence): add record serde and project repository with migration on load"
```

---

### Task 8: Catalog JSON schemas and canonical core seed data

Canonical YAML is the review surface (Q9 decision A). Seed: ~10 powder cores + ~5 ferrite toroids (Q4 decision A), all `reviewStatus: draft`.

> **DATA WARNING:** Dimension and effective-parameter values below are transcription drafts. They MUST be verified against the linked Magnetics sources by a human reviewer before any record's `reviewStatus` flips to `reviewed`. Nothing in this milestone depends on the values being correct — only on the records being schema-valid.

**Files:**
- Create: `schemas/catalog/core.v1.schema.json`
- Create: `schemas/catalog/conductor.v1.schema.json`
- Create: `catalog/README.md`
- Create: `catalog/cores/magnetics-powder.yaml`
- Create: `catalog/cores/magnetics-ferrite.yaml`
- Test: `tests/unit/catalog/__init__.py`, `tests/unit/catalog/test_canonical_data.py`

**Interfaces:**
- Produces: schema files consumed by the builder (Task 9); canonical YAML consumed by the builder; record field names identical to `record_serde` JSON (Task 7).

- [ ] **Step 1: Write the failing test**

Create `tests/unit/catalog/__init__.py` (empty) and `tests/unit/catalog/test_canonical_data.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

from inductor_designer.adapters.persistence.record_serde import core_record_from_json

ROOT = Path(__file__).resolve().parents[3]
CORE_SCHEMA = json.loads((ROOT / "schemas/catalog/core.v1.schema.json").read_text("utf-8"))
CORE_FILES = sorted((ROOT / "catalog/cores").glob("*.yaml"))


def load_records(path: Path) -> list[dict[str, object]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict) and isinstance(data["records"], list)
    return data["records"]


def test_core_files_exist() -> None:
    names = {path.name for path in CORE_FILES}
    assert {"magnetics-powder.yaml", "magnetics-ferrite.yaml"} <= names


def test_every_core_record_validates_and_maps() -> None:
    validator = Draft202012Validator(CORE_SCHEMA)
    seen: set[str] = set()
    total = 0
    for path in CORE_FILES:
        for record in load_records(path):
            validator.validate(record)
            core = core_record_from_json(record)
            assert core.part_number not in seen, f"duplicate {core.part_number}"
            seen.add(core.part_number)
            total += 1
    assert total >= 15
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/catalog -q`
Expected: FAIL — schema file missing.

- [ ] **Step 3: Add the catalog schemas**

Create `schemas/catalog/core.v1.schema.json` — identical shape to the project schema's `coreSnapshot` definition (duplicated deliberately; cross-file `$ref` would need a schema registry, not worth it for one structure):

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://github.com/smarley2/AnsysPyAEDT/schemas/catalog/core.v1.schema.json",
  "title": "Commercial toroid core record v1",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "manufacturer", "family", "partNumber", "material", "coating",
    "catalogRevision", "sourceUrl", "sourcePage",
    "outerDiameter", "innerDiameter", "height",
    "effectiveAreaM2", "pathLengthM", "volumeM3", "alValueNh",
    "reviewStatus", "reviewedBy"
  ],
  "$defs": {
    "dimension": {
      "type": "object",
      "additionalProperties": false,
      "required": ["nominalM", "minM", "maxM"],
      "properties": {
        "nominalM": {"type": "number", "exclusiveMinimum": 0},
        "minM": {"type": ["number", "null"]},
        "maxM": {"type": ["number", "null"]}
      }
    }
  },
  "properties": {
    "manufacturer": {"type": "string", "minLength": 1},
    "family": {"enum": ["powder-toroid", "ferrite-toroid"]},
    "partNumber": {"type": "string", "minLength": 1},
    "material": {
      "type": "object",
      "additionalProperties": false,
      "required": ["manufacturer", "name", "grade"],
      "properties": {
        "manufacturer": {"type": "string", "minLength": 1},
        "name": {"type": "string", "minLength": 1},
        "grade": {"type": "string", "minLength": 1}
      }
    },
    "coating": {"type": "string"},
    "catalogRevision": {"type": "string", "minLength": 1},
    "sourceUrl": {"type": "string", "minLength": 1},
    "sourcePage": {"type": "integer", "minimum": 1},
    "outerDiameter": {"$ref": "#/$defs/dimension"},
    "innerDiameter": {"$ref": "#/$defs/dimension"},
    "height": {"$ref": "#/$defs/dimension"},
    "effectiveAreaM2": {"type": "number", "exclusiveMinimum": 0},
    "pathLengthM": {"type": "number", "exclusiveMinimum": 0},
    "volumeM3": {"type": "number", "exclusiveMinimum": 0},
    "alValueNh": {"type": "number", "exclusiveMinimum": 0},
    "reviewStatus": {"enum": ["draft", "reviewed"]},
    "reviewedBy": {"type": ["string", "null"]}
  }
}
```

Create `schemas/catalog/conductor.v1.schema.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://github.com/smarley2/AnsysPyAEDT/schemas/catalog/conductor.v1.schema.json",
  "title": "Round-wire conductor record v1",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "name", "standard", "bareDiameterM", "grade1DiameterM", "grade2DiameterM",
    "source", "catalogRevision", "reviewStatus", "reviewedBy"
  ],
  "properties": {
    "name": {"type": "string", "minLength": 1},
    "standard": {"enum": ["awg", "iec-60317"]},
    "bareDiameterM": {"type": "number", "exclusiveMinimum": 0},
    "grade1DiameterM": {"type": ["number", "null"], "exclusiveMinimum": 0},
    "grade2DiameterM": {"type": ["number", "null"], "exclusiveMinimum": 0},
    "source": {"type": "string", "minLength": 1},
    "catalogRevision": {"type": "string", "minLength": 1},
    "reviewStatus": {"enum": ["draft", "reviewed"]},
    "reviewedBy": {"type": ["string", "null"]}
  }
}
```

- [ ] **Step 4: Add canonical core data**

Create `catalog/README.md`:

```markdown
# Canonical catalog data

Human-reviewed source records for commercial cores and round-wire conductors.

- YAML files here are the review surface; edit and review them, never the SQLite index.
- `tools/build_catalog.py` compiles this directory into `artifacts/catalog/catalog.sqlite`
  (gitignored build artifact — never edit or commit it).
- Field names and units match `schemas/catalog/*.schema.json`: meters, camelCase.
- `reviewStatus: draft` marks values transcribed but not yet verified against the
  cited source page. Only a human reviewer may set `reviewStatus: reviewed` and
  `reviewedBy`, after checking every number against the source.
- `catalog/conductors/round-wire.yaml` is generated by `tools/generate_conductors.py`;
  regenerate it instead of editing by hand, then review and commit the result.
```

Create `catalog/cores/magnetics-powder.yaml` with ten records. First record shown in full; the remaining nine repeat the same structure, changing the identity and numeric fields. All values are drafts to verify against the Magnetics powder-core catalog (`https://www.mag-inc.com/Media/Magnetics/File-Library/Product%20Literature/Powder%20Core%20Literature/Magnetics-Powder-Core-Catalog.pdf`):

```yaml
# Draft transcription — verify every value against the cited source before review.
records:
  - partNumber: "0077021A7"
    manufacturer: Magnetics
    family: powder-toroid
    material: {manufacturer: Magnetics, name: Kool Mu, grade: "60"}
    coating: black epoxy
    catalogRevision: magnetics-powder-2024
    sourceUrl: https://www.mag-inc.com/products/powder-cores
    sourcePage: 1
    outerDiameter: {nominalM: 0.01270, minM: null, maxM: null}
    innerDiameter: {nominalM: 0.00775, minM: null, maxM: null}
    height: {nominalM: 0.00475, minM: null, maxM: null}
    effectiveAreaM2: 1.14e-5
    pathLengthM: 0.0317
    volumeM3: 3.61e-7
    alValueNh: 27.0
    reviewStatus: draft
    reviewedBy: null
```

Add nine more powder records with the same shape for these part numbers (values drafted from the same catalog, spanning small to large OD across Kool Mu 60µ, Kool Mu 26µ, and High Flux 60µ): `0077041A7`, `0077071A7`, `0077083A7`, `0077090A7`, `0077109A7`, `0077071A2` (Kool Mu 26µ, grade `"26"`), `0077083A2` (grade `"26"`), `0058071A2` (High Flux, material name `High Flux`, grade `"60"`), `0058083A2` (High Flux, grade `"60"`). The implementer transcribes plausible draft values for each; exactness is the reviewer's job, schema validity is the implementer's job.

Create `catalog/cores/magnetics-ferrite.yaml` with five ferrite toroid records of the same shape (family `ferrite-toroid`, material name `J` or `R`, grade = initial permeability class e.g. `"5000"` for J, `"2300"` for R, coating `parylene`), source `https://www.mag-inc.com/products/ferrite-cores/ferrite-toroids`, part numbers: `J-40601-TC`, `J-41003-TC`, `J-42206-TC`, `R-41306-TC`, `R-42507-TC`. Same draft-value rule.

- [ ] **Step 5: Run tests and gates**

Run: `python -m pytest tests/unit/catalog -q && python -m ruff check .`
Expected: PASS — every record schema-validates, maps to `CoreRecord`, ≥ 15 unique parts.

- [ ] **Step 6: Commit**

```bash
git add schemas/catalog catalog tests/unit/catalog
git commit -m "feat(catalog): add catalog schemas and draft Magnetics core seed data"
```

---

### Task 9: Conductor generator and canonical conductor data

AWG 10–32 from the exact formula plus a practical IEC 60317 metric subset (Q5 decision A). Insulated diameters are `null` in M1: no consumer exists until M2 packing, and transcribing IEC 60317-0-1 grade tables belongs to the review that unlocks them (ponytail: nullable now, table when M2 needs it).

**Files:**
- Create: `tools/generate_conductors.py`
- Create: `catalog/conductors/round-wire.yaml` (generated, committed)
- Test: `tests/unit/tools/test_generate_conductors.py`

**Interfaces:**
- Consumes: `awg_bare_diameter_m` from Task 2, `conductor_record_from_json` from Task 7.
- Produces: `tools.generate_conductors.generate_records() -> list[dict[str, object]]` (deterministic, sorted by name) and `main(argv: list[str] | None = None) -> int` writing `catalog/conductors/round-wire.yaml`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/tools/test_generate_conductors.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

from inductor_designer.adapters.persistence.record_serde import conductor_record_from_json
from tools.generate_conductors import generate_records, main

ROOT = Path(__file__).resolve().parents[3]
SCHEMA = json.loads((ROOT / "schemas/catalog/conductor.v1.schema.json").read_text("utf-8"))


def test_records_validate_and_map() -> None:
    validator = Draft202012Validator(SCHEMA)
    records = generate_records()
    for record in records:
        validator.validate(record)
        conductor_record_from_json(record)


def test_awg_range_and_metric_sizes_present() -> None:
    names = {record["name"] for record in generate_records()}
    assert {"AWG 10", "AWG 18", "AWG 32"} <= names
    assert {"0.50 mm", "2.50 mm"} <= names
    assert "AWG 9" not in names


def test_awg_18_value() -> None:
    record = next(r for r in generate_records() if r["name"] == "AWG 18")
    assert record["bareDiameterM"] == pytest.approx(0.00102362, rel=1e-3)
    assert record["grade1DiameterM"] is None


def test_generation_is_deterministic() -> None:
    assert generate_records() == generate_records()


def test_main_writes_committed_file(tmp_path: Path) -> None:
    out = tmp_path / "round-wire.yaml"
    assert main(["--out", str(out)]) == 0
    written = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert written["records"] == generate_records()


def test_committed_file_matches_generator() -> None:
    committed = yaml.safe_load(
        (ROOT / "catalog/conductors/round-wire.yaml").read_text(encoding="utf-8")
    )
    assert committed["records"] == generate_records()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/tools/test_generate_conductors.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'tools.generate_conductors'`.

- [ ] **Step 3: Implement the generator**

Create `tools/generate_conductors.py`:

```python
"""Generate the canonical round-wire conductor catalog.

Bare AWG diameters use the exact ASTM B258 formula. Insulated (grade 1/2)
diameters are intentionally null in Milestone 1: they gain a consumer in the
Milestone 2 packing engine, and the IEC 60317-0-1 maximum-overall-diameter
tables must be transcribed and reviewed before they carry values.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from inductor_designer.domain.units import awg_bare_diameter_m

_CATALOG_REVISION = "round-wire-1"
_AWG_RANGE = range(10, 33)
_IEC_DIAMETERS_MM = (0.20, 0.25, 0.315, 0.40, 0.50, 0.63, 0.80, 1.00, 1.25, 1.60, 2.00, 2.50)


def _record(
    name: str, standard: str, bare_diameter_m: float, source: str
) -> dict[str, object]:
    return {
        "name": name,
        "standard": standard,
        "bareDiameterM": round(bare_diameter_m, 9),
        "grade1DiameterM": None,
        "grade2DiameterM": None,
        "source": source,
        "catalogRevision": _CATALOG_REVISION,
        "reviewStatus": "draft",
        "reviewedBy": None,
    }


def generate_records() -> list[dict[str, object]]:
    records = [
        _record(f"AWG {gauge}", "awg", awg_bare_diameter_m(gauge), "ASTM B258 formula")
        for gauge in _AWG_RANGE
    ]
    records.extend(
        _record(f"{diameter_mm:.2f} mm", "iec-60317", diameter_mm / 1000.0, "IEC 60317 nominal")
        for diameter_mm in _IEC_DIAMETERS_MM
    )
    return sorted(records, key=lambda record: str(record["name"]))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("catalog/conductors/round-wire.yaml"),
    )
    args = parser.parse_args(argv)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    document = {"records": generate_records()}
    args.out.write_text(
        "# Generated by tools/generate_conductors.py — regenerate, do not hand-edit.\n"
        + yaml.safe_dump(document, sort_keys=False),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Generate the committed file**

Run: `python -m tools.generate_conductors`
Expected: creates `catalog/conductors/round-wire.yaml` with 35 records (23 AWG + 12 metric).

- [ ] **Step 5: Run tests and gates**

Run: `python -m pytest tests/unit -q && python -m ruff check . && python -m mypy`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tools/generate_conductors.py catalog/conductors/round-wire.yaml tests/unit/tools/test_generate_conductors.py
git commit -m "feat(catalog): generate canonical round-wire conductor records"
```

---

### Task 10: Catalog builder (canonical files → SQLite)

Q6 decision A. Deterministic build, schema validation at build time, non-zero exit on any violation. No timestamps in the artifact.

**Files:**
- Create: `tools/build_catalog.py`
- Modify: `.gitignore` (add `artifacts/catalog/` if `artifacts/` is not already ignored — check first)
- Test: `tests/unit/tools/test_build_catalog.py`

**Interfaces:**
- Consumes: canonical YAML from Tasks 8–9, catalog schemas from Task 8, `record_serde` from Task 7.
- Produces: `tools.build_catalog.build(source_root: Path, schema_root: Path, out_path: Path) -> None` and `main(argv: list[str] | None = None) -> int` (CLI: `--source catalog --schemas schemas/catalog --out artifacts/catalog/catalog.sqlite`). SQLite layout consumed by Task 11:
  - `cores(part_number TEXT PRIMARY KEY, family TEXT NOT NULL, manufacturer TEXT NOT NULL, review_status TEXT NOT NULL, record_json TEXT NOT NULL)`
  - `conductors(name TEXT PRIMARY KEY, standard TEXT NOT NULL, review_status TEXT NOT NULL, record_json TEXT NOT NULL)`
  - `meta(key TEXT PRIMARY KEY, value TEXT NOT NULL)` with keys `schemaVersion` (value `"1"`), `coreCount`, `conductorCount`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/tools/test_build_catalog.py`:

```python
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
import yaml

from tools.build_catalog import build, main

ROOT = Path(__file__).resolve().parents[3]


def build_default(tmp_path: Path) -> Path:
    out = tmp_path / "catalog.sqlite"
    build(ROOT / "catalog", ROOT / "schemas" / "catalog", out)
    return out


def test_build_from_canonical_sources(tmp_path: Path) -> None:
    out = build_default(tmp_path)
    with sqlite3.connect(out) as connection:
        cores = connection.execute("SELECT COUNT(*) FROM cores").fetchone()[0]
        conductors = connection.execute("SELECT COUNT(*) FROM conductors").fetchone()[0]
        meta = dict(connection.execute("SELECT key, value FROM meta"))
    assert cores >= 15
    assert conductors == 35
    assert meta["schemaVersion"] == "1"
    assert meta["coreCount"] == str(cores)


def test_record_json_round_trips(tmp_path: Path) -> None:
    out = build_default(tmp_path)
    with sqlite3.connect(out) as connection:
        row = connection.execute(
            "SELECT record_json FROM cores WHERE part_number = ?", ("0077071A7",)
        ).fetchone()
    record = json.loads(row[0])
    assert record["partNumber"] == "0077071A7"


def test_build_is_deterministic(tmp_path: Path) -> None:
    first = build_default(tmp_path)
    second = tmp_path / "second.sqlite"
    build(ROOT / "catalog", ROOT / "schemas" / "catalog", second)
    assert first.read_bytes() == second.read_bytes()


def test_invalid_record_fails_build(tmp_path: Path) -> None:
    source = tmp_path / "catalog"
    (source / "cores").mkdir(parents=True)
    (source / "conductors").mkdir()
    (source / "cores" / "bad.yaml").write_text(
        yaml.safe_dump({"records": [{"partNumber": "X"}]}), encoding="utf-8"
    )
    (source / "conductors" / "round-wire.yaml").write_text(
        yaml.safe_dump({"records": []}), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="bad.yaml"):
        build(source, ROOT / "schemas" / "catalog", tmp_path / "out.sqlite")


def test_main_cli(tmp_path: Path) -> None:
    out = tmp_path / "cli.sqlite"
    code = main(
        [
            "--source", str(ROOT / "catalog"),
            "--schemas", str(ROOT / "schemas" / "catalog"),
            "--out", str(out),
        ]
    )
    assert code == 0
    assert out.is_file()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/tools/test_build_catalog.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement the builder**

Create `tools/build_catalog.py`:

```python
"""Compile canonical catalog YAML into the SQLite index (build artifact, never edited)."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, ValidationError

_DDL = """
CREATE TABLE cores (
    part_number TEXT PRIMARY KEY,
    family TEXT NOT NULL,
    manufacturer TEXT NOT NULL,
    review_status TEXT NOT NULL,
    record_json TEXT NOT NULL
);
CREATE TABLE conductors (
    name TEXT PRIMARY KEY,
    standard TEXT NOT NULL,
    review_status TEXT NOT NULL,
    record_json TEXT NOT NULL
);
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def _load_validator(schema_root: Path, name: str) -> Draft202012Validator:
    schema = json.loads((schema_root / name).read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def _load_records(path: Path, validator: Draft202012Validator) -> list[dict[str, Any]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("records"), list):
        raise ValueError(f"Catalog file must contain a 'records' list: {path.name}")
    records: list[dict[str, Any]] = []
    for index, record in enumerate(data["records"]):
        try:
            validator.validate(record)
        except ValidationError as error:
            raise ValueError(
                f"Invalid record {index} in {path.name}: {error.message}"
            ) from error
        records.append(record)
    return records


def build(source_root: Path, schema_root: Path, out_path: Path) -> None:
    core_validator = _load_validator(schema_root, "core.v1.schema.json")
    conductor_validator = _load_validator(schema_root, "conductor.v1.schema.json")

    cores: list[dict[str, Any]] = []
    for path in sorted((source_root / "cores").glob("*.yaml")):
        cores.extend(_load_records(path, core_validator))
    conductors: list[dict[str, Any]] = []
    for path in sorted((source_root / "conductors").glob("*.yaml")):
        conductors.extend(_load_records(path, conductor_validator))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.unlink(missing_ok=True)
    connection = sqlite3.connect(out_path)
    try:
        connection.executescript(_DDL)
        connection.executemany(
            "INSERT INTO cores VALUES (?, ?, ?, ?, ?)",
            [
                (
                    record["partNumber"],
                    record["family"],
                    record["manufacturer"],
                    record["reviewStatus"],
                    json.dumps(record, sort_keys=True),
                )
                for record in sorted(cores, key=lambda r: str(r["partNumber"]))
            ],
        )
        connection.executemany(
            "INSERT INTO conductors VALUES (?, ?, ?, ?)",
            [
                (
                    record["name"],
                    record["standard"],
                    record["reviewStatus"],
                    json.dumps(record, sort_keys=True),
                )
                for record in sorted(conductors, key=lambda r: str(r["name"]))
            ],
        )
        connection.executemany(
            "INSERT INTO meta VALUES (?, ?)",
            [
                ("schemaVersion", "1"),
                ("coreCount", str(len(cores))),
                ("conductorCount", str(len(conductors))),
            ],
        )
        connection.commit()
    finally:
        connection.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("catalog"))
    parser.add_argument("--schemas", type=Path, default=Path("schemas/catalog"))
    parser.add_argument("--out", type=Path, default=Path("artifacts/catalog/catalog.sqlite"))
    args = parser.parse_args(argv)
    build(args.source, args.schemas, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Check `.gitignore`: if `artifacts/` is not already ignored, add `artifacts/catalog/`.

Note on primary-key collisions: duplicate part numbers across files surface as `sqlite3.IntegrityError` at insert time, which fails the build — acceptable; the canonical-data test in Task 8 already asserts uniqueness for committed data.

- [ ] **Step 4: Run tests and gates**

Run: `python -m pytest tests/unit -q && python -m ruff check . && python -m mypy`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/build_catalog.py tests/unit/tools/test_build_catalog.py .gitignore
git commit -m "feat(catalog): compile canonical files into deterministic SQLite index"
```

---

### Task 11: Catalog repository port and SQLite adapter

**Files:**
- Create: `src/inductor_designer/application/ports/catalog.py`
- Create: `src/inductor_designer/adapters/catalog/__init__.py`
- Create: `src/inductor_designer/adapters/catalog/sqlite_repository.py`
- Test: `tests/unit/adapters/catalog/__init__.py`, `tests/unit/adapters/catalog/test_sqlite_repository.py`

**Interfaces:**
- Consumes: `CoreRecord`/`ConductorRecord` (Task 3), `record_serde` (Task 7), SQLite layout (Task 10).
- Produces (port, `application/ports/catalog.py`, follows the `Protocol` style of `application/ports/aedt_gateway.py`):

```python
class CatalogRepository(Protocol):
    def get_core(self, part_number: str) -> CoreRecord | None: ...
    def list_cores(self) -> tuple[CoreRecord, ...]: ...
    def get_conductor(self, name: str) -> ConductorRecord | None: ...
    def list_conductor_names(self) -> tuple[str, ...]: ...
```

- Produces (adapter): `SqliteCatalogRepository(path: Path)` implementing the port; raises `FileNotFoundError` from the constructor when the index file does not exist.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/adapters/catalog/__init__.py` (empty) and `tests/unit/adapters/catalog/test_sqlite_repository.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from inductor_designer.adapters.catalog.sqlite_repository import SqliteCatalogRepository
from inductor_designer.application.ports.catalog import CatalogRepository
from tools.build_catalog import build

ROOT = Path(__file__).resolve().parents[4]


@pytest.fixture(scope="module")
def index_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("catalog") / "catalog.sqlite"
    build(ROOT / "catalog", ROOT / "schemas" / "catalog", out)
    return out


def test_adapter_satisfies_port(index_path: Path) -> None:
    repository: CatalogRepository = SqliteCatalogRepository(index_path)
    assert repository is not None


def test_get_core(index_path: Path) -> None:
    repository = SqliteCatalogRepository(index_path)
    core = repository.get_core("0077071A7")
    assert core is not None
    assert core.material.name == "Kool Mu"
    assert repository.get_core("does-not-exist") is None


def test_list_cores_sorted(index_path: Path) -> None:
    cores = SqliteCatalogRepository(index_path).list_cores()
    part_numbers = [core.part_number for core in cores]
    assert len(part_numbers) >= 15
    assert part_numbers == sorted(part_numbers)


def test_conductors(index_path: Path) -> None:
    repository = SqliteCatalogRepository(index_path)
    names = repository.list_conductor_names()
    assert "AWG 18" in names
    wire = repository.get_conductor("AWG 18")
    assert wire is not None and wire.bare_diameter_m == pytest.approx(0.00102362, rel=1e-3)


def test_missing_index_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        SqliteCatalogRepository(tmp_path / "missing.sqlite")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/adapters/catalog -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement port and adapter**

Create `src/inductor_designer/application/ports/catalog.py`:

```python
from __future__ import annotations

from typing import Protocol

from inductor_designer.domain.catalog_records import ConductorRecord, CoreRecord


class CatalogRepository(Protocol):
    """Read access to the compiled commercial catalog index."""

    def get_core(self, part_number: str) -> CoreRecord | None: ...

    def list_cores(self) -> tuple[CoreRecord, ...]: ...

    def get_conductor(self, name: str) -> ConductorRecord | None: ...

    def list_conductor_names(self) -> tuple[str, ...]: ...
```

Create `src/inductor_designer/adapters/catalog/__init__.py` (empty) and `src/inductor_designer/adapters/catalog/sqlite_repository.py`:

```python
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from inductor_designer.adapters.persistence.record_serde import (
    conductor_record_from_json,
    core_record_from_json,
)
from inductor_designer.domain.catalog_records import ConductorRecord, CoreRecord


class SqliteCatalogRepository:
    def __init__(self, path: Path) -> None:
        if not path.is_file():
            raise FileNotFoundError(f"Catalog index not found: {path}")
        self._path = path

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(f"file:{self._path.as_posix()}?mode=ro", uri=True)

    def get_core(self, part_number: str) -> CoreRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT record_json FROM cores WHERE part_number = ?", (part_number,)
            ).fetchone()
        return core_record_from_json(json.loads(row[0])) if row else None

    def list_cores(self) -> tuple[CoreRecord, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT record_json FROM cores ORDER BY part_number"
            ).fetchall()
        return tuple(core_record_from_json(json.loads(row[0])) for row in rows)

    def get_conductor(self, name: str) -> ConductorRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT record_json FROM conductors WHERE name = ?", (name,)
            ).fetchone()
        return conductor_record_from_json(json.loads(row[0])) if row else None

    def list_conductor_names(self) -> tuple[str, ...]:
        with self._connect() as connection:
            rows = connection.execute("SELECT name FROM conductors ORDER BY name").fetchall()
        return tuple(row[0] for row in rows)
```

- [ ] **Step 4: Run tests and gates**

Run: `python -m pytest tests/unit -q && python -m ruff check . && python -m mypy && python tools/check_architecture.py`
Expected: PASS. The architecture check must confirm `application/ports/catalog.py` imports no `sqlite3`.

- [ ] **Step 5: Commit**

```bash
git add src/inductor_designer/application/ports/catalog.py src/inductor_designer/adapters/catalog tests/unit/adapters/catalog
git commit -m "feat(catalog): add catalog repository port and read-only SQLite adapter"
```

---

### Task 12: Snapshot selection, revision comparison, and adoption services

Q7 decision A: both halves, headless.

**Files:**
- Create: `src/inductor_designer/application/services/__init__.py`
- Create: `src/inductor_designer/application/services/catalog_revisions.py`
- Test: `tests/unit/application/__init__.py`, `tests/unit/application/test_catalog_revisions.py`

**Interfaces:**
- Consumes: `InductorProject`, `CatalogCoreSelection` (Task 4), `CatalogRepository` port (Task 11), `CoreRecord` (Task 3).
- Produces:
  - `select_core(project: InductorProject, repository: CatalogRepository, part_number: str) -> InductorProject` — returns a new project whose `core` is a `CatalogCoreSelection` with a fresh snapshot and no overrides; raises `LookupError` when the part is unknown.
  - `SnapshotStatus` (str Enum: `UNCHANGED = "unchanged"`, `CHANGED = "changed"`, `MISSING = "missing"`).
  - `FieldChange(field: str, old: object, new: object)` — frozen.
  - `CatalogComparison(part_number: str, status: SnapshotStatus, changes: tuple[FieldChange, ...])` — frozen.
  - `compare_core_snapshot(project: InductorProject, repository: CatalogRepository) -> CatalogComparison | None` — `None` when the project has no catalog selection; field-by-field diff of the snapshot against the current record.
  - `adopt_core_revision(project: InductorProject, repository: CatalogRepository) -> InductorProject` — replaces the snapshot with the current record, keeps part number and overrides; raises `LookupError` when the part vanished or the project has no catalog selection.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/application/__init__.py` (empty) and `tests/unit/application/test_catalog_revisions.py`:

```python
from __future__ import annotations

import dataclasses

import pytest

from inductor_designer.application.services.catalog_revisions import (
    SnapshotStatus,
    adopt_core_revision,
    compare_core_snapshot,
    select_core,
)
from inductor_designer.domain.catalog_records import ConductorRecord, CoreRecord
from inductor_designer.domain.project import CatalogCoreSelection
from tests.unit.domain.test_catalog_records import make_core
from tests.unit.domain.test_project import make_project


class FakeCatalog:
    def __init__(self, cores: dict[str, CoreRecord]) -> None:
        self._cores = cores

    def get_core(self, part_number: str) -> CoreRecord | None:
        return self._cores.get(part_number)

    def list_cores(self) -> tuple[CoreRecord, ...]:
        return tuple(self._cores.values())

    def get_conductor(self, name: str) -> ConductorRecord | None:
        return None

    def list_conductor_names(self) -> tuple[str, ...]:
        return ()


def test_select_core_snapshots_current_record() -> None:
    catalog = FakeCatalog({"0077071A7": make_core()})
    project = select_core(make_project(core=None), catalog, "0077071A7")
    assert isinstance(project.core, CatalogCoreSelection)
    assert project.core.snapshot == make_core()
    assert project.core.overrides == ()


def test_select_core_unknown_part_raises() -> None:
    with pytest.raises(LookupError, match="0099999A9"):
        select_core(make_project(core=None), FakeCatalog({}), "0099999A9")


def test_compare_unchanged() -> None:
    catalog = FakeCatalog({"0077071A7": make_core()})
    comparison = compare_core_snapshot(make_project(), catalog)
    assert comparison is not None
    assert comparison.status is SnapshotStatus.UNCHANGED
    assert comparison.changes == ()


def test_compare_detects_changed_field() -> None:
    changed = dataclasses.replace(make_core(), al_value_nh=56.0)
    comparison = compare_core_snapshot(make_project(), FakeCatalog({"0077071A7": changed}))
    assert comparison is not None
    assert comparison.status is SnapshotStatus.CHANGED
    assert any(change.field == "al_value_nh" for change in comparison.changes)


def test_compare_missing_part() -> None:
    comparison = compare_core_snapshot(make_project(), FakeCatalog({}))
    assert comparison is not None
    assert comparison.status is SnapshotStatus.MISSING


def test_compare_returns_none_without_catalog_selection() -> None:
    catalog = FakeCatalog({"0077071A7": make_core()})
    assert compare_core_snapshot(make_project(core=None), catalog) is None


def test_adopt_rewrites_snapshot_and_keeps_overrides() -> None:
    changed = dataclasses.replace(make_core(), al_value_nh=56.0)
    adopted = adopt_core_revision(make_project(), FakeCatalog({"0077071A7": changed}))
    assert isinstance(adopted.core, CatalogCoreSelection)
    assert adopted.core.snapshot.al_value_nh == 56.0


def test_adopt_missing_part_raises() -> None:
    with pytest.raises(LookupError, match="0077071A7"):
        adopt_core_revision(make_project(), FakeCatalog({}))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/application -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement the services**

Create `src/inductor_designer/application/services/__init__.py` (empty) and `src/inductor_designer/application/services/catalog_revisions.py`:

```python
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from enum import Enum

from inductor_designer.application.ports.catalog import CatalogRepository
from inductor_designer.domain.catalog_records import CoreRecord
from inductor_designer.domain.project import CatalogCoreSelection, InductorProject


class SnapshotStatus(str, Enum):
    UNCHANGED = "unchanged"
    CHANGED = "changed"
    MISSING = "missing"


@dataclass(frozen=True, slots=True)
class FieldChange:
    field: str
    old: object
    new: object


@dataclass(frozen=True, slots=True)
class CatalogComparison:
    part_number: str
    status: SnapshotStatus
    changes: tuple[FieldChange, ...]


def select_core(
    project: InductorProject, repository: CatalogRepository, part_number: str
) -> InductorProject:
    record = repository.get_core(part_number)
    if record is None:
        raise LookupError(f"Core not found in catalog: {part_number}")
    selection = CatalogCoreSelection(part_number=part_number, snapshot=record, overrides=())
    return dataclasses.replace(project, core=selection)


def _diff(snapshot: CoreRecord, current: CoreRecord) -> tuple[FieldChange, ...]:
    changes: list[FieldChange] = []
    for field in dataclasses.fields(CoreRecord):
        old = getattr(snapshot, field.name)
        new = getattr(current, field.name)
        if old != new:
            changes.append(FieldChange(field.name, old, new))
    return tuple(changes)


def compare_core_snapshot(
    project: InductorProject, repository: CatalogRepository
) -> CatalogComparison | None:
    core = project.core
    if not isinstance(core, CatalogCoreSelection):
        return None
    current = repository.get_core(core.part_number)
    if current is None:
        return CatalogComparison(core.part_number, SnapshotStatus.MISSING, ())
    changes = _diff(core.snapshot, current)
    status = SnapshotStatus.CHANGED if changes else SnapshotStatus.UNCHANGED
    return CatalogComparison(core.part_number, status, changes)


def adopt_core_revision(
    project: InductorProject, repository: CatalogRepository
) -> InductorProject:
    core = project.core
    if not isinstance(core, CatalogCoreSelection):
        raise LookupError("Project has no catalog core selection to update")
    current = repository.get_core(core.part_number)
    if current is None:
        raise LookupError(f"Core no longer exists in catalog: {core.part_number}")
    updated = dataclasses.replace(core, snapshot=current)
    return dataclasses.replace(project, core=updated)
```

- [ ] **Step 4: Run tests and gates**

Run: `python -m pytest tests/unit -q && python -m ruff check . && python -m mypy && python tools/check_architecture.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/inductor_designer/application/services tests/unit/application
git commit -m "feat(application): add core selection, revision comparison, and adoption services"
```

---

### Task 13: Milestone exit integration test, docs, and handoff

The exit criterion end to end: build catalog → select core → define multiple valid windings → validate → save → reload → equal; then catalog change → compare → adopt.

**Files:**
- Create: `tests/integration/test_project_round_trip.py` (plus `tests/integration/__init__.py` if missing)
- Modify: `docs/development/ROADMAP.md`, `docs/superpowers/plans/README.md`, `README.md`

**Interfaces:**
- Consumes: everything from Tasks 1–12. No new production code.

- [ ] **Step 1: Write the integration test**

Create `tests/integration/test_project_round_trip.py` (add empty `tests/integration/__init__.py` if the directory lacks one):

```python
from __future__ import annotations

import dataclasses
import json
import sqlite3
from pathlib import Path

import pytest

from inductor_designer.adapters.catalog.sqlite_repository import SqliteCatalogRepository
from inductor_designer.adapters.persistence.project_repository import ProjectRepository
from inductor_designer.adapters.persistence.record_serde import (
    core_record_from_json,
    core_record_to_json,
)
from inductor_designer.adapters.persistence.schema_repository import SchemaRepository
from inductor_designer.application.services.catalog_revisions import (
    SnapshotStatus,
    adopt_core_revision,
    compare_core_snapshot,
    select_core,
)
from inductor_designer.domain.aedt_target import AedtEdition, AedtRelease, ModelDimension
from inductor_designer.domain.project import CatalogCoreSelection, InductorProject
from inductor_designer.domain.validation import ValidationCategory, validate_project
from inductor_designer.domain.winding import (
    ConductorMode,
    CurrentDirection,
    WindingDefinition,
    WindingDirection,
)
from tools.build_catalog import build

ROOT = Path(__file__).resolve().parents[2]


def make_winding(winding_id: str, start_angle_deg: float) -> WindingDefinition:
    return WindingDefinition(
        winding_id=winding_id,
        label=winding_id,
        turns=15,
        conductor_name="AWG 18",
        mode=ConductorMode.SOLID,
        start_angle_deg=start_angle_deg,
        sector_deg=150.0,
        min_spacing_m=0.0002,
        min_clearance_m=0.001,
        winding_direction=WindingDirection.CLOCKWISE,
        current_direction=CurrentDirection.FORWARD,
        terminal_intent="",
        ac_magnitude_a=2.0,
        ac_phase_deg=0.0,
        frequency_hz=100_000.0,
        dc_current_a=5.0,
    )


def test_milestone_1_exit_criterion(tmp_path: Path) -> None:
    index = tmp_path / "catalog.sqlite"
    build(ROOT / "catalog", ROOT / "schemas" / "catalog", index)
    catalog = SqliteCatalogRepository(index)

    empty = InductorProject(
        project_id="3f0e8f5e-8f4e-4a5e-9d5b-6c4f2b1a0d9c",
        name="M1 exit project",
        description="",
        target_release=AedtRelease(2025, 2),
        target_edition=AedtEdition.COMMERCIAL,
        dimension_mode=ModelDimension.THREE_D,
        core=None,
        windings=(),
    )
    project = select_core(empty, catalog, "0077071A7")
    project = dataclasses.replace(
        project, windings=(make_winding("w1", 0.0), make_winding("w2", 180.0))
    )

    issues = validate_project(project, known_conductors=catalog.list_conductor_names())
    assert not [i for i in issues if i.category is ValidationCategory.ERROR]

    repo = ProjectRepository(SchemaRepository(ROOT / "schemas"))
    path = tmp_path / "exit.inductor.json"
    repo.save(project, path)
    assert repo.load(path) == project

    comparison = compare_core_snapshot(project, catalog)
    assert comparison is not None and comparison.status is SnapshotStatus.UNCHANGED

    with sqlite3.connect(index) as connection:
        row = connection.execute(
            "SELECT record_json FROM cores WHERE part_number = ?", ("0077071A7",)
        ).fetchone()
        record = core_record_from_json(json.loads(row[0]))
        changed = dataclasses.replace(record, al_value_nh=record.al_value_nh + 5.0)
        connection.execute(
            "UPDATE cores SET record_json = ? WHERE part_number = ?",
            (json.dumps(core_record_to_json(changed), sort_keys=True), "0077071A7"),
        )
        connection.commit()

    comparison = compare_core_snapshot(project, catalog)
    assert comparison is not None and comparison.status is SnapshotStatus.CHANGED

    adopted = adopt_core_revision(project, catalog)
    assert isinstance(adopted.core, CatalogCoreSelection)
    assert adopted.core.snapshot.al_value_nh == pytest.approx(record.al_value_nh + 5.0)
    repo.save(adopted, path)
    assert repo.load(path) == adopted
```

- [ ] **Step 2: Run the integration test**

Run: `python -m pytest tests/integration/test_project_round_trip.py -q`
Expected: PASS.

- [ ] **Step 3: Run the complete gate set**

Run: `python -m pytest tests -q -m "not aedt and not ui" --cov --cov-branch && python -m ruff check . && python -m mypy && python tools/check_architecture.py`
Expected: all tests pass, coverage >= 80%, no lint/type/architecture findings. (Use the exact non-AEDT test invocation the CI workflow in `.github/workflows/` defines, if it differs.)

- [ ] **Step 4: Update documentation status**

- `docs/development/ROADMAP.md`: under "Milestone 1: Toroid domain and catalogs", add a "Current state" subsection listing the implemented deliverables (domain model, validation, schema v2 + migration, catalog schemas and draft seed data, conductor generator, SQLite pipeline, catalog port/adapter, snapshot comparison services, exit integration test) and one explicit remaining-work line: "Catalog numeric values remain `draft` pending human review against the cited Magnetics sources; insulated wire diameters are intentionally null until Milestone 2 consumes them."
- `docs/superpowers/plans/README.md`: point the Milestone 1 row's "Detailed plan" cell at `2026-07-13-toroid-domain-and-catalogs.md` and update the status line above the table.
- `README.md`: update the project status paragraph to state Milestone 1 implementation status and keep the accepted-M0 statement.

- [ ] **Step 5: Commit and handoff**

```bash
git add tests/integration docs/development/ROADMAP.md docs/superpowers/plans/README.md README.md
git commit -m "test(integration): prove Milestone 1 exit criterion and update status docs"
```

Handoff summary for review: Milestone 1 exit criterion is exercised by `tests/integration/test_project_round_trip.py`; catalog data review (draft → reviewed) is an explicitly human follow-up; the Milestone 2 plan is written only after this milestone's review is accepted.

---

## Milestone 1 acceptance criteria

- A v2 project document validates, and a v1 document migrates to v2 and validates.
- `ProjectRepository.save`/`load` round-trips a project with a catalog core selection and at least two windings, byte-identical on repeated saves.
- `validate_project` reports the four spec categories and flags sector overlap, including wraparound sectors.
- `tools/build_catalog.py` compiles the canonical YAML into a deterministic SQLite index and fails with non-zero exit on any schema-invalid record.
- `SqliteCatalogRepository` serves core and conductor records through the `CatalogRepository` port; no inner module imports `sqlite3`.
- `compare_core_snapshot` distinguishes unchanged/changed/missing, and `adopt_core_revision` rewrites the snapshot explicitly — never silently.
- All catalog seed records are schema-valid and carry `reviewStatus: draft` until a human reviewer verifies them against the cited Magnetics sources.
- Non-AEDT gates pass: pytest with >= 80% branch coverage, Ruff, mypy strict, architecture checker.
- No AEDT interaction exists in this milestone; controlled-AEDT validation is not required for M1 acceptance.
