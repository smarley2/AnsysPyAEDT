# ADR 0007: Project-Local Run Artifacts and Solver Visibility

- Status: Accepted
- Date: 2026-07-29

## Context

Generated Maxwell and FEMM files must remain available for later manual
inspection, editing, and simulation. A repository-level or application-level
output directory separates those files from the saved Project document, while
reusing one output path would overwrite prior runs. Users also need a clear
choice between unobtrusive background generation and watching the solver
application.

## Decision

The directory containing the saved `*.inductor.json` file is the Project
directory. A run requires a saved Project document and creates one new,
non-overwriting directory:

```text
<project-directory>/
  <project-name>.inductor.json
  runs/
    <run-id>-<backend>/
      run-manifest.json
      <generated solver project>
      results/
```

Backend labels distinguish Maxwell 3D, Maxwell 2D, and FEMM. The generated
solver project keeps its native `.aedt` or `.fem` format. `results/` is reserved
for M8 solve outputs and may be absent or empty after an M7 Generate Only run.
Run Manifest artifact references use paths relative to the Project directory so
the directory can be moved without embedding a user's absolute path.

Every Run Request creates a new run directory. Existing run directories and
solver projects are never overwritten implicitly. Failed runs retain truthful
manifest and diagnostic evidence in their assigned directory; partial output is
not presented as a successful artifact.

Solver generation and solving run in background/non-graphical mode by default.
The UI offers a per-run `Show solver window` choice when the selected adapter
and installed solver support visible operation. If visible operation is
unavailable, the choice is disabled with an explanation; background operation
remains available. Application stage progress and status remain authoritative
in either mode.

After successful generation, the UI offers `Open generated file` and `Open run
folder`. The generated `.aedt` or `.fem` file is an independent, user-owned
output that can be opened, edited, and simulated manually. Those edits are not
imported, synchronized, compared, or written back to the
`*.inductor.json` source document.

M7 implements this behavior for Generate Only. M8 reuses the same directory and
visibility rules for Generate and Solve and populates normalized result
artifacts.

## Consequences

- Project source and all retained run evidence travel together.
- Repeated runs remain independently inspectable and reproducible.
- Background execution is the default without preventing visible expert use.
- Native solver projects remain available for unrestricted manual work.
- Solver-side edits intentionally diverge from the source Project document.
- A user must save a new Project before starting its first run.

## Rejected alternatives

- A shared repository or application `artifacts/` directory: not portable with
  the user's Project directory.
- One mutable output per backend: destroys run history and traceability.
- Requiring an arbitrary output-directory choice for every run: adds friction
  and weakens the normal project layout. A later explicit export/copy command
  may be added without changing the canonical run location.
