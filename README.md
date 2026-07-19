# PyAEDT Inductor Designer

PyAEDT Inductor Designer is a planned Windows desktop application and AEDT extension for creating parametric inductor models in Ansys Maxwell 2D and 3D through PyAEDT.

This is an independent open-source project. It is not affiliated with, endorsed by, or sponsored by Ansys, Inc. Ansys, Maxwell, and AEDT are trademarks of their respective owner.

The first product increment focuses on commercial toroidal powder and ferrite cores, round-wire windings, AC Magnetic simulations, multiple windings, material traceability, and compatibility with AEDT 2024 R2 or newer in Commercial and Student editions.

## Project status

Milestones 0–4.5 are accepted; their dates and live-verification scope are recorded in the [ROADMAP](docs/development/ROADMAP.md). Milestone 5a (material records pipeline and approved nonlinear solver export) is implementation complete as of 2026-07-18, and its automated exit proof is green. M5b Tasks 1-9 now implement the Guided Studio Material Studio workflow: CSV/XLSX template download and upload, editable selected-revision XLSX export/reimport, manual PNG/JPEG/PDF digitization, every-revision browsing, lifecycle actions, and explicit revision/B-H-series pinning in project schema v4. Their focused automated/non-live gates pass, but M5b is not yet implementation-complete: whole-change review, fresh complete gates, and native Windows manual acceptance remain pending. Formal M5a/M5b acceptance also requires a real approved datasheet record with `MATCH` and live verification of the exact pinned revision and series in AEDT and FEMM. OCR, automatic tracing, the optional GPL importer, material MCP tools, and explicit-formula records remain optional M5c scope; no M5c plan exists unless the spreadsheet/manual workflow proves insufficient.

- [Material records pipeline procedure](docs/development/material-records.md)
- [CSV material import template](src/inductor_designer/resources/material_templates/material-import-template.csv)
- [Excel material import template](src/inductor_designer/resources/material_templates/material-import-template.xlsx)
- [Milestone 5a material records plan](docs/superpowers/plans/2026-07-17-material-records-pipeline.md)
- [Milestone 5b Material Studio specification](docs/superpowers/specs/2026-07-19-material-studio-ui-design.md)
- [Milestone 5b Material Studio implementation plan](docs/superpowers/plans/2026-07-19-material-studio-ui.md)
- [MCP server and FEMM 2D backend automation](docs/development/automation-mcp-femm.md)
- [Maxwell 2D generation procedure](docs/development/maxwell2d-generation.md)
- [DC operating-point compatibility](docs/development/dc-bias-compatibility.md)
- [Milestone 3 plan](docs/superpowers/plans/2026-07-16-maxwell3d-mvp.md)
- [Maxwell 3D generation procedure](docs/development/maxwell3d-generation.md)
- [Milestone 2 plan](docs/superpowers/plans/2026-07-14-geometry-and-live-preview.md)
- [Milestone 1 plan](docs/superpowers/plans/2026-07-13-toroid-domain-and-catalogs.md)
- [Milestone 0 plan](docs/superpowers/plans/2026-07-13-foundation-compatibility-spike.md)
- [Implementation plan index](docs/superpowers/plans/README.md)
- [AEDT compatibility procedure](docs/development/aedt-compatibility-testing.md)
- [AEDT compatibility matrix](compatibility/aedt-matrix.yml)
- [Validation plan](docs/development/VALIDATION_PLAN.md)

Read the canonical design:

- [`docs/superpowers/specs/2026-07-12-pyaedt-inductor-application-design.md`](docs/superpowers/specs/2026-07-12-pyaedt-inductor-application-design.md)
- [`docs/superpowers/plans/README.md`](docs/superpowers/plans/README.md)
- [`docs/superpowers/plans/2026-07-13-foundation-compatibility-spike.md`](docs/superpowers/plans/2026-07-13-foundation-compatibility-spike.md)
- [`docs/architecture/README.md`](docs/architecture/README.md)
- [`docs/development/ROADMAP.md`](docs/development/ROADMAP.md)
- [`docs/development/coordination.md`](docs/development/coordination.md)

## Documentation language

Code, documentation, UI text, schemas, logs, commits, and GitHub content are written in English. The UI will be localization-ready, but the MVP ships with English text only.

## License strategy

Original project code is licensed under the Apache License 2.0. Third-party catalogs and data remain subject to their original terms. GPL-licensed material data is not bundled with the application; an optional importer must preserve attribution and licensing metadata.
