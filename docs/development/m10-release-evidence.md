# M10 Windows Release Evidence

- Milestone: M10, Windows Release
- Plan: [2026-09-01 M10 Windows release](../superpowers/plans/2026-09-01-m10-windows-release.md)
- Status: **implementation complete, awaiting Fabio Posser's verification.**
  Only he accepts a milestone. This record gives him what he needs to verify
  it himself: the automated gate output, the checksum evidence including an
  independently recomputed hash, an honest account of the defects the four
  task reviews found (I was not present for any of them -- Task 5 only), a
  section stating plainly what could not be verified on this machine and why,
  and the clean-machine walk that closes the exit criterion.

## Exit criterion

Verbatim from the roadmap: *"the installed application completes authoring,
generation, optional solving, result export, save, and reopen against AEDT
2025 R2 Commercial."* Everything below exists to let Fabio Posser check
exactly this, without reading code. The walk further down is the only thing
that can actually close it -- this machine has never run the installer, and
this session must not start an AEDT session.

## What M10 changed, per approved roadmap bullet

**Resolve packaged resources outside the source checkout.**

- `src/inductor_designer/adapters/system/resources.py` -- `resource_root()`,
  resolving four shipped resources (schemas, catalog index, compatibility
  matrix, material overlay) for whichever of three environments is running:
  frozen bundle, installed wheel, or source checkout, plus the
  `INDUCTOR_DESIGNER_RESOURCES` override (see the release notes).
- `pyproject.toml` -- ships the four resources inside the wheel via
  `force-include`.
- `src/inductor_designer/ui/main.py` -- the four `_DEFAULT_*` constants now
  call into the seam; a missing resource refuses the launch on screen and on
  stderr, naming what is missing, rather than raising.

**Detect AEDT 2025 R2 Commercial and optional FEMM installation.**

