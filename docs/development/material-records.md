# Material Records Pipeline

The material pipeline stores spreadsheet uploads as traceable, deterministic
`imported` revisions and exports the selected immutable snapshot to Maxwell or
FEMM. Material Studio is spreadsheet-only: it imports CSV/XLSX files, previews
the stored curves, replaces or deletes revisions, and explicitly pins a
revision and B-H series to the active project. Legacy approved records remain
readable and usable.

## Overlay layout and integrity

The default local overlay is `materials-overlay/`. It is a filesystem-backed
repository, not a database. It is intentionally available to Git: users may
commit imported records and their source bytes for others only when the source
material may legally be redistributed. The application never adds the original
workbook to Git automatically; it copies the uploaded bytes into the selected
revision's `sources/` directory.

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
point agreement before installation. Imported revisions are persisted
immediately and are immutable in Material Studio. Replacement writes the new
revision first, then removes the previous unpinned imported revision. A
revision pinned by the active project is retained. Legacy draft/reviewed and
approved records remain readable for compatibility; normal loads recheck source
hashes and CSV/JSON point agreement.

## Material table templates and uploads

Two synthetic, self-describing templates are packaged with the application:

- [material-import-template.xlsx](../../src/inductor_designer/resources/material_templates/material-import-template.xlsx)
- [material-import-template.csv](../../src/inductor_designer/resources/material_templates/material-import-template.csv)

Replace the synthetic example values before upload. The workbook and CSV are
equivalent input formats: both produce the same canonical point series when
they contain the same material data. The original upload is retained and
hashed as supplemental provenance, while each series receives a generated CSV
source so replay remains deterministic. A loss series with only positive B
values receives a generated `(0,0)` origin before persistence; the workbook
source remains byte-for-byte unchanged and the generated source description
records the normalization.

The Excel workbook has four visible sheets:

| Sheet | Columns | Purpose |
|---|---|---|
| `Instructions` | explanatory text | Describes required fields, units, grouping, and replacement of synthetic rows. |
| `Material` | `field`, `value` | Stores manufacturer, material name, grade, source URL/page, capture timestamp, and source description. |
| `B-H Curves` | `series_id`, `temperature_c`, `dc_bias_a_per_m`, `h`, `h_unit`, `b`, `b_unit` | Stores H on the x-axis and B on the y-axis, with each value beside its unit. |
| `Loss Curves` | `series_id`, `frequency_hz`, `temperature_c`, `dc_bias_a_per_m`, `b`, `b_unit`, `loss`, `loss_unit` | Stores B on the x-axis and loss density on the y-axis, with each value beside its unit. |

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

`grade` is the manufacturer/catalog designation that completes material
identity; it is not a curve coordinate. `dc_bias_a_per_m` is optional measurement
condition metadata. Leave it blank when the source does not report DC bias; use
`0` only when the source explicitly reports zero bias. It is preserved with the
series and used to distinguish conditions, but the current material-to-solver
path does not use it as an independent calculation input.

XLSX curve cells remain typed numeric values. Excel accepts and displays decimal
comma or decimal point according to the user's regional settings. `captured_at`
is required provenance text, but it does not require a special user format:
ordinary text is preserved, and Excel-native date or datetime cells are
normalized to ISO text during import. Uploading a downloaded template creates an
immediately persisted `imported` revision, canonicalizes its points, and
exposes the selected series to Material Studio's curve plot. No review or
approval action is required.

Use the packaged-resource and upload APIs without depending on repository
paths:

```python
from pathlib import Path

from inductor_designer.adapters.materials import (
    FileOverlayMaterialRepository,
    import_material_file_as_imported,
    material_import_template,
)

download = material_import_template("xlsx")  # use "csv" for the flat template
Path(download.filename).write_bytes(download.data)

uploaded_bytes = Path(download.filename).read_bytes()
imported = import_material_file_as_imported(
    download.filename,
    uploaded_bytes,
    created_at="2026-07-23T12:00:00+00:00",
)
FileOverlayMaterialRepository(Path("materials-overlay")).save(
    imported.record,
    dict(imported.source_files),
)
print(imported.record.ref, imported.record.status.value)
```

The legacy `import_material_file_as_draft` API remains available for migration
and tests that exercise the old lifecycle. Material Studio uses the imported
path above and passes the returned `source_files` to the overlay repository.

## Workbook export API

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

Reimport through this compatibility API creates a new draft revision and
recomputes any supported loss fit from the edited tables. It does not overwrite
the base revision. Material Studio exposes the same generated workbook through
`Download selected material XLSX`; after editing it, use `Replace selected
material` to import and store the new immutable revision immediately.
Scalar-only records have no editable curves and cannot be exported to this
workbook.

