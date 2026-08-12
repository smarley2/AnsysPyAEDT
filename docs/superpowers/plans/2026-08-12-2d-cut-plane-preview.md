# 2D Cut Plane Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Draw the 2D model that FEMM and Maxwell 2D will receive, plus the plane it is cut on, inside the application, so a headless run can be checked before it starts.

**Architecture:** Read-only. `GeometryModel.planar` already holds the exact `PlanarModel` the 2D plan builder consumes, so the feature is a new read path in `ui` over data the application already computes. One pure converter turns that model into millimetre drawing data, `GuidedStudioController` carries it beside the 3D preview it already rebuilds, and a QML `Canvas` paints it. No geometry, domain, persistence, or adapter change.

**Tech Stack:** Python 3.10+ (project floor; `.venv` runs 3.13), PySide6/QML with Qt Quick 3D, pytest with `pytest-xdist`, Ruff, strict mypy.

## Global Constraints

- `domain`, `geometry`, `materials` and solver-independent `simulation` import no PyAEDT, no Qt, no FEMM, no SQLite and no operating-system API; `tools/check_architecture.py` enforces this.
- Dependencies point inward. `ui` may import `simulation` and `application`; the reverse is forbidden.
- QML contains no physical formulas. It receives numbers and draws them.
- Never change a physical assumption, schema, catalog value, unit, source reference or approximation silently.
- Add or update tests before implementing a feature or a fix.
- All code, comments, commits and UI copy in English.
- Full suite: `.venv/Scripts/python.exe -m pytest -n 8`. UI tests carry `pytestmark = pytest.mark.ui`.
- Branch: `claude/2d-cut-plane-preview`.

## Authority

The design is approved and is not re-decided here:
[2026-08-12 2D Cut Plane Preview design](../specs/2026-08-12-2d-cut-plane-preview-design.md).
This plan implements it. Where the plan and that design disagree, the design wins and the plan is wrong.

## Decisions taken with Fabio Posser on 2026-08-12

1. **Preview only.** An earlier draft let the user override the cut plane. Dropped: on a toroid the XY equatorial plane is the only reduction the 2D adapters build, so a selector could only ever refuse. The plane becomes a selection when a core shape arrives whose correct plane is not obvious, and that supersedes this design rather than extending it.
2. **The rationale is headless solving.** Solver work is background and non-graphical by default (ADR 0007), so the user never sees the FEMM or Maxwell 2D window. The preview is the only chance to catch a wrong reduction before it costs a solve.

## Decisions taken in this plan

3. **One shared polarity function.** `_polarity` in `plan_builder.py` and `_base_polarity` in `plan_builder2d.py` are identical. The converter needs the same rule, and copying it into `ui` would put a physical convention in the UI layer and invite drift. Task 1 extracts `winding_polarity` and `invert_polarity` into `simulation/maxwell_plan.py` and deletes both duplicates.
4. **The converter takes the project as well as the geometry model.** Polarity depends on `WindingDefinition.winding_direction` and `WindingOperatingPoint.current_direction`, neither of which `GeometryModel` carries. `current_direction` passes through `EffectiveWindingInput` unchanged (`run_contracts.py:73`), so the value the UI reads is the value the exporter uses.
5. **A scale bar, not full axes.** The design's "millimetre scales" is satisfied by one horizontal scale bar with its length labelled plus a centre marker. Full tick-labelled axes cost noticeably more canvas code and add nothing to the check being made.

## Scope

In scope: the shared polarity extraction, the pure converter, the controller property, the QML canvas, the preview-pane toggle, and the translucent plane in the 3D view.

Out of scope: any way to change the plane; axisymmetric r-z generation; core shapes other than the toroid; any change to the 2D model itself.

## File Structure

| File | Responsibility |
| --- | --- |
| `src/inductor_designer/simulation/maxwell_plan.py` (modify) | Home of the shared `winding_polarity` and `invert_polarity` |
| `src/inductor_designer/simulation/plan_builder.py` (modify) | Use the shared polarity; delete the local `_polarity` |
| `src/inductor_designer/simulation/plan_builder2d.py` (modify) | Use the shared polarity; delete the local `_base_polarity` and `_invert` |
| `src/inductor_designer/ui/preview_geometry.py` (modify) | Publish the winding palette so both views agree on colour |
| `src/inductor_designer/ui/cut_plane_view.py` (create) | Pure: `GeometryModel` + project to millimetre drawing data |
| `src/inductor_designer/ui/guided_studio_controller.py` (modify) | Carry the drawing beside the 3D entries; expose `cutPlaneDrawing` |
| `src/inductor_designer/ui/qml/CutPlaneView.qml` (create) | Paint the drawing with `Canvas` |
| `src/inductor_designer/ui/qml/PreviewPane.qml` (modify) | 3D/2D toggle, plane checkbox, translucent plane model |

---

### Task 1: One shared winding polarity

