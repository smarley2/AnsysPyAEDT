# Milestone 2: Geometry and Live Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deterministic solver-independent toroid and multi-layer winding geometry — packing, collisions, leads, naming, symmetry proof, 2D equivalent, manifest — rendered in the Guided Studio Qt Quick 3D preview from the same intermediate model.

**Architecture:** A pure `geometry` package (no Qt/PyAEDT/sqlite/OS imports) computes everything analytically from finished core dimensions and insulated wire diameters: concentric-shell multi-layer packing, planar D-shaped turn paths with outer-face connectors, clearance checks, a data-level symmetry plan, a 2D top-view equivalent, and a canonical JSON manifest with committed goldens. An application service composes project + catalog into a `GeometryModel`; the UI adapter tessellates it into triangle meshes for Qt Quick 3D — viewer only, no editing.

**Tech Stack:** Python 3.10–3.13 stdlib math, `hypothesis` (dev-only) for property tests, PySide6 `QQuick3DGeometry` for the preview.

## Global Constraints

- Python `>=3.10,<3.14`; mypy `strict = true` over `src` and `tools`; Ruff line length 100 with `E,F,I,B,UP,ANN,SIM`; branch coverage `fail_under = 80`.
- Architecture rules enforced by `tools/check_architecture.py`: `domain`, `geometry`, `materials`, `simulation` never import PySide6/ansys/pyaedt/sqlite3/os/pathlib/etc.; `application` never imports PySide6/ansys/pyaedt/sqlite3. Run it after every task touching inner packages.
- No new runtime dependencies. `hypothesis` goes in the `dev` extra only.
- Every file starts with `from __future__ import annotations`. Frozen slots dataclasses with `__post_init__` for hard invariants, matching `src/inductor_designer/domain/`.
- Units: meters, degrees, amperes, hertz. Public geometry APIs take degrees; radians stay internal.
- Coordinate convention (document, never change): toroid axis = **Z**; the core is centered on the origin; the radial half-plane at angle θ contains direction `(cos θ, sin θ, 0)`; angles increase counter-clockwise viewed from +Z.
- **Finished-dimension rule** (ROADMAP M2 design note): geometry consumes `innerDiameter.minM`, `outerDiameter.maxM`, `height.maxM` when present, falling back to `nominalM`; manual cores and override values are used as-is (treated as finished). Never build winding geometry from a catalog core's `nominalM` when a finish bound exists.
- **Insulated-diameter rule** (Q-decision): packing uses the conductor's grade 2 insulated diameter, falling back to grade 1; a conductor with both null cannot be packed — typed error, never a silent bare-diameter fallback.
- Determinism: every float that reaches a manifest, name, or golden file is rounded with `round(x, 9)`. Identical inputs must produce byte-identical manifests.
- All insulation data added in this milestone carries `reviewStatus: draft` until a human verifies it against IEC 60317-0-1 / NEMA MW1000; draft values must never be presented as verified.
- Environment: use the project venv for all commands: `.venv\Scripts\python.exe`. Gates: `-m pytest tests -q -m "not aedt and not ui"`, `-m ruff check .`, `-m mypy`, `tools/check_architecture.py`. The `ui`-marked tests run in the tasks that touch the UI (they need PySide6, which is installed in the venv).
- Conventional commits. Don't stage unrelated files (`batch.log` stays untracked).

## Locked design decisions (from review with Fabio Posser, 2026-07-14)

1. **Multi-layer packing, concentric-shell model.** Layer k's wire centers sit at radial build `b_k = (k − 0.5)·d` off every finished core face (`d` = insulated diameter). A layer opens only when the previous one is full at minimum pitch. Bank-style deterministic winding, not a physical winding simulation.
2. **Planar D-shaped turns.** Each turn lies in the radial half-plane at its station angle: 4 straight runs (inner wall, top, outer wall, bottom) joined by 4 corner arcs of radius `c + b_k` (`c` = core corner radius). Angular advance happens in a horizontal connector arc on the outer face at z = 0. Leads are radial stubs at the first/last station.
3. **Preview = viewer, not editor.** Load a project file, render core + windings with orbit camera; no parameter editing.
4. **`hypothesis` for property-based tests** (dev extra).
5. **Symmetry is data-level.** `propose_symmetry_plan` proves periodicity and returns a `SymmetryPlan` or a typed refusal; no geometry cutting in M2.

---

### Task 1: Insulation data and hypothesis dependency

Packing consumes insulated diameters; they are currently null. Add the canonical insulation file (draft values), merge it in the conductor generator, regenerate the committed conductor catalog, and add `hypothesis` to the dev extra.

**Files:**
- Create: `catalog/conductors/insulation-round-wire.yaml`
- Modify: `tools/generate_conductors.py`
- Modify: `pyproject.toml` (dev extra)
- Test: `tests/unit/tools/test_generate_conductors.py` (extend)

**Interfaces:**
- Produces: regenerated `catalog/conductors/round-wire.yaml` where every record's `grade1DiameterM`/`grade2DiameterM` is populated (drafts) — consumed by packing via `ConductorRecord.grade2_diameter_m`.
- Produces: `hypothesis>=6.100,<7` importable in tests.

> **DATA WARNING:** the insulation values below are DRAFT transcriptions from IEC 60317-0-1 (metric, grade 1/2 maximum overall diameter) and NEMA MW1000 (AWG, single/heavy build maximum overall diameter). They MUST be verified by a human reviewer before `reviewStatus` flips to `reviewed`. M2 only needs them present and plausible; wrong values change packing results, not code correctness.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/tools/test_generate_conductors.py`:

```python
def test_all_records_have_insulated_diameters() -> None:
    for record in generate_records():
        assert record["grade1DiameterM"] is not None, record["name"]
        assert record["grade2DiameterM"] is not None, record["name"]
        bare = record["bareDiameterM"]
        assert bare < record["grade1DiameterM"] < record["grade2DiameterM"]  # type: ignore[operator]


def test_insulation_file_covers_every_conductor() -> None:
    insulation = yaml.safe_load(
        (ROOT / "catalog/conductors/insulation-round-wire.yaml").read_text(encoding="utf-8")
    )
    names = {entry["name"] for entry in insulation["records"]}
    generated = {record["name"] for record in generate_records()}
    assert generated <= names
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/tools/test_generate_conductors.py -q`
Expected: FAIL — insulation file missing, `grade1DiameterM` is None.

- [ ] **Step 3: Create the canonical insulation file**

Create `catalog/conductors/insulation-round-wire.yaml`. Full file — 35 entries, values in meters:

```yaml
# DRAFT transcription. Metric rows: IEC 60317-0-1 grade 1 / grade 2 maximum
# overall diameter. AWG rows: NEMA MW1000 single / heavy build maximum overall
# diameter. Verify every value against the standard before flipping
# reviewStatus to reviewed. Names must match catalog/conductors/round-wire.yaml.
source: IEC 60317-0-1 (metric) and NEMA MW1000 (AWG) maximum overall diameters
reviewStatus: draft
reviewedBy: null
records:
  - {name: "0.2 mm",  grade1DiameterM: 0.000222, grade2DiameterM: 0.000239}
  - {name: "0.25 mm", grade1DiameterM: 0.000275, grade2DiameterM: 0.000297}
  - {name: "0.315 mm", grade1DiameterM: 0.000342, grade2DiameterM: 0.000367}
  - {name: "0.4 mm",  grade1DiameterM: 0.000431, grade2DiameterM: 0.000459}
  - {name: "0.5 mm",  grade1DiameterM: 0.000536, grade2DiameterM: 0.000566}
  - {name: "0.63 mm", grade1DiameterM: 0.000671, grade2DiameterM: 0.000704}
  - {name: "0.8 mm",  grade1DiameterM: 0.000845, grade2DiameterM: 0.000881}
  - {name: "1 mm",    grade1DiameterM: 0.001050, grade2DiameterM: 0.001089}
  - {name: "1.25 mm", grade1DiameterM: 0.001305, grade2DiameterM: 0.001349}
  - {name: "1.6 mm",  grade1DiameterM: 0.001659, grade2DiameterM: 0.001706}
  - {name: "2 mm",    grade1DiameterM: 0.002061, grade2DiameterM: 0.002112}
  - {name: "2.5 mm",  grade1DiameterM: 0.002567, grade2DiameterM: 0.002622}
  - {name: "AWG 10", grade1DiameterM: 0.002643, grade2DiameterM: 0.002721}
  - {name: "AWG 11", grade1DiameterM: 0.002363, grade2DiameterM: 0.002435}
  - {name: "AWG 12", grade1DiameterM: 0.002113, grade2DiameterM: 0.002182}
  - {name: "AWG 13", grade1DiameterM: 0.001885, grade2DiameterM: 0.001946}
  - {name: "AWG 14", grade1DiameterM: 0.001681, grade2DiameterM: 0.001737}
  - {name: "AWG 15", grade1DiameterM: 0.001501, grade2DiameterM: 0.001554}
  - {name: "AWG 16", grade1DiameterM: 0.001341, grade2DiameterM: 0.001392}
  - {name: "AWG 17", grade1DiameterM: 0.001199, grade2DiameterM: 0.001247}
  - {name: "AWG 18", grade1DiameterM: 0.001072, grade2DiameterM: 0.001118}
  - {name: "AWG 19", grade1DiameterM: 0.000958, grade2DiameterM: 0.001001}
  - {name: "AWG 20", grade1DiameterM: 0.000856, grade2DiameterM: 0.000897}
  - {name: "AWG 21", grade1DiameterM: 0.000767, grade2DiameterM: 0.000805}
  - {name: "AWG 22", grade1DiameterM: 0.000688, grade2DiameterM: 0.000723}
  - {name: "AWG 23", grade1DiameterM: 0.000615, grade2DiameterM: 0.000649}
  - {name: "AWG 24", grade1DiameterM: 0.000552, grade2DiameterM: 0.000583}
  - {name: "AWG 25", grade1DiameterM: 0.000494, grade2DiameterM: 0.000524}
  - {name: "AWG 26", grade1DiameterM: 0.000442, grade2DiameterM: 0.000470}
  - {name: "AWG 27", grade1DiameterM: 0.000397, grade2DiameterM: 0.000424}
  - {name: "AWG 28", grade1DiameterM: 0.000355, grade2DiameterM: 0.000380}
  - {name: "AWG 29", grade1DiameterM: 0.000319, grade2DiameterM: 0.000343}
  - {name: "AWG 30", grade1DiameterM: 0.000285, grade2DiameterM: 0.000308}
  - {name: "AWG 31", grade1DiameterM: 0.000257, grade2DiameterM: 0.000279}
  - {name: "AWG 32", grade1DiameterM: 0.000231, grade2DiameterM: 0.000251}
```

Note: metric names must match the exact `:g`-formatted names the generator emits (`"0.2 mm"`, `"1 mm"`, `"2.5 mm"` — check `catalog/conductors/round-wire.yaml` for the authoritative spelling and adjust the insulation file to match if any differ).

- [ ] **Step 4: Merge insulation in the generator**

Modify `tools/generate_conductors.py`. Replace the `_record` helper and `generate_records` with:

```python
_INSULATION_PATH = Path("catalog/conductors/insulation-round-wire.yaml")


