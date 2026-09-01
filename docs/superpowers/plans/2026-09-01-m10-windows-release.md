# M10 Windows Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Windows installer that puts this application on a machine which has never seen the source tree, and which then completes the whole workflow — author, generate, optionally solve, export results, save, reopen — against AEDT 2025 R2 Commercial.

**Entry condition:** Milestone 9 accepted by Fabio Posser on 2026-09-01.

**Release decision, 2026-09-01:** the **MCP server is not shipped in this version**. `src/inductor_designer/mcp_server/` stays in the repository and keeps working from a source checkout, but it is excluded from the frozen application and from the installer, and the release notes say so. The `inductor-designer-mcp` console script stays in `pyproject.toml` for source installs; nothing in the packaged product references it.

## What "installed" has to mean, and why bullet 1 is bigger than it reads

Two facts, verified on 2026-09-01, decide the shape of this milestone:

1. **No data file is in any distribution today.** `[tool.hatch.build.targets.wheel]` packages `src/inductor_designer` and nothing else, so `schemas/`, `catalog/`, `compatibility/aedt-matrix.yml` and `materials-overlay/` are absent from the wheel. The application reads all four through paths relative to the working directory (`_DEFAULT_SCHEMAS = Path("schemas")` and its three siblings in `ui/main.py`, plus `SchemaRepository(root / "schemas")` in the MCP server). Started from a shortcut, whose working directory is anything at all, every one of those fails.
2. **The catalog index is not a source file.** `artifacts/` is git-ignored; `artifacts/catalog/catalog.sqlite` exists only because `tools.build_catalog` was run locally. A build that copies files cannot produce it — packaging has to build it from the `catalog/` sources, or the installed application starts with no cores and no conductors.

So the first task is a resource seam that answers "where is my data" identically in three environments — a source checkout, an installed wheel, and a PyInstaller bundle — and the packaging task must generate the catalog rather than copy it.

## Global constraints

- Windows is the only supported platform for the product; AEDT 2025 R2 Commercial is the only supported solver target. The non-solver test suite must keep running on the Linux CI runner, which is why the resource seam cannot assume Windows.
- Filesystem, platform and process access stays in `adapters/`; `domain`, `geometry`, `materials` and `simulation` import no OS module. `tools/check_architecture.py` enforces it.
- No physics, schema, catalog value, unit or approximation changes. This milestone ships what M0-M9 built; it does not alter it.
- Add or update tests before implementing.
- Diagnostic and advice codes stay lowercase dotted `<subject>.<reason>`; never reuse or repurpose one.
- A missing or unreadable resource must fail with a message naming what is missing and what to do, never with a traceback. The rule M9 established governs here too: a startup path that dies without explanation is worse than one that refuses clearly.
- No secret, no licence file, no user identity in the installer or in anything it writes. The M9 redaction rules already cover the diagnostic bundle; this milestone must not introduce a new writer that bypasses them.
- All code, comments, commits and UI copy in English.
- Gate: `ruff check .`, `mypy src tools`, `python -m tools.check_architecture`, `pytest -n 8 -m "not aedt and not femm"`.

---

### Task 1: One place that answers "where is my data"

**Files:**
- Create: `src/inductor_designer/adapters/system/resources.py`
- Modify: `src/inductor_designer/ui/main.py` — the four `_DEFAULT_*` constants
- Modify: `src/inductor_designer/mcp_server/server.py` — its `root / "schemas"`
- Modify: `pyproject.toml` — ship the data in the wheel
- Test: `tests/unit/adapters/system/test_resources.py`
- Test: `tests/ui/test_main_wiring.py` — startup still finds everything

**Interfaces:**
- `resource_root() -> Path` — the directory holding the shipped data, resolved for the running environment.
- `schemas_directory()`, `catalog_index_path()`, `compatibility_matrix_path()`, `material_overlay_directory()` — one function per resource, each returning an absolute path.
- `MissingResource(NamedTuple)` with the resource's name and the path looked for, plus `missing_resources() -> tuple[MissingResource, ...]` so startup can report every absence at once rather than one per launch.