**Files:**
- Modify: `src/inductor_designer/simulation/maxwell_plan.py`
- Modify: `src/inductor_designer/simulation/plan_builder.py:53-60`
- Modify: `src/inductor_designer/simulation/plan_builder2d.py:47-58`
- Test: `tests/unit/simulation/test_winding_polarity.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `winding_polarity(definition: WindingDefinition, current_direction: CurrentDirection) -> Polarity` and `invert_polarity(polarity: Polarity) -> Polarity`, both importable from `inductor_designer.simulation.maxwell_plan`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/simulation/test_winding_polarity.py`:

```python
from __future__ import annotations

import pytest

from inductor_designer.domain.winding import (
    CurrentDirection,
    WindingDirection,
)
from inductor_designer.simulation.maxwell_plan import (
    Polarity,
    invert_polarity,
    winding_polarity,
)
from tests.unit.domain.test_project import make_winding


@pytest.mark.parametrize(
    ("winding_direction", "current_direction", "expected"),
    [
        (WindingDirection.COUNTERCLOCKWISE, CurrentDirection.FORWARD, Polarity.POSITIVE),
        (WindingDirection.COUNTERCLOCKWISE, CurrentDirection.REVERSE, Polarity.NEGATIVE),
        (WindingDirection.CLOCKWISE, CurrentDirection.FORWARD, Polarity.NEGATIVE),
        (WindingDirection.CLOCKWISE, CurrentDirection.REVERSE, Polarity.POSITIVE),
    ],
)
def test_winding_polarity_covers_every_direction_pair(
    winding_direction: WindingDirection,
    current_direction: CurrentDirection,
    expected: Polarity,
) -> None:
    from dataclasses import replace

    definition = replace(make_winding(), winding_direction=winding_direction)

    assert winding_polarity(definition, current_direction) is expected


def test_invert_polarity_swaps_both_values() -> None:
    assert invert_polarity(Polarity.POSITIVE) is Polarity.NEGATIVE
    assert invert_polarity(Polarity.NEGATIVE) is Polarity.POSITIVE
```

If `make_winding` in `tests/unit/domain/test_project.py` does not accept being passed through `dataclasses.replace` with `winding_direction`, read that helper and adjust the construction to set the field directly. Do not change the helper.

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/simulation/test_winding_polarity.py -v`

Expected: FAIL with `ImportError: cannot import name 'winding_polarity'`.

- [ ] **Step 3: Add the shared functions**

In `src/inductor_designer/simulation/maxwell_plan.py`, add the imports the functions need if they are not already present:

```python
from inductor_designer.domain.winding import (
    CurrentDirection,
    WindingDefinition,
    WindingDirection,
)
```

Then add, directly after the `Polarity` definition:

```python
def winding_polarity(
    definition: WindingDefinition,
    current_direction: CurrentDirection,
) -> Polarity:
    """Sign of a winding's go leg for the given current direction.

    Shared by the Maxwell 3D and Maxwell 2D plan builders and by the 2D cut
    plane preview, so the drawn polarity and the exported polarity cannot
    disagree.
    """
    positive = (current_direction is CurrentDirection.FORWARD) == (
        definition.winding_direction is WindingDirection.COUNTERCLOCKWISE
    )
    return Polarity.POSITIVE if positive else Polarity.NEGATIVE


def invert_polarity(polarity: Polarity) -> Polarity:
    return Polarity.NEGATIVE if polarity is Polarity.POSITIVE else Polarity.POSITIVE
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/simulation/test_winding_polarity.py -v`

Expected: PASS, 5 tests.

- [ ] **Step 5: Delete the duplicate in the 3D plan builder**

In `src/inductor_designer/simulation/plan_builder.py`, delete the whole `_polarity` function (lines 53-60), add `winding_polarity` to the existing `from inductor_designer.simulation.maxwell_plan import (...)` block, and change line 126:

```python
        polarity = winding_polarity(definition, effective.current_direction)
```

Remove now-unused imports (`CurrentDirection`, `WindingDirection`) only if nothing else in the file uses them.

- [ ] **Step 6: Delete the duplicates in the 2D plan builder**

In `src/inductor_designer/simulation/plan_builder2d.py`, delete `_base_polarity` (lines 47-54) and `_invert` (lines 57-58), add `invert_polarity` and `winding_polarity` to the existing `from inductor_designer.simulation.maxwell_plan import (...)` block, and change lines 101 and 108-110:

```python
        base_polarity = winding_polarity(definition, effective.current_direction)
```

```python
                polarity=(
                    base_polarity
                    if conductor.polarity > 0
                    else invert_polarity(base_polarity)
                ),
```

Remove now-unused imports only if nothing else in the file uses them.

- [ ] **Step 7: Run the affected suites to verify nothing regressed**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/simulation -n 8`

Expected: PASS, no failures. The existing plan-builder tests already assert polarity, so they are the regression gate for this move.

- [ ] **Step 8: Check types and lint**

Run: `.venv/Scripts/python.exe -m mypy src/inductor_designer/simulation`
Expected: `Success: no issues found`.