def _load_insulation(path: Path) -> dict[str, tuple[float, float]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return {
        entry["name"]: (entry["grade1DiameterM"], entry["grade2DiameterM"])
        for entry in data["records"]
    }


def _record(
    name: str,
    standard: str,
    bare_diameter_m: float,
    source: str,
    insulation: dict[str, tuple[float, float]],
) -> dict[str, object]:
    grades = insulation.get(name)
    return {
        "name": name,
        "standard": standard,
        "bareDiameterM": round(bare_diameter_m, 9),
        "grade1DiameterM": grades[0] if grades else None,
        "grade2DiameterM": grades[1] if grades else None,
        "source": source,
        "catalogRevision": _CATALOG_REVISION,
        "reviewStatus": "draft",
        "reviewedBy": None,
    }


def generate_records(insulation_path: Path = _INSULATION_PATH) -> list[dict[str, object]]:
    insulation = _load_insulation(insulation_path)
    records = [
        _record(f"AWG {g}", "awg", awg_bare_diameter_m(g), "ASTM B258 formula", insulation)
        for g in _AWG_RANGE
    ]
    records.extend(
        _record(f"{d:g} mm", "iec-60317", d / 1000.0, "IEC 60317 nominal", insulation)
        for d in _IEC_DIAMETERS_MM
    )
    return sorted(records, key=lambda record: str(record["name"]))
```

(Keep `main()` as-is; it calls `generate_records()`. Adjust the name-format expression to match the current file exactly — the metric name format was changed to `:g` in commit 1421443.)

Bump `_CATALOG_REVISION` to `"round-wire-2"` — the records' content changed.

- [ ] **Step 5: Add hypothesis to the dev extra**

In `pyproject.toml` dev extra, after the `ruff` line, add:

```toml
  "hypothesis>=6.100,<7",
```

Install: `uv pip install -e ".[dev,ui]" --python .venv\Scripts\python.exe`

- [ ] **Step 6: Regenerate the committed conductor catalog**

Run: `.venv\Scripts\python.exe -m tools.generate_conductors`
Expected: rewrites `catalog/conductors/round-wire.yaml`; every record gains insulated diameters and `catalogRevision: round-wire-2`.

- [ ] **Step 7: Run tests and gates**

Run: `.venv\Scripts\python.exe -m pytest tests -q -m "not aedt and not ui" && .venv\Scripts\python.exe -m ruff check . && .venv\Scripts\python.exe -m mypy && .venv\Scripts\python.exe tools/check_architecture.py`
Expected: PASS — including the sqlite adapter and integration tests, which rebuild the catalog from the regenerated canonical files.

- [ ] **Step 8: Commit**

```bash
git add catalog/conductors tools/generate_conductors.py pyproject.toml tests/unit/tools/test_generate_conductors.py
git commit -m "feat(catalog): add draft IEC/NEMA insulation data and populate conductor records"
```

---

### Task 2: Geometry primitives

**Files:**
- Create: `src/inductor_designer/geometry/primitives.py`
- Test: `tests/unit/geometry/__init__.py`, `tests/unit/geometry/test_primitives.py`

**Interfaces:**
- Produces:
  - `Vec3(x: float, y: float, z: float)` — frozen; `__add__`, `__sub__`, `scaled(k: float)`, `dot(o)`, `cross(o)`, `norm()`, `normalized()` (raises `ValueError` on zero length), `rounded()` (returns Vec3 with each component `round(_, 9)`).
  - `LineSegment(start: Vec3, end: Vec3)` — frozen; `length()`; `sample(count: int) -> tuple[Vec3, ...]` (count ≥ 2, endpoints inclusive).
  - `ArcSegment(center: Vec3, normal: Vec3, start: Vec3, sweep_rad: float)` — frozen; circular arc from `start` rotating around axis `normal` (unit, through `center`) by `sweep_rad` (signed, right-hand rule); `radius()`, `end()`, `length() = |sweep|·radius`, `sample(count)` via Rodrigues rotation.
  - `PathSegment = LineSegment | ArcSegment` (type alias).
  - `path_length(segments: Sequence[PathSegment]) -> float`.
  - `sample_path(segments: Sequence[PathSegment], max_arc_step_rad: float = 0.26) -> tuple[Vec3, ...]` — lines contribute endpoints, arcs contribute `ceil(|sweep|/step)+1` points; consecutive duplicates removed.
  - `half_plane_point(theta_deg: float, r: float, z: float) -> Vec3` = `(r·cosθ, r·sinθ, z)`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/geometry/__init__.py` (empty) and `tests/unit/geometry/test_primitives.py`:

```python
from __future__ import annotations

import math

import pytest

from inductor_designer.geometry.primitives import (
    ArcSegment,
    LineSegment,
    Vec3,
    half_plane_point,
    path_length,
    sample_path,
)


def test_vec3_algebra() -> None:
    a = Vec3(1.0, 2.0, 3.0)
    b = Vec3(4.0, 5.0, 6.0)
    assert a + b == Vec3(5.0, 7.0, 9.0)
    assert b - a == Vec3(3.0, 3.0, 3.0)
    assert a.scaled(2.0) == Vec3(2.0, 4.0, 6.0)
    assert a.dot(b) == pytest.approx(32.0)
    assert Vec3(1.0, 0.0, 0.0).cross(Vec3(0.0, 1.0, 0.0)) == Vec3(0.0, 0.0, 1.0)
    assert Vec3(3.0, 4.0, 0.0).norm() == pytest.approx(5.0)
    assert Vec3(0.0, 0.0, 2.0).normalized() == Vec3(0.0, 0.0, 1.0)


def test_normalized_rejects_zero() -> None:
    with pytest.raises(ValueError, match="zero"):
        Vec3(0.0, 0.0, 0.0).normalized()


def test_line_segment() -> None:
    seg = LineSegment(Vec3(0.0, 0.0, 0.0), Vec3(3.0, 0.0, 4.0))
    assert seg.length() == pytest.approx(5.0)
    points = seg.sample(3)
    assert points[0] == seg.start and points[-1] == seg.end
    assert points[1] == Vec3(1.5, 0.0, 2.0)


def test_arc_quarter_circle() -> None:
    arc = ArcSegment(
        center=Vec3(0.0, 0.0, 0.0),
        normal=Vec3(0.0, 0.0, 1.0),
        start=Vec3(1.0, 0.0, 0.0),
        sweep_rad=math.pi / 2,
    )
    assert arc.radius() == pytest.approx(1.0)
    assert arc.length() == pytest.approx(math.pi / 2)
    end = arc.end()
    assert end.x == pytest.approx(0.0, abs=1e-12)
    assert end.y == pytest.approx(1.0)


def test_arc_negative_sweep() -> None:
    arc = ArcSegment(Vec3(0.0, 0.0, 0.0), Vec3(0.0, 0.0, 1.0), Vec3(1.0, 0.0, 0.0), -math.pi / 2)
    assert arc.end().y == pytest.approx(-1.0)
    assert arc.length() == pytest.approx(math.pi / 2)


def test_path_helpers() -> None:
    line = LineSegment(Vec3(0.0, 0.0, 0.0), Vec3(1.0, 0.0, 0.0))
    arc = ArcSegment(Vec3(1.0, 1.0, 0.0), Vec3(0.0, 0.0, 1.0), Vec3(1.0, 0.0, 0.0), math.pi / 2)
    total = path_length([line, arc])
    assert total == pytest.approx(1.0 + math.pi / 2)
    points = sample_path([line, arc])
    assert points[0] == Vec3(0.0, 0.0, 0.0)
    assert len(points) >= 4
    assert all(points[i] != points[i + 1] for i in range(len(points) - 1))


def test_half_plane_point() -> None:
    p = half_plane_point(90.0, 2.0, 0.5)
    assert p.x == pytest.approx(0.0, abs=1e-12)
    assert p.y == pytest.approx(2.0)
    assert p.z == 0.5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/geometry -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

Create `src/inductor_designer/geometry/primitives.py`:

```python
from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Vec3:
    x: float
    y: float
    z: float

    def __add__(self, other: Vec3) -> Vec3:
        return Vec3(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: Vec3) -> Vec3:
        return Vec3(self.x - other.x, self.y - other.y, self.z - other.z)

    def scaled(self, k: float) -> Vec3:
        return Vec3(self.x * k, self.y * k, self.z * k)

    def dot(self, other: Vec3) -> float:
        return self.x * other.x + self.y * other.y + self.z * other.z

    def cross(self, other: Vec3) -> Vec3:
        return Vec3(
            self.y * other.z - self.z * other.y,
            self.z * other.x - self.x * other.z,
            self.x * other.y - self.y * other.x,
        )

    def norm(self) -> float:
        return math.sqrt(self.dot(self))

    def normalized(self) -> Vec3:
        length = self.norm()
        if length == 0.0:
            raise ValueError("Cannot normalize a zero vector")
        return self.scaled(1.0 / length)

    def rounded(self) -> Vec3:
        return Vec3(round(self.x, 9), round(self.y, 9), round(self.z, 9))


@dataclass(frozen=True, slots=True)
class LineSegment:
    start: Vec3
    end: Vec3

    def length(self) -> float:
        return (self.end - self.start).norm()

    def sample(self, count: int) -> tuple[Vec3, ...]:
        if count < 2:
            raise ValueError("sample count must be >= 2")
        step = 1.0 / (count - 1)
        return tuple(
            self.start + (self.end - self.start).scaled(i * step) for i in range(count)
        )


def _rotate(point: Vec3, center: Vec3, axis: Vec3, angle_rad: float) -> Vec3:
    """Rodrigues rotation of point around the axis line through center."""
    v = point - center
    k = axis
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)
    rotated = (
        v.scaled(cos_a) + k.cross(v).scaled(sin_a) + k.scaled(k.dot(v) * (1.0 - cos_a))
    )
    return center + rotated


@dataclass(frozen=True, slots=True)
class ArcSegment:
    center: Vec3
    normal: Vec3
    start: Vec3
    sweep_rad: float

    def __post_init__(self) -> None:
        if abs(self.normal.norm() - 1.0) > 1e-9:
            raise ValueError("ArcSegment normal must be a unit vector")
        if (self.start - self.center).norm() == 0.0:
            raise ValueError("ArcSegment start must differ from center")

    def radius(self) -> float:
        return (self.start - self.center).norm()

    def end(self) -> Vec3:
        return _rotate(self.start, self.center, self.normal, self.sweep_rad)

    def length(self) -> float:
        return abs(self.sweep_rad) * self.radius()

    def sample(self, count: int) -> tuple[Vec3, ...]:
        if count < 2:
            raise ValueError("sample count must be >= 2")
        step = self.sweep_rad / (count - 1)
        return tuple(
            _rotate(self.start, self.center, self.normal, i * step) for i in range(count)
        )


PathSegment = LineSegment | ArcSegment


def path_length(segments: Sequence[PathSegment]) -> float:
    return sum(segment.length() for segment in segments)


def sample_path(
    segments: Sequence[PathSegment], max_arc_step_rad: float = 0.26
) -> tuple[Vec3, ...]:
    points: list[Vec3] = []
    for segment in segments:
        if isinstance(segment, LineSegment):
            new = segment.sample(2)
        else:
            count = max(2, math.ceil(abs(segment.sweep_rad) / max_arc_step_rad) + 1)
            new = segment.sample(count)
        for point in new:
            if not points or (point - points[-1]).norm() > 1e-12:
                points.append(point)
    return tuple(points)


def half_plane_point(theta_deg: float, r: float, z: float) -> Vec3:
    theta = math.radians(theta_deg)
    return Vec3(r * math.cos(theta), r * math.sin(theta), z)
```

- [ ] **Step 4: Run tests and gates**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/geometry -q && .venv\Scripts\python.exe -m ruff check . && .venv\Scripts\python.exe -m mypy && .venv\Scripts\python.exe tools/check_architecture.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/inductor_designer/geometry/primitives.py tests/unit/geometry
git commit -m "feat(geometry): add Vec3, line/arc segments, and path sampling primitives"
```

---

### Task 3: Finished core resolution

**Files:**
- Create: `src/inductor_designer/geometry/core_solid.py`
- Test: `tests/unit/geometry/test_core_solid.py`

**Interfaces:**
- Consumes: `CoreSelection`/`CatalogCoreSelection`/`ManualCoreSelection` (domain), `Dimension` (domain).
- Produces:
  - `FinishedCore(r_inner_m: float, r_outer_m: float, half_height_m: float, corner_radius_m: float)` — frozen; invariants `0 < r_inner < r_outer`, `half_height > 0`, `0 <= corner_radius <= min((r_outer - r_inner) / 2, half_height)`.
  - `resolve_finished_core(core: CoreSelection) -> FinishedCore` — catalog: OD from `outer_diameter.max_m or nominal`, ID from `inner_diameter.min_m or nominal`, height from `height.max_m or nominal`, corner radius 0.0, then overrides (`outer_diameter_m`/`inner_diameter_m`/`height_m`) replace the finished value; manual: fields used as-is including `corner_radius_m`.
  - `CoreGeometryError(ValueError)` raised when the resolved dimensions violate the invariants.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/geometry/test_core_solid.py`:

```python
from __future__ import annotations

import pytest

from inductor_designer.domain.project import CatalogCoreSelection, CoreOverride, ManualCoreSelection
from inductor_designer.geometry.core_solid import (
    CoreGeometryError,
    FinishedCore,
    resolve_finished_core,
)
from tests.unit.domain.test_catalog_records import make_core


def test_catalog_core_uses_finished_bounds() -> None:
    selection = CatalogCoreSelection("0077071A7", make_core(), ())
    core = resolve_finished_core(selection)
    snapshot = selection.snapshot
    assert core.r_outer_m == pytest.approx(snapshot.outer_diameter.max_m / 2)
    assert core.r_inner_m == pytest.approx(snapshot.inner_diameter.min_m / 2)
    assert core.half_height_m == pytest.approx(snapshot.height.max_m / 2)
    assert core.corner_radius_m == 0.0


def test_catalog_core_falls_back_to_nominal_without_bounds() -> None:
    import dataclasses

    from inductor_designer.domain.catalog_records import Dimension

    record = dataclasses.replace(
        make_core(),
        outer_diameter=Dimension(0.030, None, None),
        inner_diameter=Dimension(0.016, None, None),
        height=Dimension(0.012, None, None),
    )
    core = resolve_finished_core(CatalogCoreSelection(record.part_number, record, ()))
    assert core.r_outer_m == pytest.approx(0.015)
    assert core.r_inner_m == pytest.approx(0.008)


def test_override_replaces_finished_value() -> None:
    selection = CatalogCoreSelection(
        "0077071A7",
        make_core(),
        (CoreOverride("outer_diameter_m", 0.0340, "measured sample"),),
    )
    assert resolve_finished_core(selection).r_outer_m == pytest.approx(0.0170)


def test_manual_core_used_as_is() -> None:
    manual = ManualCoreSelection(0.0269, 0.0147, 0.0112, 0.0005)
    core = resolve_finished_core(manual)
    assert core == FinishedCore(0.00735, 0.01345, 0.0056, 0.0005)


def test_invalid_dimensions_raise() -> None:
    with pytest.raises(CoreGeometryError):
        resolve_finished_core(ManualCoreSelection(0.010, 0.012, 0.005, 0.0))
    with pytest.raises(CoreGeometryError):
        FinishedCore(0.005, 0.010, 0.004, 0.0045)
```

Note for the implementer: `make_core()` (Task 3 of the M1 plan) builds a record whose Dimension bounds are `outer (0.02692, 0.0264, 0.0274)`, `inner (0.01473, 0.0144, 0.0151)`, `height (0.01118, 0.0109, 0.0115)` — the first test derives expectations from the snapshot itself, so it holds regardless.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/geometry/test_core_solid.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

Create `src/inductor_designer/geometry/core_solid.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

from inductor_designer.domain.project import (
    CatalogCoreSelection,
    CoreSelection,
    ManualCoreSelection,
)


class CoreGeometryError(ValueError):
    """Resolved core dimensions cannot form a valid toroid."""


@dataclass(frozen=True, slots=True)
class FinishedCore:
    """Toroid core in finished (coated) dimensions; the surface the wire sees."""

    r_inner_m: float
    r_outer_m: float
    half_height_m: float
    corner_radius_m: float

    def __post_init__(self) -> None:
        if not 0.0 < self.r_inner_m < self.r_outer_m:
            raise CoreGeometryError(
                f"Need 0 < r_inner < r_outer, got {self.r_inner_m!r}, {self.r_outer_m!r}"
            )
        if self.half_height_m <= 0.0:
            raise CoreGeometryError(f"half_height_m must be positive: {self.half_height_m!r}")
        max_corner = min((self.r_outer_m - self.r_inner_m) / 2.0, self.half_height_m)
        if not 0.0 <= self.corner_radius_m <= max_corner:
            raise CoreGeometryError(
                f"corner_radius_m must be within [0, {max_corner}]: {self.corner_radius_m!r}"
            )


def resolve_finished_core(core: CoreSelection) -> FinishedCore:
    if isinstance(core, ManualCoreSelection):
        return FinishedCore(
            r_inner_m=core.inner_diameter_m / 2.0,
            r_outer_m=core.outer_diameter_m / 2.0,
            half_height_m=core.height_m / 2.0,
            corner_radius_m=core.corner_radius_m,
        )
    assert isinstance(core, CatalogCoreSelection)
    snapshot = core.snapshot
    outer = snapshot.outer_diameter.max_m or snapshot.outer_diameter.nominal_m
    inner = snapshot.inner_diameter.min_m or snapshot.inner_diameter.nominal_m
    height = snapshot.height.max_m or snapshot.height.nominal_m
    for override in core.overrides:
        if override.field == "outer_diameter_m":
            outer = override.value
        elif override.field == "inner_diameter_m":
            inner = override.value
        elif override.field == "height_m":
            height = override.value
    return FinishedCore(
        r_inner_m=inner / 2.0,
        r_outer_m=outer / 2.0,
        half_height_m=height / 2.0,
        corner_radius_m=0.0,
    )
```

- [ ] **Step 4: Run tests and gates**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/geometry -q && .venv\Scripts\python.exe -m ruff check . && .venv\Scripts\python.exe -m mypy && .venv\Scripts\python.exe tools/check_architecture.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/inductor_designer/geometry/core_solid.py tests/unit/geometry/test_core_solid.py
git commit -m "feat(geometry): resolve finished core dimensions from selections and overrides"
```

---

### Task 4: D-shaped turn path builder

**Files:**
- Create: `src/inductor_designer/geometry/turn_path.py`
- Test: `tests/unit/geometry/test_turn_path.py`

**Interfaces:**
- Consumes: `FinishedCore` (Task 3), primitives (Task 2).
- Produces:
  - `radial_build_m(layer: int, insulated_diameter_m: float) -> float` = `(layer - 0.5) * d` (layer ≥ 1; ValueError otherwise).
  - `build_turn_loop(core: FinishedCore, layer: int, insulated_diameter_m: float, station_deg: float) -> tuple[PathSegment, ...]` — closed 8-segment loop (4 lines + 4 arcs) in the half-plane at `station_deg`. Raises `TurnGeometryError` when the wire centerline radius at the inner wall (`r_inner − b`) minus half the wire (`d/2`) reaches ≤ 0.
  - `build_connector(core: FinishedCore, layer: int, insulated_diameter_m: float, from_deg: float, to_deg: float) -> ArcSegment` — horizontal arc at radius `r_outer + b`, z = 0, sweeping from `from_deg` to `to_deg` around +Z.
  - `build_lead(core: FinishedCore, layer: int, insulated_diameter_m: float, station_deg: float) -> LineSegment` — radial stub at z = 0 from `r_outer + b` outward by `3 * d`.
  - `turn_loop_length_m(core: FinishedCore, layer: int, insulated_diameter_m: float) -> float` — analytic: `2·(H − 2c) + 2·(W − 2c) + 2π·(c + b)` with `H = 2·half_height`, `W = r_outer − r_inner`, `c = corner_radius`, `b = radial_build`.
  - `TurnGeometryError(ValueError)`.

