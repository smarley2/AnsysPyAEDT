# M9 Reliability Evidence

- Milestone: M9, Reliability
- Plan: [2026-08-18 M9 reliability](../superpowers/plans/2026-08-18-m9-reliability.md)
- Status: **implementation complete, awaiting Fabio Posser's verification.**
  Only he accepts a milestone. This record gives him what he needs to verify
  it himself: the automated gate output, a table of forced-failure scenarios
  and what each preserved and produced, an honest account of the defects the
  reviews found (several of them leaks), the open product questions still
  waiting on his ruling, and a manual walk he runs on the Windows workstation.

## Exit criterion

Verbatim from the roadmap: *"forced UI and solver failures preserve the last
valid Project document and produce sufficient redacted evidence for
diagnosis."* Everything below exists to let him check exactly this, without
reading code.

## What M9 changed, per approved roadmap bullet

**Add autosave, crash recovery, and application-wide undo/redo.**

- `src/inductor_designer/ui/project_session.py` -- `UNDO_DEPTH` (50),
  `AUTOSAVE_DEBOUNCE_MS` (2000), `apply`/`undo`/`redo`/`applyRecovered`, and
  the debounced `flushAutosave`. `dirty` stopped being a one-way flag and
  became a structural comparison against `_saved_project`, so undoing back to
  the saved state re-enables the M7c `Generate` gate.
- `src/inductor_designer/adapters/persistence/recovery_store.py` --
  `RecoveryStore`, `RecoverySnapshot`, written through `ProjectRepository` so
  the snapshot inherits schema-v5 validation.
- `src/inductor_designer/adapters/system/environment.py` --
  `recovery_directory()`, `log_directory()`, `environment_redaction_context()`.
  The recovery snapshot lives in `%LOCALAPPDATA%\InductorDesigner\recovery`,
  outside the project directory.
- `src/inductor_designer/ui/recovery_controller.py` -- offers the snapshot at
  startup; `Recover` / `Discard`, wired into `Main.qml` and `main.py`.

**Recover interrupted runs without claiming partial success.**

- `src/inductor_designer/application/services/run_recovery.py` --
  `find_unfinished_runs`, `reconcile_unfinished_runs`,
  `INTERRUPTED_DIAGNOSTIC`, `UNSOLVED_ARTIFACT_DIAGNOSTIC`.
- `RunStatus.INTERRUPTED` in `src/inductor_designer/simulation/run_contracts.py`.
- The Review screen's interrupted-run rows (`ui/review_controller.py`). The
  word "resume" appears nowhere in the application (grep-verified, QML
  included): a killed run is never re-solved in place, only started fresh in
  a new run directory.

**Add actionable installation, license, material, file, and convergence
errors.**

- `src/inductor_designer/simulation/failure_advice.py` -- 19 first-match-wins
  rules, `AdviceCode`, `advise()`, `convergence_advice()`.
- `src/inductor_designer/application/services/maxwell_export.py` -- the single
  assembly point (`_with_advice`, called from `_build_manifest`) where every
  failed manifest's diagnostics gain their advice line.
- `src/inductor_designer/adapters/pyaedt/stage_progress.py` --
  `log_desktop_messages`, capturing AEDT's own message channel into the
  redacted application log at every stage-failure boundary.

**Produce redacted logs and a diagnostic bundle.**

- `src/inductor_designer/application/services/redaction.py` -- the one place
  that decides what "shareable" means: `RedactionContext`, `redact_text`, the
  path/email/host/user/licence-server rules and the `_TECHNICAL_EXTENSIONS`
  allowlist.
- `src/inductor_designer/adapters/system/app_logging.py` -- the rotating,
  redacting application log formatter.
- `src/inductor_designer/application/services/diagnostic_bundle.py` --
  `BundleSource`, `BundleEntry`, `build_bundle_entries`, the
  `bundle-contents.json` index recording what was removed and what was
  excluded on purpose.
- `src/inductor_designer/adapters/system/diagnostic_archive.py` --
  `collect_bundle_sources`, `write_diagnostic_archive`, `BUNDLE_SUFFIX`.
- `src/inductor_designer/ui/diagnostics_controller.py` and the `Help > Save
  diagnostic bundle...` menu item in `Main.qml`.

## Non-live gate, measured on this machine, 2026-08-21

Branch `claude/live-results-and-direction-fixes`, HEAD `1af92f1` plus this
task's commit.

```
.venv/Scripts/python.exe -m ruff check .
```

`All checks passed!`

```
.venv/Scripts/python.exe -m mypy src tools
```

`Success: no issues found in 155 source files`

```
.venv/Scripts/python.exe -m tools.check_architecture
```

Clean exit, no output.

```
.venv/Scripts/python.exe -m pytest -m "not aedt and not femm" -q
```

