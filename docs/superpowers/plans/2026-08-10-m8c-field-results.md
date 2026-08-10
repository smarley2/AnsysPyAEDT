# M8c Field Results Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Report magnetic flux density `B` and current density `J` — maximum and Area-Weighted Mean — from a solved run, using the deterministic representative cross sections already designed for 3D and direct region integration in 2D, with every section recorded and every unobtainable value explicitly unavailable.

**Architecture:** M8b established the path: adapters return backend-raw values, one pure service normalizes them, the manifest carries the result set, and the run directory exports it. M8c adds the field half along the same path. Section selection is pure and solver-independent. The Maxwell 3D adapter creates one non-model sheet per section and evaluates it; the Maxwell 2D adapter integrates the core and conductor regions directly, with no sections; FEMM reports no field value at all and says why.

**Tech Stack:** Python 3.13, PySide6/QML, PyAEDT against AEDT 2025 R2 Commercial, pyFEMM against FEMM 4.2, pytest with `pytest-xdist`, Ruff, strict mypy.

## Global Constraints

- The only supported AEDT target is AEDT 2025 R2 Commercial.
- `domain`, `geometry`, `materials` and `simulation` import no PyAEDT, no Qt, no SQLite and no operating-system API; `tools/check_architecture.py` enforces this.
- Never change a physical assumption, schema, catalog value, unit, source reference or approximation silently.
- Add or update tests before implementing a feature or a fix.
- A quantity that cannot be obtained without misrepresentation is `unavailable` with a reason. It is never silently estimated or omitted.
- A volume average never satisfies the Area-Weighted Mean requirement.
- Reason codes are lowercase dotted `<quantity>.<reason>` strings.
- The project current is RMS; the solver excitation is peak (ADR 0006).
- All code, comments, commits and UI copy in English.
- Full suite: `.venv/Scripts/python.exe -m pytest -n 8`. Live suites are behind the `aedt` and `femm` markers.

## Authority

The algorithm is already approved and is not re-decided here:
[2026-08-10 Representative Cross Sections design](../specs/2026-08-10-representative-cross-sections-design.md).
This plan implements it. Where the plan and that design disagree, the design wins and the plan is wrong.

## Decisions taken with Fabio Posser on 2026-08-10

1. **FEMM reports no field value.** `mo_blockintegral` integrates over the core block happily, but the available integral types give `∫Bx dA` and `∫By dA`, not `∫|B| dA`. In our planar toroid model the flux circulates around the ring, so those component integrals very nearly cancel and would report a near-zero mean at full working flux. FEMM therefore reports `flux-density.not_exposed` and `current-density.not_exposed`, with a reason naming the limitation. Maxwell 3D and 2D report theirs in full.
2. **A DC-biased run reports the combined field.** One solve produces the total field including the bias, so it is reported with `current_convention = combined` and an approximation naming it the DC-biased total. The AC-peak-only and AC-RMS-only entries are `unavailable` with a reason, because a single nonlinear solve cannot separate them.

## Decisions taken in this plan

3. **Per-section values are ordinary `NormalizedQuantity` entries**, scoped `core.section.<id>` and `winding.<id>.section.<id>`, with the section geometry in `provenance`. That satisfies the design's "every section is recorded in the Run Manifest" without adding a manifest schema field, and both exports carry them for free.
4. **The Review screen shows aggregates only** — worst-section mean, across-section average, point maximum — because a run can carry a dozen sections and the screen summarizes. The per-section rows are in `results.json` and `results.csv`, which the section provenance points at.

## Scope

In scope: section selection, 3D sheet creation and evaluation, 2D region integration, per-section and aggregate normalization, conventions and availability, manifest and export, the Review aggregate rows.

Out of scope: anything M8b already delivers; adaptive refinement of the section count; volume averages; non-toroidal geometry.

## File Structure

| File | Responsibility |
| --- | --- |
| `src/inductor_designer/simulation/sections.py` (create) | Pure: `CoreSection`, `ConductorSection`, identifiers |
| `src/inductor_designer/simulation/section_selection.py` (create) | Pure: feature-anchored core planes and skin-depth-gated conductor discs |
| `src/inductor_designer/simulation/raw_results.py` (modify) | `RawFieldSection` and the field half of `RawScalarResults` |
| `src/inductor_designer/simulation/result_vocabulary.py` (modify) | Field quantities, units, section scopes |
| `src/inductor_designer/application/services/field_normalization.py` (create) | Per-section entries plus worst-section and area-weighted aggregates |
| `src/inductor_designer/adapters/pyaedt/section_sheets.py` (create) | Non-model sheet creation from a section list |
| `src/inductor_designer/adapters/pyaedt/field_reader.py` (create) | `get_scalar_field_value` calls for 3D sections and 2D regions |
| `src/inductor_designer/adapters/pyaedt/maxwell3d.py` (modify) | Field extraction inside the existing `results` stage |
| `src/inductor_designer/adapters/pyaedt/maxwell2d.py` (modify) | Direct region integration in the same stage |
| `src/inductor_designer/ui/result_rows.py` (modify) | Aggregate rows; per-section rows point at the export |

