# Architecture Boundaries

The application uses a modular Python architecture with dependency inversion.
The standalone Windows desktop application is the only product UI. Existing CLI
and MCP entry points are thin optional automation surfaces over the same
application services; new MCP work is outside the active MVP roadmap.

Milestone 6 was accepted on 2026-07-28. This document distinguishes its
implemented contracts from later approved targets:

- Project schema v5 is the only supported Project document schema. It is a
  deliberate clean break with no legacy migration.
- The implemented Project document is backend-independent and contains one
  Design, one Operating Point, and one Simulation Recipe.
- Run Requests, Run Manifests, effective winding inputs, and immutable
  Normalized Result Set contracts are implemented. Generate Only execution is
  routed through the shared application service; Generate and Solve execution
  and result population remain M8 work.
- The current Canvas First UI provides a real editable-winding and preview
  slice. M7 completes project authoring, the revised Guided flow, and
  solver-independent Preliminary estimates.
- Solve orchestration and result export are M8 targets. Recovery is an M9
  target.
- M7 stores every Generate Only run in a new normalized `runs/` directory next
  to the saved Project document. M8 reuses that layout for solve results.

## Dependency direction

Dependencies point inward:

```text
Windows UI, CLI, and optional MCP
        |
Application services and ports
        |
Domain, geometry, materials, and solver-independent simulation
        ^
PyAEDT, FEMM, catalog, material, persistence, and UI adapters
```

Inner modules define the physical model and interfaces. Infrastructure and UI
code implement or adapt those interfaces.

## Implemented modules

- `domain`: Units, core selections, conductors, winding definitions,
  the v5 Project aggregate, Operating Point excitations, Simulation Recipe,
  exact material selection, and validation rules.
- `geometry`: Solver-independent toroid construction, winding packing,
  collision checks, deterministic geometry, tessellation inputs, and the 2D
  equivalent.
- `materials`: Material identities, immutable records, provenance, curve data,
  fitting, replay, and physical validation.
- `simulation`: Solver-independent Run Request/Manifest/result contracts,
  effective-input conversion, capability decisions, and Maxwell/FEMM plan
  models and builders.
- `application`: Ports and use cases for validation, geometry composition,
  project persistence, material workflows, operation-specific run planning,
  and Generate Only execution.
- `adapters/catalog`: Canonical catalog and compiled SQLite index access.
- `adapters/compatibility`: Observed AEDT 2025 R2 Commercial capabilities used
  to block unsupported operations.
- `adapters/femm`: FEMM 2D translation, execution, and result extraction.
- `adapters/materials`: CSV/XLSX import, workbook export, and filesystem
  material-overlay persistence.
- `adapters/persistence`: Deterministic v5 Project JSON and v5-only schema
  access.
- `adapters/pyaedt`: AEDT 2025 R2 Commercial Maxwell 2D/3D operations and
  staged exporters.
- `ui`: PySide6/QML Guided Studio, Material Studio, controllers, and Qt Quick 3D
  preview conversion.
- `mcp_server`: Existing optional automation over application services; not a
  separate domain model or active parity target.

## Implemented M6 contracts and approved M7 flow

The implemented v5 Project document contains:

1. **Design** — core, dimensions, windings, conductors, materials, and geometry
   choices.
2. **Operating Point** — one shared frequency, winding and core temperatures,
   and each winding's AC RMS current, phase, DC current, and direction.
3. **Simulation Recipe** — mesh intent, convergence intent, and requested
   outputs.

A separate Run Request selects Maxwell 3D, Maxwell 2D, or FEMM and chooses
`Generate Only` or `Generate and Solve`. Generate Only produces a Run Manifest
with schema version, effective RMS and peak inputs, exact material state,
recipe, versions, approximations, stages, diagnostics, and artifacts. Generate
and Solve is validated but blocked until M8 populates the implemented
Normalized Result Set contract. Generated solver files never become the
editable source of truth.

Normal generation requires one exact imported or approved material revision and
the selected B-H series. The only unresolved-material operation is an explicitly
confirmed Maxwell 3D Generate Only request. It uses a separate Geometry-Only
plan and adapter method with only core/winding geometry and no material,
excitation, region, mesh, setup, matrix, report, validation, result, or
solve-ready claim. It records the effective stored Operating Point inputs but
does not consult solve-ready DC capability because it creates no excitation,
setup, or solve.

M7 uses the approved Guided flow:

```text
Core & Material -> Windings -> Preliminary -> Simulation -> Review
```

Material Studio opens in a separate window rather than occupying a Guided
Studio step. The Preliminary estimator belongs to solver-independent
simulation/application code, consumes the same immutable Project and geometry
inputs, and never starts Maxwell or FEMM. The UI controller maps one immutable
estimate to QML-facing rows; QML contains no physical formulas.

## Critical rules

1. `domain`, `geometry`, `materials`, and solver-independent `simulation` code
   do not import PyAEDT, Qt, FEMM, SQLite, MCP, or operating-system APIs.
2. PyAEDT and FEMM objects never cross into the domain model.
3. Preview meshes and solver exports originate from the same
   solver-independent geometry model.
4. A Project is backend-independent and a Run Request selects Maxwell 3D,
   Maxwell 2D, or FEMM.
5. The UI and Project store AC RMS current. Solver-independent planning
   converts it exactly once to the peak amplitudes consumed by Maxwell and
   FEMM. FEMM converts the planned peak magnitude and phase to one complex
   circuit-current phasor at the adapter boundary without another RMS
   conversion.
6. Projects pin the exact material revision and B-H series. Catalog or material
   updates never mutate saved project behavior silently.
7. Generated AEDT and FEMM projects are independent outputs and are never
   imported back as editable source.
8. Unsupported solver quantities and capabilities are explicit; adapters never
   invent a fallback or result.
9. Maxwell 2D and FEMM toroidal models are labeled equivalent cross-sectional
   models. Maxwell 3D remains authoritative for angular placement and lead
   geometry.
10. Full models are generated. Symmetry remains an informational suggestion.
11. Preliminary results are derived, not editable persisted truth. Each
    quantity is independently `Estimated`, `Unavailable`, or `Invalid`, with an
    explicit reason and approximation label.
12. Failed edits preserve the last valid Project and preview. Partial or failed
    solver artifacts are never reported as successful.
13. Every run uses a new project-local directory. Solver work is
    background/non-graphical by default, with optional visible operation where
    supported. Native solver files remain manually editable independent
    outputs.

## Authoritative decisions

- [MVP roadmap realignment](../superpowers/specs/2026-07-24-mvp-roadmap-realignment-design.md)
- [Preliminary calculations and Guided flow](../superpowers/specs/2026-07-26-preliminary-calculations-and-guided-flow-design.md)
- [ADR 0001: modular Python and Qt](../adr/0001-modular-python-qt-architecture.md)
- [ADR 0004: standalone Windows and single AEDT target](../adr/0004-standalone-windows-and-single-aedt-target.md)
- [ADR 0005: backend-independent projects](../adr/0005-backend-independent-projects.md)
- [ADR 0006: RMS project current and peak solver excitation](../adr/0006-rms-project-current-and-peak-solver-excitation.md)
- [ADR 0007: project-local run artifacts and solver visibility](../adr/0007-project-local-run-artifacts-and-solver-visibility.md)
