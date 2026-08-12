# 2D Cut Plane Preview and Override Design

- Status: Approved in collaborative design review
- Date: 2026-08-12
- Product surface: Standalone Windows application
- Supported geometry: Toroidal cores
- Related design:
  [2026-07-26 Preliminary calculations and Guided flow](2026-07-26-preliminary-calculations-and-guided-flow-design.md)

## 1. Purpose

Let the user verify, before generating anything, which plane the application
reduces the choke to for a 2D run. The application draws that plane in the 3D
preview, draws the resulting 2D model exactly as it will be exported, and lets
the user select a different plane when the automatic choice is wrong.

Today no cut-plane decision exists. `build_planar_model` in
`geometry/planar.py` always builds the equatorial XY model, and both 2D
backends consume it directly. This design makes the plane an explicit,
inspectable, overridable value without changing the geometry that a toroid
already produces.

## 2. Problem statement

The current 2D reduction is correct for a toroid: flux runs azimuthally and
lies in the XY plane, conductor legs run out of plane, and the out-of-plane
depth is the core height. Nothing is wrong today.

Two gaps remain:

1. The user cannot see the 2D model before it reaches FEMM or Maxwell 2D, so a
   wrong reduction would surface only after a run.
2. The plane is implicit. When the application supports core shapes other than
   the toroid, the correct plane stops being a single obvious answer, and there
   is no place to record the decision, explain it, or correct it.

This design closes both gaps and creates the extension point for the second,
without building support for core shapes that do not exist yet.

## 3. Confirmed product decisions

- The cut plane is an explicit named value carried by the geometry model.
- One resolution feeds both the preview and the export. The drawing the user
  checks is the drawing that ships.
- A toroid offers two candidates: the XY equatorial plane, which generates, and
  the r-z azimuthal plane, which does not.
- The r-z candidate is listed with the reason it cannot generate. It is not
  hidden, and it is not silently replaced by the XY plane.
- Selecting a candidate that cannot generate is allowed and persists. Generate
  refuses with that candidate's own reason.
- The 2D drawing renders in the existing preview pane behind a `3D / 2D cut`
  toggle. The toggle is view state and is never saved to the project.
- The override is stored in the Project document, so a corrected plane survives
  save and reopen.
- Absence of a stored override means automatic selection.

## 4. Architecture

Dependencies keep pointing inward. `geometry` and `domain` gain no imports.
The UI converts; QML receives numbers only.

### 4.1 New module: `geometry/cut_plane.py`

Solver-independent. No Qt, no PyAEDT, no FEMM, no SQLite.

```python
class CutPlaneKind(str, Enum):
    XY_EQUATORIAL = "xy-equatorial"
    RZ_AZIMUTHAL = "rz-azimuthal"


@dataclass(frozen=True, slots=True)
class CutPlaneCandidate:
    kind: CutPlaneKind
    azimuth_deg: float   # 0.0 for XY; the section angle for r-z
    generates: bool      # a 2D adapter can export this plane today
    reason: str          # why it was chosen, or why it cannot generate


@dataclass(frozen=True, slots=True)
class CutPlane:
    selected: CutPlaneKind
    azimuth_deg: float
    overridden: bool     # True when the project overrode the automatic pick
    candidates: tuple[CutPlaneCandidate, ...]


def propose_cut_planes(
    core: FinishedCore,
) -> tuple[CutPlaneCandidate, ...]: ...


def resolve_cut_plane(
    candidates: Sequence[CutPlaneCandidate],
    override: CutPlaneKind | None,
) -> CutPlane: ...
```

`CutPlaneKind` subclasses `(str, Enum)` rather than `StrEnum`, matching
`MeshIntent` and `RequestedOutput` and the project's Python 3.10 floor.

`propose_cut_planes` takes only the core. Candidate planes for a toroid do not
depend on the windings, and the parameter is added when a core shape needs it.

`propose_cut_planes` returns a deterministic, ranked tuple. For a toroid it
returns the XY candidate with `generates=True` and the r-z candidate with
`generates=False`, whose reason names the missing axisymmetric mode in both 2D
adapters.

`resolve_cut_plane` picks the first generating candidate when the override is
`None`, and otherwise honors the override and sets `overridden=True`. An
override naming a kind that the candidate list does not contain raises
`ValueError`.

A future core shape changes `propose_cut_planes` and nothing else.

### 4.2 Geometry model

`GeometryModel` gains `cut_plane: CutPlane`, resolved once in
`application/services/geometry_model.py` where the model is already assembled.
The UI preview and the 2D plan builder both read that one value. Architecture
rule 3 already requires previews and solver exports to originate from the same
solver-independent geometry model; the cut plane joins that guarantee.

### 4.3 Domain and persistence

`SimulationRecipe` gains `cut_plane_override: CutPlaneKind | None = None`. The
recipe already holds backend-independent intent, and this field states how to
reduce the design to 2D regardless of which 2D backend a Run Request selects.

The Project document gains an optional `cutPlaneOverride` key under
`simulationRecipe` in `schemas/project/v5.schema.json`, constrained to the
`CutPlaneKind` values. It is not added to `required`, so existing v5 documents
keep validating and the schema version stays 5. An absent key means automatic
selection. An unrecognized value fails schema validation; the repository never
coerces it to automatic.

