# Material Import Templates and Workbook Design

**Date:** 2026-07-18
**Owner:** Codex
**Status:** Approved for implementation planning

## Goal

Provide self-describing material-data templates so users can prepare B-H and
core-loss curves without guessing file structure, column meanings, or units.
The application layer must accept equivalent CSV and Excel `.xlsx` uploads.
Material Studio will connect these capabilities to download and upload buttons
in Milestone 5b.

## Scope

This change delivers:

- one downloadable Excel workbook containing instructions, material metadata,
  B-H curves, and loss curves;
- one downloadable flat CSV template with the equivalent fields;
- unit dropdowns and basic spreadsheet validation in the Excel workbook;
- application services that parse and validate both formats into the existing
  material-record import model;
- packaged template access suitable for a future UI download action; and
- documentation and automated tests for both formats.

This change does not add the Material Studio screen. Interactive download,
upload, revision browsing, review, and approval controls remain in Milestone
5b. Importing a file never approves a material automatically.

## Canonical Units and Ansys Boundary

User files may use common datasheet units. Import converts them to the existing
canonical representation before validation and solver export:

| Quantity | Template choices | Canonical value |
|---|---|---|
| Magnetic field H | `A/m`, `kA/m`, `Oe` | `A/m` |
| Flux density B | `T`, `mT`, `G`, `kG` | `T` |
| Loss density P | `W/m3`, `kW/m3`, `mW/cm3` | `W/m3` |
| Frequency | `Hz` | `Hz` |
| Temperature | `degC` | degrees Celsius |
| DC bias H | `A/m` | `A/m` |

The solver boundary continues to receive B-H data in SI units. Maxwell's
official material scripting interface supports H units including `Oe`,
`A_per_meter`, and `kA_per_meter`, and examples use H in A/m with B in tesla.
The application deliberately normalizes the broader datasheet choices above
instead of passing spreadsheet units through to a solver adapter.

References:

- https://ansyshelp.ansys.com/public/Views/Secured/Electronics/v251/en/Subsystems/Maxwell/Subsystems/Maxwell%20Scripting/Content/AddMaterialMaxwell.htm
- https://ansyshelp.ansys.com/public/Views/Secured/Electronics/v251/en/Subsystems/Maxwell/Subsystems/Maxwell%20Scripting/Content/EditMaterialMaxwell.htm

## Excel Workbook

The packaged workbook is named `material-import-template.xlsx` and has four
visible sheets.

### Instructions

Explains the workflow, supported units, required fields, one-series rules, and
that the example rows are synthetic and must be replaced before review.

### Material

Contains one value column for:

- manufacturer;
- material name;
- grade;
- source URL;
- source page;
- capture timestamp; and
- source description.

Manufacturer, material name, grade, capture timestamp, and description are
required. URL and page may be blank when the source is a local or unpublished
document. The uploaded workbook itself is the source artifact hashed for
provenance; source metadata describes where its values came from.

### B-H Curves

Columns:

`series_id`, `temperature_c`, `dc_bias_a_per_m`, `h`, `h_unit`, `b`, `b_unit`

The sheet may contain multiple series. Rows sharing a `series_id` must repeat
identical metadata. Numeric H and B values sit immediately before their unit
columns. `h_unit` has a dropdown containing `A/m`, `kA/m`, and `Oe`.
`b_unit` has a dropdown containing `T`, `mT`, `G`, and `kG`. DC bias is
optional condition metadata; blank means not supplied and `0` means explicitly
zero bias.

### Loss Curves

Columns:

`series_id`, `frequency_hz`, `temperature_c`, `dc_bias_a_per_m`, `b`, `b_unit`,
`loss`, `loss_unit`

The sheet may contain multiple series. Rows sharing a `series_id` must repeat
identical metadata. Frequency is required and positive. Numeric B and loss
values sit immediately before their unit columns. `b_unit` uses the B dropdown
above; `loss_unit` contains `W/m3`, `kW/m3`, and `mW/cm3`. DC bias remains
optional measurement metadata and is not currently an independent solver input.

The workbook embeds the short unit choices directly in each list validation
and contains no support sheet. This decision avoids relying on worksheet
visibility controls that the approved artifact-tool authoring API does not
expose. Filters, input highlighting, concise instructions, and sensible column
widths make the template usable without changing its schema. Headers are not
frozen because artifact-tool 2.8.6 does not persist its documented freeze-pane
setting during XLSX export; this compact template remains usable without it.

## CSV Template

