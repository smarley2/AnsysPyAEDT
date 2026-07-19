# Material Records Pipeline

Milestone 5a provides a traceable, deterministic path from source bytes to an
approved magnetic-material revision and solver export. Milestone 5b exposes that
path in the Guided Studio `Materials` page. The final M5b whole-change review is
clean and the fresh complete non-live verification passes (822 tests, 119 UI
tests, and 91.80% coverage). Native Windows manual acceptance remains pending,
so M5b is not yet implementation-complete. Formal M5a/M5b acceptance also remains pending until
a reviewer imports a real datasheet, obtains `MATCH`, and checks the exact pinned
revision in live AEDT and FEMM; no live material handoff is claimed here.

## Overlay layout and integrity

The default local overlay is `materials-overlay/`. It is intentionally not
ignored: a reviewer may commit an approved record when the source material may
legally be redistributed.

```text
materials-overlay/
  <sanitized-manufacturer>/
    <sanitized-material-name>/
      <sanitized-grade>/
        <sanitized-revision-id>/
          record.json
          points-<sanitized-series-id>.csv
          sources/
            <sanitized-source-filename>
```

Every material identity segment, revision identifier, series identifier, and
source filename is passed independently through `sanitize_identifier` for its
physical path. Non-alphanumeric characters other than `_` become `_`, and a
component beginning with a digit gains a `W` prefix. For example, the worked
record below is stored under
`Example_Manufacturer/Example_Material/W60/<sanitized-revision-id>/`;
revision `0123456789ab` would use directory `W0123456789ab`, series
`bh-room-temperature` would use `points-bh_room_temperature.csv`, and source
`loss-100khz.csv` would use `sources/loss_100khz_csv`.

Sanitizing applies only to physical names. The `sources` mapping passed to
`save` and returned by `source_bytes` is keyed by each raw
`SourceProvenance.filename`, such as `"loss-100khz.csv"`. Its keys must match
the raw provenance filenames exactly; the repository translates those names at
the filesystem boundary.

`record.json` is deterministic JSON and embeds the canonical points; each
`points-*.csv` is the corresponding reviewable canonical series. Save-time
checks require:

- exact raw source-mapping keys and matching source SHA-256 hashes;
- points that already satisfy the nine-decimal canonical rounding contract;
- no physical source or series filename collision after sanitizing; and
- no overwrite of an existing approved revision.

Saving stages and verifies the rendered record, source hashes, and CSV/JSON
point agreement before installation. Draft and reviewed records with the same
revision identifier may be replaced atomically; an approved stored revision is
immutable. Normal loads recheck source hashes and CSV/JSON point agreement.

## Material table templates and uploads

Two synthetic, self-describing templates are packaged with the application:

- [material-import-template.xlsx](../../src/inductor_designer/resources/material_templates/material-import-template.xlsx)
- [material-import-template.csv](../../src/inductor_designer/resources/material_templates/material-import-template.csv)

Replace the synthetic example values before review. The workbook and CSV are
equivalent input formats: both produce the same canonical point series when
they contain the same material data. The original upload is retained and
hashed as supplemental provenance, while each series receives a generated CSV
source so replay remains deterministic.

The Excel workbook has four visible sheets:

| Sheet | Columns | Purpose |
|---|---|---|
| `Instructions` | explanatory text | Describes required fields, units, grouping, and replacement of synthetic rows. |
| `Material` | `field`, `value` | Stores manufacturer, material name, grade, source URL/page, capture timestamp, and source description. |
| `B-H Curves` | `series_id`, `temperature_c`, `dc_bias_a_per_m`, `h_unit`, `b_unit`, `h`, `b` | Stores H on the x-axis and B on the y-axis. |
| `Loss Curves` | `series_id`, `frequency_hz`, `temperature_c`, `dc_bias_a_per_m`, `b_unit`, `loss_unit`, `b`, `loss` | Stores B on the x-axis and loss density on the y-axis. |

Workbook dropdowns offer these retained datasheet units:

| Quantity | Choices | Canonical unit after import |
|---|---|---|
| H | `A/m`, `kA/m`, `Oe` | `A/m` |
| B | `T`, `mT`, `G`, `kG` | `T` |
| Loss density | `W/m3`, `kW/m3`, `mW/cm3` | `W/m3` |

The flat CSV uses these exact columns:

| Metadata | Series and point data |
|---|---|
| `manufacturer`, `material_name`, `grade`, `source_url`, `source_page`, `captured_at`, `source_description` | `series_id`, `curve_kind`, `frequency_hz`, `temperature_c`, `dc_bias_a_per_m`, `x_unit`, `y_unit`, `x`, `y` |

