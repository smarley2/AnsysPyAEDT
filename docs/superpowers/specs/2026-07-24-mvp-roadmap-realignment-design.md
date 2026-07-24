# PyAEDT Inductor Designer — MVP Roadmap Realignment Design

- Status: Approved in collaborative design review
- Date: 2026-07-24
- Product surface: Standalone Windows application
- Supported AEDT target: AEDT 2025 R2 Commercial only
- First geometry family: Toroidal cores
- Domain vocabulary: [`CONTEXT.md`](../../../CONTEXT.md)
- Related decisions: [ADR 0004](../../adr/0004-standalone-windows-and-single-aedt-target.md),
  [ADR 0005](../../adr/0005-backend-independent-projects.md), and
  [ADR 0006](../../adr/0006-rms-project-current-and-peak-solver-excitation.md)

## 1. Purpose

This design realigns the remaining MVP roadmap after auditing the implemented
application. The solver-independent toroid geometry, Maxwell generation, FEMM
integration, material pipeline, and spreadsheet-only Material Studio exist,
but the Windows shell still loads one design at startup and leaves the `Core`,
`Windings`, `Simulation`, and `Review` steps empty.

The roadmap must therefore complete project authoring and simulation results
before packaging. This document supersedes conflicting product-surface,
support-matrix, project/run, AC-current, and delivery-sequence requirements in
the 2026-07-12 product design. Unchanged modularity, geometry, material
provenance, and testing requirements from that design remain in force.

## 2. Accepted baseline

- Milestone 4 is accepted.
- Milestone 4.5 is accepted for the implemented FEMM backend and MCP surface.
- Milestone 5a is implementation-complete but remains open for a legally usable
  real material, reproduction `MATCH`, and live AEDT/FEMM material handoff.
- Milestone 5b is accepted and closed for the spreadsheet-only Material Studio
  workflow. Its acceptance no longer depends on the remaining M5a live-solver
  evidence.

Existing MCP functionality is retained, but no MCP expansion, parity work, or
external-client validation belongs to the active MVP roadmap. New MCP work is a
future product decision after the Windows workflow is stable.

## 3. Product boundary

The product is a standalone Windows application that creates new inductor
designs, previews them, generates solver projects, optionally runs simulations,
and presents normalized results.

The editable source of truth is a shareable `*.inductor.json` Project document.
The application can create, open, save, reopen, and edit any compatible Project
document, regardless of its author or originating machine.

A generated `*.aedt` file is an independent output. A user may open it directly
in AEDT and make arbitrary changes, but the application does not import,
round-trip, compare, or synchronize those changes back into the Project
document.

The supported Ansys environment is exactly AEDT 2025 R2 Commercial. AEDT 2024
R2, Student editions, an embedded AEDT extension, and their associated
certification or fallback policies are removed from product scope.

The supported run backends are:

- Maxwell 3D, authoritative for angular placement and lead geometry;
- Maxwell 2D, an explicitly approximate cross-sectional equivalent; and
- FEMM 2D, an explicitly approximate cross-sectional equivalent.

Every generated model is complete. The Review step may display a Symmetry
Suggestion, but the application does not apply symmetry boundaries, sectors, or
multipliers.

## 4. Project and run model

One Project document contains three backend-independent concepts:

1. **Design** — core, dimensions, windings, conductors, materials, and geometry
   choices.
2. **Operating Point** — one global frequency plus each winding's AC RMS
   current, phase, and optional DC current.
3. **Simulation Recipe** — mesh intent, convergence intent, and requested
   outputs.

A **Run Request** is separate from the Project document's physical identity. It
selects Maxwell 3D, Maxwell 2D, or FEMM and chooses `Generate Only` or
`Generate and Solve`. The same Project document can be run through all three
backends without changing the Design.

The current `dimensionMode` project field is removed. Backend and dimensional
representation are run choices, not Design properties.

No user Project documents are in use, so this change intentionally introduces a
clean schema break. M6 updates repository fixtures and examples to the new
schema and does not add legacy migration code.

