# PyAEDT Inductor Designer — Product and Architecture Design

- Status: Approved in collaborative design review
- Date: 2026-07-12
- Documentation language: English
- Target platform: Windows
- Minimum AEDT release: 2024 R2
- Supported editions: Commercial and Student

## 1. Purpose

Build a modern Windows application and AEDT extension that create parametric inductor designs in Ansys Maxwell 2D and 3D through PyAEDT. The application must guide a user from commercial core and conductor selection through winding placement, material selection, simulation setup, Maxwell generation, optional solving, and reporting.

The first functional product increment focuses on toroidal inductors. Later increments add E, PQ, EQ, EER, and other core families without changing the toroid implementation into a universal monolith.

## 2. Confirmed product decisions

- Deliver both a standalone Windows application and an AEDT extension over the same shared core.
- Support AEDT 2024 R2 and newer versions in Commercial and Student editions.
- Start with toroidal 3D geometry and an explicitly approximate Maxwell 2D representation.
- Generate projects that are ready to simulate, including materials, excitations, boundaries, mesh intent, setup, and reports.
- Prioritize AC Magnetic/Eddy Current analysis.
- Use native 3D Include DC Fields on AEDT 2025 R1 or newer when the capability is available.
- For AEDT 2024 R2, provide a visible approximation using a Magnetostatic operating point followed by an Eddy Current design with incremental material linearization.
- Use Apache-2.0 for original project code.
- Keep GPL-licensed material data outside the distributed application and provide an optional attributed importer.
- Use assisted, human-approved extraction for datasheets, screenshots, curves, CSV data, and formulas.
- Use the Guided Studio layout: step-based editing with a persistent preview and optional expert controls.
- Ship the MVP UI in English and make text localization-ready.
- Support round wire in the MVP, selected by AWG or metric diameter, with copper and insulated diameters.
- Support solid and stranded Maxwell winding behavior.
- Position windings automatically by angular sector with expert overrides.
- Seed the commercial catalog with Magnetics powder-core and ferrite toroids.
- Generate the full model by default and enable symmetry only when geometry, materials, windings, and excitations are provably periodic.

## 3. Scope

### 3.1 MVP scope

- Create, open, validate, migrate, and save versioned inductor project files.
- Select a commercial Magnetics toroid or enter manual dimensions.
- Preserve catalog nominal dimensions, tolerances, source revision, and user overrides.
- Define one or more windings with independent electrical and geometric settings.
- Select round-wire gauge, conductor mode, turns, sector, spacing, clearance, winding direction, current direction, AC magnitude and phase, and DC operating current.
- Preview the resulting 3D geometry without launching AEDT.
- Generate deterministic Maxwell 3D and equivalent Maxwell 2D projects.
- Create AC Magnetic simulation configurations and DC-biased behavior according to the AEDT capability matrix.
- Suggest valid cut planes, periodic sectors, and symmetry multipliers without forcing them.
- Create and approve traceable magnetic material records.
- Optionally run supported simulations and generate standard reports.
- Produce actionable diagnostics and a generation manifest.

### 3.2 Deferred scope

- Litz wire, foil, rectangular conductors, and arbitrary imported conductors.
- E, PQ, EQ, EER, U, and custom core families.
- Transient, thermal, mechanical, optimization, and converter co-simulation workflows.
- Automatic final approval of OCR-extracted material data.
- Cloud services or collaborative remote databases.

## 4. Architecture

Use a modular Python architecture with dependency inversion. Both user interfaces call shared application services. Inner modules define interfaces; infrastructure adapters implement them.

### 4.1 Inner modules

- `domain`: Quantities, units, core selections, conductor definitions, winding plans, excitations, project configuration, and validation results.
- `geometry`: Solver-independent objects and paths, toroid construction, winding packing, collision checks, lead reservation, deterministic naming, preview tessellation, and 2D equivalents.
- `materials`: Material identity, property datasets, formulas, provenance, fitting, residuals, approval states, and physical checks.
- `simulation`: Solver-independent requests for AC Magnetic analysis, operating-point behavior, regions, boundaries, mesh intent, convergence, and reports.
- `application`: Validate, preview, generate, solve, cancel, migrate, compare catalog revisions, approve material revisions, and export reports.

