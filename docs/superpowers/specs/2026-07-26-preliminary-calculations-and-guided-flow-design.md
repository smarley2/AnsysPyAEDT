# Preliminary Calculations and Guided Flow Design

- Status: Approved in collaborative design review
- Date: 2026-07-26
- Product surface: Standalone Windows application
- Supported geometry: Toroidal cores
- Related design:
  [2026-07-24 MVP roadmap realignment](2026-07-24-mvp-roadmap-realignment-design.md)

## 1. Purpose

Add solver-independent preliminary magnetic and loss calculations before the
Simulation step. Reorganize Guided Studio so core and material are selected
together, move Material Studio outside the project-authoring flow, and prevent
free-form text in numeric winding fields.

This design extends the MVP roadmap realignment. It replaces the separate
`Core`, `Windings`, and `Materials` ordering in that document with:

1. `Core & Material`
2. `Windings`
3. `Preliminary`
4. `Simulation`
5. `Review`

Material Studio remains part of the application but is not a Guided Studio
step.

## 2. Confirmed product decisions

- One shared frequency applies to the complete choke operating point.
- Catalog cores and material revisions filter each other in both directions.
- A Manual core can use any material after the user explicitly acknowledges
  that compatibility is their assumption.
- Material Studio opens in a separate window from a button on the
  `Core & Material` screen.
- Closing Material Studio refreshes the available material revisions without
  replacing a still-valid project selection.
- Preliminary values update after every valid relevant edit.
- A missing input or unsupported model affects only the dependent result.
  Other valid preliminary values remain visible.
- Multiple winding AC ampere-turns are combined as phasors using phase and
  current direction. DC ampere-turns are combined separately.
- Winding and core temperature are separate shared numeric inputs.
- Numeric fields reject invalid characters while editing and remain subject to
  domain validation when committed.
- Preliminary calculations never start Maxwell or FEMM.
- A run requires a saved Project document and writes to a new normalized
  project-local run directory without overwriting an earlier run.
- Solver operation is background/non-graphical by default, with a per-run
  visible-window option when the selected adapter and installed solver support
  it.
- Generated `.aedt` and `.fem` files remain available for manual use but never
  synchronize changes back into the Project document.

## 3. Project and operating-point model

The backend-independent Project document stores one operating point containing:

- `frequency_hz`, shared by all windings;
- `winding_temperature_c`, defaulting to `20 °C`;
- `core_temperature_c`, defaulting to `25 °C`; and
- each winding's AC RMS current, phase, DC current, and current direction.

Frequency is removed from individual winding definitions. The Project document
pins the exact selected core-material revision. Preliminary results are derived
data and are not persisted as editable source truth.

Catalog cores retain their required `MaterialRef`. Selecting a material revision
matches catalog cores by that identity. Selecting a catalog core restricts
material choices to revisions with the core's required identity. Revision
status, B-H series selection, and provenance remain visible and pinned exactly.

A Manual core has no authoritative compatibility mapping. All selectable
material revisions remain available, but the Project document records explicit
user acknowledgment that compatibility is assumed.

## 4. Guided Studio behavior

### 4.1 Core & Material

The screen contains two searchable selectors:

- core selector: catalog records plus Manual core;
- material selector: selectable imported or approved material revisions.

Selecting either value filters the other list. If a new choice makes the
existing paired selection incompatible, the application clears the incompatible
selection and explains why. It never substitutes a different core or material.

Manual-core dimensions stay on this screen. Selecting a material for a Manual
core requires a visible compatibility acknowledgment before Preliminary,
generation, or solve operations can treat the pair as complete.

An `Open Material Studio` button opens Material Studio in a separate application
window. Material import, replacement, download, and guarded deletion stay in
that window. When it closes, Guided Studio reloads the material library. An
exact pinned revision remains selected if it still exists and is compatible;
otherwise the selection becomes unresolved with an actionable message.

### 4.2 Windings

