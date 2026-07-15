# Fair-Rite Ferrite Toroid Catalog Import Design

## Goal

Add Fair-Rite ferrite toroids to the existing catalog in the same canonical YAML format used by the Magnetics ferrite records, while preserving source traceability and refusing to invent nominal dimensions.

## Scope

- Source category: `https://fair-rite.com/product-category/inductive-components/toroids/`
- Import only toroidal ferrite cores.
- Create `catalog/cores/fair-rite-ferrite.yaml`.
- Keep all newly imported records as `reviewStatus: draft` and `reviewedBy: null`.
- Do not modify existing Magnetics ferrite records.
- Do not add non-toroidal Fair-Rite products.

## Record mapping

Each imported record must satisfy `schemas/catalog/core.v1.schema.json` and use:

- `manufacturer: Fair-Rite`
- `family: ferrite-toroid`
- `material.manufacturer: Fair-Rite`
- `material.name`: Fair-Rite material designation
- `material.grade`: numeric material code as text
- `catalogRevision`: a stable Fair-Rite web-catalog revision identifier
- `sourceUrl`: the exact Fair-Rite product page or datasheet used
- `sourcePage: 1` for web product pages unless a PDF page is the authoritative source

Required magnetic fields are `effectiveAreaM2`, `pathLengthM`, `volumeM3`, and `alValueNh`. A product is importable only when all required schema fields can be resolved from Fair-Rite sources without inference beyond unit conversion and the coated/uncoated pairing rule below.

## Dimension rules

### Nominal dimensions with symmetric tolerance

For dimensions published as `nominal ± tolerance`:

- `nominalM = nominal`
- `minM = nominal - tolerance`
- `maxM = nominal + tolerance`

The same rule applies to outer diameter, inner diameter, and height.

### Explicit asymmetric limits

When Fair-Rite publishes a nominal value plus explicit minimum or maximum limits, preserve the published nominal and limits directly.

### Coated parts with limit-only dimensions

Some coated parts publish only:

- outer diameter maximum;
- inner diameter minimum;
- height maximum.

For these records, use the nominal dimensions of the matching uncoated Fair-Rite core only when the match is unambiguous. Preserve the coated limits as:

```yaml
outerDiameter:
  nominalM: <matching uncoated nominal OD>
  minM: null
  maxM: <coated OD maximum>
innerDiameter:
  nominalM: <matching uncoated nominal ID>
  minM: <coated ID minimum>
  maxM: null
height:
  nominalM: <matching uncoated nominal height>
  minM: null
  maxM: <coated height maximum>
```

A coated/uncoated match is unambiguous only when material, geometry, effective magnetic parameters, and Fair-Rite product relationship agree. Matching by similar dimensions alone is not sufficient.

## Unresolved review list

Any product that cannot be imported without inventing data must be excluded from `fair-rite-ferrite.yaml` and listed in:

`docs/catalog/fair-rite-ferrite-unresolved.md`

Each unresolved entry must contain:

- Fair-Rite part number;
- material code;
- product URL;
- coating or finish, when published;
- available dimensions and limits;
- missing or ambiguous required fields;
- attempted coated/uncoated match, when applicable;
- exact reason the record was not imported;
- recommended manual review action.

The list must distinguish at least these reasons:

1. no unambiguous nominal-dimension counterpart for a limit-only coated core;
2. missing `Ae`, `le`, `Ve`, or `AL`;
3. conflicting values between Fair-Rite sources;
4. duplicate part numbers with non-identical data;
5. inaccessible or malformed product page;
6. product shown in the toroid category but not actually a ferrite toroid.

The unresolved list is a review artifact and is not consumed by `tools/build_catalog.py`.

## Local-first validation

No GitHub Actions workflow may be used to debug the Fair-Rite parser.

Before any generated Fair-Rite catalog file is committed, local validation must include:

- parser unit tests using saved minimal HTML fixtures or deterministic extracted examples;
- tests for `nominal ± tolerance` conversion;
- tests for explicit min/max dimensions;
- tests for coated/uncoated pairing;
- tests that ambiguous coated parts are excluded and reported;
- tests for duplicate identical and duplicate conflicting records;
- JSON Schema validation of every generated record;
- SQLite catalog build with `tools/build_catalog.py`;
- duplicate part-number check across all catalog YAML files;
- `compileall` and the repository's existing quality/test commands.

Only after these checks pass locally may the branch be updated with generated Fair-Rite data. GitHub Actions remains a final verification mechanism, not a development or debugging environment.

## Data integrity policy

- Never infer a nominal dimension from a published maximum or minimum alone.
- Never infer magnetic parameters from geometry formulas when Fair-Rite does not publish them.
- Never silently choose between conflicting sources.
- Preserve SI units in the YAML.
- Keep every new record in `draft` status until human review.
- Record all exclusions in the unresolved review list.

## PR integration

The Fair-Rite import will be added to the existing draft PR and branch:

- branch: `agent/import-all-magnetics-powder-toroids`
- PR: `#2`

The PR description must be updated with the Fair-Rite record count, imported material families, unresolved record count, local validation evidence, and a link to the unresolved review file.