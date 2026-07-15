# Development Roadmap

## Milestone 0: Foundation and compatibility spike

- Establish Python packaging, quality gates, schemas, CI, and documentation.
- Prove connection to AEDT 2024 R2 and a current AEDT release through PyAEDT.
- Prove a minimal PySide6/QML application and Qt Quick 3D preview.
- Record a capability matrix for Commercial and Student editions.

Exit criterion: a documented spike creates and saves a trivial Maxwell 2D and 3D design without domain-to-PyAEDT coupling.

### Current state

Milestone 0 is **accepted** as of 2026-07-13. Acceptance scope is deliberately limited to the AEDT 2025 R2 Commercial release available on the development machine; the 2024 R2 (Commercial and Student) and 2025 R2 Student rows stay `out-of-scope` and become required again only when a later milestone targets those releases. Milestone 1 is unblocked.

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

Task 11 is closed: the 2025.2 Commercial review is accepted and the remaining Milestone 0 gates pass. Milestone 1 is unblocked. The deferred rows become required again only when a later milestone targets a Student or 2024 R2 release.

## Milestone 1: Toroid domain and catalogs

- Implement units, project schemas, commercial core records, conductor records, winding sectors, and validation.
- Import a reviewed subset of Magnetics commercial powder-core and ferrite toroids.
- Build the canonical-files-to-SQLite catalog pipeline.

Exit criterion: a versioned project selects a commercial core, defines multiple valid windings, and survives schema round trips.

### Current state

Milestone 1 is **accepted** as of 2026-07-14. The exit criterion is proven by
`tests/integration/test_project_round_trip.py`; the ten powder-core records are
reviewed against the 2025 Magnetics Powder Cores Catalog. The five ferrite
records remain `draft` until the ferrite catalog review; insulated wire
diameters are populated and reviewed as part of Milestone 2, which consumes
them.

Implemented Milestone 1 deliverables:

- The domain model, including units and AEDT target types.
- Declarative validation covering the four spec categories, including wraparound sector overlap.
- Project schema v2 with a v1-to-v2 migration.
- The project repository with deterministic, byte-identical saves.
- Catalog schemas and 15 draft Magnetics core records.
- A generated round-wire conductor catalog (35 records).
- The canonical-files-to-SQLite catalog builder.
- The catalog repository port with a read-only SQLite adapter.
- Snapshot comparison and adoption services for catalog revisions.
- The Milestone 1 exit-criterion integration test.

Remaining work: the five ferrite-toroid records remain `draft` pending review against the Magnetics ferrite catalog; insulated wire diameters are populated during Milestone 2, which consumes them.

## Milestone 2: Geometry and live preview

- Implement the solver-independent toroid and winding geometry.
- Add automatic sector packing, spacing rules, collision detection, lead reservation, and deterministic naming.
- Add periodicity validation and optional symmetry-plan generation.
- Render the same geometry model in the Guided Studio preview.

Exit criterion: previewed geometry passes property-based invariants and deterministic golden-manifest tests.

### Design note: winding geometry uses finished (coated), not bare, core dimensions

The wire is wound on the coated core surface, so packing and collision geometry
must consume the **finished** core dimensions, never the bare nominal. The finish
moves each dimension one way: the inner diameter shrinks (coating adds inward,
reducing the winding window and the achievable turn count), while the outer
diameter and height grow (coating adds outward, setting the board/enclosure
envelope). The worst case for fitting turns is therefore the smallest finished
inner diameter; the worst case for envelope is the largest finished outer
diameter and height.

The catalog already carries this. Each `Dimension` stores the bare value in
`nominalM` and the finish-moved limit in the single relevant bound: inner
diameter in `minM`, outer diameter and height in `maxM` (see
`catalog/cores/magnetics-powder.yaml`, transcribed from the Magnetics catalog's
"Before Finish (nominal)" and "After Finish (limits)" rows). Magnetics publishes
no finished *nominal*, only limits, so the finished limit is the honest
conservative input for packing.

Milestone 2 decision: the packing engine reads `innerDiameter.minM`,
`outerDiameter.maxM`, and `height.maxM` when present, falling back to `nominalM`
only for manual cores that carry no finish data. Do not build winding geometry
from `nominalM` on catalog cores — it models the bare core and overestimates the
available window.

### Design note: one closed loop per turn

Reviewed decision (2026-07-14): each winding turn is modeled as one closed
planar D-loop; no turn-to-turn connector and no lead wire exists in the
geometry, the wire length estimate, or the preview. Maxwell (Milestone 3)
assigns one coil terminal per closed turn and groups the turns into the
winding, which is the standard Maxwell treatment and avoids helical geometry
entirely. `leadInDeg`/`leadOutDeg` in the manifest mark the reserved packing
gap at the sector ends, not wire.

### Current state

Milestone 2 is **accepted** as of 2026-07-15. The exit criterion is proven by
the hypothesis packing invariants, the committed golden manifest, and the
preview smoke test; the interactive visual check was performed by the reviewer
(Fabio Posser) on the sample project, leading to the accepted
one-closed-loop-per-turn model. Implemented deliverables:

- Finished-core resolution that honors the design note above (`resolve_finished_core`).
- D-shaped turn paths with closed 8-segment planar loops.
- Multi-layer concentric-shell winding packing.
- Cross-winding clearance and occupancy reporting.
- Deterministic object naming.
- Data-level symmetry plans (`propose_symmetry_plan`).
- The 2D planar equivalent model.
- A canonical geometry manifest with a committed golden fixture.
- The hypothesis property suite for packing invariants.
- Core and winding tessellation into triangle-soup meshes.
- The Qt Quick 3D orbit-camera preview viewer.

Remaining work: the five ferrite core records remain `draft` pending review
against the Magnetics ferrite catalog. The insulation values were confirmed
correct by the reviewer on 2026-07-15.

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