For CSV B-H rows, `curve_kind` is `bh-curve`, `x` is H, and `y` is B. For
loss rows, `curve_kind` is `loss-table`, `x` is B, and `y` is loss density.
Material metadata repeats on every CSV row. Rows sharing a `series_id` must
repeat identical curve kind, conditions, and units. Loss frequency is required
and positive; optional temperature and DC bias cells may be blank.

Spreadsheet dropdowns are guidance only. Python validation remains
authoritative for supported units, finite values, required metadata, consistent
series, and physical checks. Formulas are rejected in material metadata and
curve cells; enter typed values instead. A workbook must retain the four named
visible sheets and their exact column headers.

Use the packaged-resource and upload APIs without depending on repository
paths:

```python
from pathlib import Path

from inductor_designer.adapters.materials import (
    import_material_file,
    material_import_template,
)

download = material_import_template("xlsx")  # use "csv" for the flat template
Path(download.filename).write_bytes(download.data)

uploaded_bytes = Path(download.filename).read_bytes()
imported = import_material_file(download.filename, uploaded_bytes)
print(imported.ref, tuple(series.series_id for series in imported.series))
```

Use the returned `sources` to build the record with `new_draft_record`, and pass
the returned `source_files` to the overlay repository save, as shown by
`tests/integration/test_material_table_upload.py`. Import never reviews or
approves a record automatically.

## Download and edit the selected material

Any record with B-H or loss curves can be exported into a populated copy of
the verified Excel template. Canonical points are converted back to each
series' retained units, all conditions are included, and the source description
names the selected base revision.

```python
from pathlib import Path

from inductor_designer.adapters.materials import (
    export_material_record_xlsx,
    import_material_file_as_draft,
)

download = export_material_record_xlsx(selected_record)
Path(download.filename).write_bytes(download.data)

# Edit the saved workbook in Excel, then import its updated bytes.
edited = import_material_file_as_draft(
    download.filename,
    Path(download.filename).read_bytes(),
    created_at="2026-07-18T13:00:00+00:00",
    notes=f"Edited from base revision {selected_record.revision_id}",
)
assert edited.record.status.value == "draft"
```

Reimport always creates a new draft revision and recomputes any supported loss
fit from the edited tables. It does not overwrite, review, or approve the base
revision. Scalar-only records have no editable curves and cannot be exported
to this workbook.

The same operations are available in Material Studio. Use `CSV template` or
`XLSX template` to save an example, or select any stored revision and use
`Export selected revision` to create a populated workbook. Edit that workbook
in Excel or a compatible workbook editor, then use `Reimport edited workbook`.
The import always opens a new draft; it never overwrites the selected base
revision.

## Material Studio workflow

Open the `Materials` step in Guided Studio and follow this sequence:

1. Select a material identity. The library shows every stored `draft`,
   `reviewed`, and `approved` revision, including timestamps, lifecycle actors,
   validation counts, and source traceability (URL, page, capture time,
   description, and SHA-256). `Suggested latest approved` is advisory only: it
   neither selects a revision nor changes the project.
2. Start from one of three sources:
   - download the CSV or XLSX template, fill it, and import it;
   - select any revision, export its populated XLSX workbook, edit it in Excel
     or a compatible editor, and reimport it as a new draft; or
   - import PNG/JPEG or one selected page from a PDF for manual digitization.
3. For an image or PDF, set the crop, place the two X-axis and two Y-axis
   calibration anchors, enter each anchor value, and choose linear or logarithmic
   scales. Set retained units from the supported H, B, and loss-density families.
   The original image/PDF bytes, selected PDF page, crop, axes, and pixel points
   remain in provenance; resizing or scaling the view does not change stored
   original-pixel coordinates.
4. Add, move, or delete manual points. Canonical point values may also be edited
   directly. Direct numeric editing intentionally converts that curve into a
   table edit while retaining the original image/PDF as supplemental provenance.
5. Set the series ID and kind plus applicable frequency, temperature, and DC-bias
   conditions. Blank optional conditions remain unspecified; physical zero is
   stored as zero. Malformed values remain visible and block applying or saving
   until corrected.
6. Inspect source points, current points, fit coefficients/residuals, and grouped
   validation issues together. Errors block review and approval; warnings remain
   visible but do not bypass the existing lifecycle rules.
7. `Save Draft`, enter a reviewer and choose `Review`, then enter an approver and
   choose `Approve`. Editing a reviewed or approved revision first creates a
   distinct draft, preserving the approved base unchanged.