### 4.2 Adapters

- PyAEDT adapter for Maxwell 2D and 3D.
- AEDT capability adapter for release and edition detection.
- Qt Quick 3D preview adapter.
- JSON project and schema-migration adapter.
- Canonical catalog file and compiled SQLite index adapter.
- Magnetics catalog importer.
- Optional GPL materialdatabase importer with preserved attribution and license metadata.

### 4.3 User interfaces

- Windows desktop shell built with PySide6 and Qt Quick/QML.
- Thin AEDT extension shell that uses an active AEDT session.
- Shared QML components where embedding constraints allow it.

### 4.4 Boundary rules

- Domain and geometry modules do not import PyAEDT, Qt, SQLite, or operating-system APIs.
- PyAEDT objects do not appear in domain interfaces.
- Preview and Maxwell export consume the same intermediate geometry model.
- Feature detection occurs before generation.
- Version fallbacks are explicit policies with manifest entries and user-visible warnings.

## 5. Data model and persistence

### 5.1 Canonical repository data

Store reviewable source data in Git:

- YAML or JSON for identity, dimensions, conditions, provenance, formulas, and metadata.
- CSV for numeric series such as B-H, permeability, temperature, bias, and loss curves.
- JSON Schema files for machine validation.
- A generated SQLite catalog index for release bundles and fast application queries.

The SQLite index is a build artifact and is never edited manually.

### 5.2 Commercial core records

Each record includes manufacturer, family, part number, material, permeability grade, finish/coating, catalog revision, source URL, source page, nominal dimensions, tolerances, effective area, effective magnetic path length, effective volume, nominal inductance factor, and any availability constraints.

Geometry, material, and finish are separate concepts even when a manufacturer encodes them in one part number.

### 5.3 Project document

Use a schema-versioned `*.inductor.json` document containing:

- Project metadata, units, requested AEDT target, edition behavior, and 2D/3D mode.
- Catalog reference plus an immutable snapshot of the exact values used.
- Manual overrides with reasons.
- Windings, conductors, sectors, turns, spacing, directions, leads, and terminal intent.
- Materials and exact approved revisions.
- AC and DC excitations.
- Simulation recipe, mesh intent, output requests, and compatibility decisions.

Updating a catalog never changes an existing project silently. The application compares revisions and requires explicit migration.

### 5.4 User materials

User-created material records live in a separate local overlay catalog and use `draft`, `reviewed`, and `approved` states. Only approved revisions export without a blocking confirmation. Records preserve source hashes and references, crop/calibration data, extracted points, units, curve conditions, fitting method, coefficients, residuals, reviewer, and timestamps.

## 6. Toroid and winding geometry

### 6.1 Core definition

The normal path is selection by manufacturer and part number. Manual input remains available for outside diameter, inside diameter, height, and supported edge-radius or chamfer parameters. Catalog tolerance limits remain visible after selection.

### 6.2 Winding definition

Each winding includes:

- Stable identifier and user label.
- Turn count.
- Conductor reference and solid/stranded mode.
- Start angle and available angular sector.
- Minimum spacing between insulated wire surfaces.
- Minimum clearance from adjacent windings.
- Clockwise or counterclockwise winding direction.
- Current reference direction.
- Lead and terminal intent.
- AC magnitude, phase, frequency, and DC operating current.

The packing engine proposes turn centers, reserves lead space, detects conductor/core and conductor/conductor collisions, calculates angular occupancy, and estimates wire length. Expert overrides remain subject to hard collision and dimension validation.

### 6.3 Maxwell 3D

Maxwell 3D is authoritative for angular placement. Round-wire profiles are swept along deterministic paths. Leads and terminal faces receive deterministic names. Solid mode preserves conductor behavior required for skin and proximity effects. Stranded mode requests equivalent winding behavior for lower simulation cost.

