from __future__ import annotations

from dataclasses import dataclass

from inductor_designer.application.services.material_import import (
    MaterialImportError,
    import_curve_csv,
)
from inductor_designer.geometry.naming import sanitize_identifier
from inductor_designer.materials.identity import MaterialRef
from inductor_designer.materials.records import (
    CurveConditions,
    PointSeries,
    SeriesKind,
    SourceKind,
    SourceProvenance,
)
from inductor_designer.materials.serde import sha256_hex


@dataclass(frozen=True, slots=True)
class MaterialTableMetadata:
    ref: MaterialRef
    source_url: str
    source_page: int | None
    captured_at: str
    source_description: str


@dataclass(frozen=True, slots=True)
class MaterialTableRow:
    series_id: str
    kind: SeriesKind
    frequency_hz: float | None
    temperature_c: float | None
    dc_bias_a_per_m: float | None
    x_unit: str
    y_unit: str
    x: float
    y: float


@dataclass(frozen=True, slots=True)
class ImportedMaterialTable:
    ref: MaterialRef
    series: tuple[PointSeries, ...]
    sources: tuple[SourceProvenance, ...]
    source_files: tuple[tuple[str, bytes], ...]


def _source(
    metadata: MaterialTableMetadata,
    kind: SourceKind,
    filename: str,
    data: bytes,
) -> SourceProvenance:
    return SourceProvenance(
        kind=kind,
        filename=filename,
        sha256=sha256_hex(data),
        url=metadata.source_url,
        page=metadata.source_page,
        captured_at=metadata.captured_at,
        description=metadata.source_description,
    )


def _source_filename_key(filename: str) -> str:
    return sanitize_identifier(filename).casefold()


def import_material_rows(
    metadata: MaterialTableMetadata,
    rows: tuple[MaterialTableRow, ...],
    *,
    upload_filename: str,
    upload_kind: SourceKind,
    upload_bytes: bytes,
) -> ImportedMaterialTable:
    if upload_kind not in (SourceKind.CSV, SourceKind.SPREADSHEET):
        raise MaterialImportError(("upload kind must be csv or spreadsheet",))
    if not rows:
        raise MaterialImportError(("material table requires at least one data row",))

    blank_ids = tuple(
        f"row {index} series_id must not be blank"
        for index, row in enumerate(rows, start=1)
        if not row.series_id.strip()
    )
    if blank_ids:
        raise MaterialImportError(blank_ids)

    grouped: dict[str, list[MaterialTableRow]] = {}
    for row in rows:
        grouped.setdefault(row.series_id, []).append(row)

    issues: list[str] = []
    metadata_fields = (
        "kind",
        "frequency_hz",
        "temperature_c",
        "dc_bias_a_per_m",
        "x_unit",
        "y_unit",
    )
    for series_id, group in grouped.items():
        first = group[0]
        for field in metadata_fields:
            if any(getattr(row, field) != getattr(first, field) for row in group[1:]):
                issues.append(f"series '{series_id}' has inconsistent {field}")

    filenames: dict[str, str] = {}
    upload_filename_key = _source_filename_key(upload_filename)
    for series_id in grouped:
        filename = f"series-{sanitize_identifier(series_id)}.csv"
        filename_key = _source_filename_key(filename)
        if previous_id := filenames.get(filename_key):
            issues.append(
                f"series IDs '{previous_id}' and '{series_id}' generate the same "
                f"source filename '{filename}'"
            )
        elif filename_key == upload_filename_key:
            issues.append(f"generated source filename '{filename}' conflicts with upload filename")
        else:
            filenames[filename_key] = series_id
    if issues:
        raise MaterialImportError(tuple(issues))

    sources = [_source(metadata, upload_kind, upload_filename, upload_bytes)]
    source_files = [(upload_filename, upload_bytes)]
    series: list[PointSeries] = []
    for series_id, group in grouped.items():
        first = group[0]
        filename = f"series-{sanitize_identifier(series_id)}.csv"
        data = ("x,y\n" + "".join(f"{row.x},{row.y}\n" for row in group)).encode()
        source = _source(metadata, SourceKind.CSV, filename, data)
        sources.append(source)
        source_files.append((filename, data))
        series.append(
            import_curve_csv(
                data.decode(),
                series_id=series_id,
                kind=first.kind,
                x_unit=first.x_unit,
                y_unit=first.y_unit,
                conditions=CurveConditions(
                    first.frequency_hz,
                    first.temperature_c,
                    first.dc_bias_a_per_m,
                ),
                source=source,
            )
        )

    return ImportedMaterialTable(
        ref=metadata.ref,
        series=tuple(series),
        sources=tuple(sources),
        source_files=tuple(source_files),
    )