8. Choose an approved revision for the project. If it contains multiple B-H
   series, explicitly choose the displayed series ID and its temperature/DC-bias
   conditions before `Use in Project`; no series is chosen by timestamp or order.

Leaving dirty Material Studio state, selecting another identity, or selecting
another revision opens `Save`, `Discard`, and `Cancel` choices. A failed save
keeps the pending navigation and unsaved state; `Cancel` stays on the current
draft, and `Discard` restores the last stored state before navigating.

## Worked CSV import in datasheet units

The importer expects a two-column CSV headed `x,y`. Units are passed separately.
Use the exact spelling `mW/cm3` in the API; “mW/cm³” below is only display
notation. Oersted is valid for the H axis of a B-H series, while mW/cm³ is valid
for the loss-density axis of a loss series. They therefore belong in separate
series, not as the two axes of one curve.

This example imports a B-H table in Oe/kG and two 100/200 kHz loss tables in
kG/mW/cm³. Two frequencies and at least two distinct flux densities allow the
draft builder to fit Steinmetz coefficients automatically.

```python
from pathlib import Path

from inductor_designer.adapters.materials import FileOverlayMaterialRepository
from inductor_designer.application.services.material_import import (
    approve_material,
    import_curve_csv,
    new_draft_record,
    review_material,
)
from inductor_designer.materials.identity import MaterialRef
from inductor_designer.materials.records import (
    CurveConditions,
    SeriesKind,
    SourceKind,
    SourceProvenance,
)
from inductor_designer.materials.serde import sha256_hex

source_text = {
    "bh.csv": "x,y\n0,0\n1,0.8\n2,1.25\n",
    "loss-100khz.csv": "x,y\n0.1,10\n0.2,45\n0.3,110\n",
    "loss-200khz.csv": "x,y\n0.1,25\n0.2,112\n0.3,274\n",
}
source_bytes = {name: text.encode("utf-8") for name, text in source_text.items()}

def provenance(filename: str, description: str) -> SourceProvenance:
    return SourceProvenance(
        kind=SourceKind.CSV,
        filename=filename,
        sha256=sha256_hex(source_bytes[filename]),
        url="https://manufacturer.example/material-datasheet.pdf",
        page=4,
        captured_at="2026-07-18T12:00:00Z",
        description=description,
    )

bh_source = provenance("bh.csv", "B-H table transcribed from the source")
loss_100_source = provenance("loss-100khz.csv", "100 kHz core-loss curve")
loss_200_source = provenance("loss-200khz.csv", "200 kHz core-loss curve")

bh = import_curve_csv(
    source_text["bh.csv"],
    series_id="bh-room-temperature",
    kind=SeriesKind.BH_CURVE,
    x_unit="Oe",
    y_unit="kG",
    conditions=CurveConditions(None, 25.0, 0.0),
    source=bh_source,
)
loss_100 = import_curve_csv(
    source_text["loss-100khz.csv"],
    series_id="loss-100khz",
    kind=SeriesKind.LOSS_TABLE,
    x_unit="kG",
    y_unit="mW/cm3",
    conditions=CurveConditions(100_000.0, 25.0, 0.0),
    source=loss_100_source,
)
loss_200 = import_curve_csv(
    source_text["loss-200khz.csv"],
    series_id="loss-200khz",
    kind=SeriesKind.LOSS_TABLE,
    x_unit="kG",
    y_unit="mW/cm3",
    conditions=CurveConditions(200_000.0, 25.0, 0.0),
    source=loss_200_source,
)

draft = new_draft_record(
    MaterialRef("Example Manufacturer", "Example Material", "60"),
    series=(bh, loss_100, loss_200),
    sources=(bh_source, loss_100_source, loss_200_source),
    created_at="2026-07-18T12:00:00Z",
    notes="Demonstration data only; not an approved datasheet transcription.",
)
reviewed = review_material(draft, "Reviewer Name")
approved = approve_material(reviewed, "Approver Name")

repository = FileOverlayMaterialRepository(Path("materials-overlay"))
repository.save(approved, source_bytes)
print(approved.revision_id)
```

The importer converts H to A/m, B to tesla, and loss density to W/m³, sorts by
the canonical x value, and rounds to nine decimal places. For reference,
`1 Oe = 79.57747154594767 A/m` and `1 mW/cm3 = 1000 W/m3`.

The numbers and URL above are deliberately synthetic. Do not approve them as a
real material record.

## Review and approval rules

The lifecycle is `draft` → `reviewed` → `approved`; transitions cannot be
skipped or reversed. Review and approval run material validation first and are
blocked by errors. Checks cover unit families, physical ranges, B-H origin and
strict B monotonicity, decreasing or duplicate H values, positive loss density,
required loss frequency, relative-permeability range, nonempty records, and the
presence of loss-series data when a Steinmetz fit is attached. A B-H slope below
vacuum permeability is retained as a warning.

