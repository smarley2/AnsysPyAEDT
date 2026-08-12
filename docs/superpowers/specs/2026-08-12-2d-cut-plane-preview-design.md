# 2D Cut Plane Preview Design

- Status: Approved in collaborative design review
- Date: 2026-08-12
- Product surface: Standalone Windows application
- Supported geometry: Toroidal cores
- Related design:
  [2026-07-26 Preliminary calculations and Guided flow](2026-07-26-preliminary-calculations-and-guided-flow-design.md)

## 1. Purpose

Show the user the 2D model the application will hand to FEMM or Maxwell 2D,
and show the plane it was cut on, before any run starts.

Solver work is background and non-graphical by default (ADR 0007). The user
never sees the FEMM or Maxwell 2D window, so today the first look at the 2D
model comes after a run, in a generated file. This design puts that look in
the application, where a wrong reduction is caught before it costs a solve.

Read-only. The application draws what it will build. It does not offer a way to
change the plane.

## 2. Problem statement

The current 2D reduction is correct for a toroid: flux runs azimuthally and
lies in the XY plane, conductor legs run out of plane, and the out-of-plane
depth is the core height. Nothing about it needs fixing.

What is missing is visibility. `build_planar_model` in `geometry/planar.py`
produces the model, `build_maxwell2d_plan` consumes it, and FEMM translates it,
all without ever showing the user a picture. A headless run therefore gives no
opportunity to notice that the conductors, the polarities, or the depth are not
what the design intended.

## 3. Confirmed product decisions

- The 2D preview is read-only. There is no plane selector and no override.
- The preview renders `GeometryModel.planar`, the same object
  `build_maxwell2d_plan` iterates. It is not a second construction of the
  geometry.
- The preview is available on every Guided Studio step, not only Simulation. A
  wrong reduction is usually a winding problem, and the user is looking at
  windings when they cause it.
- The cut plane is drawn in the 3D preview as a translucent rectangle, so the
  relationship between the solid and the flat drawing is visible.
- The 3D and 2D views share the existing preview pane through a toggle. The
  toggle and the plane checkbox are view state and are never saved to the
  project.
- The XY equatorial plane is a constant of this design. When the application
  gains a core shape whose correct 2D plane is not obvious, that constant
  becomes a selection, and this design is superseded rather than extended.

## 4. Architecture

No change to `domain`, `geometry`, `materials`, the adapters, or the Project
schema. The feature is a new read path in `ui` over data the application
already computes.

`simulation` changes only by losing a duplicate. The rule that turns a winding
direction and a current direction into a polarity is written twice today,
identically, as `_polarity` in `plan_builder.py` and `_base_polarity` in
`plan_builder2d.py`. The preview needs the same rule, and copying it a third
time into `ui` would put a physical convention in the UI layer. One
`winding_polarity`, with its `invert_polarity` companion, moves to
`simulation/maxwell_plan.py` beside the `Polarity` it returns, and both plan
builders call it. Net effect on `simulation`: one function instead of two, and
the preview shares it.

`GeometryModel` already carries `planar: PlanarModel`, built once in
`application/services/geometry_model.py` and consumed by the 2D plan builder.
The preview reads that field. Architecture rule 3 — previews and solver exports
originate from the same solver-independent geometry model — is satisfied by
construction, not by agreement.

### 4.1 New module: `ui/cut_plane_view.py`

A pure converter from `GeometryModel` to plain data for QML, mirroring the role
of `ui/preview_geometry.py`. It performs no geometry construction and contains
no physics: it reads `PlanarModel`, converts metres to millimetres, and assigns
each conductor a glyph and a colour.

```python
@dataclass(frozen=True, slots=True)
class CutPlaneCircle:
    x_mm: float
    y_mm: float
    radius_mm: float
    color: str
    into_plane: bool   # True draws a cross, False draws a dot


@dataclass(frozen=True, slots=True)
class CutPlaneDrawing:
    r_inner_mm: float
    r_outer_mm: float
    depth_mm: float
    extent_mm: float           # half-width of the drawn area, for the canvas
    circles: tuple[CutPlaneCircle, ...]
    note: str                  # depth derivation, or why the drawing is empty


def build_cut_plane_drawing(
    model: GeometryModel,
    project: InductorProject,
) -> CutPlaneDrawing: ...
```

