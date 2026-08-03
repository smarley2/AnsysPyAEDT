# Development Roadmap

> **Current authority:** The
> [2026-07-24 MVP roadmap realignment](../superpowers/specs/2026-07-24-mvp-roadmap-realignment-design.md)
> replaces the remaining delivery sequence and narrows the product to the
> standalone Windows application and AEDT 2025 R2 Commercial. Milestones 0–6
> below retain their historical implementation and acceptance evidence; the
> active sequence now begins with M7 and continues through M11.

## Milestone 0: Foundation and compatibility spike

- Establish Python packaging, quality gates, schemas, CI, and documentation.
- Prove connection to the available AEDT release through PyAEDT.
- Prove a minimal PySide6/QML application and Qt Quick 3D preview.
- Record observed compatibility evidence without inferring unsupported targets.

Exit criterion: a documented spike creates and saves a trivial Maxwell 2D and 3D design without domain-to-PyAEDT coupling.

### Current state

Milestone 0 is **accepted** as of 2026-07-13. Acceptance scope is deliberately
limited to the AEDT 2025 R2 Commercial release available on the development
machine. The 2026-07-24 scope decision permanently removes 2024 R2 and Student
rows from the active product roadmap; they do not become required in a later
milestone without a new approved scope decision. Milestone 1 is unblocked.

Implemented foundation deliverables:

- Python packaging and quality gates, including dependency-boundary enforcement.
- A versioned project-envelope schema and repository adapter.
- Solver-independent AEDT capability policy.
- The AEDT gateway contract, recording fake, and lazy PyAEDT adapter.
- A machine-readable compatibility-spike CLI.
- A minimal PySide6/QML Guided Studio shell with a Qt Quick 3D preview smoke path.
- A hosted non-AEDT CI definition.
- A controlled AEDT runner, compatibility procedure, and the historical
  four-row release/edition matrix. M5a reduces the active support data to the
  single current target.

Verified non-AEDT evidence:

- [Hosted CI run 29234286379](https://github.com/smarley2/AnsysPyAEDT/actions/runs/29234286379) passed for commit `1f24ff3` with the quality job and Windows and Ubuntu test jobs on Python 3.10 and 3.13. The quality job covered Ruff, mypy, and architecture checks; every test job installed UI dependencies and ran the non-AEDT coverage suite.
- Non-AEDT quality, architecture, unit, and contract gates have been exercised locally.
- Package installation and UI smoke checks have been exercised locally.
- Fresh release decisions must use the reproducible gates in the [validation plan](VALIDATION_PLAN.md), rather than treating this status summary as current test evidence.

Remaining evidence:

- The 2025 R2 Commercial row is reviewed and passed (evidence on disk under `artifacts/compatibility/2025.2-commercial/`, gitignored).
- Historical 2024 R2 and Student rows are `out-of-scope` and establish no
  current support claim.

Task 11 is closed: the 2025.2 Commercial review is accepted and the remaining
Milestone 0 gates pass. Milestone 1 is unblocked.

## Milestone 1: Toroid domain and catalogs

- Implement units, project schemas, commercial core records, conductor records, winding sectors, and validation.
- Import a reviewed subset of Magnetics commercial powder-core and ferrite toroids.
- Build the canonical-files-to-SQLite catalog pipeline.

Exit criterion: a versioned project selects a commercial core, defines multiple valid windings, and survives schema round trips.

### Current state

Milestone 1 is **accepted** as of 2026-07-14. Its historical round-trip,
catalog-snapshot, and adoption behavior remains covered by persistence and
catalog-revision tests; `tests/integration/test_project_round_trip.py` now owns
the M6 exit criterion. The ten powder-core records are reviewed against the
2025 Magnetics Powder Cores Catalog. The five ferrite records remain `draft`
until the ferrite catalog review; insulated wire diameters are populated and
reviewed as part of Milestone 2, which consumes them.

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
- Identify unsupported operating-point paths and block them explicitly.
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
  per-winding `DC Current` values when the matrix confirms support. Historical
  2024 R2 and 2D fallback candidates were identified but blocked from
  generation. The 2026-07-24 support decision removes the 2024 strategy from
  active scope instead of implementing it.
- The Maxwell 2D stack: solver-independent plan types and `build_maxwell2d_plan`
  from `PlanarModel`, the `Maxwell2dExporter` application port, the staged
  `PyaedtMaxwell2dExporter` (14 stages including launch and save), the
  `generate_maxwell2d` CLI, and `tools/run_aedt_maxwell2d.ps1`.
- Generation manifest schema version 2, adding `dimension`, `dcBias`, and
  `capabilities` blocks alongside the existing stage record.
- A Guided Studio Simulation summary showing the selected DC-bias strategy
  and approximation status.
- The exit-criterion integration test, `tests/integration/test_release_matrix.py`.

The 2024 R2 rows were not part of this acceptance and are not current product
targets.

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
- A live CLI solve using the historical pre-M6 FEMM 2D override on the sample
  fixture produced
  `artifacts/femm-check/M2_golden_sample_2d.fem` with all stages green and
  symmetric results: windings w1/w2 both R ≈ 0.00854 Ω, L ≈ 15.16 µH at
  100 kHz.
- The exit-criterion integration test, `tests/integration/test_mcp_session.py`,
  drives the full session (list cores, save project, validate, geometry
  summary, generate Maxwell 3D, generate 2D on the FEMM backend, read back
  the manifest) against the pure MCP tool functions with no error dicts.

The original M4.5 deliverables included pure FEMM problem translation, the
`FemmSolver` port and pyfemm adapter, 2D backend dispatch, FEMM-specific
manifests, nine pure MCP tool functions registered by a FastMCP stdio server,
and a Guided Studio backend selector. M6 retained those external capabilities
while replacing the backend dispatch and separate manifests with shared Run
Requests and Run Manifests. The current `generate_maxwell2d` CLI selects
`--backend aedt|femm` and always submits Generate Only.

The original M4.5 adapter deferred FEMM circuit phase. The M6 final-review fix
now converts the planned AC peak magnitude and phase to one complex FEMM
circuit-current phasor at the adapter boundary without another RMS conversion.
Nonlinear material transfer was implemented in M5; normalized loss and
field-result extraction belongs to M8. See
`docs/development/automation-mcp-femm.md` for the full procedure, tool list, and
verified-limits detail.

Milestone 4.5 is **accepted** as of 2026-07-17: Fabio Posser validated the
FEMM results and the Guided Studio generation flow. Driving
`inductor-designer-mcp` from an external MCP client remains an open
follow-up validation and does not gate the milestone. The existing MCP surface
is retained, but no MCP expansion, parity, or validation work belongs to
M5a–M11.

## Milestone 5: Material Studio

- Import material characteristics only from CSV or XLSX spreadsheets.
- Select material identities, revisions, and curve series; inspect read-only canonical plots; validate units and physics; and preserve provenance.
- Export imported or approved material revisions to Maxwell.

Exit criterion: a reviewer can reproduce a material record from its stored source metadata and transformation history.

### Current state

Milestone 5a is **accepted (2026-07-28, Fabio Posser)**. The High Flux 60
validation revision `94e880a99b98` reproduces as `MATCH` and reaches AEDT 2025 R2
Commercial in both 3D and 2D and FEMM 4.2 with its full 501-point nonlinear B-H
curve and its Steinmetz coefficients. Evidence is recorded in
`m5a-live-material-validation.md`.

Acceptance additionally required making the exported design **solve**, which it
originally did not. `AC Magnetic with DC` failed while mapping the DC field onto
the AC mesh across curved surfaces. The shipping fix is 16-sided conductors plus
TAU initial mesh settings with curvilinear meshing disabled; both halves are
needed. See `dc-bias-solve-limitation.md`. The lesson worth carrying forward is
that design validation passing is not evidence that a design solves — M4 and M5a
both relied on it and shipped a non-solving export unnoticed.

Mass density, also found during that work, is now a required record field with a
mandatory Material Studio template column, written to the AEDT material by both
adapters. Because revision ids are content-derived, the original validation
material `2271f4f7644f` had to be re-imported to gain its 8176 kg/m³ and became
`94e880a99b98`, with all curve data unchanged.

The PyAEDT unit defect found alongside it is also fixed: `set_power_ferrite_coreloss`
tagged `core_loss_cm` with `A_per_meter` and `core_loss_x` with `tesla`, and both
adapters now rewrite them as plain numbers, matching Ansys' shipped libraries.
Verified in live 3D and 2D projects.

Implemented Tasks 1–12 deliver:

1. canonical T/mT/G/kG, A/m/kA/m/Oe, and W/m³/kW/m³/mW/cm³ conversions;
2. immutable material records with provenance and imported plus legacy lifecycle states;
3. replayable canonical table points and per-series CSV provenance;
4. stdlib Steinmetz fitting and B-H-derived mean relative permeability;
5. unit-family, range, origin, monotonicity, duplication, slope, condition, and fit validation;
6. deterministic JSON and CSV serde, SHA-256 provenance, and content-derived revision IDs;
7. the repository port, in-memory fake, and atomic filesystem overlay with approved immutability, source-hash checks, and CSV/JSON agreement checks;
8. canonical CSV/XLSX import, immediate imported-revision construction, validation, and optional loss fitting;
9. full replay of source hashes, CSV transformations, fitted values, and revision identity;
10. project schema v3 with exact material revision snapshots and v2 migration;
11. imported/approved nonlinear material export to Maxwell 2D/3D and FEMM, including ferrite unblock, explicit revision arbitration, manifest evidence, and rejection of ambiguous multiple B-H series; and
12. the reproduction CLI plus an end-to-end integration test covering tamper detection and solver-manifest propagation.

The FEMM adapter uses the verified pyFEMM API spelling: singular
`mi_addbhpoint(name, b, h)` once per point, not `mi_addbhpoints`. PyAEDT export
sets nonlinear permeability with `(B, H)` pairs and requires a truthy result
from `set_power_ferrite_coreloss(cm, x, y)`.

Packaged `material-import-template.csv` and `material-import-template.xlsx`
resources, strict CSV/XLSX upload parsers, immediate imported-revision
persistence, replacement/deletion guards, and read-only Material Studio are
implemented. They accept retained datasheet units including `A/m`, `Oe`, and
`mW/cm3` while normalizing points to canonical SI units. Loss imports add the
solver-required origin to stored/generated data without changing the uploaded
workbook. The end-to-end integration tests cover template import, overlay
persistence, replay, replacement, explicit project pinning, and read-only
plotting.

Automated evidence covers fresh overlay save/load/replay, tampered record and
source failures, schema v3 snapshot propagation, and recording-fake Maxwell 3D
and FEMM manifests with a pinned revision and nonzero B-H point count. Full
M5a non-live quality evidence is recorded in the Task 13 handoff commit.

The 2026-07-23 approved read-only redesign removes the unused image/PDF and UI
editing workflows because spreadsheets are the source of truth. Material Studio
downloads CSV/XLSX templates, imports valid files immediately as `imported`,
loads the newest stored revision with one material click, downloads the selected
material as editable XLSX, previews canonical series with linear/log axes,
replaces or deletes materials with project-reference guards,
and explicitly pins one imported/approved revision and B-H series when multiple
series exist. Project schema v4 migrates v3 selections with `bhSeriesId: null`.
Recording Maxwell 2D/3D and FEMM exports consume only that pinned snapshot and
series.

The spreadsheet import and local material-library slice of M5b was **accepted
for the MVP on 2026-07-23**. Acceptance covers template download, CSV/XLSX
import, immediate persistence, one-click saved-material loading, read-only curve
visualization, selected-material XLSX download, replacement, and guarded
deletion. M5b is closed. Native Windows packaging/high-DPI acceptance belongs
to M10, while live Ansys AEDT/FEMM material consumption belongs only to the M5a
closeout.

Completed M5a acceptance work:

- Ran and inspected the controlled AEDT 2025 R2 Commercial handoff using exact
  revision `94e880a99b98`, in Maxwell 3D and Maxwell 2D, plus FEMM 4.2.
- Recorded sanitized AEDT and FEMM evidence with exact tool versions and the
  redistribution decision, committing no generated solver output.
- Ran the final non-solver, UI, static, architecture, and controlled-material
  gates.
- Made the exported 3D design solve, which acceptance originally rested on
  without anyone having checked it.

Remaining M10 productization work:

- On Windows, manually verify keyboard/focus, scaling, file dialogs, template
  and selected-material download, Excel-compatible workbook replacement, delete
  confirmation, and explicit B-H selection.

The completed M5b implementation work did not need live solver checks because it
uses the stable, automated M5a services. The recorded `MATCH` and FEMM
inspection do not establish AEDT material support or close M5a without the
remaining controlled evidence and review.

The implemented M5b scope is the Guided Studio spreadsheet-only workflow:
download CSV/XLSX templates, import immutable revisions, replace/delete stored
materials, load the newest revision by selecting a material, download its XLSX,
inspect its read-only linear/log curve plot, and pin one exact
imported/approved revision and B-H series. See the
[approved read-only imported-material specification](../superpowers/specs/2026-07-23-material-studio-readonly-imported-design.md),
[ADR 0003](../adr/0003-read-only-imported-materials.md), and
[implementation plan](../superpowers/plans/2026-07-23-material-studio-readonly-imported.md).

Any future non-spreadsheet importer, OCR, image tracing, material MCP tool, or
explicit-formula record requires a separately approved specification and plan.

See also the [material records procedure](material-records.md) and the
[Milestone 5a implementation plan](../superpowers/plans/2026-07-17-material-records-pipeline.md).

## Milestone 5a closeout: Live material validation and support cleanup

- Remove AEDT 2024 R2, Student, and magnetostatic-fallback product policies.
- Keep AEDT 2025 R2 Commercial as the only supported target.
- Import a legally usable real material and obtain reproduction `MATCH`.
- Verify the exact pinned material revision in live Maxwell 3D and FEMM
  artifacts.

Exit criterion: `MATCH`, licensing handling, and live AEDT 2025 R2
Commercial/FEMM material-consumption evidence are accepted.

## Milestone 6: Project Foundation

- Replace fixed project dimensional mode with a backend-independent Design,
  Operating Point, and Simulation Recipe.
- Select Maxwell 3D, Maxwell 2D, or FEMM through a per-execution Run Request.
- Store one shared frequency plus winding and core temperatures in the
  Operating Point; remove frequency from individual windings.
- Store AC RMS current and convert it once to solver peak amplitude.
- Pin one exact compatible core-material revision and record Manual-core
  compatibility acknowledgment.
- Define Run Manifest and Normalized Result Set contracts.
- Represent unresolved core materials and the confirmed Maxwell 3D
  geometry-only operation.
- Introduce the replacement schema as a clean break; no legacy project
  migration is required.

Exit criterion: one Project document round-trips deterministically and creates
validated plans for all three backends with identical physical inputs and
explicit RMS/peak and material-state evidence.

### Current state

Milestone 6 is **accepted as of 2026-07-28**. Project schema v5 is the only
supported schema and is a deliberate clean break. One backend-independent
Project document now owns Design, one shared-frequency Operating Point with
separate winding/core temperatures, and one Simulation Recipe. A Run Request
selects Maxwell 3D, Maxwell 2D, or FEMM without mutating the Project document.

The accepted implementation:

- pins one exact compatible imported/approved material revision and B-H series
  and persists Manual-core compatibility acknowledgment;
- converts AC RMS current to AC peak exactly once in solver-independent
  planning and feeds identical effective inputs to all three backends;
- records immutable backend-labeled Run Manifest and Normalized Result Set
  contracts;
- routes Generate Only through recording/live adapter ports and preserves
  truthful failed-run evidence;
- carries generation-permitted validation warnings into Run Manifests and
  requires exact operation-specific Maxwell stage sequences for success;
- writes and loads standards-compliant finite-number-only v5 JSON;
- blocks Generate and Solve until M8; and
- permits unresolved material only for a separately confirmed Maxwell 3D
  Geometry-Only artifact with no solve-ready stages or DC-capability gate.

Acceptance is proven by
`tests/integration/test_project_round_trip.py`, the three M6 golden Run
Manifests, and the complete non-live quality gate recorded in the
[implementation-plan index](../superpowers/plans/README.md). No M6 catalog,
material value, B-H/core-loss data, conductor-facet setting, or initial Maxwell
mesh setting changed. The remaining test-suite ResourceWarnings are recorded
as a non-blocking cleanup risk in that index.

M7 consumes these contracts and the already-approved
[Preliminary calculations and Guided flow design](../superpowers/specs/2026-07-26-preliminary-calculations-and-guided-flow-design.md).
Its detailed implementation plan will be written separately before M7
implementation.

## Milestone 7: Guided Studio

- Implement New/Open/Save for compatible shareable Project documents.
- Implement the `Core & Material`, `Windings`, `Preliminary`, `Simulation`, and
  `Review` flow.
- Filter catalog cores and material revisions in both directions.
- Open Material Studio in a separate window and refresh material choices when
  it closes.
- Support catalog and Manual toroidal cores and complete winding authoring.
- Enforce numeric editors and enumerated selectors at the UI boundary.
- Calculate and display solver-independent preliminary B, J, DC-resistance
  wire loss, and supported core loss.
- Make the preview reactive to valid geometry edits.
- Select a backend and execute Generate Only through the existing adapters.
- Save every run in a new normalized `runs/<run-id>-<backend>/` directory next
  to the Project document, using project-relative manifest artifact paths.
- Run solvers in background/non-graphical mode by default, allow a visible
  solver window where supported, and expose actions to open the generated
  native file or run folder.
- Display validation, approximations, and informational Symmetry Suggestions.
- Remove the hardcoded startup Design.

Exit criterion: a user starts with an empty Project document, authors and
reviews a toroidal Design, inspects traceable preliminary estimates or explicit
unavailable reasons, saves and reopens it, and generates each supported backend
artifact. A materialless Manual core can generate only a confirmed geometry-only
Maxwell 3D artifact.

Detailed requirements and physical assumptions:
[2026-07-26 preliminary calculations and Guided flow](../superpowers/specs/2026-07-26-preliminary-calculations-and-guided-flow-design.md).
Run artifact and solver visibility decision:
[ADR 0007](../adr/0007-project-local-run-artifacts-and-solver-visibility.md).

## Milestone 7a: Solver-independent preliminary estimator

M7 is split into three independently testable plans (M7a/M7b/M7c); see the
[implementation-plan index](../superpowers/plans/README.md) for the split
rationale. This section records only the first slice.

- Compute B (DC, min, max, AC peak, peak magnitude), current density
  (`J_AC_RMS`, `J_AC_peak`, `J_DC`), DC-resistance wire loss, and B-H/loss-table
  or Steinmetz-fallback core loss, each as one independently reported quantity.
- Refuse core loss under DC bias when the material's loss data was recorded
  only at zero bias, instead of interpolating or extrapolating a correction.
- Keep the estimator free of Qt, PyAEDT, FEMM, and SQLite: it consumes already
  resolved catalog and material records rather than repositories.
- Report every unavailable quantity with a stable diagnostic code and English
  text; never omit a quantity silently.

Exit criterion: the estimator reproduces traceable estimates for the real
shipped material overlay revision (`Magnetics / High Flux / 60`) and the real
core catalog record (`C058071A2`) with 5 A DC per winding, correctly refusing
core loss for that DC bias because the material's loss series was recorded
only at 0 A/m, and a clean-interpreter import of the estimator module pulls in
none of `PySide6`, `ansys`, `femm`, or `sqlite3`.

### Current state

Milestone 7a is **accepted as of 2026-07-29 (Fabio Posser)**, squash-merged to
`main` as `4f56e41`. Acceptance evidence is
`tests/integration/test_preliminary_estimator.py`, run against the real
`materials-overlay` revision `94e880a99b98` and the real `catalog/` record
`C058071A2` with no fixture substitution. On the merged result the full
non-solver suite passed 889 tests and the offscreen UI suite passed 37;
`ruff check .`, `mypy src tools`, `tools/check_architecture.py` and
`git diff --check` all passed. No live AEDT or FEMM solver was used or required.

Two whole-branch review waves closed four Critical findings, every one of them a
defect in the plan rather than in the implementation: a totals rule that
contradicted the plan's own no-partial-sums constraint; a turn-count parameter
that duplicated `WindingDefinition.turns` and could silently override the design
while still reporting an estimate; a Steinmetz fit applied across temperatures it
was not fitted for; and a temperature diagnostic that offered advice which could
never succeed.

One in-scope physics decision is worth recording, because it makes core loss
unavailable more often than a looser reading would. Specification section 8
requires that every source sample behind a Steinmetz fit support the requested
temperature and DC-bias condition, but the stored fit pools all recorded loss
series regardless of condition. The estimator therefore refuses the fit whenever
any loss series on the record mismatches the request
(`core_loss.fit_sources_mismatch_condition`). Recording condition provenance on
`SteinmetzFit` would be a material-schema change and was deliberately not taken.

## Milestone 7b: Project-local run artifacts

M7b implements
[ADR 0007](../adr/0007-project-local-run-artifacts-and-solver-visibility.md):
every generation run now writes into its own, non-overwriting
`<project-directory>/runs/<run-id>-<backend>/` directory next to the saved
Project document instead of a shared application-level output path.

- Run ids are UTC `YYYYMMDD-HHMMSS` timestamps, with a `-2`, `-3` ... suffix
  when an earlier run already owns the same second, so `runs/` sorts
  chronologically and an existing run directory is never overwritten.
- `run-manifest.json` is written by the application for both successful and
  failed runs; a run blocked before any adapter wrote discards its
  still-empty run directory instead of leaving debris behind.
- Manifest artifact paths are POSIX strings relative to the project
  directory.
- Generation runs background/non-graphical by default. A `visible_window_support`
  service reports, per backend (Maxwell 3D, Maxwell 2D, FEMM), whether a
  visible `Show solver window` choice is supported, with a reason when it is
  not, but it is not yet bound to any control; M7c still owns wiring it to
  the `Show solver window` choice.
- A new `PathOpener` port and its Windows `DesktopPathOpener` adapter hand a
  generated file or its run folder to the desktop shell.
- The Qt UI, the MCP server, and both CLI tools (`generate_maxwell3d`,
  `generate_maxwell2d`) all route through the single `start_project_run`
  entry point. The UI's old `artifacts/studio/<project-name>` output path and
  the MCP server's `output_root` containment check are gone; MCP
  `read_manifest` now requires the path of a `run-manifest.json` inside a run
  directory, and both MCP generate tools return a `runDirectory` key.

Exit criterion: a Generate Only run for each backend writes its own
`runs/<run-id>-<backend>/run-manifest.json` beside the saved project with
project-relative artifact paths, a second run never disturbs the first, and
an opt-in visible solver window works for each backend where the installed
solver supports it.

Detailed task-by-task plan and evidence:
[2026-07-30 M7b project-local run artifacts](../superpowers/plans/2026-07-30-m7b-project-local-run-artifacts.md).

### Current state

**M7b was accepted by Fabio Posser on 2026-07-30** and squash-merged to `main`
as `67ac851`.

Live acceptance evidence on AEDT 2025 R2 Commercial: three consecutive FEMM
runs and two Maxwell 3D runs each took their own `runs/<run-id>-<backend>/`
directory without disturbing an earlier one; every manifest recorded a
project-relative `runs/...` artifact path, an empty reserved `results/`, and a
run id equal to its directory name; all fifteen Maxwell 3D stages passed
including `Design validation passed` with DC applied to both windings; a run
blocked before any adapter wrote left no directory behind; the `-Graphical`
run showed the AEDT window and still succeeded, while the default run logged
`Non-graphical mode detected`; and the M5a live material suite (Maxwell 3D,
Maxwell 2D, FEMM) passed in 85 s.

Every Guided Studio screen remained M7c work at M7b acceptance time, including
the `Show solver window` control and the `Open generated file` / `Open run
folder` buttons that bind to the `PathOpener` port and run-directory contracts
this milestone delivered. M7c (below) has since implemented all of it.
`results/` population and Generate and Solve remain M8 work; M7b reserves an
empty `results/` directory but never writes into it.

M7a and M7b are both accepted. M7 as a whole is not complete until M7c ships.

## Milestone 7c: Guided Studio flow

M7c is the third and final M7 slice: the five-screen Guided Studio flow itself
— `Core & Material`, `Windings`, `Preliminary`, `Simulation`, `Review` — wired
to the M7a estimator and the M7b run services.

- Bidirectional core/material filtering that clears the incompatible side and
  never substitutes a selection.
- A separate `Open Material Studio` window (not a step) that refreshes the
  material library on close.
- Native numeric validators plus authoritative domain validation on every
  winding and operating-point input, and `ComboBox` selectors for enumerated
  values.
- Live, read-only preliminary B/J/wire-loss/core-loss estimates with
  assumptions, exclusions, units, and the pinned revision always visible.
- The `Show solver window` choice and `Open generated file` / `Open run
  folder` actions from ADR 0007.

Plan-level decisions taken with Fabio Posser on 2026-07-30, recorded in the
[implementation plan's Global Constraints](../superpowers/plans/2026-07-30-m7c-guided-studio-flow.md#global-constraints):

1. **Layout:** `Preliminary` and `Review` take the full workspace width with
   the geometry canvas hidden; the other three screens keep the canvas plus
   the right-hand context panel.
2. **Run gate:** `Generate` is disabled, with a visible reason, while the
   project has unsaved edits or no document path — a run never starts from
   state that is not on disk, and generation never saves the project itself.
3. **Units:** preliminary numbers display in engineering units (`mT`,
   `A/mm²`, `mΩ`, `mm`, `mm²`, `W`); the estimator keeps SI internally, and
   every conversion lives in one pure module, `ui/preliminary_rows.py`.
4. **Windings:** adding and removing windings is in scope. A new winding
   allocates its id and matching `WindingOperatingPoint` together; the last
   winding cannot be removed.
5. **Manual-core magnetic path:** a Manual core's path length and volume are
   computed from its entered dimensions
   (`l_e = pi * (outer_diameter + inner_diameter) / 2`,
   `A_e = ((outer_diameter - inner_diameter) / 2) * height`,
   `V_e = A_e * l_e`), always reported with a visible assumption note.
   Manufacturer effective values are never invented for a Manual core.

Exit criterion: a user authors, saves, reopens, inspects analytical
B/J/wire/core-loss estimates or explicit unavailable reasons, reviews, and
generates a non-hardcoded toroidal Design from the Windows UI. Generate and
Solve is intentionally not exposed — specification section 12 assigns solving
and `results/` population to M8.

### Current state

Milestone 7c implementation is **complete and awaiting Fabio Posser's
verification** (only he accepts a milestone). `main.py` now constructs and
shares one `ProjectSession`, one `SqliteCatalogRepository`, and one
`FileOverlayMaterialRepository` across all five controllers, so a material
imported in the Material Studio window is visible to the Core & Material
selector without a restart, and `session.projectChanged` drives the
Preliminary, Windings, and Review screens to refresh from every edit.
`tests/integration/test_guided_studio_flow.py` proves the specification
section 11 acceptance walk (a catalog core plus a real imported material
revision, and a Manual core with a computed magnetic path) end to end against
the real shipped catalog and material overlay, with no Qt window, Maxwell, or
FEMM involved.

One deliberate behavior change from the M6 design: pinning a material
revision no longer writes `*.inductor.json` on the spot. Task 8 of the M7c
plan deleted Material Studio's `Select for simulation` writer, so the Core &
Material screen pins into the session and the top-bar `Save` persists it —
which is also what the run gate above requires.

Still outstanding: the visual walkthrough of the wired application (launch
the Windows UI, check the step rail order, the Material Studio window, the
full-width Preliminary/Review layout, and the disabled-until-saved Generate
button) has not been performed in this headless environment and remains for
Fabio Posser to confirm.

M7a, M7b, and M7c together complete Milestone 7.

## Milestone 8: Simulation and Results

- Execute one Operating Point in Maxwell 3D, Maxwell 2D, and FEMM.
- Activate Generate and Solve in the Guided Studio.
- Reuse the M7 project-local run layout and populate normalized result
  artifacts without overwriting prior runs.
- Provide progress, cancellation, durable status, and failed-stage diagnostics.
- Honor AC RMS current and phase; enable DC bias only where live-validated.
- Extract R/L/Z, supported matrices, copper/core/total loss, magnetic energy,
  convergence, and solver diagnostics.
- Extract B and J maximum and Area-Weighted Mean values in peak and RMS
  conventions.
- Use deterministic Representative Cross Sections in 3D and direct regional
  area integration in 2D.
- Export normalized JSON and CSV with explicit unavailable reasons.

Exit criterion: controlled runs for all three backends produce traceable
Normalized Result Sets in which every requested quantity is evidenced or
explicitly unavailable.

## Milestone 9: Reliability

- Add autosave, crash recovery, and application-wide undo/redo.
- Recover interrupted runs without claiming partial success.
- Add actionable installation, license, material, file, and convergence errors.
- Produce redacted logs and a diagnostic bundle.

Exit criterion: forced UI and solver failures preserve the last valid Project
document and produce sufficient redacted evidence for diagnosis.

## Milestone 10: Windows Release

- Resolve packaged resources outside the source checkout.
- Package the application with PyInstaller and Inno Setup.
- Detect AEDT 2025 R2 Commercial and optional FEMM installation.
- Run the complete flow on a clean Windows installation.
- Publish release notes and checksums.

Exit criterion: the installed application completes authoring, generation,
optional solving, result export, save, and reopen against AEDT 2025 R2
Commercial.

## Milestone 11: Additional Core Families

- Add E, PQ, EQ, EER, and other approved commercial geometries as independent
  geometry components after the toroidal Windows release.

Exit criterion: each family has its own approved design, catalog/schema needs,
geometry invariants, preview, solver mapping, fixtures, and live evidence.

## Deferred beyond the active roadmap

- MCP expansion or parity.
- AEDT extension and edited-`*.aedt` round-trip.
- AEDT 2024 R2 and Student support.
- Automatic symmetry model generation.
- Automatic frequency, current, or parameter sweeps.
- Transient, thermal, mechanical, optimization, converter co-simulation,
  cloud, collaborative remote databases, and non-round conductors.
