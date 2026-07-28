# M5a live material validation evidence

Concrete observations from the controlled live run that proves one exact real
material revision reaches AEDT 2025 R2 Commercial and FEMM 4.2 with its
nonlinear B-H curve and its core-loss model.

## Review

| Field | Observation |
| --- | --- |
| Review date | 2026-07-27 |
| Reviewer | Fabio Posser (BRUSA), live run delegated to Claude Code on the licensed workstation |
| Workbook import | Performed earlier by Fabio Posser through Material Studio |
| Outcome | All automated and file-level checks pass. One human GUI check remains open; see [Outstanding](#outstanding). |

## Material source

| Field | Observation |
| --- | --- |
| Source URL | <https://www.mag-inc.com/products/powder-cores/high-flux-cores/high-flux-material-curves#high-flux-dc-mag> |
| Source filename | `MagneticsHighFlux60u.xlsx` (page 7) |
| Source SHA-256 | `3725a087798d7d737886a8cb77d2e03bee9c5f626fdbcf2d60b6d4649d452f81` |
| Capture date | 2026-07-23 |
| Redistribution decision | The overlay is a **shared** material database: colleagues check out the repository and get the records plus their sources, and add more materials the same way. Source bytes are therefore tracked in Git under `materials-overlay/`, superseding the original M5a constraint that forbade committing them. Keep the repository private unless Magnetics permits redistribution of the workbook. |

Per-series source hashes, exactly as recorded in the revision:

| Series source file | SHA-256 |
| --- | --- |
| `series-bh_25c.csv` | `0a247745fe4bb18c879f38856692e5caab03543583145266a59660828fa289c3` |
| `series-loss_100khz.csv` | `09b7743e42ca9b65995f81d8937b96a90087f9e8fbbe2ef35628baf62612c38d` |
| `series-loss_50khz.csv` | `097080dd568a911ae10d9f76a172c1ca0440447b596d36d9b2d1f0004f57d20b` |

Git must not rewrite line endings under `materials-overlay/`, or these hashes
break on checkout. `.gitattributes` pins `materials-overlay/** -text` for that
reason; without it, `core.autocrlf=true` produced
`ERROR: sha256 mismatch for source series-bh_25c.csv` on a fresh clone.

## Material identity and fit

| Field | Observation |
| --- | --- |
| Manufacturer / name / grade | `Magnetics` / `High Flux` / `60` |
| Revision ID | `2271f4f7644f` |
| Record status | `imported` |
| B-H series | `bh-25c`, 25 °C, no DC bias, source units Oe / T |
| B-H point count | 501 |
| Loss frequencies | 50 000 Hz (502 points) and 100 000 Hz (550 points), both 25 °C, 0 A/m DC bias |
| Steinmetz `k` | 28.766524299 |
| Steinmetz `alpha` | 1.311 |
| Steinmetz `beta` | 2.218 |
| RMS relative residual | 0.0 |
| Max relative residual | 0.0 |
| Relative permeability handed to solvers | 43.484830259 |
| Core used | `C058071A2` (reviewed catalog record, same physical size as the earlier `0077071A7` sample) |

The residuals are zero to nine decimal places across all 1052 loss samples
because the published Magnetics loss curves are themselves power-law curves.
The fit consumes every sample and computes true relative residuals, so this is
an exact fit rather than a degenerate one.

## Versions

| Component | Version |
| --- | --- |
| Application commit under test | `fb27600` plus the uncommitted `.gitattributes` fix described above |
| Python | 3.13.14 |
| PyAEDT | 1.2.0 |
| AEDT | 2025.2.0 Commercial (`ansysedt.exe` file version 2025.2.0.1) |
| pyfemm | 0.1.3 |
| FEMM | 4.2 (`.fem` `[Format] = 4.0`) |
| openpyxl | 3.1.5 |

## Preflight

`python -m tools.reproduce_material --grade 60 --revision 2271f4f7644f` printed
exactly `MATCH` and exited 0. `tools.prepare_material_handoff` reported `MATCH`
and wrote the pinned project plus `preflight.json`.

Recorded preflight values: `bhPointCount` 501, `bhSeriesId` `bh-25c`,
`lossFrequenciesHz` `[50000.0, 100000.0]`, `corePartNumber` `C058071A2`,
`materialRevision` `2271f4f7644f`, `supportedEnvironment` 2025.2 commercial.

## AEDT results

`tools\run_m5a_material_validation.ps1 -Revision 2271f4f7644f` ran both tagged
handoff tests: `2 passed, 1 warning in 69.07s`. The only warning is an upstream
`defusedxml.cElementTree` deprecation raised inside PyAEDT.

All fifteen adapter stages succeeded: launch, units, materials, core, windings,
terminals, excitations, eddy, region, mesh, setup, matrix, reports, validate,
save. Notable stage messages:

- `Material Magnetics_High_Flux_60_r2271f4f7644f created (draft=False).`
- `Core Core revolved and assigned Magnetics_High_Flux_60_r2271f4f7644f.`
- `2 windings excited. DC applied to 2 windings.`
- `Design validation passed.`

Manual checks against the saved project file:

| Check | Result |
| --- | --- |
| Exactly one `.aedt` beneath the AEDT artifact directory | Pass — one file |
| Core object uses `Magnetics_High_Flux_60_r2271f4f7644f` | Pass — material defined and assigned |
| Nonlinear permeability enabled | Pass — `permeability` block carries `property_type='nonlinear'`, `HUnit='A_per_meter'`, `BUnit='tesla'` |
| B-H table contains exactly `bhPointCount` rows | Pass — `Points[1002: ...]` = 501 (B, H) pairs |
| First and last B-H values match the source after unit conversion | Pass — source `0.0, 0.0` and `500.0 Oe, 1.4167755953308534 T`; canonical `0.0, 0.0` and `39788.735772974 A/m, 1.416775595 T`; AEDT identical to canonical. 500 Oe × 79.5774715459 = 39788.735772974 A/m |
| Core-loss `cm`, `x`, `y` equal stored `k`, `alpha`, `beta` | Pass — `core_loss_cm='28.766524299...'`, `core_loss_x='1.311...'`, `core_loss_y='2.218'` |
| Design uses `AC Magnetic with DC` | Pass — solution type present in the saved project |
| Both winding `DC Current` values persist | Pass — two `DC Current'='5A'` properties |
| Design validation passes | Pass — `validate` stage reported `Design validation passed.` |
| Save, close, reopen produces no repair warning | **Open** — needs a GUI session; see [Outstanding](#outstanding) |

DC bias used the native strategy `native-include-dc-fields`, not an
approximation, justified by the reviewed capability record
(`includeDcFields3d: true`, evidence source `aedt-matrix:aedt-matrix.yml`).

## FEMM results

The FEMM handoff test compares every B-H point in the written `.fem` file
against the pinned record.

| Check | Result |
| --- | --- |
| Exactly one `.fem` beneath the FEMM artifact directory | Pass — one file |
| `Magnetics_High_Flux_60_r2271f4f7644f` assigned to the annulus | Pass |
| Nonlinear B-H curve present | Pass |
| Displayed B-H point count equals `bhPointCount` | Pass — 501 numeric B-H rows |
| Exact point comparison | Pass — first row `0 0`, last row `1.4167755950000001 39788.735772974003`, matching the canonical points |
| Saving and reopening retains the material | Pass — checked earlier in a FEMM session by Fabio Posser |

## Maxwell 2D handoff — gap found and closed

The evidence above originally covered Maxwell 3D and FEMM only. Maxwell 2D was
never exercised with this material: the handoff test used `export_maxwell3d`, the
pinned project is `dimensionMode: "3d"`, and the existing live 2D test uses the
generic sample fixture whose core material is a **linear** catalog permeability.
The plan's requirement table claims "Nonlinear B-H and core-loss model reach
AEDT" without qualifying the dimension, so that requirement was only half met.

`tests/integration/aedt/test_material_handoff_2d.py` now closes it and runs with
the other two from `tools/run_m5a_material_validation.ps1`:

```
test_material_handoff.py       PASSED
test_material_handoff_2d.py    PASSED
femm/test_material_handoff.py  PASSED
3 passed, 1 warning in 79.62s
```

Verified in the saved 2D project `M2_golden_sample_2d.aedt`: the material
`Magnetics_High_Flux_60_r2271f4f7644f` is present, its permeability block carries
`property_type='nonlinear'`, the B-H table holds `Points[1002: ...]` = 501 pairs,
the core-loss coefficients are present, and the initial-mesh slider is at 6.

## Final confirmation run against the accepted code

The controlled validation was re-run against the exporter as it now ships — 16
faceted conductors and the TAU mesh settings — so this evidence corresponds to
the shipping code rather than an earlier revision:

```
MATCH / MATCH
test_material_handoff.py       PASSED
test_material_handoff_2d.py    PASSED
femm/test_material_handoff.py  PASSED
3 passed, 1 warning in 93.81s
M5a live validation completed.
```

Verified in that run's saved 3D project: `XSectionNumSegments='16'`,
`MeshMethod='AnsoftTAU'`, curvilinear `Apply=false`, 501 B-H pairs, and
`DC Current='5A'` on both windings.

Repository gates: 714 non-solver tests passed, 36 UI tests passed, `ruff`,
`mypy src tools`, `tools/check_architecture.py` and `git diff --check` all exited
0, and the removed-support-path audits returned no matches outside historical
plan documents.

An earlier confirmation run, before the solve work, passed the then-two live
tests in 56.26s after the overlay-save retry fix (Task 7 Step 4).

## Artifacts

Written beneath the ignored `artifacts/material-validation/` tree, never
committed:

- `m5a-high-flux-60.inductor.json` — pinned project document
- `preflight.json` — reproduction and handoff evidence
- `live/aedt/M2_golden_sample.aedt` and `live/aedt/generation-manifest.json`
- `live/femm/M2_golden_sample_2d.fem` and `live/femm/femm-manifest.json`
- `live/aedt/catalog.sqlite`, `live/femm/catalog.sqlite`

## Solve status — resolved, and M5a is accepted

Everything above concerns the material **reaching** the solvers. That is
necessary but not sufficient: the exported design also has to solve, and
originally it did not. `AC Magnetic with DC` failed with
`Map linked data onto target mesh failed`, on curved surfaces. The cause was
never the material — Ansys' own nonlinear `steel_1008` failed identically on the
same geometry.

The shipping fix, verified solving by Fabio Posser on 2026-07-28 with adaptive
refinement at the shipped defaults, is two changes that are both required:

1. **16-sided conductors** — `CONDUCTOR_FACETS = 16`, with the coil terminal
   sheets faceted to the same count.
2. **TAU initial mesh settings with curvilinear meshing disabled** — slider 6,
   dynamic surface resolution off, flex meshing off.

Round wire with the mesh settings alone still fails, so neither half can be
dropped. Full investigation, including the dead ends, is in
[dc-bias-solve-limitation.md](dc-bias-solve-limitation.md).

The lesson worth keeping: `Design validation passed` is an AEDT consistency
check, not a solvability guarantee. M4 and M5a both treated it as sufficient,
which is how a non-solving export got this far unnoticed.

Accepted cost of the faceted conductor: an inscribed 16-gon carries 97.4% of the
copper of the round wire, so reported DC resistance runs about 2.7% high. Fabio
accepted that on 2026-07-28 in exchange for a solve that completes with full
adaptivity; 24 sides would cut it to 1.1%.

Two defects found while investigating remain open and did not block acceptance:

1. **Mass density is never exported.** The exporter writes permeability,
   conductivity and core loss only. Measured value for this material:
   130 g / 15 900 mm³ = **8176 kg/m³**. Agreed follow-up: carry density on the
   material record and make it a mandatory column in the Material Studio
   spreadsheet template. Making it mandatory invalidates revision
   `2271f4f7644f`, which has no density, so that revision must be re-imported
   and this document's pinned revision will change with it.
2. **PyAEDT writes malformed Steinmetz units.** `material.py:2937-2938`
   hardcodes `f"{cm}A_per_meter"` and `f"{x}tesla"`, so the saved project holds
   `core_loss_cm='28.766524299A_per_meter'` and `core_loss_x='1.311tesla'`.
   Ansys' own TDK library writes plain numbers. AEDT parses the magnitudes
   correctly and the solve is unaffected, but we should overwrite both
   properties after the call rather than ship wrong units.

## Outstanding human check

Open `live/aedt/M2_golden_sample.aedt` in the AEDT GUI, then save, close, and
reopen it and confirm no repair warning appears. Every other check above is a
concrete observation from this run.
