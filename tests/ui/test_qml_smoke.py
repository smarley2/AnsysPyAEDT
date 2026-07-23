from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QSG_RHI_BACKEND", "software")

pytest.importorskip("PySide6")

from PySide6.QtCore import Property, QObject, Signal, Slot  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

from inductor_designer.ui.main import create_engine  # noqa: E402


class RecordingMaterialStudioController(QObject):
    libraryChanged = Signal()
    selectionChanged = Signal()
    editorReset = Signal()
    dirtyChanged = Signal()
    statusMessageChanged = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._materials = [
            {"manufacturer": "ACME", "name": "Ferrite", "grade": "N87"}
        ]
        self._revisions = [
            {
                "revisionId": "111111111111",
                "status": "approved",
                "createdAt": "2026-07-19T10:00:00+00:00",
                "reviewedBy": "Ada",
                "approvedBy": "Grace",
                "seriesCount": 1,
                "validationErrors": 0,
                "validationWarnings": 0,
                "isLatestApproved": True,
            }
        ]
        self._series = [
            {
                "seriesId": "bh-25c",
                "kind": "bh-curve",
                "xUnit": "A/m",
                "yUnit": "T",
                "temperatureC": 25.0,
                "frequencyHz": None,
                "dcBiasAPerM": None,
                "pointCount": 3,
                "sourceKind": "csv",
                "sourceFilename": "bh.csv",
            }
        ]
        self._points = [
            {"seriesId": "bh-25c", "index": 0, "x": 0.0, "y": 0.0},
            {"seriesId": "bh-25c", "index": 1, "x": 100.0, "y": 0.02},
            {"seriesId": "bh-25c", "index": 2, "x": 200.0, "y": 0.04},
        ]
        self._selected_material = self._materials[0]
        self._selected_revision = {
            **self._revisions[0],
            **self._selected_material,
            "sources": [
                {
                    "kind": "csv",
                    "filename": "bh.csv",
                    "sha256": "a" * 64,
                    "url": "",
                    "page": None,
                    "capturedAt": "2026-07-19T10:00:00+00:00",
                    "description": "Imported B-H table",
                }
            ],
        }
        self.calls: list[tuple[object, ...]] = []

    materials = Property(list, lambda self: self._materials, notify=libraryChanged)
    revisions = Property(list, lambda self: self._revisions, notify=libraryChanged)
    selectedMaterial = Property(
        dict, lambda self: self._selected_material, notify=selectionChanged
    )
    selectedRevision = Property(
        dict, lambda self: self._selected_revision, notify=selectionChanged
    )
    series = Property(list, lambda self: self._series, notify=selectionChanged)
    points = Property(list, lambda self: self._points, notify=selectionChanged)
    sourcePoints = Property(list, lambda self: self._points, notify=selectionChanged)
    sourceComparisonAvailable = Property(
        bool, lambda self: True, notify=selectionChanged
    )
    issues = Property(list, lambda self: [], notify=selectionChanged)
    fit = Property(dict, lambda self: {}, notify=selectionChanged)
    tableEditing = Property(
        dict,
        lambda self: {"metadata": {
            "seriesId": "bh-25c",
            "kind": "bh-curve",
            "xUnit": "A/m",
            "yUnit": "T",
            "frequencyHz": None,
            "temperatureC": 25.0,
            "dcBiasAPerM": None,
        }},
        notify=selectionChanged,
    )
    dirty = Property(bool, lambda self: False, notify=dirtyChanged)
    canSave = Property(bool, lambda self: False, notify=selectionChanged)
    canReview = Property(bool, lambda self: False, notify=selectionChanged)
    canApprove = Property(bool, lambda self: False, notify=selectionChanged)
    canUseInProject = Property(bool, lambda self: False, notify=selectionChanged)
    hasProject = Property(bool, lambda self: False, constant=True)
    statusMessage = Property(str, lambda self: "Ready", notify=statusMessageChanged)

    @Slot(str, str, str, result=bool)
    def selectMaterial(self, manufacturer: str, name: str, grade: str) -> bool:
        self.calls.append(("selectMaterial", manufacturer, name, grade))
        return True

    @Slot(str, result=bool)
    def selectRevision(self, revision_id: str) -> bool:
        self.calls.append(("selectRevision", revision_id))
        return True

    @Slot(str)
    def selectSeries(self, series_id: str) -> None:
        self.calls.append(("selectSeries", series_id))

    @Slot(str, str)
    def invalidateEditorInput(self, group: str, message: str) -> None:
        self.calls.append(("invalidateEditorInput", group, message))

    @Slot(int)
    def deletePoint(self, index: int) -> None:
        self.calls.append(("deletePoint", index))

    @Slot(str, int, float, float, result=bool)
    def setCanonicalPoint(self, series_id: str, index: int, x: float, y: float) -> bool:
        self.calls.append(("setCanonicalPoint", series_id, index, x, y))
        return True

    @Slot(str, str, str, str, float, float, float)
    def setSeriesMetadata(self, *values: object) -> None:
        self.calls.append(("setSeriesMetadata", *values))

    @Slot(str, str, str, str, float, float, float, list, result=bool)
    def addTableSeries(self, *values: object) -> bool:
        self.calls.append(("addTableSeries", *values))
        return True

    @Slot(str, result=bool)
    def removeSeries(self, series_id: str) -> bool:
        self.calls.append(("removeSeries", series_id))
        return True

    @Slot(str)
    def importTable(self, url: str) -> None:
        self.calls.append(("importTable", url))

    @Slot(str)
    def importEditedWorkbook(self, url: str) -> None:
        self.calls.append(("importEditedWorkbook", url))

    @Slot(str, str)
    def downloadTemplate(self, file_format: str, url: str) -> None:
        self.calls.append(("downloadTemplate", file_format, url))

    @Slot(str)
    def exportSelectedWorkbook(self, url: str) -> None:
        self.calls.append(("exportSelectedWorkbook", url))

    @Slot(str)
    def reviewDraft(self, actor: str) -> None:
        self.calls.append(("reviewDraft", actor))

    @Slot(str)
    def approveRevision(self, actor: str) -> None:
        self.calls.append(("approveRevision", actor))

    @Slot(str)
    def useInProject(self, series_id: str) -> None:
        self.calls.append(("useInProject", series_id))


