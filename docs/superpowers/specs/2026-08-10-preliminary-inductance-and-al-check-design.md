# Preliminary Inductance and A_L Check Design

- Status: Approved in collaborative design review
- Date: 2026-08-10
- Product surface: Standalone Windows application
- Supported geometry: Toroidal cores
- Related design:
  [2026-07-26 Preliminary calculations and guided flow](2026-07-26-preliminary-calculations-and-guided-flow-design.md)

## 1. Purpose

The Preliminary screen reports flux density, current density, and loss. It does
not report the quantity a choke is specified by: inductance. This design adds
inductance, the effective inductance factor `A_L`, a check of that factor
against the manufacturer's catalog value, effective permeability, stored energy,
and an echo of the core's effective geometry.

Every added quantity is solver-independent and derived from the field strengths
and flux densities the estimator already computes. No Maxwell or FEMM run is
started, and no value claims solver accuracy.

## 2. Confirmed product decisions

- Inductance is evaluated from the **incremental (small-signal) permeability**
  at the DC bias, because that is the inductance a converter sees at the
  operating point.
- When the operating point carries no AC ripple, the incremental slope is
  undefined. Permeability falls back to the secant `B_dc / H_dc` and the result
  carries a note saying so.
- When the operating point carries neither AC nor DC current, permeability is
  undefined and inductance is Unavailable. No zero, no default, no substituted
  initial permeability.
- `A_L` is reported once at the core level. Every winding's inductance is
  `N² · A_L`.
- The **catalog `A_L` is the only reference** for the check and for the
  permeability roll-off. The reference initial permeability is derived back from
  it, so the two reported numbers can never disagree.
- A Manual core has no catalog `A_L`. The check is Unavailable with its own
  diagnostic code, while inductance, `A_L` effective, and permeability stay
  estimated.
- Stored energy is reported once, at the core level, from the core volume. It is
  not reported per winding, because the per-winding sum is wrong for coupled
  windings without a mutual term.
- Mutual inductance and coupling factor are not reported. At this level of model
  the toroid is a perfect shared-flux path, so `k = 1` and `M = N₁ · N₂ · A_L`
  add no information.
- Catalog dimension overrides change the modeled geometry but not the
  manufacturer's effective area, path length, or volume, exactly as they already
  do not change path length and volume today.

## 3. Reported quantities

`μ₀ = 4π × 10⁻⁷ H/m`. `A_e`, `l_e`, and `V_e` are the core's effective area,
effective magnetic path length, and effective volume. `H` and `B` values are the
existing `FieldStrengths` and `FluxDensities`.

### 3.1 Permeability

The absolute incremental permeability over the operating excursion is

```
mu_abs = (B_max - B_min) / (H_max - H_min)
```

`H_max - H_min` equals `2 · h_ac_peak`. When `h_ac_peak` is zero the expression
is `0 / 0`; permeability is then the secant at the bias point,

```
mu_abs = B_dc / H_dc
```

and the result carries the zero-ripple note. When `h_ac_peak` and `H_dc` are
both zero, permeability, inductance, `A_L` effective, the `A_L` check, and
stored energy are all Unavailable with code `inductance.no_excitation`.

The reported effective relative permeability is `mu_r_eff = mu_abs / μ₀`.

### 3.2 Inductance factor and inductance

```
A_L_effective = mu_abs * A_e / l_e          [H per turn squared, shown in nH]
L_winding     = turns^2 * A_L_effective      [shown in uH]
```

`turns` is read from `WindingDefinition.turns` in the design, never from the
caller, matching how ampere-turns are already assembled.

### 3.3 A_L check

```
A_L_catalog   = al_value_nh * 1e-9
mu_r_initial  = A_L_catalog * l_e / (mu_0 * A_e)
A_L_deviation = A_L_effective / A_L_catalog - 1     [shown as a percentage]
```

