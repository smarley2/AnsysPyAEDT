# Blank project on launch

A shortcut launch of the installed application cannot load or create a
project, so every screen is empty and nothing can be selected. This closes
that, by making "no `--project`" mean "a blank project with no document path"
rather than "no project object".

## The defect

`main()` builds a `ProjectSession` only inside `if project is not None`
(`src/inductor_designer/ui/main.py`), and `project` comes only from
`--project`. The installer's Start Menu and desktop shortcuts pass no
arguments (`packaging/installer.iss`, `[Icons]`), so a normal launch reaches
QML with `projectSession = null` and every screen controller `None`.

Probed on the real `main()` with no arguments:

```
main() -> 0
context projectSession = None
context coreMaterialController = None
openProjectMenuItem: enabled=False
```

Consequences, all of them shipped in 0.1.0:

- The Core & Material core list is `coreMaterialPanel.controller !== null ?
  controller.coreOptions : []`, so it is literally `[]`. The same holds for
  Windings, Preliminary, Simulation and Review. This is what a user sees as
  "there are no cores to select" -- the catalog is fine: the installed
  `_internal/artifacts/catalog/catalog.sqlite` holds all 15 core records.
- `File > Open` is `enabled: projectSession !== null`, so it is disabled
  exactly when the user has no project. There is no `File > New`. The only
  way into the application is a command line with `--project`.
- `packaging/release_notes.md` ("No sample project is shipped") instructs the
  user to "use **File > Open** with your own project", which cannot be done.

This is not a new feature. `docs/superpowers/specs/2026-07-24-mvp-roadmap-realignment-design.md`
already specifies step 1 of the application as "**New/Open Project** -- create
a blank Project document or open any compatible shared `*.inductor.json`". The
blank-document half was never implemented.

## Approach

Always build the session. When `--project` is absent, the session holds a
blank project and `document_path is None`.

Rejected: wiring the controllers lazily after the first Open (means re-setting
context properties on an already-loaded engine, and every `!== null` branch in
QML stays live forever), and re-launching the process with `--project` (loses
window state, adds process plumbing). Neither buys anything the chosen shape
does not already give, and the stack already anticipates a pathless session:

- `RecoveryStore` has a dedicated slot for `document_path is None`
  (`adapters/persistence/recovery_store.py`), so autosave snapshots work
  before the first save.
- `SimulationController`'s run gate already refuses a pathless project with
  "The project has no document path. Save the project to a file ...".
- `ProjectSession.saveProjectAs` already acquires the new path's lock, so the
  first Save As is what starts locking.

## The blank project

A pure factory, `new_project() -> InductorProject`, with no catalog,
filesystem or Qt import, so its defaults are testable without a window and
`main()` needs nothing from the catalog to call it.

| Field | Value | Where it comes from |
| --- | --- | --- |
| `project_id` | `str(uuid4())` | new. Dashed, not `.hex`: `schemas/project/v5.schema.json` declares `projectId` as `format: uuid`, and a 32-character hex string is rejected by it -- confirmed by probing `ProjectRepository.save`. |
| `name` | `"Untitled inductor"` | new; `InductorProject` rejects a blank name |
| `description` | `""` | new |
| `design.core` | `None` | picking a core is the user's first act |
| `design.core_material` | `None` | follows the core |
| `manual_material_compatibility_acknowledged` | `False` | nothing to acknowledge yet |
| windings | one: `w1`, `"Winding 1"`, 1 turn, `SOLID`, `start_angle_deg` 0.0, `sector_deg` 360.0, `min_spacing_m` 0.0002, `min_clearance_m` 0.001, `CLOCKWISE`, `terminal_intent` `""` | spacing and clearance are the repo's existing convention (`tests/unit/domain/test_project.py`'s `make_winding`) |
| `conductor_name` | `"AWG 18"` | the gauge the repo's own fixtures already wind with (`make_winding`); pinned rather than read from the catalog so the default never shifts when a conductor is added to the index. Test 5 below pins that the shipped index actually carries it. |
| operating point | 100 kHz, 20 degC winding, 25 degC core, one entry for `w1` at 0 A AC, 0 deg, 0 A DC, `FORWARD` | 100 kHz is the repo's existing default (`make_operating_point`); the temperatures are `OperatingPoint`'s own field defaults. No new physical assumption is introduced. |
| simulation recipe | `STANDARD` mesh, 10 passes, 1.0 percent error, requested outputs resistance + inductance | the same established convention as above |

One winding, not zero: `GuidedStudioController.addWinding` copies the last
winding and refuses when there are none, so a zero-winding project could
never grow its first winding.

`sector_deg` 360.0 is legal (`domain/validation.py` accepts `0.0 <
sector_deg <= 360.0`) and says what a single-winding toroid is. It has one
consequence, accepted deliberately: `addWinding` looks for a free sector, so
adding a second winding to an untouched blank project is refused until the
first winding's sector is reduced. The refusal already explains exactly that
-- "no free sector remains on the core. Reduce an existing winding's sector
first." -- so the alternative (starting at some arbitrary fraction of the
core, e.g. 150 degrees) would trade a guided refusal for an unexplained
default.

