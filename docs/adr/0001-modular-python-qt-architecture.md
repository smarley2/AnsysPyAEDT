# ADR 0001: Modular Python and Qt Architecture

- Status: Accepted
- Date: 2026-07-12

## Context

The product must run as both a Windows desktop application and an AEDT extension, generate Maxwell 2D and 3D projects through PyAEDT, support AEDT 2024 R2 and newer releases, and remain testable without an AEDT license.

## Decision

Use a modular Python architecture with solver-independent domain, geometry, material, and simulation modules. Use PySide6 with Qt Quick/QML for the Guided Studio and Qt Quick 3D for the lightweight preview. Implement PyAEDT, persistence, preview, and catalog imports through adapters.

## Consequences

- The desktop application and AEDT extension reuse the same application services.
- Most tests run without AEDT.
- AEDT version differences remain localized.
- Initial development requires explicit interfaces and mapping code.
- Direct PyAEDT calls from UI or domain modules are prohibited.