**The three environments, in resolution order:**
1. **Frozen** — `getattr(sys, "frozen", False)` is true and `sys._MEIPASS` exists. Data sits beside the executable in the bundle. This is the product.
2. **Installed package** — the data was shipped inside the wheel, so it resolves relative to `inductor_designer.__file__`. This is what `pip install` gives.
3. **Source checkout** — walk up from `inductor_designer.__file__` until a directory containing `schemas/` and `catalog/` is found. This is how every developer and every test runs today, and it must keep working with no environment variable set.

An explicit override comes first, before all three: `INDUCTOR_DESIGNER_RESOURCES`, so a support engineer can point a frozen build at a corrected catalog without a rebuild. Document it in the release notes.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/adapters/system/test_resources.py
def test_a_source_checkout_resolves_every_resource() -> None:
    """The environment every developer and every test runs in. No variable is
    set, the working directory is arbitrary, and all four must still resolve to
    files that exist."""


def test_a_frozen_bundle_reads_beside_the_executable(monkeypatch) -> None:
    """`sys.frozen` and `sys._MEIPASS` are what PyInstaller sets; the product
    only ever runs in this mode, and no test would otherwise exercise it."""


def test_an_override_wins_over_every_other_source(monkeypatch, tmp_path) -> None:
    """A support engineer must be able to point a shipped build at a corrected
    catalog without waiting for a rebuild."""


def test_missing_resources_are_reported_together_and_by_name(tmp_path, monkeypatch) -> None:
    """One launch, one list. Reporting the first absence only means a user with
    three missing files learns that across three launches."""


def test_the_working_directory_does_not_matter(monkeypatch, tmp_path) -> None:
    """The defect this task exists for: every path was relative to the working
    directory, so a shortcut launch resolved none of them."""
