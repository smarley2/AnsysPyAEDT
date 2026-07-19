import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QSG_RHI_BACKEND", "software")

pytest.importorskip("PySide6")

from PySide6.QtCore import Property, QObject, QPointF, Qt, Signal, Slot  # noqa: E402
from PySide6.QtGui import QAccessible, QAccessibleActionInterface, QGuiApplication  # noqa: E402
from PySide6.QtQuick import QQuickItem  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from inductor_designer.ui.main import create_engine  # noqa: E402


class RecordingMaterialStudioController(QObject):
    libraryChanged = Signal()
    selectionChanged = Signal()
    sourceChanged = Signal()
    editorReset = Signal()
    dirtyChanged = Signal()
    statusMessageChanged = Signal()

    def __init__(
        self,
        *,
        materials: list[dict[str, object]] | None = None,
        revisions: list[dict[str, object]] | None = None,
        issues: list[dict[str, object]] | None = None,
        fit: dict[str, object] | None = None,
        status_message: str = "",
    ) -> None:
        super().__init__()
        self._materials = materials or []
        self._revisions = revisions or []
        self._issues = issues or []
        self._fit = fit or {}
        self._status_message = status_message
        self._selected_material = self._materials[0] if self._materials else {}
        self._selected_revision = (
            {"revisionId": self._revisions[0]["revisionId"]}
            if self._revisions
            else {}
        )
        self.selected_materials: list[tuple[str, str, str]] = []
        self.selected_revisions: list[str] = []

    materials = Property(list, lambda self: self._materials, notify=libraryChanged)
    revisions = Property(list, lambda self: self._revisions, notify=libraryChanged)
    selectedMaterial = Property(
        dict, lambda self: self._selected_material, notify=selectionChanged
    )
    selectedRevision = Property(
        dict, lambda self: self._selected_revision, notify=selectionChanged
    )
    series = Property(list, lambda self: [], notify=selectionChanged)
    points = Property(list, lambda self: [], notify=selectionChanged)
    sourcePoints = Property(list, lambda self: [], notify=selectionChanged)
    sourceComparisonAvailable = Property(
        bool, lambda self: False, notify=selectionChanged
    )
    issues = Property(list, lambda self: self._issues, notify=selectionChanged)
    fit = Property(dict, lambda self: self._fit, notify=selectionChanged)
    source = Property(dict, lambda self: {}, notify=sourceChanged)
    imageEditing = Property(
        dict,
        lambda self: {
            "crop": {},
            "xAxis": {},
            "yAxis": {},
            "pixelPoints": [],
            "metadata": {},
        },
        notify=sourceChanged,
    )
    dirty = Property(bool, lambda self: False, notify=dirtyChanged)
    canSave = Property(bool, lambda self: False, notify=selectionChanged)
    canReview = Property(bool, lambda self: False, notify=selectionChanged)
    canApprove = Property(bool, lambda self: False, notify=selectionChanged)
    canUseInProject = Property(bool, lambda self: False, notify=selectionChanged)
    statusMessage = Property(
        str, lambda self: self._status_message, notify=statusMessageChanged
    )

    @Slot(str, str, str, result=bool)
    def selectMaterial(self, manufacturer: str, name: str, grade: str) -> bool:
        self.selected_materials.append((manufacturer, name, grade))
        self._selected_material = {
            "manufacturer": manufacturer,
            "name": name,
            "grade": grade,
        }
        self.selectionChanged.emit()
        return True

    @Slot(str, result=bool)
    def selectRevision(self, revision_id: str) -> bool:
        self.selected_revisions.append(revision_id)
        self._selected_revision = {"revisionId": revision_id}
        self.selectionChanged.emit()
        return True

    @Slot(result=bool)
    def discardChanges(self) -> bool:
        return True


def _accessible_interfaces(root: QObject) -> list[object]:
    interface = QAccessible.queryAccessibleInterface(root)
    assert interface is not None
    found: list[object] = []
    pending = [interface]
    while pending:
        current = pending.pop(0)
        found.append(current)
        pending.extend(
            child
            for index in range(current.childCount())
            if (child := current.child(index)) is not None
        )
    return found


def _accessible_name(interface: object) -> str:
    return interface.text(QAccessible.Text.Name)