Run: `.venv/Scripts/python.exe -m ruff check src tests`
Expected: `All checks passed!`

- [ ] **Step 9: Commit**

```bash
git add src/inductor_designer/simulation/maxwell_plan.py src/inductor_designer/simulation/plan_builder.py src/inductor_designer/simulation/plan_builder2d.py tests/unit/simulation/test_winding_polarity.py
git commit -m "refactor(simulation): share one winding polarity rule between both plan builders"
```

---

### Task 2: The pure drawing converter

**Files:**
- Modify: `src/inductor_designer/ui/preview_geometry.py:12`
- Create: `src/inductor_designer/ui/cut_plane_view.py`
- Test: `tests/unit/ui/test_cut_plane_view.py`

**Interfaces:**
- Consumes: `winding_polarity`, `invert_polarity`, `Polarity` from `inductor_designer.simulation.maxwell_plan` (Task 1).
- Produces:
  - `PALETTE: tuple[str, ...]` from `inductor_designer.ui.preview_geometry` (the renamed `_PALETTE`).
  - `CutPlaneCircle(x_mm, y_mm, radius_mm, color, into_plane)` and `CutPlaneDrawing(r_inner_mm, r_outer_mm, depth_mm, extent_mm, circles, note)` frozen dataclasses.
  - `build_cut_plane_drawing(model: GeometryModel, project: InductorProject) -> CutPlaneDrawing`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/ui/test_cut_plane_view.py`:

```python
"""No Qt import: the converter is testable without a QGuiApplication."""

from __future__ import annotations

import math
from dataclasses import replace

from inductor_designer.application.services.geometry_model import build_geometry_model
from inductor_designer.domain.winding import CurrentDirection, WindingDirection
from inductor_designer.ui.cut_plane_view import build_cut_plane_drawing
from inductor_designer.ui.preview_geometry import PALETTE
from tests.unit.application.test_geometry_model import CATALOG
from tests.unit.domain.test_project import make_project


def test_every_planar_conductor_becomes_one_circle_in_millimetres() -> None:
    project = make_project()
    model = build_geometry_model(project, CATALOG)

    drawing = build_cut_plane_drawing(model, project)

    planar_conductors = [
        conductor
        for winding in model.planar.windings
        for conductor in winding.conductors
    ]
    assert len(drawing.circles) == len(planar_conductors)
    assert drawing.r_inner_mm == model.planar.r_inner_m * 1000.0
    assert drawing.r_outer_mm == model.planar.r_outer_m * 1000.0
    assert drawing.depth_mm == model.planar.depth_m * 1000.0

    by_position = {
        (round(c.x_mm, 6), round(c.y_mm, 6)): c for c in drawing.circles
    }
    for conductor in planar_conductors:
        key = (round(conductor.x_m * 1000.0, 6), round(conductor.y_m * 1000.0, 6))
        assert key in by_position
        assert by_position[key].radius_mm == conductor.radius_m * 1000.0


def test_reversing_the_current_swaps_every_glyph() -> None:
    project = make_project()
    model = build_geometry_model(project, CATALOG)
    forward = build_cut_plane_drawing(model, project)

    reversed_points = tuple(
        replace(point, current_direction=CurrentDirection.REVERSE)
        for point in project.operating_point.windings
    )
    reversed_project = replace(
        project,
        operating_point=replace(project.operating_point, windings=reversed_points),
    )
    reversed_drawing = build_cut_plane_drawing(model, reversed_project)

    assert [c.into_plane for c in reversed_drawing.circles] == [
        not c.into_plane for c in forward.circles
    ]


def test_the_two_legs_of_a_turn_carry_opposite_glyphs() -> None:
    project = make_project()
    model = build_geometry_model(project, CATALOG)

    drawing = build_cut_plane_drawing(model, project)

    inner = [c for c in drawing.circles if math.hypot(c.x_mm, c.y_mm) < drawing.r_inner_mm]
    outer = [c for c in drawing.circles if math.hypot(c.x_mm, c.y_mm) > drawing.r_outer_mm]
    assert inner and outer
    assert len({c.into_plane for c in inner}) == 1
    assert len({c.into_plane for c in outer}) == 1
    assert inner[0].into_plane is not outer[0].into_plane


def test_winding_colour_matches_the_three_d_preview_order() -> None:
    project = make_project()
    model = build_geometry_model(project, CATALOG)

    drawing = build_cut_plane_drawing(model, project)

    first_id = sorted(w.winding_id for w in model.planar.windings)[0]
    first_circles = [
        c
        for c in drawing.circles
        if c.color == PALETTE[0]
    ]
    assert first_circles
    expected = len(
        next(w for w in model.planar.windings if w.winding_id == first_id).conductors
    )
    assert len(first_circles) == expected


