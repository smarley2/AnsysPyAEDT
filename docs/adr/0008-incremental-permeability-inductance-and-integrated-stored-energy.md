# ADR 0008: Incremental-Permeability Inductance and Integrated Stored Energy

- Status: Accepted
- Date: 2026-08-10

## Context

The Preliminary screen reported flux density, current density, and loss, but not
the quantity a choke is specified by: inductance. Adding it forces two physical
choices that a reader will otherwise have to reverse-engineer from arithmetic.

**Which permeability.** At an operating point with a DC bias and AC ripple, a
powder or ferrite core has no single permeability. The secant `B/H` through the
bias runs several times the local slope `dB/dH` — measured at 2.56 on a
representative ferrite point — so the two choices differ by more than any
tolerance the reader might attribute the gap to.

**Which energy.** `0.5 * B_peak * H_peak * V_e` is the energy of a linear medium:
the area under a straight line from the origin to the peak. The energy a
saturating core actually stores is the area to the *left* of its B-H curve,
`V_e * integral of H dB`. On a representative saturating series the linear form
reads 21 % high, and the error grows with bias. Reported next to an
incremental-permeability inductance, it also invited the reader to expect
`0.5 * L * I_peak^2` and get a number 2.6 times smaller.

Integrating the curve requires the B-H series inside the energy calculation,
which previously saw only the interpolated flux-density values.

## Decision

Inductance is evaluated from the **incremental permeability at the DC bias**,
`(B_max - B_min) / (H_max - H_min)` over the operating excursion, because that is
the inductance a converter sees. When the operating point carries no AC ripple
the slope is `0/0`; permeability is then the secant `B_dc / H_dc`, and the value
carries a note stating that the secant runs above the incremental permeability
and the inductance is therefore optimistic. With neither AC nor DC excitation,
permeability is undefined and inductance is Unavailable — the material's initial
permeability is never substituted.

`A_L` is reported once at the core level as `mu * A_e / l_e`; every winding's
inductance is `turns^2 * A_L`. The catalog `A_L` is the single reference for the
check, and the reference initial permeability is derived back from it, so the two
reported permeabilities cannot disagree. Mutual inductance and coupling factor
are not reported: at this level of model the toroid is a perfect shared-flux
path, so they would state an assumption rather than a result.

Stored energy is `V_e * integral of H dB` along the recorded B-H curve,
integrated as exact trapezoids between recorded points with the peak-containing
segment cut at the peak. Nothing is extrapolated. Where no curve exists — the
linear-permeability fallback — the same integral has the closed form
`0.5 * B * H * V_e`, which is exact for that model and equals `0.5 * L * I_peak^2`
for it too.

`FluxDensities` therefore carries the `PointSeries` it was built from.
Re-selecting the series inside the energy calculation was rejected: it could
choose a different series than the one the flux densities came from.

## Consequences

- Reported inductance matches the converter's operating point rather than a
  small-signal datasheet figure, and the zero-ripple case says when it does not.
- Stored energy no longer over-reports by a bias-dependent margin, so it can be
  used for energy-handling sizing.
- With a recorded curve, stored energy and `0.5 * L * I_peak^2` legitimately
  differ: the first is the total stored at the peak, the second the energy of a
  small ripple about the bias. Each value's note names its model, because both
  appear on the same screen.
- `simulation` gains a dependency from `magnetic_estimate` on
  `materials.records.PointSeries`, which the module already imported. No new
  layer boundary is crossed.
- Corrupt or absent recorded data is refused rather than approximated: a B-H
  excursion that decreases with field strength, a peak above the recorded curve,
  and a curve that doubles back below the peak each report their own stable
  diagnostic code.
- The catalog `A_L` and the initial permeability derived from it depend only on
  the core, so they are reported even when flux density, permeability, and
  inductance are all unavailable. Only the deviation needs an operating point.

## References

- [2026-08-10 Preliminary inductance and A_L check design](../superpowers/specs/2026-08-10-preliminary-inductance-and-al-check-design.md)
- [ADR 0006: RMS project current and peak solver excitation](0006-rms-project-current-and-peak-solver-excitation.md),
  for the same principle applied to excitation: state the convention explicitly
  rather than leaving a factor implicit.
