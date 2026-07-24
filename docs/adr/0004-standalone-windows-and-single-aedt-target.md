# ADR 0004: Standalone Windows Product and Single AEDT Target

- Status: Accepted
- Date: 2026-07-24

## Context

The original product design included both a standalone Windows application and
an AEDT extension, with certification across AEDT 2024 R2 and newer Commercial
and Student editions. Only AEDT 2025 R2 Commercial is available for controlled
validation, and the standalone application already covers design authoring,
project generation, optional solving, and opening the generated project in AEDT.
Maintaining an extension and untestable compatibility paths would delay the
missing Guided Studio and result workflow.

## Decision

Ship only the standalone Windows application and support only AEDT 2025 R2
Commercial. Remove AEDT 2024 R2, Student, and magnetostatic-fallback product
policies. Generated AEDT projects are independent outputs that users may edit
directly; the application does not provide an AEDT extension or round-trip
edited `*.aedt` files.

## Consequences

- Packaging and release validation have one product surface and one AEDT row.
- Unsupported releases and editions are not implied by generic adapter code.
- Existing historical evidence remains valid history but establishes no current
  support claim outside AEDT 2025 R2 Commercial.
- Adding another AEDT release, edition, extension, or round-trip workflow
  requires a new approved specification and observed compatibility evidence.