def _overflow_library_values() -> tuple[
    list[dict[str, object]], list[dict[str, object]]
]:
    materials = [
        {
            "manufacturer": "ACME",
            "name": f"Material {index:02d}",
            "grade": f"G{index:02d}",
        }
        for index in range(20)
    ]
    revisions = [
        {
            "revisionId": f"rev-{index:02d}",
            "status": "approved" if index == 19 else "draft",
            "createdAt": f"2026-07-19T{index:02d}:00:00+00:00",
            "reviewedBy": "Ada" if index == 19 else "",
            "approvedBy": "Grace" if index == 19 else "",
            "seriesCount": 1,
            "validationErrors": 0,
            "validationWarnings": 0,
            "isLatestApproved": index == 19,
        }
        for index in range(20)
    ]
    return materials, revisions


@pytest.mark.ui
def test_guided_studio_qml_loads() -> None:
    app = QGuiApplication.instance() or QGuiApplication([])
    engine = create_engine()

    assert app is not None
    assert len(engine.rootObjects()) == 1


@pytest.mark.ui
def test_guided_studio_navigates_to_one_embedded_materials_page() -> None:
    app = QGuiApplication.instance() or QGuiApplication([])
    controller = RecordingMaterialStudioController()
    engine = create_engine(material_studio_controller=controller)
    root = engine.rootObjects()[0]
    guided_steps = root.findChild(QObject, "guidedStepList")
    materials_step = root.findChild(QObject, "materialsStep")
    materials_page = root.findChild(QObject, "materialStudioPage")
    material_library = root.findChild(QObject, "materialLibraryPane")
    preview = root.findChild(QObject, "previewPane")
    pages = [
        root.findChild(QObject, name)
        for name in (
            "corePage",
            "windingsPage",
            "materialStudioPage",
            "simulationPage",
            "reviewPage",
        )
    ]

    assert app is not None
    assert len(engine.rootObjects()) == 1
    assert engine.rootContext().contextProperty("materialStudioController") is controller
    assert guided_steps is not None
    assert materials_step is not None
    assert materials_page is not None
    assert material_library is not None
    assert preview is not None
    assert all(page is not None for page in pages)
    assert guided_steps.property("count") == 5
    assert guided_steps.property("currentIndex") == 0
    assert materials_page.property("visible") is False
    assert preview.property("visible") is True

    for current_index in range(5):
        guided_steps.setProperty("currentIndex", current_index)
        app.processEvents()
        assert [page.property("visible") for page in pages] == [
            index == current_index for index in range(5)
        ]
        assert preview.property("visible") is (current_index != 2)


@pytest.mark.ui
def test_guided_steps_support_keyboard_navigation() -> None:
    app = QGuiApplication.instance() or QGuiApplication([])
    controller = RecordingMaterialStudioController()
    engine = create_engine(material_studio_controller=controller)
    root = engine.rootObjects()[0]
    guided_steps = root.findChild(QObject, "guidedStepList")
    materials_page = root.findChild(QObject, "materialStudioPage")

    assert guided_steps is not None
    assert materials_page is not None
    guided_steps.forceActiveFocus()
    QTest.keyClick(root, Qt.Key.Key_Down)
    QTest.keyClick(root, Qt.Key.Key_Down)
    app.processEvents()

    assert guided_steps.property("currentIndex") == 2
    assert materials_page.property("visible") is True