The project is a parameter because polarity depends on
`WindingDefinition.winding_direction` and
`WindingOperatingPoint.current_direction`, neither of which `GeometryModel`
carries. `current_direction` passes through `EffectiveWindingInput` unchanged,
so the value the preview reads is the value the exporter uses.

Winding colours come from the palette `ui/preview_geometry.py` already uses,
indexed in the same winding-id order, so a winding is the same colour in both
views.

### 4.2 Controller

`GuidedStudioController` already owns the preview, rebuilds it after every
accepted edit, and keeps the last valid one when an edit fails. The 2D drawing
is part of the preview and follows it rather than duplicating those five
rebuild sites in a second controller.

`_build_preview` returns a small frozen `PreviewState` holding both the 3D
entries and the drawing. Each existing assignment site stores that one value.
A `cutPlaneDrawing` property exposes the drawing, notified by the existing
`previewEntriesChanged` signal, so no new emit sites appear.

### 4.3 QML

`ui/qml/CutPlaneView.qml` paints the drawing with `Canvas`, following the
pattern already proven in `MaterialCurveEditor.qml`. It receives numbers and
draws them; it computes nothing.

`PreviewPane.qml` gains a `3D / 2D cut` toggle and a `Show cut plane` checkbox.
The 2D canvas fills the same pane slot when selected, so the shell layout is
unchanged.

## 5. What the drawing shows

The exported model at 1:1, viewed along the toroid axis:

- The core annulus, grey fill, from `r_inner` to `r_outer`.
- Two circles per winding turn station at the bare conductor radius: the inner
  leg at `r_inner - radial_build`, the outer leg at `r_outer + radial_build`,
  in the winding's palette colour.
- Polarity by the standard convention: a dot for current out of the plane, a
  cross for current into the plane. This is what the user scans to catch a bad
  reduction. The glyph follows the winding direction and the current direction
  through the shared `winding_polarity`, so a winding wound the wrong way is
  visible here.
- An annotation line giving the model depth in millimetres and its derivation
  (`2 x half_height`).
- A millimetre scale bar spanning the outer diameter, labelled with its length.
  A labelled bar carries the size information a tick-labelled pair of axes
  would, for much less canvas code.

The plane in the 3D view is one built-in `#Rectangle` model at the origin,
sized to roughly 2.2 times `r_outer`, semi-transparent, double-sided, with
depth writing disabled so it never occludes the core. The toroid axis is z, so
the XY equatorial plane needs no rotation.

## 6. Error handling

- A geometry error during an edit leaves the last valid drawing in place,
  through the same guard `GuidedStudioController.refresh` already applies.
  Architecture rule 12 continues to hold: a failed edit never blanks the
  preview.
- A design with no windings renders the annulus and states in `note` that the
  model has no conductors, rather than showing an empty canvas.
- The converter raises nothing. Any failure to build the geometry model is
  already reported by the existing preview path before the drawing is reached.

## 7. Testing

Tests are written before the implementation, as `AGENTS.md` requires.

- `simulation/maxwell_plan`: `winding_polarity` returns the expected value for
  all four winding-direction and current-direction pairs, and `invert_polarity`
  swaps both values. The existing plan-builder tests are the regression gate
  for the two deleted duplicates.
- `ui/cut_plane_view`: the drawing's circles match `GeometryModel.planar` one
  for one in count, coordinates, radius, and polarity-to-glyph mapping; metres
  convert to millimetres exactly; a winding's colour matches the colour
  `build_preview_entries` gives it. This is the test that keeps the preview
  from drifting away from the export.
- Empty design: no windings yields an annulus, no circles, and an explanatory
  note.
- Controller: `cutPlaneDrawing` updates after an accepted winding edit; a
  rejected edit leaves the previous drawing in place and sets the status
  message.
- QML: the toggle, the checkbox, and the canvas resolve by `objectName`,
  matching the existing panel tests.

## 8. Verification

```text
pytest -n 8
ruff check
mypy
```

## 9. Out of scope

- Any way to change the cut plane. Considered and dropped: on a toroid the XY
  equatorial plane is the only reduction the 2D adapters build, so a selector
  could only ever refuse.
- Axisymmetric r-z generation in Maxwell 2D or FEMM.
- Core shapes other than the toroid.
- Any change to the 2D model itself. The geometry a toroid produces is
  identical before and after this design.
