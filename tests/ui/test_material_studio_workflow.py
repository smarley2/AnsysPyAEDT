from __future__ import annotations

import base64
import math
import os
from collections.abc import Mapping
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QSG_RHI_BACKEND", "software")

pytest.importorskip("PySide6")

from PySide6.QtCore import (  # noqa: E402
    Property,
    QMetaObject,
    QObject,
    QPoint,
    QPointF,
    Qt,
    QUrl,
    Signal,
    Slot,
)
from PySide6.QtGui import QAccessible, QAccessibleActionInterface, QGuiApplication  # noqa: E402
from PySide6.QtQuick import QQuickItem  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from inductor_designer.adapters.materials import (  # noqa: E402
    import_material_file_as_draft,
    material_import_template,
)
from inductor_designer.materials.records import MaterialRecord  # noqa: E402
from inductor_designer.ui.main import create_engine  # noqa: E402
from inductor_designer.ui.material_source import render_material_source  # noqa: E402
from inductor_designer.ui.material_studio_controller import (  # noqa: E402
    MaterialStudioController,
)
from tests.fakes.material_repository import InMemoryMaterialRepository  # noqa: E402

_IMAGE = Path(__file__).parents[1] / "fixtures" / "materials" / "manual-bh.png"


class FailingSaveMaterialRepository(InMemoryMaterialRepository):
    def __init__(self) -> None:
        super().__init__()
        self.fail_save = False

    def save(self, record: MaterialRecord, sources: Mapping[str, bytes]) -> None:
        if self.fail_save:
            raise ValueError("controlled material save failure")
        super().save(record, sources)


class WorkflowController(QObject):
    libraryChanged = Signal()
    selectionChanged = Signal()
    sourceChanged = Signal()
    editorReset = Signal()
    dirtyChanged = Signal()
    statusMessageChanged = Signal()

    def __init__(self) -> None:
        super().__init__()
        rendered = render_material_source(_IMAGE.name, _IMAGE.read_bytes())
        self._source = {
            "dataUrl": "data:image/png;base64,"
            + base64.b64encode(rendered.png_data).decode("ascii"),
            "filename": _IMAGE.name,
            "width": rendered.width_px,
            "height": rendered.height_px,
            "pageCount": 1,
            "pageIndex": 0,
        }
        self._editing = {
            "crop": {
                "left": 0,
                "top": 0,
                "width": rendered.width_px,
                "height": rendered.height_px,
            },
            "xAxis": {
                "scale": "linear",
                "pixelA": 1.0,
                "valueA": 0.0,
                "pixelB": 11.0,
                "valueB": 2.0,
            },
            "yAxis": {
                "scale": "linear",
                "pixelA": 7.0,
                "valueA": 0.0,
                "pixelB": 1.0,
                "valueB": 2.0,
            },
            "pixelPoints": [
                {"xPx": 1.0, "yPx": 7.0},
                {"xPx": 11.0, "yPx": 1.0},
            ],
            "metadata": {
                "seriesId": "bh-25c",
                "kind": "bh-curve",
                "xUnit": "A/m",
                "yUnit": "T",
                "frequencyHz": None,
                "temperatureC": 25.0,
                "dcBiasAPerM": 0.0,
            },
        }
        self._series = [
            {
                "seriesId": "bh-25c",
                "kind": "bh-curve",
                "xUnit": "A/m",
                "yUnit": "T",
                "frequencyHz": None,
                "temperatureC": 25.0,
                "dcBiasAPerM": 0.0,
                "pointCount": 2,
                "imageBacked": True,
            },
            {
                "seriesId": "bh-100c",
                "kind": "bh-curve",
                "xUnit": "A/m",
                "yUnit": "T",
                "frequencyHz": None,
                "temperatureC": 100.0,
                "dcBiasAPerM": None,
                "pointCount": 2,
                "imageBacked": False,
            },
        ]
        self._points = [
            {"seriesId": "bh-25c", "index": 0, "x": 0.0, "y": 0.0},
            {"seriesId": "bh-25c", "index": 1, "x": 100.0, "y": 0.2},
        ]
        self._dirty = False
        self._materials = [
            {"manufacturer": "Example", "name": "Ferrite", "grade": "N87"},
            {"manufacturer": "Other", "name": "Ferrite", "grade": "N97"},
        ]
        self._revisions = [
            {
                "revisionId": "111111111111",
                "status": "draft",
                "createdAt": "2026-07-19T10:00:00+00:00",
                "reviewedBy": "",
                "approvedBy": "",
                "seriesCount": 2,
                "validationErrors": 0,
                "validationWarnings": 0,
                "isLatestApproved": False,
            },
            {
                "revisionId": "222222222222",
                "status": "approved",
                "createdAt": "2026-07-19T11:00:00+00:00",
                "reviewedBy": "reviewer@example.com",
                "approvedBy": "approver@example.com",
                "seriesCount": 2,
                "validationErrors": 0,
                "validationWarnings": 0,
                "isLatestApproved": True,
            },
        ]
        self._selected_revision = {
            "manufacturer": "Example",
            "name": "Ferrite",
            "grade": "N87",
            "revisionId": "111111111111",
            "status": "approved",
            "sources": [
                {
                    "kind": "image",
                    "filename": "manual.png",
                    "sha256": "a" * 64,
                    "url": "https://example.com/manual.png",
                    "page": 0,
                    "capturedAt": "2026-07-19T09:00:00+00:00",
                    "description": "Manual B-H graph",
                },
                {
                    "kind": "spreadsheet",
                    "filename": "catalog.xlsx",
                    "sha256": "b" * 64,
                    "url": "https://example.com/catalog.xlsx",
                    "page": None,
                    "capturedAt": "2026-07-19T09:30:00+00:00",
                    "description": "Vendor material table",
                },
            ],
        }
        self._selected_material = {
            "manufacturer": "Example",
            "name": "Ferrite",
            "grade": "N87",
        }
        self.save_succeeds = True
        self.reorder_on_save = False
        self.selection_succeeds = True
        self.can_save = True
        self.can_review = True
        self.can_approve = True
        self.can_use = True
        self._source_points = [dict(point) for point in self._points]
        self._fit = {"k": 1.0, "lossSeriesIds": ["loss-100khz", "loss-200khz"]}
        self.calls: list[tuple[object, ...]] = []

    materials = Property(list, lambda self: self._materials, notify=libraryChanged)
    revisions = Property(list, lambda self: self._revisions, notify=libraryChanged)
    selectedMaterial = Property(
        dict, lambda self: self._selected_material, notify=selectionChanged
    )
    selectedRevision = Property(
        dict,
        lambda self: self._selected_revision,
        notify=selectionChanged,
    )
    series = Property(list, lambda self: self._series, notify=selectionChanged)
    points = Property(list, lambda self: self._points, notify=selectionChanged)
    issues = Property(list, lambda self: [], notify=selectionChanged)
    fit = Property(dict, lambda self: self._fit, notify=selectionChanged)
    sourcePoints = Property(
        list, lambda self: self._source_points, notify=selectionChanged
    )
    sourceComparisonAvailable = Property(
        bool, lambda self: bool(self._source_points), notify=selectionChanged
    )
    source = Property(dict, lambda self: self._source, notify=sourceChanged)
    imageEditing = Property(dict, lambda self: self._editing, notify=sourceChanged)
    statusMessage = Property(str, lambda self: "Ready", notify=statusMessageChanged)
    dirty = Property(bool, lambda self: self._dirty, notify=dirtyChanged)
    canSave = Property(bool, lambda self: self.can_save, notify=selectionChanged)
    canReview = Property(bool, lambda self: self.can_review, notify=selectionChanged)
    canApprove = Property(bool, lambda self: self.can_approve, notify=selectionChanged)
    canUseInProject = Property(bool, lambda self: self.can_use, notify=selectionChanged)

    def set_dirty(self, value: bool) -> None:
        self._dirty = value
        self.dirtyChanged.emit()

    @Slot(float, float)
    def addPixelPoint(self, x_px: float, y_px: float) -> None:
        self.calls.append(("addPixelPoint", x_px, y_px))

    @Slot(int, int, int, int)
    def setCrop(self, left: int, top: int, width: int, height: int) -> None:
        self.calls.append(("setCrop", left, top, width, height))
        self._editing["crop"] = {
            "left": left,
            "top": top,
            "width": width,
            "height": height,
        }
        self.sourceChanged.emit()

    @Slot(str, float, float, float, float)
    def setXAxis(self, *values: object) -> None:
        self.calls.append(("setXAxis", *values))
        self._editing["xAxis"] = {
            "scale": values[0],
            "pixelA": values[1],
            "valueA": values[2],
            "pixelB": values[3],
            "valueB": values[4],
        }
        self.sourceChanged.emit()

    @Slot(str, float, float, float, float)
    def setYAxis(self, *values: object) -> None:
        self.calls.append(("setYAxis", *values))
        self._editing["yAxis"] = {
            "scale": values[0],
            "pixelA": values[1],
            "valueA": values[2],
            "pixelB": values[3],
            "valueB": values[4],
        }
        self.sourceChanged.emit()

    @Slot(int, float, float)
    def movePixelPoint(self, index: int, x_px: float, y_px: float) -> None:
        self.calls.append(("movePixelPoint", index, x_px, y_px))

    @Slot(int)
    def deletePoint(self, index: int) -> None:
        self.calls.append(("deletePoint", index))

    @Slot(str, int, float, float, result=bool)
    def setCanonicalPoint(self, series_id: str, index: int, x: float, y: float) -> bool:
        self.calls.append(("setCanonicalPoint", series_id, index, x, y))
        if not math.isfinite(x) or not math.isfinite(y):
            return False
        self.can_save = True
        self._dirty = True
        self._points[index] = {
            "seriesId": series_id,
            "index": index,
            "x": x,
            "y": y,
        }
        self.selectionChanged.emit()
        return True

    @Slot(str, str, str, str, float, float, float)
    def setSeriesMetadata(self, *values: object) -> None:
        self.calls.append(("setSeriesMetadata", *values))

    @Slot()
    def saveDraft(self) -> None:
        self.calls.append(("saveDraft",))
        if self.save_succeeds:
            if self.reorder_on_save:
                self._materials = self._materials[1:] + self._materials[:1]
                self._revisions = self._revisions[1:] + self._revisions[:1]
                self.libraryChanged.emit()
            self.set_dirty(False)

    @Slot(str)
    def reviewDraft(self, actor: str) -> None:
        self.calls.append(("reviewDraft", actor))

    @Slot(str)
    def approveRevision(self, actor: str) -> None:
        self.calls.append(("approveRevision", actor))

    @Slot(str)
    def useInProject(self, series_id: str) -> None:
        self.calls.append(("useInProject", series_id))

    @Slot(result=bool)
    def discardChanges(self) -> bool:
        self.calls.append(("discardChanges",))
        self.set_dirty(False)
        return True

    @Slot(str, str)
    def downloadTemplate(self, file_format: str, url: str) -> None:
        self.calls.append(("downloadTemplate", file_format, url))

    @Slot(str)
    def importTable(self, url: str) -> None:
        self.calls.append(("importTable", url))

    @Slot(str)
    def exportSelectedWorkbook(self, url: str) -> None:
        self.calls.append(("exportSelectedWorkbook", url))

    @Slot(str)
    def importEditedWorkbook(self, url: str) -> None:
        self.calls.append(("importEditedWorkbook", url))

    @Slot(str, int)
    def importSourceImage(self, url: str, page: int) -> None:
        self.calls.append(("importSourceImage", url, page))

    @Slot(str, str, str, str)
    def createImageDraft(self, *values: object) -> None:
        self.calls.append(("createImageDraft", *values))

    @Slot(str)
    def selectSeries(self, series_id: str) -> None:
        self.calls.append(("selectSeries", series_id))

    @Slot(str, str, str, result=bool)
    def selectMaterial(self, manufacturer: str, name: str, grade: str) -> bool:
        self.calls.append(("selectMaterial", manufacturer, name, grade))
        if self.selection_succeeds:
            self._selected_material = {
                "manufacturer": manufacturer,
                "name": name,
                "grade": grade,
            }
            self._selected_revision = {}
            self.selectionChanged.emit()
        return self.selection_succeeds

    @Slot(str, result=bool)
    def selectRevision(self, revision_id: str) -> bool:
        self.calls.append(("selectRevision", revision_id))
        if self.selection_succeeds:
            self._selected_revision = {
                **self._selected_revision,
                "revisionId": revision_id,
            }
            self.selectionChanged.emit()
        return self.selection_succeeds

    @Slot(str, str)
    def invalidateEditorInput(self, group: str, message: str) -> None:
        self.calls.append(("invalidateEditorInput", group, message))
        self.can_save = False
        self.set_dirty(True)
        self.selectionChanged.emit()

    @Slot(str, str, str, str, float, float, float, list, result=bool)
    def addTableSeries(self, *values: object) -> bool:
        self.calls.append(("addTableSeries", *values))
        return True

    @Slot(str, str, str, str, float, float, float, result=bool)
    def addImageSeries(self, *values: object) -> bool:
        self.calls.append(("addImageSeries", *values))
        return True

    @Slot(str, result=bool)
    def removeSeries(self, series_id: str) -> bool:
        self.calls.append(("removeSeries", series_id))
        return True


