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

## Non-live gate, measured on this machine, 2026-08-21 (fix wave)

Branch `claude/live-results-and-direction-fixes`, HEAD `137436d` (the M9
task 9 evidence commit) plus this review-fix-wave's commit. Re-measured after
the fix wave below because the fix wave changed
`tests/integration/test_reliability_recovery.py` and this document; no
production code under `src/` changed (confirmed below by byte-identical
`git diff` after every mutation was restored).

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

`1717 passed, 16 deselected in 64.79s (0:01:04)`

Re-run for speed as `-n 8`: `1717 passed in 28.72s`. The recorded count is
from the serial command above, as the brief requires. The count is unchanged
from the original task-9 measurement (still four tests in
`test_reliability_recovery.py`, no tests added or removed by this fix wave --
only assertions inside the existing four were strengthened).

```
git diff --check
```

Exit code 0. Two advisory "LF will be replaced by CRLF" notices for the two
files this fix wave edited (line-ending normalisation on this checkout, not a
whitespace error); no error output.

`%LOCALAPPDATA%\InductorDesigner` does not exist after either run (checked on
the real, unredirected `%LOCALAPPDATA%`, `C:\Users\fpo01\AppData\Local`): the
test file still never calls `recovery_directory()` or `log_directory()`, it
builds its own `RecoveryStore` against `tmp_path`.

## Forced-failure scenarios

All four run against the real catalog (`SqliteCatalogRepository` built from
`catalog/`), the real material overlay (`FileOverlayMaterialRepository` over
`materials-overlay/`), and the recording exporter fakes in `tests/fakes/`. No
AEDT, no FEMM.

