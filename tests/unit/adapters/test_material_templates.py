from __future__ import annotations

import io

import pytest
from openpyxl import load_workbook

from inductor_designer.adapters.materials.table_file import import_material_file
from inductor_designer.adapters.materials.templates import material_import_template


def test_packaged_templates_have_download_metadata_and_equivalent_examples() -> None:
    csv_download = material_import_template("csv")
    xlsx_download = material_import_template("xlsx")

    assert csv_download.filename == "material-import-template.csv"
    assert csv_download.content_type == "text/csv"
    assert isinstance(csv_download.data, bytes)
    assert csv_download.data
    assert xlsx_download.filename == "material-import-template.xlsx"
    assert (
        xlsx_download.content_type
        == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert isinstance(xlsx_download.data, bytes)
    assert xlsx_download.data

    csv_result = import_material_file(csv_download.filename, csv_download.data)
    xlsx_result = import_material_file(xlsx_download.filename, xlsx_download.data)
    assert xlsx_result.ref == csv_result.ref
    assert xlsx_result.series == csv_result.series


def test_packaged_xlsx_has_documented_structure_and_validations() -> None:
    download = material_import_template("xlsx")
    workbook = load_workbook(io.BytesIO(download.data), data_only=False)

    assert tuple(sheet.title for sheet in workbook.worksheets) == (
        "Instructions",
        "Material",
        "B-H Curves",
        "Loss Curves",
    )
    assert all(sheet.sheet_state == "visible" for sheet in workbook.worksheets)

    material = workbook["Material"]
    bh = workbook["B-H Curves"]
    loss = workbook["Loss Curves"]
    assert tuple(cell.value for cell in material[1]) == ("field", "value")
    assert tuple(cell.value for cell in bh[1]) == (
        "series_id",
        "temperature_c",
        "dc_bias_a_per_m",
        "h_unit",
        "b_unit",
        "h",
        "b",
    )
    assert tuple(cell.value for cell in loss[1]) == (
        "series_id",
        "frequency_hz",
        "temperature_c",
        "dc_bias_a_per_m",
        "b_unit",
        "loss_unit",
        "b",
        "loss",
    )
    for sheet in (material, bh, loss):
        assert tuple(table.ref for table in sheet.tables.values()) == (sheet.dimensions,)

    validations = {
        (sheet.title, validation.sqref): validation.formula1
        for sheet in (bh, loss)
        for validation in sheet.data_validations.dataValidation
    }
    assert validations == {
        ("B-H Curves", "D2:D200"): '\"A/m,kA/m,Oe\"',
        ("B-H Curves", "E2:E200"): '\"T,mT,G,kG\"',
        ("Loss Curves", "E2:E200"): '\"T,mT,G,kG\"',
        ("Loss Curves", "F2:F200"): '\"W/m3,kW/m3,mW/cm3\"',
    }


def test_material_import_template_rejects_unknown_format() -> None:
    with pytest.raises(ValueError, match="csv.*xlsx"):
        material_import_template("xls")
