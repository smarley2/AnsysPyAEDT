# PyAEDT Inductor Designer 0.4.0

Windows installer. This file is edited in place for each release rather than
starting a new one, so the version and the artifact hashes below always
describe what is actually attached to the current GitHub release.

## What changed in 0.4.0

- **Conductor sizes now show their review status.** All 35 shipped conductor
  sizes are draft transcriptions of IEC 60317 and AWG tables, never checked
  against the source by a second person, and every winding is sized on one of
  them. The Windings screen says so, and Review states it for the core and
  each winding's conductor.
- **You can mark an imported core reviewed** once you have checked its
  numbers against the datasheet -- see "Adding your own cores".
- **`--check-solver-imports`** reports whether this installed build can
  import the PyAEDT and FEMM modules it needs, without starting AEDT.

## What changed in 0.3.0

**You can add your own cores.** The shipped catalog carries 15 toroids; a core
it does not have used to require the source tree and a rebuilt installer.
Download a template on **Core & Material**, fill one row per part number from
the datasheet, and import it -- see "Adding your own cores" below.

Every core row now states whether it is `reviewed` or `draft`, and whether it
was shipped or imported. Five of the shipped ferrite cores are `draft`
transcriptions; they always were, and now the list says so.

Your imported cores and materials are kept under
`%LOCALAPPDATA%\InductorDesigner`, outside the program folder. Imported
materials previously lived inside the installed folder, where upgrading the
application could remove them -- if you imported materials into 0.1.0, copy
them out of the old program folder before uninstalling it.

## What changed in 0.2.0

**0.1.0 could not be used from its own shortcut.** It opened with no project,
and without one every screen was empty -- the Core & Material screen offered
no cores to select -- while `File > Open`, the only way to load a project,
was disabled precisely because no project was loaded. There was no
`File > New`. The catalog was never at fault: 0.1.0 shipped all 15 core
records and could not show you any of them. If you installed 0.1.0, replace
it with this build.

- A launch with no project now opens a blank, unsaved project, so every
  screen is live from the first click (see "No sample project is shipped").
- **File > New** starts another blank project, warning first if the current
  one has unsaved edits.
- **File > Save** asks for a filename when the project does not have one yet,
  instead of reporting that it cannot save.
- The winding cross-section now says why it is empty. Picking a core whose
  bore cannot hold the winding's conductor reports that ("Wire does not fit
  the core bore at layer 1") rather than showing nothing.
- **Ctrl+Shift+Z** redoes. Only Ctrl+Y was wired up before.

## Supported target

**AEDT 2025 R2 Commercial only.** No other AEDT release, no other edition
(Student or otherwise), and no other Ansys product is supported. If AEDT is
not the 2025 R2 Commercial release, the application still starts, but the
solver-backend picker reports it as an unsupported release rather than as
missing -- those are different problems with different remedies, and the
application tells you which one you have.

## FEMM is optional