Each completed or failed run produces a **Run Manifest** recording:

- the source Project document identity and effective inputs;
- backend, dimensional representation, application version, solver version,
  and adapter version;
- effective AC RMS and peak currents;
- material identities or unresolved-material state;
- mesh, convergence, and requested-output intent;
- approximation and capability warnings;
- named stages, status, diagnostics, and generated artifacts; and
- result availability and extraction provenance.

## 5. AC and DC current conventions

The user interface and Project document use AC RMS current. The
solver-independent simulation plan performs the only input conversion:

```text
I_peak = I_rms * sqrt(2)
```

Maxwell Eddy Current and FEMM AC adapters receive peak complex amplitudes. They
must not repeat the conversion. The Run Manifest records both RMS and peak
values for every winding.

Winding phase is part of the Operating Point and must be honored by every
backend that claims multi-winding AC support. A backend may not silently ignore
phase. Unsupported phase behavior blocks the run or marks the requested result
unavailable with an actionable reason, according to whether continuing would
misrepresent the excitation.

DC current is distinct from AC RMS and peak values. Native DC-biased operation
is enabled only for a backend and analysis type that has been live-validated on
AEDT 2025 R2 Commercial. Unsupported DC bias is visible and blocked; no
approximate fallback is generated.

## 6. Core and material rules

The normal core path selects a traceable catalog record. A user may instead
define a Manual core because custom toroidal designs are part of the MVP.

A Manual core may be saved and previewed before a material is selected. Normal
generation and every solve require explicit material identities for all
physical objects.

One exception supports CAD handoff:

- the user chooses Maxwell 3D and `Generate Only`;
- the core material is unresolved;
- the application explains that the output is incomplete and requires explicit
  confirmation;
- the output contains only the 3D core and winding geometry;
- no excitations, setup, mesh, reports, or solve-ready claim are created; and
- the Run Manifest records an unresolved core material and
  `geometry-only/incomplete` status.

This exception does not apply to `Generate and Solve`, Maxwell 2D, or FEMM.

## 7. Guided Studio workflow

The completed M8 Windows application uses the established steps:

1. **New/Open Project** — create a blank Project document or open any compatible
   shared `*.inductor.json`.
2. **Core** — select a catalog core or edit Manual toroid dimensions.
3. **Windings** — add, edit, remove, and reorder windings; configure turns,
   conductor, material, placement, AC RMS current, phase, and DC current.
4. **Materials** — use the accepted spreadsheet-only Material Studio and pin
   exact material revisions and B-H series.
5. **Simulation** — edit the Operating Point and Simulation Recipe, select a
   backend for this run, and choose `Generate Only` or `Generate and Solve`.
6. **Review** — display the complete Design, Operating Point, backend,
   dimensional approximation, validation findings, unresolved data, requested
   outputs, and any Symmetry Suggestion.
7. **Run/Results** — show stage progress, support cancellation, and present or
   export the Normalized Result Set.

The preview is reactive: every valid geometry edit updates the same
solver-independent geometry model consumed by the solver adapters. M7 removes
the startup-only hardcoded Project document and all empty workflow pages.
M7 completes this workflow through `Generate Only`; M8 activates
`Generate and Solve` and the Results state.

Manual save is part of M7. Autosave, crash recovery, and application-wide
undo/redo are M9 reliability work.

## 8. Run execution and normalized results

One Run Request evaluates one Operating Point. Automatic frequency, current, or
parameter sweeps are outside the first release.

`Generate and Solve` is a staged application service shared by the UI and
future automation surfaces. It supports progress events, cooperative
cancellation between safe stages, durable status, and a final Run Manifest. A
partial artifact or interrupted analysis is never reported as successful.

The Normalized Result Set requests:

- resistance, inductance, and complex impedance per winding;
- resistance, inductance, impedance, or coupling matrices where the backend
  exposes them without reinterpretation;