`1717 passed, 16 deselected in 71.98s (0:01:11)`

Re-run for speed as `-n 8`: `1717 passed in 51.65s`. The recorded count is
from the serial command above, as the brief requires.

```
git diff --check
```

Clean, no output.

`%LOCALAPPDATA%\InductorDesigner` does not exist after either run (checked on
the real, unredirected `%LOCALAPPDATA%`): the new test file never calls
`recovery_directory()` or `log_directory()`, it builds its own `RecoveryStore`
against `tmp_path`, and the existing `tests/ui/conftest.py` autouse fixture
already redirects `LOCALAPPDATA` to `tmp_path` for every test under `tests/ui`.

The 1713 -> 1717 delta is exactly the four new tests in
`tests/integration/test_reliability_recovery.py`.

## Forced-failure scenarios

All four run against the real catalog (`SqliteCatalogRepository` built from
`catalog/`), the real material overlay (`FileOverlayMaterialRepository` over
`materials-overlay/`), and the recording exporter fakes in `tests/fakes/`. No
AEDT, no FEMM.

| # | Forced failure | What was preserved | What was produced |
| --- | --- | --- | --- |
| 1 | `save_callback` raises `OSError` after an edit | `session.project` still holds the edited project; `dirty` stays `True`; the file on disk is untouched | `saveProject()` returns `False`; the status message names the failure; `flushAutosave()` writes a recovery snapshot that loads back as the exact edited project |
| 2 | A run directory seeded with `"status": "running"` and a saved `Inductor3D.aedt`, as a killed solve would leave it | The `.aedt` artifact stays on disk, untouched | `reconcile_unfinished_runs` rewrites the manifest to `"status": "interrupted"`, `"results": null`, with both `run.interrupted_before_completion` and `run.artifact_saved_but_unsolved` in `diagnostics`; the recording exporter recorded **zero** calls -- recovery reached no adapter |
| 3 | The recording Maxwell 3D exporter fails its `launch` stage with `License checkout failed on 1055@LICSRV01` | -- (no artifact exists yet at `launch`) | `ProjectRunFailed`, manifest `status: failed`, diagnostics carrying the raw text *and* `license.unavailable: ...`; a bundle built from the run directory contains `license.unavailable` but neither `1055@LICSRV01` nor any absolute path (the licence-server text is caught by the e-mail-shaped redaction rule, `port@host` reads as `local@domain`) |
| 4 | A valid edit (add a winding), then an edit the domain rejects (the new winding's start angle overlaps the first winding's sector) | `session.project` still holds the valid edit, unchanged by the rejected attempt | The rejected edit returns `False` and changes nothing; `undo()` returns `True` and restores the pre-edit project exactly; `SimulationController.canGenerate` is `True` before any edit, `False` once dirty, and `True` again once undo returns to the saved state |

Test file: `tests/integration/test_reliability_recovery.py`. Each of the four
scenarios has its own test function; the red-then-green mutation evidence
below shows each test actually fails when the production line it protects is
broken.

### Mutation evidence (red then green)

Required to prove at least three assertions load-bearing; four are shown.
Each mutation was applied at the stated line, the affected test alone was run
red, then the file was restored with `git checkout --` and the full new-test
file was re-run green. All runs used `PYTHONDONTWRITEBYTECODE=1` and
`-p no:cacheprovider`.

| # | File : line | Change | Result |
| --- | --- | --- | --- |
| 1 | `ui/project_session.py:252` | `saveProject`'s exception handler: `return False` -> `return True` | `test_a_save_that_fails_preserves_the_last_valid_project` failed: `assert True is False` |
| 2 | `application/services/run_recovery.py:183` | `if artifacts:` -> `if False:` (never append the unsolved-artifact diagnostic) | `test_a_killed_solve_is_reconciled_and_never_re_solved` failed: `run.artifact_saved_but_unsolved` missing from `diagnostics` |
| 3 | `application/services/maxwell_export.py:502` | `_with_advice`: `advised.append(f"{advice.code}: {advice.action}")` -> `advised.append("mutated")` | `test_a_licence_failure_produces_actionable_redactable_evidence` failed: `license.unavailable:` missing from the manifest diagnostics |
| 4 | `domain/validation.py:42` | `_sectors_overlap`: `return any(...)` -> `return False and any(...)` | `test_undo_restores_the_last_valid_project_after_a_rejected_edit` failed: the overlapping edit was accepted instead of refused |

Every mutation was confirmed reverted (`git status --short` clean for `src/`)
and the full four-test file was re-run green after each restore.

## Defects the reviews found

M9's value is not that it shipped clean -- it shipped only after these were
found and closed. The ones that mattered most were leaks: text that would
have left BRUSA's systems inside evidence meant to be shareable.

