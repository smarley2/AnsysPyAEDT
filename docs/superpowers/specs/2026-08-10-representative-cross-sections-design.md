# Representative Cross Sections for 3D Field Results Design

- Status: Approved in collaborative design review
- Date: 2026-08-10
- Delivery milestone: M8, Simulation and Results
- Supported geometry: Toroidal cores
- Supported AEDT target: AEDT 2025 R2 Commercial only
- Related designs:
  [2026-07-24 MVP roadmap realignment](2026-07-24-mvp-roadmap-realignment-design.md)
  section 8, and
  [2026-07-26 Preliminary calculations and Guided flow](2026-07-26-preliminary-calculations-and-guided-flow-design.md)

## 1. Purpose

The roadmap realignment requires an Area-Weighted Mean of magnetic flux
density `B` and current density `J`, and states that in 3D the evaluated area
is a Representative Cross Section. It also requires M8 to define a
deterministic section-selection algorithm before implementation, to record
every section in the Run Manifest, to report each section mean and the worst
section mean, and it forbids satisfying the requirement with a volume average.

That algorithm is undefined everywhere else in the documentation. This design
defines it, and nothing else. Solver execution, progress, cancellation, result
export mechanics, and the non-field quantities remain M8 work governed by the
realignment design.

## 2. Scope

In scope:

- how 3D core sections and 3D conductor sections are chosen;
- what each section records;
- how per-section values become the reported aggregates;
- how sections appear in the Run Manifest and in the JSON and CSV exports; and
- what happens when a section cannot be evaluated.

Out of scope:

- Maxwell 2D and FEMM 2D, which integrate the evaluated region directly and
  use no sections at all;
- adaptive refinement that adds sections in response to extracted values;
- volume averages, which the realignment design forbids for this requirement;
  and
- every non-field result quantity.

## 3. Architectural boundary

Section selection is a pure, solver-independent computation. It lives in
`simulation/` beside the existing run contracts, imports no PyAEDT, no Qt, and
no operating-system API, and depends only on the domain project, the existing
toroid geometry functions, and the run request.

Sheet creation and field-calculator evaluation live in the Maxwell 3D adapter.
The adapter consumes a section list it did not choose and returns per-section
values. It never selects, reorders, adds, or drops a section.

## 4. Section model

A `CoreSection` records:

- `section_id`, the stable identifier `core.<nn>.<feature>`;
- `azimuth_deg`, the plane azimuth in `[0, 360)`;
- `feature`, the layout feature that produced the plane; and
- the evaluated region, the core cross-section cut by the r-z half-plane at
  that azimuth.

A `ConductorSection` records:

- `section_id`, the stable identifier
  `winding.<winding-id>.turn<nn>.<station>`;
- `winding_id`, `turn_index`, and `station`;
- `center_m`, the disc centre on the modelled turn path;
- `normal`, the local wire tangent at that point, so the disc is perpendicular
  to the current direction; and
- `radius_m`, the bare conductor radius, giving area `pi * radius_m^2`.

Identifiers are stable: the same Project document and the same run frequency
produce the same identifiers in the same order on any machine. `<nn>` is
zero-padded to two digits and assigned after the ordering rules below.

## 5. Core section selection

Core planes are anchored to the winding layout, because in a toroid `B` is
azimuthally uniform except where the magnetomotive force distribution changes:
at the edges of a winding sector and in the azimuthal gaps that no winding
covers.

Each winding contributes its span from the domain fields `start_angle_deg` and
`sector_deg`. For every winding span, three planes are emitted with features
`span-start`, `span-mid`, and `span-end`. For every maximal azimuthal gap that
no winding sector covers, one plane is emitted at the gap midpoint with
feature `gap-mid`.

The emitted planes are then deduplicated with a tolerance of 0.5 degrees,
keeping the first plane in feature precedence order `span-start`, `span-end`,
`span-mid`, `gap-mid`, and sorted ascending by azimuth before identifiers are
assigned. A single winding covering the full 360 degrees therefore yields two
planes, its start and its midpoint, because its end aliases its start and no
gap exists.

This produces four to eight planes for the layouts the product supports, and
every plane sits at a position where a departure from azimuthal uniformity is
expected rather than at an arbitrary angle.

## 6. Conductor section selection

The wire cross-section area is constant along a winding, so a single disc
represents the whole winding exactly whenever the current distribution inside
the wire is uniform. That condition is decidable before the run: it holds at
DC and wherever the skin depth is not smaller than the wire radius. Where the
skin depth is smaller, proximity effect from neighbouring turns and from the
core makes the distribution position-dependent, and the crowded inner bore no
longer matches the outer wall.

The skin depth is

```text
delta = sqrt(rho(T_winding) / (pi * f * mu_0))
```

