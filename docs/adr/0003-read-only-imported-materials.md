# ADR 0003: Read-Only Imported Material Revisions

- Status: Accepted
- Date: 2026-07-23

## Context

Material Studio is backed by user-provided CSV/XLSX tables. The previous page
treated an upload as a draft and exposed point editing, series metadata editing,
and manual review/approval actions. That made the spreadsheet and the UI two
competing sources of truth and made a valid import unnecessarily depend on a
second lifecycle workflow.

Maxwell loss data also requires an origin point. User workbooks must remain
unchanged for provenance, while the normalized data used by storage and
simulation needs the solver-compatible origin when it is absent.

## Decision

1. A validated CSV/XLSX upload is persisted immediately as an `imported`
   content-addressed material revision. Imported and legacy approved revisions
   are read-only in Material Studio.
2. Changes arrive through `Replace selected material`, which validates and
   stores the replacement before removing an unpinned previous imported
   revision. `Delete selected material` is confirmation-gated and refuses to
   remove revisions pinned by the active project.
3. The page only selects revisions and series, displays provenance/validation,
   previews curves with independent linear/log axes, and explicitly pins a
   material revision and B-H series to a loaded project.
4. For a loss series whose B values are all positive, import prepends `(0,0)`
   to the generated normalized source and stored record. A zero-B nonzero-loss
   point or invalid ordering is rejected. The uploaded workbook remains the
   original byte-for-byte provenance source, and the inserted origin is ignored
   by the Steinmetz fit.

## Consequences

- Spreadsheet files are the single editing surface; the UI cannot silently
  diverge from them by changing points or metadata.
- Imported revisions can be used by simulation without a reviewer or approver,
  while existing approved records and legacy lifecycle APIs remain readable.
- The local material overlay is a filesystem repository. It may be committed to
  Git for collaboration only when source redistribution is permitted; the
  application does not automatically commit or delete the user's workbook.
- A future UI editing workflow would require a new approved specification and
  ADR rather than re-enabling the removed controls implicitly.
