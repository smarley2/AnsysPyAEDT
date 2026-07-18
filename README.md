# PyAEDT Inductor Designer

PyAEDT Inductor Designer is a planned Windows desktop application and AEDT extension for creating parametric inductor models in Ansys Maxwell 2D and 3D through PyAEDT.

This is an independent open-source project. It is not affiliated with, endorsed by, or sponsored by Ansys, Inc. Ansys, Maxwell, and AEDT are trademarks of their respective owner.

The first product increment focuses on commercial toroidal powder and ferrite cores, round-wire windings, AC Magnetic simulations, multiple windings, material traceability, and compatibility with AEDT 2024 R2 or newer in Commercial and Student editions.

## Project status

Milestones 0–4.5 are accepted; their dates and live-verification scope are recorded in the [ROADMAP](docs/development/ROADMAP.md). Milestone 5a (material records pipeline and approved nonlinear solver export) is implementation complete as of 2026-07-18, and its automated exit proof is green. Packaged `material-import-template.csv` and `material-import-template.xlsx` resources, strict CSV/XLSX upload parsers, and editable selected-material workbook reimport are implemented for `A/m`, `Oe`, `mW/cm3`, and the other documented material units. It is not accepted yet: a real approved datasheet record and live AEDT/FEMM material handoff remain pending. Material Studio download/upload and revision UI, OCR, the optional GPL importer, and MCP material tools are planned for M5b.

- [Material records pipeline procedure](docs/development/material-records.md)
- [CSV material import template](src/inductor_designer/resources/material_templates/material-import-template.csv)
- [Excel material import template](src/inductor_designer/resources/material_templates/material-import-template.xlsx)
- [Milestone 5a material records plan](docs/superpowers/plans/2026-07-17-material-records-pipeline.md)
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
