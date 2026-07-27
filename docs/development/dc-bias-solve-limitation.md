# Native DC-bias solves fail above a model-size threshold

Maxwell 3D solution type `AC Magnetic with DC` exports and validates correctly
but **fails during the solve** on production-sized toroid models. Design
validation passing is not evidence that a design solves; M4 and M5a both proved
persistence and validation only, and never ran a solver.

- Environment: AEDT 2025.2.0 Commercial (`ansysedt.exe` 2025.2.0.1),
  PyAEDT 1.2.0, Python 3.13.14, Windows 11.
- First observed: 2026-07-27 by Fabio Posser, then reproduced headlessly.

## Symptom

```
[error] Map linked data onto target mesh failed! It may be the result of
        mismatching objects, orientations, or mesh elements on curved
        surfaces from source design.
[error] Simulation completed with execution error on server: Local Machine.
```

Earlier attempts on the same design also reported `No such file: Setup1.sld`
and `Unable to create child process: 3dedy`. Both are downstream of the same
failure: the linked DC solution is never produced, so the eddy-current stage
has nothing to consume.

## Reproduction

Generate the M5a pinned project (core `C058071A2`, two windings, 10 turns each,
100 kHz, 5 A DC per winding) with `tools/generate_maxwell3d.py`, then solve
`Setup1`. Fails in roughly 14 minutes, single task, 8 cores, non-graphical.

## Root cause

`AC Magnetic with DC` runs two solves inside one setup: a nonlinear DC
magnetostatic solve, then the AC eddy-current solve that consumes the DC
operating point. Each drives its own adaptive refinement from its own error
estimator, so the two meshes diverge. Maxwell then has to interpolate the DC
field onto the AC mesh, and that interpolation fails on the revolved core and
revolved D-loop conductors — all curved surfaces.

Small models survive because the two meshes stay close enough to interpolate.

## Evidence

| Configuration (real geometry unless noted) | Result |
| --- | --- |
| 2 turns/winding, default adaptivity | solves clean, 3m27s |
| 10 turns/winding, default adaptivity | map failed |
| 10 turns, `ImportMeshForMuLink=true` | map failed (flag persisted in the saved project) |
| 10 turns, every DC knob matched to its AC counterpart | map failed |
| 10 turns, 2 adaptive passes both steps | map failed |
| **10 turns, 1 adaptive pass both steps** | **solves, 14m24s, no errors** |

Excluded as causes:

- **Our material.** Ansys stock nonlinear `steel_1008` fails identically on the
  same geometry, and our High Flux 60 record solves fine at 2 turns.
- **Distributed solving and GPU.** The original failure used DDM with 5 tasks
  and 16 cores; the headless reproduction uses one task, 8 cores, no GPU.
- **B-H data quality.** 501 points, strictly increasing in both H and B, no
  duplicate or flat segments, differential relative permeability falling
  smoothly from 83.6 to 9.3. The DC operating point reaches roughly 1800 A/m,
  well inside the tabulated range, so no extrapolation is involved.
- **Mass density.** Setting it changed nothing (it is a separate real defect —
  the exporter never writes it; see the material-records follow-up).

The DC half of the solve is not the problem: the profile records
`Adaptive Passes converged` for the DC stage, and `.DCMesh` and `.DCField`
artifacts are written before the mapping fails.

## Two-design mu-link: attempted, blocked

The supported Ansys route for DC bias is a magnetostatic source design plus an
`AC Magnetic` design that mu-links to it and imports its mesh, which keeps both
solves on one converged mesh. Confirmed working on our geometry:

- the design duplicates, and the copy accepts `Magnetostatic`;
- both windings accept `Current = 5A` for the DC operating point;
- the magnetostatic design **solves with full adaptivity** (`Normal completion`);
- the target accepts plain `AC Magnetic`, whose setup natively exposes
  `UseMuLink` and `MeshLink`;
- `Setup.add_mesh_link("InductorDC")` succeeds, filling `MeshLink` with
  `ImportMesh`, `Product='Maxwell 3D'`, `Design`, `Project='This Project*'`,
  `Soln='Setup1 : LastAdaptive'`, `ForceSourceToSolve`, `PreservePartnerSoln`.

Blocked at the last step. Enabling `UseMuLink` is rejected with:

```
[error] the partner project name of the link cannot be empty.
```

Mu-link does not read `MeshLink`; it wants its own partner block, and that
property name is not available anywhere on the machine — not in PyAEDT's setup
templates, not in `Ansys.Ansoft.SimSetupData.dll` (which does carry the other
setup keys), not in the shipped example projects, and not in the installed
help.

Probed so far: `MuLinkSetup` as the outer key (rejected with the message above),
and a fully populated `MeshLink` block with `UseMuLink=true` (rejected with the
same message, which is what proves mu-link reads a different block). A sweep of
further candidate names — `MuLinkData`, `MuLink`, `MuLinkSoln`, `MuLinkInfo`,
`MuLinkPartner`, `MuLinkSetupData`, `MuLinkSource`, `LinkedDesign`,
`MuLinkSolution` — was prepared but has not been run, so those remain untested
rather than eliminated.

To finish this route, record the property name from a GUI session: configure
Mu Link once in the Eddy Current setup's advanced options, save, and read the
`Setup1` block out of the `.aedt` file. That is a five-minute manual step and
it unblocks the whole approach.

## Ordering constraints discovered

- Changing a design's solution type **deletes setups the new type cannot
  host**. Any exporter that switches solution type must create the setup after
  the switch, not before.
- PyAEDT pushes every `setup.props[...]` assignment to AEDT immediately.
  Interdependent properties must be batched with `setup.auto_update = False`
  and a single `update()`, or AEDT rejects the intermediate state.
- A link must point at a solution that already exists; wire links after the
  source design has solved.

## Status

Unresolved for production-sized models. `1 adaptive pass on both steps` is the
only configuration observed to solve, and it reports
`Adaptive Passes did not converge based on specified criteria`, so its accuracy
is not established. It is a diagnostic workaround, not a shipping default, and
the exporter has deliberately **not** been changed to adopt it.