---

### Task 1: Core section selection

**Files:**
- Create: `src/inductor_designer/simulation/sections.py`
- Create: `src/inductor_designer/simulation/section_selection.py`
- Test: `tests/unit/simulation/test_core_section_selection.py`

**Interfaces:**
- Consumes: `Winding.start_angle_deg` and `Winding.sector_deg` from the domain.
- Produces: `CoreSection(section_id, azimuth_deg, feature)`; `select_core_sections(windings) -> tuple[CoreSection, ...]` emitting `span-start`, `span-mid`, `span-end` per winding span plus `gap-mid` per uncovered gap, deduplicated at `SECTION_DEDUPE_TOLERANCE_DEG = 0.5` in the feature precedence `span-start`, `span-end`, `span-mid`, `gap-mid`, sorted ascending, identifiers `core.<nn>.<feature>` assigned after sorting.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/simulation/test_core_section_selection.py
from dataclasses import replace

from inductor_designer.simulation.section_selection import select_core_sections
from tests.unit.domain.test_project import make_project


def windings(*spans: tuple[float, float]):
    base = make_project().design.windings[0]
    return tuple(
        replace(base, winding_id=f"w{index}", start_angle_deg=start, sector_deg=sector)
        for index, (start, sector) in enumerate(spans, start=1)
    )


def azimuths(sections) -> list[float]:
    return [section.azimuth_deg for section in sections]


def test_one_full_cover_winding_yields_start_and_midpoint_only() -> None:
    sections = select_core_sections(windings((0.0, 360.0)))

    assert azimuths(sections) == [0.0, 180.0]
    assert [section.feature for section in sections] == ["span-start", "span-mid"]


def test_a_partial_winding_adds_the_uncovered_gap_midpoint() -> None:
    sections = select_core_sections(windings((0.0, 180.0)))

    assert azimuths(sections) == [0.0, 90.0, 180.0, 270.0]
    assert sections[-1].feature == "gap-mid"


def test_two_disjoint_sectors_produce_two_gap_midpoints() -> None:
    sections = select_core_sections(windings((0.0, 90.0), (180.0, 90.0)))

    gaps = [section.azimuth_deg for section in sections if section.feature == "gap-mid"]
    assert gaps == [135.0, 315.0]


def test_a_wrapping_sector_is_handled_as_one_span() -> None:
    sections = select_core_sections(windings((350.0, 40.0)))

    assert 350.0 in azimuths(sections)
    assert 30.0 in azimuths(sections)  # the span end, wrapped


def test_planes_closer_than_the_tolerance_collapse_to_one() -> None:
    sections = select_core_sections(windings((0.0, 180.0), (180.3, 179.7)))

    assert len(azimuths(sections)) == len(set(azimuths(sections)))
    assert all(
        abs(later - earlier) >= 0.5
        for earlier, later in zip(azimuths(sections), azimuths(sections)[1:])
    )


def test_a_span_start_wins_over_a_colliding_span_mid() -> None:
    sections = select_core_sections(windings((0.0, 180.0), (180.0, 180.0)))

    at_180 = [section for section in sections if section.azimuth_deg == 180.0]
    assert len(at_180) == 1
    assert at_180[0].feature in {"span-start", "span-end"}


def test_identifiers_are_stable_and_ordered() -> None:
    first = select_core_sections(windings((0.0, 120.0)))
    second = select_core_sections(windings((0.0, 120.0)))

    assert [section.section_id for section in first] == [
        section.section_id for section in second
    ]
    assert first[0].section_id.startswith("core.00.")
    assert first[1].section_id.startswith("core.01.")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/simulation/test_core_section_selection.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'inductor_designer.simulation.section_selection'`

- [ ] **Step 3: Write the implementation**

`sections.py` holds the two frozen dataclasses and the tolerance constant. `section_selection.py` implements exactly the design's section 5: emit the four feature kinds, normalize every azimuth into `[0, 360)`, deduplicate within the tolerance keeping the higher-precedence feature, sort, then assign zero-padded identifiers. Gap enumeration walks the sorted, wrap-normalized span list once and emits the midpoint of every uncovered arc.

- [ ] **Step 4: Run the tests**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/simulation -q && .venv/Scripts/python.exe -m tools.check_architecture`
Expected: PASS, then a clean architecture check

- [ ] **Step 5: Commit**

```bash
git add src/inductor_designer/simulation/sections.py src/inductor_designer/simulation/section_selection.py tests/unit/simulation/test_core_section_selection.py
git commit -m "feat(simulation): select feature-anchored core sections"
```

---

### Task 2: Conductor section selection

**Files:**
- Modify: `src/inductor_designer/simulation/sections.py`, `src/inductor_designer/simulation/section_selection.py`
- Test: `tests/unit/simulation/test_conductor_section_selection.py`