### 6.4 Maxwell 2D equivalent

The 2D toroid is an explicitly approximate XY cross-sectional model with an annular core and paired outgoing/returning conductor regions for each winding. Turns and polarity are represented through Maxwell coil and winding assignments, and model depth is derived from core height.

The 2D model does not claim to reproduce angular bends, local wire spacing, lead routing, or three-dimensional leakage and proximity effects. The UI and generation manifest identify which outputs are approximate.

### 6.5 Cuts and symmetry

The generator creates a full model by default. It may offer an optional symmetry plan only after verifying that core geometry, material orientation, winding placement, conductor geometry, current magnitude, phase, and direction repeat across the proposed sector. The Review step shows the cut planes, boundary intent, sector angle, and symmetry multiplier. If periodicity cannot be proven, automatic symmetry is unavailable and the user may apply manual changes to the completed AEDT project.

## 7. Simulation behavior

The AC Magnetic recipe defines core and conductor materials, coil and winding assignments, AC magnitudes and phases, DC operating currents where supported, current directions, air region, boundaries, eddy-effect intent, mesh intent, convergence, frequency, and standard reports.

Standard requested results include winding resistance, inductance and impedance or matrix data where supported, copper loss, core loss, magnetic energy, peak flux-density indicators, current-density indicators, and convergence information. Reports are created only when the selected solver and dimensional model support the quantity without misrepresentation.

Generation and solving are separate operations. A user may stop after creating a ready-to-run AEDT project.

### 7.1 Compatibility policies

- AEDT 2025 R1 or newer, Maxwell 3D with required capability: use native Include DC Fields and DC winding/current values.
- AEDT 2024 R2: create coordinated Magnetostatic and Eddy Current designs and use an incremental-linearization approximation derived from the DC operating point.
- Maxwell 2D or any environment without the requested native capability: use only a documented supported fallback or block generation with an actionable explanation.
- Student limitations are detected and reported before geometry generation. The application does not guess undocumented limits.

An approximation always records its method, inputs, validity limitations, and the native capability that would replace it.

## 8. Guided Studio user experience

The main steps are `Core`, `Windings`, `Materials`, `Simulation`, and `Review`.

- The current step and parameters appear on the left.
- A persistent interactive preview occupies the main area.
- Validation, complexity, and progress appear in a stable status area.
- Expert controls reveal detailed placement and solver settings without changing the underlying model.
- Unit-aware inputs accept explicit engineering quantities.
- Valid edits are autosaved to a recovery file.
- Parameter edits support undo and redo.
- The Review step lists every object, material, winding, excitation, approximation, setup, and output before AEDT is modified.
- Generation is cancelable and reports its current stage.

All UI text uses translation identifiers. English is the only MVP locale.

## 9. Material Studio

The assisted material workflow is:

1. Import a PDF page image, screenshot, CSV, or formula.
2. Record manufacturer, material, document revision, URL, page, and operating conditions.
3. Crop the relevant table or curve.
4. Calibrate axes, including linear or logarithmic scales and units.
5. Extract points automatically and allow manual correction.
6. Associate curve parameters such as frequency, temperature, DC bias, and flux density.
7. Fit a supported B-H, permeability, loss-table, Steinmetz-family, or explicit formula representation.
8. Compare source points, fitted values, and residual error.
9. Run unit, range, monotonicity, duplication, and applicable physical consistency checks.
10. Save a draft and require explicit review and approval.

OCR only proposes values. It never approves or exports a material automatically.

## 10. Errors, diagnostics, and recovery

Validation uses four categories:

- `Info`: recommendation or explanatory assumption.
- `Warning`: generation is allowed and the condition is recorded.
- `Error`: generation is blocked.
- `Compatibility`: behavior changes with AEDT release or edition.

Maxwell generation executes as named stages and writes a manifest. On failure, the application reports the failed stage, retains the validated input, and preserves diagnostic logs. A partial AEDT design is never reported as successful. Logs must exclude credentials, license data, and unrelated personal paths where practical.

