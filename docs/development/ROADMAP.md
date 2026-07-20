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

### Current state

Milestone 3 is **accepted** as of 2026-07-16. The exit criterion is proven by
the full 15-stage export on AEDT 2025 R2 Commercial (`run_aedt_maxwell3d.ps1`),
with every stage succeeding and the generated project passing design
validation. Implemented deliverables:

- The solver-independent `Maxwell3dDesignPlan` (frozen dataclasses) and `build_maxwell3d_plan` plan builder.
- The staged PyAEDT exporter (`PyaedtMaxwell3dExporter`) running 15 named stages with guaranteed `release_desktop`; a partial design is never reported as successful.
- The `Maxwell3dExporter` application port with a recording fake and a `FakeMaxwell3dApp` for unit tests.
- The `export_maxwell3d` application service with a deterministic generation manifest, refusing 2D projects, manual cores, and collisions.
- `core_material_spec` deriving a linear draft material from the powder grade (D2); ferrites and non-numeric grades refuse export.
- Terminal-per-turn excitations with the D6 polarity convention.
- The `generate_maxwell3d` CLI, the `run_aedt_maxwell3d.ps1` controlled runner, and the `aedt`-marked integration test.
- The M2 should-fix #2 unique-identifier guard (`unique_identifiers`).

Exit criterion is verified by `tools/run_aedt_maxwell3d.ps1` plus a manual open in AEDT 2025 R2 Commercial (evidence gitignored under `artifacts/maxwell3d/`). The `aedt`-marked integration test is the arbiter for exact PyAEDT keyword names; the adapter was fixed to match the installed pyaedt 1.2.0 API (`assign_matrix` schema, `validate_simple`) during verification.

## Milestone 4: Maxwell 2D and DC operating point compatibility

- Generate the documented 2D equivalent cross-sectional model.
- Use native 3D Include DC Fields where supported.
- Implement the AEDT 2024 R2 Magnetostatic plus incremental-linearization fallback.
- Make approximations and capability differences visible in the project manifest and UI.

Exit criterion: release-matrix fixtures generate valid projects and identify native versus approximate operating-point treatment.

### Current state

Milestone 4 is **accepted** as of 2026-07-17. Live verification ran on AEDT
2025 R2 Commercial in four rounds; each round's defect was fixed and
re-verified on the real machine:

1. The 2D region silently failed (`create_air_region` is 3D-only; the 2D XY
   API is `create_region(pad_value, pad_type)`), and stage failures discarded
   the project. Fixed with the correct call, falsy-return guards on pyaedt
   calls, and a diagnostic save on any stage failure.
2. Maxwell 2D AC Magnetic requires an explicit outer boundary; a balloon
   boundary is now assigned on the region edges.
3. Non-graphical AEDT rejects design-settings writes on an empty design, so
   the 2D model depth is set after geometry exists.
4. The native DC guesses (`IncludeDcFields` setup property, `DCValue` winding
   property) were silently ignored by AEDT. The verified mechanism is the
   **"AC Magnetic with DC" solution type** plus the per-winding
   **`DC Current`** property, both confirmed persisted in the saved project.
   pyaedt 1.2.0's `assign_matrix` does not support that solution type, so the
   3D adapter assigns the matrix through the raw `MaxwellParameterSetup`
   module.

Accepted evidence: the `aedt`-marked 2D and 3D export tests pass against
AEDT 2025.2 Commercial; a full 15-stage native-DC 3D generation (all stages
succeeded, design validation passed, `'DC Current'='5A'` persisted for both
windings, `Matrix1` assigned) ran via `tools/generate_maxwell3d.py`; the 2D
runner generated, validated, and simulated a project reviewed by Fabio
Posser. The matrix row `2025.2/commercial` now records
`includeDcFields3d: true` (live probe, 2026-07-17) with the two discovered
pyaedt limits. Implemented deliverables:

- The `MatrixCapabilityRepository` loader turning
  `compatibility/aedt-matrix.yml` rows into `CapabilitySnapshot` values.
