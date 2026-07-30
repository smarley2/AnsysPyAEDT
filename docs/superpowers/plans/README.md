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
- Milestone 6, Project Foundation, is **accepted as of 2026-07-28**. Its
  [detailed implementation plan](2026-07-28-m6-project-foundation.md) records
  the implemented schema-v5 Project/Run contracts and exact acceptance
  evidence.
- **Milestone 7 is split into three plans**, because its approved specification
  covers three independently testable subsystems and one combined plan would
  gate a whole milestone behind a single review. Requirements are unchanged; only
  the delivery order is:
  - **M7a**, implementation complete on branch `m7a/preliminary-estimator`:
    [solver-independent preliminary estimator](2026-07-29-m7a-preliminary-estimator.md)
    — specification sections 5–8, no Qt and no solver. All eight tasks are
    implemented and reviewed. Exit criterion proven against the real shipped
    overlay revision `94e880a99b98` and core `C058071A2`: 876 non-solver tests
    pass, no live solver was required, and the estimator's import isolation is
    verified in a clean interpreter. Awaiting the final whole-branch review and
    Fabio Posser's acceptance.
  - **M7b**, next plan to write: project-local run artifacts implementing
    [ADR 0007](../../adr/0007-project-local-run-artifacts-and-solver-visibility.md)
    — `runs/<run-id>-<backend>/`, background generation by default, optional
    solver-window visibility, post-generation open actions.
  - **M7c**, not yet written: the Guided Studio flow — `Core & Material`,
    `Windings`, `Preliminary`, `Simulation`, `Review`, bidirectional
    core/material filtering, numeric validators, and the separate Material
    Studio window.

  Plan-level decisions taken with Fabio Posser on 2026-07-29: run identifiers are
  UTC timestamps (`YYYYMMDD-HHMMSS`, numeric suffix on collision) so `runs/`
  sorts chronologically; diagnostic codes are lowercase dotted
  `<quantity>.<reason>` strings; a B-H or loss series supports a requested
  temperature only on exact equality, and a mismatch names the recorded
  temperatures so the user can pick one that exists.

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
| 6 | Project Foundation | [2026-07-28-m6-project-foundation.md](2026-07-28-m6-project-foundation.md) | Accepted schema-v5 Project round trip; identical effective inputs and golden Run Manifests for Maxwell 3D, Maxwell 2D, and FEMM |

Historical plans retain the decisions and evidence valid when they were
executed. They do not override the current support and product scope.

## Remaining milestone sequence

| Order | Milestone | Entry condition | Exit evidence |
| --- | --- | --- | --- |
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
5. A clean handoff naming the next detailed-plan task.

## M6 acceptance evidence

Implementation and review commits are:

`e26315c`, `0946fca`, `560732c`, `5194cab`, `3e0a682`, `b709909`,
`c8c61c0`, `86a9f67`, `79e982f`, `24ca082`, `63b50d6`, `c5c158b`, and
`ed62bda`. The Task 9 acceptance record is `6891dfb`
(`docs: accept m6 project foundation`). Its review-round-1 follow-up uses
message `test: strengthen m6 acceptance evidence`; that commit's exact hash is
recorded in the Task 9 handoff report because a commit cannot contain its own
hash.

The clean-process gate ran these exact commands:

```bash
.venv/bin/python -m ruff check .
.venv/bin/python -m mypy src tools
.venv/bin/python -m tools.check_architecture
QT_QPA_PLATFORM=offscreen QSG_RHI_BACKEND=software \
  .venv/bin/python -m pytest -m "not aedt and not femm" \
  --cov=inductor_designer --cov-report=term-missing
git diff --check
.venv/bin/python -m pytest tests/integration/test_project_round_trip.py -q
```

The review-round-1 final gate reported Ruff clean, strict mypy clean across 102
source files, architecture and diff checks clean, 801 passed and 7 deselected
in 9.96 seconds, and 86.55% total coverage (87% in the rounded table). The
explicit M6 integration file passed 2 tests in 0.23 seconds. It matches the
three golden Run Manifests byte-for-byte after a byte-identical v5
save/load/save, verifies that every native plan consumes the shared operating
point and selected material data, and proves a Manual core/material pair
persists and validates with its acknowledgment set to true. Controlled
mutations of the Maxwell 3D native current to 99 A and of the persisted Manual
acknowledgment to false both made the relevant acceptance test fail before the
normal green run.

The physical/compatibility audit found no changes to catalog or material source
data, B-H/core-loss series, the accepted 16-facet conductor, AnsoftTAU initial
mesh method, slider level 6, region padding, or mesh-length formulas. The sole
RMS-to-peak conversion remains in solver-independent run contracts; no solver
adapter performs it. AEDT support remains exactly 2025 R2 Commercial. Both 2D
golden manifests retain the explicit equivalent-cross-section warning, and the
Geometry-Only adapter has no solve-ready stages.

The final review fix wave closed six additional evidence gaps:

- FEMM now applies the planned AC peak magnitude and phase as one complex
  circuit-current phasor at its adapter boundary;
- returned failed Maxwell stages and missing, extra, or out-of-order stage
  sequences raise `RunGenerationFailed` with the failed manifest intact;
- `WARNING` validation findings enter planned-run and manifest warnings while
  `INFO` findings do not;
- confirmed unresolved-material Geometry-Only records effective stored inputs
  without a solve-ready DC-capability gate;
- v5 validation/load rejects every nonfinite numeric value with an exact
  document path and save uses `allow_nan=False`; and
- direct Maxwell result consumers must supply the exact expected 3D, 2D, or
  Geometry-Only stage sequence when evaluating success.

The final review gate selected 821 non-live tests: all 821 passed, 7 live tests
were deselected, 76 existing warnings remained, and total coverage was 86.66%
(87% rounded). The first full run observed the existing Material Studio
reflow timing test before its binding settled; that test passed immediately in
isolation and the fresh complete rerun passed. Ruff, strict mypy across 102
source files, architecture, stale-symbol, one-conversion, and diff checks were
clean. The fix wave uses conventional commit message
`fix: close m6 final review findings`; its exact hash is recorded in the
out-of-commit handoff.

Unresolved risks:

- The final gate emitted 76 existing Python `ResourceWarning`s, primarily for
  SQLite connections (the initial pre-change baseline emitted 82). They do not
  fail the gate but remain cleanup work.
- M6 adds no live-solver claim and did not repeat the accepted M5a live AEDT or
  FEMM runs. The complex FEMM call is covered through the real adapter against
  the protocol fake and matches the official FEMM/pyFEMM complex-argument
  contract, but the seven live tests remain deselected.
- Generate and Solve remains intentionally blocked until M8; M6 defines its
  request/result contracts but does not execute or populate results.

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
exclusions, validation, and acceptance criteria.
[ADR 0007](../../adr/0007-project-local-run-artifacts-and-solver-visibility.md)
additionally fixes project-local run storage and solver-window behavior. The
detailed M7 implementation plan will be written separately before M7
implementation so it targets the stable M6 contracts and both approved
decisions. Do not repeat discovery or redesign unless implementation exposes a
documented contradiction.