FEMM (femm.info's free 2D solver) is detected automatically if it is
installed, and its absence is normal -- the application never treats a
missing FEMM as an error. What its absence costs: FEMM is only ever an
alternative *2D* solver backend, so without it you lose the option to solve
a 2D design with FEMM specifically. Maxwell 2D and Maxwell 3D, both through
AEDT, are unaffected either way -- FEMM never participates in 3D.

## The MCP server is not included in this version

`inductor-designer-mcp`, the Model Context Protocol server that lets an
external MCP client (Claude Desktop, or any other MCP-speaking tool) drive
this application's catalog, project and generation tools, is **excluded from
this installer**. It stays in the source repository
(`src/inductor_designer/mcp_server/`) and keeps working exactly as before
from a source checkout (`pip install -e ".[mcp]"`, then
`inductor-designer-mcp`) -- it is a packaging exclusion, not a feature
removal. Nothing in the installed application references it.

## The installer is unsigned

This release has no code-signing certificate. **Windows SmartScreen will
show a warning the first time you run the installer** -- "Windows protected
your PC", with the publisher listed as "Unknown publisher". This is
expected for this release, not a sign the file was tampered with -- verify
that yourself with the checksum below before proceeding if you want
independent confirmation.

To proceed past the warning: click **More info**, then **Run anyway**. If
your organization's endpoint protection blocks the executable outright
rather than warning, or quarantines the extracted bundle, that is your
antivirus policy responding to an unsigned executable, not a defect this
application can work around from inside the installer -- see your IT
department about an exception if you hit this.

## A console window opens behind the application

The frozen build is a console-subsystem executable, not a windowed one, so a
console window appears (briefly, or for the whole session if launched from a
terminal) alongside the application window. This is deliberate: it is what
keeps `inductor-designer.exe --help` and the startup refusal messages (a
missing shipped resource, a locked project) readable as plain text, for
anyone launching from a terminal or from a support script. A Start Menu or
desktop shortcut cannot suppress it in this release.

## Installing and uninstalling

- **Per-user install, no administrator needed.** The installer requests no
  elevation and installs to `%LOCALAPPDATA%\Programs\PyAEDT Inductor
  Designer`, not `%ProgramFiles%`. An engineering workstation account that
  cannot elevate can still install this application.
- A Start Menu shortcut is created unconditionally; a desktop shortcut is
  offered as an unticked, opt-in checkbox during install.
- Uninstalling (Settings > Apps, or the `unins000.exe` the installer writes
  alongside the application) removes the installed program only. It never
  touches `%LOCALAPPDATA%\InductorDesigner`, which holds your crash-recovery
  snapshots and the application log -- that directory, and everything in it,
  survives an uninstall untouched.

## No sample project is shipped

Nothing this installer places on your machine carries a design. The first
launch opens a blank, unsaved project: no core selected, one winding, and a
neutral operating point (100 kHz, no current). Pick a core on **Core &
Material**, edit the winding, then use **File > Save As** to name the file.
A run cannot start until the project has been saved, because every run
writes its directory beside the project document.

**File > New** starts another blank project at any time, and **File > Open**
loads an existing `.inductor.json` from anywhere it already exists.

## Adding your own cores

The shipped catalog carries 15 toroids. To use one it does not have:

1. On **Core & Material**, click **Core template…** and save the empty table
   (`.csv`, or `.xlsx` if you name it that way).
2. Fill one row per part number, straight from the datasheet. Every column is
   required except the tolerance bounds (`...MinM`, `...MaxM`) and
   `reviewedBy`, which may be left blank. Dimensions are in **meters**, areas
   in m2, volumes in m3, and `alValueNh` in nH per turn squared.
3. `sourceUrl` and `sourcePage` are required on purpose: a core whose numbers
   cannot be traced back to a page is a core nobody can check.
4. Click **Import cores…** and choose the filled file.

Every row that stands on its own is imported; the rest are reported by row
number and reason, so a single typo does not cost you the other nine rows of
a family. Imported cores appear in the core list marked **imported, draft**
and can be used immediately -- `draft` means the numbers have not been
checked against the cited page by a second person, not that they are
unusable.

Once you have checked an imported core's numbers against the datasheet
yourself, select it and use **Mark reviewed** -- it asks who did the checking
and records that name with the core, because a review status with nobody
attached to it is the same unverified number wearing a better label. It marks
your local copy as checked; a core that belongs in the product still gets
added to the shipped catalog by the development team. The control appears only
for your own imported drafts: a shipped core's status belongs to the catalog's
own review process.

A part number the shipped catalog already carries is refused rather than
replaced, so a project's Review page can never cite a catalog part while
using someone's edited numbers. Rename yours, or use the shipped core.

Formulas in a spreadsheet cell are refused. Every value has to be a number
read from the datasheet, because a formula is a value this application cannot
show you or cite.

### Where your cores and materials are kept

`%LOCALAPPDATA%\InductorDesigner\catalog-overlay\cores` (one file per core)
and `%LOCALAPPDATA%\InductorDesigner\materials-overlay`. Both sit beside
your logs and recovery snapshots, outside the installed program folder, so
upgrading or uninstalling the application does not touch them. To remove an
imported core, delete its file.

## Checking the solver stack without solving

```
"%LOCALAPPDATA%\Programs\PyAEDT Inductor Designer\inductor-designer.exe" --check-solver-imports
```

Reports whether this installed build can import the PyAEDT and FEMM modules
it needs and find the data files PyAEDT reads off disk, then exits. It does
not start AEDT, does not need a license and does not solve, so it is safe to
run anywhere -- useful when a run fails and the question is whether the
installation is incomplete or the solver itself refused. `FEMM absent` is a
normal result; a `FAILED` line naming an `ansys.aedt.core` module is not, and
belongs in a support report with the application log.

## `INDUCTOR_DESIGNER_RESOURCES`

The application ships four resources beside its executable: the JSON
schemas, the built catalog index, the AEDT compatibility matrix, and the
material overlay. Setting the environment variable
`INDUCTOR_DESIGNER_RESOURCES` to a directory containing that same layout
(`schemas/`, `artifacts/catalog/catalog.sqlite`, `compatibility/aedt-matrix.yml`,
`materials-overlay/`) overrides where the application reads all four from,
taking priority over the shipped copy beside the executable. This exists so
a support engineer can point an already-installed build at a corrected
catalog or overlay without waiting for a new installer. It is a support
tool, not a normal end-user setting: if it is set to a directory missing one
or more of those four resources, the application refuses to start and names
exactly which resource is missing and that the override is the reason,
rather than starting with silently wrong or absent data.

## Known limitations

- **No automated live-solver test exists for the reliability behavior M9
  added** (autosave, crash recovery, interrupted-run reconciliation, the
  diagnostic bundle). M9's forced-failure evidence runs against the real
  catalog and material data with recording fakes standing in for AEDT and
  FEMM, not a live solver session; the one live-adjacent check was a manual
  walk on a real workstation.
- **Eight M9 product questions remain open**, each shipped with a working
  default that this release inherits unchanged:
  - Autosave interval: 2000 ms debounce.
  - Recovery snapshot location: `%LOCALAPPDATA%\InductorDesigner\recovery\`,
    not beside the project document.
  - Undo depth: bounded at 50 project snapshots.
  - Recovery prompt vs. silent restore: prompts once at startup
    (Recover / Discard), never restores silently.
  - Whether a diagnostic bundle is also written automatically on a failed
    run: no -- only when you ask, from **Help > Save diagnostic bundle...**.
  - Whether reconciling an interrupted run is automatic: yes -- it happens
    at startup and on every **File > Open**, so a stale "running" manifest
    is never displayed as if it were still live.
  - How long interrupted-run directories are kept: indefinitely -- nothing
    in this application deletes them; they are your evidence.
  - **A redaction residual in the application log and diagnostic bundle**:
    an extensionless path whose last path component contains a space
    strands its last word when redacted (`opened C:\Users\Jane Doe` becomes
    `opened [redacted-path] Doe`). This was found and accepted as a known
    residual during M9; the alternative (letting the final path segment
    admit spaces) was measured and found worse, because it swallows the
    word after *every* redacted path, not just the rare one with a space in
    its last component.
- **The catalog index is built during packaging, not shipped as source.**
  `artifacts/catalog/catalog.sqlite` is generated fresh from the canonical
  `catalog/` YAML every time this installer's bundle is built
  (`packaging/build_frozen.py`); it is not a file that exists in the
  repository to be copied. If you rebuild this installer yourself from
  source, the catalog you get is whatever `catalog/` contains at build time.

## The diagnostic bundle is safe to share

**Help > Save diagnostic bundle...** writes a `.zip` you can attach to a bug
report without exposing anything private. Every path, machine name, user
name, licence-server identifier, and e-mail address inside it is redacted
before it is written -- verified adversarially during M9 against the real
redaction code, not merely asserted.

Two things are deliberately **excluded** from the bundle entirely, not
redacted:

- **The project document itself** (your `.inductor.json`). It is free text
  a redaction rule cannot reliably classify -- attach it yourself only if
  you judge it safe to share.
- **AEDT's own log files.** Their format is not something this application
  controls, so their redaction cannot be proven the way this application's
  own log can. Instead, the diagnostic bundle captures AEDT's desktop
  message channel through this application's own redacting logger at every
  stage failure, so the evidence AEDT would have shown you is still in the
  bundle -- just captured by code this application owns, not copied from
  AEDT's own files.

`bundle-contents.json`, the first entry in every bundle, states both
exclusions and their reasons explicitly, along with everything the
redaction pass removed.

## Verifying what you downloaded

`SHA256SUMS.txt`, published alongside the installer and the bundle archive
on the release, names each artifact by its SHA-256 hash and its filename
only -- never by a download link. Verify what you downloaded actually
matches before you run it:

```powershell
Get-FileHash .\inductor-designer-0.4.0-setup.exe -Algorithm SHA256
```

Compare the printed hash, case-insensitively, against the matching line in
`SHA256SUMS.txt`. Artifacts are published on the `smarley2/AnsysPyAEDT`
GitHub release for now; if this repository ever moves to a different host,
the checksum is what still identifies the artifact correctly -- the
download link is not the source of truth, the hash is.
