from __future__ import annotations

import io
from copy import copy
from dataclasses import dataclass
from importlib.resources import files

from openpyxl import load_workbook  # type: ignore[import-untyped]
from openpyxl.worksheet.worksheet import Worksheet  # type: ignore[import-untyped]

from inductor_designer.domain.units import from_canonical
from inductor_designer.geometry.naming import sanitize_identifier
from inductor_designer.materials.records import MaterialRecord, PointSeries, SeriesKind


class MaterialTemplateExportError(ValueError):
    """Raised when a material record cannot be represented as an editable workbook."""


@dataclass(frozen=True, slots=True)
class MaterialTemplateDownload:
    filename: str
    content_type: str
    data: bytes


_TEMPLATES = {
    "csv": ("material-import-template.csv", "text/csv"),
    "xlsx": (
        "material-import-template.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ),
}


def material_import_template(file_format: str) -> MaterialTemplateDownload:
    """Return an immutable packaged material import template."""
    try:
        filename, content_type = _TEMPLATES[file_format]
    except KeyError as error:
        raise ValueError("file_format must be 'csv' or 'xlsx'") from error
    data = files("inductor_designer.resources.material_templates").joinpath(filename).read_bytes()
    return MaterialTemplateDownload(filename, content_type, data)


def _replace_rows(sheet: Worksheet, rows: list[tuple[object, ...]], table_name: str) -> None:
    column_count = sheet.max_column
    template_styles = tuple(
        copy(sheet.cell(row=2, column=column)._style)
        for column in range(1, column_count + 1)
    )
    if sheet.max_row > 1:
        sheet.delete_rows(2, sheet.max_row - 1)
    for row_number, values in enumerate(rows, start=2):
        for column, value in enumerate(values, start=1):
            cell = sheet.cell(row=row_number, column=column, value=value)
            cell._style = copy(template_styles[column - 1])
    last_row = max(1, len(rows) + 1)
    sheet.tables[table_name].ref = f"A1:{sheet.cell(row=last_row, column=column_count).coordinate}"


def _bh_rows(series: PointSeries) -> list[tuple[object, ...]]:
    return [
        (
            series.series_id,
            series.conditions.temperature_c,
            series.conditions.dc_bias_a_per_m,
            series.x_unit,
            series.y_unit,
            from_canonical(point.x, series.x_unit),
            from_canonical(point.y, series.y_unit),
        )
        for point in series.points
    ]


def _loss_rows(series: PointSeries) -> list[tuple[object, ...]]:
    return [
        (
            series.series_id,
            series.conditions.frequency_hz,
            series.conditions.temperature_c,
            series.conditions.dc_bias_a_per_m,
            series.x_unit,
            series.y_unit,
            from_canonical(point.x, series.x_unit),
            from_canonical(point.y, series.y_unit),
        )
        for point in series.points
    ]


def export_material_record_xlsx(record: MaterialRecord) -> MaterialTemplateDownload:
    """Export all tabular curves in a material record as an editable workbook."""
    if not record.series:
        raise MaterialTemplateExportError(
            "Material has no curves to export; add B-H or loss curves before editing a workbook."
        )

    template = material_import_template("xlsx")
    workbook = load_workbook(io.BytesIO(template.data), data_only=False)
    source = record.sources[0]
    metadata = {
        "manufacturer": record.ref.manufacturer,
        "material_name": record.ref.name,
        "grade": record.ref.grade,
        "source_url": source.url,
        "source_page": source.page,
        "captured_at": source.captured_at,
        "source_description": f"Editable export of base material revision {record.revision_id}",
    }
    material = workbook["Material"]
    for row in range(2, material.max_row + 1):
        field = str(material.cell(row=row, column=1).value)
        material.cell(row=row, column=2, value=metadata[field])

    bh_rows = [
        row
        for series in record.series
        if series.kind is SeriesKind.BH_CURVE
        for row in _bh_rows(series)
    ]
    loss_rows = [
        row
        for series in record.series
        if series.kind is SeriesKind.LOSS_TABLE
        for row in _loss_rows(series)
    ]
    _replace_rows(workbook["B-H Curves"], bh_rows, "BHCurvesTable")
    _replace_rows(workbook["Loss Curves"], loss_rows, "LossCurvesTable")

    workbook.properties.creator = "PyAEDT Inductor Designer"
    workbook.properties.title = f"{record.ref.manufacturer} {record.ref.name} {record.ref.grade}"
    workbook.properties.subject = f"Editable material revision {record.revision_id}"
    workbook.properties.description = metadata["source_description"]
    stream = io.BytesIO()
    workbook.save(stream)
    ref = sanitize_identifier(
        "_".join((record.ref.manufacturer, record.ref.name, record.ref.grade))
    )
    return MaterialTemplateDownload(
        f"material-{ref}-{record.revision_id}.xlsx",
        template.content_type,
        stream.getvalue(),
    )
