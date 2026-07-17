# M5a Task 11 Report — Approved Material Export Integration

## Status

Implemented Task 11 from dependency baseline `b3f2bc3`.

## Scope

- Extended the shared solver `MaterialSpec` with B-H points, the existing
  `materials.SteinmetzFit`, and material revision identity.
- Added approved-record conversion and threaded matching project snapshots through the
  Maxwell 3D, Maxwell 2D, and FEMM export services.
- Added nonlinear/core-loss calls to both PyAEDT adapters and B-H point calls to the FEMM
  adapter protocol and recording fake.
- Extended both AEDT and FEMM manifests with B-H point count, Steinmetz coefficients, and
  material revision.
- Updated focused simulation, adapter, export-service, and recording-fake tests. No new
  dependency, UI change, catalog change, schema change, or broad refactor was introduced.

## TDD RED evidence

The material-spec and plan-builder tests were written first. Their initial focused run failed
during collection because the requested conversion API did not exist:

```text
.venv/bin/python -m pytest tests/unit/simulation/test_maxwell_plan.py \
  tests/unit/simulation/test_plan_builder.py \
  tests/unit/simulation/test_plan_builder2d.py -q
ImportError: cannot import name 'material_spec_from_material_record'
3 errors in 0.22s
```

After that first minimal slice passed, tests for both PyAEDT adapters, FEMM propagation and
solver calls, project snapshot resolution, approval enforcement, and manifests were added.
The second RED run isolated all missing integration behavior:

```text
.venv/bin/python -m pytest tests/unit/adapters/test_maxwell3d_exporter.py \
  tests/unit/adapters/test_maxwell2d_exporter.py \
  tests/unit/simulation/test_femm_problem.py \
  tests/unit/adapters/test_femm_solver.py \
  tests/unit/application/test_maxwell_export.py -q
9 failed, 36 passed in 0.34s
```

The nine failures covered nonlinear permeability assignment, both Steinmetz calls, FEMM B-H
problem/call propagation, approved snapshot selection and rejection, fallback manifest
fields, and 2D/FEMM revision propagation.

## GREEN evidence

- First material-spec/builder slice: `24 passed in 0.18s`.
- Second adapter/export slice: `45 passed in 0.27s`.
- Combined focused Task 11 suite: `69 passed in 0.40s`.

## Acceptance and self-review

- Export accepts a project material snapshot only when its full `MaterialRef` matches the
  selected core and the record status is `APPROVED`; matching non-approved records become a
  typed export block.
- Approved B-H data bypasses the powder-family/grade fallback, so ferrite records export.
  With no matching snapshot, the existing powder grade path and draft behavior are unchanged.
- Canonical record points stored as `(H, B)` become solver points `(B, H)` exactly once.
- Relative permeability uses the record scalar when present and otherwise reuses
  `mean_relative_permeability` over canonical B-H points. FEMM retains that scalar in
  `mi_addmaterial` as its linear fallback before adding nonlinear points.
- The native-DC linear-material caveat is omitted only when the selected material has a B-H
  curve; all other DC decision notes remain unchanged.
- PyAEDT recording fakes assert list-of-lists permeability assignments and exact
  `set_power_ferrite_coreloss(cm=k, x=alpha, y=beta)` keyword calls in both dimensions.
- FEMM recording tests assert `mi_addbhpoints(name, [[B, H], ...])` occurs after material
  creation. The FEMM protocol and fake expose the same API.
- Both manifest formats emit `bhPointCount`, `steinmetz` (`k`, `alpha`, `beta` or null), and
  `materialRevision` (revision or null); grade fallback assertions remain green.
- The added `material_revision` plan field is the minimum state required to produce the
  approved manifest identity without parsing a sanitized material name.
- No architecture boundary or physical assumption changed beyond approved plan decision D10;
  no ADR is required. UI gates are not applicable because no UI surface changed.

## Required gates

- `.venv/bin/python -m pytest tests -q -m "not aedt and not ui and not femm"`
  - `513 passed, 9 deselected in 3.09s`
- `.venv/bin/python -m ruff check .`
  - `All checks passed!`
- `.venv/bin/python -m mypy`
  - `Success: no issues found in 85 source files`
- `.venv/bin/python tools/check_architecture.py`
  - Exit code 0, no output.
- `git diff --check`
  - Exit code 0, no output.

## Live verification pending

No AEDT/PyAEDT or FEMM live installation was available, so this task makes no live-solver
claim. Exact pending risks are:

1. In supported AEDT releases, confirm the nonlinear permeability list and ferrite core-loss
   keyword calls persist in the material editor for both Maxwell 2D and Maxwell 3D.
2. In FEMM 4.2 through the installed pyfemm version, confirm `mi_addbhpoints(name, points)`
   accepts the recorded list shape/order and that the B-H table survives save and reopen.
3. Confirm live FEMM combines the scalar `mi_addmaterial` permeability fallback with the
   subsequent nonlinear table as expected.
4. Run one approved ferrite record end-to-end and inspect material assignment, core loss, and
   nonlinear B-H data in each solver; the current evidence is unit/recording-fake only.

## Commit

`feat(simulation): approved material records drive nonlinear solver materials`

## Concerns

Only the live solver arbitration listed above remains pending.
