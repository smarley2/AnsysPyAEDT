# ADR 0005: Backend-Independent Project Documents

- Status: Accepted
- Date: 2026-07-24

## Context

The current Project document stores a fixed 2D/3D mode, while the product must
run the same inductor through Maxwell 3D, Maxwell 2D, or FEMM. Keeping the
backend in the editable Design prevents legitimate cross-backend runs and makes
the UI reject a 2D backend when a Project document was created as 3D.

## Decision

Keep the `*.inductor.json` Project document backend-independent. It contains
the Design, one Operating Point, and a Simulation Recipe. A separate Run Request
selects Maxwell 3D, Maxwell 2D, or FEMM and produces a Run Manifest and
Normalized Result Set. Remove fixed `dimensionMode`. Generated solver projects
are independent outputs and never become the editable source of truth.

No user Project documents are in use, so the replacement schema is an explicit
clean break rather than a legacy migration.

## Consequences

- One shareable Project document can be evaluated by all supported backends.
- Backend approximations and capabilities belong to a run, not to the Design.
- UI, CLI, and future automation can reuse the same application services.
- Fixtures and examples move to the new schema without maintaining unused
  compatibility code.
