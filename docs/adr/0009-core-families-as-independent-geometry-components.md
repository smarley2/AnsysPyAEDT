# ADR 0009: Core Families as Independent Geometry Components

- Status: Accepted
- Date: 2026-09-04

## Context

The application was a toroid application. `geometry/` held nine modules whose
every coordinate was azimuthal, `WindingDefinition` placed turns by
`start_angle_deg` and `sector_deg`, `FinishedCore` was `r_inner_m` /
`r_outer_m` / `half_height_m`, and the whole preview and export stack read
those. Milestone 11 adds E, PQ, EQ and EER families, and the approved design
spec constrains how: later families arrive "without changing the toroid
implementation into a universal monolith".

Two shapes were available. Widen the existing types until they describe every
family -- a core with optional legs, a placement with optional angles -- or add
each family as its own component behind the seams the application already has.
The first is cheaper for one family and worse for every family after it: each
consumer then asks which half of its input is populated, and a reader cannot
tell which numbers a given design actually used.

An E core also forced a physical question the toroid never raised. An E core
used as an inductor is gapped, and a gap changes the magnetic model rather than
its parameters: reluctance is no longer `l_e/(mu*A_e)`, and the iron's share of
the ampere-turns depends on the flux density, which depends on the material.

## Decision

**Families are independent geometry components.** `geometry/toroid/` and
`geometry/ecore/` each own their body type, packer, turn path and profile.
Nothing in the toroid package knows what a leg is; nothing in the E-core
package knows what an azimuth is. They meet only at the geometry model, and
each family has its own model type -- `GeometryModel` and
`ECoreGeometryModel` -- rather than one type carrying both families' packings.

**Placement is a union, not a shared pair of numbers.**
`ToroidPlacement(start_angle_deg, sector_deg)` and
`LegPlacement(leg, window_start_m, window_span_m)`. Toroid code obtains the
first through `require_toroid_placement`, which states the assumption once and
refuses the other by name.

**The project schema is replaced, not migrated.** v6 carries the placement
union and the E-core selection; a v5 document is refused with its version
named. Consistent with v3, v4 and v5, each of which replaced its predecessor.
Ruled by Fabio Posser on 2026-09-04, on the specific ground that before
release 0.2.0 the installed application could neither open nor create a
project, so almost no v5 documents can exist. That ground expires: once real
designs are saved, the next bump is a different decision and must not cite
this one.

**A gapped core's magnetics are a reluctance network, summed per section**
(centre leg, both yokes, the two outer legs in parallel) and reduced exactly
to an iron length and a gap length referred to the centre-leg area. Exactly,
because every iron term carries `1/mu_r` and no gap term does. Flux then comes
from the loadline `NI = H*l_iron + (B/mu_0)*l_gap` intersected with the
material's recorded B-H curve, not from ampere-turns over a path length.

**Fringing is excluded**, matching the exclusion the inductance estimate
already declares. The consequence is stated wherever a gapped value is
reported: reluctance understated, inductance overstated, worse as the gap
grows -- and, with fringing ignored, several small gaps are indistinguishable
from one gap of the same total, which is the very reason distributed gaps
exist. A solved run is what shows the difference.

## Consequences

The toroid is untouched by construction: its modules moved with `git mv` and
its tests passed with nothing but import lines changed. Every family after the
E core costs a new component rather than a widening of the old one, and no
consumer of a toroid model can be handed E-core data.

The cost is duplication that a universal type would have avoided: two packers,
two geometry models, and -- until M11b -- an E core with no 3D mesh and no
solver export. Consumers that only ever meant the toroid (`plan_builder`,
`tessellation`, `manifest`) refuse an E-core project rather than half-handling
it.

Two failures this design made possible, both found by review after the first
implementation and both worth recording:

- The gapped loadline and the gap term in `A_L` were written, unit-tested and
  then never called from the estimate, so gapped numbers silently used
  `H = NI/l_iron` while their provenance note claimed the network. Unit tests
  for a solver nothing calls prove nothing; the estimate is now pinned through
  its public entry point.
- The yoke reluctance was counted twice -- each yoke is two runs in parallel,
  not one run in series -- giving 1.349x the true reluctance. Every test
  compared the implementation against the same expression evaluated by hand,
  so the error in the expression was invisible. There is now a brute-force
  node analysis that builds the network independently.