@pytest.mark.ui
def test_material_library_renders_every_revision_and_only_actions_select() -> None:
    app = QGuiApplication.instance() or QGuiApplication([])
    revisions = [
        {
            "revisionId": "rev-draft",
            "status": "draft",
            "createdAt": "2026-07-19T10:00:00+00:00",
            "reviewedBy": "",
            "approvedBy": "",
            "seriesCount": 1,
            "validationErrors": 2,
            "validationWarnings": 1,
            "isLatestApproved": False,
        },
        {
            "revisionId": "rev-reviewed",
            "status": "reviewed",
            "createdAt": "2026-07-18T09:00:00+00:00",
            "reviewedBy": "Ada",
            "approvedBy": "",
            "seriesCount": 2,
            "validationErrors": 0,
            "validationWarnings": 3,
            "isLatestApproved": False,
        },
        {
            "revisionId": "rev-approved",
            "status": "approved",
            "createdAt": "2026-07-17T08:00:00+00:00",
            "reviewedBy": "Ada",
            "approvedBy": "Grace",
            "seriesCount": 3,
            "validationErrors": 0,
            "validationWarnings": 0,
            "isLatestApproved": True,
        },
    ]
    controller = RecordingMaterialStudioController(
        materials=[
            {"manufacturer": "ACME", "name": "Ferrite", "grade": "N87"}
        ],
        revisions=revisions,
    )
    engine = create_engine(material_studio_controller=controller)
    root = engine.rootObjects()[0]
    guided_steps = root.findChild(QObject, "guidedStepList")
    revision_list = root.findChild(QObject, "revisionList")
    material_list = root.findChild(QObject, "materialList")

    assert guided_steps is not None
    assert revision_list is not None
    assert material_list is not None
    guided_steps.setProperty("currentIndex", 2)
    app.processEvents()

    assert revision_list.property("count") == 3
    assert material_list.property("count") == 1
    names: list[str] = []
    for index in range(len(revisions)):
        revision_list.setProperty("currentIndex", index)
        app.processEvents()
        names.extend(_accessible_name(item) for item in _accessible_interfaces(root))
    interfaces = _accessible_interfaces(root)
    for revision in revisions:
        details = next(name for name in names if revision["revisionId"] in name)
        assert revision["status"].title() in details
        assert revision["createdAt"] in details
        assert str(revision["seriesCount"]) in details
        assert str(revision["validationErrors"]) in details
        assert str(revision["validationWarnings"]) in details
        if revision["reviewedBy"]:
            assert revision["reviewedBy"] in details
        if revision["approvedBy"]:
            assert revision["approvedBy"] in details
    assert any("Reviewer: Not reviewed" in name for name in names)
    assert any("Approver: Not approved" in name for name in names)

    material_action = next(
        interface
        for interface in interfaces
        if _accessible_name(interface) == "Select material ACME, Ferrite, N87"
    )
    assert material_action.state().focusable
    material_action.actionInterface().doAction(QAccessibleActionInterface.pressAction())
    app.processEvents()
    assert controller.selected_materials == [("ACME", "Ferrite", "N87")]

    suggestion = [
        interface
        for interface in interfaces
        if _accessible_name(interface) == "Suggested latest approved"
    ]
    assert len(suggestion) == 1
    suggestion_action = suggestion[0].actionInterface()
    assert suggestion_action is None or QAccessibleActionInterface.pressAction() not in (
        suggestion_action.actionNames()
    )
    assert controller.selected_revisions == []

    assert all(f"Select revision {item['revisionId']}" in names for item in revisions)
    assert all(
        item.state().focusable
        for item in interfaces
        if _accessible_name(item).startswith("Select revision ")
    )
    revision_list.setProperty("currentIndex", 0)
    app.processEvents()
    material_list.forceActiveFocus()
    app.processEvents()
    QTest.keyClick(root, Qt.Key.Key_Tab)
    app.processEvents()
    assert revision_list.property("activeFocus") is True
    QTest.keyClick(root, Qt.Key.Key_Return)
    app.processEvents()
    assert controller.selected_revisions == ["rev-draft"]

    revision_list.setProperty("currentIndex", 2)
    app.processEvents()
    approved_action = next(
        item
        for item in _accessible_interfaces(root)
        if _accessible_name(item) == "Select revision rev-approved"
    )
    action = approved_action.actionInterface()
    assert action is not None
    action.doAction(QAccessibleActionInterface.pressAction())
    app.processEvents()
    assert revision_list.property("currentIndex") == 2
    assert controller.selected_revisions == ["rev-draft", "rev-approved"]