with `rho` the temperature-corrected copper resistivity already implemented in
`simulation/winding_estimate.py` and `f` the run frequency.

Selection is therefore gated:

- `f = 0`, or `delta >= wire_radius`: one section per winding, on the middle
  turn, at the `inner-bore` station.
- `delta < wire_radius`: four sections per winding, on the middle turn, at the
  `inner-bore`, `top-face`, `outer-wall`, and `bottom-face` stations.
- The winding temperature outside the validated copper range in
  `winding_estimate.py` makes `rho`, and therefore the gate, unevaluable. The
  four-station branch is then selected as the conservative outcome and the
  reason is recorded.

The middle turn is turn index `floor((N - 1) / 2)` for a winding of `N` turns,
so the choice is deterministic and independent of turn parity. Station centres
and tangents come from the existing modelled turn path in
`geometry/turn_path.py`; no new turn geometry is introduced.

The Run Manifest records `delta`, the wire radius, the winding temperature,
and which branch fired, so a reader can tell a one-section result that is
exact from a one-section result that merely was not escalated.

## 7. Extraction

For each section the adapter creates one sheet in the Maxwell 3D design,
named after the `section_id`, and flags it non-model so it cannot affect the
mesh or the solution. The sheets remain in the saved `*.aedt` file: a user who
opens the generated project sees exactly which surfaces produced each reported
number, which the manifest geometry description alone cannot show.

For each section the adapter evaluates, through the field calculator, the area
integral of the field magnitude divided by the section area, and the maximum
magnitude on the section:

```text
F_section_mean = integral_A(|F| dA) / A
```

For core sections `F` is `B` over the core region. For conductor sections `F`
is `J` over the conductor region of the owning winding.

## 8. Current conventions

Section values are extracted at AC peak, matching the peak solver excitation
fixed by ADR 0006.

An AC RMS value is derived as the peak value divided by the square root of two
only when the run carries no DC bias and is a single-harmonic solve on a
linearly operating material. Otherwise the AC RMS entry is `unavailable` with
reason code `field.rms_not_derivable`, naming the condition that failed.

With DC bias, DC, AC peak, and AC RMS remain separate entries, and no combined
maximum is reported unless the backend supplies a defensible one. This repeats
the realignment design rather than relaxing it.

## 9. Reported quantities

Every section value is reported individually. Two aggregates are reported per
scope, where the scope is `core` for core sections and `winding.<id>` for
conductor sections:

- the **worst-section mean**, the maximum over sections of the section area
  mean; and
- the **across-section average**, the section area means averaged with each
  section weighted by its own area.

The reported point maximum for a scope is the maximum over sections of the
per-section maximum.

Each entry keeps the existing `NormalizedQuantity` contract: backend,
dimensional representation, unit, current convention, approximation status,
availability, and provenance. Provenance names the section or the section set
that produced the value.

## 10. Availability and failure

Availability is per section. If some sections fail to evaluate, the aggregates
are computed from the surviving sections and carry an approximation note that
names the failed `section_id` values. If every section in a scope fails, the
quantity for that scope is `unavailable` with a reason. A section is never
silently dropped, and a partial section set is never presented as complete.

## 11. Manifest and export

Every section is recorded in the Run Manifest whether or not it evaluated,
with its identifier, feature or station, azimuth or turn and station, centre,
normal, area, mean, maximum, and availability. The exported JSON carries the
same section tree with its provenance. The exported CSV carries one row per
section plus the aggregate rows, so a section value and the aggregate derived
from it are both traceable in the tabular export.

## 12. Verification

Selection is verified without a solver:

- winding span and gap enumeration, including a full-cover winding and
  multiple disjoint sectors;
- deduplication exactly at the 0.5 degree tolerance boundary;
- identifier and ordering stability across two independent builds of the same
  Project document;
- both skin-depth branches, and the out-of-range-temperature branch that
  forces four stations; and
- golden section sets for the three M6 golden projects, so a change in
  selection cannot pass unnoticed.

Extraction is verified against the protocol fake at the adapter boundary, and
end to end in a live Maxwell 3D run behind the existing `aedt` marker.

## 13. Physical assumptions

- `B` in a toroid departs from azimuthal uniformity at winding sector edges
  and in uncovered gaps; planes anchored to those features find the departure.
  No claim is made that these planes bound the field for a layout outside the
  supported toroidal family.
- One conductor disc represents a winding exactly only under the skin-depth
  condition in section 6; outside it, four stations sample the positions where
  proximity crowding differs most, and this is sampling, not a bound.
- Copper resistivity, its temperature coefficient, and its validated
  temperature range are unchanged from `simulation/winding_estimate.py`. This
  design introduces no new material constant.