- `src/inductor_designer/adapters/system/installations.py` --
  `detect_aedt()`, `detect_unsupported_aedt()`, `detect_femm()`. Cheapest
  route first (`ANSYSEM_ROOT252` environment variable), then the standard
  install location, then the registry -- verified against this machine's
  real AEDT 2025 R2 registry layout, not a faked one (see "Defects the
  reviews found" below). Detection imports no PyAEDT and starts no desktop.
- `src/inductor_designer/simulation/failure_advice.py` --
  `installation.aedt_missing` / `installation.aedt_unsupported_release`
  advice codes.
- Findings surfaced on the Simulation panel and logged once at startup
  through the redacting logger.

**Package the application with PyInstaller and Inno Setup.**

- `packaging/inductor-designer.spec` -- one-folder `COLLECT` build; the four
  resources plus pyaedt's 114 non-Python data files as `datas`; an explicit
  `excludes=` list (MCP, dev tooling, unused PySide6 Qt submodules) with the
  reason inline for each entry; a post-`Analysis` filter dropping unused
  native Qt DLLs and 17 unused `qml/` module directories that `excludes=`
  alone cannot reach.
- `packaging/build_frozen.py` -- builds the catalog index into a temporary
  directory first (refusing to proceed if it has zero cores), then runs
  PyInstaller against the spec.
- `packaging/installer.iss` -- per-user (`PrivilegesRequired=lowest`,
  no administrator), unsigned, version read from `__about__.py`, Start Menu
  shortcut unconditional, desktop shortcut opt-in, no sample project, and no
  `[UninstallDelete]`/`[Dirs]` entry anywhere naming
  `%LOCALAPPDATA%\InductorDesigner`.
- Measured bundle size (2026-09-01, this machine): 296.5 MB after a QML/DLL
  prune that cut 248.0 MB (45.5%) from the pre-prune 544.5 MB. Full
  before/after table in `docs/development/packaging.md`.

**Publish release notes and checksums (this task).**

- `packaging/build_frozen.py` -- `sha256_file`, `archive_bundle`,
  `write_checksums`, `emit_checksums`; every build now zips the bundle and
  writes `dist/SHA256SUMS.txt` over the bundle archive and the installer
  (when one was built), naming each by hash and filename only, never a
  download URL.
- `packaging/release_notes.md` -- the filled 0.1.0 release notes.
- `docs/development/m10-release-evidence.md` -- this record.

**Run the complete flow on a clean Windows installation.**

Not done in any implementation task, including this one -- see "What is NOT
verified on this machine" below. This is the one roadmap bullet only Fabio
Posser's walk can close.

## Non-live gate, measured on this machine, 2026-09-01

Branch `claude/live-results-and-direction-fixes`, on top of commit `3d5bc1b`
(M10 Task 4's final commit) plus this task's changes.

```
.venv/Scripts/python.exe -m ruff check .
```

`All checks passed!`

```
.venv/Scripts/python.exe -m mypy src tools
```

`Success: no issues found in 158 source files`

```
.venv/Scripts/python.exe -m tools.check_architecture
```

Clean exit, no output.

```
.venv/Scripts/python.exe -m pytest -q -n 8 -m "not aedt and not femm"
```

`1812 passed in 32.29s`

Up from Task 4's `1805 passed` by exactly the 7 new tests this task added
(`tests/unit/tools/test_build_frozen.py`, the checksum logic -- see below);
no test was removed, and three pre-existing tests were widened to also
monkeypatch the new `emit_checksums` seam so they stay independent of
whether a real bundle happens to exist under `dist/` when they run.

`git status --porcelain` after the gate: only the two intended source edits
(`packaging/build_frozen.py`, `tests/unit/tools/test_build_frozen.py`
modified) plus this task's three new files
(`packaging/release_notes.md`, `docs/development/m10-release-evidence.md`,
and this document's own commit). No `dist/` or `build/` output appears --
both are git-ignored, confirmed by inspection of `.gitignore` and by this
`git status` output.

## Checksums: what was emitted and how one hash was verified independently

`emit_checksums(version)` was run directly (not through the full
`python packaging/build_frozen.py`, which would have re-run the multi-minute
catalog build and PyInstaller freeze for no new evidence) against the real
bundle already on disk at `dist/inductor-designer/` from Task 4's build --
296.5 MB, unmodified since Task 4. It produced:

- `dist/inductor-designer-0.1.0-win64.zip` -- 129,073,846 bytes (123.1 MiB),
  the whole bundle folder zipped with `inductor-designer/` kept as the
  archive's single top-level entry.
- `dist/SHA256SUMS.txt`:

  ```
  e22556554d46b7d8c727d5b723655c92ce1423bb3ba8247fb35c299c95f3b776  inductor-designer-0.1.0-win64.zip
  ```

  One line only -- no installer exists on this machine (Inno Setup 6 is not
  installed; see Task 4's report and "What is NOT verified" below), and
  `emit_checksums` correctly omits an installer entry when
  `dist/installer/inductor-designer-0.1.0-setup.exe` does not exist (proven
  by `test_emit_checksums_covers_only_the_bundle_when_no_installer_was_built`
  and, when the file is present, by
  `test_emit_checksums_covers_the_installer_too_when_it_was_built`).

**Independent verification, not trusting the code that wrote it**: the same
zip's hash was recomputed with PowerShell's `Get-FileHash`, a completely
separate implementation from this script's `hashlib`-based
`sha256_file`:

```
Get-FileHash -Algorithm SHA256 "dist\inductor-designer-0.1.0-win64.zip"

Algorithm : SHA256
Hash      : E22556554D46B7D8C727D5B723655C92CE1423BB3BA8247FB35C299C95F3B776
```

Matches `e22556554d46b7d8c727d5b723655c92ce1423bb3ba8247fb35c299c95f3b776`
case-insensitively -- the two independent tools agree.

`dist/` is git-ignored (`inductor-designer/`, `_internal/`,
`inductor-designer.exe*`, `dist/` are all in `.gitignore`), so neither the
296.5 MB bundle, the 123.1 MiB zip, nor `SHA256SUMS.txt` itself is part of
this commit -- they are build output, reproduced by anyone who runs
`packaging/build_frozen.py` and then published on the GitHub release, not
checked into the repository.

### Why checksums, not a hard-coded download URL

The plan's git-migration note requires this: the repository may move from
`smarley2/AnsysPyAEDT` to a BRUSA-hosted remote later, and
`packaging/build_frozen.py` never embeds a download URL anywhere --
`write_checksums` names each artifact by its hash and filename only. The
release notes' verification section does the same: it tells the reader to
compare a locally computed hash against the matching line in
`SHA256SUMS.txt`, not to trust a specific link. Whichever host the artifact
is actually downloaded from, the hash is what identifies it.

## Red-then-green and mutation evidence

New tests written first (TDD): `tests/unit/tools/test_build_frozen.py` grew
seven new test functions (`test_sha256_file_matches_a_known_test_vector`,
`test_sha256_file_reads_large_files_in_chunks`,
`test_write_checksums_uses_the_sha256sum_verifiable_format`,
`test_archive_bundle_zips_the_bundle_with_its_folder_as_the_top_level_entry`,
`test_emit_checksums_covers_only_the_bundle_when_no_installer_was_built`,
`test_emit_checksums_covers_the_installer_too_when_it_was_built`,
`test_main_calls_emit_checksums_with_the_apps_own_version`) against
`sha256_file`/`archive_bundle`/`write_checksums`/`emit_checksums`, which did
not exist yet. Run before implementation:

```
10 failed, 12 passed in 1.27s
```

(the ten failures: the seven new tests plus three existing `main()` tests
updated in the same pass to expect the new `emit_checksums` call, all
failing with `AttributeError: module ... has no attribute 'emit_checksums'`).
Implemented, then re-run: `22 passed in 1.58s`.

Two production lines then proven load-bearing by reverting each in a backup
copy of `packaging/build_frozen.py` kept outside the repository
(`PYTHONDONTWRITEBYTECODE=1`, `-p no:cacheprovider`, never `git checkout`),
confirming red, restoring from the copy, confirming green again:

1. **`emit_checksums`'s installer-inclusion guard**
   (`packaging/build_frozen.py:277`):
   `if installer_path.is_file():` -> `if False:  # MUTATION build_frozen.py:277`.
   Red: `test_emit_checksums_covers_the_installer_too_when_it_was_built`
   failed --
   `assert len(lines) == 2` against the actual `1`, the installer line
   silently dropped even though the fake installer file existed on disk.
   Restored from the backup copy; `22 passed` again.
2. **`sha256_file`'s chunk-accumulation line**
   (`packaging/build_frozen.py:226`): `digest.update(chunk)` ->
   `pass  # MUTATION build_frozen.py:226` (the read loop still executes,
   chunk-by-chunk, but never feeds any of the file's bytes into the digest).
   Red: both `test_sha256_file_matches_a_known_test_vector` and
   `test_sha256_file_reads_large_files_in_chunks` failed, each producing
   `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` --
   the well-known SHA-256 of the *empty* string, proving the function had
   silently stopped hashing any content at all while still appearing to run
   its loop. Restored from the backup copy; `22 passed` again.

## Defects the reviews found (Tasks 1-4; I was not present for any of them)

Drawn from `.superpowers/sdd/m10-task-1-report.md` through
`m10-task-4-report.md`, since `.superpowers/sdd/progress.md`'s M10 section
was not filled in by the time this task started. Recorded here because a
release evidence record should carry an honest account of what almost
shipped wrong, not just what shipped.

- **Task 1 (resources), Important**: the startup refusal gate checked only
  the seam's own default paths and ignored `--catalog`/`--matrix` --  a
  *valid* `--catalog` flag pointing at a real index still refused to launch
  because the override resource root it was checked against lacked one.
  Fixed so an explicit, valid flag supersedes the seam's own resource for
  gate purposes.
- **Task 1, Important**: the installed-wheel resolution branch (the one
  `pip install` depends on) had no automated test at all, proven only by a
  manual wheel extraction. Now covered by monkeypatching the package
  directory to a fake wheel layout.
- **Task 1, Important**: the refusal log line dropped the resource names and
  logged at `INFO`, not `ERROR` -- for a Start Menu launch with no console,
  the log file is the only durable record, and it named nothing.
- **Task 1, Minor**: the source-checkout walk-up matched on `schemas/` +
  `catalog/` alone, so a checkout nested inside an unrelated directory that
  happened to also contain those two names would silently resolve to the
  *outer* decoy directory and report nothing missing. Fixed by also
  requiring `pyproject.toml`.
- **Task 2 (installation detection), Critical**: the registry route's key
  path was invented and never existed on any real AEDT install --
  `SOFTWARE\Ansys Inc\AnsysEM` versus the real
  `SOFTWARE\Ansoft\ElectronicsDesktop\<version>\Desktop\InstallationDirectory`
  -- so the fallback route was dead code every test's faked seam had hidden.
  Fixed and verified against this machine's real registry with the two
  cheaper routes disabled.
- **Task 2, Important**: the FEMM path join used `Path(system_drive) /
  relative` with `SYSTEMDRIVE="C:"` (no trailing separator), which
  `pathlib` resolves as *relative to the current directory*, not the drive
  root -- the existing test could not catch it because `tmp_path` is already
  multi-segment. Fixed with an explicit `_drive_root()` helper.
- **Task 2, Important**: the absent/unsupported-AEDT and detected-FEMM
  advice paths carried no advice code at all. Two codes added
  (`installation.aedt_missing`, `installation.aedt_unsupported_release`).
- **Task 3 (freeze), Critical**: the spec's `datas=` shipped zero of
  pyaedt's 114 non-Python data files, including
  `expression_catalog.toml`, which `PostProcessor3D` reads eagerly on
  construction -- every result-reading path in this application would have
  raised `TypeError` in the frozen build. A frozen bundle could have
  generated a solve but never read one back. Fixed with
  `collect_data_files("ansys.aedt.core")`.
- **Task 3, Important**: the packaging doc's own size analysis was wrong on
  two counts -- it claimed `PySide6/qml/` was ~384 MB (measured: 29 MB) and
  that pyaedt/pyfemm were large contributors under `_internal/` (both are
  pure Python inside the PYZ archive; neither ships a directory there at
  all). Corrected with measured, byte-counted numbers.
- **Task 3, Important**: the QML/DLL prune itself -- the review confirmed the
  root cause (PySide6's PyInstaller hook copies the whole `qml/` tree
  regardless of `excludes=`, and QML plugin DLLs pull native Qt DLLs back in
  even for already-excluded modules) and the fix cut 248.0 MB (45.5%),
  re-verified by relaunching the pruned bundle from outside the checkout
  with no missing-module or missing-plugin error.

None of the above reached this task's starting commit (`3d5bc1b`) unfixed --
every one was closed within its own task's fix wave before the next task
began. They are listed here so Fabio Posser sees what the review process
actually caught, not just the state it left behind.

### And two in Task 5 itself, found by its own review (fixed in `b0993b6`)

Recorded by the same standard, including the one that was a defect in this
very document -- an evidence record that hid a correction found in itself
would be worth nothing.

- **`emit_checksums` could publish a stale installer hash.** It decided
  whether to list the installer by probing `dist/installer/` with
  `is_file()`, and that directory is not cleaned between runs. A
  bundle-only build after an `--installer` build therefore wrote one
  `SHA256SUMS.txt` holding a fresh bundle's hash beside the PREVIOUS
  installer's -- two entries describing different builds. Anyone verifying
  that installer hash would get a match and conclude they held the current
  release, which is precisely the conclusion a checksums file exists to
  make safe. Now driven by the `--installer` flag, so the file lists only
  what the run produced.
- **The clean-machine walk cited a project file that does not exist
  anywhere but this machine.** The prerequisite below pointed at
  `artifacts/maxwell3d/2025.2-commercial/m7b.inductor.json` "in this
  repository". `artifacts/` is git-ignored (`.gitignore:18`): that file is
  untracked leftover state from manual M7b testing on this one development
  machine. The walk's whole premise is a machine that has never held the
  source tree, so the step would have dead-ended on the first reader who
  was not me. It now names the tracked fixture
  `tests/fixtures/sample_geometry_project.inductor.json`.

One Minor was accepted rather than fixed: `write_checksums` writes
`SHA256SUMS.txt` with a plain `write_text`, not a temp-file-plus-rename. It
is a single-process build script with no concurrent reader, so the atomic
write buys nothing; a crash mid-write leaves a truncated file that the next
build overwrites.

## What is NOT verified on this machine

Stated plainly, in its own section, rather than left for the reader to
infer:

1. ~~**No installer has ever been compiled.**~~ **CLOSED 2026-09-01** --
   see "The installer, compiled" below. Inno Setup 6.7.3 was installed at
   Fabio Posser's explicit request and
   `packaging/build_frozen.py --installer` produced
   `dist/installer/inductor-designer-0.1.0-setup.exe` (90,354,682 bytes)
   from a fresh end-to-end build.
2. **The install -> launch -> uninstall walk has never run.** Consequently
   the "user data survives an uninstall" guarantee is verified only
   structurally (the `.iss` script has no `[UninstallDelete]`/`[Dirs]` entry
   naming `%LOCALAPPDATA%\InductorDesigner` anywhere in it, confirmed by
   reading the whole file), never by actually installing, running once, and
   uninstalling.
3. **The bundle's window and 3D preview were confirmed visually only before
   the QML/DLL size-pruning pass.** Task 3's original launch (pre-prune) was
   screen-captured and showed a real rendered toroid-and-windings preview.
   After the prune (the state that actually ships), the re-launch was
   confirmed *statically* only: clean stderr, no missing-module or
   missing-plugin error, a live process whose working set grew from 116 MB
   to 316 MB over about 8 seconds (consistent with `QtQuick3D` scene setup),
   a correct application-log trail, and a clean lock-released shutdown. No
   screenshot of the post-prune window exists -- the only screenshot tool
   available in that session captured the machine operator's live desktop,
   which was showing an unrelated video call at the time, not the frozen
   application. **What this means concretely**: every signal consistent
   with correct rendering is present and matches the pre-prune,
   visually-confirmed launch on every point that can be checked without
   eyes on the screen, but nobody has actually looked at the pruned bundle's
   window since the prune was applied.
4. **Generate-and-Solve against a real AEDT or FEMM session has never run
   against the frozen bundle.** Task 3's launches (both pre- and post-prune)
   opened a sample project and confirmed geometry, catalog and compatibility
   resolution; neither drove a live solve, per this session's own house
   rules (never start an AEDT session, never run a test marked
   `aedt`/`femm`). Whether PyAEDT behaves identically frozen -- it imports
   lazily and reaches for its own installed files -- remains the plan's
   known risk 2, unresolved.
5. ~~**The checksum step ran against the Task 4 bundle already on disk, not
   against a fresh end-to-end `build_frozen.py` run.**~~ **CLOSED
   2026-09-01** -- `dist/` was deleted and the whole chain re-run: catalog
   build, PyInstaller freeze, ISCC compile, archive, checksums. Numbers
   below.

Items 2, 3 and 4 remain open. None of them can be closed from this machine
or by an automated gate -- item 2 needs someone to actually run the
installer, and items 3 and 4 need eyes on a screen and a licensed solver.
They are what the clean-machine walk below exists to close.

## The installer, compiled (2026-09-01)

Closing items 1 and 5 above. Recorded here because the previous revision of
this document stated as fact that no installer had ever existed, and a
reader who trusted that statement is entitled to see exactly what changed
it.

**How Inno Setup got onto this machine.** This account has no
administrator rights and the machine has no `winget`, `scoop` or `choco`,
so the ordinary `%ProgramFiles(x86)%` install was not available.
`innosetup-6.7.3.exe` was downloaded from the vendor's own release --
`github.com/jrsoftware/issrc`, tag `is-6_7_3` -- and its Authenticode
signature checked BEFORE it was run: status `Valid`, signer
`CN=Pyrsys B.V., O=Pyrsys B.V., C=NL` under `Sectigo Public Code Signing CA
R36`, version resource `Inno Setup 6.7.3 / jrsoftware.org / Copyright
1997-2026 Jordan Russell, portions 2000-2026 Martijn Laan`, SHA-256
`9C73C3BAE7ED48D44112A0F48E66742C00090BDB5BEF71D9D3C056C66E97B732`,
10,592,232 bytes. The publisher name is not literally "jrsoftware" --
Pyrsys B.V. is co-maintainer Martijn Laan's company -- and that mismatch is
recorded rather than glossed, since a reader checking the signature
themselves will hit the same surprise.

It installed **per-user** with `/CURRENTUSER /VERYSILENT`, into
`%LOCALAPPDATA%\Programs\Inno Setup 6`. Nothing machine-wide: `HKLM`
carries no uninstall entry (verified), only `HKCU` does, so it is removable
from Settings > Apps by this user alone. Version 6, not the available 7.1.0,
deliberately -- `installer.iss` and `find_iscc` are both written against
Inno Setup 6, and a major-version jump would put directive compatibility
into the same change as the first compile.

`find_iscc()` needed one fix to see it: `_ISCC_CANDIDATES` listed only the
two `%ProgramFiles%` locations, so the per-user install -- the only route
open to a builder without administrator rights -- produced the "not found"
refusal while a working `ISCC.exe` sat installed. `%LOCALAPPDATA%\Programs`
is now the third candidate, and the refusal message names `/CURRENTUSER`.

**The build.** `dist/` was deleted first, so nothing on disk could stand in
for a step that did not run:

```
rm -rf dist
.venv/Scripts/python.exe packaging/build_frozen.py --installer
```

Exit 0. `Successful compile (85.172 sec)`.

| Artifact | Bytes | SHA-256 |
| --- | --- | --- |
| `dist/installer/inductor-designer-0.1.0-setup.exe` | 90,354,682 | `5294f5c3152105f5c69e7050b4b05c88cee75838bda11800115a8d4228573a2f` |
| `dist/inductor-designer-0.1.0-win64.zip` | 129,073,278 | `fe37c2abf8d1736b3902518dd0320beabbea4559e924ef05f457254843b0e0d1` |

Both hashes recomputed with PowerShell `Get-FileHash -Algorithm SHA256`,
independently of the `hashlib` code that wrote `dist/SHA256SUMS.txt`, and
both matched. `SHA256SUMS.txt` holds exactly these two lines, in this order.

**What was checked on the compiled output, without installing it:**

- `Get-AuthenticodeSignature` on the installer returns `NotSigned`. The
  release notes' unsigned/SmartScreen warning is therefore accurate, not a
  precaution.
- The bundle is 2,956 files, 296,534,636 bytes (282.8 MiB). The 296.5 MB
  figure quoted elsewhere in this document is the same number in MB.
- The catalog index actually shipped:
  `_internal/artifacts/catalog/catalog.sqlite`, 53,248 bytes, **15 cores**,
  tables `cores` / `conductors` / `meta`. This is the failure mode
  `build_frozen.py`'s docstring calls the worst available -- an application
  that starts and shows an empty core list -- and it is now measured in the
  shipped artifact rather than argued from the build script.
- All five resource roots the runtime seam resolves are present under
  `_internal/`: `schemas`, `compatibility`, `materials-overlay`,
  `artifacts/catalog`, `inductor_designer/ui/qml`.

**Still not proven by any of the above**: that the installer installs. It
has been compiled and inspected, never executed. Item 2 stays open, and the
walk below is still the thing that closes it.

## The clean-machine walk (Fabio Posser, on a machine that has never held the source tree)

**Any step that does not behave as described rejects the milestone** -- this
walk is what turns "the code looks right" into "the product actually
installs and works," and a failure here is a defect, not a note for later.

### Prerequisites

- A Windows machine that has **never** had this repository's source tree on
  it -- the whole point of this walk is proving the resource seam and the
  installer, not a developer's already-configured checkout.
- **AEDT 2025 R2 Commercial** installed and licensed on that machine. FEMM
  is optional; install it too if you want to exercise the FEMM backend, but
  its absence is not a failure of any step below.
- **A project file, copied there by hand.** This release ships no sample
  project (ruled 2026-09-01), so step 3 needs a `.inductor.json` file that
  did not come from the installer. Get one either of two ways: copy the
  tracked fixture `tests/fixtures/sample_geometry_project.inductor.json`
  from a source checkout (it is in git, so every checkout has it, and the
  live FEMM tests load it -- so it is current against the document schema),
  or use any existing `.inductor.json` of your own. Do NOT reach for
  anything under `artifacts/`: that directory is git-ignored, so whatever
  is in it exists only on the one machine that produced it. Copy the file
  onto the clean machine by USB drive, network share, or any transfer
  method you trust -- this application never reaches across machines by
  itself.
- The installer file (`inductor-designer-0.1.0-setup.exe`) and
  `SHA256SUMS.txt`, both from the GitHub release or a build you trust.

### Time to allow

About 45-60 minutes: the install and SmartScreen prompt are quick, but a
real Generate/Solve/Export cycle against a licensed AEDT session takes
several minutes on its own, and this walk asks you to also confirm the
uninstaller separately afterward.

### Steps

1. **Verify the download.** Open PowerShell where you saved the installer
   and run
   `Get-FileHash .\inductor-designer-0.1.0-setup.exe -Algorithm SHA256`.
   Compare the printed hash, case-insensitively, against the matching line
   in `SHA256SUMS.txt`. They must match exactly.
2. **Run the installer.** Double-click it. **Expect a SmartScreen warning**
   ("Windows protected your PC", publisher "Unknown publisher") -- this is
   expected for this unsigned release, not a sign of a problem. Click
   **More info**, then **Run anyway**. Confirm the installer never asks for
   administrator elevation (no UAC prompt), and that it offers an unticked
   "Create a desktop shortcut" option.
3. **Launch from the Start Menu.** Confirm a console window opens alongside
   the application window (expected -- see the release notes), and that the
   application window itself opens without error.
4. **Open the project file you copied over** (File > Open). Confirm it
   loads: the winding count and core selection match what you expect from
   that file, and the 3D preview renders (not a blank pane).
5. **Author a change.** Edit something on the Windings or Core & Material
   screen (a turn count, a wire gauge, anything that changes the design).
   Confirm the 3D preview updates to match.
6. **Generate.** Save the project first if `Generate` is disabled with a
   reason (it stays disabled until the document has no unsaved edits).
   Generate the design against your chosen backend (Maxwell 3D, Maxwell 2D,
   or FEMM if installed). Confirm it completes without error and a `runs/`
   directory appears beside the project file.
7. **Solve (optional but recommended if you have a free licence seat).**
   From the same run, let it solve. Confirm the Review screen shows results
   (resistance, inductance, losses) once the solve finishes, or a clearly
   labelled unavailable reason if it does not.
8. **Export results.** Confirm `results.json` and `results.csv` exist inside
   the run's directory, and open one to confirm it has real numbers in it
   (not `null` throughout, unless the run genuinely produced no results).
9. **Save, close, and reopen.** Save the project, close the application
   entirely, relaunch it, and open the same project file again. Confirm the
   design matches what you saved -- same windings, same core, same edits
   from step 5.
10. **Uninstall.** Before uninstalling, note
    `%LOCALAPPDATA%\InductorDesigner`'s current contents:
    `Get-ChildItem -Recurse "$env:LOCALAPPDATA\InductorDesigner" | Select-Object FullName, Length, LastWriteTime`.
    Then uninstall (Settings > Apps, or the `unins000.exe` under the install
    directory). Confirm the install directory
    (`%LOCALAPPDATA%\Programs\PyAEDT Inductor Designer`) and both shortcuts
    are gone, **and** that `%LOCALAPPDATA%\InductorDesigner` still exists
    with every file in it -- by name, byte count, and modified time --
    unchanged from the `Get-ChildItem` output you captured just before
    uninstalling. This directory holds your recovery snapshots and the
    application log; the installer must never touch it.

### Recording the walk

Fill this in as you go.

| Step | Expected | Observed | Pass / fail |
| --- | --- | --- | --- |
| 1 | The downloaded installer's hash matches `SHA256SUMS.txt` exactly | | |
| 2 | SmartScreen warns, no admin prompt, install completes, desktop shortcut option offered unticked | | |
| 3 | Start Menu shortcut launches the app; a console window is also visible | | |
| 4 | The copied-over project opens; the 3D preview renders | | |
| 5 | An edit on Windings or Core & Material updates the 3D preview | | |
| 6 | Generate completes; a `runs/` directory appears | | |
| 7 | Solve completes with results shown, or a labelled unavailable reason | | |
| 8 | `results.json` / `results.csv` exist with real values | | |
| 9 | Save, close, reopen reproduces the saved design exactly | | |
| 10 | Uninstall removes the program and shortcuts; `%LOCALAPPDATA%\InductorDesigner` is byte-for-byte and mtime-for-mtime unchanged | | |

## Known risks carried forward

Unchanged from the plan; repeated here because they remain true after this
task and Fabio Posser's walk is what tests most of them directly:

1. **PyInstaller and PySide6 Qt plugins.** A frozen Qt application that
   starts but renders nothing is almost always a missing platform or QML
   plugin. Task 3's post-prune re-launch found no such error, but see "What
   is NOT verified on this machine" above -- the window itself was not
   re-screenshotted after the prune.
2. **PyAEDT inside a frozen bundle.** Whether it works frozen at all remains
   unverified; the M8 live-solve evidence is exercised only from source.
   Step 6/7 of the walk above is the first real test of this.
3. **Antivirus on an unsigned one-folder bundle.** BRUSA endpoint protection
   may quarantine an unsigned executable; outside this application's
   control, and worth knowing if step 2 or 3 of the walk behaves
   unexpectedly.
4. **The catalog build is a build-time dependency on source data.** If
   `catalog/` and the built index ever disagree, the installed application
   ships something no developer ran. Unchanged mitigation: the index is
   built during packaging, never copied.
5. **`INDUCTOR_DESIGNER_RESOURCES` is a support tool with product reach.**
   Documented in the release notes per Task 1's docstring promise; a
   mis-set value now produces a refusal naming the override as the cause
   rather than a silent wrong-data launch (Task 1's Minor 4 fix, above).

## The defect 0.1.0 actually shipped, found by installing it (2026-09-03)

Fabio Posser installed 0.1.0, launched it from the shortcut, and reported
that there was no core to select. Every core-selection screen was empty, on
every step, and there was no way in the application to open or create a
project.

The walk above never caught it because every step of it, and every test,
launches with `--project`. Nothing exercised the launch the installer's own
shortcuts perform.

**What was wrong.** `main()` built the `ProjectSession` only inside `if
project is not None`, and `project` came only from `--project`. The
installer's `[Icons]` entries pass no arguments at all, so a shortcut launch
reached QML with `projectSession` null, and every screen controller with it:
the Core & Material core list is `controller !== null ? controller.coreOptions
: []`, which is `[]`, and Windings, Preliminary, Simulation and Review were
equally inert. `File > Open` -- the one control that could have loaded a
project -- is gated on `projectSession !== null`, so it was disabled exactly
when it was needed, and there was no `File > New` at all. The only way into
the shipped application was a command line.

The catalog was never involved. The installed
`_internal/artifacts/catalog/catalog.sqlite` carries all 15 core records; it
was read and counted directly to rule this out before anything was changed.

**What the release notes said.** "The first launch opens with nothing loaded;
use **File > Open** with your own project" -- a flow the application could
not perform. Documentation asserting a capability nobody had executed.

**Fixed** by `docs/superpowers/specs/2026-09-03-blank-project-on-launch-design.md`
and its plan: a launch with no `--project` now opens a blank unsaved project,
so every screen is live, plus `File > New` and a `Save` that asks for a name
when the project has none. Three further defects surfaced while implementing
it, each found by running the thing rather than reading it:

- `GuidedStudioController.__init__` built the geometry preview unguarded, and
  `build_geometry_model` refuses a project with no core. A blank project
  raised `GeometryModelError` out of the constructor -- the fix's own first
  attempt crashed on launch until the constructor adopted the tolerance
  `refresh()` already had.
- The cut plane kept saying "Select a core to see the winding cross-section."
  after a core had been selected. With no previous valid preview to keep,
  `refresh()`'s keep-the-last-geometry behaviour left the placeholder
  standing while the real refusal ("Wire does not fit the core bore at layer
  1", which `AWG 18` genuinely earns in the smallest powder toroid) reached
  nowhere the user could see.
- `sequence: StandardKey.Redo` bound one of the two bindings Windows gives
  Redo, so Ctrl+Shift+Z did nothing. Qt says so at load; because that warning
  carries a QML source location, it also leaked intermittently into the
  shortcut tests' own no-QML-errors assertion under `pytest -n 8`.

**The lesson for this record.** Every step of the clean-machine walk above
starts from a project document. The one thing a first-time user does --
double-click the shortcut and look for a core -- was not among them.

## Accepted (2026-09-04)

Fabio Posser accepted Milestone 10 on 2026-09-04, after installing the
release and using it. What acceptance does and does not cover:

**Covered.** The installer (per-user, unsigned, no administrator), resource
resolution inside the frozen bundle, AEDT 2025 R2 Commercial detection with
FEMM optional, the release artifacts and their checksums, and -- after the
two defects below were fixed -- authoring a design from a shortcut launch:
opening a blank project, choosing a core, editing a winding, and saving.

**Not covered.** A live solve from the frozen bundle. Known risk 2 remains
open: PyAEDT has only ever been exercised from source. Acceptance was granted
with that stated, not overlooked.

**The two defects acceptance was granted around**, both found by installing
rather than by testing, and both fixed first: 0.1.0's shortcut launch could
neither open nor create a project, which presented as an empty core list on
every screen; and an installed user had no way to add a core, since that
required the source tree and a rebuilt installer. Shipped as 0.2.0 and 0.3.0
-- separate version numbers because a build that differs must not answer to a
number whose hash is already published.
