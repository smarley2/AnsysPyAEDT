# Streamlined Material Library Design

- Status: Implemented; MVP accepted
- Date: 2026-07-23
- Accepted: 2026-07-23
- Scope: Material Studio library and saved-material workflow

## Purpose

Make Material Studio behave as a spreadsheet-backed material viewer instead of
an internal review or curve-editing workspace.

## Decisions

- The material library shows materials only. It does not expose a separate
  revision list.
- Selecting a material immediately loads its newest stored revision and displays
  its available curves.
- Reviewer and approver metadata are not shown.
- The Fit and Validation pane is removed. Import validation still runs and
  rejects invalid files before persistence.
- A selected material can be downloaded as a generated XLSX workbook containing
  all stored metadata and curves.
- The downloaded workbook is compatible with the existing replacement import
  flow so users can add curves for other frequencies, temperatures, or
  conditions and then choose Replace selected material.
- Replace and Delete remain explicit actions with their existing safeguards.
- Backward compatibility with previously released user projects is not a
  requirement because the software has no production users yet. The internal
  revision model remains because it is already the repository identity and
  removing it does not simplify the requested workflow.

## UI Flow

1. Open Material Studio.
2. Select a material from the library.
3. The newest revision loads automatically.
4. Select any stored series in Curve preview and inspect it with linear or
   logarithmic axes.
5. Optionally download the selected material as XLSX, edit the workbook, and
   replace the selected material with the updated file.
6. Optionally delete the selected material after confirmation.

## Error Handling

- Selecting a material with no stored revisions leaves the curve preview empty
  and reports an actionable status message.
- Download is disabled until a material revision is loaded.
- Filesystem and export errors use the existing controller status reporting.
- Invalid replacement workbooks do not modify the stored material.

## Verification

- Controller tests verify that selecting a material loads its newest revision.
- UI tests verify that revision, reviewer, approver, fit, and validation controls
  are absent.
- UI tests verify that the material XLSX download action is present and enabled
  only for a loaded material.
- Export tests verify that the downloaded XLSX contains all stored series and is
  accepted by the existing material importer.
- A live UI test opens the program, selects a saved material, confirms the curve,
  downloads the workbook, and opens the delete confirmation without deleting
  the material.