**Interfaces:**
- Consumes: the modelled turn path from `geometry/turn_path.py`; copper resistivity and its validated temperature range from `simulation/winding_estimate.py`.
- Produces: `ConductorSection(section_id, winding_id, turn_index, station, center_m, normal, radius_m)`; `skin_depth_m(frequency_hz, winding_temperature_c) -> float | None` returning `None` when the temperature leaves the validated copper range; `select_conductor_sections(...) -> tuple[ConductorSection, ...]` applying the gate from the design's section 6 — one `inner-bore` disc on the middle turn when `f = 0` or `delta >= wire_radius`, four stations otherwise, and four stations when the gate cannot be evaluated.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/simulation/test_conductor_section_selection.py
import math

import pytest

from inductor_designer.simulation.section_selection import (
    select_conductor_sections,
    skin_depth_m,
)

STATIONS = ("inner-bore", "top-face", "outer-wall", "bottom-face")


def test_skin_depth_falls_with_frequency() -> None:
    assert skin_depth_m(1_000.0, 25.0) > skin_depth_m(1_000_000.0, 25.0)


def test_skin_depth_is_none_outside_the_validated_copper_range() -> None:
    assert skin_depth_m(100_000.0, 200.0) is None


def test_dc_uses_one_disc_on_the_middle_turn() -> None:
    sections = select_conductor_sections(
        winding_id="w1", turn_count=9, wire_radius_m=1e-3,
        frequency_hz=0.0, winding_temperature_c=25.0,
    )

    assert len(sections) == 1
    assert sections[0].station == "inner-bore"
    assert sections[0].turn_index == 4


def test_a_thick_skin_depth_still_uses_one_disc() -> None:
    # 1 kHz in copper is about 2 mm of skin depth, wider than a 0.5 mm wire.
    sections = select_conductor_sections(
        winding_id="w1", turn_count=4, wire_radius_m=5e-4,
        frequency_hz=1_000.0, winding_temperature_c=25.0,
    )

    assert len(sections) == 1


def test_a_thin_skin_depth_escalates_to_four_stations() -> None:
    sections = select_conductor_sections(
        winding_id="w1", turn_count=4, wire_radius_m=2e-3,
        frequency_hz=1_000_000.0, winding_temperature_c=25.0,
    )

    assert tuple(section.station for section in sections) == STATIONS


def test_an_unevaluable_gate_escalates_conservatively() -> None:
    sections = select_conductor_sections(
        winding_id="w1", turn_count=4, wire_radius_m=2e-3,
        frequency_hz=100_000.0, winding_temperature_c=200.0,
    )

    assert len(sections) == 4


def test_the_middle_turn_is_deterministic_for_both_parities() -> None:
    even = select_conductor_sections(
        winding_id="w1", turn_count=8, wire_radius_m=1e-3,
        frequency_hz=0.0, winding_temperature_c=25.0,
    )
    odd = select_conductor_sections(
        winding_id="w1", turn_count=9, wire_radius_m=1e-3,
        frequency_hz=0.0, winding_temperature_c=25.0,
    )

    assert even[0].turn_index == 3
    assert odd[0].turn_index == 4


def test_every_disc_is_perpendicular_to_the_wire() -> None:
    sections = select_conductor_sections(
        winding_id="w1", turn_count=4, wire_radius_m=2e-3,
        frequency_hz=1_000_000.0, winding_temperature_c=25.0,
    )

    for section in sections:
        assert math.isclose(
            math.sqrt(sum(component**2 for component in section.normal)), 1.0,
            rel_tol=1e-9,
        )


def test_identifiers_name_the_winding_turn_and_station() -> None:
    sections = select_conductor_sections(
        winding_id="w1", turn_count=9, wire_radius_m=1e-3,
        frequency_hz=0.0, winding_temperature_c=25.0,
    )

    assert sections[0].section_id == "winding.w1.turn04.inner-bore"
```

The signature above is deliberately flat rather than taking a plan object: selection needs only these five values, and a flat signature keeps the test readable. The caller in Task 4 supplies them from the plan.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/simulation/test_conductor_section_selection.py -q`
Expected: FAIL, `ImportError: cannot import name 'select_conductor_sections'`

- [ ] **Step 3: Write the implementation**

```python
MU_0 = 4.0e-7 * math.pi
STATIONS: tuple[str, ...] = ("inner-bore", "top-face", "outer-wall", "bottom-face")


def skin_depth_m(frequency_hz: float, winding_temperature_c: float) -> float | None:
    """``None`` when copper resistivity is not validated at this temperature."""
    if not (
        COPPER_MIN_TEMPERATURE_C
        <= winding_temperature_c
        <= COPPER_MAX_TEMPERATURE_C
    ):
        return None
    if frequency_hz <= 0.0:
        return math.inf
    rho = COPPER_RHO_20_OHM_M * (
        1.0 + COPPER_ALPHA_20_PER_C * (winding_temperature_c - 20.0)
    )
    return math.sqrt(rho / (math.pi * frequency_hz * MU_0))
```

The gate then reads: `delta is None` or `delta < wire_radius_m` selects all four stations; otherwise one `inner-bore` disc. Station centres and tangents come from the existing turn path; the tangent is normalized before it becomes the disc normal.