Loop construction in half-plane (r, z) coordinates, mapped with `half_plane_point`; with `b` = radial build, `c` = corner radius, `hh` = half_height, `ρ = c + b`:
- inner run: `(r_inner − b, −(hh − c)) → (r_inner − b, +(hh − c))`
- arc around inner-top fillet center `(r_inner + c, hh − c)`, quarter sweep to `(r_inner + c, hh + b)`
- top run: `(r_inner + c, hh + b) → (r_outer − c, hh + b)`
- arc around outer-top center `(r_outer − c, hh − c)` to `(r_outer + b, hh − c)`
- outer run down, arc around outer-bottom, bottom run (outer→inner), arc around inner-bottom closing at the inner-run start.
Arc normals are the half-plane's out-of-plane direction `t = (−sin θ, cos θ, 0)`; pick sweep signs so each arc turns the path in the walk direction (verify numerically: each arc's `end()` must equal the next segment's start within 1e-12).

- [ ] **Step 1: Write the failing test**

Create `tests/unit/geometry/test_turn_path.py`:

```python
from __future__ import annotations

import math

import pytest

from inductor_designer.geometry.core_solid import FinishedCore
from inductor_designer.geometry.primitives import ArcSegment, LineSegment, path_length
from inductor_designer.geometry.turn_path import (
    TurnGeometryError,
    build_connector,
    build_lead,
    build_turn_loop,
    radial_build_m,
    turn_loop_length_m,
)

CORE = FinishedCore(r_inner_m=0.00973, r_outer_m=0.01683, half_height_m=0.005715,
                    corner_radius_m=0.0005)
D = 0.001118  # AWG 18 grade 2 draft


def test_radial_build() -> None:
    assert radial_build_m(1, D) == pytest.approx(D / 2)
    assert radial_build_m(3, D) == pytest.approx(2.5 * D)
    with pytest.raises(ValueError):
        radial_build_m(0, D)


def test_loop_is_closed_and_continuous() -> None:
    loop = build_turn_loop(CORE, 1, D, station_deg=30.0)
    assert len(loop) == 8
    for i, segment in enumerate(loop):
        nxt = loop[(i + 1) % 8]
        seg_end = segment.end() if isinstance(segment, ArcSegment) else segment.end
        nxt_start = nxt.start
        assert (seg_end - nxt_start).norm() < 1e-12, f"gap after segment {i}"


def test_loop_lies_in_half_plane() -> None:
    theta = math.radians(30.0)
    normal = (-math.sin(theta), math.cos(theta), 0.0)
    loop = build_turn_loop(CORE, 1, D, station_deg=30.0)
    for segment in loop:
        for point in (segment.start,):
            assert point.x * normal[0] + point.y * normal[1] == pytest.approx(0.0, abs=1e-12)


def test_loop_length_matches_analytic() -> None:
    loop = build_turn_loop(CORE, 2, D, station_deg=0.0)
    assert path_length(loop) == pytest.approx(turn_loop_length_m(CORE, 2, D), rel=1e-9)


def test_analytic_length_value() -> None:
    b = radial_build_m(1, D)
    c = CORE.corner_radius_m
    expected = (
        2 * (2 * CORE.half_height_m - 2 * c)
        + 2 * (CORE.r_outer_m - CORE.r_inner_m - 2 * c)
        + 2 * math.pi * (c + b)
    )
    assert turn_loop_length_m(CORE, 1, D) == pytest.approx(expected)


def test_bore_exhaustion_raises() -> None:
    with pytest.raises(TurnGeometryError, match="bore"):
        build_turn_loop(CORE, 9, D, station_deg=0.0)  # 9th layer eats the whole bore


def test_connector_and_lead() -> None:
    connector = build_connector(CORE, 1, D, from_deg=10.0, to_deg=25.0)
    assert connector.radius() == pytest.approx(CORE.r_outer_m + D / 2)
    assert connector.length() == pytest.approx(math.radians(15.0) * connector.radius())
    lead = build_lead(CORE, 1, D, station_deg=10.0)
    assert isinstance(lead, LineSegment)
    assert lead.length() == pytest.approx(3 * D)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/geometry/test_turn_path.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

Create `src/inductor_designer/geometry/turn_path.py`:

```python
from __future__ import annotations

import math

from inductor_designer.geometry.core_solid import FinishedCore
from inductor_designer.geometry.primitives import (
    ArcSegment,
    LineSegment,
    PathSegment,
    Vec3,
    half_plane_point,
)


class TurnGeometryError(ValueError):
    """A turn cannot be constructed at the requested layer."""


def radial_build_m(layer: int, insulated_diameter_m: float) -> float:
    if layer < 1:
        raise ValueError(f"layer must be >= 1, got {layer!r}")
    return (layer - 0.5) * insulated_diameter_m


def _out_of_plane(theta_deg: float) -> Vec3:
    theta = math.radians(theta_deg)
    return Vec3(-math.sin(theta), math.cos(theta), 0.0)


def build_turn_loop(
    core: FinishedCore,
    layer: int,
    insulated_diameter_m: float,
    station_deg: float,
) -> tuple[PathSegment, ...]:
    d = insulated_diameter_m
    b = radial_build_m(layer, d)
    c = core.corner_radius_m
    hh = core.half_height_m
    rho = c + b
    if core.r_inner_m - b - d / 2.0 <= 0.0:
        raise TurnGeometryError(
            f"Layer {layer} exhausts the core bore: r_inner={core.r_inner_m}, build={b}"
        )

    def p(r: float, z: float) -> Vec3:
        return half_plane_point(station_deg, r, z)

    normal = _out_of_plane(station_deg)
    r_in = core.r_inner_m - b
    r_out = core.r_outer_m + b
    quarter = math.pi / 2.0

    inner_top_center = p(core.r_inner_m + c, hh - c)
    outer_top_center = p(core.r_outer_m - c, hh - c)
    outer_bottom_center = p(core.r_outer_m - c, -(hh - c))
    inner_bottom_center = p(core.r_inner_m + c, -(hh - c))

    segments: tuple[PathSegment, ...] = (
        LineSegment(p(r_in, -(hh - c)), p(r_in, hh - c)),
        ArcSegment(inner_top_center, normal, p(r_in, hh - c), -quarter),
        LineSegment(p(core.r_inner_m + c, hh + b), p(core.r_outer_m - c, hh + b)),
        ArcSegment(outer_top_center, normal, p(core.r_outer_m - c, hh + b), -quarter),
        LineSegment(p(r_out, hh - c), p(r_out, -(hh - c))),
        ArcSegment(outer_bottom_center, normal, p(r_out, -(hh - c)), -quarter),
        LineSegment(p(core.r_outer_m - c, -(hh + b)), p(core.r_inner_m + c, -(hh + b))),
        ArcSegment(inner_bottom_center, normal, p(core.r_inner_m + c, -(hh + b)), -quarter),
    )
    return segments


def build_connector(
    core: FinishedCore,
    layer: int,
    insulated_diameter_m: float,
    from_deg: float,
    to_deg: float,
) -> ArcSegment:
    b = radial_build_m(layer, insulated_diameter_m)
    radius = core.r_outer_m + b
    return ArcSegment(
        center=Vec3(0.0, 0.0, 0.0),
        normal=Vec3(0.0, 0.0, 1.0),
        start=half_plane_point(from_deg, radius, 0.0),
        sweep_rad=math.radians(to_deg - from_deg),
    )


def build_lead(
    core: FinishedCore,
    layer: int,
    insulated_diameter_m: float,
    station_deg: float,
) -> LineSegment:
    b = radial_build_m(layer, insulated_diameter_m)
    r0 = core.r_outer_m + b
    return LineSegment(
        half_plane_point(station_deg, r0, 0.0),
        half_plane_point(station_deg, r0 + 3.0 * insulated_diameter_m, 0.0),
    )


def turn_loop_length_m(core: FinishedCore, layer: int, insulated_diameter_m: float) -> float:
    b = radial_build_m(layer, insulated_diameter_m)
    c = core.corner_radius_m
    height = 2.0 * core.half_height_m
    width = core.r_outer_m - core.r_inner_m
    return 2.0 * (height - 2.0 * c) + 2.0 * (width - 2.0 * c) + 2.0 * math.pi * (c + b)
```

Implementer note on arc sweep signs: the walk direction chosen above goes up the inner wall, outward along the top, down the outer wall, back along the bottom. With the out-of-plane normal `t = (−sinθ, cosθ, 0)`, all four fillets turn clockwise when viewed from +t, hence `−π/2` sweeps. The continuity test (`test_loop_is_closed_and_continuous`) is the oracle: if any arc end misses the next start, a sign is wrong — flip that arc's sweep, don't loosen the test.

- [ ] **Step 4: Run tests and gates**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/geometry -q && .venv\Scripts\python.exe -m ruff check . && .venv\Scripts\python.exe -m mypy && .venv\Scripts\python.exe tools/check_architecture.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/inductor_designer/geometry/turn_path.py tests/unit/geometry/test_turn_path.py
git commit -m "feat(geometry): build planar D-shaped turn loops, connectors, and leads"
```

---

### Task 5: Multi-layer packing engine

**Files:**
- Create: `src/inductor_designer/geometry/packing.py`
- Test: `tests/unit/geometry/test_packing.py`

**Interfaces:**
- Consumes: `FinishedCore` (Task 3), `radial_build_m`, `turn_loop_length_m` (Task 4).
- Produces:
  - `WindingSpec(winding_id: str, turns: int, insulated_diameter_m: float, start_deg: float, sector_deg: float, min_spacing_m: float, min_clearance_m: float)` — frozen input DTO (application layer maps domain windings to this).
  - `PackedLayer(index: int, radial_build_m: float, station_deg: tuple[float, ...], pitch_deg: float, min_pitch_deg: float)` — frozen; stations rounded to 9 decimals, ascending.
  - `PackedWinding(winding_id: str, insulated_diameter_m: float, sector_deg: float, start_deg: float, layers: tuple[PackedLayer, ...], lead_in_deg: float, lead_out_deg: float, wire_length_m: float)` — frozen.
  - `pack_winding(core: FinishedCore, spec: WindingSpec) -> PackedWinding` — deterministic; raises `PackingError`.
  - `PackingError(ValueError)` with attributes `winding_id: str` and `max_turns: int` (the largest turn count that packs).

Algorithm (all radians internal, degrees at the boundary):
1. Minimum pitch on layer k: wire centers sit on the inner-wall circle of radius `r_k = r_inner − radial_build(k)`. Adjacent centers must be chord-separated by at least `d + min_spacing`: `Δθ_k = 2·asin((d + min_spacing) / (2·r_k))`. Guard: if `r_k − d/2 ≤ 0` or the asin argument ≥ 1, layer k does not exist.
2. Lead margin: `margin = Δθ_1` (one layer-1 min pitch), reserved at both sector ends: `usable = radians(sector_deg) − 2·margin`. If `usable < Δθ_1` the winding packs 0 turns.
3. Capacity of layer k: `N_k = floor(usable / Δθ_k)`.
4. Greedy assignment: fill layer 1 up to `N_1`, then layer 2, … until all `turns` are placed or layers run out (bore exhausted) — the latter raises `PackingError` carrying `max_turns = ΣN_k` over all existing layers.
5. Station angles for the `n_k` turns on layer k: evenly distributed across the usable span: `pitch_k = usable / n_k`, `θ_i = start + margin + (i + 0.5)·pitch_k` for `i = 0..n_k−1` (all converted to degrees, rounded 9). By construction `pitch_k ≥ Δθ_k`.
6. `lead_in_deg = start + margin/2`, `lead_out_deg = start + sector − margin/2` (degrees, rounded).
7. Wire length: `Σ_k n_k · turn_loop_length_m(core, k, d)` + connectors `Σ_k (n_k − 1)·pitch_k_rad·(r_outer + build_k)` + leads `2·3d`.
8. `sector_deg == 360` is legal; margins still apply (the gap is where leads exit).

- [ ] **Step 1: Write the failing test**

Create `tests/unit/geometry/test_packing.py`:

```python
from __future__ import annotations

import math

import pytest

from inductor_designer.geometry.core_solid import FinishedCore
from inductor_designer.geometry.packing import PackingError, WindingSpec, pack_winding
from inductor_designer.geometry.turn_path import turn_loop_length_m

CORE = FinishedCore(r_inner_m=0.00973, r_outer_m=0.01683, half_height_m=0.005715,
                    corner_radius_m=0.0)
D = 0.001118


def spec(**overrides: object) -> WindingSpec:
    values: dict[str, object] = {
        "winding_id": "w1",
        "turns": 20,
        "insulated_diameter_m": D,
        "start_deg": 0.0,
        "sector_deg": 300.0,
        "min_spacing_m": 0.0001,
        "min_clearance_m": 0.001,
    }
    values.update(overrides)
    return WindingSpec(**values)  # type: ignore[arg-type]


def min_pitch_rad(layer: int) -> float:
    r_k = CORE.r_inner_m - (layer - 0.5) * D
    return 2 * math.asin((D + 0.0001) / (2 * r_k))


def test_single_layer_fit() -> None:
    packed = pack_winding(CORE, spec(turns=20))
    assert len(packed.layers) == 1
    layer = packed.layers[0]
    assert len(layer.station_deg) == 20
    assert layer.pitch_deg >= layer.min_pitch_deg
    margin = math.degrees(min_pitch_rad(1))
    for station in layer.station_deg:
        assert 0.0 + margin <= station <= 300.0 - margin


def test_overflow_opens_second_layer() -> None:
    usable = math.radians(300.0) - 2 * min_pitch_rad(1)
    capacity_1 = math.floor(usable / min_pitch_rad(1))
    packed = pack_winding(CORE, spec(turns=capacity_1 + 5))
    assert len(packed.layers) == 2
    assert len(packed.layers[0].station_deg) == capacity_1
    assert len(packed.layers[1].station_deg) == 5
    assert packed.layers[1].radial_build_m == pytest.approx(1.5 * D)


def test_infeasible_reports_max_turns() -> None:
    with pytest.raises(PackingError) as excinfo:
        pack_winding(CORE, spec(turns=100000))
    assert excinfo.value.winding_id == "w1"
    max_turns = excinfo.value.max_turns
    assert 0 < max_turns < 100000
    packed = pack_winding(CORE, spec(turns=max_turns))
    assert sum(len(layer.station_deg) for layer in packed.layers) == max_turns


def test_wire_length_analytic() -> None:
    packed = pack_winding(CORE, spec(turns=10))
    layer = packed.layers[0]
    loops = 10 * turn_loop_length_m(CORE, 1, D)
    connectors = 9 * math.radians(layer.pitch_deg) * (CORE.r_outer_m + 0.5 * D)
    leads = 2 * 3 * D
    assert packed.wire_length_m == pytest.approx(loops + connectors + leads, rel=1e-9)


def test_full_circle_sector_reserves_lead_gap() -> None:
    packed = pack_winding(CORE, spec(turns=5, sector_deg=360.0))
    margin = math.degrees(min_pitch_rad(1))
    for station in packed.layers[0].station_deg:
        assert margin <= station <= 360.0 - margin


def test_determinism() -> None:
    assert pack_winding(CORE, spec()) == pack_winding(CORE, spec())


def test_zero_capacity_sector() -> None:
    with pytest.raises(PackingError) as excinfo:
        pack_winding(CORE, spec(turns=1, sector_deg=10.0))
    assert excinfo.value.max_turns == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/geometry/test_packing.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

Create `src/inductor_designer/geometry/packing.py`:

```python
from __future__ import annotations

import math
from dataclasses import dataclass

from inductor_designer.geometry.core_solid import FinishedCore
from inductor_designer.geometry.turn_path import radial_build_m, turn_loop_length_m


class PackingError(ValueError):
    def __init__(self, winding_id: str, max_turns: int, message: str) -> None:
        super().__init__(message)
        self.winding_id = winding_id
        self.max_turns = max_turns


@dataclass(frozen=True, slots=True)
class WindingSpec:
    winding_id: str
    turns: int
    insulated_diameter_m: float
    start_deg: float
    sector_deg: float
    min_spacing_m: float
    min_clearance_m: float


