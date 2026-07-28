# Native DC-bias solves and the curved-surface mapping failure

**Resolved 2026-07-28.** The shipping configuration is 16-sided conductors plus
TAU initial mesh settings with curvilinear meshing disabled, verified solving by
Fabio Posser on AEDT 2025 R2 with adaptive refinement at the shipped defaults.
Both halves are required; either alone fails. The rest of this document is the
investigation that established it, kept because the dead ends are expensive to
rediscover.

## Background

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
| 10 turns, 1 pass, after a solved magnetostatic design in the same project | solves, 2m30s, no errors (mesh import itself failed; see below) |
| 10 turns, TAU mesh settings, curvilinear off, **round** conductor, default adaptivity | fails |
| **10 turns, TAU mesh settings, curvilinear off, 16-sided conductor, default adaptivity** | **solves** — the shipping configuration |

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

## Importing a converged mesh instead: also blocked

If the mu-link cannot be enabled, the next idea is to keep the native
`AC Magnetic with DC` setup but feed it the adaptively converged mesh from a
solved magnetostatic design, and disable in-design refinement. That would take
mesh quality from AEDT's own adaptivity rather than from our sizing rules.

Tried, and it does not work: `Setup.add_mesh_link()` returns `False` on an
`AC Magnetic with DC` setup, while succeeding on a plain `AC Magnetic` setup in
the same project on the same geometry. Mesh import is not available on the
native DC-bias solution type, even though the setup does carry a `MeshLink`
block. The run therefore degenerated to the plain one-pass case: the target
solved with no solver errors, but on its own unrefined mesh, with no accuracy
gained.

So both routes out of this defect are closed for now — mu-link needs an
undocumented property name, and mesh import is unsupported on the solution type
that needs it.

## Ordering constraints discovered

- Changing a design's solution type **deletes setups the new type cannot
  host**. Any exporter that switches solution type must create the setup after
  the switch, not before.
- PyAEDT pushes every `setup.props[...]` assignment to AEDT immediately.
  Interdependent properties must be batched with `setup.auto_update = False`
  and a single `update()`, or AEDT rejects the intermediate state.
- A link must point at a solution that already exists; wire links after the
  source design has solved.

## Resolution: initial mesh settings

Fabio Posser found it. The trigger is the **initial mesh configuration**, not the
setup, the material, or the geometry. Curvilinear meshing produces curved
elements on curved surfaces, and the DC-to-AC mapping fails on precisely those —
which is what the error message said all along.

The working configuration, read back out of his saved project rather than
transcribed from the dialog:

```
GlobalSurfApproximation: CurvedSurfaceApproxChoice='UseSlider', SliderMeshSettings=6
GlobalCurvilinear:       Apply=false
GlobalModelRes:          UseAutoLength=true
MeshMethod='AnsoftTAU'
UseLegacyFaceterForTauVolumeMesh=false
DynamicSurfaceResolution=false
UseFlexMeshingForTAUvolumeMesh=false
```

The 3D adapter's mesh stage now applies exactly this through
`Mesh.assign_initial_mesh_from_slider(level=6, method="AnsoftTAU",
curvilinear=False, dynamic_surface=False, flex_mesh=False)`, and two unit tests
pin the values so curvilinear meshing cannot be switched back on unnoticed.

Adaptive refinement is left at the shipped defaults, so the earlier workaround of
forcing one pass is no longer needed.

**The mesh settings alone are not sufficient.** Tested 2026-07-28 by Fabio
Posser: `artifacts/mesh-fix-round-wire/`, which pairs these settings with the
original **round** conductor and default adaptivity, still fails. An earlier
revision of this document claimed the mesh configuration superseded conductor
faceting; that was wrong.

Both changes are required together — the mesh settings **and** a faceted
conductor. That is consistent with the failure mode: the settings stop AEDT
generating curved *elements*, but a round wire still presents curved *surfaces*
for the mapper to work across. Removing both is what clears it.

The combination under test is `artifacts/faceted-wire/facets-16/`: 16-sided
conductors plus these mesh settings, default adaptivity.

### Maxwell 2D

PyAEDT restricts Maxwell 2D to mesh methods `["Auto", "AnsoftClassic"]` and emits
no curvilinear or dynamic-surface arguments for it, so this configuration cannot
be applied there. Only the surface-approximation slider carries over, and the 2D
adapter sets it to the same level. 2D never links a DC solution into an AC one,
so it does not hit this failure mode at all.

## Conductor faceting — the second half of the fix

`CONDUCTOR_FACETS` in the 3D adapter sets the number of flat facets on the
conductor cross-section, and the coil terminal's `num_sides` must match it. It
still defaults to `0` (true circle) pending a solve that confirms the 16-sided
combination, and pending the copper-area decision below.

Faceting the conductor **without** faceting the terminal fails validation with
`Find conduction path: '..._Coil (Face_N)' is not on any conduction path`: the
terminal sheets are built separately, and a round terminal overhangs a faceted
conductor. Conductor and terminal must use the same side count — a coupling in
the exporter that nothing had exercised before.

### The copper-area cost, still undecided

An inscribed regular N-gon carries less copper than the wire circle it replaces,
so DC resistance rises by roughly the inverse:

| Sides | Copper area vs round | DC resistance |
| --- | --- | --- |
| 8 | 90.0% | about 11% high |
| 16 | 97.4% | about 2.7% high |
| 24 | 98.9% | about 1.1% high |

This is a change to the numbers the tool reports, not a meshing detail, and it
needs an explicit decision before faceting becomes the default. Options:

1. Accept it at a high side count.
2. Compensate the cross-section width by `sqrt(pi / ((n/2) sin(2pi/n)))` so the
   areas match. This widens the conductor envelope, which the clearance and
   packing checks validated against the round diameter, so it can create overlaps
   those checks already approved.
3. Keep round wire for reporting and facet only for solving, which means two
   geometries to keep consistent.

## Superseded workaround

**One adaptive pass on both steps** solves (14m24s) but reports
`Adaptive Passes did not converge`, so its accuracy was never established. The
exporter was deliberately not changed to adopt it, and the mesh settings remove
the need for it.