```

- [ ] **Step 2: Implement `resources.py`**

Pure resolution plus `Path.is_file()` / `is_dir()` checks. No reading, no parsing — the repositories already own that.

- [ ] **Step 3: Ship the data in the wheel**

Add the four directories to the wheel via hatch's `force-include` (or `shared-data`), so an installed package carries them. Verify by building a wheel into a temp directory and listing its contents; assert the four resources are present in the built artifact, not merely configured.

- [ ] **Step 4: Replace every relative default**

`ui/main.py`'s four constants become calls into the seam, keeping `--catalog`, `--matrix` and the other flags as explicit overrides that still win. `mcp_server/server.py` uses the same seam, so the two cannot drift.

- [ ] **Step 5: Report absences at startup, actionably**

Before building anything, call `missing_resources()`. If it is non-empty, print each one and exit with a distinct code — and show the same list in a window, reusing the `show_launch_refusal` pattern from the project lock, since a shortcut launch shows no console. Add a `resources.missing` advice code to `simulation/failure_advice.py`'s table.

**Acceptance:** all four resources resolve from an arbitrary working directory in a source checkout; a built wheel contains them; a simulated frozen layout resolves them beside the executable; a missing one is named on screen and on stderr rather than raising.

---

### Task 2: Detect what the machine actually has

**Files:**
- Create: `src/inductor_designer/adapters/system/installations.py`
- Modify: `src/inductor_designer/ui/main.py` — log the findings at startup
- Modify: `src/inductor_designer/ui/qml/ReviewPage.qml` or the Simulation panel — surface the detected target
- Test: `tests/unit/adapters/system/test_installations.py`

**Interfaces:**
- `detect_aedt() -> AedtInstallation | None` — the supported release only (2025 R2 Commercial), with the install root it was found in and how it was found.
- `detect_femm() -> FemmInstallation | None` — optional; its absence is normal and must never read as a fault.
- Both return records, never raise.

**How to look, cheapest first:** the `ANSYSEM_ROOT252` environment variable AEDT itself sets; then the standard install location under `%PROGRAMFILES%\ANSYS Inc\v252\AnsysEM`; then the registry, if the first two miss. Record which route succeeded — when a user reports "it says AEDT is missing", the route is the first thing worth knowing.

**What must NOT happen:** detection must not import PyAEDT or start a desktop. It answers "is it installed", not "does it work" — the M8 solve path already answers the second, and starting a session at launch would take a licence seat just to draw a label.

- [ ] **Step 1: Write the failing tests** — a fake environment for each route; absence of AEDT; absence of FEMM as a normal, non-error state; a wrong release present (e.g. v242) reported as unsupported rather than as absent, since those are different remedies.
- [ ] **Step 2: Implement, with no PyAEDT import.**
- [ ] **Step 3: Log both findings once at startup**, through the redacting logger — an install root is an absolute path, so this is exactly the text M9's formatter exists for.
- [ ] **Step 4: Show the detected target** where the user chooses a backend, so an unsupported release is visible before they generate rather than after a failed run.

**Acceptance:** each route detected in isolation; a machine with no AEDT reports absence with the advice code, not a traceback; FEMM absent is silent; a v242-only machine is reported as unsupported.

---

### Task 3: Freeze the application

**Files:**
- Create: `packaging/inductor-designer.spec`
- Create: `packaging/build_frozen.py` — build the catalog, then run PyInstaller
- Modify: `pyproject.toml` — a `packaging` optional-dependency group holding PyInstaller
- Create: `docs/development/packaging.md`
- Test: `tests/unit/tools/test_build_frozen.py` — the build script's own logic, not the freeze

**The catalog is generated, not copied.** `packaging/build_frozen.py` runs `tools.build_catalog` into a temporary directory first and hands PyInstaller the result. A build that finds no catalog must fail loudly at build time; shipping an installer whose application has an empty core list is the worst outcome available here.

**Excluded from the bundle, deliberately:** `inductor_designer.mcp_server` and the `mcp` dependency (the 2026-09-01 release decision), `pytest`, `hypothesis`, `mypy`, `ruff`, and PySide6's unused Qt modules. Every exclusion goes in the spec with a comment saying why, because an unexplained `excludes` entry is how a later maintainer breaks a build they cannot debug.

**One folder, not one file.** A one-file build unpacks to a temp directory on every launch, which costs seconds on a large PySide6 bundle and confuses antivirus. One folder also lets a support engineer replace a single resource in place — which the `INDUCTOR_DESIGNER_RESOURCES` override then makes usable.

- [ ] **Step 1: Write the failing test for the build script** — it must refuse to proceed when the catalog build produces no index, and must pass the resolved data paths to PyInstaller.
- [ ] **Step 2: Write the spec**, with the four resources as `datas` and the exclusions above.
- [ ] **Step 3: Build it, run the frozen executable with `--help`**, and record the output plus the bundle's size and top-level layout in `docs/development/packaging.md`.
- [ ] **Step 4: Launch the frozen application on the sample project** from a working directory that is NOT the checkout — the defect Task 1 exists to prevent, verified against the real artifact rather than a simulated `sys.frozen`.

**Acceptance:** a fresh clone builds a bundle with one command; the frozen executable starts from an unrelated working directory, finds all four resources, and opens the sample project.

---

### Task 4: The installer

**Files:**
- Create: `packaging/installer.iss` — Inno Setup script
- Modify: `packaging/build_frozen.py` — an optional `--installer` step
- Modify: `docs/development/packaging.md`

**Decisions this task implements** (see the open questions for the ones that are Fabio Posser's):
- Per-user install by default (`PrivilegesRequired=lowest`), so no administrator is needed. An engineering workstation user who cannot elevate must still be able to install.
- Start Menu shortcut; desktop shortcut as an unticked option.
- An uninstaller that removes the application but **never** touches `%LOCALAPPDATA%\InductorDesigner` — that holds the user's recovery snapshots and their log. Deleting a recovery snapshot during an uninstall would destroy unsaved work at the worst possible moment.
- Version and product name read from `__about__.py`, so the installer cannot disagree with the application's About box.

- [ ] **Step 1: Write the Inno script** with the above.
- [ ] **Step 2: Build the installer**, install it into a throwaway per-user location, and record what lands where.
- [ ] **Step 3: Verify the uninstaller** leaves `%LOCALAPPDATA%\InductorDesigner` intact — a test that a person can repeat, written down in `packaging.md`.

**Acceptance:** the installer runs without elevation, the Start Menu entry launches the application, and uninstalling removes the program while leaving user data.

---

### Task 5: Release notes, checksums, and the clean-machine walk

**Files:**
- Create: `docs/development/m10-release-evidence.md`
- Create: `packaging/release_notes.md` — the template filled per release
- Modify: `packaging/build_frozen.py` — emit `SHA256SUMS.txt` beside the artifacts

**The release notes must state, plainly:**
- The supported target: AEDT 2025 R2 Commercial, and nothing else.
- That FEMM is optional, and what its absence costs.
- **That the MCP server is not included in this version.**
- The known limitations already recorded: no automated live-solver test in M9, the eight open product questions with their current defaults, and M9's accepted redaction residual (a path whose last component contains a space strands its last word).
- That the installer is unsigned, if it is — a SmartScreen warning that nobody warned the user about reads as malware.

- [ ] **Step 1: Emit checksums** for the bundle and the installer, and verify one by recomputing it independently.
- [ ] **Step 2: Write the release notes** from the template.
- [ ] **Step 3: Write the clean-machine walk** for Fabio Posser, as numbered steps with a recording table, ending at the exit criterion: author, generate, solve, export, save, reopen — on a machine that has never held the source tree. State plainly that a failed step rejects the milestone.

**Acceptance:** checksums verify; the notes carry every item above; the walk is followable by someone who has not read this plan.

---

## Open questions for Fabio Posser

All five were ruled by Fabio Posser on 2026-09-01. They are kept here, with
their reasoning, so the decisions live with the questions rather than only in a
commit message.

1. ~~Per-user or per-machine install?~~ **Per-user.** `PrivilegesRequired=lowest`; no administrator needed to install.
2. ~~Is the installer signed?~~ **Unsigned for this release.** So the release notes MUST warn about the SmartScreen prompt on first run -- an unexplained warning teaches users to click through security prompts, which is worse than the warning itself.
3. ~~What version number ships?~~ **0.1.0.** `__about__.py` is bumped from `0.1.0.dev0`; the installer, the About box and the release notes all read from it, and `tests/unit/test_package.py` pins it.
4. ~~Does the release include the sample project?~~ **No.** Nothing shipped carries a design, so the first launch starts from File > Open with the user's own project. Note the consequence for the clean-machine walk: it needs a project copied to that machine by hand, which Task 5's walk must say.
5. ~~Where do release artifacts live?~~ **A GitHub release on `smarley2/AnsysPyAEDT`, for now.** The checksums file is published beside the installer there. See the migration note below.

## Migrating to a BRUSA-hosted git later

Asked on 2026-09-01, and worth recording because it affects what this release
should avoid baking in. Git is distributed, so moving the repository later is a
remote change, not a conversion: add the new remote, push every branch and tag,
repoint `origin`. Two things in this milestone must therefore stay portable:

- No release artifact, script or document may hard-code the GitHub URL as the
  only source of truth. `packaging/build_frozen.py` must not embed a download
  URL, and the release notes should name the artifact by checksum rather than by
  link alone.
- The CI definition currently targets GitHub Actions. It keeps working until the
  move and is rewritten for whatever BRUSA hosts; nothing in the product reads
  it, so this is not a product dependency.

The move is also the natural moment to settle the identity strings still present
in five commits of this branch's history and in two off-branch files -- a history
rewrite is disruptive on a shared remote, and far cheaper to do while re-pushing
into a fresh one.

## Known risks

1. **PyInstaller and PySide6 Qt plugins.** A frozen Qt application that starts but renders nothing is almost always a missing platform or QML plugin, and the failure appears only in the frozen build. Task 3 Step 4 launching the real artifact — not a simulated frozen layout — is what catches it.
2. **PyAEDT inside a frozen bundle.** PyAEDT imports lazily and reaches for its own installed files; whether it works frozen is unverified here, and the M8 solve path is exercised only from source today. If it does not, the honest fallback is documented in the release notes rather than papered over, since generation and preview do not depend on it.
3. **Antivirus on an unsigned one-folder bundle.** BRUSA endpoint protection may quarantine an unsigned executable. Related to open question 2, and outside this application's control.
4. **The catalog build is a build-time dependency on source data.** If `catalog/` and the built index ever disagree, the installed application ships something no developer ran. Building it in the packaging step, rather than copying a local artifact, is what keeps them the same.
5. **`INDUCTOR_DESIGNER_RESOURCES` is a support tool with product reach.** It lets a shipped build read data from anywhere, which is the point — and also means a mis-set variable produces a confusing failure. Task 1 Step 5's "missing resources" report must name the override when it is set, so the cause is visible.