@dataclass(frozen=True, slots=True)
class PackedLayer:
    index: int
    radial_build_m: float
    station_deg: tuple[float, ...]
    pitch_deg: float
    min_pitch_deg: float


@dataclass(frozen=True, slots=True)
class PackedWinding:
    winding_id: str
    insulated_diameter_m: float
    sector_deg: float
    start_deg: float
    layers: tuple[PackedLayer, ...]
    lead_in_deg: float
    lead_out_deg: float
    wire_length_m: float


def _min_pitch_rad(core: FinishedCore, layer: int, d: float, spacing: float) -> float | None:
    """Minimum angular pitch on layer `layer`, or None when the layer cannot exist."""
    r_k = core.r_inner_m - radial_build_m(layer, d)
    if r_k - d / 2.0 <= 0.0:
        return None
    ratio = (d + spacing) / (2.0 * r_k)
    if ratio >= 1.0:
        return None
    return 2.0 * math.asin(ratio)


def pack_winding(core: FinishedCore, spec: WindingSpec) -> PackedWinding:
    d = spec.insulated_diameter_m
    pitch_1 = _min_pitch_rad(core, 1, d, spec.min_spacing_m)
    if pitch_1 is None:
        raise PackingError(spec.winding_id, 0, "Wire does not fit the core bore at layer 1")
    margin = pitch_1
    usable = math.radians(spec.sector_deg) - 2.0 * margin

    capacities: list[tuple[int, float, float]] = []  # (layer, min_pitch_rad, capacity)
    layer = 1
    while True:
        min_pitch = _min_pitch_rad(core, layer, d, spec.min_spacing_m)
        if min_pitch is None:
            break
        capacity = math.floor(usable / min_pitch) if usable >= min_pitch else 0
        if capacity <= 0:
            break
        capacities.append((layer, min_pitch, float(capacity)))
        layer += 1

    total_capacity = int(sum(capacity for _, _, capacity in capacities))
    if spec.turns > total_capacity:
        raise PackingError(
            spec.winding_id,
            total_capacity,
            f"Winding {spec.winding_id!r} needs {spec.turns} turns; "
            f"only {total_capacity} fit in sector {spec.sector_deg} deg",
        )

    layers: list[PackedLayer] = []
    remaining = spec.turns
    wire_length = 0.0
    for layer_index, min_pitch, capacity in capacities:
        if remaining <= 0:
            break
        count = min(remaining, int(capacity))
        remaining -= count
        pitch = usable / count
        start_rad = math.radians(spec.start_deg) + margin
        stations = tuple(
            round(math.degrees(start_rad + (i + 0.5) * pitch), 9) for i in range(count)
        )
        build = radial_build_m(layer_index, d)
        layers.append(
            PackedLayer(
                index=layer_index,
                radial_build_m=round(build, 9),
                station_deg=stations,
                pitch_deg=round(math.degrees(pitch), 9),
                min_pitch_deg=round(math.degrees(min_pitch), 9),
            )
        )
        wire_length += count * turn_loop_length_m(core, layer_index, d)
        wire_length += (count - 1) * pitch * (core.r_outer_m + build)
    wire_length += 2.0 * 3.0 * d

    return PackedWinding(
        winding_id=spec.winding_id,
        insulated_diameter_m=d,
        sector_deg=spec.sector_deg,
        start_deg=spec.start_deg,
        layers=tuple(layers),
        lead_in_deg=round(spec.start_deg + math.degrees(margin) / 2.0, 9),
        lead_out_deg=round(spec.start_deg + spec.sector_deg - math.degrees(margin) / 2.0, 9),
        wire_length_m=round(wire_length, 9),
    )
```

- [ ] **Step 4: Run tests and gates**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/geometry -q && .venv\Scripts\python.exe -m ruff check . && .venv\Scripts\python.exe -m mypy && .venv\Scripts\python.exe tools/check_architecture.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/inductor_designer/geometry/packing.py tests/unit/geometry/test_packing.py
git commit -m "feat(geometry): add deterministic multi-layer concentric-shell packing"
```

---

### Task 6: Cross-winding clearance and occupancy

**Files:**
- Create: `src/inductor_designer/geometry/collisions.py`
- Test: `tests/unit/geometry/test_collisions.py`

**Interfaces:**
- Consumes: `FinishedCore`, `PackedWinding` (Task 5).
- Produces:
  - `CollisionIssue(kind: str, first_winding: str, second_winding: str, required_m: float, actual_m: float, message: str)` — frozen. `kind` is always `"clearance"` in M2.
  - `check_clearances(core: FinishedCore, packings: Sequence[PackedWinding]) -> tuple[CollisionIssue, ...]` — for each adjacent pair around the circle (windings sorted by `start_deg`, wrap-around pair included): angular gap between one winding's sector end and the next winding's sector start, converted to arc length at the worst radius `r_ref = min over both windings of (r_inner − deepest_build − d/2)`; requirement: `gap_arc ≥ max(min_clearance of both) + d_a/2 + d_b/2` (wire surfaces, not centers). Emits one issue per violating pair. Empty/single-winding input → no issues.
  - `occupancy_summary(packings: Sequence[PackedWinding]) -> dict[str, float]` — winding_id → declared sector as a fraction of 360, rounded 9.

Clearance inputs come from `WindingSpec.min_clearance_m`; carry it through by extending `PackedWinding` — **no**: keep `PackedWinding` as defined in Task 5, and give `check_clearances` the clearances explicitly: signature is `check_clearances(core, packings, clearances)` with `clearances: Mapping[str, float]` (winding_id → min_clearance_m). This keeps Task 5's type stable.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/geometry/test_collisions.py`:

```python
from __future__ import annotations

import pytest

from inductor_designer.geometry.collisions import check_clearances, occupancy_summary
from inductor_designer.geometry.core_solid import FinishedCore
from inductor_designer.geometry.packing import WindingSpec, pack_winding

CORE = FinishedCore(r_inner_m=0.00973, r_outer_m=0.01683, half_height_m=0.005715,
                    corner_radius_m=0.0)
D = 0.001118


def packed(winding_id: str, start: float, sector: float, turns: int = 8) -> object:
    return pack_winding(
        CORE,
        WindingSpec(winding_id, turns, D, start, sector, 0.0001, 0.001),
    )


def test_well_separated_windings_have_no_issues() -> None:
    packings = [packed("w1", 0.0, 150.0), packed("w2", 180.0, 150.0)]
    issues = check_clearances(CORE, packings, {"w1": 0.001, "w2": 0.001})
    assert issues == ()


def test_tight_gap_reports_clearance_violation() -> None:
    packings = [packed("w1", 0.0, 179.0), packed("w2", 180.0, 179.0)]
    issues = check_clearances(CORE, packings, {"w1": 0.004, "w2": 0.004})
    assert len(issues) == 2  # both gaps (179->180 and 359->360) violate
    issue = issues[0]
    assert issue.kind == "clearance"
    assert issue.actual_m < issue.required_m


def test_single_winding_no_issues() -> None:
    assert check_clearances(CORE, [packed("w1", 0.0, 300.0)], {"w1": 0.001}) == ()


def test_occupancy() -> None:
    packings = [packed("w1", 0.0, 90.0), packed("w2", 180.0, 45.0)]
    summary = occupancy_summary(packings)
    assert summary == {"w1": 0.25, "w2": 0.125}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/geometry/test_collisions.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

Create `src/inductor_designer/geometry/collisions.py`:

```python
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from inductor_designer.geometry.core_solid import FinishedCore
from inductor_designer.geometry.packing import PackedWinding


@dataclass(frozen=True, slots=True)
class CollisionIssue:
    kind: str
    first_winding: str
    second_winding: str
    required_m: float
    actual_m: float
    message: str


def _worst_radius(core: FinishedCore, packing: PackedWinding) -> float:
    deepest = max(layer.radial_build_m for layer in packing.layers)
    return core.r_inner_m - deepest - packing.insulated_diameter_m / 2.0


def check_clearances(
    core: FinishedCore,
    packings: Sequence[PackedWinding],
    clearances: Mapping[str, float],
) -> tuple[CollisionIssue, ...]:
    windings = sorted(packings, key=lambda p: p.start_deg)
    if len(windings) < 2:
        return ()
    issues: list[CollisionIssue] = []
    for i, first in enumerate(windings):
        second = windings[(i + 1) % len(windings)]
        gap_deg = (second.start_deg - (first.start_deg + first.sector_deg)) % 360.0
        r_ref = min(_worst_radius(core, first), _worst_radius(core, second))
        actual = math.radians(gap_deg) * r_ref
        required = (
            max(clearances[first.winding_id], clearances[second.winding_id])
            + first.insulated_diameter_m / 2.0
            + second.insulated_diameter_m / 2.0
        )
        if actual < required:
            issues.append(
                CollisionIssue(
                    kind="clearance",
                    first_winding=first.winding_id,
                    second_winding=second.winding_id,
                    required_m=round(required, 9),
                    actual_m=round(actual, 9),
                    message=(
                        f"Windings {first.winding_id!r} and {second.winding_id!r} are "
                        f"{actual * 1000:.3f} mm apart at the bore; "
                        f"{required * 1000:.3f} mm required"
                    ),
                )
            )
    return tuple(issues)


def occupancy_summary(packings: Sequence[PackedWinding]) -> dict[str, float]:
    return {p.winding_id: round(p.sector_deg / 360.0, 9) for p in packings}
```

- [ ] **Step 4: Run tests and gates**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/geometry -q && .venv\Scripts\python.exe -m ruff check . && .venv\Scripts\python.exe -m mypy && .venv\Scripts\python.exe tools/check_architecture.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/inductor_designer/geometry/collisions.py tests/unit/geometry/test_collisions.py
git commit -m "feat(geometry): check cross-winding bore clearance and report occupancy"
```

---

### Task 7: Deterministic naming

**Files:**
- Create: `src/inductor_designer/geometry/naming.py`
- Test: `tests/unit/geometry/test_naming.py`

**Interfaces:**
- Consumes: `PackedWinding` (Task 5).
- Produces:
  - `sanitize_identifier(raw: str) -> str` — every character outside `[A-Za-z0-9_]` becomes `_`; a leading digit gains a `W` prefix; empty result raises `ValueError`.
  - `core_name() -> str` — constant `"Core"`.
  - `turn_name(winding_id: str, layer: int, turn: int) -> str` — `f"{sanitize_identifier(winding_id)}_L{layer:02d}_T{turn:03d}"` (turn is 1-based).
  - `lead_names(winding_id: str) -> tuple[str, str]` — `(..._LeadIn, ..._LeadOut)`.
  - `terminal_names(winding_id: str) -> tuple[str, str]` — `(..._TermIn, ..._TermOut)` (reserved for M3 terminal faces).
  - `winding_names(packing: PackedWinding) -> tuple[str, ...]` — all turn names in layer order then station order; deterministic.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/geometry/test_naming.py`:

```python
from __future__ import annotations

import pytest

from inductor_designer.geometry.core_solid import FinishedCore
from inductor_designer.geometry.naming import (
    core_name,
    lead_names,
    sanitize_identifier,
    terminal_names,
    turn_name,
    winding_names,
)
from inductor_designer.geometry.packing import WindingSpec, pack_winding


def test_sanitize() -> None:
    assert sanitize_identifier("w1") == "w1"
    assert sanitize_identifier("primary winding-a") == "primary_winding_a"
    assert sanitize_identifier("1w") == "W1w"
    with pytest.raises(ValueError):
        sanitize_identifier("")


def test_names() -> None:
    assert core_name() == "Core"
    assert turn_name("w1", 1, 7) == "w1_L01_T007"
    assert lead_names("w-1") == ("w_1_LeadIn", "w_1_LeadOut")
    assert terminal_names("w1") == ("w1_TermIn", "w1_TermOut")


def test_winding_names_cover_all_turns_in_order() -> None:
    core = FinishedCore(0.00973, 0.01683, 0.005715, 0.0)
    packing = pack_winding(core, WindingSpec("w1", 30, 0.001118, 0.0, 300.0, 0.0001, 0.001))
    names = winding_names(packing)
    assert len(names) == 30
    assert names[0] == "w1_L01_T001"
    assert len(set(names)) == 30
    assert names == tuple(sorted(names))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/geometry/test_naming.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

Create `src/inductor_designer/geometry/naming.py`:

```python
from __future__ import annotations

import re

from inductor_designer.geometry.packing import PackedWinding

_INVALID = re.compile(r"[^A-Za-z0-9_]")


def sanitize_identifier(raw: str) -> str:
    cleaned = _INVALID.sub("_", raw)
    if not cleaned:
        raise ValueError("Identifier is empty after sanitizing")
    if cleaned[0].isdigit():
        cleaned = f"W{cleaned}"
    return cleaned


def core_name() -> str:
    return "Core"


def turn_name(winding_id: str, layer: int, turn: int) -> str:
    return f"{sanitize_identifier(winding_id)}_L{layer:02d}_T{turn:03d}"


def lead_names(winding_id: str) -> tuple[str, str]:
    base = sanitize_identifier(winding_id)
    return (f"{base}_LeadIn", f"{base}_LeadOut")


def terminal_names(winding_id: str) -> tuple[str, str]:
    base = sanitize_identifier(winding_id)
    return (f"{base}_TermIn", f"{base}_TermOut")


def winding_names(packing: PackedWinding) -> tuple[str, ...]:
    names: list[str] = []
    counter = 1
    for layer in packing.layers:
        for _ in layer.station_deg:
            names.append(turn_name(packing.winding_id, layer.index, counter))
            counter += 1
    return tuple(names)
```

Note: the turn counter is global across layers (T001..T030 through layer 1 then 2), which keeps names sortable and unique; layer index still appears in the name.

- [ ] **Step 4: Run tests and gates**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/geometry -q && .venv\Scripts\python.exe -m ruff check . && .venv\Scripts\python.exe -m mypy && .venv\Scripts\python.exe tools/check_architecture.py`
Expected: PASS. (Heads-up: `test_winding_names_cover_all_turns_in_order` asserts sorted order — with a global counter and zero-padded fields this holds; if it ever fails the padding widths are wrong, not the test.)

- [ ] **Step 5: Commit**

```bash
git add src/inductor_designer/geometry/naming.py tests/unit/geometry/test_naming.py
git commit -m "feat(geometry): deterministic object naming for turns, leads, and terminals"
```

---

### Task 8: Symmetry plan proposal

**Files:**
- Create: `src/inductor_designer/geometry/symmetry.py`
- Test: `tests/unit/geometry/test_symmetry.py`

**Interfaces:**
- Consumes: `WindingDefinition` (domain), `PackedWinding` (Task 5).
- Produces:
  - `SymmetryPlan(multiplier: int, sector_deg: float, cut_angles_deg: tuple[float, float])` — frozen.
  - `SymmetryRefusal(code: str, message: str)` — frozen. Codes: `"single-winding"`, `"unequal-windings"`, `"unequal-spacing"`, `"unequal-excitation"`.
  - `propose_symmetry_plan(windings: Sequence[WindingDefinition]) -> SymmetryPlan | SymmetryRefusal` — proposes rotational symmetry of order m = number of windings when: m ≥ 2; all windings share turns, conductor_name, mode, sector_deg, min_spacing_m, min_clearance_m; all share ac_magnitude_a, ac_phase_deg, frequency_hz, dc_current_a; start angles are equally spaced: sorted starts satisfy `start_i = start_0 + i·(360/m)` within 1e-6 deg. Cut angles: midpoints of the gap before winding 0 and before winding 1: `cut_0 = start_0 − gap/2` where `gap = 360/m − sector`, normalized to [0, 360); `cut_1 = cut_0 + 360/m`.

Spec §6.5 anchoring: full model remains the default; this only *proposes*. Current-direction and winding-direction asymmetry is deliberately allowed to differ? No — **strict**: also require equal `winding_direction` and `current_direction` (a flipped winding breaks field periodicity). Add those two fields to the equality check under code `"unequal-windings"`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/geometry/test_symmetry.py`:

```python
from __future__ import annotations

import dataclasses

from inductor_designer.geometry.symmetry import (
    SymmetryPlan,
    SymmetryRefusal,
    propose_symmetry_plan,
)
from tests.unit.domain.test_project import make_winding


def trio(sector: float = 100.0) -> tuple[object, object, object]:
    return (
        make_winding(winding_id="w1", start_angle_deg=0.0, sector_deg=sector),
        make_winding(winding_id="w2", start_angle_deg=120.0, sector_deg=sector),
        make_winding(winding_id="w3", start_angle_deg=240.0, sector_deg=sector),
    )


def test_three_identical_windings_give_order_three() -> None:
    plan = propose_symmetry_plan(trio())
    assert isinstance(plan, SymmetryPlan)
    assert plan.multiplier == 3
    assert plan.sector_deg == 120.0
    cut0, cut1 = plan.cut_angles_deg
    assert cut0 == 350.0  # gap = 20 deg, start_0 = 0 -> cut at -10 -> 350
    assert cut1 == 110.0


def test_single_winding_refused() -> None:
    refusal = propose_symmetry_plan([make_winding(winding_id="w1")])
    assert isinstance(refusal, SymmetryRefusal)
    assert refusal.code == "single-winding"


def test_unequal_turns_refused() -> None:
    w1, w2, w3 = trio()
    w2 = dataclasses.replace(w2, turns=99)  # type: ignore[type-var]
    refusal = propose_symmetry_plan([w1, w2, w3])
    assert isinstance(refusal, SymmetryRefusal)
    assert refusal.code == "unequal-windings"


def test_unequal_spacing_refused() -> None:
    w1, w2, w3 = trio()
    w2 = dataclasses.replace(w2, start_angle_deg=100.0)  # type: ignore[type-var]
    refusal = propose_symmetry_plan([w1, w2, w3])
    assert isinstance(refusal, SymmetryRefusal)
    assert refusal.code == "unequal-spacing"


def test_unequal_excitation_refused() -> None:
    w1, w2, w3 = trio()
    w2 = dataclasses.replace(w2, ac_phase_deg=120.0)  # type: ignore[type-var]
    refusal = propose_symmetry_plan([w1, w2, w3])
    assert isinstance(refusal, SymmetryRefusal)
    assert refusal.code == "unequal-excitation"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/geometry/test_symmetry.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

Create `src/inductor_designer/geometry/symmetry.py`:

```python
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from inductor_designer.domain.winding import WindingDefinition

_ANGLE_TOL_DEG = 1e-6


@dataclass(frozen=True, slots=True)
class SymmetryPlan:
    multiplier: int
    sector_deg: float
    cut_angles_deg: tuple[float, float]


@dataclass(frozen=True, slots=True)
class SymmetryRefusal:
    code: str
    message: str


def _geometry_key(w: WindingDefinition) -> tuple[object, ...]:
    return (
        w.turns,
        w.conductor_name,
        w.mode,
        w.sector_deg,
        w.min_spacing_m,
        w.min_clearance_m,
        w.winding_direction,
        w.current_direction,
    )


def _excitation_key(w: WindingDefinition) -> tuple[float, float, float, float]:
    return (w.ac_magnitude_a, w.ac_phase_deg, w.frequency_hz, w.dc_current_a)


def propose_symmetry_plan(
    windings: Sequence[WindingDefinition],
) -> SymmetryPlan | SymmetryRefusal:
    m = len(windings)
    if m < 2:
        return SymmetryRefusal(
            "single-winding", "Rotational symmetry needs at least two identical windings."
        )
    first = windings[0]
    if any(_geometry_key(w) != _geometry_key(first) for w in windings[1:]):
        return SymmetryRefusal(
            "unequal-windings",
            "Windings differ in turns, conductor, mode, sector, spacing, or direction.",
        )
    if any(_excitation_key(w) != _excitation_key(first) for w in windings[1:]):
        return SymmetryRefusal(
            "unequal-excitation", "Windings differ in AC/DC excitation values."
        )
    starts = sorted(w.start_angle_deg for w in windings)
    pitch = 360.0 / m
    if any(
        abs((starts[i] - starts[0]) - i * pitch) > _ANGLE_TOL_DEG for i in range(m)
    ):
        return SymmetryRefusal(
            "unequal-spacing", f"Winding start angles are not spaced by {pitch} degrees."
        )
    gap = pitch - first.sector_deg
    cut0 = (starts[0] - gap / 2.0) % 360.0
    cut1 = (cut0 + pitch) % 360.0
    return SymmetryPlan(
        multiplier=m,
        sector_deg=round(pitch, 9),
        cut_angles_deg=(round(cut0, 9), round(cut1, 9)),
    )
```

- [ ] **Step 4: Run tests and gates**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/geometry -q && .venv\Scripts\python.exe -m ruff check . && .venv\Scripts\python.exe -m mypy && .venv\Scripts\python.exe tools/check_architecture.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/inductor_designer/geometry/symmetry.py tests/unit/geometry/test_symmetry.py
git commit -m "feat(geometry): propose data-level rotational symmetry plans with typed refusals"
```

---

### Task 9: 2D equivalent (top-view planar model)

**Files:**
- Create: `src/inductor_designer/geometry/planar.py`
- Test: `tests/unit/geometry/test_planar.py`

**Interfaces:**
- Consumes: `FinishedCore` (Task 3), `PackedWinding` (Task 5), `radial_build_m` (Task 4).
- Produces:
  - `PlanarConductor(x_m: float, y_m: float, radius_m: float, polarity: int)` — frozen; polarity `+1` = inside the window (current into the plane for a forward-wound turn), `-1` = outside the OD (return).
  - `PlanarWinding(winding_id: str, conductors: tuple[PlanarConductor, ...])` — frozen.
  - `PlanarModel(r_inner_m: float, r_outer_m: float, depth_m: float, windings: tuple[PlanarWinding, ...])` — frozen; `depth_m` = finished core height (spec §6.4: model depth derived from core height).
  - `build_planar_model(core: FinishedCore, packings: Sequence[PackedWinding], bare_radius_m: Mapping[str, float]) -> PlanarModel` — for every packed turn at station θ on layer k: inner conductor at radius `r_inner − build_k`, outer at `r_outer + build_k`, both at angle θ, circle radius = the winding's bare wire radius. Coordinates rounded 9.

This is the explicitly approximate XY model of spec §6.4: annular core plus paired outgoing/returning conductor regions per winding — a direct top-view projection of the 3D stations, no angular bends or lead routing.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/geometry/test_planar.py`:

```python
from __future__ import annotations

import math

import pytest

from inductor_designer.geometry.core_solid import FinishedCore
from inductor_designer.geometry.packing import WindingSpec, pack_winding
from inductor_designer.geometry.planar import build_planar_model

CORE = FinishedCore(r_inner_m=0.00973, r_outer_m=0.01683, half_height_m=0.005715,
                    corner_radius_m=0.0)
D = 0.001118
BARE_R = 0.00102362 / 2


def test_planar_model_projects_stations() -> None:
    packing = pack_winding(CORE, WindingSpec("w1", 6, D, 0.0, 180.0, 0.0001, 0.001))
    model = build_planar_model(CORE, [packing], {"w1": BARE_R})
    assert model.r_inner_m == CORE.r_inner_m
    assert model.r_outer_m == CORE.r_outer_m
    assert model.depth_m == pytest.approx(2 * CORE.half_height_m)
    winding = model.windings[0]
    assert len(winding.conductors) == 12  # 6 turns x (inner + outer)
    inner = [c for c in winding.conductors if c.polarity == 1]
    outer = [c for c in winding.conductors if c.polarity == -1]
    assert len(inner) == len(outer) == 6
    for conductor in inner:
        r = math.hypot(conductor.x_m, conductor.y_m)
        assert r == pytest.approx(CORE.r_inner_m - D / 2, rel=1e-6)
        assert conductor.radius_m == BARE_R
    for conductor in outer:
        r = math.hypot(conductor.x_m, conductor.y_m)
        assert r == pytest.approx(CORE.r_outer_m + D / 2, rel=1e-6)


def test_second_layer_projects_deeper() -> None:
    packing = pack_winding(CORE, WindingSpec("w1", 40, D, 0.0, 300.0, 0.0001, 0.001))
    assert len(packing.layers) >= 2
    model = build_planar_model(CORE, [packing], {"w1": BARE_R})
    radii = sorted(
        round(math.hypot(c.x_m, c.y_m), 6)
        for c in model.windings[0].conductors
        if c.polarity == 1
    )
    assert radii[0] < radii[-1]  # layer-2 inner conductors sit deeper in the window
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/geometry/test_planar.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

Create `src/inductor_designer/geometry/planar.py`:

```python
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from inductor_designer.geometry.core_solid import FinishedCore
from inductor_designer.geometry.packing import PackedWinding


@dataclass(frozen=True, slots=True)
class PlanarConductor:
    x_m: float
    y_m: float
    radius_m: float
    polarity: int


@dataclass(frozen=True, slots=True)
class PlanarWinding:
    winding_id: str
    conductors: tuple[PlanarConductor, ...]


@dataclass(frozen=True, slots=True)
class PlanarModel:
    r_inner_m: float
    r_outer_m: float
    depth_m: float
    windings: tuple[PlanarWinding, ...]


def _conductor(r: float, theta_deg: float, radius: float, polarity: int) -> PlanarConductor:
    theta = math.radians(theta_deg)
    return PlanarConductor(
        x_m=round(r * math.cos(theta), 9),
        y_m=round(r * math.sin(theta), 9),
        radius_m=radius,
        polarity=polarity,
    )


def build_planar_model(
    core: FinishedCore,
    packings: Sequence[PackedWinding],
    bare_radius_m: Mapping[str, float],
) -> PlanarModel:
    windings: list[PlanarWinding] = []
    for packing in packings:
        radius = bare_radius_m[packing.winding_id]
        conductors: list[PlanarConductor] = []
        for layer in packing.layers:
            r_in = core.r_inner_m - layer.radial_build_m
            r_out = core.r_outer_m + layer.radial_build_m
            for station in layer.station_deg:
                conductors.append(_conductor(r_in, station, radius, +1))
                conductors.append(_conductor(r_out, station, radius, -1))
        windings.append(PlanarWinding(packing.winding_id, tuple(conductors)))
    return PlanarModel(
        r_inner_m=core.r_inner_m,
        r_outer_m=core.r_outer_m,
        depth_m=round(2.0 * core.half_height_m, 9),
        windings=tuple(windings),
    )
```

- [ ] **Step 4: Run tests and gates**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/geometry -q && .venv\Scripts\python.exe -m ruff check . && .venv\Scripts\python.exe -m mypy && .venv\Scripts\python.exe tools/check_architecture.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/inductor_designer/geometry/planar.py tests/unit/geometry/test_planar.py
git commit -m "feat(geometry): project packed windings into the approximate 2D planar model"
```

---

### Task 10: Application service — build the geometry model

**Files:**
- Create: `src/inductor_designer/application/services/geometry_model.py`
- Test: `tests/unit/application/test_geometry_model.py`

**Interfaces:**
- Consumes: `InductorProject`, `validate_project`, `ValidationCategory` (domain); `CatalogRepository` port; `ConductorRecord`; everything from Tasks 3–9.
- Produces:
  - `GeometryModelError(ValueError)` with attribute `issues: tuple[str, ...]` (human-readable reasons).
  - `GeometryModel(core: FinishedCore, packings: tuple[PackedWinding, ...], collisions: tuple[CollisionIssue, ...], symmetry: SymmetryPlan | SymmetryRefusal, planar: PlanarModel, insulated_diameter_m: dict[str, float], bare_diameter_m: dict[str, float])` — frozen dataclass (use `field(default_factory=...)`? No — all fields required, plain frozen).
  - `insulated_diameter(record: ConductorRecord) -> float` — grade 2, else grade 1, else raises `GeometryModelError` naming the conductor (the insulated-diameter rule).
  - `build_geometry_model(project: InductorProject, catalog: CatalogRepository) -> GeometryModel` — steps: (1) run `validate_project` with the catalog's conductor names; any ERROR issue → `GeometryModelError` listing them; (2) reject `project.core is None`; (3) resolve `FinishedCore`; (4) per winding: fetch conductor, resolve insulated + bare diameters, `pack_winding` (PackingError → GeometryModelError with its message); (5) `check_clearances`; (6) `propose_symmetry_plan`; (7) `build_planar_model`. Collisions do NOT raise — they are reported in the model (the manifest and UI surface them; generation gating is an M3 decision).

- [ ] **Step 1: Write the failing test**

Create `tests/unit/application/test_geometry_model.py`:

```python
from __future__ import annotations

import dataclasses

import pytest

from inductor_designer.application.services.geometry_model import (
    GeometryModel,
    GeometryModelError,
    build_geometry_model,
    insulated_diameter,
)
from inductor_designer.domain.catalog_records import (
    ConductorRecord,
    ConductorStandard,
    CoreRecord,
    ReviewStatus,
)
from inductor_designer.geometry.symmetry import SymmetryRefusal
from tests.unit.domain.test_catalog_records import make_core
from tests.unit.domain.test_project import make_project, make_winding


def make_conductor(**overrides: object) -> ConductorRecord:
    values: dict[str, object] = {
        "name": "AWG 18",
        "standard": ConductorStandard.AWG,
        "bare_diameter_m": 0.00102362,
        "grade1_diameter_m": 0.001072,
        "grade2_diameter_m": 0.001118,
        "source": "test",
        "catalog_revision": "round-wire-2",
        "review_status": ReviewStatus.DRAFT,
        "reviewed_by": None,
    }
    values.update(overrides)
    return ConductorRecord(**values)  # type: ignore[arg-type]


class FakeCatalog:
    def __init__(self, conductors: dict[str, ConductorRecord]) -> None:
        self._conductors = conductors

    def get_core(self, part_number: str) -> CoreRecord | None:
        return make_core() if part_number == "0077071A7" else None

    def list_cores(self) -> tuple[CoreRecord, ...]:
        return (make_core(),)

    def get_conductor(self, name: str) -> ConductorRecord | None:
        return self._conductors.get(name)

    def list_conductor_names(self) -> tuple[str, ...]:
        return tuple(self._conductors)


CATALOG = FakeCatalog({"AWG 18": make_conductor()})


def test_insulated_diameter_prefers_grade2() -> None:
    assert insulated_diameter(make_conductor()) == 0.001118
    assert insulated_diameter(make_conductor(grade2_diameter_m=None)) == 0.001072
    with pytest.raises(GeometryModelError, match="AWG 18"):
        insulated_diameter(make_conductor(grade1_diameter_m=None, grade2_diameter_m=None))


def test_build_model_end_to_end() -> None:
    project = make_project(
        windings=(
            make_winding(winding_id="w1", start_angle_deg=0.0, sector_deg=150.0, turns=10),
            make_winding(winding_id="w2", start_angle_deg=180.0, sector_deg=150.0, turns=10),
        )
    )
    model = build_geometry_model(project, CATALOG)
    assert isinstance(model, GeometryModel)
    assert len(model.packings) == 2
    assert model.collisions == ()
    assert model.symmetry.multiplier == 2  # type: ignore[union-attr]
    assert model.planar.depth_m > 0
    assert model.insulated_diameter_m["w1"] == 0.001118


def test_validation_errors_block() -> None:
    project = make_project(windings=(make_winding(turns=0),))
    with pytest.raises(GeometryModelError) as excinfo:
        build_geometry_model(project, CATALOG)
    assert any("winding.turns" in issue for issue in excinfo.value.issues)


