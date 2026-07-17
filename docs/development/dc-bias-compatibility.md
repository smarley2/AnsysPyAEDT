# DC operating-point compatibility

`select_dc_bias_strategy` is the single decision point. Its inputs come from
`compatibility/aedt-matrix.yml` through `MatrixCapabilityRepository`; the
decision lands in the generation manifest (`dcBias` block) and the Guided
Studio Simulation summary.

| Situation | Strategy | Approximate |
|---|---|---|
| 2D project | blocked | – |
| Row unreviewed / missing | blocked | – |
| `includeDcFields3d: true` (2025 R1+) | native-include-dc-fields | no |
| `includeDcFields3d: false`, release 2024 R2 | magnetostatic-incremental-fallback | yes |
| otherwise | blocked | – |

## Reviewing Include DC Fields on 2025 R2 (required to unlock native)

1. Open the M0 probe project (or any Eddy Current design) in AEDT 2025 R2.
2. Confirm the solve setup exposes the "Include DC fields" option and that a
   winding accepts a DC value alongside the AC excitation.
3. Set `includeDcFields3d: true` on the 2025.2/commercial row of
   `compatibility/aedt-matrix.yml`, update `evidenceReviewedAt`/`evidenceReviewedBy`.
4. Re-run `tools/run_aedt_maxwell3d.ps1` with a project carrying nonzero
   `dcCurrentA`; verify the manifest reports `native-include-dc-fields`, the
   design uses the `AC Magnetic with DC` solution type, per-winding
   `'DC Current'` values exist in AEDT, and validation passes.

Verified live against AEDT 2025.2 (2026-07-17): native DC bias is the design
solution type `AC Magnetic with DC` (pyaedt maps this to
`DCBiasedEddyCurrent`, 2025 R1+); the setup then carries DC convergence
properties (`DCMaxmumPasses`, etc.) automatically — there is no
`IncludeDcFields` setup property. Per-winding DC is set via
`winding.props["DC Current"] = "<value>A"` followed by `.update()`; this is
the only prop name AEDT persists — `DCCurrent`/`DCValue` are silently
ignored and the field stays at its `0mA` default.

## 2024 R2 fallback

Deferred (decision D4, 2026-07-16). The strategy is identified and recorded
in the manifest, but nothing is generated for it: no 2024 R2 installation
exists, and the incremental linearization is physically a no-op until
Milestone 5 delivers nonlinear B-H material data (today's material model is
linear μr). Generation work returns when a 2024 R2 installation is available.