def test_a_winding_wound_the_other_way_flips_its_own_glyphs() -> None:
    project = make_project()
    model = build_geometry_model(project, CATALOG)
    original = build_cut_plane_drawing(model, project)

    flipped_windings = tuple(
        replace(winding, winding_direction=WindingDirection.CLOCKWISE)
        if winding.winding_direction is WindingDirection.COUNTERCLOCKWISE
        else replace(winding, winding_direction=WindingDirection.COUNTERCLOCKWISE)
        for winding in project.design.windings
    )
    flipped = replace(
        project, design=replace(project.design, windings=flipped_windings)
    )

    flipped_drawing = build_cut_plane_drawing(model, flipped)

    assert [c.into_plane for c in flipped_drawing.circles] == [
        not c.into_plane for c in original.circles
    ]


def test_extent_covers_the_outermost_conductor_edge() -> None:
    project = make_project()
    model = build_geometry_model(project, CATALOG)

    drawing = build_cut_plane_drawing(model, project)

    furthest = max(
        math.hypot(c.x_mm, c.y_mm) + c.radius_mm for c in drawing.circles
    )
    assert drawing.extent_mm >= furthest
    assert drawing.extent_mm >= drawing.r_outer_mm


def test_a_design_without_conductors_still_draws_the_annulus() -> None:
    project = make_project()
    model = build_geometry_model(project, CATALOG)
    empty_model = replace(
        model, planar=replace(model.planar, windings=()), packings=()
    )

    drawing = build_cut_plane_drawing(empty_model, project)

    assert drawing.circles == ()
    assert drawing.r_outer_mm == model.planar.r_outer_m * 1000.0
    assert drawing.extent_mm == drawing.r_outer_mm
    assert "no conductors" in drawing.note


def test_the_note_states_where_the_depth_comes_from() -> None:
    project = make_project()
    model = build_geometry_model(project, CATALOG)

    drawing = build_cut_plane_drawing(model, project)

    assert "half height" in drawing.note
    assert f"{drawing.depth_mm:.2f}" in drawing.note
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/ui/test_cut_plane_view.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'inductor_designer.ui.cut_plane_view'`.

- [ ] **Step 3: Publish the palette**

In `src/inductor_designer/ui/preview_geometry.py`, rename the module constant on line 12 and its single use on line 76:

```python
PALETTE = ("#e07a5f", "#3d9970", "#3f88c5", "#f2bb05", "#9656a1", "#2a9d8f")
```

```python
        entries.append(PreviewEntry(MeshGeometry(mesh), PALETTE[i % len(PALETTE)], 1.0))