def test_missing_core_blocks() -> None:
    project = make_project(core=None)
    with pytest.raises(GeometryModelError, match="core"):
        build_geometry_model(project, CATALOG)


def test_packing_overflow_blocks_with_max_turns() -> None:
    project = make_project(windings=(make_winding(turns=5000),))
    with pytest.raises(GeometryModelError) as excinfo:
        build_geometry_model(project, CATALOG)
    assert any("5000" in issue for issue in excinfo.value.issues)


def test_asymmetric_project_gets_refusal_not_error() -> None:
    project = make_project(
        windings=(
            make_winding(winding_id="w1", sector_deg=150.0, turns=10),
            make_winding(winding_id="w2", start_angle_deg=180.0, sector_deg=100.0, turns=10),
        )
    )
    model = build_geometry_model(project, CATALOG)
    assert isinstance(model.symmetry, SymmetryRefusal)


def test_conductor_without_insulation_blocks() -> None:
    catalog = FakeCatalog(
        {"AWG 18": make_conductor(grade1_diameter_m=None, grade2_diameter_m=None)}
    )
    project = make_project(windings=(make_winding(turns=5),))
    with pytest.raises(GeometryModelError, match="insulated"):
        build_geometry_model(project, catalog)


def test_bare_diameter_recorded() -> None:
    project = make_project(windings=(make_winding(turns=5),))
    model = build_geometry_model(project, CATALOG)
    assert model.bare_diameter_m["w1"] == pytest.approx(0.00102362)
```

Note: `make_core()` is the M1 test helper in `tests/unit/domain/test_catalog_records.py` (finished ID = `inner_diameter.min_m` = 14.4 mm) — 10-turn AWG 18 windings pack in one layer there; 5000 turns cannot. The reviewed real 0077071A7 values only matter for the golden fixture in Task 11, which reads them from the built catalog.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/application/test_geometry_model.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

Create `src/inductor_designer/application/services/geometry_model.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

from inductor_designer.application.ports.catalog import CatalogRepository
from inductor_designer.domain.catalog_records import ConductorRecord
from inductor_designer.domain.project import InductorProject
from inductor_designer.domain.validation import ValidationCategory, validate_project
from inductor_designer.geometry.collisions import CollisionIssue, check_clearances
from inductor_designer.geometry.core_solid import CoreGeometryError, FinishedCore, resolve_finished_core
from inductor_designer.geometry.packing import PackedWinding, PackingError, WindingSpec, pack_winding
from inductor_designer.geometry.planar import PlanarModel, build_planar_model
from inductor_designer.geometry.symmetry import SymmetryPlan, SymmetryRefusal, propose_symmetry_plan


class GeometryModelError(ValueError):
    def __init__(self, issues: tuple[str, ...]) -> None:
        super().__init__("; ".join(issues))
        self.issues = issues


@dataclass(frozen=True, slots=True)
class GeometryModel:
    core: FinishedCore
    packings: tuple[PackedWinding, ...]
    collisions: tuple[CollisionIssue, ...]
    symmetry: SymmetryPlan | SymmetryRefusal
    planar: PlanarModel
    insulated_diameter_m: dict[str, float]
    bare_diameter_m: dict[str, float]


def insulated_diameter(record: ConductorRecord) -> float:
    value = record.grade2_diameter_m or record.grade1_diameter_m
    if value is None:
        raise GeometryModelError(
            (f"Conductor {record.name!r} has no insulated diameter; packing needs one.",)
        )
    return value


def build_geometry_model(
    project: InductorProject, catalog: CatalogRepository
) -> GeometryModel:
    validation = validate_project(project, known_conductors=catalog.list_conductor_names())
    errors = tuple(
        f"{issue.code}: {issue.message}"
        for issue in validation
        if issue.category is ValidationCategory.ERROR
    )
    if errors:
        raise GeometryModelError(errors)
    if project.core is None:
        raise GeometryModelError(("Project has no core selection; geometry needs one.",))
    try:
        core = resolve_finished_core(project.core)
    except CoreGeometryError as error:
        raise GeometryModelError((str(error),)) from error

    packings: list[PackedWinding] = []
    clearances: dict[str, float] = {}
    insulated: dict[str, float] = {}
    bare: dict[str, float] = {}
    for winding in project.windings:
        record = catalog.get_conductor(winding.conductor_name)
        assert record is not None  # validation already checked membership
        d_ins = insulated_diameter(record)
        insulated[winding.winding_id] = d_ins
        bare[winding.winding_id] = record.bare_diameter_m
        clearances[winding.winding_id] = winding.min_clearance_m
        spec = WindingSpec(
            winding_id=winding.winding_id,
            turns=winding.turns,
            insulated_diameter_m=d_ins,
            start_deg=winding.start_angle_deg,
            sector_deg=winding.sector_deg,
            min_spacing_m=winding.min_spacing_m,
            min_clearance_m=winding.min_clearance_m,
        )
        try:
            packings.append(pack_winding(core, spec))
        except PackingError as error:
            raise GeometryModelError((str(error),)) from error

    collisions = check_clearances(core, packings, clearances)
    symmetry = propose_symmetry_plan(project.windings)
    planar = build_planar_model(
        core, packings, {w: b / 2.0 for w, b in bare.items()}
    )
    return GeometryModel(
        core=core,
        packings=tuple(packings),
        collisions=collisions,
        symmetry=symmetry,
        planar=planar,
        insulated_diameter_m=insulated,
        bare_diameter_m=bare,
    )
```

(If Ruff flags the long import lines, break them with parentheses — keep line length ≤ 100.)

- [ ] **Step 4: Run tests and gates**

Run: `.venv\Scripts\python.exe -m pytest tests/unit -q && .venv\Scripts\python.exe -m ruff check . && .venv\Scripts\python.exe -m mypy && .venv\Scripts\python.exe tools/check_architecture.py`
Expected: PASS — architecture checker must stay green (`application` imports only domain/geometry + its own port).

- [ ] **Step 5: Commit**

```bash
git add src/inductor_designer/application/services/geometry_model.py tests/unit/application/test_geometry_model.py
git commit -m "feat(application): compose project and catalog into the geometry model"
```

---

### Task 11: Geometry manifest with committed golden

**Files:**
- Create: `src/inductor_designer/geometry/manifest.py`
- Create: `tests/fixtures/sample_geometry_project.inductor.json` (generated in Step 4)
- Create: `tests/golden/sample_geometry_manifest.json` (generated in Step 5)
- Test: `tests/unit/geometry/test_manifest.py`

**Interfaces:**
- Consumes: `GeometryModel` (Task 10), naming (Task 7), `occupancy_summary` (Task 6).
- Produces:
  - `build_manifest(model: GeometryModel) -> dict[str, object]` — canonical structure below; every float already rounded by producers, manifest re-rounds defensively.
  - `manifest_json(model: GeometryModel) -> str` — `json.dumps(manifest, indent=2, sort_keys=True) + "\n"`.

Manifest structure (exact keys):

```json
{
  "schemaVersion": 1,
  "core": {"name": "Core", "rInnerM": 0.0, "rOuterM": 0.0, "halfHeightM": 0.0,
           "cornerRadiusM": 0.0},
  "windings": [
    {"windingId": "w1", "insulatedDiameterM": 0.0, "bareDiameterM": 0.0,
     "sectorDeg": 0.0, "startDeg": 0.0, "occupancy": 0.0,
     "leadInDeg": 0.0, "leadOutDeg": 0.0, "wireLengthM": 0.0,
     "leadNames": ["w1_LeadIn", "w1_LeadOut"],
     "terminalNames": ["w1_TermIn", "w1_TermOut"],
     "layers": [{"layer": 1, "radialBuildM": 0.0, "pitchDeg": 0.0,
                 "minPitchDeg": 0.0, "stationsDeg": [], "turnNames": []}]}
  ],
  "collisions": [{"kind": "clearance", "windings": ["w1", "w2"],
                  "requiredM": 0.0, "actualM": 0.0, "message": ""}],
  "symmetry": null,
  "symmetryRefusal": {"code": "", "message": ""},
  "planar": {"depthM": 0.0, "rInnerM": 0.0, "rOuterM": 0.0, "conductorCount": 0}
}
```

Exactly one of `symmetry` / `symmetryRefusal` is non-null. `turnNames` per layer slice the global `winding_names` sequence in order. Windings sorted by `windingId`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/geometry/test_manifest.py`:

```python
from __future__ import annotations

import json

from inductor_designer.application.services.geometry_model import build_geometry_model
from inductor_designer.geometry.manifest import build_manifest, manifest_json
from tests.unit.application.test_geometry_model import CATALOG
from tests.unit.domain.test_project import make_project, make_winding


def two_winding_project() -> object:
    return make_project(
        windings=(
            make_winding(winding_id="w1", start_angle_deg=0.0, sector_deg=150.0, turns=10),
            make_winding(winding_id="w2", start_angle_deg=180.0, sector_deg=150.0, turns=10),
        )
    )


def test_manifest_structure() -> None:
    model = build_geometry_model(two_winding_project(), CATALOG)  # type: ignore[arg-type]
    manifest = build_manifest(model)
    assert manifest["schemaVersion"] == 1
    core = manifest["core"]
    assert core["name"] == "Core"  # type: ignore[index]
    windings = manifest["windings"]
    assert [w["windingId"] for w in windings] == ["w1", "w2"]  # type: ignore[index]
    w1 = windings[0]  # type: ignore[index]
    assert len(w1["layers"][0]["turnNames"]) == 10
    assert w1["layers"][0]["turnNames"][0] == "w1_L01_T001"
    assert manifest["symmetry"] is not None
    assert manifest["symmetryRefusal"] is None
    assert manifest["collisions"] == []
    assert manifest["planar"]["conductorCount"] == 40  # type: ignore[index]


def test_manifest_json_deterministic() -> None:
    model_a = build_geometry_model(two_winding_project(), CATALOG)  # type: ignore[arg-type]
    model_b = build_geometry_model(two_winding_project(), CATALOG)  # type: ignore[arg-type]
    assert manifest_json(model_a) == manifest_json(model_b)
    parsed = json.loads(manifest_json(model_a))
    assert parsed == json.loads(manifest_json(model_a))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/geometry/test_manifest.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

Create `src/inductor_designer/geometry/manifest.py`:

```python
from __future__ import annotations

import json
from typing import TYPE_CHECKING

from inductor_designer.geometry.collisions import occupancy_summary
from inductor_designer.geometry.naming import (
    core_name,
    lead_names,
    terminal_names,
    winding_names,
)
from inductor_designer.geometry.symmetry import SymmetryPlan

if TYPE_CHECKING:
    from inductor_designer.application.services.geometry_model import GeometryModel


def build_manifest(model: GeometryModel) -> dict[str, object]:
    occupancy = occupancy_summary(model.packings)
    windings: list[dict[str, object]] = []
    for packing in sorted(model.packings, key=lambda p: p.winding_id):
        names = winding_names(packing)
        layers: list[dict[str, object]] = []
        cursor = 0
        for layer in packing.layers:
            count = len(layer.station_deg)
            layers.append(
                {
                    "layer": layer.index,
                    "radialBuildM": layer.radial_build_m,
                    "pitchDeg": layer.pitch_deg,
                    "minPitchDeg": layer.min_pitch_deg,
                    "stationsDeg": list(layer.station_deg),
                    "turnNames": list(names[cursor : cursor + count]),
                }
            )
            cursor += count
        windings.append(
            {
                "windingId": packing.winding_id,
                "insulatedDiameterM": model.insulated_diameter_m[packing.winding_id],
                "bareDiameterM": model.bare_diameter_m[packing.winding_id],
                "sectorDeg": packing.sector_deg,
                "startDeg": packing.start_deg,
                "occupancy": occupancy[packing.winding_id],
                "leadInDeg": packing.lead_in_deg,
                "leadOutDeg": packing.lead_out_deg,
                "wireLengthM": packing.wire_length_m,
                "leadNames": list(lead_names(packing.winding_id)),
                "terminalNames": list(terminal_names(packing.winding_id)),
                "layers": layers,
            }
        )
    symmetry_plan: dict[str, object] | None = None
    symmetry_refusal: dict[str, object] | None = None
    if isinstance(model.symmetry, SymmetryPlan):
        symmetry_plan = {
            "multiplier": model.symmetry.multiplier,
            "sectorDeg": model.symmetry.sector_deg,
            "cutAnglesDeg": list(model.symmetry.cut_angles_deg),
        }
    else:
        symmetry_refusal = {
            "code": model.symmetry.code,
            "message": model.symmetry.message,
        }
    conductor_count = sum(len(w.conductors) for w in model.planar.windings)
    return {
        "schemaVersion": 1,
        "core": {
            "name": core_name(),
            "rInnerM": round(model.core.r_inner_m, 9),
            "rOuterM": round(model.core.r_outer_m, 9),
            "halfHeightM": round(model.core.half_height_m, 9),
            "cornerRadiusM": round(model.core.corner_radius_m, 9),
        },
        "windings": windings,
        "collisions": [
            {
                "kind": issue.kind,
                "windings": [issue.first_winding, issue.second_winding],
                "requiredM": issue.required_m,
                "actualM": issue.actual_m,
                "message": issue.message,
            }
            for issue in model.collisions
        ],
        "symmetry": symmetry_plan,
        "symmetryRefusal": symmetry_refusal,
        "planar": {
            "depthM": model.planar.depth_m,
            "rInnerM": round(model.planar.r_inner_m, 9),
            "rOuterM": round(model.planar.r_outer_m, 9),
            "conductorCount": conductor_count,
        },
    }


def manifest_json(model: GeometryModel) -> str:
    return json.dumps(build_manifest(model), indent=2, sort_keys=True) + "\n"
```

Architecture note: `geometry` must not import `application` at runtime — the `GeometryModel` import is under `TYPE_CHECKING` only, and `build_manifest` accesses attributes structurally. The boundary checker only bans infrastructure imports, but keep the runtime import direction clean anyway. If mypy complains about the forward reference, the annotation string form `"GeometryModel"` is already in place via `from __future__ import annotations`.

- [ ] **Step 4: Create the committed sample project fixture**

Write a tiny throwaway script (do not commit it) or a Python `-c` one-liner that: builds the catalog into a temp sqlite (`tools.build_catalog.build`), opens `SqliteCatalogRepository`, builds an `InductorProject` with `project_id="a7e5b21c-6a53-4f0e-9d3a-2f1b4c8d9e0f"`, `name="M2 golden sample"`, target 2025.2 commercial 3d, `select_core(..., "0077071A7")`, two windings `w1`/`w2` (`turns=10`, `conductor="AWG 18"`, sectors 150° at 0°/180°, spacing 0.0001, clearance 0.001, solid, cw, forward, AC 2 A @ 0°, 100 kHz, DC 5 A), and saves it with `ProjectRepository.save` to `tests/fixtures/sample_geometry_project.inductor.json`.

Run it, then verify: `.venv\Scripts\python.exe -m pytest tests/unit -q` still green.

- [ ] **Step 5: Generate and commit the golden manifest + golden test**

Append to `tests/unit/geometry/test_manifest.py`:

```python
from pathlib import Path

from inductor_designer.adapters.catalog.sqlite_repository import SqliteCatalogRepository
from inductor_designer.adapters.persistence.project_repository import ProjectRepository
from inductor_designer.adapters.persistence.schema_repository import SchemaRepository
from tools.build_catalog import build

ROOT = Path(__file__).resolve().parents[3]
GOLDEN = ROOT / "tests" / "golden" / "sample_geometry_manifest.json"