def _root(
    controller: RecordingMaterialStudioController,
) -> tuple[QGuiApplication, object, QObject, RecordingMaterialStudioController]:
    app = QGuiApplication.instance() or QGuiApplication([])
    engine = create_engine(material_studio_controller=controller)
    root = engine.rootObjects()[0]
    root.findChild(QObject, "guidedStepList").setProperty("currentIndex", 2)
    app.processEvents()
    return app, engine, root, controller


@pytest.mark.ui
def test_guided_studio_qml_loads() -> None:
    app = QGuiApplication.instance() or QGuiApplication([])
    engine = create_engine()

    assert app is not None
    assert len(engine.rootObjects()) == 1


@pytest.mark.ui
def test_material_page_has_no_image_workflow_and_exposes_curve_plot() -> None:
    controller = RecordingMaterialStudioController()
    app, engine, root, _controller = _root(controller)

    assert engine.rootContext().contextProperty("materialStudioController") is controller
    for name in (
        "materialLibraryPane",
        "materialImportExportPane",
        "materialCurveWorkspace",
        "materialCurveEditor",
        "materialCurveCanvas",
        "curvePlotTitle",
        "curvePlotDetails",
        "curvePlotXAxisLabel",
        "curvePlotYAxisLabel",
    ):
        assert root.findChild(QObject, name) is not None, name
    for name in (
        "materialSourceView",
        "imageSourceDialog",
        "importImageButton",
        "cropSectionTitle",
        "xAxisSectionTitle",
        "yAxisSectionTitle",
        "materialValidationPane",
        "revisionList",
    ):
        assert root.findChild(QObject, name) is None, name
    assert app is not None


@pytest.mark.ui
def test_material_library_renders_material_without_revision_list() -> None:
    _app, _engine, root, _controller = _root(RecordingMaterialStudioController())
    material_list = root.findChild(QObject, "materialList")
    revision_list = root.findChild(QObject, "revisionList")

    assert material_list is not None
    assert material_list.property("count") == 1
    assert revision_list is None


@pytest.mark.ui
def test_curve_labels_are_accessible() -> None:
    _app, _engine, root, _controller = _root(RecordingMaterialStudioController())
    plot_details = root.findChild(QObject, "curvePlotDetails")
    x_label = root.findChild(QObject, "curvePlotXAxisLabel")
    y_label = root.findChild(QObject, "curvePlotYAxisLabel")

    assert "bh-25c" in str(plot_details.property("text"))
    assert "temperature 25" in str(plot_details.property("text"))
    assert "A/m" in str(x_label.property("text"))
    assert "T" in str(y_label.property("text"))
