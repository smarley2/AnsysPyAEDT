# DC Operating-Point Compatibility

`select_dc_bias_strategy` remains the single current decision point until M6
replaces the historical compatibility model. Only observed AEDT 2025 R2
Commercial capability may unlock native DC bias.

| Situation | Behavior |
| --- | --- |
| Maxwell 3D, reviewed AEDT 2025 R2 Commercial capability | Native `AC Magnetic with DC` |
| Maxwell 2D | AC-only; DC bias ignored, after explicit user confirmation |
| FEMM | AC-only; DC bias ignored, after explicit user confirmation |
| Missing, unreviewed, or different AEDT target | Blocked |

There is no AEDT 2024 R2 magnetostatic-incremental fallback in the product
scope.

## Amendment, 2026-08-07 (decided by Fabio Posser)

Maxwell 2D and FEMM used to refuse a project with any nonzero DC winding
current outright (`DcBiasStrategy.BLOCKED`, "Maxwell 2D DC-bias generation is
blocked until a validated policy is available"). Fabio hit that refusal in
the shipped app with 5 A DC on the windings and decided it was wrong: neither
backend can represent a DC bias in an AC solve and neither ever will, but
refusing the whole run is not the right response to that fact.

Both backends now generate **AC-only, with the DC current ignored**
(`DcBiasStrategy.AC_ONLY_DC_IGNORED`, `approximate=True`) after the user is
warned and explicitly confirms:

- `select_dc_bias_strategy` returns `AC_ONLY_DC_IGNORED` for every
  `ModelDimension.TWO_D` request, naming the physics: Maxwell 2D and FEMM
  linearize about zero bias and cannot carry a DC premagnetization into an AC
  solve, so the run models the AC excitation only. 3D is unchanged --
  `BLOCKED` for unreviewed or unavailable 3D evidence still means blocked.
- The requested DC current cannot leak into a generated model: the Maxwell 2D
  adapter (`adapters/pyaedt/maxwell2d.py`) never reads
  `Winding2dGroupPlan.dc_current_a`, and `FemmCircuit`
  (`simulation/femm_problem.py`) has no DC field at all. `run_planning.py`'s
  DC-requested check simply stops matching (the strategy is no longer
  `BLOCKED`); the run is not merely relabeled, it never had a DC excitation
  path to begin with.
- The omission is recorded in the plan's notes and therefore in the run
  manifest's `warnings` (`dc_bias_notes` in `simulation/maxwell_plan.py`), so
  a `run-manifest.json` reader cannot mistake an AC-only run for a biased
  solve.
- `SimulationController` (`ui/simulation_controller.py`) exposes
  `dcBiasIgnored`/`dcBiasNotice` for the currently selected backend and
  project; `generate()` refuses to start such a run until
  `proceedAcOnly()` is called, which QML wires to a confirmation dialog's
  Proceed button (`ui/qml/SimulationPanel.qml`). A DC-free project never
  triggers the dialog.

## Verified AEDT 2025 R2 behavior

Live verification on 2026-07-17 established that native DC bias uses the design
solution type `AC Magnetic with DC` (mapped by PyAEDT to
`DCBiasedEddyCurrent`). It is not an `IncludeDcFields` setup property.

Per-winding DC is set through:

```text
winding.props["DC Current"] = "<value>A"
winding.update()
```

AEDT persisted only the exact `DC Current` property name. Historical
`DCCurrent` and `DCValue` guesses were silently ignored and must not return.

Every run with DC bias records the strategy, applied DC current per winding,
backend, exact AEDT/PyAEDT versions, and whether the requested result separates
DC and AC components. A backend that cannot provide a defensible combined field
maximum marks that quantity unavailable.
