from __future__ import annotations

import os
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QBuffer, QIODevice, QRectF  # noqa: E402
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPdfWriter  # noqa: E402
from PySide6.QtPdf import QPdfDocument  # noqa: E402

from inductor_designer.ui import material_source  # noqa: E402
from inductor_designer.ui.material_source import (  # noqa: E402
    MaterialSourceError,
    render_material_source,
)

pytestmark = pytest.mark.ui

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/materials/manual-bh.png"


@pytest.fixture(scope="module", autouse=True)
def _application() -> QGuiApplication:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    return QGuiApplication.instance() or QGuiApplication([])


def _encoded_image(width: int, height: int, file_format: str) -> bytes:
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor("darkcyan"))
    output = QBuffer()
    assert output.open(QIODevice.OpenModeFlag.WriteOnly)
    assert image.save(output, file_format)
    return bytes(output.data())


def _two_page_pdf() -> bytes:
    output = QBuffer()
    assert output.open(QIODevice.OpenModeFlag.WriteOnly)
    writer = QPdfWriter(output)
    writer.setResolution(72)
    painter = QPainter(writer)
    painter.fillRect(QRectF(0.0, 0.0, writer.width(), writer.height()), QColor("red"))
    assert writer.newPage()
    painter.fillRect(QRectF(0.0, 0.0, writer.width(), writer.height()), QColor("blue"))
    painter.end()
    return bytes(output.data())


def test_render_png_fixture_to_png_at_original_dimensions() -> None:
    rendered = render_material_source("manual-bh.png", _FIXTURE.read_bytes())

    assert rendered.png_data.startswith(b"\x89PNG\r\n\x1a\n")
    assert (rendered.width_px, rendered.height_px) == (12, 8)
    assert rendered.page_count == 1
    assert rendered.page_index == 0


def test_render_in_memory_jpeg_to_png_at_original_dimensions() -> None:
    rendered = render_material_source("curve.JPEG", _encoded_image(9, 7, "JPEG"))

    assert rendered.png_data.startswith(b"\x89PNG\r\n\x1a\n")
    assert (rendered.width_px, rendered.height_px) == (9, 7)
    assert rendered.page_count == 1
    assert rendered.page_index == 0


def test_render_requested_pdf_page_without_text_extraction(monkeypatch: pytest.MonkeyPatch) -> None:
    class NoTextPdfDocument(QPdfDocument):
        def getAllText(self, page: int) -> object:  # noqa: N802
            raise AssertionError(f"PDF text extraction called for page {page}")

    monkeypatch.setattr(material_source, "QPdfDocument", NoTextPdfDocument)
    pdf_data = _two_page_pdf()

    first = render_material_source("curve.pdf", pdf_data, page_index=0)
    second = render_material_source("curve.pdf", pdf_data, page_index=1)

    assert first.page_count == second.page_count == 2
    assert first.page_index == 0
    assert second.page_index == 1
    assert first.png_data.startswith(b"\x89PNG\r\n\x1a\n")
    assert second.png_data.startswith(b"\x89PNG\r\n\x1a\n")
    assert (first.width_px, first.height_px) == (second.width_px, second.height_px)
    assert first.png_data != second.png_data


@pytest.mark.parametrize(
    ("filename", "data", "page_index"),
    [
        ("curve.gif", b"GIF89a", 0),
        ("curve.png", b"", 0),
        ("curve.jpg", b"not a JPEG", 0),
        ("curve.png", _encoded_image(2, 2, "PNG"), -1),
        ("curve.jpeg", _encoded_image(2, 2, "JPEG"), 1),
    ],
)
def test_render_rejects_unsupported_invalid_empty_or_raster_page_input(
    filename: str,
    data: bytes,
    page_index: int,
) -> None:
    with pytest.raises(MaterialSourceError):
        render_material_source(filename, data, page_index=page_index)


def test_render_rejects_invalid_or_out_of_range_pdf_page() -> None:
    with pytest.raises(MaterialSourceError):
        render_material_source("curve.pdf", b"not a PDF")
    with pytest.raises(MaterialSourceError):
        render_material_source("curve.pdf", _two_page_pdf(), page_index=2)