@pytest.mark.ui
def test_material_list_keyboard_reaches_and_activates_overflow_row_once() -> None:
    app = QGuiApplication.instance() or QGuiApplication([])
    materials, revisions = _overflow_library_values()
    controller = RecordingMaterialStudioController(
        materials=materials,
        revisions=revisions,
    )
    engine = create_engine(material_studio_controller=controller)
    root = engine.rootObjects()[0]
    guided_steps = root.findChild(QObject, "guidedStepList")
    material_list = root.findChild(QObject, "materialList")
    revision_list = root.findChild(QObject, "revisionList")

    assert guided_steps is not None
    assert material_list is not None
    assert revision_list is not None
    guided_steps.setProperty("currentIndex", 2)
    app.processEvents()

    initial_names = [
        _accessible_name(item) for item in _accessible_interfaces(root)
    ]
    realized_actions = [
        name for name in initial_names if name.startswith("Select material ")
    ]
    assert 0 < len(realized_actions) < len(materials)
    assert material_list.property("activeFocusOnTab") is True
    assert material_list.property("currentIndex") == 0
    material_interface = QAccessible.queryAccessibleInterface(material_list)
    assert material_interface is not None
    assert _accessible_name(material_interface) == "Material library"
    assert material_interface.state().focusable

    material_list.forceActiveFocus()
    app.processEvents()
    QTest.keyClick(root, Qt.Key.Key_Tab)
    app.processEvents()
    assert revision_list.property("activeFocus") is True
    QTest.keyClick(
        root,
        Qt.Key.Key_Tab,
        Qt.KeyboardModifier.ShiftModifier,
    )
    app.processEvents()
    assert material_list.property("activeFocus") is True

    material_list.setProperty("currentIndex", -1)
    QTest.keyClick(root, Qt.Key.Key_Down)
    app.processEvents()
    assert material_list.property("currentIndex") == 0

    for _ in range(25):
        QTest.keyClick(root, Qt.Key.Key_Down)
    app.processEvents()

    assert material_list.property("currentIndex") == 19
    assert material_list.property("contentY") > 0
    assert controller.selected_materials == []
    interfaces = _accessible_interfaces(root)
    last_action = next(
        item
        for item in interfaces
        if _accessible_name(item) == "Select material ACME, Material 19, G19"
    )
    assert "Current material" in last_action.text(QAccessible.Text.Description)

    QTest.keyClick(root, Qt.Key.Key_Space)
    app.processEvents()
    assert controller.selected_materials == [("ACME", "Material 19", "G19")]
    QTest.keyClick(root, Qt.Key.Key_Down)
    app.processEvents()
    assert material_list.property("currentIndex") == 19
    assert controller.selected_materials == [("ACME", "Material 19", "G19")]


@pytest.mark.ui
def test_revision_list_keyboard_reaches_and_activates_overflow_row_once() -> None:
    app = QGuiApplication.instance() or QGuiApplication([])
    materials, revisions = _overflow_library_values()
    controller = RecordingMaterialStudioController(
        materials=materials,
        revisions=revisions,
    )
    engine = create_engine(material_studio_controller=controller)
    root = engine.rootObjects()[0]
    guided_steps = root.findChild(QObject, "guidedStepList")
    revision_list = root.findChild(QObject, "revisionList")

    assert guided_steps is not None
    assert revision_list is not None
    guided_steps.setProperty("currentIndex", 2)
    app.processEvents()

    initial_names = [
        _accessible_name(item) for item in _accessible_interfaces(root)
    ]
    realized_actions = [
        name for name in initial_names if name.startswith("Select revision ")
    ]
    assert 0 < len(realized_actions) < len(revisions)
    assert revision_list.property("activeFocusOnTab") is True
    assert revision_list.property("currentIndex") == 0
    revision_interface = QAccessible.queryAccessibleInterface(revision_list)
    assert revision_interface is not None
    assert _accessible_name(revision_interface) == "Material revisions"
    assert revision_interface.state().focusable

    revision_list.forceActiveFocus()
    for _ in range(25):
        QTest.keyClick(root, Qt.Key.Key_Down)
    app.processEvents()

    assert revision_list.property("currentIndex") == 19
    assert revision_list.property("contentY") > 0
    assert controller.selected_revisions == []
    names = [_accessible_name(item) for item in _accessible_interfaces(root)]
    assert names.count("Current revision") == 1
    assert "Select revision rev-19" in names

    QTest.keyClick(root, Qt.Key.Key_Return)
    app.processEvents()
    assert controller.selected_revisions == ["rev-19"]
    for _ in range(25):
        QTest.keyClick(root, Qt.Key.Key_Up)
    app.processEvents()
    assert revision_list.property("currentIndex") == 0
    assert controller.selected_revisions == ["rev-19"]
    QTest.keyClick(root, Qt.Key.Key_Enter)
    app.processEvents()
    assert controller.selected_revisions == ["rev-19", "rev-00"]


