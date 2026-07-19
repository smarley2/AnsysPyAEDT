from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePath

from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtGui import QImage
from PySide6.QtPdf import QPdfDocument

_RASTER_SUFFIXES = frozenset({".png", ".jpg", ".jpeg"})
_SUPPORTED_SUFFIXES = _RASTER_SUFFIXES | {".pdf"}


class MaterialSourceError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class RenderedMaterialSource:
    png_data: bytes
    width_px: int
    height_px: int
    page_count: int
    page_index: int


def _out_of_range(filename: str, page_index: int, page_count: int) -> MaterialSourceError:
    return MaterialSourceError(
        f"Material source page {page_index} is out of range for {filename} "
        f"({page_count} pages)."
    )


def _render_pdf_page(filename: str, data: bytes, page_index: int) -> tuple[QImage, int]:
    source_buffer = QBuffer()
    source_buffer.setData(data)
    if not source_buffer.open(QIODevice.OpenModeFlag.ReadOnly):
        raise MaterialSourceError(f"Cannot decode material source: {filename}")

    document = QPdfDocument()
    document.load(source_buffer)
    if document.status() != QPdfDocument.Status.Ready:
        raise MaterialSourceError(f"Cannot decode material source: {filename}")
    page_count = document.pageCount()
    if not 0 <= page_index < page_count:
        raise _out_of_range(filename, page_index, page_count)
    render_size = document.pagePointSize(page_index).toSize()
    if render_size.isEmpty():
        raise MaterialSourceError(f"Cannot decode material source: {filename}")
    image = document.render(page_index, render_size)
    return image, page_count


def _image_to_png(image: QImage) -> bytes:
    output_buffer = QBuffer()
    if not output_buffer.open(QIODevice.OpenModeFlag.WriteOnly):
        raise MaterialSourceError("Cannot encode rendered material source as PNG.")
    saved = image.save(output_buffer, "PNG")  # type: ignore[call-overload]
    if not saved:
        raise MaterialSourceError("Cannot encode rendered material source as PNG.")
    return bytes(output_buffer.data().data())


def render_material_source(
    filename: str,
    data: bytes,
    *,
    page_index: int = 0,
) -> RenderedMaterialSource:
    suffix = PurePath(filename).suffix.casefold()
    if suffix not in _SUPPORTED_SUFFIXES:
        raise MaterialSourceError(f"Unsupported material source type: {filename}")

    if suffix == ".pdf":
        image, page_count = _render_pdf_page(filename, data, page_index)
    else:
        page_count = 1
        if page_index != 0:
            raise _out_of_range(filename, page_index, page_count)
        image = QImage.fromData(data)
    if image.isNull():
        raise MaterialSourceError(f"Cannot decode material source: {filename}")
    return RenderedMaterialSource(
        png_data=_image_to_png(image),
        width_px=image.width(),
        height_px=image.height(),
        page_count=page_count,
        page_index=page_index,
    )
