# Maxwell 2D generation procedure

Milestone 4 generates a documented approximate Maxwell 2D cross-sectional
project from an inductor project file. Generation runs as named stages; the
generation manifest (`generation-manifest.json`) records every stage, and a
partial design is never reported as successful.

## Prerequisites

- Controlled Windows machine with a licensed AEDT installation (2025 R2
  Commercial is the accepted row).
- `pip install -e ".[dev,aedt]"` in the project venv.

## Procedure

1. Run the controlled runner (graphical first, per compatibility policy):

   ```powershell
   .\tools\run_aedt_maxwell2d.ps1 -Release 2025.2 -Edition commercial -Graphical
   ```

2. Review `artifacts\maxwell2d\2025.2-commercial\generation-manifest.json`:
   every stage `succeeded: true`, `succeeded: true` at top level, `dimension`
   is `2d`, and the `dcBias` block reports `blocked` (DC bias is not generated
   in 2D — see `dc-bias-compatibility.md`).
3. Open the generated `.aedt` in AEDT. Confirm:
   - An annular core (outer circle minus bore) in the XY plane.
   - Two conductor circles per turn (go and return), sized from the bare
     conductor diameter.
   - Coils assigned per conductor circle, grouped into one winding per
     definition with go/return polarity opposite within the pair.
   - Model depth equals the core height.
   - Air region with the standard padding, length-based mesh operations on
     conductors and core.
   - `Setup1` (Eddy Current) at the project frequency, `Matrix1` over all
     windings, resistance/inductance report definitions.
   - Design validation (checkmark button) passes.
4. Optionally run the marked integration test on the same machine:

   ```powershell
   $env:INDUCTOR_AEDT_RELEASE = "2025.2"
   $env:INDUCTOR_AEDT_EDITION = "commercial"
   .venv\Scripts\python.exe -m pytest tests/integration/aedt/test_maxwell2d_export.py -v
   ```

## Milestone 4 scope notes

- The 2D model is a documented approximate XY cross-section equivalent, not a
  reproduction of the 3D toroid: no angular bends, local wire spacing, lead
  routing, or three-dimensional leakage/proximity effects (design spec §6.4).
  The generation manifest and Guided Studio summary label the result
  approximate.
- Core material is the same linear draft model used in 3D (relative
  permeability = grade, conductivity 0). Ferrite cores refuse export.
- DC operating-point generation is blocked in 2D regardless of capability
  matrix state; see `docs/development/dc-bias-compatibility.md`.
- Exact PyAEDT keyword names (`create_circle(origin=...)`, the 4-argument
  `create_air_region`, `model_depth` as a unit string, `MatrixACMagnetic` on
  Maxwell2d) are best-effort until verified against the installed pyaedt by
  the `aedt`-marked integration test; the recording fakes mirror the
  adapter's calls.
