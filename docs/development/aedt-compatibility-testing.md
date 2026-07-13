# AEDT Compatibility Testing

## Purpose

This controlled test verifies observed behavior. It does not infer support from an AEDT or PyAEDT version number.

## Current controlled-execution status

Controlled execution is pending because no supported AEDT executable was detected on the development machine. All four matrix rows remain unverified until a human operator completes the controlled runs and evidence review.

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

1. Open both generated projects and confirm the named rectangle/box exists.
2. Confirm each project saves, closes, and reopens without a repair warning.
3. Record the exact PyAEDT version from `evidence.json`.
4. In Maxwell 3D, inspect whether the AC Magnetic/Eddy Current setup exposes Include DC Fields; do not set the matrix value from release number alone.
5. Record exact reproducible Student restrictions in `discoveredLimits`; do not include license server names, user names, or machine paths.
6. Update only the matching row in `compatibility/aedt-matrix.yml` to `passed` or `failed`, copy booleans from reviewed evidence, and set ISO-8601 UTC review time and reviewer GitHub handle.
7. Delete local artifacts after the review if they are no longer needed. They must remain ignored by Git.

## Acceptance

Milestone 0 requires reviewed rows for AEDT 2024 R2 Commercial, AEDT 2024 R2 Student, the latest supported Commercial release, and the latest supported Student release. A failed row is valid evidence but blocks a support claim until its cause and policy are documented.
