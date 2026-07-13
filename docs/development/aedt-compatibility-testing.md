# AEDT Compatibility Testing

## Purpose

This controlled test verifies observed behavior. It does not infer support from an AEDT or PyAEDT version number.

## Current controlled-execution status

Controlled execution is in progress: AEDT 2025 R2 Commercial has been reviewed and passed. The 2024 R2 (Commercial and Student) and 2025 R2 Student rows are marked `out-of-scope` for Milestone 0 — the development machine has no matching executable or license — and become required again only when a later milestone targets them.

## Prerequisites

- Windows machine with the exact AEDT release and edition under test.
- A valid license for that edition.
- Python 3.10 virtual environment with `python -m pip install -e ".[dev,aedt]"` completed.
- No unrelated AEDT projects open; the runner starts and closes dedicated sessions.

## Run

From the repository root:

```powershell
.\tools\run_aedt_spike.ps1 -Release 2024.2 -Edition commercial -Graphical
```

Repeat with `student`, then with the latest installed Commercial and Student release values. Use graphical mode first because Student gRPC startup behavior must be observed rather than assumed.

## Review evidence

1. Compare `requestedEnvironment` with every artifact's `observedSession`. Stop and preserve the evidence without updating a matrix row if either AEDT session reports a different release or edition than requested.
2. Open both generated projects and confirm the named rectangle/box exists.
3. Confirm each project saves, closes, and reopens without a repair warning.
4. Record the exact PyAEDT version from `evidence.json`.
5. In Maxwell 3D, inspect whether the AC Magnetic/Eddy Current setup exposes Include DC Fields; do not set the value from a release number alone.
6. In the `manualReview` object in the ignored local `evidence.json`, record the inspected `includeDcFields3d` boolean, exact reproducible `discoveredLimits`, reviewer GitHub handle in `reviewedBy`, and ISO-8601 UTC review time in `reviewedAt`. These fields are intentionally null or empty when the spike finishes and must be completed only by the human reviewer. Do not include license server names, user names, or machine paths.
7. Update only the matching row in `compatibility/aedt-matrix.yml` to `passed` or `failed`, copy the manually reviewed values and exact PyAEDT version, and set `evidenceReviewedAt` and `evidenceReviewedBy` from the manual-review record. The generated `capabilities.reviewStatus` remains `unreviewed`; it is not approval evidence.
8. Delete local artifacts after the review if they are no longer needed. They must remain ignored by Git.

## Acceptance

Milestone 0 requires reviewed rows for AEDT 2024 R2 Commercial, AEDT 2024 R2 Student, the latest supported Commercial release, and the latest supported Student release. A failed row is valid evidence but blocks a support claim until its cause and policy are documented.