def test_golden_manifest(tmp_path: Path) -> None:
    index = tmp_path / "catalog.sqlite"
    build(ROOT / "catalog", ROOT / "schemas" / "catalog", index)
    catalog = SqliteCatalogRepository(index)
    repo = ProjectRepository(SchemaRepository(ROOT / "schemas"))
    project = repo.load(ROOT / "tests" / "fixtures" / "sample_geometry_project.inductor.json")
    model = build_geometry_model(project, catalog)
    assert manifest_json(model) == GOLDEN.read_text(encoding="utf-8")
```

Generate the golden: run the same build steps in a `-c` script and write `manifest_json(model)` to `tests/golden/sample_geometry_manifest.json`. **Eyeball the file before committing** — station angles must be within sectors, 2 windings × 1 layer × 10 turns, symmetry multiplier 2, zero collisions. Then run the golden test — it must pass.

- [ ] **Step 6: Run tests and gates**

Run: `.venv\Scripts\python.exe -m pytest tests -q -m "not aedt and not ui" && .venv\Scripts\python.exe -m ruff check . && .venv\Scripts\python.exe -m mypy && .venv\Scripts\python.exe tools/check_architecture.py`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/inductor_designer/geometry/manifest.py tests/unit/geometry/test_manifest.py tests/fixtures/sample_geometry_project.inductor.json tests/golden/sample_geometry_manifest.json
git commit -m "feat(geometry): canonical geometry manifest with committed golden"
```

---

### Task 12: Property-based invariants (hypothesis)

**Files:**
- Test: `tests/property/__init__.py`, `tests/property/test_packing_properties.py`

**Interfaces:**
- Consumes: Tasks 3–5 public APIs. No production code in this task; if a property finds a real bug, fix it in the owning module with a regression note in the commit.

- [ ] **Step 1: Write the property suite**

Create `tests/property/__init__.py` (empty) and `tests/property/test_packing_properties.py`:

```python
from __future__ import annotations

import math

from hypothesis import given, settings
from hypothesis import strategies as st

from inductor_designer.geometry.core_solid import FinishedCore
from inductor_designer.geometry.packing import PackingError, WindingSpec, pack_winding
from inductor_designer.geometry.turn_path import turn_loop_length_m

cores = st.builds(
    FinishedCore,
    r_inner_m=st.floats(min_value=0.004, max_value=0.03),
    r_outer_m=st.floats(min_value=0.032, max_value=0.06),
    half_height_m=st.floats(min_value=0.002, max_value=0.02),
    corner_radius_m=st.just(0.0),
)

specs = st.builds(
    WindingSpec,
    winding_id=st.just("w"),
    turns=st.integers(min_value=1, max_value=300),
    insulated_diameter_m=st.floats(min_value=0.0002, max_value=0.003),
    start_deg=st.floats(min_value=0.0, max_value=359.0),
    sector_deg=st.floats(min_value=15.0, max_value=360.0),
    min_spacing_m=st.floats(min_value=0.0, max_value=0.0005),
    min_clearance_m=st.just(0.001),
)


@settings(max_examples=200, deadline=None)
@given(core=cores, spec=specs)
def test_packing_invariants(core: FinishedCore, spec: WindingSpec) -> None:
    try:
        packed = pack_winding(core, spec)
    except PackingError as error:
        assert 0 <= error.max_turns < spec.turns
        if error.max_turns > 0:
            refit = pack_winding(core, WindingSpec(
                spec.winding_id, error.max_turns, spec.insulated_diameter_m,
                spec.start_deg, spec.sector_deg, spec.min_spacing_m, spec.min_clearance_m,
            ))
            total = sum(len(layer.station_deg) for layer in refit.layers)
            assert total == error.max_turns
        return

    total = sum(len(layer.station_deg) for layer in packed.layers)
    assert total == spec.turns

    for layer in packed.layers:
        # stations inside the declared sector
        for station in layer.station_deg:
            assert spec.start_deg <= station <= spec.start_deg + spec.sector_deg
        # pitch respects the chord constraint
        assert layer.pitch_deg >= layer.min_pitch_deg - 1e-9
        # layer stays inside the bore
        r_k = core.r_inner_m - layer.radial_build_m
        assert r_k - spec.insulated_diameter_m / 2.0 > 0.0
        # stations strictly increasing
        assert all(
            b > a for a, b in zip(layer.station_deg, layer.station_deg[1:], strict=False)
        )
        # adjacent wire surfaces truly separated (chord distance at the bore circle)
        if len(layer.station_deg) >= 2:
            gap_rad = math.radians(layer.pitch_deg)
            chord = 2.0 * r_k * math.sin(gap_rad / 2.0)
            assert chord >= spec.insulated_diameter_m + spec.min_spacing_m - 1e-9

    # wire length lower bound: turns * single loop at layer 1
    floor_length = spec.turns * turn_loop_length_m(core, 1, spec.insulated_diameter_m)
    assert packed.wire_length_m >= floor_length - 1e-9


@settings(max_examples=100, deadline=None)
@given(core=cores, spec=specs)
def test_packing_is_deterministic(core: FinishedCore, spec: WindingSpec) -> None:
    try:
        first = pack_winding(core, spec)
    except PackingError:
        return
    assert first == pack_winding(core, spec)
```

- [ ] **Step 2: Run the property suite**

Run: `.venv\Scripts\python.exe -m pytest tests/property -q`
Expected: PASS. If hypothesis finds a counterexample, the shrunk case is a real bug in Tasks 4–5: fix the owning module, add the shrunk case as a named regression test in that module's unit test file, re-run everything.

- [ ] **Step 3: Run full gates**

Run: `.venv\Scripts\python.exe -m pytest tests -q -m "not aedt and not ui" && .venv\Scripts\python.exe -m ruff check . && .venv\Scripts\python.exe -m mypy`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/property
git commit -m "test(geometry): property-based packing invariants with hypothesis"
```

---

### Task 13: Tessellation

**Files:**
- Create: `src/inductor_designer/geometry/tessellation.py`
- Test: `tests/unit/geometry/test_tessellation.py`

**Interfaces:**
- Consumes: `FinishedCore`, turn/connector/lead builders (Task 4), `PackedWinding` (Task 5), primitives (Task 2).
- Produces:
  - `Mesh(positions: tuple[float, ...], normals: tuple[float, ...])` — frozen; non-indexed triangle soup, `len(positions) == len(normals)`, divisible by 9 (3 vertices × xyz per triangle). Invariants in `__post_init__`.
  - `tessellate_core(core: FinishedCore, angular_segments: int = 96, corner_samples: int = 4) -> Mesh` — sweeps the cross-section outline (rectangle, or rounded rectangle when `corner_radius > 0`) around Z; flat per-quad normals (each quad → 2 triangles sharing the face normal).
  - `tessellate_winding(core: FinishedCore, packing: PackedWinding, tube_sides: int = 12) -> Mesh` — for every turn: `build_turn_loop` sampled via `sample_path`, swept as a tube of radius `insulated_diameter/2` with parallel-transport frames; plus connectors between consecutive stations of each layer and the two lead stubs.
  - `tube(points: Sequence[Vec3], radius: float, sides: int = 12) -> Mesh` — public helper (used by winding tessellation and unit-testable alone). Degenerate inputs (`len(points) < 2`, zero-length steps) raise `ValueError`.

Tube construction: for each polyline vertex compute tangent (mean of adjacent segment directions); build the first frame with any perpendicular seed; parallel-transport the normal along the polyline (project previous normal onto the plane perpendicular to the new tangent, re-normalize; fall back to the seed when projection collapses). Ring vertices `p_i + (n·cos φ + b·sin φ)·radius`. Adjacent rings form quads → 2 triangles; smooth normals = radial direction of each ring vertex.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/geometry/test_tessellation.py`:

```python
from __future__ import annotations

import math

import pytest

from inductor_designer.geometry.core_solid import FinishedCore
from inductor_designer.geometry.packing import WindingSpec, pack_winding
from inductor_designer.geometry.primitives import Vec3
from inductor_designer.geometry.tessellation import Mesh, tessellate_core, tessellate_winding, tube

CORE = FinishedCore(r_inner_m=0.00973, r_outer_m=0.01683, half_height_m=0.005715,
                    corner_radius_m=0.0)
D = 0.001118


def triangle_count(mesh: Mesh) -> int:
    assert len(mesh.positions) == len(mesh.normals)
    assert len(mesh.positions) % 9 == 0
    return len(mesh.positions) // 9


def test_mesh_invariants() -> None:
    with pytest.raises(ValueError):
        Mesh(positions=(0.0,) * 8, normals=(0.0,) * 8)
    with pytest.raises(ValueError):
        Mesh(positions=(0.0,) * 9, normals=(0.0,) * 18)


def test_core_mesh_bounds() -> None:
    mesh = tessellate_core(CORE, angular_segments=48)
    assert triangle_count(mesh) > 0
    xs = mesh.positions[0::3]
    zs = mesh.positions[2::3]
    radius = max(math.hypot(x, y) for x, y in zip(mesh.positions[0::3],
                                                  mesh.positions[1::3], strict=True))
    assert radius == pytest.approx(CORE.r_outer_m, rel=1e-6)
    assert max(zs) == pytest.approx(CORE.half_height_m, rel=1e-6)
    assert min(xs) < 0 < max(xs)  # full revolution


def test_tube_straight_segment() -> None:
    points = [Vec3(0.0, 0.0, 0.0), Vec3(0.0, 0.0, 0.01)]
    mesh = tube(points, radius=0.001, sides=8)
    assert triangle_count(mesh) == 8 * 2
    radii = [
        math.hypot(x, y)
        for x, y in zip(mesh.positions[0::3], mesh.positions[1::3], strict=True)
    ]
    assert all(r == pytest.approx(0.001, rel=1e-9) for r in radii)


def test_tube_rejects_degenerate() -> None:
    with pytest.raises(ValueError):
        tube([Vec3(0.0, 0.0, 0.0)], radius=0.001)


def test_winding_mesh_scales_with_turns() -> None:
    small = pack_winding(CORE, WindingSpec("w1", 3, D, 0.0, 300.0, 0.0001, 0.001))
    large = pack_winding(CORE, WindingSpec("w1", 12, D, 0.0, 300.0, 0.0001, 0.001))
    mesh_small = tessellate_winding(CORE, small)
    mesh_large = tessellate_winding(CORE, large)
    assert triangle_count(mesh_large) > triangle_count(mesh_small)


def test_winding_mesh_stays_outside_axis() -> None:
    packing = pack_winding(CORE, WindingSpec("w1", 8, D, 0.0, 300.0, 0.0001, 0.001))
    mesh = tessellate_winding(CORE, packing)
    for x, y in zip(mesh.positions[0::3], mesh.positions[1::3], strict=True):
        assert math.hypot(x, y) > 0.001
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/geometry/test_tessellation.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

Create `src/inductor_designer/geometry/tessellation.py`:

```python
from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from inductor_designer.geometry.core_solid import FinishedCore
from inductor_designer.geometry.packing import PackedWinding
from inductor_designer.geometry.primitives import Vec3, sample_path
from inductor_designer.geometry.turn_path import build_connector, build_lead, build_turn_loop


@dataclass(frozen=True, slots=True)
class Mesh:
    positions: tuple[float, ...]
    normals: tuple[float, ...]

    def __post_init__(self) -> None:
        if len(self.positions) != len(self.normals):
            raise ValueError("positions and normals must have equal length")
        if len(self.positions) % 9 != 0:
            raise ValueError("triangle soup length must be divisible by 9")


def _merge(meshes: Sequence[Mesh]) -> Mesh:
    positions: list[float] = []
    normals: list[float] = []
    for mesh in meshes:
        positions.extend(mesh.positions)
        normals.extend(mesh.normals)
    return Mesh(tuple(positions), tuple(normals))


def _emit_quad(
    positions: list[float],
    normals: list[float],
    a: Vec3,
    b: Vec3,
    c: Vec3,
    d: Vec3,
    na: Vec3,
    nb: Vec3,
    nc: Vec3,
    nd: Vec3,
) -> None:
    for tri in ((a, b, c), (a, c, d)):
        norms = {id(a): na, id(b): nb, id(c): nc, id(d): nd}
        for vertex in tri:
            positions.extend((vertex.x, vertex.y, vertex.z))
            n = norms[id(vertex)]
            normals.extend((n.x, n.y, n.z))


def _cross_section_outline(core: FinishedCore, corner_samples: int) -> list[tuple[float, float]]:
    """Closed (r, z) outline of the cross-section, counter-clockwise."""
    c = core.corner_radius_m
    ri, ro, hh = core.r_inner_m, core.r_outer_m, core.half_height_m
    if c <= 0.0:
        return [(ri, -hh), (ro, -hh), (ro, hh), (ri, hh)]
    outline: list[tuple[float, float]] = []
    corners = (
        ((ro - c, -(hh - c)), -90.0),
        ((ro - c, hh - c), 0.0),
        ((ri + c, hh - c), 90.0),
        ((ri + c, -(hh - c)), 180.0),
    )
    for (cr, cz), start_deg in corners:
        for i in range(corner_samples + 1):
            angle = math.radians(start_deg + 90.0 * i / corner_samples)
            outline.append((cr + c * math.cos(angle), cz + c * math.sin(angle)))
    return outline


def tessellate_core(
    core: FinishedCore, angular_segments: int = 96, corner_samples: int = 4
) -> Mesh:
    outline = _cross_section_outline(core, corner_samples)
    count = len(outline)
    positions: list[float] = []
    normals: list[float] = []

    def at(theta: float, r: float, z: float) -> Vec3:
        return Vec3(r * math.cos(theta), r * math.sin(theta), z)

    for s in range(angular_segments):
        t0 = 2.0 * math.pi * s / angular_segments
        t1 = 2.0 * math.pi * (s + 1) / angular_segments
        for i in range(count):
            (r0, z0) = outline[i]
            (r1, z1) = outline[(i + 1) % count]
            a = at(t0, r0, z0)
            b = at(t1, r0, z0)
            c_v = at(t1, r1, z1)
            d = at(t0, r1, z1)
            edge1 = b - a
            edge2 = d - a
            face_n = edge1.cross(edge2)
            n = face_n.normalized() if face_n.norm() > 0 else Vec3(0.0, 0.0, 1.0)
            _emit_quad(positions, normals, a, b, c_v, d, n, n, n, n)
    return Mesh(tuple(positions), tuple(normals))


def _frames(points: Sequence[Vec3]) -> list[tuple[Vec3, Vec3, Vec3]]:
    """(tangent, normal, binormal) per point via parallel transport."""
    if len(points) < 2:
        raise ValueError("tube needs at least 2 points")
    tangents: list[Vec3] = []
    for i in range(len(points)):
        if i == 0:
            direction = points[1] - points[0]
        elif i == len(points) - 1:
            direction = points[-1] - points[-2]
        else:
            direction = points[i + 1] - points[i - 1]
        if direction.norm() == 0.0:
            raise ValueError("degenerate step in tube path")
        tangents.append(direction.normalized())
    seed = Vec3(0.0, 0.0, 1.0)
    if abs(tangents[0].dot(seed)) > 0.9:
        seed = Vec3(1.0, 0.0, 0.0)
    normal = (seed - tangents[0].scaled(tangents[0].dot(seed))).normalized()
    frames: list[tuple[Vec3, Vec3, Vec3]] = []
    for tangent in tangents:
        projected = normal - tangent.scaled(tangent.dot(normal))
        if projected.norm() < 1e-9:
            projected = seed - tangent.scaled(tangent.dot(seed))
        normal = projected.normalized()
        frames.append((tangent, normal, tangent.cross(normal)))
    return frames