@pytest.mark.ui
def test_material_validation_groups_severity_and_preserves_display_values() -> None:
    app = QGuiApplication.instance() or QGuiApplication([])
    controller = RecordingMaterialStudioController(
        issues=[
            {"code": "warn", "severity": "warning", "message": "Check range"},
            {"code": "error", "severity": "error", "message": "Missing source"},
            {"code": "info", "severity": "info", "message": "Fit available"},
        ],
        fit={
            "k": "0.0000123456789",
            "alpha": "1.23456789",
            "beta": "2.34567891",
            "rmsRelativeResidual": "0.0123456789",
            "maxRelativeResidual": "0.0987654321",
        },
        status_message="Library ready",
    )
    engine = create_engine(material_studio_controller=controller)
    root = engine.rootObjects()[0]
    guided_steps = root.findChild(QObject, "guidedStepList")
    issue_list = root.findChild(QObject, "validationIssueList")
    status_text = root.findChild(QObject, "materialStatusText")

    assert guided_steps is not None
    assert issue_list is not None
    assert status_text is not None
    guided_steps.setProperty("currentIndex", 2)
    app.processEvents()

    assert issue_list.property("count") == 3
    names = [_accessible_name(item) for item in _accessible_interfaces(root)]
    assert names.index("Error") < names.index("Warning") < names.index("Info")
    assert "Missing source" in names
    assert "Check range" in names
    assert "Fit available" in names
    for value in controller._fit.values():
        assert any(value in name for name in names)
    assert status_text.property("text") == "Library ready"
    assert any("Library ready" in name for name in names)


@pytest.mark.ui
def test_material_studio_reflows_panes_for_compact_and_wide_windows() -> None:
    app = QGuiApplication.instance() or QGuiApplication([])
    controller = RecordingMaterialStudioController()
    engine = create_engine(material_studio_controller=controller)
    root = engine.rootObjects()[0]
    guided_steps = root.findChild(QObject, "guidedStepList")
    material_page = root.findChild(QObject, "materialStudioPage")
    library_pane = root.findChild(QObject, "materialLibraryPane")
    import_pane = root.findChild(QObject, "materialImportExportPane")
    lifecycle_pane = root.findChild(QObject, "materialLifecyclePane")
    workspace_pane = root.findChild(QObject, "materialSourceCurveWorkspace")
    validation_pane = root.findChild(QObject, "materialValidationPane")

    assert app is not None
    assert guided_steps is not None
    assert material_page is not None
    assert library_pane is not None
    assert import_pane is not None
    assert lifecycle_pane is not None
    assert workspace_pane is not None
    assert validation_pane is not None
    assert root.property("minimumWidth") == 1000
    assert root.property("minimumHeight") == 700

    guided_steps.setProperty("currentIndex", 2)
    root.setProperty("width", 1200)
    root.setProperty("height", 760)
    app.processEvents()

    assert material_page.property("overviewColumns") == 1
    assert material_page.property("workspaceColumns") == 1
    assert library_pane.property("y") < import_pane.property("y")
    assert import_pane.property("y") < lifecycle_pane.property("y")
    assert workspace_pane.property("y") < validation_pane.property("y")

    root.setProperty("width", 1600)
    root.setProperty("height", 900)
    app.processEvents()

    assert material_page.property("overviewColumns") == 2
    assert material_page.property("workspaceColumns") == 2
    assert library_pane.property("y") == import_pane.property("y")
    assert lifecycle_pane.property("y") > library_pane.property("y")
    assert abs(workspace_pane.property("y") - validation_pane.property("y")) < 1

    for width, height in ((2200, 1200), (3840, 2160)):
        root.setProperty("width", width)
        root.setProperty("height", height)
        app.processEvents()

        assert material_page.property("overviewColumns") == 3
        assert material_page.property("workspaceColumns") == 2
        assert abs(library_pane.property("y") - import_pane.property("y")) < 1
        assert abs(import_pane.property("y") - lifecycle_pane.property("y")) < 1
        assert abs(workspace_pane.property("y") - validation_pane.property("y")) < 1


