# Implementation Plan Index

This directory is the execution index for the approved
[MVP roadmap realignment](../specs/2026-07-24-mvp-roadmap-realignment-design.md).
The original
[product and architecture design](../specs/2026-07-12-pyaedt-inductor-application-design.md)
remains authoritative only where the realignment does not supersede it.

Implementation plans are written one milestone at a time. Each milestone must
finish with working, independently testable software and accepted interfaces
before the next plan freezes assumptions that depend on it.

## Current status

- Milestones 0–4.5 are accepted with the dates and exact live-verification
  scope recorded in the [roadmap](../../development/ROADMAP.md).
- Milestone 5a is **accepted as of 2026-07-28**. Validation revision
  `94e880a99b98` reproduces as `MATCH` and reaches AEDT 2025 R2 Commercial in
  Maxwell 3D and Maxwell 2D and FEMM 4.2 with its 501-point nonlinear B-H curve
  and Steinmetz coefficients, and the 3D design solves. Evidence is in
  [m5a-live-material-validation.md](../../development/m5a-live-material-validation.md);
  the solve fix is in
  [dc-bias-solve-limitation.md](../../development/dc-bias-solve-limitation.md).
- Milestone 5b is accepted and closed as of 2026-07-23 for the spreadsheet-only
  Material Studio workflow.
- **Milestone 6, Project Foundation, is next.** It has no detailed plan yet; the
  next worker must write one from the approved roadmap realignment before
  changing any schema or runtime contract.

The only supported AEDT target is AEDT 2025 R2 Commercial. The Windows
application is the only product UI. Existing MCP functionality from M4.5
remains in the repository, but MCP expansion or parity is future work and does
not gate the active roadmap.

## Completed and historical plans

| Order | Milestone | Detailed plan | Accepted evidence |
| --- | --- | --- | --- |
| 0 | Foundation and compatibility spike | [2026-07-13-foundation-compatibility-spike.md](2026-07-13-foundation-compatibility-spike.md) | Non-AEDT CI and controlled AEDT 2025 R2 Commercial spike |
| 1 | Toroid domain and catalogs | [2026-07-13-toroid-domain-and-catalogs.md](2026-07-13-toroid-domain-and-catalogs.md) | Versioned project round trip with reviewed commercial core and multiple windings |
| 2 | Geometry and live preview | [2026-07-14-geometry-and-live-preview.md](2026-07-14-geometry-and-live-preview.md) | Deterministic toroid/winding geometry, property tests, golden manifest, and reviewed preview |
| 3 | Maxwell 3D MVP | [2026-07-16-maxwell3d-mvp.md](2026-07-16-maxwell3d-mvp.md) | AEDT 2025 R2 Commercial opens a generated ready-to-solve Maxwell 3D project |
| 4 | Maxwell 2D and DC operating point | [2026-07-16-maxwell2d-dc-compat.md](2026-07-16-maxwell2d-dc-compat.md) | Live Maxwell 2D/3D evidence and explicit native/blocked DC behavior |
| 4.5 | MCP server and FEMM 2D backend | [2026-07-17-automation-mcp-femm.md](2026-07-17-automation-mcp-femm.md) | Accepted FEMM 2D generation/solve and the implemented nine-tool MCP surface |
| 5a | Material records pipeline and solver export | [2026-07-17-material-records-pipeline.md](2026-07-17-material-records-pipeline.md) | Accepted 2026-07-28: revision `94e880a99b98` reports `MATCH` and reaches Maxwell 3D, Maxwell 2D and FEMM, and the 3D design solves |
| 5b | Spreadsheet-only Material Studio | [2026-07-20-material-studio-spreadsheet-only.md](2026-07-20-material-studio-spreadsheet-only.md), [read-only revision](2026-07-23-material-studio-readonly-imported.md), [streamlined library](2026-07-23-streamlined-material-library.md) | Accepted CSV/XLSX import, immutable library, plotting, download, replacement/deletion, and project pinning |
| 5b history | Superseded manual Material Studio UI | [2026-07-19-material-studio-ui.md](2026-07-19-material-studio-ui.md) | Historical record only; image/PDF and UI-editing instructions do not describe the product |