- copper loss, core loss, and total loss;
- magnetic energy;
- convergence history, final convergence state, solver status, and diagnostics;
- magnetic flux density `B`; and
- current density `J` per winding.

For both `B` and `J`, the result contract includes:

- maximum magnitude at AC peak;
- Area-Weighted Mean magnitude at AC peak;
- maximum magnitude at AC RMS;
- Area-Weighted Mean magnitude at AC RMS.

The Area-Weighted Mean of a field magnitude `F` is:

```text
F_area_mean = integral_A(|F| dA) / A
```

In 2D, `A` is the evaluated core or conductor region. In 3D, `A` is a
Representative Cross Section. M8 must define a deterministic section-selection
algorithm before implementation, record every section in the Run Manifest,
report each section mean, and report the worst section mean. A volume average
does not satisfy this requirement.

For a sinusoidal AC component, RMS field values are derived from peak values
only when that relationship is physically valid for the extracted quantity and
solver solution. With DC bias, the result separates DC, AC peak, and AC RMS
components and reports a combined maximum only when the backend provides a
defensible value.

Every result carries backend, dimensional representation, unit, current
convention, approximation status, and availability. A quantity that cannot be
obtained without misrepresentation is `unavailable` with a reason. It is never
silently estimated or omitted.

The application exports the normalized result and its provenance as JSON and
tabular quantities as CSV.

## 9. Validation, errors, and recovery

Pre-run validation distinguishes:

- information and recommendations;
- warnings that allow generation and enter the Run Manifest;
- errors that block the selected operation; and
- backend capability or approximation findings.

Validation is operation-specific. For example, an unresolved core material is
an acknowledged warning for the Maxwell 3D geometry-only operation and an error
for every solve.

M8 reports the failed stage and preserves inputs, manifest state, solver logs,
and safe partial artifacts for diagnosis. M9 adds autosave, restart recovery,
undo/redo, interrupted-run recovery, and a redacted diagnostic bundle.

## 10. Revised milestones

### M5a — Live Validation Closeout

Scope:

- remove AEDT 2024 R2, Student, and magnetostatic-fallback product policies;
- retain only the AEDT 2025 R2 Commercial compatibility target;
- import a legally usable real material record;
- obtain reproduction `MATCH`;
- generate and inspect Maxwell 3D and FEMM artifacts using the exact pinned
  revision; and
- verify the material data consumed by both solvers.

Exit criterion: the real material reproduces with `MATCH`, its licensing and
redistribution handling are documented, and live AEDT 2025 R2 Commercial and
FEMM evidence confirms the pinned nonlinear data reaches each solver.

### M5b — Spreadsheet-Only Material Studio

Status: accepted and closed on 2026-07-23.

Its accepted scope is template download, CSV/XLSX import, immutable imported
revisions, one-click library loading, read-only plotting, workbook download,
replacement, guarded deletion, and explicit project pinning.

### M6 — Project Foundation

Scope:

- introduce the backend-independent Project document;
- introduce Design, Operating Point, Simulation Recipe, Run Request, Run
  Manifest, and Normalized Result Set contracts;
- remove fixed `dimensionMode`;
- replace ambiguous AC magnitude with explicit AC RMS current;
- convert RMS to peak exactly once in solver-independent planning;
- represent unresolved core material explicitly;
- define Maxwell 3D geometry-only generation;
- update fixtures and examples through a deliberate schema break; and
- expose shared application services without Qt or solver dependencies.

Exit criterion: one Project document round-trips deterministically and produces
validated run plans for Maxwell 3D, Maxwell 2D, and FEMM with identical physical
inputs, explicit RMS/peak evidence, and operation-specific material validation.

### M7 — Guided Studio

Scope:

- implement New/Open/Save for compatible shareable Project documents;
- implement functional Core, Windings, Materials, Simulation, and Review pages;
- support catalog and Manual toroidal cores;
- support complete winding authoring;
- make preview updates reactive;
- select a backend and execute `Generate Only` through the existing adapters;
- display validation, approximations, and Symmetry Suggestions; and
- remove the hardcoded startup Design.

