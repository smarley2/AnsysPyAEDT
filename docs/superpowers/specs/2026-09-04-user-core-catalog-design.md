# Adding cores without a rebuild

- Status: Approved 2026-09-04 by Fabio Posser
- Date: 2026-09-04
- Depends on: `2026-09-03-blank-project-on-launch-design.md` (a shortcut launch
  reaches the Core & Material screen at all only after that change)

An installed user cannot add a core. Today a new core means editing
`catalog/cores/*.yaml`, running `python -m tools.build_catalog`, and rebuilding
the installer -- a developer workflow, on a machine with the source tree. This
gives the installed application a way to take a datasheet core and use it.

## What a user-added core is

A full catalog record, the same 17 fields
`schemas/catalog/core.v1.schema.json` already requires -- `effectiveAreaM2`,
`pathLengthM`, `volumeM3`, `alValueNh`, the material identity, `sourceUrl` and
`sourcePage` included.

Not a saved Manual toroid. The Manual core already exists for one-off
dimensions, and it is honest about what it is: `core_magnetic_properties`
(`application/services/preliminary_inputs.py`) derives its path length, area
and volume from ideal toroid geometry, attaches `MANUAL_CORE_PATH_NOTE` as
provenance, and sets `al_value_nh=None` so the A_L cross-check reports itself
unavailable rather than guessing. An added core is meant to be a real part, so
it carries the manufacturer's own numbers and earns the A_L check; deriving
those numbers from three dimensions and presenting the result as a catalog
part would be exactly the silent physical assumption this repository forbids.

## Where they live

`application_data_directory() / "catalog-overlay" / "cores"`, one JSON file
per core, named for the sanitized part number.

That is `%LOCALAPPDATA%\InductorDesigner`, beside `logs/` and `recovery/`.
The reason is specific: the shipped resources live inside the installed
bundle, which an upgrade rewrites, and the uninstaller only removes what
`[Files]/[Icons]/[Dirs]` installed (`packaging/installer.iss`), so nothing
under the per-user data directory can be reached by either. User data an
upgrade can delete is not storage, it is a countdown.

### The same hazard already exists for materials, and is closed here

`resources.material_overlay_directory()` resolves to
`_internal/materials-overlay` inside the bundle, and
`FileOverlayMaterialRepository` both reads the shipped seed material and
writes every user import there. An upgrade rewrites that tree.

The fix is the smallest one that makes writes safe: the material overlay
root becomes `application_data_directory() / "materials-overlay"`, and on
first run -- when that directory does not exist -- the shipped seed tree is
copied into it once. No repository change, no read-both layering, nothing
moved or deleted.

Its ceiling, stated rather than discovered later: a later release shipping a
*corrected* seed material will not reach a user who already has the copy.
That is acceptable while the seed is one reviewed material, and support can
still re-import or point `INDUCTOR_DESIGNER_RESOURCES` at a corrected tree.
If a corrected seed ever has to ship, the upgrade path is read-both layering
(seed read-only, per-user writable), which touches six of the repository's
methods -- the reason it is not the first move.

## How they are read

A second implementation of the existing `CatalogRepository` port
(`application/ports/catalog.py`, four methods), plus a composite that merges
it with the shipped `SqliteCatalogRepository`. Every screen, service and
exporter already talks to that port, so nothing else changes: `list_cores()`
simply returns more.

Records are deserialized by the `core_record_from_json` that already backs
the SQLite reader, so an overlay core and a shipped core are the same
`CoreRecord` type, validated against the same schema.

### Conflicts are refused, never shadowed

An imported core whose `partNumber` already exists in the shipped index is
rejected at import, naming the collision. An overlay file quietly replacing a
datasheet part would mean a project's Review page cites `0077109A7` while the
numbers behind it are someone's edit -- the exact failure the catalog's
provenance rules exist to prevent.

That makes the merge disjoint by construction. One case survives it: a later
release adds a part number a user had already imported. The shipped record
wins on read, and the shadowed overlay file is reported by name, so the user
learns their file is being ignored instead of wondering which numbers are in
play.

### Every imported core is `draft`

Whatever the file's `reviewStatus` column says. `catalog/README.md` rules
that only a human reviewer may set `reviewed`, after checking every number
against the cited source page; an import is not that reviewer.

Which forces one existing gap closed here: `CoreOption` carries no review
status today and the core list never shows one, so a `draft` core and a
reviewed one are indistinguishable when picked. With user cores in the list
that becomes unacceptable, so `CoreOption` gains `review_status` and
`origin` (shipped or imported) and the list shows both. It also labels the
five shipped `draft` ferrite cores honestly for the first time.

## The template and the import

Mirrors materials, which were ruled spreadsheet-only on 2026-07-20: download
a template, fill it, import it. One row per part number, CSV and XLSX both,
with the controller slots named after the ones Material Studio already has
(`downloadTemplate` / `importTable`).

The parser is a new `adapters/catalog/core_table.py`, not a change to
`adapters/materials/table_file.py`: that reader is material-shaped (metadata
blocks, series kinds, unit validation) and a core table is a flat header plus
rows. It borrows the one genuinely general rule from it -- **reject formula
cells rather than evaluate them** -- so an imported `A_L` is a number a person
typed, not the output of a spreadsheet the application cannot see or cite.

Columns are the schema's field names, in schema order, so the template and
the validator can never disagree about what a column means.

Import reports per row: imported, or rejected with the row number and the
reason. A partly-bad file imports its good rows and names the rest -- a
datasheet family is ten rows, and one typo must not discard the other nine.

## The surface

Two buttons beside the existing core list in `CoreMaterialPanel.qml`
(`coreTemplateButton`, `importCoresButton`), a `FileDialog` each, and the
report rendered in the panel's existing `coreMaterialMessage` area. No new
window: the screen that shows an empty core list is where the problem is
felt, and a second window is another engine lifetime, QML tree and place to
look.

## Tests

Red first, at the level each rule lives at.

1. An overlay JSON core appears in `list_cores()`, in `coreOptions`, and can
   be selected into a project end to end.
2. A part number that collides with a shipped core is refused at import,
   naming it, and the shipped record still reads back unchanged.
3. Import writes under `application_data_directory()`, never inside the
   resource root -- asserted against both paths, since surviving an upgrade
   is the whole point.
4. A ten-row file with one bad row imports nine and reports the tenth by row
   number and reason.
5. A formula cell is rejected rather than evaluated.
6. An imported core is `draft` even when the file's `reviewStatus` column
   says `reviewed`.
7. `coreOptions` carries review status and origin, and the shipped ferrite
   cores report `draft`.
8. A shadowed overlay file (part number later shipped) does not win, and is
   reported by name.
9. The material overlay resolves under `application_data_directory()`, and
   the shipped seed material is readable after the one-time copy.
10. The one-time copy does not run when the per-user overlay already exists,
    so it can never overwrite a user's own material with the shipped seed.

## Out of scope

- Promoting an imported core to `reviewed` inside the application. A human
  reviewer's act; `catalog/README.md` rules how.
- Editing or deleting imported cores in the UI. Delete the file.
- Non-toroid families. That is Milestone 11, with its own geometry,
  invariants and live evidence per family.
- Migrating or copying existing user data. Cores are new, and the material
  change seeds only into an empty directory.
