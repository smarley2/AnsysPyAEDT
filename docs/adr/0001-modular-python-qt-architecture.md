# ADR 0001: Modular Python and Qt Architecture

- Status: Accepted; product-surface and support assumptions superseded by ADR 0004
- Date: 2026-07-12

## Context

The original product scope required both a Windows desktop application and an
AEDT extension across AEDT 2024 R2 and newer Commercial and Student releases.
ADR 0004 replaces that scope with a standalone Windows application for AEDT
2025 R2 Commercial only. The modularity and dependency-inversion decision in
this ADR remains accepted.

## Decision

Use a modular Python architecture with solver-independent domain, geometry, material, and simulation modules. Use PySide6 with Qt Quick/QML for the Guided Studio and Qt Quick 3D for the lightweight preview. Implement PyAEDT, persistence, preview, and catalog imports through adapters.

## Consequences

- The desktop application, CLI, and optional automation surfaces reuse the same application services.
- Most tests run without AEDT.
- AEDT version differences remain localized.
- Initial development requires explicit interfaces and mapping code.
- Direct PyAEDT calls from UI or domain modules are prohibited.
