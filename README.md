# PyAEDT Inductor Designer

PyAEDT Inductor Designer is a standalone Windows application for creating
parametric toroidal-inductor models, previewing their geometry, and generating
models for Ansys Maxwell 2D/3D through PyAEDT or for FEMM 2D.

This is an independent open-source project. It is not affiliated with,
endorsed by, or sponsored by Ansys, Inc. Ansys, Maxwell, and AEDT are
trademarks of their respective owners.

The first release is intentionally narrow: commercial and manual toroidal
cores, round-wire windings, spreadsheet-sourced magnetic materials, and AEDT
2025 R2 Commercial. Maxwell 3D is authoritative for angular placement and lead
geometry; Maxwell 2D and FEMM are explicitly approximate cross-sectional
equivalents.

## Project status

The repository is an active pre-release implementation, not a packaged end-user
release.

| Area | Current state |
| --- | --- |
| Foundation through solver generation (M0–M4.5) | Accepted. This includes deterministic toroid geometry and preview, live-verified Maxwell 3D/2D generation on AEDT 2025 R2 Commercial, native validated 3D DC bias, FEMM 2D generation/solve, and the existing nine-tool MCP surface. |
| Spreadsheet-only Material Studio (M5b) | Accepted. CSV/XLSX import, immutable local revisions, plotting, download, replacement/deletion guards, and exact project pinning are implemented. |
| Live material closeout (M5a) | Still open. A redistributable High Flux 60 validation record, fresh reproduction `MATCH`, and FEMM inspection exist; live AEDT material inspection, sanitized evidence, and the final quality gates still prevent acceptance. |
| Guided Studio UI | A Canvas First shell and a tested editable-winding slice are integrated. Valid edits rebuild the real solver-independent preview and can be saved. Core selection, complete project authoring, preliminary estimates, review, and non-hardcoded New/Open/Save are still M7 work. |
| Project and run contracts (M6) | Approved but not implemented. The current schema is replaced in M6 by the backend-independent Project/Run model described below. |
| Simulation results, reliability, and packaging (M8–M10) | Planned. Normalized results, run recovery, autosave/undo, installer creation, and clean-machine release validation are not complete. |

Exact acceptance dates, evidence, and open gates are maintained in the
[development roadmap](docs/development/ROADMAP.md) and
[implementation-plan index](docs/superpowers/plans/README.md).

## Accepted product decisions

- The product UI is a standalone Windows application. An AEDT extension and
  edited-`*.aedt` round-trip are outside the active roadmap.
- AEDT 2025 R2 Commercial is the only supported Ansys target. AEDT 2024 R2 and
  Student editions are not support claims.
- Maxwell 3D, Maxwell 2D, and FEMM are selected per run. Generated solver files
  are independent outputs; the editable source of truth remains a shareable
  `*.inductor.json` Project document.
- The approved M6 Project model separates a backend-independent Design,
  Operating Point, and Simulation Recipe from the Run Request, Run Manifest,
  and Normalized Result Set. This is target architecture until M6 replaces the
  current schema.
- User-facing and persisted AC current will be RMS. Solver-independent planning
  will convert it to peak exactly once for Maxwell and FEMM. The current schema
  retains its older field until M6 performs the deliberate clean break.
- Material Studio is spreadsheet-only. Material records preserve provenance,
  immutable revisions, exact B-H-series selection, and explicit project
  pinning.
- Full models are generated. Symmetry is informational only, and unsupported
  capabilities are blocked or reported as unavailable rather than replaced by
  invented fallbacks.
- Toroids and round wire define the first release. Other core families and
  conductor shapes require separate designs and validation.

The decisions are recorded in
[ADR 0004](docs/adr/0004-standalone-windows-and-single-aedt-target.md),
[ADR 0005](docs/adr/0005-backend-independent-projects.md), and
[ADR 0006](docs/adr/0006-rms-project-current-and-peak-solver-excitation.md).

## Architecture

The code follows dependency inversion. Solver-independent packages define the
model and interfaces; UI, persistence, and solver integrations adapt those
interfaces at the repository boundary.

```text
Windows UI · CLI · optional MCP
              |
      application services
              |
   domain · geometry · materials · simulation
              ^
              |
PyAEDT · FEMM · preview · persistence · catalog adapters
```

- `domain` owns units, core and winding definitions, project data, and
  validation rules.
- `geometry` owns deterministic toroid construction, winding packing,
  collision checks, tessellation, and the 2D equivalent.
- `materials` owns identities, provenance, curve records, fitting, replay, and
  physical validation.
- `simulation` owns solver-independent Maxwell/FEMM plans, capability
  decisions, and simulation recipes.
- `application` coordinates validation, preview, persistence, generation, and
  material workflows through ports.
- `adapters` contain PyAEDT, FEMM, catalog, compatibility, material, and
  persistence integration.
- `ui` contains the PySide6/QML Guided Studio. `mcp_server` and CLI tools are
  optional automation surfaces over the same application services, not
  separate domain models.

The dependency boundary is enforced by tests: `domain`, `geometry`,
`materials`, and solver-independent simulation code may not import PyAEDT, Qt,
SQLite, or operating-system APIs. Preview and solver export consume the same
geometry model, PyAEDT objects never enter the domain, catalog changes never
silently mutate a saved project, and unsupported results remain explicit.

See the [architecture boundaries](docs/architecture/README.md), the
[approved MVP realignment](docs/superpowers/specs/2026-07-24-mvp-roadmap-realignment-design.md),
and the [domain vocabulary](CONTEXT.md) for the authoritative details.

## Roadmap

The active delivery sequence is:

1. close M5a live material validation;
2. implement the M6 backend-independent Project and run contracts;
3. complete M7 Guided Studio authoring and traceable preliminary B, J,
   resistance, wire-loss, and supported core-loss estimates;
4. add M8 execution and normalized results;
5. add M9 reliability and recovery;
6. package and validate the Windows release in M10; and
7. add independently designed core families only after the toroidal release.

The M7 calculation rules and exclusions are already approved in the
[preliminary calculations and Guided flow design](docs/superpowers/specs/2026-07-26-preliminary-calculations-and-guided-flow-design.md).

## Material workflow

- [Material records procedure](docs/development/material-records.md)
- [CSV import template](src/inductor_designer/resources/material_templates/material-import-template.csv)
- [Excel import template](src/inductor_designer/resources/material_templates/material-import-template.xlsx)
- [Maxwell 3D generation procedure](docs/development/maxwell3d-generation.md)
- [Maxwell 2D generation procedure](docs/development/maxwell2d-generation.md)
- [MCP and FEMM automation](docs/development/automation-mcp-femm.md)
- [Validation plan](docs/development/VALIDATION_PLAN.md)

## Documentation language

Code, documentation, UI text, schemas, logs, commits, and GitHub content are
written in English. The UI is localization-ready, but the MVP ships with
English text only.

## License strategy

Original project code is licensed under the Apache License 2.0. Third-party
catalogs and data remain subject to their original terms. GPL-licensed material
data is not bundled with the application; any future importer must preserve
attribution and licensing metadata.