## Wiring

### `main()`

The `if project is not None:` block becomes unconditional. What stays behind
`if args.project is not None`:

- the `--project` file-exists check,
- the project lock and its refusal paths,
- `_load_project`,
- the startup `reconcile_unfinished_runs`.

The `--catalog` and `--matrix` file checks move OUT of that branch: they guard
resources every launch now needs, not just a launch with a document. (The
startup `_refuse_if_resources_are_missing` covers the shipped defaults but not
an explicitly passed bad flag.)

Otherwise `project = new_project()`, `document_path = None`, `lock = None`.
Every controller is then always built, which is the fix: the core list is
populated on a shortcut launch.

### `ProjectSession.newProject()`

A `@Slot(result=bool)` mirroring `openProject` minus the file.
`_adopt_loaded_project` takes `path: Path | None`; with `None` it sets
`_autosaved_path = None` (the RecoveryStore "unsaved" slot) and skips
`reconcile_unfinished_runs`, which has no directory to scan. It releases the
previous document's lock, clears undo and redo, and seeds `_saved_project`
with the pristine blank project.

That seed matters: `dirty` is `current != _saved_project`, so without it a
launch would report unsaved changes and the Exit guard would nag before the
user touched anything. An untouched new project is therefore not dirty, Save
stays disabled until the first edit, and Save As is how an untouched blank
project gets a name.

### `GuidedStudioController.__init__`

Today the constructor calls `self._build_preview(project)` unguarded, and
`build_geometry_model` refuses a project with no core: "Project has no core
selection; geometry needs one." A blank project would therefore raise
`GeometryModelError` out of the constructor and kill the launch -- probed
directly, not inferred.

The constructor adopts the tolerance `refresh()` already has: on
`GeometryModelError` it starts with an empty preview -- no entries, and a
`CutPlaneDrawing` matching the defaults `CutPlaneView.qml` already carries
(`r_inner_mm`, `r_outer_mm`, `depth_mm` 0.0, `extent_mm` 1.0, no circles or
starts) whose `note` says a core has to be selected first. The QML already
guards its own scaling with `Math.max(root.drawing.extent_mm, 1e-6)` and
already renders `drawing.note`, so nothing on that side changes.

This is the one change outside `main()`, the session and the menu, and it is
the difference between a blank project and a crash on launch.

### QML

- `File > New` above Open, routed through the existing
  `window.requestGuardedProjectAction(...)`, so unsaved work prompts first
  through the one dialog that already guards Open and Exit.
- `File > Save` on a pathless project opens `saveProjectAsDialog` instead of
  calling `saveDraft()`. Today that path raises `RuntimeError("The project has
  no document path to save into.")` from the persister in `main()`.
- `Open`, `Save As` and the Undo/Redo items keep their existing
  `projectSession !== null` guards unchanged. They simply stop being false.

## What stays refused

- Generate and Solve still refuse a pathless project, with the message
  `SimulationController` already produces. A run writes a directory beside the
  document, and there is no document yet.
- No lock is held until the first Save As, which acquires it through the
  existing code and reports the already-open case.

## Tests

Written before the implementation, per `AGENTS.md`.

1. `main()` with no `--project`: the session exists, `coreMaterialController.coreOptions`
   is non-empty, `openProjectMenuItem.enabled is True`, and the session is not
   dirty. This is the defect above, stated as a test.
2. `File > Save` on a pathless project opens the Save As dialog and writes
   nothing; after accepting it, `documentPath` is set and the lock is held.
3. `File > New` from a dirty project shows the unsaved-changes dialog;
   Discard leaves a blank project with an empty undo stack, no document path,
   and the previous document's lock released.
4. `new_project()` round-trips through `ProjectRepository.save`/`load`, which
   proves the defaults satisfy `schemas/project/v5.schema.json`.
5. `new_project()`'s `conductor_name` exists in the built catalog index. A
   pinned gauge is only safe while the shipped index carries it: without this
   test, dropping `AWG 18` from `catalog/conductors/round-wire.yaml` would
   leave the Windings screen on first launch naming a conductor no lookup can
   resolve, and every other test would stay green.
6. Generate stays refused on a pathless project, with the existing message.
7. `GuidedStudioController(session, catalog)` on a coreless project
   constructs without raising, reports no preview entries, and puts the
   select-a-core note on the cut plane. Today this raises `GeometryModelError`
   from the constructor.

## Documentation

`packaging/release_notes.md`'s "No sample project is shipped" section
currently documents a flow the application cannot perform. It becomes: the
first launch opens a blank unsaved project, `File > Save As` names it, and
`File > Open` loads an existing `.inductor.json`.

## Out of scope

Adding catalog cores from inside the application. Today a new core means
editing `catalog/cores/*.yaml`, running `python -m tools.build_catalog`, and
rebuilding the installer (or pointing `INDUCTOR_DESIGNER_RESOURCES` at a tree
containing a rebuilt `artifacts/catalog/catalog.sqlite`). That gap is real and
gets its own design; it is unreachable for a user until this one lands.