Exit criterion: starting from an empty project, a user can author, save, reopen,
review, and `Generate Only` a valid toroidal Design for each backend. A
materialless Manual core can produce only the confirmed Maxwell 3D
Geometry-Only AEDT Project.

### M8 — Simulation and Results

Scope:

- execute Maxwell 3D, Maxwell 2D, and FEMM runs;
- activate `Generate and Solve` in the Guided Studio;
- provide progress, cancellation, durable run status, and failure diagnostics;
- honor multi-winding AC RMS current and phase;
- validate DC-biased behavior only where supported;
- extract and normalize the requested electrical, loss, energy, field, and
  convergence results;
- implement deterministic 3D Representative Cross Sections and direct 2D area
  integration;
- present result availability and approximation warnings; and
- export JSON and CSV.

Exit criterion: controlled end-to-end runs at one Operating Point produce
traceable Normalized Result Sets for all three backends, and every requested
quantity is either evidenced or explicitly unavailable.

### M9 — Reliability

Scope:

- autosave and crash recovery;
- undo/redo for project edits;
- interrupted-run recovery;
- actionable installation, license, material, file, and convergence errors;
- redacted logs and a diagnostic bundle; and
- robustness tests for cancellation, failed stages, and recovery.

Exit criterion: forced UI and solver failures preserve the last valid Project
document, never report a partial run as successful, and produce sufficient
redacted evidence for diagnosis.

### M10 — Windows Release

Scope:

- resolve packaged resources independently of the source checkout;
- build the Windows executable with PyInstaller;
- build the installer with Inno Setup;
- detect AEDT 2025 R2 Commercial and required optional solver installations;
- run clean-install smoke tests;
- publish release notes and checksums; and
- execute the controlled AEDT 2025 R2 Commercial release checklist.

Exit criterion: a clean Windows installation completes the authoring,
generation, optional solve, result export, save, and reopen workflow against the
single supported AEDT target.

### M11 — Additional Core Families

Scope: add approved non-toroidal core families as independent geometry
components after the toroidal Windows release is accepted.

Exit criterion: each family receives its own approved design, schema,
invariants, preview, solver mapping, fixtures, and live evidence without
weakening toroidal behavior.

## 11. Explicitly deferred work

The following items require a future approved specification and do not block
M5a–M11:

- MCP expansion or parity with the completed Windows workflow;
- an AEDT extension;
- AEDT 2024 R2 or Student support;
- reverse import, comparison, or synchronization of edited `*.aedt` files;
- automatic symmetry model generation;
- automatic sweeps;
- transient, thermal, mechanical, optimization, or converter co-simulation;
- non-round conductors; and
- cloud or collaborative remote services.

## 12. Verification strategy

- M5a uses the controlled real-material reproduction and live AEDT/FEMM
  procedures.
- M6 uses schema, domain, application-service, golden-manifest, and adapter
  contract tests without Qt or live solvers.
- M7 uses controller and QML workflow tests with recording adapters, plus a
  manual Windows interaction check.
- M8 uses unit tests for normalization and area calculations, adapter contract
  tests, failure/cancellation tests, and tagged live AEDT/FEMM integration
  tests.
- M9 uses deterministic crash, cancellation, recovery, and diagnostic-redaction
  scenarios.
- M10 uses a clean Windows virtual machine or controlled clean machine and the
  single-row AEDT 2025 R2 Commercial release checklist.
- M11 is planned and verified one core family at a time.

All milestones retain Ruff, strict mypy, architecture-boundary checks,
non-solver pytest coverage, repository-hygiene checks, and explicit live
evidence where a solver claim is made.

## 13. Planning rule

Detailed implementation plans are written one milestone at a time. M5a closes
before M6 acceptance, and each later milestone consumes only accepted contracts
from its predecessor. Packaging remains M10 and cannot absorb unfinished
authoring, simulation, result, or reliability work.