- [ ] **Step 4: Run the tests**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/simulation -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/inductor_designer/simulation tests/unit/simulation/test_conductor_section_selection.py
git commit -m "feat(simulation): select skin-depth-gated conductor sections"
```

---

### Task 3: Field vocabulary and raw field values

**Files:**
- Modify: `src/inductor_designer/simulation/result_vocabulary.py`
- Modify: `src/inductor_designer/simulation/raw_results.py`
- Test: `tests/unit/simulation/test_field_vocabulary.py`

**Interfaces:**
- Produces: `FIELD_QUANTITIES = (FLUX_DENSITY, CURRENT_DENSITY)`; units `T` and `A/m^2`; `core_section_scope(section_id)` returning `core.section.<id>` and `conductor_section_scope(winding_id, section_id)` returning `winding.<id>.section.<id>`; `RawFieldSection(section_id, scope, area_m2, mean, maximum, diagnostic)` where `mean` and `maximum` are `float | None`; `RawScalarResults.flux_density_sections` and `.current_density_sections`, both defaulting to `()`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/simulation/test_field_vocabulary.py
from inductor_designer.domain.project import RequestedOutput
from inductor_designer.simulation.raw_results import RawFieldSection, RawScalarResults
from inductor_designer.simulation.result_vocabulary import (
    FIELD_QUANTITIES,
    SCALAR_QUANTITIES,
    conductor_section_scope,
    core_section_scope,
    unit_for,
)


def test_field_quantities_are_separate_from_the_scalar_set() -> None:
    assert set(FIELD_QUANTITIES) == {
        RequestedOutput.FLUX_DENSITY,
        RequestedOutput.CURRENT_DENSITY,
    }
    assert not set(FIELD_QUANTITIES) & set(SCALAR_QUANTITIES)


def test_field_units_are_si() -> None:
    assert unit_for(RequestedOutput.FLUX_DENSITY) == "T"
    assert unit_for(RequestedOutput.CURRENT_DENSITY) == "A/m^2"


def test_section_scopes_are_stable() -> None:
    assert core_section_scope("core.00.span-start") == "core.section.core.00.span-start"
    assert (
        conductor_section_scope("w1", "winding.w1.turn04.inner-bore")
        == "winding.w1.section.winding.w1.turn04.inner-bore"
    )


def test_a_raw_field_section_may_report_nothing() -> None:
    section = RawFieldSection(
        section_id="core.00.span-start",
        scope="core.section.core.00.span-start",
        area_m2=1e-4,
        mean=None,
        maximum=None,
        diagnostic="field calculator returned no data",
    )

    assert section.mean is None
    assert section.diagnostic


def test_raw_results_default_to_no_field_sections() -> None:
    raw = RawScalarResults()

    assert raw.flux_density_sections == ()
    assert raw.current_density_sections == ()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/simulation/test_field_vocabulary.py -q`
Expected: FAIL, `ImportError: cannot import name 'FIELD_QUANTITIES'`

- [ ] **Step 3: Write the implementation**

Add the two quantities, their units and the two scope helpers to `result_vocabulary.py`, keeping `SCALAR_QUANTITIES` unchanged so M8b behaviour is untouched. Add `RawFieldSection` and the two tuple fields to `raw_results.py`.

- [ ] **Step 4: Run the tests**

Run: `.venv/Scripts/python.exe -m pytest tests/unit -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/inductor_designer/simulation tests/unit/simulation/test_field_vocabulary.py
git commit -m "feat(simulation): add field quantities and raw section values"
```

---

### Task 4: Maxwell 3D section sheets and evaluation

**Files:**
- Create: `src/inductor_designer/adapters/pyaedt/section_sheets.py`
- Create: `src/inductor_designer/adapters/pyaedt/field_reader.py`
- Modify: `src/inductor_designer/adapters/pyaedt/maxwell3d.py`
- Test: `tests/unit/adapters/test_maxwell3d_field_extraction.py`

**Interfaces:**
- Consumes: the section lists from Tasks 1 and 2.
- Produces: on the app protocol, `create_section_sheet(section) -> str` returning the created sheet name and `field_value(quantity, scalar_function, object_name, object_type) -> float`; `read_field_sections(app, sections, quantity) -> tuple[RawFieldSection, ...]`. Sheets are created non-model. Every evaluation is individually guarded: a failure fills that section's `diagnostic` and leaves its `mean` and `maximum` as `None`, and never fails the run.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/adapters/test_maxwell3d_field_extraction.py
from pathlib import Path

import pytest

from inductor_designer.adapters.pyaedt.maxwell3d import PyaedtMaxwell3dExporter
from inductor_designer.application.ports.maxwell_exporter import Maxwell3dExportRequest
from inductor_designer.domain.aedt_target import AedtEdition, AedtRelease
from tests.fakes.maxwell3d_app import FakeMaxwell3dApp, FakeMaxwell3dAppFactory
from tests.unit.simulation.test_plan_builder import build, make_definition

pytestmark = pytest.mark.usefixtures("fake_maxwell_boundary")