Lifecycle validation does not recompute fitted coefficients or check their
residuals against the loss points. When a stored record has a Steinmetz fit, the
reproduction flow independently rebuilds its loss samples, recomputes the fit,
and compares the complete stored and recomputed fit values.

Approval records both reviewer and approver identities. It does not replace
engineering review of the source, curve conditions, units, transcription,
fit residuals, source licensing, or redistribution rights. OCR never approves
data automatically.

## Reproduce a stored revision

Run the replay CLI from the repository root with the exact material identity
and revision printed by the import flow:

```console
python -m tools.reproduce_material \
  --overlay-root materials-overlay \
  --manufacturer "Example Manufacturer" \
  --name "Example Material" \
  --grade "60" \
  --revision <12-hex-revision>
```

`MATCH` and exit code 0 mean that source hashes, replayed CSV or image
extraction points, a recomputed Steinmetz fit, and the content-derived revision
identifier all match. Missing or changed artifacts print mismatches and exit 1.
This is reproducibility evidence, not proof that the original transcription or
physical interpretation is correct.

## Project pinning and solver export

Project schema v4 stores material selections as
`{ref, revisionId, bhSeriesId, snapshot}`. The snapshot is the complete record
used for generation. Schema v3 projects migrate deterministically by adding
`bhSeriesId: null`; migration never guesses a series. A project must contain
exactly one matching selection for the selected core when it uses an approved
record:

- zero matches preserves the older powder-grade linear fallback;
- one match exports that explicitly pinned snapshot; and
- multiple matches block export as ambiguous.

Export never queries `latest_approved` and never silently changes a saved
project. The UI lists every revision, may suggest the most recent **approved**
revision, and requires the user to select and persist one exact revision.

An approved record bypasses the powder-only fallback and therefore unblocks
ferrite core generation when it supplies scalar permeability or a usable B-H
curve. Maxwell 2D and 3D receive nonlinear permeability as `(B, H)` pairs and,
when present, the fitted Steinmetz parameters through
`set_power_ferrite_coreloss(cm=k, x=alpha, y=beta)`. A falsy PyAEDT result
blocks the material stage. The manifest records the pinned revision, selected
B-H series ID, B-H point count, and fit coefficients.

FEMM receives the same `(B, H)` table. The adapter deliberately calls the
singular pyFEMM API `mi_addbhpoint(name, b, h)` once per point; there is no bulk
`mi_addbhpoints` call in the implementation. This API shape is covered by fake
adapter tests but still requires verification in a real FEMM session.

For zero B-H series, the scalar-permeability path remains available. One B-H
series can be selected directly. More than one B-H series requires an explicit
`bhSeriesId`; project use and export block when it is absent. Maxwell 2D,
Maxwell 3D, and FEMM consume only that pinned series from the stored snapshot.

## Milestone 5b handoff and pending acceptance

The spreadsheet and manual-digitization workflow is the required M5b scope.
OCR proposals, automatic curve tracing, the optional attributed GPL
`materialdatabase` importer, material MCP tools, and explicit-formula records
are deferred to optional M5c. M5c has no plan or scaffold and will be considered
only if Windows user acceptance shows that the M5b workflow is insufficient.

M5b has automated evidence for library/revision listing, immutable draft
editing, image/PDF replay, schema v3-to-v4 migration, explicit B-H selection,
recording-fake Maxwell/FEMM manifests, controller behavior, and offscreen QML
flows. This is not native Windows, Excel/FileDialog, high-DPI, or live-solver
evidence. The final whole-change review and fresh complete gates pass. Before
M5b can be marked implementation-complete, record native Windows manual
acceptance for keyboard/focus, scaling, PNG/JPEG/PDF pages, file dialogs,
template download, workbook edit/reimport, revision visibility, lifecycle, and
explicit B-H selection.

Before formally accepting M5a or M5b, Fabio must:

1. Import a legally usable real Magnetics Kool Mu 60 core-loss and B-H source,
   review it, approve it under the reviewer's real name, and optionally commit
   the overlay revision.
2. Pin that exact approved revision and B-H series in a schema v4 project,
   generate Maxwell 3D and FEMM, open both, and check the nonlinear B-H data and
   ferrite core-loss coefficients in AEDT plus every B-H point in FEMM.
3. Run the reproduction CLI for that revision and obtain `MATCH`.
4. Record the live evidence and explicitly accept Milestone 5a in the roadmap.