| # | Forced failure | What was preserved | What was produced |
| --- | --- | --- | --- |
| 1 | `save_callback` raises `OSError` after an edit | `session.project` still holds the edited project; `dirty` stays `True`; the file on disk is byte-identical to what the test wrote (`document_path.read_text() == "{}"`, asserted) | `saveProject()` returns `False`; the status message names the failure; `flushAutosave()` writes a recovery snapshot that loads back as the exact edited project |
| 2 | A run directory seeded with `"status": "running"` and a saved `Inductor3D.aedt`, as a killed solve would leave it | The `.aedt` artifact stays on disk, byte-identical to what the test wrote (`saved_artifact.read_text() == "saved before the process was killed"`, asserted) | `reconcile_unfinished_runs` rewrites the manifest to `"status": "interrupted"`, `"results": null`, with both `run.interrupted_before_completion` and `run.artifact_saved_but_unsolved` in `diagnostics`; the recording exporter recorded **zero** calls -- recovery reached no adapter |
| 3 | The recording Maxwell 3D exporter fails its `launch` stage with `License checkout failed on 1055@LICSRV01`, and a faked application-log source (containing the failing project document's absolute path) is fed into the bundle alongside the run's own manifest | -- (no artifact exists yet at `launch`) | `ProjectRunFailed`, manifest `status: failed`, diagnostics carrying the raw text *and* `license.unavailable: ...`; a bundle built from the run directory *and* the faked log contains `license.unavailable` but neither `1055@LICSRV01` nor the absolute path that was in the faked log source (both redaction rules -- licence-server and drive-path -- are exercised on a source proven to actually contain the hazard) |
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
| 5 | `application/services/redaction.py:220` | `redact_text`: `redacted = _DRIVE_PATH.sub(_path_replacement, redacted)` -> `redacted = redacted` (drive-path rule neutralised) | `test_a_licence_failure_produces_actionable_redactable_evidence` failed: `assert str(tmp_path) not in bundle_text` -- the absolute path added by the fix-wave's log source leaked into the bundle text |
| 6 | `application/services/redaction.py:211` | `redact_text`: `redacted = _LICENSE_SERVER.sub(REDACTED_LICENSE_SERVER, text)` -> `redacted = text` (licence-server rule alone neutralised) | `test_a_licence_failure_produces_actionable_redactable_evidence` **stayed green** -- see the "Known risks" entry on defence-in-depth below |
| 7 | Both `application/services/redaction.py:211` and `:212` (licence-server *and* e-mail rules) neutralised together | `test_a_licence_failure_produces_actionable_redactable_evidence` failed: `assert '1055@LICSRV01' not in bundle_text` | Confirms the two rules jointly, not singly, guarantee the licence-server text is caught |

Every mutation was confirmed reverted (`git status --short` clean for `src/`,
and `git diff -- src/` empty -- byte-identical to `HEAD`) and the full
four-test file was re-run green after each restore.

Mutations 1-4 predate this fix wave, protect assertions this fix wave did not
change, and were not re-run here. Mutations 5-7 were added by this fix wave.
Mutation 5 closes a real gap: before this fix wave, scenario 3's test built
its bundle sources from the run manifest alone, which never carries an
absolute path (artifact paths in a manifest are always written relative to
the project directory), so `assert str(tmp_path) not in bundle_text` could
never fail no matter what `redact_text` did. The fix wave added a faked
application-log source containing the failing project document's absolute
path (see scenario 3's row above) specifically so that assertion has
something real to catch; mutation 5 is what proves it now does. Mutations 6
and 7 together prove the Known-risk entry on licence-server redaction added
below.

Two of this fix wave's other strengthened assertions -- the byte-identity
checks in scenarios 1 and 2 above (`document_path` untouched, `saved_artifact`
untouched) -- have **no corresponding production line to mutate**, and that
is stated plainly rather than papered over with a manufactured mutant.
`saveProject`'s only interaction with the document file is through the
injected `_save_callback` (here, a test-local function that unconditionally
raises before writing anything), and `reconcile_unfinished_runs` never opens
or writes any file other than `run-manifest.json`. Both assertions guard
against a *future* regression -- a save path that partially writes before
failing, or a reconciliation change that touches solver output -- that does
not exist in the current code to break. They were still added because Minor
4 and Minor 5 of the review named exactly this gap: the evidence document
claimed byte-identity without asserting it anywhere.

## Defects the reviews found

M9's value is not that it shipped clean -- it shipped only after these were
found and closed. The ones that mattered most were leaks: text that would
have left BRUSA's systems inside evidence meant to be shareable.

**The truncation slice that stranded a user-profile path and a file-server
path in a real archive.** Task 8's bundle reader truncated an oversized log
with a raw character slice, which can land mid-path and strip the `C:\` or
`\\host` anchor every redaction rule matches on. A real archive, produced from
a real bundle build (not a mock), contained an unredacted drive-letter path
of the shape `:\Users\<login>\Projects\<customer>\coil.aedt` and an unredacted
UNC path of the shape `\\<file-server>\share\<customer>\coil.aedt` in clear
text, because the log rotates at 1 MB against a 512 kB cap -- this was the
*ordinary* case, not an edge case. The specific login, server, and customer
names in that finding were the seeded fixture values from
`tests/unit/adapters/system/test_diagnostic_archive.py`, not a real person or
machine -- the leak mechanism was real, the identity in it was not. The UNC
form was worse: a file-server name is not in `RedactionContext` at all, so
nothing downstream could have caught it either way. Fixed by dropping the
partial first line of the truncated tail.

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

**This walk has not been run yet.** It needs a licensed AEDT session and a
real process kill on the Windows workstation, neither of which this
implementation pass had. Two of the artifacts the brief for this task
requires -- the verbatim `run-manifest.json` of an interrupted run, and the
complete member list of one real diagnostic bundle with its redaction
confirmation -- can therefore not be the real thing yet. What follows instead
is the *shape* those two artifacts take, produced by running the real
production code (`reconcile_unfinished_runs`, `collect_bundle_sources`,
`build_bundle_entries`) against a faked run directory in a temp folder --
exactly what `test_a_killed_solve_is_reconciled_and_never_re_solved` and
`test_a_licence_failure_produces_actionable_redactable_evidence` already
exercise, run once more here standalone so the output could be captured
outside pytest. **No AEDT was involved in producing either artifact below**;
they are placeholders for what step 3 and step 4 of the walk will produce for
real, not evidence that the walk happened.

**Artifact 1 -- reconciled `run-manifest.json`, shape, produced without a live
solve:**

```json
{
  "artifacts": [
    {
      "kind": "unsolved-solver-project",
      "path": "Inductor3D.aedt"
    }
  ],
  "backend": "maxwell-3d",
  "diagnostics": [
    "run.interrupted_before_completion: The application or the solver stopped before this run finished. No result was produced, and no part of this run may be read as a result.",
    "run.artifact_saved_but_unsolved: This run never recorded a completed analysis, so the saved project may hold no solution. Start a new run, which gets its own directory; solving this directory again fails on its missing solver data."
  ],
  "mode": "generate-and-solve",
  "reconciledUtc": "2026-08-21T09:03:00+00:00",
  "results": null,
  "runId": "20260821-090000",
  "startedUtc": "2026-08-21T09:00:00+00:00",
  "status": "interrupted"
}
```

**Artifact 2 -- diagnostic bundle member list and redaction confirmation,
shape, produced without a live solve.** Built from the same faked run
directory plus a faked application-log source containing one absolute path
and one FlexNet-shaped licence identifier:

- `bundle-contents.json` (the marker legend and the excluded-on-purpose list,
  as shown earlier in this document)
- `logs/app.log`
- `runs/20260821-090000-maxwell-3d/run-manifest.json`

The faked `logs/app.log` source contained the absolute path of the faked
project document; the corresponding bundle entry reads:

```
AEDT [analyze]: Engine Detected Error: missing file X.adp
AEDT [analyze]: failed while staging [redacted-path].json
```

Redaction confirmation for this faked bundle: the absolute path was present
in the raw log source before redaction, and is absent from every entry's
text after `build_bundle_entries` -- checked here by substring search over
all three entries' text, the same check step 4 of the real walk performs by
reading the archive.

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
5. On the Core & Material, Windings, and Simulation screens in turn, make one
   edit, then **Edit > Undo** and **Edit > Redo**. Confirm each screen
   redraws correctly after both, and that undoing all the way back to the
   last-saved state re-enables **Generate**. Preliminary and Review are
   read-only (`PreliminaryPage.qml` and `ReviewPage.qml` contain no
   `TextField`, `SpinBox`, `ComboBox`, or `CheckBox`), so there is no edit to
   make on either: instead, while viewing each of them, undo and redo an edit
   made on one of the other three screens, and confirm the Preliminary and
   Review screen redraws to match -- e.g. a changed winding count or a
   changed **Generate** availability is reflected without needing to
   navigate away and back.

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
7. The "no licence server identifier" guarantee rests on two overlapping
   redaction rules, not one, and only one of them is labelled for it.
   `_LICENSE_SERVER` in `redaction.py` matches the FlexNet `port@host` shape
   and is meant to be what catches `1055@LICSRV01`. In practice `_EMAIL` also
   matches that shape (`port@host` reads the same as `local@domain`), so if
   `_LICENSE_SERVER` alone is ever weakened, `_EMAIL` independently catches
   the same text -- confirmed by disabling `_LICENSE_SERVER.sub` alone and
   observing `test_a_licence_failure_produces_actionable_redactable_evidence`
   stay green; only disabling both rules together turns it red. This is real
   defence in depth today, but it means the licence-server rule is not
   independently proven by this test suite: if `_EMAIL`'s two-character host
   requirement is ever narrowed or its pattern otherwise changed, a licence
   server identifier could start leaking with no test catching it until
   someone also breaks `_LICENSE_SERVER`.