**The truncation slice that stranded `\\BRUSA-FS01\share\...` in a real
archive.** Task 8's bundle reader truncated an oversized log with a raw
character slice, which can land mid-path and strip the `C:\` or `\\host`
anchor every redaction rule matches on. Real archives from a used machine
contained `:\Users\hans.mueller\Projects\CustomerACME\coil.aedt` and
`\BRUSA-FS01\share\CustomerACME\coil.aedt` in clear text, because the log
rotates at 1 MB against a 512 kB cap -- this was the *ordinary* case, not an
edge case. The UNC form was worse: a file-server name is not in
`RedactionContext` at all, so nothing downstream could have caught it either
way. Fixed by dropping the partial first line of the truncated tail.

**The extension-guessing that published a surname.** Early in Task 1, the
redaction rule tried to guess where a path ended by looking for a short
extension. `jane.doe` and `notes.txt` are structurally identical, so that
guess read `jane.doe` as a name plus a `.doe` extension and published the
surname. The design is now an explicit `_TECHNICAL_EXTENSIONS` allowlist:
only extensions this application, AEDT, or FEMM actually produce survive.

**The doubled-backslash JSON shape.** A later Task 1 wave found that
`json.dumps` -- exactly what writes `run-manifest.json` -- doubles every
backslash, and the path rule as written did not handle that shape. It leaked
a surname again, and separately broke idempotence, and stranded the second
server name when two UNC paths appeared on one line.

**The live run displayed as interrupted.** Task 7's reconciliation could not
tell that a `"status": "running"` manifest belonged to a run *this process*
was executing right now. Every live run was shown on the Review screen as
"Interrupted run ... cannot be solved again," 100% reproducibly, because
Review's refresh is wired to the same signal the worker emits per stage
event. Fixed with one busy-check read at the two sites that matter
(`GenerationController.busy`, threaded through
`ProjectSession.set_busy_check`), so a manifest write is skipped -- not
gated -- while this process's own run is in flight.

**The recovery path that crashed startup.** Task 6's first defect: a
snapshot with a parseable but timezone-naive `savedAtUtc` escaped
`except ValueError` and raised `TypeError` out of `main()`. The application
could not start at all, and the only remedy was deleting a file in
`%LOCALAPPDATA%` -- strictly worse than having no recovery feature.

**The prompt that offered work which did not exist.** Task 6's second
defect: a snapshot byte-identical to the already-saved document was offered
for recovery, and re-offered on every subsequent launch. This was reachable
from ordinary use -- edit, undo back to the saved state (undo schedules an
autosave), then crash -- and it told the user "Recovered unsaved changes"
when nothing had actually changed. Fixed by comparing snapshot and document
bytes directly, which is exact because both come from the same
`ProjectRepository.save`.

**Also worth knowing**, in brief (full detail in
`.superpowers/sdd/progress.md`, M9 section): the licence-advice rules
originally routed a genuine solver-death diagnostic and an installed-FEMM
error to the wrong advice, and sent both an expired licence and an
exhausted-seats failure to the same generic "flexnet" bucket; an autosave
Open-race could silently destroy the one snapshot worth keeping;
`RecoveryStore.clear()` raises on Windows for a locked file and both the
session's autosave-cleanup path and the recovery dialog's `Discard` needed
their own guard against it; `Ctrl+Z`/`Ctrl+Y` were dead on arrival (a QML
`Shortcut` is not an `Item`, so `parent` did not resolve inside it); and the
zip-slip guard in the bundle writer was defeated by its own platform
(`ZipInfo` rewrites `os.sep` to `/` *after* the safety check ran).

## Accepted residuals and open questions

These are product rulings, not implementation gaps. Two were already ruled on
2026-08-18 and are recorded as closed; eight remain open, each with a working
default the plan uses until Fabio rules otherwise.

**Ruled 2026-08-18:**

- Whether the bundle may contain the Project document: **excluded** -- it
  carries user-authored text no redaction rule can classify.
- Whether the bundle may contain AEDT's own log files: **excluded**, with the
  desktop message channel captured through this application's own redacting
  logger instead.

**Open, awaiting his ruling:**

1. **Autosave interval** -- currently a 2000 ms debounce
   (`AUTOSAVE_DEBOUNCE_MS`).
2. **Recovery snapshot location** -- currently
   `%LOCALAPPDATA%\InductorDesigner\recovery\`, not beside the project
   document.
3. **Undo depth** -- currently bounded at 50 project snapshots (`UNDO_DEPTH`).
4. **Recovery prompt versus silent restore** -- currently prompts once at
   startup (`Recover` / `Discard`), never restores silently.
5. **Whether a bundle is also written automatically on a failed run** --
   currently written only when the user asks, from the Help menu.
8. **Whether reconciliation of an interrupted run is automatic** -- currently
   reconciles at startup and on Open, so a stale `running` manifest can never
   be read as live.
9. **How long interrupted run directories are kept** -- currently never
   deleted; they are the user's evidence.
10. **A path whose last component contains a space, with no allowlisted
    extension, strands its last word.** Found while implementing Task 1 and
    pinned by two tests: `opened C:\Users\Jane Doe` redacts to
    `opened [redacted-path] Doe`. Letting the final segment admit spaces was
    measured and is worse -- it swallows the prose after *every* path, so
    `saved C:\a\b.log successfully` would lose its last word. Exposure is
    limited because a BRUSA login is a single token, so a user-profile path
    has no space to break on; the residual is a directory someone named with
    a space. The plan keeps the stranded word rather than destroy prose;
    changing that is one constant plus one regex branch.

## What is NOT covered

M9 adds no new automated live-solver test. It reuses the accepted M8 live
evidence and adds none of its own. The one live-adjacent verification is the
manual forced-kill walk below, which needs a real solve to interrupt -- and
therefore the single-AEDT-session rule.

## Manual forced-failure walk (Fabio Posser, on the Windows workstation)

This is the part only a person can do, and it is what closes the exit
criterion. **One AEDT session at a time:** confirm no `ansysedt.exe` process
is running before starting, and between steps.

1. Start the application on a saved project, edit a winding, and kill the
   process from Task Manager without saving. Restart the application: the
   recovery dialog should offer the autosaved changes; choose **Recover**.
   Confirm the edited winding is back, that the project file on disk was
   never modified, and that **Generate** stays disabled until you save.
2. Repeat step 1, but this time choose **Discard** at the recovery dialog.
   Confirm the project that loads is exactly what was last saved to disk, and
   that the recovery snapshot is gone (the dialog does not reappear on a
   third restart with no new edit).
3. Start a **Generate and Solve** run on Maxwell 3D, and kill the process
   from Task Manager while the `analyze` stage is visible in the run log.
   Restart the application and open the project. On the Review screen, the
   interrupted run should be named explicitly. Open
   `runs/<run-id>-maxwell-3d/run-manifest.json` in a text editor and confirm
   `"status": "interrupted"`, `"results": null`, and both
   `run.interrupted_before_completion` and `run.artifact_saved_but_unsolved`
   in `diagnostics`. Confirm the saved `*.aedt` is still in that directory,
   and that nothing on the Review screen offers to resume or re-solve it.
   Start a new run: confirm it lands in a new, separate run directory and
   succeeds normally.
4. Open **Help > Save diagnostic bundle...**, save it anywhere, then open the
   `.zip` and read every member. Confirm:
   - `bundle-contents.json` lists both what was removed (the marker legend)
     and what was excluded on purpose (the project document, AEDT's own log
     files) with the stated reasons.
   - The failure text from step 3 and its advice code (for example
     `solver.stopped_early`) are still readable in the run manifest entry.
   - The `AEDT [analyze]:` log lines captured when that stage failed appear
     in the application log entry -- this is the evidence that AEDT's own
     log files were excluded without losing the reason the solve died.
   - **No drive letter, no UNC path, no machine name, no user name, no
     licence server identifier, and no e-mail address appears anywhere in any
     entry name or in any entry's bytes.** Read the whole archive, not just
     the parts that look interesting -- a leak in a section nobody expected
     to check is exactly the failure mode the earlier defects above produced.
5. On each of the five Guided Studio screens in turn -- Core & Material,
   Windings, Preliminary, Simulation, Review -- make one edit, then
   **Edit > Undo** and **Edit > Redo**. Confirm each screen redraws correctly
   after both, and that undoing all the way back to the last-saved state
   re-enables **Generate**.

## Known risks carried into M9 acceptance

Unchanged from the plan; repeated here because they remain true after Task 9
and a reviewer will ask about them:

1. The advice substrings in `failure_advice.py` are unproven text: matched
   against AEDT 2025 R2, pyFEMM and CPython wording observed as of
   2026-08-18, with no live test able to prove AEDT still phrases a failure
   that way. An unmatched diagnostic fails honestly as
   `run.unclassified_failure` rather than guessing.
2. `dirty` is now a structural value comparison on `InductorProject`. All of
   its members are frozen dataclasses and tuples today; a future mutable
   member would silently make the comparison identity-based.
3. `find_unfinished_runs` treats a run directory with no readable manifest as
   interrupted. The window between directory creation and marker write is
   microseconds today; a future change that widens it must revisit this.
4. Redaction cannot recognise a user-authored string. A project name or
   winding label could name a person, and no regular expression can tell --
   which is exactly why the project document is excluded from the bundle.
5. No new live-solver claim, as stated above.
6. `application_data_directory()` falls back to `~/.local/share` when
   `LOCALAPPDATA` is unset, purely so the non-solver suite runs on Linux CI.
   Not a supported product configuration (ADR 0004).