A shared operating-point section exposes:

- frequency in hertz;
- winding temperature in degrees Celsius; and
- core temperature in degrees Celsius.

Each winding exposes turns, conductor, conductor mode, placement, spacing,
clearance, AC RMS current, AC phase, DC current, winding direction, and current
direction.

Integer and floating-point editors use native QML validators to block invalid
characters. Domain validation remains authoritative for positivity, finiteness,
ranges, collision constraints, and integer-only turn counts. Conductor, mode,
and direction values use selectors rather than free-form text. Only values
whose meaning is textual, such as a user label or terminal intent, use
unrestricted text input.

### 4.3 Preliminary

The Preliminary screen is read-only. It contains:

- core summary: DC flux density, AC flux-density swing, minimum and maximum
  flux density, peak magnitude, and core loss;
- winding table: conductor area, estimated wire length, resistance,
  `J_AC_RMS`, `J_AC_peak`, `J_DC`, and wire loss for every winding; and
- totals: total wire loss, core loss when available, and total preliminary loss
  only when both components are available.

Every displayed result has one state:

- `Estimated`: calculation completed, with approximation labels;
- `Unavailable`: required input or supported material model is absent; or
- `Invalid`: an input exists but violates a physical or model constraint.

The screen always shows assumptions, excluded effects, units, selected material
revision, and the reason for every non-estimated value.

### 4.4 Simulation and Review

Simulation selects backend, generate/solve mode, mesh intent, convergence
intent, and requested solver outputs. It does not duplicate frequency or
temperature inputs.

Review shows the paired core and material, shared operating point, winding
excitations, preliminary estimates and limitations, run request, validation
findings, and solver approximation notices.

Before its first run, a new Project must be saved so it has a stable Project
directory. Each Run Request creates:

```text
<project-directory>/
  <project-name>.inductor.json
  runs/
    <run-id>-<backend>/
      run-manifest.json
      <generated solver project>
      results/
```

Backend labels distinguish Maxwell 3D, Maxwell 2D, and FEMM. The native solver
project uses `.aedt` or `.fem`. `results/` is reserved for M8 and may be absent
or empty after Generate Only. Run Manifest artifact references are relative to
the Project directory. A new run never implicitly overwrites a prior directory
or solver project.

Generation uses background/non-graphical solver operation by default.
Simulation exposes `Show solver window` for a run when the selected adapter and
installed solver support it. An unsupported visible mode is disabled with an
explanation rather than silently changing behavior. Application stage progress
remains authoritative whether the solver window is shown or hidden.

After successful generation, Review offers `Open generated file` and `Open run
folder`. The generated solver file can be edited and simulated manually, but it
is an independent output: the application does not import, synchronize,
compare, or back-propagate solver-side edits into `*.inductor.json`.

## 5. Solver-independent estimator

The estimator belongs inside solver-independent simulation/application code.
It may consume domain objects, material records, catalog records, and the
existing solver-independent geometry model. It must not import Qt, PyAEDT,
FEMM, SQLite, or operating-system APIs.

The UI controller requests one immutable preliminary result and converts it to
QML-facing rows. QML contains no physical formulas.

Each quantity is evaluated independently. For example, missing loss curves can
make core loss unavailable while flux density, current density, and wire loss
remain estimated.

## 6. Magnetic-field estimate

For winding `k`, let:

- `N_k` be its turn count;
- `I_rms,k` be AC RMS current;
- `phi_k` be AC phase;
- `I_dc,k` be DC current; and
- `s_k` be `+1` or `-1` from current direction.

The shared-frequency AC peak ampere-turn phasor is:

```text
A_AC_peak = sum_k(s_k * N_k * sqrt(2) * I_rms,k * exp(j * phi_k))
```

The DC ampere-turn value is:

```text
A_DC = sum_k(s_k * N_k * I_dc,k)
```

Using the core effective magnetic path length `l_e`:

```text
H_AC_peak = abs(A_AC_peak) / l_e
H_DC = A_DC / l_e
H_min = H_DC - H_AC_peak
H_max = H_DC + H_AC_peak
```

The selected B-H series must support the requested core temperature. It maps
`H_min`, `H_DC`, and `H_max` to `B_min`, `B_DC`, and `B_max`. A first-quadrant
monotonic B-H series uses an explicitly reported odd-symmetry assumption for
negative `H`. Interpolation is allowed within the recorded range; extrapolation
is not.

Derived values are:

```text
B_AC_peak = (B_max - B_min) / 2
B_peak_magnitude = max(abs(B_min), abs(B_max))
```

If no selected B-H series exists but the material has a valid relative
permeability, the estimator may use:

```text
B = mu_0 * mu_r * H
```

This result is labeled `linear permeability approximation; saturation and
hysteresis are not modeled`. If neither model exists, flux-density results are
unavailable.

The preliminary `B` value is a lumped effective-core estimate. It is not a
local maximum, area-weighted mean, leakage-field result, or replacement for
Maxwell/FEMM field extraction.

## 7. Current-density and wire-loss estimate

For a round conductor with bare diameter `d_bare`:

```text
A_copper = pi * d_bare^2 / 4
J_AC_RMS = I_AC_RMS / A_copper
J_AC_peak = sqrt(2) * J_AC_RMS
J_DC = I_DC / A_copper
```

Current density is uniform over the copper area. Skin and proximity
redistribution are excluded.

The existing packing result provides the modeled closed-loop turn length. The
estimate excludes connectors, external leads, and terminals because those
lengths are not part of the current solver-independent winding model. This
exclusion is always visible.

For copper at winding temperature `T_w`, use:

```text
rho(T_w) = rho_20 * (1 + alpha_20 * (T_w - 20 °C))
R_DC(T_w) = rho(T_w) * wire_length / A_copper
P_wire = R_DC(T_w) * (I_AC_RMS^2 + I_DC^2)
```

The initial model uses annealed 100% IACS copper:

```text
rho_20 = 1.7241e-8 ohm metre
alpha_20 = 0.00393 per degree Celsius
valid winding-temperature range = 10 °C through 100 °C
```

These values and the linear validity range derive from the US National Bureau
of Standards copper measurements:
https://nvlpubs.nist.gov/nistpubs/bulletin/07/nbsbulletinv7n1p71_A2b.pdf.
Temperatures outside that range make wire resistance and loss unavailable
rather than extrapolated.

The result is labeled `DC-resistance wire-loss estimate`. It excludes skin
effect, proximity effect, eddy-current loss, terminal loss, connector loss, and
temperature rise.

Per-winding wire losses may be summed because they are real dissipated powers.

## 8. Core-loss estimate

Core loss requires an available flux-density estimate, positive shared
frequency, positive core volume, a compatible selected material revision, and
loss data whose conditions support the requested core temperature and DC bias.

Preferred evaluation order:

1. Use a compatible recorded loss table at the requested frequency,
   temperature, and DC-bias condition, interpolating only within its recorded
   flux-density range.
2. Otherwise use the Steinmetz fit stored in the eligible selected immutable
   revision when the requested frequency and `B_AC_peak` lie within the
   source-data envelope and all source loss samples used by the fit support the
   requested temperature and DC-bias condition.
3. Otherwise report core loss as unavailable.

For a compatible Steinmetz fit:

```text
P_volume = k * frequency^alpha * B_AC_peak^beta
P_core = P_volume * core_volume
```

No temperature correction, DC-bias correction, waveform correction,
frequency extrapolation, flux-density extrapolation, or material substitution
is invented. Nonzero DC bias without supporting loss data makes core loss
unavailable while leaving other quantities unaffected.

## 9. Validation and diagnostics

- Empty, nonnumeric, nonfinite, and physically invalid inputs are rejected at
  their owning boundary.