def export(tmp_path: Path, app: FakeMaxwell3dApp, **overrides: object):
    base: dict[str, object] = {
        "plan": build((make_definition(),)),
        "release": AedtRelease(2025, 2),
        "edition": AedtEdition.COMMERCIAL,
        "non_graphical": True,
        "output_directory": tmp_path / "out",
        "project_name": "Field_case",
        "solve": True,
    }
    base.update(overrides)
    return PyaedtMaxwell3dExporter(app_factory=FakeMaxwell3dAppFactory(app)).export(
        Maxwell3dExportRequest(**base)  # type: ignore[arg-type]
    )


def test_a_solved_run_reports_a_section_per_selected_plane(tmp_path: Path) -> None:
    app = FakeMaxwell3dApp()

    raw = export(tmp_path, app).raw_results

    assert raw is not None
    assert raw.flux_density_sections
    assert all(section.area_m2 > 0.0 for section in raw.flux_density_sections)


def test_every_sheet_is_created_non_model(tmp_path: Path) -> None:
    app = FakeMaxwell3dApp()

    export(tmp_path, app)

    assert app.created_sheets, "sections become real sheets in the design"
    assert all(sheet.non_model for sheet in app.created_sheets)


def test_conductor_sections_report_current_density(tmp_path: Path) -> None:
    raw = export(tmp_path, FakeMaxwell3dApp()).raw_results

    assert raw is not None
    assert raw.current_density_sections
    assert all(
        section.scope.startswith("winding.")
        for section in raw.current_density_sections
    )


def test_one_failed_section_never_loses_the_others(tmp_path: Path) -> None:
    app = FakeMaxwell3dApp()
    app.fail_field_value_for = "core.00.span-start"

    raw = export(tmp_path, app).raw_results

    assert raw is not None
    failed = [s for s in raw.flux_density_sections if s.diagnostic]
    healthy = [s for s in raw.flux_density_sections if s.mean is not None]
    assert len(failed) == 1
    assert healthy, "the remaining sections still reported"


def test_a_generate_only_run_creates_no_sheets(tmp_path: Path) -> None:
    app = FakeMaxwell3dApp()

    export(tmp_path, app, solve=False)

    assert app.created_sheets == []
```

Extend the fake with `created_sheets`, `fail_field_value_for`, `create_section_sheet` and `field_value`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/adapters/test_maxwell3d_field_extraction.py -q`
Expected: FAIL on the missing field sections

- [ ] **Step 3: Write the implementation**

`section_sheets.py` turns one section into one sheet: a core section is a rectangle in the r-z half-plane at its azimuth, spanning the core cross-section; a conductor section is a circle of the bare wire radius at the disc centre, oriented by the disc normal. Both are created with `non_model=True` so the mesh and the solution are untouched, and both are named after the `section_id`.

`field_reader.py` evaluates each sheet through the app protocol, which the adapter implements over PyAEDT's
`post.get_scalar_field_value(quantity, scalar_function, object_name=..., object_type="surface")`:

```python
def read_field_sections(
    app: FieldCapableApp,
    sections: Sequence[SectionSheet],
    quantity: str,
) -> tuple[RawFieldSection, ...]:
    results: list[RawFieldSection] = []
    for sheet in sections:
        try:
            integral = app.field_value(quantity, "Integrate", sheet.name, "surface")
            maximum = app.field_value(quantity, "Maximum", sheet.name, "surface")
            mean = integral / sheet.area_m2 if sheet.area_m2 > 0.0 else None
            diagnostic = None if mean is not None else "section area is not positive"
        except Exception as error:  # noqa: BLE001 - one section failing is evidence
            mean = maximum = None
            diagnostic = f"{type(error).__name__}: {error}"
        results.append(
            RawFieldSection(
                section_id=sheet.section_id,
                scope=sheet.scope,
                area_m2=sheet.area_m2,
                mean=mean,
                maximum=maximum,
                diagnostic=diagnostic,
            )
        )
    return tuple(results)
```

The Maxwell 3D adapter calls both inside its existing `results` stage, after the scalar read.

> **Live verification required before this task closes:** `Mag_B` and `Mag_J`
> are the assumed field-quantity names, and `"Integrate"` and `"Maximum"` the
> assumed `scalar_function` values. They follow the same rule as the M8b
> expression table: a name AEDT does not recognize produces a per-section
> diagnostic and an unavailable quantity, never a wrong number. Task 8 proves
> them live; the fix is one constant.

- [ ] **Step 4: Run the tests**

Run: `.venv/Scripts/python.exe -m pytest tests/unit -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/inductor_designer/adapters/pyaedt tests/unit/adapters/test_maxwell3d_field_extraction.py tests/fakes
git commit -m "feat(maxwell3d): evaluate B and J on non-model representative cross sections"
```

---

### Task 5: Maxwell 2D region integration

**Files:**
- Modify: `src/inductor_designer/adapters/pyaedt/maxwell2d.py`
- Test: `tests/unit/adapters/test_maxwell2d_field_extraction.py`

**Interfaces:**
- Consumes: `field_reader.read_field_regions(app, regions, quantity)`, the same evaluation with no sheet creation.
- Produces: one `RawFieldSection` for the core region and one per winding's conductor regions, scoped `core.region` and `winding.<id>.region`. 2D creates no sections and no sheets: the design forbids it, because the evaluated area is the region itself.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/adapters/test_maxwell2d_field_extraction.py
from dataclasses import replace
from pathlib import Path

