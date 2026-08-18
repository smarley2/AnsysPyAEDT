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

## The report-quantity names, settled live on 2026-08-18

The two risks this section used to carry -- that the Maxwell names and the
convergence source could not be proven without AEDT -- are now settled, on AEDT
2025 R2 Commercial, Maxwell 3D, solution type AC Magnetic.

An AC Magnetic design exposes exactly these quantities, enumerated by walking
`post.available_quantities_categories` and then
`post.available_report_quantities` per category:

| Category | Quantities |
| --- | --- |
| Loss | `CoreLoss`, `SolidLoss`, `PerWindingSolidLoss(<w>)`, `StrandedLoss`, `StrandedLossAC`, `StrandedLossR` |
| L / Lnom / R / Rnom / Z / Znom / Coupling Coeff | `Matrix1.<name>(<w>,<w>)` |
| Winding | `FluxLinkage(<w>)`, `InducedVoltage(<w>)`, `InputCurrent(<w>)` |
| Design | `Volume(<object>)`, `Area(<terminal>)` |

Read back from one completed solve of the M8b test design at 125 kHz, 2 A RMS,
20 turns:

| Expression | Value |
| --- | --- |
| `Matrix1.L(w1,w1)` | 21 423.5 nH |
| `Matrix1.Lnom(w1,w1)` | 21 423.5 nH, identical |
| `Matrix1.R(w1,w1)` | 0.073 144 ohm |
| `Matrix1.Z(w1,w1)` | 0.073 144 + j16.826 ohm |
| `SolidLoss` | 292.84 mW |
| `CoreLoss` | 80.68 mW |

The reactance is its own cross-check: 2 pi x 125 kHz x 21.4235 uH = 16.83 ohm,
which is the imaginary part AEDT reports separately. So `SolidLoss`, `CoreLoss`
and the `Matrix1.L` / `Matrix1.R` entries are the right names, and the `nom`
flavours carry the same numbers.

**`Total_Energy` was wrong and is gone.** AC Magnetic has no energy category at
all -- not `Total_Energy`, `TotalEnergy`, `Energy` or `Total_Magnetic_Energy`,
all four tried. Magnetic energy needs a Magnetostatic or Transient solution.
The application no longer asks: `DEVICE_EXPRESSIONS` holds the two loss names,
and magnetic energy reports `magnetic-energy.not_exposed` on the Maxwell
backends, naming AC Magnetic as the reason. FEMM keeps
`magnetic-energy.not_reported`, because FEMM does expose a stored-energy block
integral that nothing here reads yet.

**Convergence comes from `ExportConvergence`,** parsed by
`adapters/pyaedt/convergence_file.py`. `get_profile()` describes timing steps
and carries no adaptive error, which is why walking it returned nothing.

### A dead solver was being reported as a solved run

The same session exposed a defect the recorded risks did not predict. One live
run finished its first adaptive pass, then lost its eddy-current child process:

```
Unable to create child process: 3dedy. Please contact Ansys technical support.
Simulation completed with execution error on server: Local Machine.
```

The desktop then reported no simulation running, which is exactly what
`solve_watch.analyze_watched` waited for, so the run was recorded `succeeded`.
It published the copper loss, core loss and 1-pass convergence that the one
completed pass had produced, while every matrix entry read NaN and resistance,
inductance, impedance and both matrices came back unavailable.

`Setup.is_solved` cannot catch this: it was `True` for the broken run and for a
good one. `setup.get_profile()[setup].status` separates them exactly --
`Engine Detected Error` against `Normal Completion` -- and survives a reopen.
`analyze_watched` now reads that verdict and refuses to call such a solve
finished. An empty status stays acceptable, because absence of a verdict is not
a verdict.

## Known risks

- **One intermittent UI test.** `tests/ui/test_simulation_controller.py`
  occasionally crashes its `pytest-xdist` worker (`test_proceed_ac_only_...`,
  `test_a_second_proceed_ac_only_...`). It passes serially every time and on a
  rerun under `-n 8`. This is pre-existing Qt/xdist behaviour, not an M8b
  regression, but it is unresolved.
