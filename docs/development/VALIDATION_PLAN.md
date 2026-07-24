# Supported Environment Validation Plan

## Purpose

This plan defines the reproducible evidence required for the only supported
Ansys environment: AEDT 2025 R2 Commercial. Historical AEDT 2024 R2 and Student
matrix rows establish no current support claim and are removed during the M5a
closeout.

## Required environment

| Product | Required target |
| --- | --- |
| Operating system | Windows |
| AEDT | 2025 R2 (`2025.2`) |
| Edition | Commercial |
| PyAEDT | Exact installed version recorded in evidence |
| FEMM | User-installed FEMM 4.2 when validating the optional FEMM backend |

Support is based on observed behavior, never inferred from version numbers.

## Phase A: Non-solver release gates

From a clean checkout and fresh virtual environment:

```powershell
python -m pip install -e ".[dev,ui]"
python -m ruff check .
python -m mypy src tools
python -m tools.check_architecture
python -m pytest -m "not aedt and not femm" --cov=inductor_designer --cov-report=term-missing
```

The installation and every command must succeed. Review `git status --short`
for only intentional files. Generated projects, solver output, raw material
sources without redistribution permission, credentials, license details, and
machine-specific evidence remain outside Git.

## Phase B: Controlled AEDT capability run

Follow the [AEDT compatibility procedure](aedt-compatibility-testing.md) on a
Windows machine with AEDT 2025 R2 Commercial and a valid license:

```powershell
.\tools\run_aedt_spike.ps1 -Release 2025.2 -Edition commercial -Graphical
```

Confirm that the observed session is exactly AEDT `2025.2` Commercial, record
the exact PyAEDT version, reopen both generated projects, and verify the native
3D `AC Magnetic with DC` behavior described in
[DC operating-point compatibility](dc-bias-compatibility.md).

## Phase C: M5a real-material gate

Use a legally usable material workbook and the
[material-record procedure](material-records.md):

1. Preserve source identity, hash, conditions, and redistribution decision.
2. Import and pin the exact material revision and B-H series.
3. Run the reproduction command and require `MATCH`.
4. Generate Maxwell 3D and FEMM artifacts from that same pinned revision.
5. In AEDT 2025 R2 Commercial, inspect the nonlinear B-H data and supported
   core-loss representation.
6. In FEMM, verify every expected singular `mi_addbhpoint` call is reflected in
   the material definition.
7. Record exact application, PyAEDT, AEDT, pyfemm, and FEMM versions.

M5a remains open until this evidence is reviewed. M5b is already accepted and
does not depend on this gate.

## Phase D: M8 simulation/result gate

For Maxwell 3D, Maxwell 2D, and FEMM, run one controlled Operating Point and
verify:

- effective AC RMS and peak currents and winding phases;
- generated geometry, material assignments, setup, and solver completion;
- result units, conventions, dimensional labels, and approximation warnings;
- R/L/Z and each supported matrix;
- copper/core/total loss and magnetic energy availability;
- B/J maximum and Area-Weighted Mean extraction;
- convergence and failure diagnostics; and
- JSON/CSV agreement with the Run Manifest.

Every requested unsupported quantity must be explicitly unavailable with a
reason.

## Phase E: M10 clean-install gate

Install the packaged application on a clean controlled Windows environment.
Without a source checkout, complete:

1. New Project.
2. Core, winding, material, and Operating Point authoring.
3. Save, close, open, and edit the Project document.
4. Generate Only for each backend.
5. Generate and Solve for each installed backend.
6. Result inspection and JSON/CSV export.
7. Confirmed Maxwell 3D Geometry-Only AEDT Project generation for a Manual core
   without material.
8. AEDT 2025 R2 Commercial project reopen and manual edit.

The application must locate packaged schemas, catalogs, templates,
compatibility evidence, and other resources without repository-relative paths.

## Evidence and acceptance rules

- Keep raw controlled-run evidence in ignored artifact directories.
- Remove credentials, license-server data, user names, and unrelated personal
  paths before sharing evidence.
- A failed observed run is valid diagnostic evidence but does not establish
  support.
- A partial solver artifact is never a successful run.
- No AEDT release or edition other than 2025 R2 Commercial is a required or
  implied target.
