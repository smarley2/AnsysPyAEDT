# Maxwell 2D generation procedure

The M6 application service generates a documented approximate Maxwell 2D
cross-sectional AEDT project from a backend-independent schema-v5 Project
document and a Maxwell 2D Generate Only Run Request. Generation runs as named
stages; the Run Manifest records effective inputs, assumptions, every stage,
and artifacts. A partial design is never reported as successful.

## Prerequisites

- Controlled Windows machine with a licensed AEDT installation (2025 R2
  Commercial is the accepted row).
- `pip install -e ".[dev,aedt]"` in the project venv.

## Procedure

1. Run the controlled runner (graphical first, per compatibility policy):

   ```powershell
   .\tools\run_aedt_maxwell2d.ps1 -Release 2025.2 -Edition commercial -Graphical
   ```

2. Review `artifacts\maxwell2d\2025.2-commercial\generation-manifest.json`.
   The file contains the shared Run Manifest: `status` is `succeeded`, `backend`
   is `maxwell-2d`, `mode` is `generate-only`,
   `dimensionalRepresentation` is `equivalent-cross-section`, every stage has
   status `succeeded`, and the approximation warning is present. Confirm the
   shared frequency and temperatures, both RMS and peak winding currents, exact
   material revision/B-H series, recipe, solver/adapter versions, and AEDT
   artifact.
3. Open the generated `.aedt` in AEDT. Confirm:
   - An annular core (outer circle minus bore) in the XY plane.
   - Two conductor circles per turn (go and return), sized from the bare
     conductor diameter.
   - Coils assigned per conductor circle, grouped into one winding per
     definition with go/return polarity opposite within the pair.
   - Model depth equals the core height.
   - Air region with the standard padding and a balloon boundary assigned on
     the region edges (Maxwell 2D AC Magnetic requires an explicit outer
     boundary; the region alone does not satisfy validation), length-based
     mesh operations on conductors and core.
   - `Setup1` (Eddy Current) at the shared Operating Point frequency, `Matrix1`
     over all windings, and the requested report definitions.
   - Design validation (checkmark button) passes.
4. Optionally run the marked integration test on the same machine:

   ```powershell
   $env:INDUCTOR_AEDT_RELEASE = "2025.2"
   $env:INDUCTOR_AEDT_EDITION = "commercial"
   .venv\Scripts\python.exe -m pytest tests/integration/aedt/test_maxwell2d_export.py -v
   ```

## Current scope notes

- The 2D model is a documented approximate XY cross-section equivalent, not a
  reproduction of the 3D toroid: no angular bends, local wire spacing, lead
  routing, or three-dimensional leakage/proximity effects (design spec §6.4).
  The Run Manifest and Guided Studio summary label the result approximate.
- Normal generation requires one exact imported/approved material revision and
  its selected B-H series. Unresolved material is blocked for Maxwell 2D; no
  scalar-permeability or compatibility fallback is generated.
- Nonzero DC operating current is blocked in Maxwell 2D regardless of
  capability matrix state; see `docs/development/dc-bias-compatibility.md`.
- Project/UI current is AC RMS. Solver-independent run planning records it and
  converts it once to the AC peak amplitude consumed unchanged by the adapter.
- Exact PyAEDT calls were corrected through live AEDT 2025 R2 Commercial
  verification. The adapter uses `create_region` for the 2D air region, assigns
  an explicit balloon boundary, sets `model_depth` after geometry exists, and
  mirrors the verified calls in recording fakes and `aedt`-marked tests.
