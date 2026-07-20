# ADR 0002: Spreadsheet-Only Material Ingestion

- Status: Accepted
- Date: 2026-07-20

## Context

The first Material Studio implementation included manual PNG/JPEG/PDF curve
digitization with crop and axis calibration. No user materials have been
imported yet, and the intended review data is already represented by the
validated CSV/XLSX templates and the local material repository.

Image-based extraction adds UI state, pixel-coordinate provenance, rendering
dependencies, and editing paths that are not needed for the initial material
workflow. The user also explicitly does not want OCR or curves created from
images.

## Decision

Material Studio will use CSV and XLSX as its only material ingestion formats.
Remove the image/PDF source renderer, QML source view, crop/calibration editor,
image-backed draft/series creation functions, and extraction metadata from the
material record model. Keep the curve plot based on canonical table points and
let the user select a material, revision, and series before inspecting it.

## Consequences

- The Material Studio workflow is smaller and easier to validate: file import,
  table editing, lifecycle, explicit project selection, and plot inspection.
- The materials model no longer depends on image/PDF extraction semantics.
- The QtPdf/image rendering dependency is no longer needed for Material Studio.
- Existing test fixtures for manual image extraction are removed because the
  repository has no user-imported material data to migrate.
- Future OCR or image tracing would require a new, separately approved ADR and
  specification rather than reappearing as an implicit fallback.