- A failed edit preserves the last valid Project document and preview.
- Incompatible core/material selection is visible and unresolved, never
  auto-corrected.
- Material deletion or replacement cannot silently alter a pinned revision.
- Geometry failure marks only geometry-dependent preliminary results invalid.
- Every unavailable or invalid result carries a stable diagnostic code plus
  user-facing English text.
- Preliminary estimates never claim solver accuracy.

## 10. Testing

Test-driven implementation covers:

- AC phasor summation across multiple windings, phases, and current directions;
- separate DC ampere-turn summation;
- B-H interpolation, negative-field odd symmetry, range blocking, and linear
  permeability fallback;
- conductor area and AC RMS, AC peak, and DC current density;
- copper resistance temperature correction and mixed AC/DC wire loss;
- explicit exclusion of connectors and leads;
- loss-table and Steinmetz evaluation within supported conditions;
- missing, mismatched, and out-of-range material data;
- per-quantity `Estimated`, `Unavailable`, and `Invalid` states;
- bidirectional core/material filtering and incompatible-selection clearing;
- Manual-core compatibility acknowledgment;
- native numeric validators and domain range validation;
- separate Material Studio launch and material-library refresh;
- live Preliminary refresh after valid project edits; and
- dependency-boundary enforcement for estimator modules.

UI tests verify accessible names, keyboard entry, decimal input, negative values
where valid, integer-only turns, selectors for enumerated values, and visible
diagnostic reasons.

## 11. Acceptance criteria

Starting from a valid toroidal project, a user can:

1. choose a compatible core and exact material revision in either order;
2. open Material Studio separately, import a material, return, and see refreshed
   compatible choices;
3. enter one shared frequency plus core and winding temperatures;
4. edit all numeric winding values without entering arbitrary strings;
5. view live preliminary `B`, per-winding `J`, DC-resistance wire loss, and core
   loss before choosing a solver;
6. see exact assumptions and reasons for unsupported values;
7. continue to Maxwell or FEMM generation using the same persisted physical
   inputs; and
8. reproduce all estimates deterministically without Qt, Maxwell, or FEMM.

No preliminary result includes or implies conductor eddy-current, skin,
proximity, local-field, leakage, thermal-rise, or solver-derived behavior.

## 12. Milestone ownership and execution gate

This specification is the complete approved requirements record for this M7
change. Requirements do not need to be brainstormed again after M6.

M6 owns only the prerequisite contracts and persistence changes:

- one shared `frequency_hz` in the Operating Point;
- explicit `winding_temperature_c` and `core_temperature_c`;
- AC RMS current naming and the single RMS-to-peak conversion;
- removal of per-winding frequency;
- an exact pinned core-material revision;
- Manual-core material-compatibility acknowledgment; and
- deterministic round-trip of those values in the replacement Project schema.

M7 owns:

- the `Core & Material`, `Windings`, `Preliminary`, `Simulation`, and `Review`
  flow;
- bidirectional core/material filtering;
- the separate Material Studio window and library refresh;
- numeric validators and enumerated selectors;
- the complete solver-independent estimator defined in sections 5–8;
- partial result availability and diagnostics;
- reactive Preliminary presentation; and
- the existing Generate Only Guided Studio exit criterion;
- normalized, non-overwriting project-local run directories;
- background generation by default, optional supported solver-window
  visibility, and visible status inside the application; and
- post-generation actions to open the native solver project or its run folder.

M8 reuses the same run-directory and visibility rules for Generate and Solve
and owns population of normalized result artifacts. M9 remains responsible for
interrupted-run recovery.

The detailed M7 implementation plan will be written separately before M7
implementation. It must target the stable M6 contracts, cite this
specification, copy its physical constants and exclusions verbatim, and
implement
[ADR 0007](../../adr/0007-project-local-run-artifacts-and-solver-visibility.md)
without reopening approved product or physics decisions unless the existing
contracts prove a direct contradiction.
