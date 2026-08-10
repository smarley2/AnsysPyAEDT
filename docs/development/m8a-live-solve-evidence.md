# M8a Solve Execution Evidence

- Milestone: M8a, solve execution
- Plan: [2026-08-10 M8a solve execution](../superpowers/plans/2026-08-10-m8a-solve-execution.md)
- Status: implementation complete; **live solver evidence is still outstanding**
  and only Fabio Posser can record it

## What M8a changed

`Generate and Solve` is no longer blocked. A run in that mode carries the
solve intent to the adapter, which appends one `analyze` stage after `save`,
emits a stage event around every stage, and checks a cancellation token at
each stage boundary. `start_project_run` writes a `running` placeholder into
`run-manifest.json` before dispatching the adapter, overwrites it with the
real manifest when the run ends, and leaves `results/solve-log.txt` behind
for a solve run.

`RunManifest.results` stays `None` for the whole slice by design. Normalized
scalar results are M8b; field results and representative cross sections are
M8c.

## Non-live gate

Run on the development machine on 2026-08-10, in the working tree that
carries the M8a commits:

```bash
.venv/Scripts/python.exe -m ruff check .
```

`All checks passed!`

```bash
.venv/Scripts/python.exe -m mypy src tools
```

`Success: no issues found in 127 source files`

```bash
.venv/Scripts/python.exe -m tools.check_architecture
```

Clean, no output.

```bash
.venv/Scripts/python.exe -m pytest -n 8 -m "not aedt and not femm" -q
```

`1213 passed in 46.44s`

Covered without a solver: both skin-free adapters reaching `analyze`,
cancellation stopping before `analyze` while still saving what the design
reached, a failed `analyze` recorded as a failed stage, the `running`
placeholder observed mid-run, the cancelled manifest reporting
`status: cancelled` rather than `failed`, the solve log landing in `results/`,
and the Simulation screen streaming stage events and cancelling a run.

## Live evidence still to record

Two commands on the Windows workstation. Both suites now contain a dedicated
M8a solve test, so no manual steps are needed.

```bash
.venv/Scripts/python.exe -m pytest -m aedt -q
```

Requires `INDUCTOR_AEDT_RELEASE=2025.2` and `INDUCTOR_AEDT_EDITION=commercial`.
`tests/integration/aedt/test_maxwell_solve_live.py` runs one Maxwell 3D and
one Maxwell 2D `generate-and-solve` run and asserts the manifest ends with a
succeeded `analyze` stage, `results` is `null`, and `results/solve-log.txt`
exists and mentions `analyze`.

```bash
.venv/Scripts/python.exe -m pytest -m femm -q
```

Requires `INDUCTOR_FEMM_LIVE=1` with `pyfemm` installed.
`tests/integration/femm/test_femm_solve_live.py` runs one FEMM
`generate-and-solve` run and asserts the stage sequence is exactly
`generate`, `analyze`.

Record here, once run:

- the run directory name, stage sequence, status and wall-clock solve time per
  backend;
- the tail of `results/solve-log.txt` for one run per backend; and
- one deliberately cancelled run from the Guided Studio, showing
  `"status": "cancelled"` in its manifest, no `analyze` stage, and the saved
  project still present in the run directory.

## Known limitations

- The `running` placeholder is not a Run Manifest. It carries only `runId`,
  `backend`, `mode`, `status` and `startedUtc`, because the real manifest
  needs a planned run that does not exist until planning succeeds. A reader
  that finds `"status": "running"` is looking at a run whose process died.
- Cancellation is cooperative and takes effect only at a stage boundary. A
  long `analyze` call runs to completion before the run stops; the UI says so
  with `Cancelling after the current stage...`. Superseded: `analyze` is now
  interruptible, see
  [ui-freeze-during-solve.md](ui-freeze-during-solve.md).
- No result value of any kind is extracted, normalized or exported in M8a.