import pytest

from inductor_designer.adapters.pyaedt.maxwell2d import PyaedtMaxwell2dExporter
from tests.contract.test_maxwell2d_exporter_contract import make_request
from tests.fakes.maxwell2d_app import FakeMaxwell2dApp, FakeMaxwell2dAppFactory

pytestmark = pytest.mark.usefixtures("fake_maxwell_boundary")


def export(tmp_path: Path, app: FakeMaxwell2dApp, **overrides: object):
    request = replace(make_request(tmp_path), **overrides)  # type: ignore[arg-type]
    return PyaedtMaxwell2dExporter(app_factory=FakeMaxwell2dAppFactory(app)).export(
        request
    )


def test_2d_integrates_the_regions_directly(tmp_path: Path) -> None:
    raw = export(tmp_path, FakeMaxwell2dApp(), solve=True).raw_results

    assert raw is not None
    assert [s.scope for s in raw.flux_density_sections] == ["core.region"]
    assert all(
        s.scope.endswith(".region") for s in raw.current_density_sections
    )


def test_2d_creates_no_section_sheets(tmp_path: Path) -> None:
    app = FakeMaxwell2dApp()

    export(tmp_path, app, solve=True)

    assert app.created_sheets == [], "2D evaluates the region, never a cut plane"


def test_a_generate_only_2d_run_reports_no_field_sections(tmp_path: Path) -> None:
    raw = export(tmp_path, FakeMaxwell2dApp()).raw_results

    assert raw is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/adapters/test_maxwell2d_field_extraction.py -q`
Expected: FAIL on the missing field sections

- [ ] **Step 3: Write the implementation**

The 2D adapter builds its region list from the plan — the core object name and every conductor object name grouped by winding — and calls `read_field_regions`, which is `read_field_sections` without the sheet creation step. Region area comes from the plan geometry, which already knows the annulus and conductor areas, so no extra solver call is needed.

- [ ] **Step 4: Run the tests**

Run: `.venv/Scripts/python.exe -m pytest tests/unit tests/contract -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/inductor_designer/adapters/pyaedt/maxwell2d.py tests
git commit -m "feat(maxwell2d): integrate B and J over the evaluated regions"
```

---

### Task 6: Field normalization

**Files:**
- Create: `src/inductor_designer/application/services/field_normalization.py`
- Modify: `src/inductor_designer/application/services/result_normalization.py`
- Test: `tests/unit/application/test_field_normalization.py`

**Interfaces:**
- Consumes: `RawFieldSection` tuples, the field vocabulary, `dc_biased: bool`.
- Produces: `normalize_field_results(...) -> tuple[NormalizedQuantity, ...]` emitting, per field quantity: one entry per section, one `worst-section mean`, one `across-section area-weighted average`, and one point maximum. `normalize_scalar_results` gains a `field_sections` argument and appends them, so callers still build one result set.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/application/test_field_normalization.py
import pytest

from inductor_designer.application.services.field_normalization import (
    DC_BIASED_FIELD_NOTE,
    normalize_field_results,
)
from inductor_designer.domain.project import RequestedOutput
from inductor_designer.simulation.raw_results import RawFieldSection
from inductor_designer.simulation.run_contracts import (
    CurrentConvention,
    ResultAvailability,
)


def section(name: str, mean: float | None, maximum: float | None, area: float = 1e-4):
    return RawFieldSection(
        section_id=name,
        scope=f"core.section.{name}",
        area_m2=area,
        mean=mean,
        maximum=maximum,
        diagnostic=None if mean is not None else "no data",
    )


def normalize(sections, *, dc_biased: bool = False):
    return normalize_field_results(
        RequestedOutput.FLUX_DENSITY,
        tuple(sections),
        scope="core",
        provenance="Maxwell 3D field calculator",
        dc_biased=dc_biased,
    )


def find(entries, scope: str):
    return next(entry for entry in entries if entry.scope == scope)


def test_each_section_is_reported_individually() -> None:
    entries = normalize([section("a", 0.1, 0.2), section("b", 0.3, 0.5)])

    assert find(entries, "core.section.a").value == 0.1
    assert find(entries, "core.section.b").value == 0.3


def test_the_worst_section_mean_is_the_maximum_of_the_section_means() -> None:
    entries = normalize([section("a", 0.1, 0.2), section("b", 0.3, 0.5)])

    assert find(entries, "core.worst-section-mean").value == 0.3


def test_the_average_is_weighted_by_section_area() -> None:
    entries = normalize(
        [section("a", 0.1, 0.2, area=1e-4), section("b", 0.3, 0.5, area=3e-4)]
    )

    assert find(entries, "core.area-weighted-average").value == pytest.approx(0.25)


def test_the_point_maximum_is_the_maximum_over_sections() -> None:
    entries = normalize([section("a", 0.1, 0.2), section("b", 0.3, 0.5)])

    assert find(entries, "core.maximum").value == 0.5


def test_a_failed_section_is_named_and_the_aggregates_say_so() -> None:
    entries = normalize([section("a", 0.1, 0.2), section("b", None, None)])

    failed = find(entries, "core.section.b")
    assert failed.availability is ResultAvailability.UNAVAILABLE
    aggregate = find(entries, "core.worst-section-mean")
    assert aggregate.approximation is not None
    assert "b" in aggregate.approximation


def test_every_section_failing_makes_the_aggregate_unavailable() -> None:
    entries = normalize([section("a", None, None), section("b", None, None)])

    aggregate = find(entries, "core.worst-section-mean")
    assert aggregate.availability is ResultAvailability.UNAVAILABLE
    assert aggregate.reason is not None
    assert aggregate.reason.startswith("flux-density.")


def test_without_dc_bias_the_values_carry_the_peak_convention() -> None:
    entries = normalize([section("a", 0.1, 0.2)])

    assert find(entries, "core.maximum").current_convention is CurrentConvention.AC_PEAK


def test_with_dc_bias_the_values_are_combined_and_labelled() -> None:
    entries = normalize([section("a", 0.1, 0.2)], dc_biased=True)

    entry = find(entries, "core.maximum")
    assert entry.current_convention is CurrentConvention.COMBINED
    assert entry.approximation == DC_BIASED_FIELD_NOTE


def test_no_section_at_all_reports_not_exposed() -> None:
    entries = normalize([])

    aggregate = find(entries, "core.worst-section-mean")
    assert aggregate.availability is ResultAvailability.UNAVAILABLE
    assert "not_exposed" in (aggregate.reason or "")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/application/test_field_normalization.py -q`
