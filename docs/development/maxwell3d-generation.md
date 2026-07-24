# Maxwell 3D generation procedure

Milestone 3 generates a ready-to-solve Maxwell 3D project from an inductor
project file. Generation runs as named stages; the generation manifest
(`generation-manifest.json`) records every stage, and a partial design is
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

2. Review `artifacts\maxwell3d\2025.2-commercial\generation-manifest.json`:
   every stage `succeeded: true`, `succeeded: true` at top level.
3. Open the generated `.aedt` in AEDT. Confirm: core + turn solids present,
   one coil terminal per turn, windings grouped, material assigned, region,
   mesh operations, `Setup1` (Eddy Current) at the project frequency,
   `Matrix1`, report definitions. Validation (checkmark button) passes.
4. Optionally run the marked integration test on the same machine:

   ```powershell
   $env:INDUCTOR_AEDT_RELEASE = "2025.2"
   $env:INDUCTOR_AEDT_EDITION = "commercial"
   .venv\Scripts\python.exe -m pytest tests/integration/aedt/test_maxwell3d_export.py -v
   ```

## Milestone 3 scope notes

- Core material is a linear draft model derived from the powder grade
  (relative permeability = grade, conductivity 0). Real material records
  arrive with Material Studio (Milestone 5). Ferrite cores refuse to export.
- DC operating currents are recorded in the manifest and, as of Milestone 4,
  applied natively (via the `AC Magnetic with DC` solution type) when the
  reviewed capability matrix confirms native DC support; see
  `docs/development/dc-bias-compatibility.md` for the single-target decision
  table and unsupported-case behavior.
- Full model only; symmetry stays data-level (Milestone 2 plan output).
- Exact PyAEDT keyword names were verified against the installed pyaedt by
  the AEDT integration test; the recording fakes mirror the adapter's calls.
