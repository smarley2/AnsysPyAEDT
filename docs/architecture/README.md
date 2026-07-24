# Architecture Boundaries

The application uses a modular Python architecture with dependency inversion.
The standalone Windows desktop application is the product UI. Existing CLI and
MCP entry points are thin optional automation surfaces over the same
application services; new MCP work is outside the active MVP roadmap.

## Dependency direction

Dependencies point inward:

```text
Windows UI, CLI, and optional MCP
        |
Application services
        |
Domain, geometry, materials, and simulation recipes
        ^
PyAEDT, preview, persistence, and catalog-import adapters
```

The inner modules define interfaces. Infrastructure implements them.

## Modules

- `domain`: Units, core selections, conductors, winding definitions, excitations, project configuration, and validation rules.
- `geometry`: Solver-independent geometry representation, toroid construction, winding packing, collision checks, and 2D-equivalent construction.
- `materials`: Material records, provenance, curve data, fitting, approval state, and physical validation.
- `simulation`: Solver-independent AC Magnetic recipes, run requests, Maxwell and FEMM plans, mesh intent, convergence intent, and result requests.
- `application`: Use cases such as create, open, save, validate, preview, generate, solve, cancel, recover, and export results.
- `adapters/pyaedt`: AEDT 2025 R2 Commercial Maxwell 2D/3D operations and staged exporters.
- `adapters/compatibility`: Observed AEDT 2025 R2 Commercial capabilities used to block unsupported operations.
- `adapters/femm`: FEMM 2D problem translation, execution, and result extraction.
- `adapters/preview`: Qt Quick 3D mesh conversion.
- `adapters/persistence`: Project JSON, canonical catalog files, and compiled SQLite indexes.
- `ui`: PySide6 and QML Guided Studio.
- `mcp_server`: Existing optional automation over application services; not a separate domain model or active parity target.

## Critical rules

1. PyAEDT objects never cross into the domain model.
2. Preview meshes and Maxwell exports originate from the same solver-independent geometry model.
3. A Project document is backend-independent; a Run Request selects Maxwell 3D, Maxwell 2D, or FEMM.
4. The UI and Project document store AC RMS current. Solver-independent planning converts it once to the peak amplitudes consumed by Maxwell and FEMM.
5. Generated AEDT projects are independent outputs and are never imported back as editable source.
6. Catalog updates never mutate saved project behavior silently.
7. Unsupported solver quantities and capabilities are explicit; adapters never invent a fallback or result.
8. Maxwell 2D and FEMM toroidal models are labeled equivalent cross-sectional models. Maxwell 3D remains authoritative for angular placement and lead geometry.
9. Full models are generated. Symmetry remains an informational suggestion.

The current rationale and product requirements are in the
[approved roadmap realignment](../superpowers/specs/2026-07-24-mvp-roadmap-realignment-design.md).