`A_L_deviation` is the roll-off statement: percent permeability at the operating
point is `100 % + A_L_deviation`. Only one of the two is reported, because they
are the same fact.

The reported `mu_r_initial` is derived from `A_L_catalog`, not read from the
material record. The material snapshot's `relative_permeability` remains what it
is today: a fallback B-H model, never a reference for this check.

### 3.4 Stored energy

```
W = 0.5 * B_peak_magnitude * H_peak * V_e           [shown in mJ]
```

where `H_peak = max(|H_min|, |H_max|)`, chosen to pair with the existing
`b_peak_magnitude_t` so the two factors describe the same instant of the cycle.

This is the energy of a linear medium taken from the origin to the peak, and it
is an upper bound on the true `V_e * integral of H dB` for any saturating
curve. It is therefore **not** `0.5 * L * I_peak^2` computed from the reported
incremental inductance: on a biased powder core the two differ by roughly the
ratio of the secant to the incremental permeability, measured at 2.6 on a
representative ferrite point. Both numbers appear on the same screen, so the
stored-energy note states which permeability it assumes and in which direction
it errs. Integrating the recorded B-H series instead would remove the
discrepancy and is the open improvement here; it needs the series itself passed
into the estimator, which this design does not do.

## 4. Diagnostics

New stable codes, added to `DiagnosticCode` and never reused:

| Code | Meaning |
| --- | --- |
| `inductance.no_flux_density` | Flux density is unavailable, so permeability, inductance, and `A_L` cannot be evaluated. Carries the flux-density reason in its message. |
| `inductance.no_excitation` | The operating point has neither AC nor DC ampere-turns, so permeability is undefined. |
| `inductance.non_positive_geometry` | The core's effective area or magnetic path length is not positive, or their ratio underflows to zero, so `A_L` cannot be evaluated. |
| `inductance.non_finite_geometry` | The core's effective area or magnetic path length is not finite, or their ratio overflows. |
| `inductance.non_positive_permeability` | The recorded B-H excursion does not increase with field strength. Corrupt series data, which material selection blocks but a persisted project snapshot is never revalidated against; without this the screen reports a negative inductance as Estimated. |
| `al_check.no_catalog_al` | The core has no usable manufacturer `A_L` value, so the check has no reference. Reported for a Manual core, and for a recorded value that is not positive and finite. |
| `stored_energy.no_flux_density` | Flux density is unavailable, so stored energy cannot be evaluated. |
| `stored_energy.non_positive_volume` | The core's effective volume is not positive. |
| `stored_energy.non_finite_volume` | The core's effective volume is not a finite number. |
| `stored_energy.not_finite` | The product of peak flux density, peak field strength, and volume overflows. |
| `inductance.not_finite` | The permeability slope, or the inductance factor derived from it, overflows. Prevents a non-finite estimate from becoming a screen-level failure. |
| `core_geometry.non_positive` | An echoed effective dimension is not positive. |
| `core_geometry.not_finite` | An echoed effective dimension is not a finite number. |

Each dependent quantity reports its own code rather than borrowing the
flux-density code, following the rule already established for
`core_loss.no_flux_density`: a borrowed code would claim a quantity failed for a
reason that is not its own.

## 5. Architecture

### 5.1 Core magnetic properties

`CoreMagneticProperties` in `simulation/preliminary_contracts.py` gains

- `effective_area_m2: float`
- `al_value_nh: float | None`, where `None` means "this core has no
  manufacturer inductance factor".

`application/services/preliminary_inputs.core_magnetic_properties` fills both. A
catalog core takes them from its snapshot. A Manual core supplies the effective
area it already computes and discards today, and `None` for `al_value_nh`; its
existing `MANUAL_CORE_PATH_NOTE` already documents how `A_e` is obtained.

### 5.2 A new estimator module

`simulation/inductance_estimate.py` holds the whole computation as one pure
function taking `FieldStrengths`, `FluxDensities`, and `CoreMagneticProperties`,
and returning either a value object or a single `PreliminaryValue` diagnostic.
It imports nothing beyond the existing simulation contracts.