Expected: FAIL, `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

Aggregates come from the surviving sections only, and carry an approximation naming the failed `section_id` values whenever any section failed. With `dc_biased=True` every field entry uses `CurrentConvention.COMBINED` and carries `DC_BIASED_FIELD_NOTE`; the AC-peak-only and AC-RMS-only entries are not emitted at all, because a single nonlinear solve cannot separate them — decision 2 above. Without DC bias the convention is `AC_PEAK`, and an AC-RMS entry is derived as `peak / sqrt(2)` only under the design's section 8 rule, otherwise `unavailable` with `field.rms_not_derivable`.

- [ ] **Step 4: Run the tests**

Run: `.venv/Scripts/python.exe -m pytest tests/unit -q && .venv/Scripts/python.exe -m mypy src tools`
Expected: PASS, then `Success: no issues found`

- [ ] **Step 5: Commit**

```bash
git add src/inductor_designer/application/services tests/unit/application/test_field_normalization.py
git commit -m "feat(simulation): normalize per-section field results and their aggregates"
```

---

### Task 7: FEMM refusal, manifest, export and Review

**Files:**
- Modify: `src/inductor_designer/application/services/result_normalization.py`
- Modify: `src/inductor_designer/ui/result_rows.py`
- Test: `tests/unit/application/test_field_availability.py`, `tests/unit/ui/test_field_rows.py`

**Interfaces:**
- Produces: for a FEMM run, `flux-density.not_exposed` and `current-density.not_exposed` with the reason from decision 1; field entries flowing into `results.json` and `results.csv` unchanged, because both already render whatever the result set holds; Review rows for the three aggregates per scope, with the per-section rows pointing at the export.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/application/test_field_availability.py
from inductor_designer.application.services.result_normalization import (
    normalize_scalar_results,
)
from inductor_designer.domain.project import RequestedOutput
from inductor_designer.simulation.raw_results import RawScalarResults
from inductor_designer.simulation.run_contracts import ResultAvailability, RunBackend


def test_femm_says_why_it_reports_no_field_value() -> None:
    result_set = normalize_scalar_results(
        RawScalarResults(),
        run_id="r",
        backend=RunBackend.FEMM,
        requested_outputs=(RequestedOutput.FLUX_DENSITY,),
        provenance="FEMM circuit properties",
    )

    entry = result_set.quantities[0]
    assert entry.availability is ResultAvailability.UNAVAILABLE
    assert entry.reason is not None
    assert entry.reason.startswith("flux-density.not_exposed")
    assert "block integral" in entry.reason.casefold()
```

```python
# tests/unit/ui/test_field_rows.py
from inductor_designer.domain.project import RequestedOutput
from inductor_designer.ui.result_rows import result_rows
from tests.unit.ui.test_result_rows import available, rows


def test_a_flux_density_renders_in_millitesla() -> None:
    row = rows(available(RequestedOutput.FLUX_DENSITY, "core.maximum", 0.32))[0]

    assert row["label"] == "Flux density (maximum)"
    assert row["text"].startswith("320")
    assert row["text"].endswith("mT")


def test_a_current_density_renders_in_amperes_per_square_millimetre() -> None:
    row = rows(
        available(RequestedOutput.CURRENT_DENSITY, "winding.w1.maximum", 3.5e6)
    )[0]

    assert "A/mm²" in row["text"]


def test_a_per_section_row_points_at_the_export() -> None:
    row = rows(
        available(
            RequestedOutput.FLUX_DENSITY, "core.section.core.00.span-start", 0.31
        )
    )[0]

    assert "results.json" in row["text"] or "section" in row["label"].casefold()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/application/test_field_availability.py tests/unit/ui/test_field_rows.py -q`