def tube(points: Sequence[Vec3], radius: float, sides: int = 12) -> Mesh:
    frames = _frames(points)
    rings: list[list[Vec3]] = []
    ring_normals: list[list[Vec3]] = []
    for point, (_, normal, binormal) in zip(points, frames, strict=True):
        ring: list[Vec3] = []
        ring_n: list[Vec3] = []
        for s in range(sides):
            phi = 2.0 * math.pi * s / sides
            radial = normal.scaled(math.cos(phi)) + binormal.scaled(math.sin(phi))
            ring.append(point + radial.scaled(radius))
            ring_n.append(radial)
        rings.append(ring)
        ring_normals.append(ring_n)
    positions: list[float] = []
    normals: list[float] = []
    for i in range(len(rings) - 1):
        for s in range(sides):
            s_next = (s + 1) % sides
            _emit_quad(
                positions,
                normals,
                rings[i][s],
                rings[i][s_next],
                rings[i + 1][s_next],
                rings[i + 1][s],
                ring_normals[i][s],
                ring_normals[i][s_next],
                ring_normals[i + 1][s_next],
                ring_normals[i + 1][s],
            )
    return Mesh(tuple(positions), tuple(normals))


def tessellate_winding(
    core: FinishedCore, packing: PackedWinding, tube_sides: int = 12
) -> Mesh:
    d = packing.insulated_diameter_m
    radius = d / 2.0
    meshes: list[Mesh] = []
    for layer in packing.layers:
        for station in layer.station_deg:
            loop = build_turn_loop(core, layer.index, d, station)
            points = list(sample_path(loop))
            points.append(points[0])  # close the loop
            meshes.append(tube(points, radius, tube_sides))
        for a, b in zip(layer.station_deg, layer.station_deg[1:], strict=False):
            connector = build_connector(core, layer.index, d, a, b)
            meshes.append(tube(list(sample_path([connector])), radius, tube_sides))
    for station in (packing.lead_in_deg, packing.lead_out_deg):
        lead = build_lead(core, 1, d, station)
        meshes.append(tube(list(sample_path([lead])), radius, tube_sides))
    return _merge(meshes)
```

- [ ] **Step 4: Run tests and gates**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/geometry -q && .venv\Scripts\python.exe -m ruff check . && .venv\Scripts\python.exe -m mypy && .venv\Scripts\python.exe tools/check_architecture.py`
Expected: PASS. (`_emit_quad`'s `id()`-keyed normal lookup requires the four corner objects to be distinct instances — they are, coming fresh from arithmetic. If a property test ever hits aliasing, switch to passing `(vertex, normal)` pairs.)

- [ ] **Step 5: Commit**

```bash
git add src/inductor_designer/geometry/tessellation.py tests/unit/geometry/test_tessellation.py
git commit -m "feat(geometry): tessellate core and windings into triangle-soup meshes"
```

---

### Task 14: Qt Quick 3D preview (viewer only)

**Files:**
- Create: `src/inductor_designer/ui/preview_geometry.py`
- Modify: `src/inductor_designer/ui/main.py` (read it first; extend, don't rewrite)
- Modify: `src/inductor_designer/ui/qml/PreviewPane.qml` (read it first)
- Test: `tests/ui/test_preview_smoke.py`

**Interfaces:**
- Consumes: `GeometryModel` (Task 10), `Mesh`/`tessellate_core`/`tessellate_winding` (Task 13), `ProjectRepository`, `SchemaRepository`, `SqliteCatalogRepository`.
- Produces:
  - `ui.preview_geometry.MeshGeometry(QQuick3DGeometry)` — fills interleaved position+normal float32 vertex data from a `Mesh`; sets bounds and `Triangles` primitive type.
  - `ui.preview_geometry.build_preview_entries(model: GeometryModel) -> list[PreviewEntry]` where `PreviewEntry` is a small `QObject` with constant properties `geometry` (the `MeshGeometry`), `color` (str, `#rrggbb`), `opacity` (float). Core entry first (color `#8a8a8a`, opacity 0.35), then one entry per winding (opacity 1.0) cycling the palette `("#e07a5f", "#3d9970", "#3f88c5", "#f2bb05", "#9656a1", "#2a9d8f")` in `windingId` order.
  - `inductor-designer --project <path> [--catalog <sqlite>]` CLI: loads the project, opens the catalog index (default `artifacts/catalog/catalog.sqlite`; missing file → exit code 2 with message `Catalog index not found; run: python -m tools.build_catalog`), builds the model, injects `previewEntries` as a QML context property, shows the window. Without `--project` the launcher behaves exactly as today (M0 shell).

QML sketch for `PreviewPane.qml` (adapt to the existing file's structure — keep whatever the M0 smoke test asserts):

```qml
View3D {
    anchors.fill: parent
    environment: SceneEnvironment { clearColor: "#1a1a2e"; backgroundMode: SceneEnvironment.Color }
    PerspectiveCamera { id: camera; position: Qt.vector3d(0, -80, 40) }
    OrbitCameraController { camera: camera; origin: originNode }
    Node { id: originNode }
    DirectionalLight { eulerRotation.x: -30 }
    DirectionalLight { eulerRotation.x: 150; brightness: 0.5 }
    Repeater3D {
        model: typeof previewEntries !== "undefined" ? previewEntries : []
        Model {
            geometry: modelData.geometry
            scale: Qt.vector3d(1000, 1000, 1000)  // meters -> millimeters for camera sanity
            materials: DefaultMaterial {
                diffuseColor: modelData.color
                opacity: modelData.opacity
            }
        }
    }
}
```

`MeshGeometry` implementation core (PySide6):

```python
from __future__ import annotations

import struct

from PySide6.QtCore import Property, QByteArray, QObject
from PySide6.QtQuick3D import QQuick3DGeometry

from inductor_designer.application.services.geometry_model import GeometryModel
from inductor_designer.geometry.tessellation import Mesh, tessellate_core, tessellate_winding


class MeshGeometry(QQuick3DGeometry):
    def __init__(self, mesh: Mesh) -> None:
        super().__init__()
        vertex_count = len(mesh.positions) // 3
        interleaved = bytearray()
        for i in range(vertex_count):
            interleaved += struct.pack(
                "<6f",
                mesh.positions[3 * i],
                mesh.positions[3 * i + 1],
                mesh.positions[3 * i + 2],
                mesh.normals[3 * i],
                mesh.normals[3 * i + 1],
                mesh.normals[3 * i + 2],
            )
        self.setVertexData(QByteArray(bytes(interleaved)))
        self.setStride(24)
        self.addAttribute(
            QQuick3DGeometry.Attribute.PositionSemantic,
            0,
            QQuick3DGeometry.Attribute.F32Type,
        )
        self.addAttribute(
            QQuick3DGeometry.Attribute.NormalSemantic,
            12,
            QQuick3DGeometry.Attribute.F32Type,
        )
        self.setPrimitiveType(QQuick3DGeometry.PrimitiveType.Triangles)
        xs = mesh.positions[0::3]
        ys = mesh.positions[1::3]
        zs = mesh.positions[2::3]
        from PySide6.QtGui import QVector3D

        self.setBounds(
            QVector3D(min(xs), min(ys), min(zs)), QVector3D(max(xs), max(ys), max(zs))
        )
```

`PreviewEntry` + `build_preview_entries`:

```python
_PALETTE = ("#e07a5f", "#3d9970", "#3f88c5", "#f2bb05", "#9656a1", "#2a9d8f")


class PreviewEntry(QObject):
    def __init__(self, geometry: MeshGeometry, color: str, opacity: float) -> None:
        super().__init__()
        self._geometry = geometry
        self._color = color
        self._opacity = opacity
        geometry.setParent(self)

    @Property(QObject, constant=True)  # type: ignore[operator, arg-type]
    def geometry(self) -> MeshGeometry:
        return self._geometry

    @Property(str, constant=True)  # type: ignore[operator, arg-type]
    def color(self) -> str:
        return self._color

    @Property(float, constant=True)  # type: ignore[operator, arg-type]
    def opacity(self) -> float:
        return self._opacity


def build_preview_entries(model: GeometryModel) -> list[PreviewEntry]:
    entries = [PreviewEntry(MeshGeometry(tessellate_core(model.core)), "#8a8a8a", 0.35)]
    for i, packing in enumerate(sorted(model.packings, key=lambda p: p.winding_id)):
        mesh = tessellate_winding(model.core, packing)
        entries.append(PreviewEntry(MeshGeometry(mesh), _PALETTE[i % len(_PALETTE)], 1.0))
    return entries
```

- [ ] **Step 1: Read the existing launcher and QML**

Read `src/inductor_designer/ui/main.py`, `src/inductor_designer/ui/qml/Main.qml`, `src/inductor_designer/ui/qml/PreviewPane.qml`, and `tests/ui/test_qml_smoke.py`. The changes below must preserve the M0 smoke test.

- [ ] **Step 2: Write the failing smoke test**

Create `tests/ui/test_preview_smoke.py` (follow the offscreen pattern of `tests/ui/test_qml_smoke.py` — same marker and skip guards):

```python
from __future__ import annotations

import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.ui

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def catalog_index(tmp_path: Path) -> Path:
    from tools.build_catalog import build

    index = tmp_path / "catalog.sqlite"
    build(ROOT / "catalog", ROOT / "schemas" / "catalog", index)
    return index


def test_preview_entries_built_offscreen(catalog_index: Path) -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QGuiApplication

    from inductor_designer.adapters.catalog.sqlite_repository import SqliteCatalogRepository
    from inductor_designer.adapters.persistence.project_repository import ProjectRepository
    from inductor_designer.adapters.persistence.schema_repository import SchemaRepository
    from inductor_designer.application.services.geometry_model import build_geometry_model
    from inductor_designer.ui.preview_geometry import build_preview_entries

    app = QGuiApplication.instance() or QGuiApplication([])
    assert app is not None
    repo = ProjectRepository(SchemaRepository(ROOT / "schemas"))
    project = repo.load(ROOT / "tests" / "fixtures" / "sample_geometry_project.inductor.json")
    model = build_geometry_model(project, SqliteCatalogRepository(catalog_index))
    entries = build_preview_entries(model)
    assert len(entries) == 3  # core + 2 windings
    assert entries[0].opacity < 1.0
    assert entries[1].color != entries[2].color
    assert entries[1].geometry is not None
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/ui/test_preview_smoke.py -q -m ui`
Expected: FAIL with `ModuleNotFoundError: ... preview_geometry`.

- [ ] **Step 4: Implement**

Create `src/inductor_designer/ui/preview_geometry.py` with the `MeshGeometry`, `PreviewEntry`, and `build_preview_entries` code from the Interfaces section (one module, imports consolidated at the top — move the `QVector3D` import up).

Extend `src/inductor_designer/ui/main.py`: add `--project` / `--catalog` argument parsing (argparse or the existing pattern); when `--project` is given, load → build model → `engine.rootContext().setContextProperty("previewEntries", entries)` before loading the QML; keep a Python reference to `entries` for the window's lifetime. Errors: missing catalog index → print the run-builder message, return exit code 2; `GeometryModelError` → print each issue, return exit code 3.

Extend `src/inductor_designer/ui/qml/PreviewPane.qml` with the `View3D` + `Repeater3D` sketch above, guarded so the pane still renders when `previewEntries` is undefined (M0 behavior).

- [ ] **Step 5: Run UI tests and gates**

Run: `.venv\Scripts\python.exe -m pytest tests/ui -q -m ui && .venv\Scripts\python.exe -m pytest tests -q -m "not aedt and not ui" && .venv\Scripts\python.exe -m ruff check . && .venv\Scripts\python.exe -m mypy && .venv\Scripts\python.exe tools/check_architecture.py`
Expected: all PASS — both the old QML smoke test and the new preview smoke test.

- [ ] **Step 6: Manual visual check (report, don't skip)**

Run: `.venv\Scripts\python.exe -m tools.build_catalog` then `.venv\Scripts\python.exe -m inductor_designer.ui.main --project tests/fixtures/sample_geometry_project.inductor.json` (or via the console script). Confirm: a gray translucent toroid, two colored windings on opposite sides, orbit with the mouse. Record what you saw in the task report.

- [ ] **Step 7: Commit**

```bash
git add src/inductor_designer/ui/preview_geometry.py src/inductor_designer/ui/main.py src/inductor_designer/ui/qml/PreviewPane.qml tests/ui/test_preview_smoke.py
git commit -m "feat(ui): render the geometry model in a Qt Quick 3D orbit-camera preview"
```

---

### Task 15: Milestone exit verification, docs, and handoff

**Files:**
- Modify: `docs/development/ROADMAP.md`, `docs/superpowers/plans/README.md`, `README.md`

**Interfaces:**
- Consumes: everything. No new production code.

- [ ] **Step 1: Run the complete gate set**

Run:
```
.venv\Scripts\python.exe -m pytest tests -q -m "not aedt" --cov --cov-branch
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m mypy
.venv\Scripts\python.exe tools/check_architecture.py
```
Expected: all green, coverage ≥ 80%. The `-m "not aedt"` run includes the `ui` tests — PySide6 is installed in the venv.

- [ ] **Step 2: Verify the M2 exit criterion explicitly**

The exit criterion is "previewed geometry passes property-based invariants and deterministic golden-manifest tests". Confirm and note in the report:
- `tests/property/test_packing_properties.py` — passed (property invariants)
- `tests/unit/geometry/test_manifest.py::test_golden_manifest` — passed (golden manifest)
- `tests/ui/test_preview_smoke.py` — passed (preview renders the same model)

- [ ] **Step 3: Update documentation status**

- `docs/development/ROADMAP.md`, under "Milestone 2": add a "### Current state" subsection listing the implemented deliverables (finished-core resolution honoring the design note, D-turn paths, multi-layer packing, clearance/occupancy, deterministic naming, symmetry plans, 2D planar model, canonical manifest with golden, hypothesis property suite, tessellation, Qt Quick 3D viewer) and the remaining-work line: "Insulation data (catalog/conductors/insulation-round-wire.yaml) remains `draft` pending human review against IEC 60317-0-1 / NEMA MW1000; the five ferrite core records remain `draft`."
- `docs/superpowers/plans/README.md`: status line gains "Milestone 2 implementation is complete, pending review."
- `README.md`: project status paragraph gains the M2 implementation status.

- [ ] **Step 4: Commit and handoff**

```bash
git add docs/development/ROADMAP.md docs/superpowers/plans/README.md README.md
git commit -m "docs: record Milestone 2 implementation status and remaining reviews"
```

Handoff summary: exit criterion proven by the three test files named in Step 2; human follow-ups are the insulation-data review and the ferrite catalog review; the Milestone 3 plan is written only after M2 review is accepted.

---

## Milestone 2 acceptance criteria

- Geometry never consumes bare nominal dimensions when a catalog finish bound exists (`resolve_finished_core` tests) and never packs a conductor without an insulated diameter.
- `pack_winding` is deterministic, multi-layer, respects spacing/sector/lead margins, and reports the exact feasible turn count on overflow — all proven by unit tests plus hypothesis invariants (≥ 200 examples).
- Turn loops are closed 8-segment planar paths whose sampled length matches the analytic formula to 1e-9 relative.
- Cross-winding bore clearance violations are reported as data, not exceptions; occupancy is reported per winding.
- `propose_symmetry_plan` returns order-m plans only for provably periodic winding sets and typed refusals otherwise.
- The 2D planar model projects every packed turn as an inner/outer conductor pair with core-height depth.
- The geometry manifest is canonical JSON, byte-stable across rebuilds, and matches the committed golden for the committed sample project.
- The Qt Quick 3D preview renders core + windings from the same `GeometryModel` (offscreen smoke test + recorded manual visual check).
- Object names are deterministic and unique (`Core`, `w1_L01_T001`, leads, reserved terminal names).
- Non-AEDT gates green: pytest (unit + property + ui) with ≥ 80% branch coverage, Ruff, mypy strict over `src` and `tools`, architecture checker (geometry imports no Qt/sqlite/OS; application imports no infrastructure).
- Draft-data discipline: insulation values carry `reviewStatus: draft` and are flagged for human review; no draft value is presented as verified.



