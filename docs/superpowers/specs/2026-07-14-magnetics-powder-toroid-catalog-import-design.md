# Magnetics Powder Toroid Catalog Import Design

## Goal

Populate the canonical powder-core catalog with every toroidal part-number row that has complete physical and magnetic data in the 2025 Magnetics Powder Cores Catalog, while preserving the repository's review workflow and existing reviewed records.

## Scope

- Source: 2025 Magnetics Powder Cores Catalog.
- Import surface: printed catalog pages 154 through 196, the detailed Toroid Data section.
- Included material columns: Kool Mu, Kool Mu MAX, Kool Mu Hf, Kool Mu Ultra, XFlux, XFlux Ultra, Edge, High Flux, and MPP.
- Excluded: E, Block, U, EQ, EER, LP, ferrite, and any non-toroid geometry.
- No domain or JSON-schema expansion is required because all imported records use `family: powder-toroid`.

## Source-of-truth policy

The detailed Toroid Data tables are authoritative because they provide the complete tuple required by `core.v1.schema.json`: part number, permeability, AL, dimensions, effective area, path length, and effective volume.

The Core Locator index is used as a cross-check, not as the primary source. The catalog contains these internal inconsistencies:

- Index-only entries without corresponding data-table rows: `0055340A2`, `0055341A2`. They are not imported because AL values are absent and must not be inferred.
- Data-table entries omitted from the index: `0058443A2`, `0058876A2`, `0059534A2`, `0078937A7`. They are imported because complete data rows exist.
- The index prints `078050A7`; the data table and material-code convention identify the part as `0078050A7`.
- PDF text extraction renders graded part `C058031A2` as `CO58031A2`; the catalog image and part-number convention resolve the second character as zero.

The resulting authoritative data-table set contains 1,923 unique toroidal records across 43 pages.

## Record mapping

Each table row is expanded across its non-empty material columns. The row permeability becomes `material.grade`; the row AL becomes `alValueNh`.

Dimensions map exactly as follows:

```yaml
outerDiameter:
  nominalM: <Before Finish OD in meters>
  minM: null
  maxM: <After Finish OD limit in meters>
innerDiameter:
  nominalM: <Before Finish ID in meters>
  minM: <After Finish ID limit in meters>
  maxM: null
height:
  nominalM: <Before Finish HT in meters>
  minM: null
  maxM: <After Finish HT limit in meters>
```

The opposite tolerance bounds intentionally remain `null`; they do not describe a meaningful coating limit.

Physical and magnetic values are converted from catalog units:

- `Cross Section (Ae)`: mm2 to m2
- `Path Length (Le)`: mm to m
- `Effective Volume (Ve)`: mm3 to m3
- `AL`: nH/T2, stored unchanged numerically

## Coating mapping

New records use the catalog's standard epoxy finish color by material:

- Kool Mu, Kool Mu MAX, Kool Mu Hf, Kool Mu Ultra: `black epoxy`
- XFlux, XFlux Ultra: `brown epoxy`
- Edge: `green epoxy`
- High Flux: `khaki epoxy`
- MPP: `gray epoxy`

The ten records already marked `reviewed` remain reviewed by Fabio Posser and retain their currently committed values, including coating text.

## Review status

- Existing reviewed records remain `reviewStatus: reviewed` with `reviewedBy: Fabio Posser`.
- Every newly imported record is `reviewStatus: draft` with `reviewedBy: null`.
- No generated record is promoted to reviewed automatically.

## Validation

The implementation must prove:

1. YAML parses and every record validates against `schemas/catalog/core.v1.schema.json`.
2. Exactly 1,923 unique powder-toroid part numbers are present in `magnetics-powder.yaml`.
3. The data covers all nine material families and pages 154 through 196.
4. Every record follows the asymmetric dimension-bound rule.
5. The ten pre-existing reviewed records retain reviewed status and reviewer.
6. The catalog compiles into SQLite without duplicate primary keys.
7. Representative first, middle, last, graded, and material-family records can be retrieved through `SqliteCatalogRepository`.

## Files

- Replace: `catalog/cores/magnetics-powder.yaml`
- Modify: `tests/unit/adapters/catalog/test_sqlite_repository.py`
- Add this design document and the corresponding implementation plan.

No extraction utility or copy of the supplier PDF is committed. The YAML remains the human review surface; SQLite remains a generated artifact.
