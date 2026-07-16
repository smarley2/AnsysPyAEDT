# PyAEDT Inductor Designer

PyAEDT Inductor Designer is a planned Windows desktop application and AEDT extension for creating parametric inductor models in Ansys Maxwell 2D and 3D through PyAEDT.

This is an independent open-source project. It is not affiliated with, endorsed by, or sponsored by Ansys, Inc. Ansys, Maxwell, and AEDT are trademarks of their respective owner.

The first product increment focuses on commercial toroidal powder and ferrite cores, round-wire windings, AC Magnetic simulations, multiple windings, material traceability, and compatibility with AEDT 2024 R2 or newer in Commercial and Student editions.

## Project status

Milestone 0 is accepted as of 2026-07-13, scoped to the AEDT 2025 R2 Commercial release verified on the development machine; the 2024 R2 (Commercial and Student) and 2025 R2 Student rows stay `out-of-scope` until a later milestone targets them. Milestone 1 (toroid domain and catalogs) is accepted as of 2026-07-14, with powder-core records reviewed against the 2025 Magnetics catalog and ferrite records still draft. Milestone 2 (geometry and live preview) is accepted as of 2026-07-15, with the one-closed-loop-per-turn winding model confirmed in the interactive preview; the five ferrite core records remain draft. Milestone 3 (Maxwell 3D MVP) is accepted as of 2026-07-16, with all 15 export stages succeeding on AEDT 2025 R2 Commercial and the generated project passing design validation. Milestone 4 (Maxwell 2D and DC operating-point compatibility) is implementation complete, pending Fabio Posser's live verification on AEDT 2025 R2 Commercial before acceptance (see [ROADMAP](docs/development/ROADMAP.md)).

- [Maxwell 2D generation procedure](docs/development/maxwell2d-generation.md)
- [DC operating-point compatibility](docs/development/dc-bias-compatibility.md)
- [Active implementation plan (Milestone 3)](docs/superpowers/plans/2026-07-16-maxwell3d-mvp.md)
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
