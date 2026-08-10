# M8c Field Results Evidence

- Milestone: M8c, field results
- Plan: [2026-08-10 M8c field results](../superpowers/plans/2026-08-10-m8c-field-results.md)
- Design: [2026-08-10 Representative Cross Sections](../superpowers/specs/2026-08-10-representative-cross-sections-design.md)
- Status: implementation complete; **live solver evidence is still outstanding**
  and only Fabio Posser can record it

## What M8c changed

A solved run now reports magnetic flux density and current density, evaluated
the way the approved design requires.

- **Selection is pure.** `simulation/section_selection.py` chooses the core
  planes from the winding layout and the conductor discs from the skin-depth
  gate. The same project and frequency give the same sections, in the same
  order, with the same identifiers, on any machine.
- **3D evaluates sections.** The Maxwell 3D adapter creates one non-model sheet
  per section — a rectangle in the rotated half-plane for the core, a disc
  perpendicular to the wire for a conductor — and reads the integral and the
  maximum off each. The sheets stay in the saved project, so a reader can see
  which surfaces produced which number.
- **2D integrates regions.** Maxwell 2D evaluates the core annulus and the
  conductor regions directly and creates no sheets: in 2D the evaluated area is
  the region itself.
- **Reporting.** Every section appears individually, plus the worst-section
  mean, the across-section area-weighted average and the point maximum. A
  volume average never appears.

## Decisions this slice implements

Taken with Fabio Posser on 2026-08-10:

1. **FEMM reports no field value.** `mo_blockintegral` integrates over the core
   block, but its integral types expose `∫Bx dA` and `∫By dA` rather than
   `∫|B| dA`. In the planar toroid model the flux circulates around the ring,
   so those components cancel and a component mean would read near zero at full
   working flux. FEMM therefore reports `flux-density.not_exposed` and
   `current-density.not_exposed` with that reason.
2. **A DC-biased run reports the combined field.** One solve produces the total
   field including the bias, so it is reported with
   `current_convention = combined` and an approximation naming it a DC-biased
   total. No AC-only entry is emitted, because a single nonlinear solve cannot
   separate the components.

Taken in the plan:

3. Per-section values are ordinary `NormalizedQuantity` entries scoped
   `core.section.<id>` and `winding.<id>.section.<id>`, with the section
   geometry in `provenance`. That satisfies the design's requirement that every
   section is recorded in the Run Manifest, with no schema change.
4. The Review screen shows the three aggregates and a `Per-section detail` row
   pointing at `results.json` and `results.csv`. A run can carry a dozen
   sections; the screen summarizes, the exports keep everything.

## A gap this slice closed in M8b

M8b added `solution_values` and `convergence_rows` to the Maxwell app
protocols, but a real PyAEDT `Maxwell3d` object has neither, so the live
extraction would have failed into a diagnostic and reported everything as
unavailable. `adapters/pyaedt/live_app.py` now wraps the real application and
implements the whole extraction protocol over PyAEDT, delegating everything
else untouched. The scalar path and the field path share it.

## Non-live gate

Run on the development machine on 2026-08-10, on the branch carrying the M8c
commits:

```bash
.venv/Scripts/python.exe -m ruff check .
```

`All checks passed!`

```bash
.venv/Scripts/python.exe -m mypy src tools
```

`Success: no issues found in 141 source files`

```bash
.venv/Scripts/python.exe -m tools.check_architecture
```

Clean, no output.

```bash
.venv/Scripts/python.exe -m pytest -n 8 -m "not aedt and not femm" -q
```

`1396 passed`

Covered without a solver: core-plane selection including a full-cover winding,
disjoint sectors, a wrapping sector, the 0.5-degree deduplication boundary and
feature precedence; the skin-depth gate in all three branches including the
unevaluable-temperature escalation; sheet creation as non-model, rectangles for
the core and discs for conductors; one failed section leaving the others
intact; 2D integrating regions and creating no sheets; the two aggregates and
the point maximum, with the partial-failure note and the all-failed reason; the
FEMM refusal text; the DC-bias label; and the Review rows.

## Live evidence still to record

```bash
.venv/Scripts/python.exe -m pytest -m aedt -q
```

Requires `INDUCTOR_AEDT_RELEASE=2025.2` and `INDUCTOR_AEDT_EDITION=commercial`.
`tests/integration/aedt/test_maxwell_fields_live.py` runs one Maxwell 3D and
one Maxwell 2D solve with every output requested, asserts the contract for each
field entry, and cross-checks that the extraction saw exactly the sections
selection chose.

Record here, once run:

- the sections chosen for the test project, with their azimuths and features;
- the per-section means and maxima, and the two aggregates, per backend;
- every unavailable entry with its reason; and
- one DC-biased run showing the `combined` convention and the absent AC-only
  entries.

## Known risks

- **The field-quantity names are unproven.** `Mag_B`, `Mag_J`, `"Integrate"`
  and `"Maximum"` in `adapters/pyaedt/field_reader.py` are assumed. An
  unrecognized name yields a per-section diagnostic and an unavailable
  quantity, never a wrong number. The fix is one constant.
- **Sheet creation is unproven.** `create_rectangle` with `non_model=True`
  followed by a rotation about Z, and `create_circle` in the XY or YZ plane
  followed by a rotation, are the assumed mechanics. Selection only ever
  produces axial or radial disc normals, so no arbitrary orientation is needed
  — but whether PyAEDT accepts `non_model` on a rectangle is a live question.
  If sheet creation fails, the whole field set reports unavailable with the
  modeler's own error attached; nothing is invented.
- **Convergence rows remain the weakest scalar.** `Setup.get_profile()` is used
  for lack of a convergence accessor; if its shape does not carry a per-pass
  error, convergence stays `not_exposed`.
- **One intermittent UI test.** `tests/ui/test_simulation_controller.py`
  occasionally crashes its `pytest-xdist` worker and passes on rerun and
  serially. Pre-existing Qt/xdist behaviour, unresolved.