```

- [ ] **Step 4: Write the converter**

Create `src/inductor_designer/ui/cut_plane_view.py`:

```python
"""Millimetre drawing data for the 2D cut plane preview.

Pure and Qt-free. It reads the same `PlanarModel` that `build_maxwell2d_plan`
iterates, so the drawing the user checks is the model that reaches FEMM and
Maxwell 2D.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from inductor_designer.application.services.geometry_model import GeometryModel
from inductor_designer.domain.project import InductorProject
from inductor_designer.simulation.maxwell_plan import (
    Polarity,
    invert_polarity,
    winding_polarity,
)
from inductor_designer.ui.preview_geometry import PALETTE

_MM_PER_M = 1000.0

_NO_CONDUCTORS = "This design has no conductors, so only the core annulus is drawn."


@dataclass(frozen=True, slots=True)
class CutPlaneCircle:
    x_mm: float
    y_mm: float
    radius_mm: float
    color: str
    into_plane: bool


@dataclass(frozen=True, slots=True)
class CutPlaneDrawing:
    r_inner_mm: float
    r_outer_mm: float
    depth_mm: float
    extent_mm: float
    circles: tuple[CutPlaneCircle, ...]
    note: str


def build_cut_plane_drawing(
    model: GeometryModel,
    project: InductorProject,
) -> CutPlaneDrawing:
    planar = model.planar
    definitions = {
        winding.winding_id: winding for winding in project.design.windings
    }
    directions = {
        point.winding_id: point.current_direction
        for point in project.operating_point.windings
    }

    circles: list[CutPlaneCircle] = []
    # Sorted by winding id so a winding keeps the colour `build_preview_entries`
    # gives it in the 3D view, which sorts the same way.
    ordered = sorted(planar.windings, key=lambda winding: winding.winding_id)
    for index, winding in enumerate(ordered):
        color = PALETTE[index % len(PALETTE)]
        base = winding_polarity(
            definitions[winding.winding_id], directions[winding.winding_id]
        )
        for conductor in winding.conductors:
            polarity = base if conductor.polarity > 0 else invert_polarity(base)
            circles.append(
                CutPlaneCircle(
                    x_mm=conductor.x_m * _MM_PER_M,
                    y_mm=conductor.y_m * _MM_PER_M,
                    radius_mm=conductor.radius_m * _MM_PER_M,
                    color=color,
                    into_plane=polarity is Polarity.NEGATIVE,
                )
            )

    r_outer_mm = planar.r_outer_m * _MM_PER_M
    depth_mm = planar.depth_m * _MM_PER_M
    extent_mm = max(
        [r_outer_mm]
        + [math.hypot(circle.x_mm, circle.y_mm) + circle.radius_mm for circle in circles]
    )
    note = (
        _NO_CONDUCTORS
        if not circles
        else f"Model depth {depth_mm:.2f} mm, twice the core half height."
    )
    return CutPlaneDrawing(
        r_inner_mm=planar.r_inner_m * _MM_PER_M,
        r_outer_mm=r_outer_mm,
        depth_mm=depth_mm,
        extent_mm=extent_mm,
        circles=tuple(circles),
        note=note,
    )
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/ui/test_cut_plane_view.py -v`

Expected: PASS, 8 tests.

If `test_winding_colour_matches_the_three_d_preview_order` fails because the fixture project has one winding, that is still a valid assertion; do not weaken it.

- [ ] **Step 6: Confirm nothing else used the old palette name**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/ui tests/ui -n 8 -m "not ui"`

Expected: PASS. Then run: `.venv/Scripts/python.exe -m ruff check src tests` and `.venv/Scripts/python.exe -m mypy src/inductor_designer/ui`

Expected: `All checks passed!` and `Success: no issues found`.

- [ ] **Step 7: Commit**

```bash
git add src/inductor_designer/ui/cut_plane_view.py src/inductor_designer/ui/preview_geometry.py tests/unit/ui/test_cut_plane_view.py
git commit -m "feat(ui): convert the planar model into 2D cut plane drawing data"
```

---

### Task 3: Carry the drawing on the controller

**Files:**
- Modify: `src/inductor_designer/ui/guided_studio_controller.py`
- Test: `tests/ui/test_guided_studio_controller.py`

**Interfaces:**
- Consumes: `build_cut_plane_drawing` and `CutPlaneDrawing` from `inductor_designer.ui.cut_plane_view` (Task 2).
- Produces: `GuidedStudioController.cutPlaneDrawing`, a `dict` property notified by the existing `previewEntriesChanged` signal, shaped `{"r_inner_mm": float, "r_outer_mm": float, "depth_mm": float, "extent_mm": float, "circles": [{"x_mm": float, "y_mm": float, "radius_mm": float, "color": str, "into_plane": bool}], "note": str}`.

- [ ] **Step 1: Write the failing test**

Append to `tests/ui/test_guided_studio_controller.py`. Match the existing imports and controller-construction helper already in that file rather than inventing a new one; the assertions below are what matters.

```python
def test_cut_plane_drawing_follows_an_accepted_winding_edit() -> None:
    session = ProjectSession(make_project())
    controller = GuidedStudioController(session, CATALOG)
    winding_id = controller.windings[0]["windingId"]
    before = len(controller.cutPlaneDrawing["circles"])

    assert controller.setWindingField(winding_id, "turns", "3") is True

    after = controller.cutPlaneDrawing["circles"]
    assert len(after) != before
    assert all("into_plane" in circle for circle in after)
    assert controller.cutPlaneDrawing["depth_mm"] > 0.0


def test_a_rejected_edit_keeps_the_previous_cut_plane_drawing() -> None:
    session = ProjectSession(make_project())
    controller = GuidedStudioController(session, CATALOG)
    winding_id = controller.windings[0]["windingId"]
    before = controller.cutPlaneDrawing

    assert controller.setWindingField(winding_id, "turns", "not a number") is False

    assert controller.cutPlaneDrawing == before
    assert "Unable to apply change" in controller.statusMessage


def test_the_drawing_and_the_three_d_entries_describe_the_same_windings() -> None:
    session = ProjectSession(make_project())
    controller = GuidedStudioController(session, CATALOG)

    colors = {circle["color"] for circle in controller.cutPlaneDrawing["circles"]}
    entry_colors = {entry.color for entry in controller.previewEntries[1:]}

    assert colors == entry_colors
```

The `previewEntries[1:]` slice skips the core entry, which `build_preview_entries` always puts first.

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/ui/test_guided_studio_controller.py -v -m ui`

Expected: FAIL with `AttributeError: 'GuidedStudioController' object has no attribute 'cutPlaneDrawing'`.

- [ ] **Step 3: Introduce the combined preview state**

In `src/inductor_designer/ui/guided_studio_controller.py`, add the imports:

```python
from dataclasses import dataclass, replace
```

(the module already imports `replace`; extend that line rather than adding a second import)

```python
from inductor_designer.ui.cut_plane_view import CutPlaneDrawing, build_cut_plane_drawing
```

Add, above the controller class:

```python
@dataclass(frozen=True, slots=True)
class _PreviewState:
    """The 3D entries and the 2D drawing, always rebuilt together.

    They come from one `build_geometry_model` call, so the two views can never
    show different geometry.
    """

    entries: list[PreviewEntry]
    drawing: CutPlaneDrawing
```

- [ ] **Step 4: Rebuild both in `_build_preview`**

Replace the method at line 76:

```python
    def _build_preview(self, project: InductorProject) -> _PreviewState:
        model = build_geometry_model(project, self._catalog)
        return _PreviewState(
            entries=build_preview_entries(model),
            drawing=build_cut_plane_drawing(model, project),
        )
```

- [ ] **Step 5: Rename the stored field and add the property**

In `__init__`, replace the `self._preview_entries = self._build_preview(project)` assignment with:

```python
        self._preview = self._build_preview(project)
```

Replace the `previewEntries` getter and add the new property beside it:

```python
    def _get_preview_entries(self) -> list[PreviewEntry]:
        return self._preview.entries

    previewEntries = Property(list, _get_preview_entries, notify=previewEntriesChanged)

    def _get_cut_plane_drawing(self) -> dict[str, object]:
        return asdict(self._preview.drawing)

    cutPlaneDrawing = Property(
        dict, _get_cut_plane_drawing, notify=previewEntriesChanged
    )
```

Add `asdict` to the dataclasses import line.

- [ ] **Step 6: Update the five assignment sites**

Every existing `self._preview_entries = preview_entries` becomes `self._preview = preview_state`, and every local `preview_entries = self._build_preview(...)` becomes `preview_state = self._build_preview(...)`. The sites are in `setOperatingPointField`, `setWindingField`, `addWinding`, `removeWinding`, and `refresh`. In `refresh` the guarded call becomes:

```python
        with contextlib.suppress(GeometryModelError):
            self._preview = self._build_preview(project)
```

Do not add a new signal. `previewEntriesChanged` is already emitted at each of these sites and now notifies both properties.

- [ ] **Step 7: Run the tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/ui/test_guided_studio_controller.py -v -m ui`

Expected: PASS, including the three new tests and every pre-existing test in the file.

- [ ] **Step 8: Check types and lint**

Run: `.venv/Scripts/python.exe -m mypy src/inductor_designer/ui`
Expected: `Success: no issues found`.

Run: `.venv/Scripts/python.exe -m ruff check src tests`
Expected: `All checks passed!`

- [ ] **Step 9: Commit**

```bash
git add src/inductor_designer/ui/guided_studio_controller.py tests/ui/test_guided_studio_controller.py
git commit -m "feat(ui): expose the 2D cut plane drawing beside the 3D preview"
```

---

### Task 4: Draw it

**Files:**
- Create: `src/inductor_designer/ui/qml/CutPlaneView.qml`
- Modify: `src/inductor_designer/ui/qml/PreviewPane.qml`
- Test: `tests/ui/test_cut_plane_qml.py`

**Interfaces:**
- Consumes: `guidedStudioController.cutPlaneDrawing` (Task 3).
- Produces: QML objects reachable by `objectName` — `cutPlaneView`, `cutPlaneCanvas`, `cutPlaneNote`, `previewMode3DButton`, `previewMode2DButton`, `showCutPlaneCheck`, `cutPlaneModel`.

- [ ] **Step 1: Write the failing test**

Create `tests/ui/test_cut_plane_qml.py`:

```python
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QSG_RHI_BACKEND", "software")

pytest.importorskip("PySide6")

from PySide6.QtCore import QObject  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

from inductor_designer.ui.guided_studio_controller import (  # noqa: E402
    GuidedStudioController,
)
from inductor_designer.ui.main import create_engine  # noqa: E402
from inductor_designer.ui.project_session import ProjectSession  # noqa: E402
from tests.unit.application.test_geometry_model import CATALOG  # noqa: E402
from tests.unit.domain.test_project import make_project  # noqa: E402

pytestmark = pytest.mark.ui

# The engine owns the root window; a collected engine takes every findChild
# target with it. See tests/ui/test_winding_panel_qml.py for the full note.
_ENGINES: list[object] = []
_CONTROLLERS: list[object] = []


def open_preview() -> tuple[QGuiApplication, QObject]:
    app = QGuiApplication.instance() or QGuiApplication([])
    session = ProjectSession(make_project())
    controller = GuidedStudioController(session, CATALOG)
    engine = create_engine(guided_studio_controller=controller)
    _ENGINES.append(engine)
    _CONTROLLERS.append(controller)
    app.processEvents()
    return app, engine.rootObjects()[0]


def test_the_preview_pane_exposes_the_toggle_the_checkbox_and_the_canvas() -> None:
    _app, root = open_preview()

    for name in (
        "previewMode3DButton",
        "previewMode2DButton",
        "showCutPlaneCheck",
        "cutPlaneView",
        "cutPlaneCanvas",
        "cutPlaneNote",
        "cutPlaneModel",
    ):
        assert root.findChild(QObject, name) is not None, name


def test_the_two_d_view_is_hidden_until_the_toggle_selects_it() -> None:
    app, root = open_preview()
    view = root.findChild(QObject, "cutPlaneView")

    assert view.property("visible") is False

    root.findChild(QObject, "previewMode2DButton").setProperty("checked", True)
    app.processEvents()

    assert view.property("visible") is True


def test_selecting_two_d_also_shows_the_plane_in_the_three_d_scene() -> None:
    app, root = open_preview()

    root.findChild(QObject, "previewMode2DButton").setProperty("checked", True)
    app.processEvents()

    assert root.findChild(QObject, "showCutPlaneCheck").property("checked") is True
    assert root.findChild(QObject, "cutPlaneModel").property("visible") is True


def test_the_note_reaches_qml_from_the_controller() -> None:
    _app, root = open_preview()

    note = root.findChild(QObject, "cutPlaneNote").property("text")

    assert "Model depth" in note
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/ui/test_cut_plane_qml.py -v -m ui`

Expected: FAIL, `assert ... is not None` for `previewMode3DButton`.

- [ ] **Step 3: Write the canvas**

Create `src/inductor_designer/ui/qml/CutPlaneView.qml`:

```qml
import QtQuick

// The 2D model exactly as FEMM and Maxwell 2D will receive it. Every number
// arrives from `GuidedStudioController.cutPlaneDrawing`; this file only paints.
Item {
    id: root
    objectName: "cutPlaneView"

    property var drawing: ({
        "r_inner_mm": 0.0,
        "r_outer_mm": 0.0,
        "depth_mm": 0.0,
        "extent_mm": 1.0,
        "circles": [],
        "note": ""
    })
    property color background: "#f8f7f4"

    onDrawingChanged: canvas.requestPaint()

    Rectangle {
        anchors.fill: parent
        color: root.background
    }

    Canvas {
        id: canvas
        objectName: "cutPlaneCanvas"
        anchors.fill: parent
        anchors.bottomMargin: 52
        anchors.margins: 20
        renderStrategy: Canvas.Immediate

        onPaint: {
            var ctx = getContext("2d")
            ctx.reset()

            var extent = Math.max(root.drawing.extent_mm, 1e-6)
            var scale = Math.min(width, height) / (2 * extent * 1.06)
            var cx = width / 2
            var cy = height / 2

            function px(mm) { return cx + mm * scale }
            function py(mm) { return cy - mm * scale }

            // Annulus: an outer grey disc with the bore painted back out. QML's
            // Canvas fill is non-zero winding, so a two-arc even-odd path is
            // not available.
            ctx.fillStyle = "#b9b6b0"
            ctx.beginPath()
            ctx.arc(cx, cy, root.drawing.r_outer_mm * scale, 0, 2 * Math.PI)
            ctx.fill()
            ctx.fillStyle = root.background
            ctx.beginPath()
            ctx.arc(cx, cy, root.drawing.r_inner_mm * scale, 0, 2 * Math.PI)
            ctx.fill()

            for (var i = 0; i < root.drawing.circles.length; ++i) {
                var c = root.drawing.circles[i]
                var r = Math.max(c.radius_mm * scale, 1.5)
                var x = px(c.x_mm)
                var y = py(c.y_mm)

                ctx.fillStyle = c.color
                ctx.beginPath()
                ctx.arc(x, y, r, 0, 2 * Math.PI)
                ctx.fill()

                ctx.strokeStyle = "#ffffff"
                ctx.fillStyle = "#ffffff"
                ctx.lineWidth = Math.max(r * 0.28, 1)
                if (c.into_plane) {
                    // Cross: current flows away from the viewer.
                    var d = r * 0.5
                    ctx.beginPath()
                    ctx.moveTo(x - d, y - d)
                    ctx.lineTo(x + d, y + d)
                    ctx.moveTo(x + d, y - d)
                    ctx.lineTo(x - d, y + d)
                    ctx.stroke()
                } else {
                    // Dot: current flows towards the viewer.
                    ctx.beginPath()
                    ctx.arc(x, y, Math.max(r * 0.32, 1), 0, 2 * Math.PI)
                    ctx.fill()
                }
            }

            // Scale bar: the outer radius, drawn under the model.
            var barMm = root.drawing.r_outer_mm
            var barPx = barMm * scale
            var barY = height - 10
            ctx.strokeStyle = "#5b5852"
            ctx.lineWidth = 1
            ctx.beginPath()
            ctx.moveTo(cx - barPx / 2, barY)
            ctx.lineTo(cx + barPx / 2, barY)
            ctx.moveTo(cx - barPx / 2, barY - 4)
            ctx.lineTo(cx - barPx / 2, barY + 4)
            ctx.moveTo(cx + barPx / 2, barY - 4)
            ctx.lineTo(cx + barPx / 2, barY + 4)
            ctx.stroke()
            ctx.fillStyle = "#5b5852"
            ctx.font = "11px sans-serif"
            ctx.textAlign = "center"
            ctx.fillText(barMm.toFixed(2) + " mm", cx, barY - 8)
        }
    }

    Text {
        objectName: "cutPlaneNote"
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.margins: 12
        wrapMode: Text.WordWrap
        color: "#5b5852"
        font.pixelSize: 12
        text: root.drawing.note
    }
}
```

- [ ] **Step 4: Wire the pane**

In `src/inductor_designer/ui/qml/PreviewPane.qml`, add `import QtQuick.Controls` at the top, give the root `Rectangle` an `id: pane`, and add below the existing `previewModel` properties:

```qml
    property bool showTwoD: false
    property var cutPlaneDrawing: guidedStudioController !== null
        ? guidedStudioController.cutPlaneDrawing
        : ({ "r_inner_mm": 0.0, "r_outer_mm": 0.0, "depth_mm": 0.0,
             "extent_mm": 1.0, "circles": [], "note": "" })
```

Add `visible: !pane.showTwoD` to the existing `View3D`, and inside it, after the `Repeater3D`:

```qml
        // The equatorial XY plane the 2D model is cut on. The toroid axis is z,
        // so the built-in rectangle already lies in the right plane. Its native
        // size is 100 units and the scene draws metres scaled by 1000, so the
        // scale factor is the wanted size in millimetres over 100.
        // ponytail: one fixed plane, because XY equatorial is the only
        // reduction the 2D adapters build. It becomes a selector when a core
        // shape arrives whose plane is not obvious.
        Model {
            objectName: "cutPlaneModel"
            visible: showCutPlaneCheck.checked && hasPreviewEntries
            source: "#Rectangle"
            scale: {
                var size = 2.2 * pane.cutPlaneDrawing.r_outer_mm
                return Qt.vector3d(size / 100, size / 100, 1)
            }
            depthDrawMode: Model.NeverDepthDraw
            materials: PrincipledMaterial {
                baseColor: "#3f88c5"
                opacity: 0.18
                alphaMode: PrincipledMaterial.Blend
                cullMode: Material.NoCulling
            }
        }
```

Then add the 2D view and the controls as siblings of the `View3D`:

```qml
    CutPlaneView {
        anchors.fill: parent
        visible: pane.showTwoD
        drawing: pane.cutPlaneDrawing
        background: pane.color
    }

    Row {
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.margins: 10
        spacing: 8

        Button {
            objectName: "previewMode3DButton"
            text: qsTr("3D")
            checkable: true
            checked: !pane.showTwoD
            onClicked: pane.showTwoD = false
        }
        Button {
            objectName: "previewMode2DButton"
            text: qsTr("2D cut")
            checkable: true
            checked: pane.showTwoD
            onClicked: {
                pane.showTwoD = true
                showCutPlaneCheck.checked = true
            }
        }
        CheckBox {
            id: showCutPlaneCheck
            objectName: "showCutPlaneCheck"
            text: qsTr("Show cut plane")
        }
    }
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/ui/test_cut_plane_qml.py -v -m ui`

Expected: PASS, 4 tests.

If `cutPlaneModel` is not found, confirm `CutPlaneView.qml` sits in the same directory as `PreviewPane.qml` and that the directory is on the engine's import path — `create_engine` in `ui/main.py` already adds it for the other pane components, so no new registration should be needed.

- [ ] **Step 6: Run the whole UI suite**

Run: `.venv/Scripts/python.exe -m pytest tests/ui -m ui -n 8`

Expected: PASS. `tests/ui/test_panel_layout_containment.py` and `tests/ui/test_qml_smoke.py` are the ones most likely to notice a broken `PreviewPane.qml`.

- [ ] **Step 7: Run the full suite and the checks**

Run: `.venv/Scripts/python.exe -m pytest -n 8`
Expected: PASS, no failures.

Run: `.venv/Scripts/python.exe -m ruff check src tests`
Expected: `All checks passed!`

Run: `.venv/Scripts/python.exe -m mypy src`
Expected: `Success: no issues found`.

Run: `.venv/Scripts/python.exe tools/check_architecture.py`
Expected: no violations. `ui` importing `simulation` is inward and allowed.

- [ ] **Step 8: Commit**

```bash
git add src/inductor_designer/ui/qml/CutPlaneView.qml src/inductor_designer/ui/qml/PreviewPane.qml tests/ui/test_cut_plane_qml.py
git commit -m "feat(ui): draw the 2D cut plane and show its plane in the 3D preview"
```

---

## Manual check before calling it done

Offscreen tests prove the objects exist and the numbers arrive. They do not prove the drawing is legible. Render the pane once and look at it.

Use a near-full-circumference winding, not the default sector. A real choke is wound over most of the core, and that is the only case where the drawing fills the canvas and the translucent plane meets conductors all the way round -- the default 90-degree sector shows neither.

- Open the application, go to the Windings step, and set the winding to a 355-degree sector with 40 turns.
- Switch the preview to `2D cut`.
- Confirm the annulus, the inner and outer conductor rings, and that inner and outer legs carry opposite glyphs.
- Confirm the scale bar and its millimetre label sit clear of the bottom conductor glyphs, and that the bar spans the outer diameter.
- Switch back to `3D` and confirm the translucent plane sits at the core's mid height without hiding the core or the conductors it now crosses.
- Reverse the winding's current direction on the Windings step and confirm every glyph in that winding swaps.
