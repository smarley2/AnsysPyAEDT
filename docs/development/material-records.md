# Material Records Pipeline

Milestone 5a provides a traceable, deterministic path from source bytes to an
approved magnetic-material revision and solver export. The implementation and
automated exit-criterion proof are complete. Acceptance remains pending until a
reviewer imports a real datasheet and checks the result in AEDT and FEMM; no live
material handoff has been performed in this repository.

## Overlay layout and integrity

The default local overlay is `materials-overlay/`. It is intentionally not
ignored: a reviewer may commit an approved record when the source material may
legally be redistributed.

```text
materials-overlay/
  <manufacturer>/
    <material-name>/
      <grade>/
        <revision-id>/
          record.json
          points-<series-id>.csv
          sources/
            <source-file>
```

Path components are sanitized for solver and filesystem safety. `record.json`
is deterministic JSON and embeds the canonical points; each `points-*.csv` is
the corresponding reviewable canonical series. The repository verifies all of
the following on save or load:

- source filenames match the provenance entries exactly;
- each source byte stream matches its recorded SHA-256 hash;
- CSV and JSON points agree exactly;
- points already satisfy the nine-decimal canonical rounding contract; and
- an approved revision is never overwritten.

Draft and reviewed records with the same revision identifier may be replaced
atomically. Approval makes the stored revision immutable.

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
strict monotonicity, duplicate H values, required loss frequency, permeability
range, and consistency between loss data and a fitted model. Applicable slope
findings are retained as warnings.

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

Project schema v3 stores material selections as `{ref, revisionId, snapshot}`.
The snapshot is the complete record used for generation. A project must contain
exactly one matching selection for the selected core when it uses an approved
record:

- zero matches preserves the older powder-grade linear fallback;
- one match exports that explicitly pinned snapshot; and
- multiple matches block export as ambiguous.

Export never queries `latest_approved` and never silently changes a saved
project. In Milestone 5b the UI must list every revision, may suggest the most
recent **approved** revision, and must require the user to select and persist
one explicit revision.

An approved record bypasses the powder-only fallback and therefore unblocks
ferrite core generation when it supplies scalar permeability or a usable B-H
curve. Maxwell 2D and 3D receive nonlinear permeability as `(B, H)` pairs and,
when present, the fitted Steinmetz parameters through
`set_power_ferrite_coreloss(cm=k, x=alpha, y=beta)`. A falsy PyAEDT result
blocks the material stage. The manifest records the pinned revision, B-H point
count, and fit coefficients.

FEMM receives the same `(B, H)` table. The adapter deliberately calls the
singular pyFEMM API `mi_addbhpoint(name, b, h)` once per point; there is no bulk
`mi_addbhpoints` call in the implementation. This API shape is covered by fake
adapter tests but still requires verification in a real FEMM session.

One approved B-H series is exportable. More than one B-H series is ambiguous
because the record does not yet select temperature, frequency, or bias
conditions; export blocks until Milestone 5b provides an explicit condition
selection.

## Milestone 5b scope and live handoff

Milestone 5b owns the Material Studio screens for image load, crop, axis
calibration, point extraction and editing, residual comparison, review,
approval, revision listing, and explicit condition/revision selection. It also
owns explicit-formula records, the planned OCR proposal flow, optional
attributed GPL importer, and MCP material inspection/approval tools. None of
those interfaces is implemented by Milestone 5a.

Before accepting Milestone 5a, Fabio must:

1. Import a legally usable real Magnetics Kool Mu 60 core-loss and B-H source,
   review it, approve it under the reviewer's real name, and optionally commit
   the overlay revision.
2. Pin that exact approved revision in a schema v3 project, generate Maxwell 3D
   and FEMM, open both, and check the nonlinear B-H data and ferrite core-loss
   coefficients in AEDT plus every B-H point in FEMM.
3. Run the reproduction CLI for that revision and obtain `MATCH`.
4. Record the live evidence and explicitly accept Milestone 5a in the roadmap.
