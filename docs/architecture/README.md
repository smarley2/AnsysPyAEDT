# Architecture Boundaries

The application uses a modular Python architecture with dependency inversion. The Windows desktop application and AEDT extension are separate user-interface shells over the same application services.

## Dependency direction

Dependencies point inward:

```text
UI and AEDT extension
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
- `simulation`: Solver-independent AC Magnetic recipes, DC-biased capability requests, mesh intent, and report intent.
- `application`: Use cases such as validate, preview, generate, solve, migrate, and export.
- `adapters/pyaedt`: Maxwell 2D/3D operations and AEDT-version capability handling.
- `adapters/preview`: Qt Quick 3D mesh conversion.
- `adapters/persistence`: Project JSON, canonical catalog files, and compiled SQLite indexes.
- `ui`: PySide6 and QML Guided Studio.
- `aedt_extension`: Thin shell that connects the shared application services to an active AEDT session.

## Critical rules

1. PyAEDT objects never cross into the domain model.
2. Preview meshes and Maxwell exports originate from the same solver-independent geometry model.
3. Catalog updates never mutate saved project behavior without an explicit migration.
4. AEDT 2024 R2 fallbacks are visible approximations, not silent emulations of newer solvers.
5. Maxwell 2D toroidal models are labeled equivalent cross-sectional models. Maxwell 3D remains authoritative for angular placement and lead geometry.

The complete rationale and product requirements are in the approved design specification.