### 4.4 Simulation and adapters

`build_maxwell2d_plan` accepts the resolved `CutPlane`, records it on
`Maxwell2dDesignPlan`, and reports it in the Run Manifest alongside the existing
2D approximation note.

When the selected candidate has `generates=False`, the builder raises
`PlanBuildError` carrying that candidate's own reason. No fallback to the XY
plane is invented, consistent with architecture rule 8.

`femm_problem_from_plan` reads the plan's cut plane and refuses any plane other
than XY equatorial with the same explicit reason.

No adapter gains an axisymmetric mode in this design.

## 5. User interface

### 5.1 What the 2D drawing shows

The drawing is the exported model at 1:1, derived from the same `PlanarModel`
that `build_maxwell2d_plan` iterates:

- The core annulus, gray fill, from `r_inner` to `r_outer`.
- Two circles per winding turn station at the bare conductor radius: the inner
  leg at `r_inner - radial_build`, the outer leg at `r_outer + radial_build`,
  in the winding's palette color.
- Polarity by the standard convention: a dot for current out of the plane, a
  cross for current into the plane.
- An annotation line giving the model depth in millimetres, its derivation
  (`2 x half_height`), the selected plane, and whether it was automatic.
- Millimetre scales on both axes.

The drawing introduces no physics. It renders values the geometry model
already produces.

### 5.2 Components

- `ui/cut_plane_view.py` converts `GeometryModel` into plain dictionaries for
  QML, mirroring `ui/preview_geometry.py`.
- `ui/cut_plane_controller.py` exposes `drawing`, `candidates`,
  `selectedPlane`, `overridden`, and `blockedReason`, plus a `setCutPlane`
  slot that writes through `ProjectSession` like the existing controllers.
- `ui/qml/CutPlaneView.qml` paints the drawing with `Canvas`, following the
  pattern already proven in `MaterialCurveEditor.qml`.

### 5.3 Placement

`PreviewPane.qml` gains a `3D / 2D cut` toggle in a corner. The 2D canvas fills
the same pane slot when selected, so the shell layout is unchanged.

The plane appears in the 3D view as one built-in `#Rectangle` model at the
origin, sized to roughly 2.2 times `r_outer`, semi-transparent, double-sided,
with depth writing disabled so it never occludes the core. The toroid axis is
z, so the XY equatorial plane needs no rotation; the r-z candidate is the same
rectangle rotated to the vertical plane at its azimuth. A `Show cut plane`
checkbox in the preview pane controls the rectangle's visibility. The checkbox
is checked automatically when the toggle moves to 2D, and the user may then
uncheck it or check it while the toggle is on 3D.

The override control sits in `SimulationPanel.qml` next to the backend choice.
It lists every candidate with its reason. Choosing a candidate that cannot
generate persists the choice and displays the block reason; Generate then
refuses with that same text.

## 6. Error handling

- An unrecognized stored override fails schema validation and the document is
  rejected, like any other invalid document.
- A selected plane that cannot generate produces a `PlanBuildError` carrying
  the candidate's reason. The Simulation panel shows that text and Generate
  refuses. The selection is not discarded.
- A geometry error during an edit leaves the last valid drawing in place, using
  the same guard `GuidedStudioController.refresh` already applies. Architecture
  rule 12 continues to hold.
- A design with no windings renders the annulus with an explicit note that the
  model has no conductors, rather than a blank canvas.

## 7. Testing

Tests are written before the implementation, as `AGENTS.md` requires.

- `geometry/cut_plane`: a toroid yields a generating XY candidate and a
  non-generating r-z candidate with a reason; `resolve_cut_plane` honors an
  override, picks the single generating candidate when the override is `None`,
  and rejects an override that is not among the candidates; output is
  deterministic.
- Domain: `SimulationRecipe` accepts `None` and both kinds.
- Persistence: round trip with and without the key; a v5 document lacking the
  key loads as automatic; an invalid value is rejected; emitted JSON stays
  deterministic.
- `plan_builder2d`: the plan and the Run Manifest carry the cut plane; a
  non-generating selection raises `PlanBuildError` naming the reason; existing
  2D plan tests continue to pass.
- FEMM: `femm_problem_from_plan` refuses a non-XY plane with an explicit
  reason.
- `ui/cut_plane_view`: the drawing's circles match the `PlanarModel` one for
  one in count, coordinates, and polarity-to-glyph mapping. This test is what
  prevents the preview from drifting away from the export.
- Controller: `setCutPlane` persists the choice and marks the session dirty;
  the failure path keeps the last valid drawing and sets the status message.
- QML: the toggle and the canvas resolve by `objectName`, matching the existing
  panel tests.

## 8. Verification

```text
pytest -n 8
ruff check
mypy
```

## 9. Out of scope

- Axisymmetric r-z generation in Maxwell 2D or FEMM.
- Core shapes other than the toroid.
- Any change to the physics of the existing XY reduction. The plane a toroid
  resolves to, and the model it produces, are identical before and after this
  design.
