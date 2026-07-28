# Maxwell 3D generation procedure

The M6 application service generates a ready-to-solve Maxwell 3D AEDT project
from a backend-independent schema-v5 Project document and a Maxwell 3D Generate
Only Run Request. Generation runs as named stages; the Run Manifest records
effective inputs, assumptions, every stage, and artifacts. A partial design is
never reported as successful.

## Prerequisites

- Controlled Windows machine with a licensed AEDT installation (2025 R2
  Commercial is the accepted row).
- `pip install -e ".[dev,aedt]"` in the project venv.

## Procedure

1. Run the controlled runner (graphical first, per compatibility policy):

   ```powershell
   .\tools\run_aedt_maxwell3d.ps1 -Release 2025.2 -Edition commercial -Graphical
   ```

2. Review `artifacts\maxwell3d\2025.2-commercial\generation-manifest.json`.
   The file contains the shared Run Manifest: `status` is `succeeded`, `backend`
   is `maxwell-3d`, `mode` is `generate-only`,
   `dimensionalRepresentation` is `three-dimensional`, and every stage has
   status `succeeded`. Confirm the shared frequency and temperatures, both RMS
   and peak winding currents, exact material revision/B-H series, recipe,
   solver/adapter versions, and AEDT artifact.
3. Open the generated `.aedt` in AEDT. Confirm: core + turn solids present,
   one coil terminal per turn, windings grouped, material assigned, region,
   mesh operations, `Setup1` (Eddy Current) at the shared Operating Point frequency,
   `Matrix1`, report definitions. Validation (checkmark button) passes.
4. Optionally run the marked integration test on the same machine:

   ```powershell
   $env:INDUCTOR_AEDT_RELEASE = "2025.2"
   $env:INDUCTOR_AEDT_EDITION = "commercial"
   .venv\Scripts\python.exe -m pytest tests/integration/aedt/test_maxwell3d_export.py -v
   ```

## Current scope notes

- Normal generation requires one exact imported/approved material revision and
  its selected B-H series. No scalar-permeability or compatibility fallback is
  generated.
- The only unresolved-material operation is a separately confirmed Maxwell 3D
  Geometry-Only Generate Only request. Its distinct plan and adapter path
  create only core/winding geometry and save the AEDT project; they do not
  create material assignments, terminals, excitations, region, mesh, setup,
  matrix, reports, validation, results, or a solve-ready claim.
- Geometry-Only still records the effective stored Operating Point inputs in
  its Run Manifest. Nonzero stored DC does not require native DC capability for
  this operation because the adapter creates no excitation, setup, or solve.
- Project/UI current is AC RMS. Solver-independent run planning records it and
  converts it once to the AC peak amplitude consumed unchanged by the adapter.
- DC operating currents are recorded in the manifest and, as of Milestone 4,
  applied natively (via the `AC Magnetic with DC` solution type) when the
  reviewed capability matrix confirms native DC support; see
  `docs/development/dc-bias-compatibility.md` for the single-target decision
  table and unsupported-case behavior.
- Full model only; symmetry stays data-level (Milestone 2 plan output).
- The accepted solve configuration remains 16-sided conductors with the
  AnsoftTAU initial mesh at slider level 6, curvilinear meshing disabled, 100%
  region padding, and the established conductor/core length formulas.
- Exact PyAEDT keyword names were verified against the installed pyaedt by
  the AEDT integration test; the recording fakes mirror the adapter's calls.