@pytest.mark.ui
def test_material_workspace_keeps_source_and_validation_content_visible() -> None:
    app = QGuiApplication.instance() or QGuiApplication([])
    controller = RecordingMaterialStudioController()
    engine = create_engine(material_studio_controller=controller)
    root = engine.rootObjects()[0]
    guided_steps = root.findChild(QObject, "guidedStepList")
    workspace_grid = root.findChild(QQuickItem, "materialWorkspaceGrid")
    source_workspace = root.findChild(QQuickItem, "materialSourceCurveWorkspace")
    validation_pane = root.findChild(QQuickItem, "materialValidationPane")
    source_view = root.findChild(QQuickItem, "materialSourceView")
    curve_editor = root.findChild(QQuickItem, "materialCurveEditor")
    source_comparison = root.findChild(QQuickItem, "sourcePointComparison")
    source_description = root.findChild(QQuickItem, "sourceDescriptionField")
    temperature_field = root.findChild(QQuickItem, "temperatureConditionField")
    dc_bias_field = root.findChild(QQuickItem, "dcBiasConditionField")

    assert app is not None
    assert guided_steps is not None
    assert workspace_grid is not None
    assert source_workspace is not None
    assert validation_pane is not None
    assert source_view is not None
    assert curve_editor is not None
    assert source_comparison is not None
    assert source_description is not None
    assert temperature_field is not None
    assert dc_bias_field is not None

    guided_steps.setProperty("currentIndex", 2)
    content_item = root.contentItem()

    def assert_inside(item: QQuickItem, container: QQuickItem) -> None:
        item_top_left = item.mapToItem(content_item, QPointF(0, 0))
        container_top_left = container.mapToItem(content_item, QPointF(0, 0))
        assert item_top_left.x() >= container_top_left.x() - 1
        assert item_top_left.y() >= container_top_left.y() - 1
        assert item_top_left.x() + item.width() <= container_top_left.x() + container.width() + 1
        assert item_top_left.y() + item.height() <= container_top_left.y() + container.height() + 1

    for width, height in ((1200, 760), (1600, 900), (2200, 1200), (3840, 2160)):
        root.setProperty("width", width)
        root.setProperty("height", height)
        app.processEvents()

        assert_inside(source_workspace, workspace_grid)
        assert_inside(validation_pane, workspace_grid)
        assert_inside(source_view, source_workspace)
        assert_inside(curve_editor, source_workspace)
        assert_inside(source_comparison, curve_editor)
        assert_inside(source_description, source_workspace)
        assert_inside(temperature_field, source_workspace)
        assert_inside(dc_bias_field, source_workspace)
        assert validation_pane.width() >= 360

        if width == 1200:
            assert abs(curve_editor.y() - source_view.y()) < 1
            assert curve_editor.x() > source_view.x()
        elif width == 1600:
            assert curve_editor.y() > source_view.y()
        else:
            assert abs(curve_editor.y() - source_view.y()) < 1


@pytest.mark.ui
def test_material_source_editor_explains_crop_and_axis_calibration() -> None:
    app = QGuiApplication.instance() or QGuiApplication([])
    controller = RecordingMaterialStudioController()
    engine = create_engine(material_studio_controller=controller)
    root = engine.rootObjects()[0]
    guided_steps = root.findChild(QObject, "guidedStepList")

    assert app is not None
    assert guided_steps is not None
    guided_steps.setProperty("currentIndex", 2)
    app.processEvents()

    expected_instructions = {
        "materialWorkflowGuide": "Import a source image or PDF",
        "cropInstructions": "image pixels",
        "xAxisInstructions": "horizontal image positions",
        "yAxisInstructions": "vertical image positions",
    }
    for object_name, expected_text in expected_instructions.items():
        instruction = root.findChild(QObject, object_name)
        assert instruction is not None
        assert expected_text in instruction.property("text")

    for object_name, expected_text in {
        "cropLeftLabel": "Left (image px)",
        "cropTopLabel": "Top (image px)",
        "cropWidthLabel": "Width (image px)",
        "cropHeightLabel": "Height (image px)",
        "xAxisPixelALabel": "Pixel A (image px)",
        "xAxisValueALabel": "Value A (X unit)",
        "yAxisPixelALabel": "Pixel A (image px)",
        "yAxisValueALabel": "Value A (Y unit)",
    }.items():
        label = root.findChild(QObject, object_name)
        assert label is not None
        assert label.property("text") == expected_text