This mirrors `magnetic_estimate.py`, `winding_estimate.py`, and
`core_loss_estimate.py`. Placing it in `preliminary.py` would give that module a
third responsibility and make the permeability rules untestable without
assembling a whole `PreliminaryRequest`.

### 5.3 Result shape

`CorePreliminary` gains `effective_area`, `path_length`, `volume`,
`mu_r_effective`, `mu_r_initial`, `al_catalog`, `al_effective`, `al_deviation`,
and `stored_energy`. `WindingPreliminary` gains `inductance`.

`_core_all` propagates one flux-density reason into every new field, using the
codes in section 4 rather than the flux-density code, exactly as it already does
for core loss.

A winding's inductance depends on the core, not on its conductor record, so it
stays estimated when a conductor fails to resolve, and becomes Unavailable when
the core does. This is the reverse of the copper quantities and is deliberate.

The effective-geometry echo is evaluated from `CoreMagneticProperties`
independently of flux density, in the same way wire length is evaluated
independently of wire loss. A missing B-H series at the requested temperature
must not make the core's effective area read Unavailable, which is why the echo
carries its own `core_geometry.*` reasons.

### 5.4 Presentation

`ui/preliminary_rows.py` gains display units for microhenry, nanohenry per turn
squared, percent, cubic centimetre, millijoule, and a dimensionless unit whose
formatted text carries no suffix. All conversion stays in this module; QML
computes nothing.

The Core summary table gains rows for effective area, magnetic path length,
effective volume, effective relative permeability, initial relative permeability
from catalog `A_L`, catalog `A_L`, effective `A_L`, `A_L` deviation, and stored
energy. The winding table gains an `Inductance` column, pinned at its own fixed
preferred width like the existing eight, so the columns still do not scale with
the window.

`ui/review_controller.py` picks up the new core rows without change, because it
maps `coreRows` generically. It gains one per-winding inductance line beside the
existing per-winding current-density line.

## 6. Assumptions and excluded effects

The Preliminary screen's assumptions list gains:

- inductance uses the incremental permeability at the DC bias; air-gap fringing,
  leakage inductance, and winding self-capacitance are excluded;
- the catalog inductance factor is a low-signal value, so the reported deviation
  mixes bias roll-off with catalog tolerance and cannot separate them;
- stored energy is the effective-core-volume estimate; energy stored in the
  winding window and in leakage paths is excluded.

The zero-ripple secant note is attached to the affected values only, not to the
permanent list.

## 7. Verification

Tests are written before implementation, per `AGENTS.md`.

- `tests/unit/simulation/test_inductance_estimate.py`: incremental permeability
  from a known excursion; zero-ripple secant fallback and its note; both-zero
  excitation Unavailable; `A_L` and inductance against a hand-computed toroid;
  deviation sign for an effective factor above and below catalog; stored energy;
  non-positive and non-finite area and volume guards.
- `tests/unit/simulation/test_preliminary.py`: each new field Unavailable with
  its own code when the core, the material, or the acknowledgment is missing;
  Manual core reports `al_check.no_catalog_al` while inductance stays estimated;
  inductance stays estimated when a conductor record is missing.
- `tests/unit/simulation/test_preliminary_contracts.py`: the extended
  `CoreMagneticProperties`.
- `tests/unit/application/test_preliminary_inputs.py`: catalog area and `A_L`
  taken from the snapshot; Manual area computed and `A_L` `None`.
- `tests/unit/ui/test_preliminary_rows.py`: every new row and column, its unit
  text, and the dimensionless suffix.
- `tests/ui/test_preliminary_controller.py`, `tests/ui/test_flow_screens_qml.py`,
  `tests/ui/test_review_controller.py`: the new column and rows reach the views.

Command: `pytest -n 8`.