Material Studio accepts only CSV and XLSX material uploads. The former
image/PDF digitization path was removed instead of being retained as a
compatibility workflow. Select a material to load its newest revision
automatically, then select a series in the Materials page to inspect the
canonical curve plot produced from the imported table.

## Material Studio workflow

The spreadsheet import and local material-library workflow was accepted for the
MVP on 2026-07-23. This acceptance covers import, persistence, visualization,
XLSX download, replacement, and deletion; live solver consumption remains a
separate acceptance gate.

Open the `Materials` step in Guided Studio and follow this sequence:

1. Download the CSV or XLSX template, fill it, and choose `Import CSV or XLSX`.
   A valid file is stored immediately as an `imported` immutable revision.
2. Select a material identity and revision to inspect its read-only status,
   provenance, validation issues, fit information, and series metadata.
3. Select a B-H or loss series. The preview shows numeric X/Y tick values,
   units, conditions, source filename, and visible markers. `Log X` and `Log Y`
   are independent; non-positive points are omitted only from logarithmic
   rendering and a notice explains this. Stored points are never changed.
4. To change a material, choose `Replace selected material` and import a new
   file with the same manufacturer, material name, and grade. The replacement
   is saved first. The prior imported revision is removed unless the active
   project pins it.
5. To remove a material, choose `Delete selected material` and confirm. The
   action is blocked if the active project pins any revision and never deletes
   the original workbook outside the application overlay.
6. When a project is loaded, choose `Select for simulation`. A revision with
   multiple B-H series requires an explicit B-H series selection. Imported and
   legacy approved revisions are accepted by simulation; project selection
   remains explicit so the project stores the exact immutable snapshot.

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

## Validation and legacy lifecycle rules

Imported records are validated before persistence and are immediately usable by
simulation. Checks cover unit families, physical ranges, B-H origin and strict
B monotonicity, decreasing or duplicate H values, positive loss density,
loss-origin rules, increasing loss B, required loss frequency,
relative-permeability range, nonempty records, and the presence of loss-series
data when a Steinmetz fit is attached. A B-H slope below vacuum permeability is
retained as a warning. The legacy `draft` → `reviewed` → `approved` services
remain for existing records and compatibility APIs; they are not exposed in
Material Studio.

Lifecycle validation does not recompute fitted coefficients or check their
residuals against the loss points. When a stored record has a Steinmetz fit, the
reproduction flow independently rebuilds its loss samples, recomputes the fit,
and compares the complete stored and recomputed fit values.

The inserted loss origin is excluded from the Steinmetz fit because the fit
uses logarithms. Source licensing and redistribution rights still require
engineering review before an overlay is committed for other users.

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

`MATCH` and exit code 0 mean that source hashes, replayed CSV points, a
recomputed Steinmetz fit, and the content-derived revision
identifier all match. Missing or changed artifacts print mismatches and exit 1.
This is reproducibility evidence, not proof that the original transcription or
physical interpretation is correct.

## Project pinning and solver export

Project schema v4 stores material selections as
`{ref, revisionId, bhSeriesId, snapshot}`. The snapshot is the complete record
used for generation. Schema v3 projects migrate deterministically by adding
`bhSeriesId: null`; migration never guesses a series. A project must contain
exactly one matching selection for the selected core when it uses an imported
or approved
record:

- zero matches preserves the older powder-grade linear fallback;
- one match exports that explicitly pinned snapshot; and
- multiple matches block export as ambiguous.

Export never queries `latest_approved` and never silently changes a saved
project. The UI lists every revision and requires the user to select and persist
one exact imported or approved revision.

An imported or approved record bypasses the powder-only fallback and therefore unblocks
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

## Material Studio acceptance notes

The spreadsheet-only workflow is the required M5b scope. The application has no
OCR, image tracing, or PDF digitization path. Any future non-spreadsheet
importer, material MCP tool, or explicit-formula record requires a separate
approved specification and plan.

Automated evidence covers imported persistence, replacement/deletion guards,
CSV/XLSX replay, loss-origin normalization, explicit B-H selection,
recording-fake Maxwell/FEMM manifests, controller behavior, numeric linear/log
plot labels, and offscreen QML flows. This is not native Windows,
Excel/FileDialog, high-DPI, or live-solver evidence.

Before formally accepting M5a or M5b, Fabio must:

1. Import a legally usable real Magnetics Kool Mu 60 core-loss and B-H source
   and optionally commit the imported overlay revision.
2. Pin that exact approved revision and B-H series in a schema v4 project,
   generate Maxwell 3D and FEMM, open both, and check the nonlinear B-H data and
   ferrite core-loss coefficients in AEDT plus every B-H point in FEMM.
3. Run the reproduction CLI for that revision and obtain `MATCH`.
4. Record the live evidence and explicitly accept Milestone 5 in the roadmap.
