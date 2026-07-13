# Development Roadmap

## Milestone 0: Foundation and compatibility spike

- Establish Python packaging, quality gates, schemas, CI, and documentation.
- Prove connection to AEDT 2024 R2 and a current AEDT release through PyAEDT.
- Prove a minimal PySide6/QML application and Qt Quick 3D preview.
- Record a capability matrix for Commercial and Student editions.

Exit criterion: a documented spike creates and saves a trivial Maxwell 2D and 3D design without domain-to-PyAEDT coupling.

### Current state

The Milestone 0 implementation is present, but controlled AEDT validation and formal milestone acceptance are pending.

Implemented foundation deliverables:

- Python packaging and quality gates, including dependency-boundary enforcement.
- A versioned project-envelope schema and repository adapter.
- Solver-independent AEDT capability policy.
- The AEDT gateway contract, recording fake, and lazy PyAEDT adapter.
- A machine-readable compatibility-spike CLI.
- A minimal PySide6/QML Guided Studio shell with a Qt Quick 3D preview smoke path.
- A hosted non-AEDT CI definition.
- A controlled AEDT runner, compatibility procedure, and four-row release/edition matrix.

Verified non-AEDT evidence:

- [Hosted CI run 29234286379](https://github.com/smarley2/AnsysPyAEDT/actions/runs/29234286379) passed for commit `1f24ff3` with the quality job and Windows and Ubuntu test jobs on Python 3.10 and 3.13. The quality job covered Ruff, mypy, and architecture checks; every test job installed UI dependencies and ran the non-AEDT coverage suite.
- Non-AEDT quality, architecture, unit, and contract gates have been exercised locally.
- Package installation and UI smoke checks have been exercised locally.
- Fresh release decisions must use the reproducible gates in the [validation plan](VALIDATION_PLAN.md), rather than treating this status summary as current test evidence.

Remaining evidence:

- The 2025 R2 Commercial row is reviewed and passed (evidence on disk under `artifacts/compatibility/2025.2-commercial/`, gitignored).
- The 2024 R2 (Commercial and Student) and 2025 R2 Student rows are marked `out-of-scope` for Milestone 0 because no matching AEDT executable or license is available on the development machine.

Task 11 closes when the 2025.2 Commercial review is accepted and the remaining Milestone 0 gates pass. Milestone 1 remains blocked by Milestone 0 acceptance. The deferred rows become required again only when a later milestone targets a Student or 2024 R2 release.

## Milestone 1: Toroid domain and catalogs

- Implement units, project schemas, commercial core records, conductor records, winding sectors, and validation.
- Import a reviewed subset of Magnetics commercial powder-core and ferrite toroids.
- Build the canonical-files-to-SQLite catalog pipeline.

Exit criterion: a versioned project selects a commercial core, defines multiple valid windings, and survives schema round trips.

## Milestone 2: Geometry and live preview

- Implement the solver-independent toroid and winding geometry.
- Add automatic sector packing, spacing rules, collision detection, lead reservation, and deterministic naming.
- Add periodicity validation and optional symmetry-plan generation.
- Render the same geometry model in the Guided Studio preview.

Exit criterion: previewed geometry passes property-based invariants and deterministic golden-manifest tests.

## Milestone 3: Maxwell 3D MVP

- Generate toroid core geometry and round-wire windings.
- Support solid and stranded winding behavior.
- Assign materials, coils, winding groups, directions, region, boundaries, mesh intent, AC Magnetic setup, and standard reports.

Exit criterion: a supported AEDT installation opens a generated 3D project that is ready to solve.

## Milestone 4: Maxwell 2D and DC operating point compatibility

- Generate the documented 2D equivalent cross-sectional model.
- Use native 3D Include DC Fields where supported.
- Implement the AEDT 2024 R2 Magnetostatic plus incremental-linearization fallback.
- Make approximations and capability differences visible in the project manifest and UI.

Exit criterion: release-matrix fixtures generate valid projects and identify native versus approximate operating-point treatment.

## Milestone 5: Material Studio

- Import PDF images, screenshots, CSV data, and formulas.
- Calibrate linear and logarithmic axes, extract/edit points, fit supported models, validate units and physics, and preserve provenance.
- Export only approved material revisions to Maxwell.

Exit criterion: a reviewer can reproduce a material record from its stored source metadata and transformation history.

## Milestone 6: Productization

- Package the Windows application with PyInstaller and Inno Setup.
- Package the AEDT extension separately.
- Add recovery, diagnostics, reports, release notes, checksums, and the controlled AEDT release checklist.

Exit criterion: the installer and extension pass the Commercial/Student compatibility matrix.

## Milestone 7: Additional core families

- Add E, PQ, EQ, EER, and other approved commercial geometries as independent geometry plugins.

Exit criterion: each family has its own catalog schema, geometry invariants, previews, Maxwell adapters, and integration fixtures.