Historical plans retain the decisions and evidence valid when they were
executed. They do not override the current support and product scope.

## Remaining milestone sequence

| Order | Milestone | Entry condition | Exit evidence |
| --- | --- | --- | --- |
| 5a closeout | [Live material validation and support cleanup](2026-07-24-m5a-live-validation-closeout.md) | Approved roadmap realignment | Real-material `MATCH`; live AEDT 2025 R2 Commercial and FEMM handoff; 2024/Student/fallback product policies removed |
| 6 | Project Foundation | M5a accepted | One backend-independent Project document round-trips shared frequency, winding/core temperatures, RMS currents, and exact core-material state, then creates validated Maxwell 3D, Maxwell 2D, and FEMM run plans |
| 7 | Guided Studio and Preliminary Estimates | M6 contracts accepted | A user authors, saves, reopens, inspects analytical B/J/wire/core-loss estimates or explicit unavailable reasons, reviews, and generates a non-hardcoded toroidal Design from the Windows UI |
| 8 | Simulation and Results | M7 generation workflow accepted | All three backends run one Operating Point and return traceable normalized results or explicit unavailable reasons |
| 9 | Reliability | M8 run/result contracts accepted | Autosave, recovery, undo/redo, cancellation recovery, and redacted diagnostics survive forced failures |
| 10 | Windows Release | M9 reliability accepted | A clean Windows install completes the workflow against AEDT 2025 R2 Commercial and publishes release notes/checksums |
| 11 | Additional Core Families | Toroidal Windows release accepted | Each approved family has an independent design, schema, invariants, preview, solver mapping, fixtures, and live evidence |

## Execution rule

Only one detailed milestone plan is active at a time. Every completed milestone
closes with:

1. Exact automated and controlled-solver test results.
2. Accepted public interfaces and schema versions.
3. Documented physical assumptions, compatibility findings, and unresolved
   risks.
4. A clean Git commit and handoff.
5. The detailed plan for the next milestone.

## Approved specification coverage

| Specification area | Delivery milestone |
| --- | --- |
| Real material reproduction and live AEDT/FEMM consumption; single supported AEDT target cleanup | 5a closeout |
| Backend-independent Design/Operating Point/Simulation Recipe; shared frequency and temperatures; exact core-material pin; per-run backend; explicit RMS/peak; manifests/results contracts | 6 |
| Approved Core & Material/Windings/Preliminary/Simulation/Review UI; separate Material Studio; analytical estimates; shareable project lifecycle; reactive preview; generation | 7 |
| Solver execution; progress/cancellation; R/L/Z, losses, energy, B/J maximum and area mean, convergence, JSON/CSV | 8 |
| Autosave, recovery, undo/redo, interrupted-run handling, actionable diagnostics | 9 |
| Resource discovery, PyInstaller, Inno Setup, clean-install and AEDT 2025 R2 Commercial release validation | 10 |
| Independently implemented non-toroidal core families | 11 |

AEDT 2024 R2, Student editions, an AEDT extension, edited-`*.aedt` round-trip,
automatic symmetry, automatic sweeps, MCP expansion, transient, thermal,
mechanical, optimization, converter co-simulation, cloud services, and
non-round conductors require a separately approved future specification.

## M7 scope lock

The approved
[preliminary calculations and Guided flow design](../specs/2026-07-26-preliminary-calculations-and-guided-flow-design.md)
fully records M7 product behavior, analytical formulas, physical constants,
exclusions, validation, and acceptance criteria. Write the detailed M7
implementation plan after M6 acceptance so it targets stable contracts. Do not
repeat discovery or redesign unless M6 exposes a documented contradiction.