- DC-bias strategy selection (`select_dc_bias_strategy`) wired into 3D
  generation: native DC through the "AC Magnetic with DC" solution type and
  per-winding `DC Current` values when the matrix confirms support; the
  2024 R2 magnetostatic-incremental fallback and the 2D case are identified
  in the manifest but blocked from generation (decision D4, 2026-07-16 — no
  2024 R2 installation exists, and the fallback is a physical no-op until
  Milestone 5's nonlinear material data).
- The Maxwell 2D stack: solver-independent plan types and `build_maxwell2d_plan`
  from `PlanarModel`, the `Maxwell2dExporter` application port, the staged
  `PyaedtMaxwell2dExporter` (14 stages including launch and save), the
  `generate_maxwell2d` CLI, and `tools/run_aedt_maxwell2d.ps1`.
- Generation manifest schema version 2, adding `dimension`, `dcBias`, and
  `capabilities` blocks alongside the existing stage record.
- A Guided Studio Simulation summary showing the selected DC-bias strategy
  and approximation status.
- The exit-criterion integration test, `tests/integration/test_release_matrix.py`.

The 2024 R2 rows stay `out-of-scope` per D4 and were not part of this
acceptance.

## Milestone 4.5: Automation interfaces — MCP server and FEMM 2D backend

Requirements added 2026-07-17 by Fabio Posser:

- Expose the designer over MCP so an AI client can create projects, validate
  them, generate solver designs, run simulations, and read results by itself.
- Offer FEMM (https://www.femm.info) as a user-selectable alternative to
  Ansys Maxwell for the 2D equivalent model, including an in-loop solve with
  R/L result extraction.

- Translate the solver-independent 2D design plan to a FEMM planar problem
  (circuits with signed one-turn conductor blocks, linear materials,
  asymptotic open boundary), solve headless, and extract per-winding
  impedance results.
- Select the 2D backend per call (CLI flag, MCP argument); project files stay
  backend-agnostic.
- Serve catalog, project, generation, and solve operations as MCP tools over
  stdio behind an optional extra.

Exit criterion: an MCP client session can create a valid project, generate a
ready-to-solve Maxwell design, run a FEMM solve of the 2D equivalent, and
read back per-winding R/L — with the backend chosen per call.

### Current state

Milestone 4.5 is implementation complete and live-verified on FEMM 4.2 the
same day (2026-07-17). Evidence:

- `INDUCTOR_FEMM_LIVE=1 pytest tests/integration/femm -m femm` passed against
  the real FEMM 4.2 installation. One live fix was needed: the core
  bore-interior air region (`r < r_inner`) had no material label, causing
  FEMM analysis to fail; a second air block label at the origin fixed it
  (commit `f30e662`).
- A live CLI solve, `python -m tools.generate_maxwell2d --backend femm
  --force-2d` on the sample fixture, produced
  `artifacts/femm-check/M2_golden_sample_2d.fem` with all stages green and
  symmetric results: windings w1/w2 both R ≈ 0.00854 Ω, L ≈ 15.16 µH at
  100 kHz.
- The exit-criterion integration test, `tests/integration/test_mcp_session.py`,
  drives the full session (list cores, save project, validate, geometry
  summary, generate Maxwell 3D, generate 2D on the FEMM backend, read back
  the manifest) against the pure MCP tool functions with no error dicts.

Implemented deliverables mirror the plan: pure FEMM problem translation
(`adapters/femm/model.py`), the `FemmSolver` port with a recording fake and
the pyfemm adapter (`adapters/femm/solver.py`), backend dispatch
(`Backend2d`, `export_femm2d`) and FEMM manifests in
`application/services/maxwell_export.py`, the `--backend`/`--no-analyze` CLI
flags on `generate_maxwell2d`, nine pure MCP tool functions
(`mcp_server/tools.py`) registered by a FastMCP stdio server
(`mcp_server/server.py`, the `inductor-designer-mcp` console script), and a
Guided Studio backend selector and Generate action.

Deferred/known limits: circuit phase is not yet applied to FEMM circuits
(magnitude-only excitation; a message is emitted when a circuit's phase is
nonzero); loss integrals are deferred to Milestone 5 alongside nonlinear
material data. See `docs/development/automation-mcp-femm.md` for the full
procedure, tool list, and verified-limits detail.

Milestone 4.5 is **accepted** as of 2026-07-17: Fabio Posser validated the
FEMM results and the Guided Studio generation flow. Driving
`inductor-designer-mcp` from an external MCP client remains an open
follow-up validation and does not gate the milestone.

## Milestone 5: Material Studio

- Import material characteristics only from CSV or XLSX spreadsheets.
- Select material identities, revisions, and curve series; inspect canonical plots; edit table points; fit supported models; validate units and physics; and preserve provenance.
- Export only approved material revisions to Maxwell.

Exit criterion: a reviewer can reproduce a material record from its stored source metadata and transformation history.

### Current state

Milestone 5a is **implementation complete but not accepted** as of 2026-07-18.
The automated exit-criterion integration proof is green; a real approved
datasheet record and live AEDT/FEMM handoff are still pending. No real material
datasheet has been approved and no solver behavior from this milestone is
claimed as live-verified.

Implemented Tasks 1–12 deliver:

1. canonical T/mT/G/kG, A/m/kA/m/Oe, and W/m³/kW/m³/mW/cm³ conversions;
2. immutable material records with provenance and draft/reviewed/approved states;
3. replayable canonical table points and per-series CSV provenance;
4. stdlib Steinmetz fitting and B-H-derived mean relative permeability;
5. unit-family, range, origin, monotonicity, duplication, slope, condition, and fit validation;
6. deterministic JSON and CSV serde, SHA-256 provenance, and content-derived revision IDs;
7. the repository port, in-memory fake, and atomic filesystem overlay with approved immutability, source-hash checks, and CSV/JSON agreement checks;
8. canonical CSV import, draft construction, validation-gated review/approval, and optional loss fitting;
9. full replay of source hashes, CSV transformations, fitted values, and revision identity;
10. project schema v3 with exact material revision snapshots and v2 migration;
11. approved nonlinear material export to Maxwell 2D/3D and FEMM, including ferrite unblock, explicit revision arbitration, manifest evidence, and rejection of ambiguous multiple B-H series; and
12. the reproduction CLI plus an end-to-end integration test covering tamper detection and solver-manifest propagation.

The FEMM adapter uses the verified pyFEMM API spelling: singular
`mi_addbhpoint(name, b, h)` once per point, not `mi_addbhpoints`. PyAEDT export
sets nonlinear permeability with `(B, H)` pairs and requires a truthy result
from `set_power_ferrite_coreloss(cm, x, y)`.

Packaged `material-import-template.csv` and `material-import-template.xlsx`
resources, strict CSV/XLSX upload parsers, editable current-material workbook
export, and new-draft reimport are implemented. They accept retained datasheet
units including `A/m`, `Oe`, and `mW/cm3` while normalizing points to canonical
SI units. The end-to-end integration test covers template import,
review/approval, overlay persistence, replay, export, edit, and immutable-base
reimport.

Automated evidence covers fresh overlay save/load/replay, tampered record and
source failures, schema v3 snapshot propagation, and recording-fake Maxwell 3D
and FEMM manifests with a pinned revision and nonzero B-H point count. Full
M5a non-live quality evidence is recorded in the Task 13 handoff commit.

The 2026-07-20 spreadsheet-only redesign removes the unused image/PDF workflow
because no user materials have been imported. Material Studio downloads CSV/XLSX
templates, exports any selected revision as editable XLSX, reimports edits as a
distinct draft, shows validation and fit results, lists every lifecycle revision,
plots the selected canonical series, and performs explicit draft/review/approve
transitions. The latest approved badge is advisory only. Project schema v4
migrates v3 selections with `bhSeriesId: null`, and the user must explicitly pin
one approved revision and B-H series when multiple series exist. Recording
Maxwell 2D/3D and FEMM exports consume only that pinned snapshot and series.

M5b is **implementation ready but pending native acceptance evidence**, not complete:
the whole-change review and fresh complete suite/static gates pass, while native
Windows manual UI acceptance has not yet been recorded. This computer cannot provide
the required native Windows/high-DPI/FileDialog and manual Excel-compatible
workbook evidence. It also has no live Ansys AEDT or FEMM material-validation
run for this milestone.

Remaining acceptance work and risks:

- Import, review, and approve a real Magnetics Kool Mu 60 B-H and core-loss source, then obtain `MATCH` from the reproduction CLI.
- Generate and open Maxwell 3D and FEMM outputs using that exact pinned revision; verify nonlinear B-H data and ferrite-loss coefficients in AEDT and every singular `mi_addbhpoint` result in FEMM.
- Confirm source licensing and redistribution rights before committing real datasheet bytes.
- On Windows, manually verify keyboard/focus, scaling, file dialogs, template
  download, Excel-compatible workbook edit/reimport, all revisions, lifecycle
  actions, and explicit B-H selection.

The completed M5b implementation work did not need live solver checks because it
uses the stable, automated M5a services. The real-record import and `MATCH`
reproduction plus live AEDT/FEMM handoff remain hard gates for formally accepting
either milestone and for making live-solver claims. Source licensing must be
confirmed before real datasheet bytes are committed or redistributed.

The implemented M5b scope is the Guided Studio spreadsheet-only workflow:
download CSV/XLSX templates, export any selected revision to editable XLSX,
reimport edits as a new draft, select a material/revision/series, inspect its
canonical curve plot, browse all revisions, perform review/approval, and pin one
exact approved revision and B-H series. See the [spreadsheet-only M5b
specification](../superpowers/specs/2026-07-20-material-studio-spreadsheet-only-design.md),
[ADR 0002](../adr/0002-spreadsheet-only-material-ingestion.md), and
[implementation plan](../superpowers/plans/2026-07-20-material-studio-spreadsheet-only.md).

Any future non-spreadsheet importer, OCR, image tracing, material MCP tool, or
explicit-formula record requires a separately approved specification and plan.

See also the [material records procedure](material-records.md) and the
[Milestone 5a implementation plan](../superpowers/plans/2026-07-17-material-records-pipeline.md).

## Milestone 6: Productization

- Package the Windows application with PyInstaller and Inno Setup.
- Package the AEDT extension separately.
- Add recovery, diagnostics, reports, release notes, checksums, and the controlled AEDT release checklist.

Exit criterion: the installer and extension pass the Commercial/Student compatibility matrix.

## Milestone 7: Additional core families

- Add E, PQ, EQ, EER, and other approved commercial geometries as independent geometry plugins.

Exit criterion: each family has its own catalog schema, geometry invariants, previews, Maxwell adapters, and integration fixtures.
