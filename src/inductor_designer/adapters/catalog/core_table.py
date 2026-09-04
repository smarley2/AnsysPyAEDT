"""The table a user fills in from a datasheet, one row per part number.

Design: ``docs/superpowers/specs/2026-09-04-user-core-catalog-design.md``.

Deliberately not a change to ``adapters/materials/table_file.py``: that reader
is material-shaped (metadata blocks, series kinds, unit validation across a
whole workbook), and a core table is a flat header plus rows. It borrows the
one rule from it that is about trust rather than shape -- reject formula cells
rather than evaluate them -- so an imported ``alValueNh`` is a number a person
read off a datasheet, not the output of a spreadsheet this application can
neither see nor cite.

The columns ARE the catalog schema's field names, with the material object and
each dimension flattened because a spreadsheet has no nesting, and every row
is validated against ``schemas/catalog/core.v1.schema.json`` itself. The
template and the validator therefore cannot disagree about what a column
means.

A bad row is rejected on its own and named by the line number the user sees;
a bad header refuses the file, because then there is no way to know which
value was meant for which field.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

from jsonschema import Draft202012Validator, ValidationError
from openpyxl import Workbook, load_workbook  # type: ignore[import-untyped]

from inductor_designer.adapters.persistence.record_serde import core_record_from_json

if TYPE_CHECKING:
    from inductor_designer.domain.catalog_records import CoreRecord

_DIMENSIONS = ("outerDiameter", "innerDiameter", "height")

#: Schema field order, flattened. `material` becomes three columns and each
#: dimension becomes its nominal plus the two optional tolerance bounds.
CORE_TEMPLATE_COLUMNS: tuple[str, ...] = (
    "manufacturer",
    "family",
    "partNumber",
    "materialManufacturer",
    "materialName",
    "materialGrade",
    "coating",
    "catalogRevision",
    "sourceUrl",
    "sourcePage",
    *(f"{name}{bound}" for name in _DIMENSIONS for bound in ("NominalM", "MinM", "MaxM")),
    "effectiveAreaM2",
    "pathLengthM",
    "volumeM3",
    "alValueNh",
    "reviewStatus",
    "reviewedBy",
)

_NUMBER_COLUMNS = frozenset(
    {
        *(f"{name}NominalM" for name in _DIMENSIONS),
        *(f"{name}MinM" for name in _DIMENSIONS),
        *(f"{name}MaxM" for name in _DIMENSIONS),
        "effectiveAreaM2",
        "pathLengthM",
        "volumeM3",
        "alValueNh",
    }
)
_OPTIONAL_COLUMNS = frozenset(
    {
        *(f"{name}MinM" for name in _DIMENSIONS),
        *(f"{name}MaxM" for name in _DIMENSIONS),
        "reviewedBy",
    }
)

_TEMPLATE_STEM = "core-import-template"


class CoreTableError(ValueError):
    """The file cannot be read as a core table at all."""


@dataclass(frozen=True, slots=True)
class CoreTemplateDownload:
    filename: str
    content_type: str
    data: bytes


@dataclass(frozen=True, slots=True)
class CoreRowRejection:
    """One row that could not become a core, and why.

    `row` is the line number in the user's own file (the header is row 1), so
    the report names the row they can go and look at.
    """

    row: int
    reason: str


@dataclass(frozen=True, slots=True)
class CoreImportResult:
    records: tuple[CoreRecord, ...]
    rejections: tuple[CoreRowRejection, ...]


def core_import_template(file_format: str) -> CoreTemplateDownload:
    """An empty table with the header filled in, in the requested format.

    Generated rather than shipped as a resource file: the header comes from
    `CORE_TEMPLATE_COLUMNS`, so there is one definition of the columns instead
    of a packaged file that can drift from it.
    """
    if file_format == "csv":
        buffer = io.StringIO()
        csv.writer(buffer, lineterminator="\n").writerow(CORE_TEMPLATE_COLUMNS)
        return CoreTemplateDownload(
            f"{_TEMPLATE_STEM}.csv", "text/csv", buffer.getvalue().encode("utf-8")
        )
    if file_format == "xlsx":
        workbook = Workbook()
        sheet = workbook.active
        assert sheet is not None
        sheet.title = "cores"
        sheet.append(list(CORE_TEMPLATE_COLUMNS))
        stream = io.BytesIO()
        workbook.save(stream)
        return CoreTemplateDownload(
            f"{_TEMPLATE_STEM}.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            stream.getvalue(),
        )
    raise ValueError("file_format must be 'csv' or 'xlsx'")


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    from inductor_designer.adapters.system import resources

    schema_path = resources.schemas_directory() / "catalog" / "core.v1.schema.json"
    return Draft202012Validator(json.loads(schema_path.read_text(encoding="utf-8")))


def _check_header(header: tuple[str, ...]) -> None:
    missing = [name for name in CORE_TEMPLATE_COLUMNS if name not in header]
    if missing:
        raise CoreTableError(
            "The file is missing these columns: "
            + ", ".join(missing)
            + ". Download the core template and fill that in."
        )


def _number(text: str, column: str) -> float:
    try:
        return float(text)
    except ValueError as error:
        raise ValueError(f"{column} must be a number, got {text!r}") from error


def _record_json(values: dict[str, str]) -> dict[str, Any]:
    """One row as the schema's own shape, so the schema can judge it."""
    document: dict[str, Any] = {}
    for column in CORE_TEMPLATE_COLUMNS:
        text = (values.get(column) or "").strip()
        if not text and column not in _OPTIONAL_COLUMNS:
            raise ValueError(f"{column} is required")
        if column in _NUMBER_COLUMNS:
            document[column] = _number(text, column) if text else None
        elif column == "sourcePage":
            document[column] = int(_number(text, column))
        else:
            document[column] = text or None

    material = {
        "manufacturer": document.pop("materialManufacturer"),
        "name": document.pop("materialName"),
        "grade": document.pop("materialGrade"),
    }
    dimensions = {
        name: {
            "nominalM": document.pop(f"{name}NominalM"),
            "minM": document.pop(f"{name}MinM"),
            "maxM": document.pop(f"{name}MaxM"),
        }
        for name in _DIMENSIONS
    }
    return {**document, "material": material, **dimensions}