## 11. Testing and verification

- Unit tests cover domain rules, quantities, schemas, fitting, migrations, and compatibility decisions.
- Property-based tests cover winding packing, collision detection, angular occupancy, dimension limits, and deterministic naming.
- Golden-manifest tests verify stable generation intent without AEDT.
- Contract tests exercise PyAEDT adapters through recording or fake gateways.
- UI tests exercise the Guided Studio, validation, recovery, and cancellation.
- Tagged real-AEDT integration tests run on controlled licensed Windows machines.

Release validation covers AEDT 2024 R2 Commercial, AEDT 2024 R2 Student, the latest supported Commercial release, and the latest supported Student release. GitHub-hosted CI runs non-AEDT checks on Windows and Linux. Licensed integration tests use a controlled self-hosted runner or a documented manual checklist.

## 12. Repository and collaboration

The planned repository contains focused Python packages, canonical data, schemas, separate test categories, importer tools, architecture documents, ADRs, development guides, specifications, and implementation plans.

`AGENTS.md` and `CLAUDE.md` point contributors to the same canonical sources. Agents work on separate branches and worktrees, never concurrently in one working tree. Tasks define ownership, allowed files, dependencies, interfaces, acceptance criteria, and verification commands. GitHub Issues track ownership; specifications and plans define technical behavior.

All code, documentation, UI copy, schemas, logs, branches, commits, and GitHub content are written in English.

## 13. Packaging and licensing

- Original code uses Apache-2.0.
- The desktop application is bundled with PyInstaller and delivered through Inno Setup.
- The AEDT extension is packaged separately.
- Releases use Semantic Versioning, conventional commits, checksums, and release notes.
- Code signing is part of the release design but is not required for the first internal prototype.
- Third-party data retains its own attribution and licensing metadata.
- GPL material data is not copied into the application distribution or canonical project database.

## 14. Delivery sequence

1. Foundation, schemas, CI, and compatibility spike.
2. Toroid domain, commercial catalogs, conductor catalog, and project persistence.
3. Geometry, validation, automatic winding packing, and live preview.
4. Maxwell 3D ready-to-solve MVP.
5. Maxwell 2D equivalent and operating-point compatibility policies.
6. Material Studio and approved-material export.
7. AEDT extension, installer, reporting, and release validation.
8. Additional independently implemented core families.

Each milestone produces a working, independently testable deliverable. Additional core families do not start until the toroidal workflow passes its release criteria.

## 15. Authoritative references

- PyAEDT documentation: https://aedt.docs.pyansys.com/
- PyAEDT Maxwell 3D API: https://aedt.docs.pyansys.com/version/stable/API/_autosummary/ansys.aedt.core.maxwell.Maxwell3d.html
- PyAEDT coil extension example: https://aedt.docs.pyansys.com/version/dev/User_guide/pyaedt_extensions_doc/maxwell/create_coil.html
- AEDT 2025 R1 release notes describing 3D Eddy Current Include DC Fields: https://ansyshelp.ansys.com/public/Views/Secured/Electronics/v251/en/PDFs/WhatsNewInElectronicsDesktop.pdf
- Magnetics powder-core catalog: https://www.mag-inc.com/Media/Magnetics/File-Library/Product%20Literature/Powder%20Core%20Literature/Magnetics-Powder-Core-Catalog.pdf
- Magnetics part-number guidance: https://www.mag-inc.com/products/powder-cores/how-to-order-magnetics-powder-cores
- Magnetics ferrite toroids: https://www.mag-inc.com/products/ferrite-cores/ferrite-toroids
- UPB-LEA materialdatabase: https://github.com/upb-lea/materialdatabase

## 16. Success criteria for the first product release

A user can select a reviewed commercial Magnetics toroid, define one or more valid round-wire windings, select approved materials, configure AC and DC operating conditions, preview the design, generate deterministic ready-to-run Maxwell 3D and documented Maxwell 2D projects, understand every compatibility fallback, save and reopen the source project, and reproduce the generation from the recorded catalog and material snapshots.
