import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QSG_RHI_BACKEND", "software")

pytest.importorskip("PySide6")

from PySide6.QtCore import Property, QObject, Qt, Signal, Slot  # noqa: E402
from PySide6.QtGui import QAccessible, QAccessibleActionInterface, QGuiApplication  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from inductor_designer.ui.main import create_engine  # noqa: E402


class RecordingMaterialStudioController(QObject):
    libraryChanged = Signal()
    selectionChanged = Signal()
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
        self.selected_materials: list[tuple[str, str, str]] = []
        self.selected_revisions: list[str] = []

    materials = Property(list, lambda self: self._materials, notify=libraryChanged)
    revisions = Property(list, lambda self: self._revisions, notify=libraryChanged)
    issues = Property(list, lambda self: self._issues, notify=selectionChanged)
    fit = Property(dict, lambda self: self._fit, notify=selectionChanged)
    statusMessage = Property(
        str, lambda self: self._status_message, notify=statusMessageChanged
    )

    @Slot(str, str, str)
    def selectMaterial(self, manufacturer: str, name: str, grade: str) -> None:
        self.selected_materials.append((manufacturer, name, grade))

    @Slot(str)
    def selectRevision(self, revision_id: str) -> None:
        self.selected_revisions.append(revision_id)


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
    interfaces = _accessible_interfaces(root)
    names = [_accessible_name(interface) for interface in interfaces]
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

    select_actions = [
        interface
        for interface in interfaces
        if _accessible_name(interface).startswith("Select revision ")
    ]
    assert [_accessible_name(interface) for interface in select_actions] == [
        "Select revision rev-draft",
        "Select revision rev-reviewed",
        "Select revision rev-approved",
    ]
    assert all(interface.state().focusable for interface in select_actions)
    first_action = select_actions[0].actionInterface()
    assert first_action is not None
    first_action.doAction(QAccessibleActionInterface.setFocusAction())
    app.processEvents()
    QTest.keyClick(root, Qt.Key.Key_Tab)
    app.processEvents()
    focus = app.focusObject()
    assert focus is not None
    focus_interface = QAccessible.queryAccessibleInterface(focus)
    assert focus_interface is not None
    assert _accessible_name(focus_interface) == "Select revision rev-reviewed"
    QTest.keyClick(root, Qt.Key.Key_Return)
    app.processEvents()
    assert controller.selected_revisions == ["rev-reviewed"]

    action = select_actions[2].actionInterface()
    assert action is not None
    action.doAction(QAccessibleActionInterface.pressAction())
    app.processEvents()
    assert controller.selected_revisions == ["rev-reviewed", "rev-approved"]


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