def _press(item: QObject) -> None:
    interface = QAccessible.queryAccessibleInterface(item)
    assert interface is not None
    action = interface.actionInterface()
    assert action is not None
    action.doAction(QAccessibleActionInterface.pressAction())


def _accessible_object(root: QObject, name: str) -> QObject:
    pending = [QAccessible.queryAccessibleInterface(root)]
    while pending:
        current = pending.pop(0)
        if current is None:
            continue
        if current.text(QAccessible.Text.Name) == name:
            result = current.object()
            assert result is not None
            return result
        pending.extend(current.child(index) for index in range(current.childCount()))
    raise AssertionError(f"Accessible object not found: {name}")


def _root(controller: WorkflowController) -> tuple[QGuiApplication, object, QObject]:
    app = QGuiApplication.instance() or QGuiApplication([])
    engine = create_engine(material_studio_controller=controller)
    root = engine.rootObjects()[0]
    root.findChild(QObject, "guidedStepList").setProperty("currentIndex", 2)
    app.processEvents()
    return app, engine, root


def _scroll_to_source_workspace(root: QObject, source_view: QQuickItem) -> None:
    scroll_view = root.findChild(QObject, "materialStudioScrollView")
    assert scroll_view is not None
    content_item = scroll_view.property("contentItem")
    assert isinstance(content_item, QQuickItem)
    source_y = source_view.mapToItem(content_item, QPointF(0, 0)).y()
    content_item.setProperty("contentY", max(0.0, source_y - 80.0))


def _real_image_root() -> tuple[
    MaterialStudioController,
    QGuiApplication,
    object,
    QObject,
]:
    controller = MaterialStudioController(
        InMemoryMaterialRepository(),
        now=lambda: "2026-07-19T10:00:00+00:00",
    )
    controller.importSourceImage(QUrl.fromLocalFile(str(_IMAGE)).toString(), 0)
    controller.setXAxis("linear", 1.0, 0.0, 11.0, 2.0)
    controller.setYAxis("linear", 7.0, 0.0, 1.0, 2.0)
    controller.setSeriesMetadata(
        "bh-real",
        "bh-curve",
        "A/m",
        "T",
        float("nan"),
        25.0,
        0.0,
    )
    controller.addPixelPoint(1.0, 7.0)
    controller.addPixelPoint(11.0, 1.0)
    controller.createImageDraft("Real", "QML", "R1", "Real controller workflow")
    app, engine, root = _root(controller)  # type: ignore[arg-type]
    return controller, app, engine, root


