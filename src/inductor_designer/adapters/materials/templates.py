from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files


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
