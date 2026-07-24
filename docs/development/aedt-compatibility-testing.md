# AEDT 2025 R2 Commercial Compatibility Testing

## Purpose

This controlled test verifies observed behavior for the only supported AEDT
target. It does not infer support from an AEDT or PyAEDT version number.

## Current status

AEDT 2025 R2 Commercial has reviewed foundation, Maxwell 2D, Maxwell 3D, and
native DC-bias evidence. Fresh milestone and release claims must repeat the
relevant checks. AEDT 2024 R2 and Student editions are out of product scope.

## Prerequisites

- Windows machine with AEDT 2025 R2 Commercial.
- A valid Commercial license.
- Python 3.10 virtual environment with
  `python -m pip install -e ".[dev,aedt]"` completed.
- No unrelated AEDT projects open; the runner starts and closes dedicated
  sessions.

## Run

From the repository root:

```powershell
.\tools\run_aedt_spike.ps1 -Release 2025.2 -Edition commercial -Graphical
```

Use graphical mode first so observed project state can be inspected directly.

## Review evidence

1. Compare `requestedEnvironment` with every artifact's `observedSession`.
   Stop without updating support evidence if the session is not exactly
   `2025.2` Commercial.
2. Open both generated projects and confirm the named rectangle or box exists.
3. Confirm each project saves, closes, and reopens without a repair warning.
4. Record the exact PyAEDT version from `evidence.json`.
5. In Maxwell 3D, verify the `AC Magnetic with DC` solution type and persisted
   per-winding `DC Current` property when the test requests DC bias.
6. Record reproducible discovered limits, reviewer identity, and ISO-8601 UTC
   review time without license-server names, local user names, or machine paths.
7. Update only the `2025.2/commercial` compatibility evidence after human
   review.
8. Delete local artifacts when no longer needed; never commit generated AEDT
   projects or raw sensitive evidence.

## Acceptance

The required row is AEDT 2025 R2 Commercial. A failed run is valid evidence but
blocks the associated support claim until its cause and policy are documented
and accepted. Other releases or editions require a separately approved scope
and their own controlled evidence.