def _replace_field_text(root: QObject, field: QObject, text: str) -> None:
    field.forceActiveFocus()
    QTest.keyClick(root, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    for character in text:
        key = getattr(Qt.Key, f"Key_{character.upper()}")
        QTest.keyClick(root, key)


@pytest.mark.ui
def test_material_workflow_has_five_regions_and_accessible_file_actions() -> None:
    app, engine, root = _root(WorkflowController())

    for name in (
        "materialLibraryPane",
        "materialImportExportPane",
        "materialSourceCurveWorkspace",
        "materialValidationPane",
        "materialLifecyclePane",
        "downloadCsvTemplateButton",
        "downloadXlsxTemplateButton",
        "uploadTableButton",
        "exportRevisionButton",
        "reimportWorkbookButton",
        "importImageButton",
        "templateCsvDialog",
        "templateXlsxDialog",
        "tableUploadDialog",
        "revisionExportDialog",
        "workbookReimportDialog",
        "imageSourceDialog",
        "workspaceSeriesChoice",
    ):
        assert root.findChild(QObject, name) is not None, name
    names = []
    pending = [QAccessible.queryAccessibleInterface(root)]
    while pending:
        current = pending.pop(0)
        if current is None:
            continue
        names.append(current.text(QAccessible.Text.Name))
        pending.extend(current.child(index) for index in range(current.childCount()))
    for label in (
        "Download CSV template",
        "Download XLSX template",
        "Upload CSV or XLSX",
        "Export selected revision",
        "Reimport edited workbook",
        "Import PNG, JPEG, or PDF page",
    ):
        assert label in names
    assert app is not None
    assert engine.rootObjects()


@pytest.mark.ui
def test_all_file_dialogs_forward_controlled_urls_with_exact_semantics(
    tmp_path: Path,
) -> None:
    controller = WorkflowController()
    app, engine, root = _root(controller)
    page = root.findChild(QObject, "materialStudioPage")
    pdf_page = root.findChild(QObject, "pdfPageField")
    pdf_page.setProperty("value", 7)
    cases = [
        ("templateCsvDialog", "template.csv", ("downloadTemplate", "csv")),
        ("templateXlsxDialog", "template.xlsx", ("downloadTemplate", "xlsx")),
        ("tableUploadDialog", "source.csv", ("importTable",)),
        ("revisionExportDialog", "revision.xlsx", ("exportSelectedWorkbook",)),
        ("workbookReimportDialog", "edited.xlsx", ("importEditedWorkbook",)),
        ("imageSourceDialog", "source.pdf", ("importSourceImage",)),
    ]

    for dialog_name, filename, prefix in cases:
        dialog = root.findChild(QObject, dialog_name)
        path = tmp_path / filename
        if dialog_name in {
            "tableUploadDialog",
            "workbookReimportDialog",
            "imageSourceDialog",
        }:
            path.write_bytes(b"controlled input")
        url = QUrl.fromLocalFile(str(path)).toString()
        assert dialog.setProperty("selectedFile", QUrl(url))
        assert QMetaObject.invokeMethod(dialog, "accepted")
        app.processEvents()
        expected = (*prefix, url)
        if dialog_name == "imageSourceDialog":
            expected = (*expected, 7)
        assert controller.calls[-1] == expected

    assert page is not None
    assert engine.rootObjects()
@pytest.mark.ui
def test_curve_workspace_converts_display_clicks_and_forwards_numeric_edits() -> None:
    controller = WorkflowController()
    app, engine, root = _root(controller)
    source_view = root.findChild(QQuickItem, "materialSourceView")
    point_x = _accessible_object(root, "Point 2 canonical X value")
    point_y = _accessible_object(root, "Point 2 canonical Y value")
    apply_point = _accessible_object(root, "Apply point 2 numeric values")
    delete_point = _accessible_object(root, "Delete point 2")
    move_point = _accessible_object(root, "Move source point 2")

    assert source_view is not None
    assert point_x is not None
    assert point_y is not None
    assert apply_point is not None
    assert delete_point is not None
    assert move_point is not None
    _scroll_to_source_workspace(root, source_view)
    scale = float(source_view.property("sourceScale"))
    offset_x = float(source_view.property("sourceOffsetX"))
    offset_y = float(source_view.property("sourceOffsetY"))
    scene = source_view.mapToScene(QPointF(offset_x + 3.0 * scale, offset_y + 2.0 * scale))
    QTest.mouseClick(
        root,
        Qt.MouseButton.LeftButton,
        pos=QPoint(round(scene.x()), round(scene.y())),
    )
    app.processEvents()
    assert controller.calls[-1][0] == "addPixelPoint"
    assert controller.calls[-1][1:] == pytest.approx((3.0, 2.0), abs=0.02)

    move_interface = QAccessible.queryAccessibleInterface(move_point)
    assert move_interface is not None
    move_action = move_interface.actionInterface()
    assert move_action is not None
    move_action.doAction(QAccessibleActionInterface.setFocusAction())
    app.processEvents()
    QTest.keyClick(root, Qt.Key.Key_Right)
    app.processEvents()
    assert controller.calls[-1] == ("movePixelPoint", 1, 12.0, 1.0)

    point_x.setProperty("text", "200")
    assert QMetaObject.invokeMethod(point_x, "textEdited")
    point_y.setProperty("text", "0.3")
    assert QMetaObject.invokeMethod(point_y, "textEdited")
    _press(apply_point)
    delete_point = _accessible_object(root, "Delete point 2")
    _press(delete_point)
    assert controller.calls[-2:] == [
        ("setCanonicalPoint", "bh-25c", 1, 200.0, 0.3),
        ("deletePoint", 1),
    ]
    assert engine.rootObjects()


@pytest.mark.ui
def test_crop_and_every_axis_handle_support_mouse_drag_and_keyboard() -> None:
    controller = WorkflowController()
    app, engine, root = _root(controller)
    source_view = root.findChild(QQuickItem, "materialSourceView")
    scale = float(source_view.property("sourceScale"))
    _scroll_to_source_workspace(root, source_view)

    def handle(name: str) -> QQuickItem:
        item = root.findChild(QQuickItem, name)
        if item is None:
            accessible_names = {
                "xAxisAnchorA": "X axis anchor A",
                "xAxisAnchorB": "X axis anchor B",
                "yAxisAnchorA": "Y axis anchor A",
                "yAxisAnchorB": "Y axis anchor B",
            }
            item = _accessible_object(root, accessible_names[name])
        assert item is not None
        assert isinstance(item, QQuickItem)
        return item

    def drag(item: QQuickItem, dx: float, dy: float) -> None:
        center = item.mapToScene(QPointF(item.width() / 2, item.height() / 2))
        start = QPoint(round(center.x()), round(center.y()))
        finish = QPoint(round(center.x() + dx), round(center.y() + dy))
        QTest.mousePress(root, Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(root, finish, delay=40)
        QTest.mouseRelease(root, Qt.MouseButton.LeftButton, pos=finish)
        app.processEvents()

    def key(item: QQuickItem, value: Qt.Key) -> None:
        item.forceActiveFocus()
        app.processEvents()
        QTest.keyClick(root, value)
        app.processEvents()

    crop_bottom_right = handle("cropHandleBottomRight")
    drag(crop_bottom_right, -scale, -scale)
    assert controller.calls[-1] == ("setCrop", 0, 0, 11, 7)
    key(crop_bottom_right, Qt.Key.Key_Left)
    assert controller.calls[-1] == ("setCrop", 0, 0, 10, 7)

    crop_top_left = handle("cropHandleTopLeft")
    drag(crop_top_left, scale, scale)
    assert controller.calls[-1] == ("setCrop", 1, 1, 9, 6)
    key(crop_top_left, Qt.Key.Key_Down)
    assert controller.calls[-1] == ("setCrop", 1, 2, 9, 5)

    axis_cases = [
        ("xAxisAnchorA", scale, 0.0, Qt.Key.Key_Right, "setXAxis", 3.0),
        ("xAxisAnchorB", -scale, 0.0, Qt.Key.Key_Left, "setXAxis", 9.0),
        ("yAxisAnchorA", 0.0, -scale, Qt.Key.Key_Up, "setYAxis", 5.0),
        ("yAxisAnchorB", 0.0, scale, Qt.Key.Key_Down, "setYAxis", 3.0),
    ]
    for name, dx, dy, arrow, slot_name, expected_pixel in axis_cases:
        item = handle(name)
        drag(item, dx, dy)
        assert controller.calls[-1][0] == slot_name
        key(item, arrow)
        call = controller.calls[-1]
        assert call[0] == slot_name
        pixel_index = 2 if name.endswith("A") else 4
        assert call[pixel_index] == pytest.approx(expected_pixel, abs=0.05)

    assert source_view is not None
    assert engine.rootObjects()


@pytest.mark.ui
def test_lifecycle_requires_actor_and_explicit_multi_bh_selection() -> None:
    controller = WorkflowController()
    app, engine, root = _root(controller)
    reviewer = root.findChild(QObject, "reviewerField")
    approver = root.findChild(QObject, "approverField")
    review = root.findChild(QObject, "reviewDraftButton")
    approve = root.findChild(QObject, "approveRevisionButton")
    save = root.findChild(QObject, "saveDraftButton")
    bh_choice = root.findChild(QObject, "projectBhSeriesChoice")
    use = root.findChild(QObject, "useInProjectButton")

    assert all(
        item is not None
        for item in (reviewer, approver, review, approve, save, bh_choice, use)
    )
    assert save.property("enabled") is True
    assert review.property("enabled") is False
    assert approve.property("enabled") is False
    assert use.property("enabled") is False
    reviewer.setProperty("text", "reviewer@example.com")
    approver.setProperty("text", "approver@example.com")
    bh_choice.setProperty("currentIndex", 1)
    app.processEvents()
    assert review.property("enabled") is True
    assert approve.property("enabled") is True
    assert use.property("enabled") is True
    _press(review)
    _press(approve)
    _press(use)
    assert controller.calls[-3:] == [
        ("reviewDraft", "reviewer@example.com"),
        ("approveRevision", "approver@example.com"),
        ("useInProject", "bh-100c"),
    ]
    assert engine.rootObjects()


@pytest.mark.ui
def test_bh_choice_displays_exact_id_and_condition_context() -> None:
    controller = WorkflowController()
    app, engine, root = _root(controller)
    choice = root.findChild(QObject, "projectBhSeriesChoice")

    choice.setProperty("currentIndex", 0)
    app.processEvents()
    assert choice.property("currentText") == (
        "bh-25c — temperature 25 °C — DC bias 0 A/m"
    )

    choice.setProperty("currentIndex", 1)
    app.processEvents()
    assert choice.property("currentText") == (
        "bh-100c — temperature 100 °C — DC bias unspecified"
    )
    _press(root.findChild(QObject, "useInProjectButton"))
    assert controller.calls[-1] == ("useInProject", "bh-100c")
    assert engine.rootObjects()


@pytest.mark.ui
def test_lifecycle_displays_all_source_traceability_fields() -> None:
    controller = WorkflowController()
    app, engine, root = _root(controller)
    region = root.findChild(QObject, "materialTraceabilityRegion")
    details = root.findChild(QObject, "materialSourceTraceabilityDetails")

    assert region is not None
    assert details.property("text") == (
        "Source: manual.png\n"
        "URL: https://example.com/manual.png\n"
        "Page: 0\n"
        "Captured: 2026-07-19T09:00:00+00:00\n"
        "Description: Manual B-H graph\n"
        f"SHA-256: {'a' * 64}\n\n"
        "Source: catalog.xlsx\n"
        "URL: https://example.com/catalog.xlsx\n"
        "Page: unspecified\n"
        "Captured: 2026-07-19T09:30:00+00:00\n"
        "Description: Vendor material table\n"
        f"SHA-256: {'b' * 64}"
    )
    assert details.property("visible") is True
    assert app is not None
    assert engine.rootObjects()


@pytest.mark.ui
def test_blank_conditions_forward_nan_while_physical_zero_is_preserved() -> None:
    controller = WorkflowController()
    app, engine, root = _root(controller)
    frequency = root.findChild(QObject, "frequencyConditionField")
    temperature = root.findChild(QObject, "temperatureConditionField")
    dc_bias = root.findChild(QObject, "dcBiasConditionField")
    apply_metadata = root.findChild(QObject, "applySeriesMetadataButton")

    frequency.setProperty("text", "")
    temperature.setProperty("text", "0")
    dc_bias.setProperty("text", "")
    _press(apply_metadata)
    call = controller.calls[-1]
    assert call[:5] == ("setSeriesMetadata", "bh-25c", "bh-curve", "A/m", "T")
    assert math.isnan(call[5])
    assert call[6] == 0.0
    assert math.isnan(call[7])
    assert app is not None
    assert engine.rootObjects()


@pytest.mark.ui
def test_malformed_optional_condition_stays_visible_and_never_applies() -> None:
    controller = WorkflowController()
    app, engine, root = _root(controller)
    frequency = root.findChild(QObject, "frequencyConditionField")
    apply_metadata = root.findChild(QObject, "applySeriesMetadataButton")
    save = root.findChild(QObject, "saveDraftButton")
    error = root.findChild(QObject, "seriesMetadataInputError")
    frequency.forceActiveFocus()
    QTest.keyClick(root, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    for key, modifier in (
        (Qt.Key.Key_1, Qt.KeyboardModifier.NoModifier),
        (Qt.Key.Key_0, Qt.KeyboardModifier.NoModifier),
        (Qt.Key.Key_K, Qt.KeyboardModifier.NoModifier),
        (Qt.Key.Key_H, Qt.KeyboardModifier.ShiftModifier),
        (Qt.Key.Key_Z, Qt.KeyboardModifier.NoModifier),
    ):
        QTest.keyClick(root, key, modifier)
    app.processEvents()

    assert frequency.property("text") == "10khz"
    assert apply_metadata.property("enabled") is False
    assert save.property("enabled") is False
    assert error.property("visible") is True
    assert "valid number" in error.property("text")
    _press(apply_metadata)
    assert any(call[0] == "invalidateEditorInput" for call in controller.calls)
    assert not any(call[0] == "setSeriesMetadata" for call in controller.calls)
    assert app is not None
    assert engine.rootObjects()


@pytest.mark.ui
def test_pending_calibration_text_disables_stale_save() -> None:
    controller = WorkflowController()
    app, engine, root = _root(controller)
    crop_width = root.findChild(QObject, "cropWidthField")
    save = root.findChild(QObject, "saveDraftButton")

    crop_width.forceActiveFocus()
    QTest.keyClick(root, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    QTest.keyClick(root, Qt.Key.Key_X)
    app.processEvents()

    assert crop_width.property("text") == "x"
    assert controller.calls[-1][0] == "invalidateEditorInput"
    assert save.property("enabled") is False
    assert engine.rootObjects()


@pytest.mark.ui
def test_real_controller_preserves_malformed_metadata_across_sibling_edits() -> None:
    controller, app, engine, root = _real_image_root()
    frequency = root.findChild(QObject, "frequencyConditionField")
    _replace_field_text(root, frequency, "10khz")
    app.processEvents()
    before = controller.imageEditing
    revision_before = controller.selectedRevision

    crop = root.findChild(QQuickItem, "cropHandleBottomRight")
    x_axis = _accessible_object(root, "X axis anchor A")
    point = _accessible_object(root, "Move source point 1")
    for item, key in (
        (crop, Qt.Key.Key_Left),
        (x_axis, Qt.Key.Key_Right),
        (point, Qt.Key.Key_Right),
    ):
        item.forceActiveFocus()
        QTest.keyClick(root, key)
        app.processEvents()
        assert frequency.property("text") == "10khz"
        assert controller.imageEditing == before
        assert controller.selectedRevision == revision_before
        assert controller.canSave is False

    assert engine.rootObjects()


@pytest.mark.ui
def test_real_controller_preserves_malformed_calibration_across_sibling_edits() -> None:
    controller, app, engine, root = _real_image_root()
    crop_width = root.findChild(QObject, "cropWidthField")
    _replace_field_text(root, crop_width, "x")
    app.processEvents()
    before = controller.imageEditing
    revision_before = controller.selectedRevision

    x_axis = _accessible_object(root, "X axis anchor A")
    point = _accessible_object(root, "Move source point 1")
    for item, key in (
        (x_axis, Qt.Key.Key_Right),
        (point, Qt.Key.Key_Right),
    ):
        item.forceActiveFocus()
        QTest.keyClick(root, key)
        app.processEvents()
        assert crop_width.property("text") == "x"
        assert controller.imageEditing == before
        assert controller.selectedRevision == revision_before
        assert controller.canSave is False

    assert engine.rootObjects()


@pytest.mark.ui
def test_real_controller_resolves_invalid_groups_without_erasing_sibling_text() -> None:
    controller, app, engine, root = _real_image_root()
    crop_width = root.findChild(QObject, "cropWidthField")
    frequency = root.findChild(QObject, "frequencyConditionField")
    apply_metadata = root.findChild(QObject, "applySeriesMetadataButton")
    apply_crop = root.findChild(QObject, "applyCropButton")

    _replace_field_text(root, crop_width, "x")
    _replace_field_text(root, frequency, "10khz")
    app.processEvents()
    assert controller.canSave is False

    _replace_field_text(root, frequency, "10")
    _press(apply_metadata)
    app.processEvents()

    assert crop_width.property("text") == "x"
    assert frequency.property("text") == "10"
    assert controller.imageEditing["metadata"]["frequencyHz"] == 10.0
    assert controller.canSave is False
    controller.saveDraft()
    assert controller.dirty is True

    _replace_field_text(root, crop_width, "12")
    _press(apply_crop)
    app.processEvents()

    assert crop_width.property("text") == "12"
    assert controller.canSave is True
    assert engine.rootObjects()


@pytest.mark.ui
def test_source_only_editor_resolves_invalid_groups_without_erasing_sibling_text() -> None:
    controller = MaterialStudioController(
        InMemoryMaterialRepository(),
        now=lambda: "2026-07-19T10:00:00+00:00",
    )
    controller.importSourceImage(QUrl.fromLocalFile(str(_IMAGE)).toString(), 0)
    controller.setXAxis("linear", 1.0, 0.0, 11.0, 2.0)
    controller.setYAxis("linear", 7.0, 0.0, 1.0, 2.0)
    controller.addPixelPoint(1.0, 7.0)
    controller.addPixelPoint(11.0, 1.0)
    app, engine, root = _root(controller)  # type: ignore[arg-type]
    crop_width = root.findChild(QObject, "cropWidthField")
    frequency = root.findChild(QObject, "frequencyConditionField")

    _replace_field_text(root, crop_width, "x")
    _replace_field_text(root, frequency, "10khz")
    _replace_field_text(root, frequency, "10")
    _press(root.findChild(QObject, "applySeriesMetadataButton"))
    app.processEvents()

    assert crop_width.property("text") == "x"
    assert controller.canSave is False

    _replace_field_text(root, crop_width, "12")
    _press(root.findChild(QObject, "applyCropButton"))
    app.processEvents()

    assert crop_width.property("text") == "12"
    assert controller.canSave is False
    controller.createImageDraft("Source", "Only", "R1", "Sequential correction")
    assert controller.canSave is True
    assert engine.rootObjects()


@pytest.mark.ui
def test_controller_refresh_selects_new_material_and_revision_identities() -> None:
    repository = InMemoryMaterialRepository()
    controller = MaterialStudioController(
        repository,
        now=lambda: "2026-07-19T10:00:00+00:00",
    )

    def create_and_save(manufacturer: str, name: str, grade: str) -> None:
        controller.importSourceImage(QUrl.fromLocalFile(str(_IMAGE)).toString(), 0)
        controller.setXAxis("linear", 1.0, 0.0, 11.0, 2.0)
        controller.setYAxis("linear", 7.0, 0.0, 1.0, 2.0)
        controller.addPixelPoint(1.0, 7.0)
        controller.addPixelPoint(11.0, 1.0)
        controller.createImageDraft(manufacturer, name, grade, "Identity refresh")
        controller.saveDraft()

    create_and_save("Example", "Ferrite", "N87")
    app, engine, root = _root(controller)  # type: ignore[arg-type]
    material_list = root.findChild(QQuickItem, "materialList")
    revision_list = root.findChild(QQuickItem, "revisionList")
    assert material_list.property("currentIndex") == 0

    create_and_save("Zulu", "New", "Z9")
    app.processEvents()

    selected = controller.selectedRevision
    assert (selected["manufacturer"], selected["name"], selected["grade"]) == (
        "Zulu",
        "New",
        "Z9",
    )
    material = controller.materials[material_list.property("currentIndex")]
    revision = controller.revisions[revision_list.property("currentIndex")]
    assert (material["manufacturer"], material["name"], material["grade"]) == (
        "Zulu",
        "New",
        "Z9",
    )
    assert revision["revisionId"] == selected["revisionId"]
    assert engine.rootObjects()


@pytest.mark.ui
def test_imported_source_clears_authoritative_and_current_library_identities() -> None:
    controller = MaterialStudioController(
        InMemoryMaterialRepository(),
        now=lambda: "2026-07-19T10:00:00+00:00",
    )
    controller.importSourceImage(QUrl.fromLocalFile(str(_IMAGE)).toString(), 0)
    controller.setXAxis("linear", 1.0, 0.0, 11.0, 2.0)
    controller.setYAxis("linear", 7.0, 0.0, 1.0, 2.0)
    controller.addPixelPoint(1.0, 7.0)
    controller.addPixelPoint(11.0, 1.0)
    controller.createImageDraft("Example", "Ferrite", "N87", "Detach identity")
    controller.saveDraft()
    app, engine, root = _root(controller)  # type: ignore[arg-type]
    page = root.findChild(QObject, "materialStudioPage")
    material_list = root.findChild(QQuickItem, "materialList")
    revision_list = root.findChild(QQuickItem, "revisionList")
    assert material_list.property("currentIndex") == 0
    assert revision_list.property("currentIndex") == 0

    controller.importSourceImage(QUrl.fromLocalFile(str(_IMAGE)).toString(), 0)
    app.processEvents()

    assert controller.selectedMaterial == {}
    assert controller.selectedRevision == {}
    assert page.property("confirmedMaterialSelection").toVariant() == []
    assert page.property("confirmedRevisionSelection").toVariant() == []
    assert material_list.property("currentIndex") == -1
    assert revision_list.property("currentIndex") == -1
    assert engine.rootObjects()


@pytest.mark.ui
def test_crop_and_both_axis_anchor_controls_forward_explicit_values() -> None:
    controller = WorkflowController()
    app, engine, root = _root(controller)
    for name in ("cropHandleTopLeft", "cropHandleBottomRight"):
        assert root.findChild(QObject, name) is not None
    for label in (
        "X axis anchor A",
        "X axis anchor B",
        "Y axis anchor A",
        "Y axis anchor B",
    ):
        assert _accessible_object(root, label) is not None

    crop_left = _accessible_object(root, "Crop left in image pixels")
    crop_top = _accessible_object(root, "Crop top in image pixels")
    crop_width = _accessible_object(root, "Crop width in image pixels")
    crop_height = _accessible_object(root, "Crop height in image pixels")
    crop_apply = _accessible_object(root, "Apply crop")
    crop_left.setProperty("text", "1")
    crop_top.setProperty("text", "2")
    crop_width.setProperty("text", "9")
    crop_height.setProperty("text", "5")
    _press(crop_apply)

    for axis, values in (
        ("X", ("log", 1.0, 0.1, 11.0, 100.0)),
        ("Y", ("linear", 7.0, 0.0, 1.0, 2.0)),
    ):
        scale = root.findChild(QObject, f"{axis.lower()}AxisScaleField")
        pixel_a = root.findChild(QObject, f"{axis.lower()}AxisPixelAField")
        value_a = root.findChild(QObject, f"{axis.lower()}AxisValueAField")
        pixel_b = root.findChild(QObject, f"{axis.lower()}AxisPixelBField")
        value_b = root.findChild(QObject, f"{axis.lower()}AxisValueBField")
        apply_axis = root.findChild(QObject, f"apply{axis}AxisButton")
        assert all(
            item is not None
            for item in (scale, pixel_a, value_a, pixel_b, value_b, apply_axis)
        )
        scale.setProperty("currentIndex", 1 if values[0] == "log" else 0)
        for field, value in zip(
            (pixel_a, value_a, pixel_b, value_b), values[1:], strict=True
        ):
            field.setProperty("text", str(value))
        _press(apply_axis)

    assert controller.calls[-3:] == [
        ("setCrop", 1, 2, 9, 5),
        ("setXAxis", "log", 1.0, 0.1, 11.0, 100.0),
        ("setYAxis", "linear", 7.0, 0.0, 1.0, 2.0),
    ]
    assert app is not None
    assert engine.rootObjects()


@pytest.mark.ui
@pytest.mark.parametrize(
    ("values", "expected"),
    [
        (("-5", "-6", "99", "99"), ("setCrop", 0, 0, 12, 8)),
        (("99", "99", "0", "0"), ("setCrop", 11, 7, 1, 1)),
    ],
)
def test_crop_text_application_clamps_the_complete_source_rectangle(
    values: tuple[str, str, str, str],
    expected: tuple[object, ...],
) -> None:
    controller = WorkflowController()
    app, engine, root = _root(controller)
    fields = [
        root.findChild(QObject, name)
        for name in (
            "cropLeftField",
            "cropTopField",
            "cropWidthField",
            "cropHeightField",
        )
    ]
    assert all(field is not None for field in fields)
    for field, value in zip(fields, values, strict=True):
        field.setProperty("text", value)

    _press(root.findChild(QObject, "applyCropButton"))
    app.processEvents()

    assert controller.calls[-1] == expected
    assert engine.rootObjects()


@pytest.mark.ui
def test_dirty_navigation_save_discard_and_cancel_are_transactional() -> None:
    controller = WorkflowController()
    app, engine, root = _root(controller)
    steps = root.findChild(QObject, "guidedStepList")
    simulation = root.findChild(QObject, "simulationStep")
    core = root.findChild(QObject, "coreStep")
    dialog = root.findChild(QObject, "dirtyMaterialTransactionDialog")
    save = root.findChild(QObject, "dirtyMaterialTransactionSaveButton")
    discard = root.findChild(QObject, "dirtyMaterialTransactionDiscardButton")
    cancel = root.findChild(QObject, "dirtyMaterialTransactionCancelButton")

    controller.set_dirty(True)
    _press(simulation)
    app.processEvents()
    assert steps.property("currentIndex") == 2
    assert dialog.property("visible") is True
    _press(cancel)
    assert steps.property("currentIndex") == 2

    controller.save_succeeds = False
    _press(simulation)
    _press(save)
    app.processEvents()
    assert steps.property("currentIndex") == 2
    assert dialog.property("visible") is True

    controller.save_succeeds = True
    _press(save)
    app.processEvents()
    assert steps.property("currentIndex") == 3
    assert dialog.property("visible") is False

    steps.setProperty("currentIndex", 2)
    controller.set_dirty(True)
    _press(core)
    _press(discard)
    app.processEvents()
    assert steps.property("currentIndex") == 0
    assert controller.calls[-1] == ("discardChanges",)
    assert engine.rootObjects()


@pytest.mark.ui
@pytest.mark.parametrize(
    ("selection_name", "selection_call"),
    [
        (
            "Select material Other, Ferrite, N97",
            ("selectMaterial", "Other", "Ferrite", "N97"),
        ),
        ("Select revision 222222222222", ("selectRevision", "222222222222")),
    ],
)
def test_dirty_library_selection_save_discard_cancel_transaction(
    selection_name: str,
    selection_call: tuple[object, ...],
) -> None:
    controller = WorkflowController()
    app, engine, root = _root(controller)
    selection = (
        None
        if selection_name.startswith("Select revision")
        else _accessible_object(root, selection_name)
    )
    revision_list = root.findChild(QQuickItem, "revisionList")
    material_list = root.findChild(QQuickItem, "materialList")
    selection_list = revision_list if selection is None else material_list
    dialog = root.findChild(QObject, "dirtyMaterialTransactionDialog")
    save = root.findChild(QObject, "dirtyMaterialTransactionSaveButton")
    discard = root.findChild(QObject, "dirtyMaterialTransactionDiscardButton")
    cancel = root.findChild(QObject, "dirtyMaterialTransactionCancelButton")
    assert selection_list is not None
    assert selection_list.property("currentIndex") == 0

    def activate_selection() -> None:
        if selection is not None:
            _press(selection)
            return
        assert revision_list is not None
        revision_list.setProperty("currentIndex", 1)
        revision_list.forceActiveFocus()
        QTest.keyClick(root, Qt.Key.Key_Return)

    controller.set_dirty(True)
    activate_selection()
    app.processEvents()
    assert dialog.property("visible") is True
    assert selection_list.property("currentIndex") == 0
    assert selection_call not in controller.calls
    _press(cancel)
    assert dialog.property("visible") is False
    assert selection_list.property("currentIndex") == 0
    assert selection_call not in controller.calls

    controller.save_succeeds = False
    activate_selection()
    _press(save)
    app.processEvents()
    assert dialog.property("visible") is True
    assert selection_list.property("currentIndex") == 0
    assert selection_call not in controller.calls

    controller.save_succeeds = True
    _press(save)
    app.processEvents()
    assert dialog.property("visible") is False
    assert controller.calls[-1] == selection_call
    assert selection_list.property("currentIndex") == 1

    controller.set_dirty(True)
    activate_selection()
    _press(discard)
    app.processEvents()
    assert controller.calls[-2:] == [("discardChanges",), selection_call]
    assert dialog.property("visible") is False
    assert selection_list.property("currentIndex") == 1
    assert engine.rootObjects()


@pytest.mark.ui
@pytest.mark.parametrize("selection_kind", ["material", "revision"])
@pytest.mark.parametrize("selection_succeeds", [True, False])
def test_dirty_library_selection_resolves_identity_after_save_reorders_model(
    selection_kind: str,
    selection_succeeds: bool,
) -> None:
    controller = WorkflowController()
    controller._materials.append(  # noqa: SLF001 - controlled QML model fake
        {"manufacturer": "Third", "name": "Ferrite", "grade": "N49"}
    )
    controller._revisions.append(  # noqa: SLF001 - controlled QML model fake
        {
            "revisionId": "333333333333",
            "status": "reviewed",
            "createdAt": "2026-07-19T12:00:00+00:00",
            "reviewedBy": "reviewer@example.com",
            "approvedBy": "",
            "seriesCount": 1,
            "validationErrors": 0,
            "validationWarnings": 0,
            "isLatestApproved": False,
        }
    )
    controller.reorder_on_save = True
    controller.selection_succeeds = selection_succeeds
    app, engine, root = _root(controller)
    material_list = root.findChild(QQuickItem, "materialList")
    revision_list = root.findChild(QQuickItem, "revisionList")
    selection_list = material_list if selection_kind == "material" else revision_list
    assert selection_list is not None

    controller.set_dirty(True)
    selection_list.setProperty("currentIndex", 1)
    selection_list.forceActiveFocus()
    QTest.keyClick(root, Qt.Key.Key_Return)
    app.processEvents()
    _press(root.findChild(QObject, "dirtyMaterialTransactionSaveButton"))
    app.processEvents()

    current_index = selection_list.property("currentIndex")
    if selection_kind == "material":
        current = controller.materials[current_index]
        expected = (
            {"manufacturer": "Other", "name": "Ferrite", "grade": "N97"}
            if selection_succeeds
            else {"manufacturer": "Example", "name": "Ferrite", "grade": "N87"}
        )
    else:
        current = controller.revisions[current_index]
        expected = {
            "revisionId": "222222222222" if selection_succeeds else "111111111111"
        }
    assert all(current[key] == value for key, value in expected.items())
    assert root.findChild(QObject, "dirtyMaterialTransactionDialog").property("visible") is False
    assert engine.rootObjects()


@pytest.mark.ui
@pytest.mark.parametrize("selection_kind", ["material", "revision"])
@pytest.mark.parametrize("outcome", ["cancel", "failed-save", "save", "discard"])
def test_empty_confirmed_identity_dirty_transaction_restores_or_commits_selection(
    selection_kind: str,
    outcome: str,
) -> None:
    repository = FailingSaveMaterialRepository()
    controller = MaterialStudioController(
        repository,
        now=lambda: "2026-07-19T10:00:00+00:00",
    )

    def load_source() -> None:
        controller.importSourceImage(QUrl.fromLocalFile(str(_IMAGE)).toString(), 0)
        controller.setXAxis("linear", 1.0, 0.0, 11.0, 2.0)
        controller.setYAxis("linear", 7.0, 0.0, 1.0, 2.0)
        controller.addPixelPoint(1.0, 7.0)
        controller.addPixelPoint(11.0, 1.0)

    load_source()
    controller.createImageDraft("Example", "Ferrite", "N87", "Confirmed base")
    controller.saveDraft()
    confirmed_revision_id = str(controller.selectedRevision["revisionId"])
    app, engine, root = _root(controller)  # type: ignore[arg-type]

    load_source()
    if selection_kind == "revision":
        controller.setSeriesMetadata(
            "bh-manual",
            "bh-curve",
            "A/m",
            "T",
            123.0,
            float("nan"),
            float("nan"),
        )
        controller.createImageDraft("Example", "Ferrite", "N87", "New revision")
    else:
        controller.createImageDraft("Zulu", "New", "Z9", "New material")
    app.processEvents()

    material_list = root.findChild(QQuickItem, "materialList")
    revision_list = root.findChild(QQuickItem, "revisionList")
    selection_list = material_list if selection_kind == "material" else revision_list
    assert selection_list.property("currentIndex") == -1
    selection_list.setProperty("currentIndex", 0)
    selection_list.forceActiveFocus()
    QTest.keyClick(root, Qt.Key.Key_Return)
    app.processEvents()

    dialog = root.findChild(QObject, "dirtyMaterialTransactionDialog")
    assert dialog.property("visible") is True
    if outcome == "cancel":
        _press(root.findChild(QObject, "dirtyMaterialTransactionCancelButton"))
    elif outcome == "failed-save":
        repository.fail_save = True
        _press(root.findChild(QObject, "dirtyMaterialTransactionSaveButton"))
    elif outcome == "save":
        _press(root.findChild(QObject, "dirtyMaterialTransactionSaveButton"))
    else:
        _press(root.findChild(QObject, "dirtyMaterialTransactionDiscardButton"))
    app.processEvents()

    if outcome in {"cancel", "failed-save"}:
        assert selection_list.property("currentIndex") == -1
        assert controller.dirty is True
        assert dialog.property("visible") is (outcome == "failed-save")
    else:
        assert selection_list.property("currentIndex") >= 0
        assert controller.dirty is False
        assert dialog.property("visible") is False
        if selection_kind == "material":
            material = controller.materials[selection_list.property("currentIndex")]
            assert (material["manufacturer"], material["name"], material["grade"]) == (
                "Example",
                "Ferrite",
                "N87",
            )
        else:
            revision = controller.revisions[selection_list.property("currentIndex")]
            assert revision["revisionId"] == confirmed_revision_id
    assert engine.rootObjects()


@pytest.mark.ui
@pytest.mark.parametrize(
    ("dialog_name", "expected_call"),
    [
        ("tableUploadDialog", "importTable"),
        ("workbookReimportDialog", "importEditedWorkbook"),
        ("imageSourceDialog", "importSourceImage"),
    ],
)
def test_every_destructive_import_uses_shared_dirty_transaction(
    tmp_path: Path,
    dialog_name: str,
    expected_call: str,
) -> None:
    controller = WorkflowController()
    app, engine, root = _root(controller)
    source = tmp_path / ("source.pdf" if dialog_name == "imageSourceDialog" else "source.xlsx")
    source.write_bytes(b"controlled")
    dialog = root.findChild(QObject, dialog_name)
    transaction = root.findChild(QObject, "dirtyMaterialTransactionDialog")
    save = root.findChild(QObject, "dirtyMaterialTransactionSaveButton")
    discard = root.findChild(QObject, "dirtyMaterialTransactionDiscardButton")
    cancel = root.findChild(QObject, "dirtyMaterialTransactionCancelButton")
    assert dialog.setProperty("selectedFile", QUrl.fromLocalFile(str(source)))

    controller.set_dirty(True)
    assert QMetaObject.invokeMethod(dialog, "accepted")
    app.processEvents()
    assert transaction.property("visible") is True
    assert not any(call[0] == expected_call for call in controller.calls)
    _press(cancel)
    assert transaction.property("visible") is False
    assert controller.dirty is True

    assert QMetaObject.invokeMethod(dialog, "accepted")
    controller.save_succeeds = False
    _press(save)
    app.processEvents()
    assert transaction.property("visible") is True
    assert not any(call[0] == expected_call for call in controller.calls)

    controller.save_succeeds = True
    _press(save)
    app.processEvents()
    assert transaction.property("visible") is False
    assert controller.calls[-1][0] == expected_call

    controller.set_dirty(True)
    assert QMetaObject.invokeMethod(dialog, "accepted")
    _press(discard)
    app.processEvents()
    assert controller.calls[-2][0] == "discardChanges"
    assert controller.calls[-1][0] == expected_call
    assert engine.rootObjects()


@pytest.mark.ui
def test_application_close_is_intercepted_by_shared_dirty_transaction() -> None:
    controller = WorkflowController()
    app, engine, root = _root(controller)
    transaction = root.findChild(QObject, "dirtyMaterialTransactionDialog")
    cancel = root.findChild(QObject, "dirtyMaterialTransactionCancelButton")
    discard = root.findChild(QObject, "dirtyMaterialTransactionDiscardButton")
    controller.set_dirty(True)

    root.close()
    app.processEvents()
    assert root.property("visible") is True
    assert transaction.property("visible") is True
    _press(cancel)
    assert root.property("visible") is True

    root.close()
    app.processEvents()
    _press(discard)
    app.processEvents()
    assert controller.calls[-1] == ("discardChanges",)
    assert root.property("visible") is False
    assert engine.rootObjects()


@pytest.mark.ui
def test_canonical_point_fields_own_pending_invalid_text_until_successful_apply() -> None:
    controller = WorkflowController()
    app, engine, root = _root(controller)
    x_field = _accessible_object(root, "Point 1 canonical X value")
    y_field = _accessible_object(root, "Point 1 canonical Y value")
    apply = _accessible_object(root, "Apply point 1 numeric values")
    save = root.findChild(QObject, "saveDraftButton")
    x_field.forceActiveFocus()
    QTest.keyClick(root, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    QTest.keyClick(root, Qt.Key.Key_Backspace)
    app.processEvents()

    assert x_field.property("text") == ""
    assert apply.property("enabled") is False
    assert save.property("enabled") is False
    assert any(call[0] == "invalidateEditorInput" for call in controller.calls)
    controller.sourceChanged.emit()
    app.processEvents()
    assert x_field.property("text") == ""

    x_field.setProperty("text", "12.5")
    assert QMetaObject.invokeMethod(x_field, "textEdited")
    y_field.setProperty("text", "0.15")
    assert QMetaObject.invokeMethod(y_field, "textEdited")
    app.processEvents()
    assert apply.property("enabled") is True
    _press(apply)
    app.processEvents()
    assert controller.calls[-1] == ("setCanonicalPoint", "bh-25c", 0, 12.5, 0.15)
    assert save.property("enabled") is True
    assert engine.rootObjects()


@pytest.mark.ui
def test_series_management_controls_forward_explicit_values_and_points() -> None:
    controller = WorkflowController()
    app, engine, root = _root(controller)
    new_id = root.findChild(QObject, "newSeriesIdField")
    new_points = root.findChild(QObject, "newSeriesPointsField")
    new_id.setProperty("text", "loss-extra")
    new_points.setProperty("text", "0.1,1000\n0.2,4000")

    _press(root.findChild(QObject, "addTableSeriesButton"))
    call = controller.calls[-1]
    assert call[0:5] == ("addTableSeries", "loss-extra", "bh-curve", "A/m", "T")
    assert call[-1] == [{"x": 0.1, "y": 1000}, {"x": 0.2, "y": 4000}]

    new_id.setProperty("text", "bh-image-extra")
    _press(root.findChild(QObject, "addImageSeriesButton"))
    assert controller.calls[-1][0:5] == (
        "addImageSeries",
        "bh-image-extra",
        "bh-curve",
        "A/m",
        "T",
    )
    _press(root.findChild(QObject, "removeSeriesButton"))
    assert controller.calls[-1] == ("removeSeries", "bh-25c")
    assert engine.rootObjects()


@pytest.mark.ui
def test_source_current_comparison_and_fit_series_are_visible_and_accessible() -> None:
    controller = WorkflowController()
    app, engine, root = _root(controller)
    source = root.findChild(QObject, "sourcePointComparison")
    current = root.findChild(QObject, "currentPointComparison")
    fit_sources = root.findChild(QObject, "fitLossSeriesIds")

    assert "Source points" in source.property("text")
    assert "0, 0" in source.property("text")
    assert "Current points" in current.property("text")
    assert "100, 0.2" in current.property("text")
    assert fit_sources.property("text") == (
        "Loss series used by fit: loss-100khz, loss-200khz"
    )
    assert source.property("activeFocusOnTab") is True
    assert current.property("activeFocusOnTab") is True
    assert app is not None
    assert engine.rootObjects()


def _saved_table_controller_for_pending_point_test() -> MaterialStudioController:
    repository = InMemoryMaterialRepository()
    template = material_import_template("csv")
    imported = import_material_file_as_draft(
        template.filename,
        template.data,
        created_at="2026-07-19T10:00:00+00:00",
    )
    repository.save(imported.record, dict(imported.source_files))
    controller = MaterialStudioController(repository)
    controller.selectMaterial(
        imported.record.ref.manufacturer,
        imported.record.ref.name,
        imported.record.ref.grade,
    )
    controller.selectRevision(imported.record.revision_id)
    return controller


@pytest.mark.ui
def test_discard_clears_pending_canonical_text_from_real_qml() -> None:
    controller = _saved_table_controller_for_pending_point_test()
    app, engine, root = _root(controller)  # type: ignore[arg-type]
    field = _accessible_object(root, "Point 1 canonical X value")
    original = field.property("text")
    field.setProperty("text", "999")
    assert QMetaObject.invokeMethod(field, "textEdited")
    app.processEvents()
    assert controller.dirty is True

    assert controller.discardChanges() is True
    app.processEvents()
    field = _accessible_object(root, "Point 1 canonical X value")
    assert controller.dirty is False
    assert field.property("text") == original
    assert engine.rootObjects()


@pytest.mark.ui
def test_revision_replacement_never_reuses_same_key_pending_point_text() -> None:
    repository = InMemoryMaterialRepository()
    template = material_import_template("csv")
    first = import_material_file_as_draft(
        template.filename,
        template.data,
        created_at="2026-07-19T10:00:00+00:00",
    )
    second = import_material_file_as_draft(
        template.filename,
        template.data.replace(b"0.16", b"0.19"),
        created_at="2026-07-19T11:00:00+00:00",
    )
    repository.save(first.record, dict(first.source_files))
    repository.save(second.record, dict(second.source_files))
    controller = MaterialStudioController(repository)
    controller.selectMaterial(
        first.record.ref.manufacturer,
        first.record.ref.name,
        first.record.ref.grade,
    )
    controller.selectRevision(first.record.revision_id)
    app, engine, root = _root(controller)  # type: ignore[arg-type]
    field = _accessible_object(root, "Point 1 canonical X value")
    field.setProperty("text", "999")
    assert QMetaObject.invokeMethod(field, "textEdited")

    assert controller.discardChanges() is True
    assert controller.selectRevision(second.record.revision_id) is True
    app.processEvents()
    field = _accessible_object(root, "Point 1 canonical X value")
    assert float(field.property("text")) == controller.points[0]["x"]
    assert field.property("text") != "999"
    assert engine.rootObjects()


@pytest.mark.ui
def test_failed_revision_prepare_keeps_qml_buffer_until_successful_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = InMemoryMaterialRepository()
    template = material_import_template("csv")
    first = import_material_file_as_draft(
        template.filename,
        template.data,
        created_at="2026-07-19T10:00:00+00:00",
    )
    second = import_material_file_as_draft(
        template.filename,
        template.data.replace(b"0.16", b"0.19"),
        created_at="2026-07-19T11:00:00+00:00",
    )
    repository.save(first.record, dict(first.source_files))
    repository.save(second.record, dict(second.source_files))
    controller = MaterialStudioController(repository)
    ref = first.record.ref
    controller.selectMaterial(ref.manufacturer, ref.name, ref.grade)
    assert controller.selectRevision(first.record.revision_id) is True
    app, engine, root = _root(controller)  # type: ignore[arg-type]
    editor = root.findChild(QObject, "materialCurveEditor")
    editor.setProperty(
        "pendingCanonicalPoints",
        {"bh-25c:0": {"x": "999", "y": "0"}},
    )
    app.processEvents()
    field = _accessible_object(root, "Point 1 canonical X value")
    assert field.property("text") == "999"
    resets: list[None] = []
    controller.editorReset.connect(lambda: resets.append(None))
    real_list = repository.list_materials
    monkeypatch.setattr(
        repository,
        "list_materials",
        lambda: (_ for _ in ()).throw(ValueError("library failed")),
    )

    assert controller.selectRevision(second.record.revision_id) is False
    app.processEvents()
    assert resets == []
    assert _accessible_object(root, "Point 1 canonical X value").property("text") == "999"

    monkeypatch.setattr(repository, "list_materials", real_list)
    assert controller.selectRevision(second.record.revision_id) is True
    app.processEvents()
    assert resets == [None]
    field = _accessible_object(root, "Point 1 canonical X value")
    assert field.property("text") != "999"
    assert editor.property("pendingCanonicalPoints").toVariant() == {}
    assert engine.rootObjects()