def _rows_from_csv(filename: str, data: bytes) -> list[dict[str, str]]:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise CoreTableError(f"{filename} must be valid UTF-8 text.") from error
    reader = csv.DictReader(io.StringIO(text))
    _check_header(tuple(reader.fieldnames or ()))
    return [{key: (value or "") for key, value in row.items() if key} for row in reader]


def _rows_from_xlsx(filename: str, data: bytes) -> list[dict[str, str]]:
    try:
        # `data_only=False` keeps formulas visible as formulas, which is the
        # only way to refuse them instead of silently taking a cached value.
        workbook = load_workbook(io.BytesIO(data), data_only=False)
    except Exception as error:  # noqa: BLE001 - openpyxl raises several unrelated types
        raise CoreTableError(f"{filename} could not be read as a workbook.") from error
    sheet = workbook.active
    if sheet is None:
        raise CoreTableError(f"{filename} has no worksheet.")
    for row in sheet.iter_rows():
        for cell in row:
            if cell.data_type == "f":
                raise CoreTableError(
                    f"{filename}!{cell.coordinate} contains a formula. Every "
                    "value must be a number read from the datasheet, not a "
                    "formula this application cannot cite."
                )
    header = tuple(str(cell.value) if cell.value is not None else "" for cell in sheet[1])
    _check_header(header)
    rows: list[dict[str, str]] = []
    for values in sheet.iter_rows(min_row=2, values_only=True):
        if all(value is None or str(value).strip() == "" for value in values):
            continue
        rows.append(
            {
                name: ("" if value is None else str(value))
                for name, value in zip(header, values, strict=False)
            }
        )
    return rows


def import_core_file(filename: str, data: bytes) -> CoreImportResult:
    """Read a filled core table, keeping every row that stands on its own.

    A datasheet family is ten rows off one page. Refusing all ten because of
    one typo sends the user back to asking for a rebuild, so each row is
    judged alone and the rejections carry the row number and the reason.
    """
    suffix = Path(filename).suffix.casefold()
    rows = (
        _rows_from_xlsx(filename, data)
        if suffix in {".xlsx", ".xlsm"}
        else _rows_from_csv(filename, data)
    )

    records: list[CoreRecord] = []
    rejections: list[CoreRowRejection] = []
    for offset, values in enumerate(rows):
        row_number = offset + 2  # the header is row 1
        try:
            document = _record_json(values)
        except ValueError as error:
            rejections.append(CoreRowRejection(row_number, str(error)))
            continue
        try:
            _validator().validate(document)
        except ValidationError as error:
            field = ".".join(str(part) for part in error.absolute_path) or "the row"
            rejections.append(CoreRowRejection(row_number, f"{field}: {error.message}"))
            continue
        records.append(core_record_from_json(document))
    return CoreImportResult(tuple(records), tuple(rejections))