The packaged file is named `material-import-template.csv`. Because CSV has no
sheets or dropdowns, it uses one flat table with these columns:

`manufacturer`, `material_name`, `grade`, `source_url`, `source_page`,
`captured_at`, `source_description`, `series_id`, `curve_kind`,
`frequency_hz`, `temperature_c`, `dc_bias_a_per_m`, `x_unit`, `y_unit`, `x`,
`y`

`curve_kind` is either `bh-curve` or `loss-table`. Material and series metadata
repeat on every row. The parser groups rows by series and requires repeated
metadata to agree. For B-H rows, `x` is H and `y` is B. For loss rows, `x` is B
and `y` is loss density.

The CSV contains synthetic example rows for both curve kinds. Users replace or
delete them before upload.

## Parsing and Data Flow

A new application service accepts a filename and bytes:

1. Select the parser strictly from the lowercase file extension (`.csv` or
   `.xlsx`); other formats are rejected with a typed import error.
2. Parse cells as typed values and reject formulas in data or metadata cells.
3. Validate required columns, material identity, supported units, finite
   numbers, consistent repeated metadata, and nonempty series.
4. Convert each group through the existing `import_curve_csv` path so unit
   conversion, sorting, rounding, and physics validation remain centralized.
5. Return the material identity, source metadata, and imported point series for
   the existing draft-record lifecycle.

The `.xlsx` implementation uses `openpyxl` as a runtime dependency. Recreating
a reliable Excel reader with `zipfile` and raw XML would add more bespoke code
and risk than one established dependency. Workbook authoring and visual QA use
the repository's artifact workflow; runtime parsing does not depend on the
authoring tool.

## Template Distribution

Templates live as packaged resources under the application package rather than
only in documentation. A small application service exposes immutable bytes by
format (`csv` or `xlsx`) and a suggested filename. M5b can call this service
from a save-file dialog without knowing repository paths.

The templates are also linked from the material-record documentation for
developers and pre-UI testing.

## Exporting and Updating an Existing Material

The template service also exports a selected `MaterialRecord` as an editable
Excel workbook. It starts from the verified packaged workbook so styling,
instructions, columns, and dropdown validations stay identical to the blank
template. It removes the synthetic example rows and fills:

- manufacturer, material name, and grade;
- every B-H and loss series;
- each series identifier, unit choices, frequency, temperature, and DC bias;
  and
- a source description identifying the exported base revision.

Stored curve points are canonical SI values, while each series retains the
units used at import. Export converts canonical points back to those retained
units so the workbook displays the selected material in its original unit
system. A new `from_canonical(value, unit)` unit helper is the inverse of the
existing conversion path and supports only the already-approved material
units.

The exported workbook itself becomes the source artifact when uploaded again.
The original approved revision remains immutable. A high-level import service
creates a new `draft` record and returns its source files; it never overwrites,
reviews, or approves the selected base revision. Loss fits are recomputed from
the edited loss tables rather than copied from the old revision. Image-derived
series are exported as editable tabular points and therefore become
spreadsheet-derived series in the new draft.

Records without any B-H or loss series cannot produce an editable curve
workbook and are rejected with an actionable export error. Material Studio M5b
will call this export service from “Download current material” and the draft
import service from its upload action.

## Error Handling

All file-shape and content failures raise `MaterialImportError` with actionable
messages that identify the sheet or CSV row, field, and expected value. The
parser accumulates independent row errors where practical but does not create
partial imported results. Spreadsheet dropdowns are guidance only; server-side
validation is authoritative.

## Testing

Tests are written before implementation and cover:

- packaged CSV and Excel templates are readable and contain the documented
  sheets or columns;
- Excel unit cells have the expected dropdown validation lists;
- equivalent CSV and Excel inputs produce equal canonical series;
- multiple B-H and loss series are grouped correctly;
- supported CGS and SI unit choices convert correctly;
- missing columns, unknown units, formulas, nonfinite values, inconsistent
  repeated metadata, and unsupported extensions are rejected clearly;
- packaged-resource access works from an installed-package-style path; and
- exporting a record preserves all series, original unit selections, and
  conditions, while converting canonical points back to those units;
- reimporting an exported workbook creates a different draft revision and
  leaves the base approved revision unchanged;
- scalar-only records are rejected by editable-workbook export; and
- workbook rendering is visually inspected for clipping and readability.

The full non-live test suite, Ruff, strict mypy, the architecture checker, and
diff checks remain required before merge and push. Live Ansys and FEMM are not
required because this feature ends at canonical material records and uses the
already-tested solver boundary.
