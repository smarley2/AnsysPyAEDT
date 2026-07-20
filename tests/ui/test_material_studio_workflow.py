from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QSG_RHI_BACKEND", "software")

pytest.importorskip("PySide6")

from PySide6.QtCore import QObject, QUrl  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from inductor_designer.adapters.materials import (  # noqa: E402
    material_import_template,
)
from inductor_designer.ui.main import create_engine  # noqa: E402
from inductor_designer.ui.material_studio_controller import (  # noqa: E402
    MaterialStudioController,
)
from tests.fakes.material_repository import InMemoryMaterialRepository  # noqa: E402

_APP = QGuiApplication.instance() or QGuiApplication([])


def _file_url(path: Path) -> str:
    return QUrl.fromLocalFile(str(path)).toString()


def _root(tmp_path: Path, *, import_table: bool = True) -> tuple[object, object, object]:
    controller = MaterialStudioController(
        InMemoryMaterialRepository(),
        now=lambda: "2026-07-19T10:00:00+00:00",
    )
    if import_table:
        template = material_import_template("csv")
        path = tmp_path / template.filename
        path.write_bytes(template.data)
        controller.importTable(_file_url(path))
    engine = create_engine(material_studio_controller=controller)
    root = engine.rootObjects()[0]
    root.findChild(QObject, "guidedStepList").setProperty("currentIndex", 2)
    _APP.processEvents()
    return controller, engine, root


@pytest.mark.ui
def test_material_workflow_exposes_table_import_and_curve_plot_regions(
    tmp_path: Path,
) -> None:
    app_controller, engine, root = _root(tmp_path)

    for name in (
        "materialLibraryPane",
        "materialImportExportPane",
        "materialCurveWorkspace",
        "materialValidationPane",
        "materialLifecyclePane",
        "downloadCsvTemplateButton",
        "downloadXlsxTemplateButton",
        "uploadTableButton",
        "exportRevisionButton",
        "reimportWorkbookButton",
        "templateCsvDialog",
        "templateXlsxDialog",
        "tableUploadDialog",
        "revisionExportDialog",
        "workbookReimportDialog",
        "materialCurveEditor",
        "materialCurveCanvas",
        "curvePlotTitle",
        "curvePlotDetails",
        "curvePlotXAxisLabel",
        "curvePlotYAxisLabel",
        "curvePlotEmptyState",
    ):
        assert root.findChild(QObject, name) is not None, name

    assert root.findChild(QObject, "materialSourceView") is None
    assert root.findChild(QObject, "imageSourceDialog") is None
    assert root.findChild(QObject, "cropSectionTitle") is None
    assert root.findChild(QObject, "xAxisSectionTitle") is None
    assert root.findChild(QObject, "yAxisSectionTitle") is None
    assert app_controller.selectedRevision["status"] == "draft"
    assert engine.rootObjects()


@pytest.mark.ui
def test_curve_plot_labels_follow_selected_table_series(tmp_path: Path) -> None:
    controller, _engine, root = _root(tmp_path)
    plot_details = root.findChild(QObject, "curvePlotDetails")
    x_label = root.findChild(QObject, "curvePlotXAxisLabel")
    y_label = root.findChild(QObject, "curvePlotYAxisLabel")

    assert "bh-25c" in str(plot_details.property("text"))
    assert "temperature 25" in str(plot_details.property("text"))
    assert "Oe" in str(x_label.property("text"))
    assert "G" in str(y_label.property("text"))

    controller.selectSeries("loss-100khz")
    _APP.processEvents()

    assert "loss-100khz" in str(plot_details.property("text"))
    assert "frequency 100000" in str(plot_details.property("text"))
    assert "kG" in str(x_label.property("text"))
    assert "mW/cm3" in str(y_label.property("text"))


@pytest.mark.ui
def test_empty_library_has_explicit_table_import_empty_state(tmp_path: Path) -> None:
    _controller, _engine, root = _root(tmp_path, import_table=False)
    empty_state = root.findChild(QObject, "curvePlotEmptyState")
    text = str(empty_state.property("text"))

    assert empty_state.property("visible") is True
    assert "CSV" in text
    assert "XLSX" in text


@pytest.mark.ui
def test_material_page_reflows_for_compact_and_wide_windows(tmp_path: Path) -> None:
    _controller, _engine, root = _root(tmp_path)
    page = root.findChild(QObject, "materialStudioPage")
    overview = root.findChild(QObject, "materialOverviewGrid")
    workspace = root.findChild(QObject, "materialWorkspaceGrid")

    page.setProperty("width", 860)
    _APP.processEvents()
    assert overview.property("columns") == 1
    assert workspace.property("columns") == 1

    page.setProperty("width", 1900)
    _APP.processEvents()
    assert overview.property("columns") == 3
    assert workspace.property("columns") == 2
