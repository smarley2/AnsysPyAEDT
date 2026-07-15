# Implementation Plan Index

This directory is the execution index for the approved [PyAEDT Inductor Designer product and architecture design](../specs/2026-07-12-pyaedt-inductor-application-design.md).

Implementation plans are deliberately written one milestone at a time. Each milestone must finish with working, independently testable software and verified interfaces before the next plan freezes assumptions that depend on it.

Milestone 0 status: **Accepted 2026-07-13**, scoped to the AEDT 2025 R2 Commercial release available on the development machine. The 2024 R2 and 2025 R2 Student rows stay `out-of-scope` until a later milestone targets them; see the [validation plan](../../development/VALIDATION_PLAN.md).

Milestone 1 status: **Accepted 2026-07-14**. Powder-core records reviewed against the 2025 Magnetics catalog; ferrite records stay `draft` until their catalog review. Milestone 2 is the active milestone.

Milestone 2 status: **Accepted 2026-07-15** (exit tests green; interactive preview reviewed; one-closed-loop-per-turn model confirmed). Milestone 3 planning is next.

| Order | Milestone | Detailed plan | Entry condition | Exit evidence |
| --- | --- | --- | --- | --- |
| 0 | Foundation and compatibility spike | [2026-07-13-foundation-compatibility-spike.md](2026-07-13-foundation-compatibility-spike.md) | Approved product design | Non-AEDT CI passes; controlled runs create and save trivial Maxwell 2D and 3D projects; capability results are recorded for the release matrix |
| 1 | Toroid domain and catalogs | [2026-07-13-toroid-domain-and-catalogs.md](2026-07-13-toroid-domain-and-catalogs.md) | Milestone 0 contracts accepted | Versioned project round trip with reviewed commercial core and multiple windings |
| 2 | Geometry and live preview | [2026-07-14-geometry-and-live-preview.md](2026-07-14-geometry-and-live-preview.md) | Project and catalog schemas accepted | Deterministic toroid/winding geometry passes property and golden-manifest tests |
| 3 | Maxwell 3D MVP | Written after Milestone 2 review | Geometry intermediate representation accepted | Supported AEDT installation opens a generated ready-to-solve Maxwell 3D project |
| 4 | Maxwell 2D and DC operating point | Written after Milestone 3 review | Maxwell 3D gateway and manifest accepted | Valid 2D equivalents and explicit native/fallback DC-bias decisions across the release matrix |
| 5 | Material Studio | Written after Milestone 4 review | Material interface and solver export requirements accepted | Traceable human-approved material revision can be reproduced and exported |
| 6 | Productization | Written after Milestone 5 review | Desktop and extension workflows accepted | Installer and extension pass Commercial and Student release validation |
| 7 | Additional core families | One plan per core family after toroid release criteria pass | Toroid workflow released | Each family has independent schemas, invariants, previews, adapters, and fixtures |

## Execution rule

Only one detailed milestone plan is active at a time. Every completed milestone closes with:

1. Exact automated and controlled-AEDT test results.
2. Accepted public interfaces and schema versions.
3. Documented compatibility findings and unresolved risks.
4. A clean Git commit and handoff.
5. The detailed plan for the next milestone.

## Approved specification coverage

| Specification area | Delivery milestone |
| --- | --- |
| Shared modular architecture, dependency inversion, schemas, diagnostics foundation, test strategy, and AEDT release/edition capability evidence | 0 |
| Toroid project model, commercial Magnetics core records, conductor catalog, multiple winding definitions, units, snapshots, and migrations | 1 |
| Solver-independent 3D geometry, approximate 2D intermediate geometry, packing, collisions, leads, naming, symmetry proof, and persistent preview | 2 |
| Ready-to-solve Maxwell 3D geometry, materials, solid/stranded windings, excitations, region, boundaries, mesh, setup, and supported reports | 3 |
| Maxwell 2D equivalent, native Include DC Fields, AEDT 2024 R2 operating-point fallback, compatibility warnings, and generation manifest | 4 |
| Traceable datasheet/image/CSV/formula material workflow, curve calibration, fitting, physical checks, review, approval, and optional GPL importer | 5 |
| Guided Studio completion, autosave/recovery, undo/redo, cancellation, AEDT extension, PyInstaller, Inno Setup, release matrix, checksums, and release documentation | 6 |
| E, PQ, EQ, EER, and subsequently approved core-family plugins | 7 |

Deferred transient, thermal, mechanical, optimization, converter co-simulation, cloud, and non-round-conductor work requires a separately approved specification before it enters this index.