Expected: FAIL on the missing FEMM reason and the missing field units

- [ ] **Step 3: Write the implementation**

In `result_normalization.py`, a requested field quantity with no sections and a FEMM backend produces:

```python
FEMM_FIELD_REASON = (
    "FEMM's block integrals expose the field components, not the magnitude, "
    "and around a toroid those components cancel; a magnitude mean cannot be "
    "obtained without misrepresentation."
)
```

`result_rows.py` gains `MILLITESLA` and `AMPERE_PER_SQUARE_MILLIMETRE` from `preliminary_rows.py`, so the field numbers read exactly like the preliminary estimates they are meant to be compared against, and labels the three aggregate scopes.

- [ ] **Step 4: Run the tests**

Run: `set QT_QPA_PLATFORM=offscreen && .venv/Scripts/python.exe -m pytest -n 8 -m "not aedt and not femm" -q`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add src tests
git commit -m "feat(simulation): refuse FEMM field values with a reason and show field rows"
```

---

### Task 8: Live verification and acceptance evidence

**Files:**
- Create: `tests/integration/aedt/test_maxwell_fields_live.py`
- Create: `docs/development/m8c-field-evidence.md`
- Modify: `docs/development/ROADMAP.md`, `docs/superpowers/plans/README.md`

- [ ] **Step 1: Write the live test**

One Maxwell 3D and one Maxwell 2D solve with every output requested. Assert the contract, never a physical value: every selected section appears exactly once, each is available with a unit and a provenance or unavailable with a reason, the aggregates exist, and `results.json` carries the section rows. Assert additionally that the 3D run's section count equals what `select_core_sections` and `select_conductor_sections` chose for that project — the selection and the extraction must not disagree.

- [ ] **Step 2: Run the non-live gate**

```bash
.venv/Scripts/python.exe -m ruff check .
```

```bash
.venv/Scripts/python.exe -m mypy src tools
```

```bash
.venv/Scripts/python.exe -m pytest -n 8 -m "not aedt and not femm" -q
```

Record the exact count and duration.

- [ ] **Step 3: Run the live suites**

```bash
.venv/Scripts/python.exe -m pytest -m aedt -q
```

```bash
.venv/Scripts/python.exe -m pytest -m femm -q
```

The AEDT run proves `Mag_B`, `Mag_J`, `"Integrate"` and `"Maximum"`. A wrong name shows up as a per-section diagnostic, so read `results.json` before concluding anything about the physics.

- [ ] **Step 4: Write the evidence document**

`docs/development/m8c-field-evidence.md` records, per backend: the sections chosen and why, the per-section means and maxima, the two aggregates, and every unavailable entry with its reason. Include one DC-biased run showing the `combined` convention and the absent AC-only entries.

- [ ] **Step 5: Update the roadmap and the plan index**

State that M8c is implementation-complete and awaiting Fabio Posser's acceptance, and that M8 as a whole then rests on M8a, M8b and M8c together.

- [ ] **Step 6: Commit**

```bash
git add docs tests/integration
git commit -m "docs: record M8c field result evidence"
```

---

## Self-Review

**Spec coverage against the representative cross sections design:** the section model — Task 1 and Task 3. Core selection, section 5 — Task 1. Conductor selection with the skin-depth gate, section 6 — Task 2. Extraction and non-model sheets, section 7 — Task 4. Current conventions, section 8 — Task 6. Reported quantities, section 9 — Task 6. Availability and failure, section 10 — Tasks 4 and 6. Manifest and export, section 11 — Task 7, through per-section `NormalizedQuantity` entries rather than a new manifest field (decision 3). Verification, section 12 — Tasks 1, 2 and 8, including the golden-section-set idea, which lands as the live test's cross-check that the extraction saw exactly the sections selection chose. 2D direct region integration — Task 5.

**Placeholder scan:** no TBD. The unproven items — the PyAEDT field-quantity names and the `scalar_function` values — are named explicitly in Task 4 with the live command that settles them.

**Type consistency:** `CoreSection` and `ConductorSection` come from Task 1 and 2 and are consumed in Task 4. `RawFieldSection` comes from Task 3 and is produced in Tasks 4 and 5, consumed in Task 6. `normalize_field_results` is defined in Task 6 and used from `normalize_scalar_results` in Task 7.

**Known risks to raise at review:**

- The 3D section sheet geometry is the least certain part: a core section is a rectangle in a rotated half-plane, and PyAEDT's `create_rectangle` takes a coordinate system rather than an arbitrary normal, so the adapter may need a temporary relative coordinate system per azimuth. That is adapter-local and does not touch selection or normalization.
- Conductor discs are perpendicular to the wire, which means an arbitrary normal in 3D. If sheet creation at an arbitrary orientation proves impractical, the honest fallback is to report the conductor sections as `unavailable` with a reason rather than to silently substitute an axis-aligned cut.
- Section count scales with the winding layout; a design with many disjoint sectors could produce more sheets than expected. The design bounds this in practice at four to eight core planes, but it is not a hard cap.
