# M8b Scalar Normalized Results Evidence

- Milestone: M8b, scalar normalized results
- Plan: [2026-08-10 M8b scalar results](../superpowers/plans/2026-08-10-m8b-scalar-results.md)
- Status: implementation complete; **live solver evidence is still outstanding**
  and only Fabio Posser can record it

## What M8b changed

A solved run now produces the scalar half of the Normalized Result Set. Each
adapter returns backend-raw values through one narrow structure, one pure
service normalizes them, `RunManifest.results` carries the result set, and the
run directory gains `results.json` and `results.csv` beside `solve-log.txt`.
The Review screen shows the numbers in engineering units, with an explicit
reason wherever a backend reported nothing.

Field quantities are untouched: `flux-density` and `current-density` remain
M8c, together with the representative cross sections.

Per backend, what each one can and cannot report:

| Quantity | Maxwell 3D / 2D | FEMM |
| --- | --- | --- |
| Resistance, inductance per winding | matrix diagonal | circuit properties |
| Complex impedance per winding | derived from R and L at the run frequency | derived the same way |
| Resistance and inductance matrices | full matrix when every entry came back | `matrices.not_exposed` |
| Copper loss | `SolidLoss` | `0.5 * R * abs(I_peak)^2` per circuit |
| Core loss | `CoreLoss` | `core-loss.not_reported` |
| Total loss | reported, else derived from the parts and labelled | derived only if a core loss ever appears |
| Magnetic energy | `Total_Energy` | `magnetic-energy.not_reported` |
| Convergence | `convergence_rows` from the solved setup | `convergence.not_exposed` |

## Decisions this slice implements

Taken with Fabio Posser on 2026-08-10:

1. Export is automatic: every solve run writes both files into its own
   `results/`, and there is no export button.
2. Results are a section on the existing Review screen, not a sixth Guided
   Studio step.
3. A total loss the backend does not report is derived as copper plus core
   loss, carrying `DERIVED_TOTAL_LOSS_NOTE` as its approximation and a
   `derived from ...` provenance. It is never presented as solver-reported.

## Non-live gate

Run on the development machine on 2026-08-10, on the branch carrying the M8b
commits:

```bash
.venv/Scripts/python.exe -m ruff check .
```

`All checks passed!`

```bash
.venv/Scripts/python.exe -m mypy src tools
```

`Success: no issues found in 135 source files`

```bash
.venv/Scripts/python.exe -m tools.check_architecture
```

Clean, no output.

```bash
.venv/Scripts/python.exe -m pytest -n 8 -m "not aedt and not femm" -q
```

`1338 passed in 20.28s`

Covered without a solver: the unit and convention table, the raw structure's
square-matrix invariant, normalization of every scalar quantity including the
labelled derivation and the missing-part refusal, Maxwell extraction from the
matrix diagonal, an extraction failure that leaves the solved run successful
while recording its diagnostic, FEMM's per-winding scalars and cycle-mean
copper loss, manifest population, both export files and their artifacts, and
the Review results section.

## Live evidence still to record

```bash
.venv/Scripts/python.exe -m pytest -m aedt -q
```

Requires `INDUCTOR_AEDT_RELEASE=2025.2` and `INDUCTOR_AEDT_EDITION=commercial`.
`tests/integration/aedt/test_maxwell_results_live.py` runs one Maxwell 3D and
one Maxwell 2D solve and asserts every requested scalar quantity is accounted
for, each one available with a unit and a provenance or unavailable with a
dotted reason.

```bash
.venv/Scripts/python.exe -m pytest -m femm -q
```

Requires `INDUCTOR_FEMM_LIVE=1` with `pyfemm` installed.

Record here, once run, the exact `results.json` from one run per backend:
which quantities came back available with which units and provenance, and
every unavailable quantity with its reason. That table is the M8b exit
criterion made concrete.

## Known risks

- **The Maxwell report-quantity names are unproven.** `SolidLoss`,
  `CoreLoss` and `Total_Energy` in `simulation/result_expressions.py` are the
  names this application asks for, and `convergence_rows` is the assumed
  convergence source. None can be verified without AEDT. A name AEDT does not
  recognize returns no data, which surfaces as an `unavailable` quantity with
  a reason and a diagnostic — never as a wrong number. The fix is one line in
  that table; if a quantity is genuinely not exposed, remove the name and let
  it report unavailable.
- **PyAEDT exposes no convergence accessor on `Setup`.** Only `get_profile`
  exists, so the adapter's `convergence_rows` may need
  `post.get_solution_data` with the adaptive-cost report category instead.
  This is isolated to one adapter method.
- **One intermittent UI test.** `tests/ui/test_simulation_controller.py`
  occasionally crashes its `pytest-xdist` worker (`test_proceed_ac_only_...`,
  `test_a_second_proceed_ac_only_...`). It passes serially every time and on a
  rerun under `-n 8`. This is pre-existing Qt/xdist behaviour, not an M8b
  regression, but it is unresolved.
