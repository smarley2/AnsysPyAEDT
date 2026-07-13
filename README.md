# PyAEDT Inductor Designer

PyAEDT Inductor Designer is a planned Windows desktop application and AEDT extension for creating parametric inductor models in Ansys Maxwell 2D and 3D through PyAEDT.

This is an independent open-source project. It is not affiliated with, endorsed by, or sponsored by Ansys, Inc. Ansys, Maxwell, and AEDT are trademarks of their respective owner.

The first product increment focuses on commercial toroidal powder and ferrite cores, round-wire windings, AC Magnetic simulations, multiple windings, material traceability, and compatibility with AEDT 2024 R2 or newer in Commercial and Student editions.

## Project status

The Milestone 0 foundation implementation exists, and controlled AEDT validation is pending. The four required release/edition rows remain unverified, so Milestone 0 is not complete and Milestone 1 remains blocked.

- [Active implementation plan](docs/superpowers/plans/2026-07-13-foundation-compatibility-spike.md)
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
