"""The application menu bar (File > Open/Save/Save As/Exit, Help > About).

Before this, the only project operations were the top-bar Save button and
the `--project` CLI argument -- there was no way to open a different project,
save under a new name, see version info, or quit other than the window close
button. These tests exercise the real QML wiring: the menu items themselves,
`ProjectSession.openProject`/`saveProjectAs` replacing the project and
document path in place, Exit routing through the same
`requestApplicationClose()` guard the window close button uses, and About
showing the real version string.
"""

from __future__ import annotations

import os
import sys
from dataclasses import replace
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QSG_RHI_BACKEND", "software")

pytest.importorskip("PySide6")

import PySide6.QtGui as QtGui  # noqa: E402
from PySide6.QtCore import (  # noqa: E402
    QMessageLogContext,
    QMetaObject,
    QObject,
    QtMsgType,
    QUrl,
    qInstallMessageHandler,
)
from PySide6.QtGui import QAccessible, QGuiApplication, QKeySequence  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

import inductor_designer.ui.main as main_module  # noqa: E402
from inductor_designer import __version__  # noqa: E402
from inductor_designer.adapters.persistence.project_repository import (  # noqa: E402
    ProjectRepository,
)
from inductor_designer.adapters.persistence.schema_repository import (  # noqa: E402
    SchemaRepository,
)
from inductor_designer.application.services.aedt_support import (  # noqa: E402
    SUPPORTED_AEDT_EDITION,
    SUPPORTED_AEDT_RELEASE,
)
from inductor_designer.domain.project import ManualCoreSelection  # noqa: E402
from inductor_designer.ui.guided_studio_controller import (  # noqa: E402
    GuidedStudioController,
)
from inductor_designer.ui.main import create_engine  # noqa: E402
from inductor_designer.ui.project_session import ProjectSession  # noqa: E402
from tests.unit.application.test_geometry_model import CATALOG  # noqa: E402
from tests.unit.domain.test_project import (  # noqa: E402
    make_project,
    make_project_with_material,
    make_winding,
)
from tools.build_catalog import build  # noqa: E402

pytestmark = pytest.mark.ui

ROOT = Path(__file__).resolve().parents[2]

# Same lifetime idiom as tests/ui/test_main_close_dialog.py and
# tests/ui/test_main_wiring.py: a QObject handed to `create_engine` /
# `setContextProperty`, or the engine itself, is garbage collected the moment
# nothing in Python still references it.
_KEEPALIVE: list[object] = []


def _trigger(item: QObject) -> None:
    assert QMetaObject.invokeMethod(item, "triggered") is True


def _capture_qml_messages() -> list[str]:
    """Record every `qWarning`/`qCritical` message the QML engine itself
    reports, which is how a QML runtime error (e.g. an uncaught
    `ReferenceError`) surfaces -- the exact mechanism `main.py`'s
    `_install_qml_logging()` prints to stderr.
    Caller must restore the previous handler with `qInstallMessageHandler(None)`.

    Only messages carrying a QML source location are kept. `qInstallMessageHandler`
    is process global and catches the platform's own chatter too: Qt's Windows
    style opens native theme data per styled control, and when that fails it
    logs `OpenThemeData() failed for theme 2 (EDIT). (The handle is invalid.)`
    -- once per control, from whichever window happens to be building itself,
    at a moment nothing in this test controls. That made `assert not messages`
    fail at random under `pytest -n 8` and pass on every rerun. A QML
    diagnostic always names the file and line of the offending QML; the
    platform warnings name nothing, which is the difference filtered on here.
    """
    messages: list[str] = []

    def handler(_mode: QtMsgType, context: QMessageLogContext, message: str) -> None:
        if context.line > 0 or context.file:
            messages.append(message)

    qInstallMessageHandler(handler)
    return messages


def _accessible_text(item: QObject, part: QAccessible.Text) -> str:
    """The real accessibility text for `item`, via the same bridge a screen
    reader uses.

    `.property("Accessible.description")` cannot see this at all: an attached
    property like `Accessible.description` has no matching Q_PROPERTY on the
    object itself, so `.property()` always returns `None` for it -- which is
    why `open_item.property("Accessible.description") != ""` used to pass
    (`None != ""` is always `True`) even with the QML line deleted entirely.
    """
    interface = QAccessible.queryAccessibleInterface(item)
    assert interface is not None, "item exposes no accessibility interface"
    return interface.text(part)


def _accept_file_dialog(dialog: QObject, path: Path) -> None:
    """Drive `FileDialog` the way `test_main_close_dialog.py` drives a
    `Button`: emit the signal its `on...:` handler is connected to, rather
    than the dialog's own `accept()` slot, which -- under the offscreen
    platform's non-native fallback implementation -- resets `selectedFile`
    to empty as part of closing instead of using the value set here.
    """
    assert dialog.setProperty("selectedFile", QUrl.fromLocalFile(str(path))) is True
    assert QMetaObject.invokeMethod(dialog, "accepted") is True


def _bare_root(app_info_controller: object = None) -> tuple[object, object]:
    """A window with no project loaded, e.g. no `--project` was given."""
    app = QGuiApplication.instance() or QGuiApplication([])
    engine = create_engine(app_info_controller=app_info_controller)
    root = engine.rootObjects()[0]
    _KEEPALIVE.append((app, engine, *engine.rootObjects(), app_info_controller))
    app.processEvents()
    return app, root


def _loaded_root(document_path: Path | None = None) -> tuple[object, object, ProjectSession]:
    app = QGuiApplication.instance() or QGuiApplication([])
    session = ProjectSession(make_project(), document_path)
    controller = GuidedStudioController(session, CATALOG)
    engine = create_engine(guided_studio_controller=controller, project_session=session)
    root = engine.rootObjects()[0]
    _KEEPALIVE.append((app, engine, *engine.rootObjects(), controller, session))
    app.processEvents()
    return app, root, session


def test_menu_bar_and_items_exist_with_expected_enabled_state() -> None:
    _app, root = _bare_root()

    menu_bar = root.findChild(QObject, "appMenuBar")
    assert menu_bar is not None
    file_menu = root.findChild(QObject, "fileMenu")
    assert file_menu is not None and file_menu.property("title") == "File"
    edit_menu = root.findChild(QObject, "editMenu")
    assert edit_menu is not None and edit_menu.property("title") == "Edit"
    help_menu = root.findChild(QObject, "helpMenu")
    assert help_menu is not None and help_menu.property("title") == "Help"

    open_item = root.findChild(QObject, "openProjectMenuItem")
    save_item = root.findChild(QObject, "saveProjectMenuItem")
    save_as_item = root.findChild(QObject, "saveProjectAsMenuItem")
    undo_item = root.findChild(QObject, "undoMenuItem")
    redo_item = root.findChild(QObject, "redoMenuItem")
    exit_item = root.findChild(QObject, "exitMenuItem")
    about_item = root.findChild(QObject, "aboutMenuItem")
    save_bundle_item = root.findChild(QObject, "saveDiagnosticBundleMenuItem")
    save_bundle_dialog = root.findChild(QObject, "saveBundleDialog")

    for item in (
        open_item,
        save_item,
        save_as_item,
        undo_item,
        redo_item,
        exit_item,
        about_item,
        save_bundle_item,
        save_bundle_dialog,
    ):
        assert item is not None

    # No project loaded: Open/Save/Save As/Undo/Redo are all disabled, and
    # the reason is exposed to accessibility tooling (and to this test), not
    # just a dead button.
    assert open_item.property("enabled") is False
    assert save_item.property("enabled") is False
    assert save_as_item.property("enabled") is False
    assert undo_item.property("enabled") is False
    assert redo_item.property("enabled") is False
    assert _accessible_text(open_item, QAccessible.Description) != ""
    assert _accessible_text(save_item, QAccessible.Description) != ""
    assert _accessible_text(undo_item, QAccessible.Description) != ""
    assert _accessible_text(redo_item, QAccessible.Description) != ""
    # Exit and About are always available.
    assert exit_item.property("enabled") is True
    assert about_item.property("enabled") is True


def test_undo_and_redo_menu_items_reflect_and_drive_the_session_history() -> None:
    app, root, session = _loaded_root(Path("boost.inductor.json"))
    undo_item = root.findChild(QObject, "undoMenuItem")
    redo_item = root.findChild(QObject, "redoMenuItem")
    assert undo_item.property("enabled") is False
    assert redo_item.property("enabled") is False

    session.apply(replace(session.project, description="edited"))
    app.processEvents()
    assert undo_item.property("enabled") is True

    _trigger(undo_item)
    app.processEvents()
    assert session.project.description == ""
    assert undo_item.property("enabled") is False
    assert redo_item.property("enabled") is True

    _trigger(redo_item)
    app.processEvents()
    assert session.project.description == "edited"


def test_ctrl_z_and_ctrl_y_actually_undo_and_redo_with_no_qml_errors() -> None:
    """The `Shortcut { onActivated: parent.triggered() }` wiring is dead:
    `Shortcut` is a `QObject`, not an `Item`, so `parent` never resolves and
    every keypress logs a QML `ReferenceError` instead of undoing anything.
    `QTest.keySequence` delivers a real key event to the window, the same
    path an actual keypress takes -- unlike calling the `Shortcut`'s
    `activated` signal directly (`QMetaObject.invokeMethod`), which would
    emit it unconditionally and could not tell a working shortcut from a
    broken one, nor respect `enabled`.
    """
    app, root, session = _loaded_root(Path("boost.inductor.json"))
    session.apply(replace(session.project, description="edited"))
    app.processEvents()
    root.requestActivate()
    app.processEvents()

    messages = _capture_qml_messages()
    try:
        QTest.keySequence(root, QKeySequence.Undo)
        app.processEvents()

        assert session.project.description == ""
        assert not messages, messages

        messages.clear()
        QTest.keySequence(root, QKeySequence.Redo)
        app.processEvents()

        assert session.project.description == "edited"
        assert not messages, messages
    finally:
        qInstallMessageHandler(None)


def test_ctrl_z_does_nothing_when_undo_is_disabled() -> None:
    """`Shortcut.enabled` defaults to `true` and, unless bound to the menu
    item's own `enabled`, fires even when there is no project loaded at all
    -- calling `projectSession.undo()` on a null `projectSession`.
    """
    _app, root = _bare_root()
    undo_item = root.findChild(QObject, "undoMenuItem")
    assert undo_item.property("enabled") is False
    root.requestActivate()
    QGuiApplication.instance().processEvents()

    messages = _capture_qml_messages()
    try:
        QTest.keySequence(root, QKeySequence.Undo)
        QGuiApplication.instance().processEvents()

        assert not messages, messages
    finally:
        qInstallMessageHandler(None)


def test_the_qml_message_capture_keeps_qml_errors_and_drops_platform_chatter() -> None:
    """Pins the filter the two shortcut tests above depend on.

    Without it, `assert not messages` gated on every warning in the process,
    so Qt's Windows style logging `OpenThemeData() failed ...` while some
    other window built itself failed the shortcut tests at random under
    `pytest -n 8`. Deleting the filter must not be the fix either: a capture
    that drops everything would make those tests green with the QML wiring
    ripped out, which is the regression they exist to catch. So both halves
    are asserted here -- the real `ReferenceError` a broken
    `Shortcut { onActivated: parent.triggered() }` produces is kept, the
    location-less platform warning is not.
    """
    from PySide6.QtCore import qWarning
    from PySide6.QtQml import QQmlApplicationEngine

    app = QGuiApplication.instance() or QGuiApplication([])
    engine = QQmlApplicationEngine()
    messages = _capture_qml_messages()
    try:
        qWarning("OpenThemeData() failed for theme 2 (EDIT). (The handle is invalid.)")
        assert messages == []

        # The exact shape of the wiring bug: `QtObject`, like `Shortcut`, is
        # not an `Item`, so `parent` does not resolve at all there -- it is
        # not merely null -- and the handler throws when it runs.
        engine.loadData(
            b"""
            import QtQml
            QtObject {
                objectName: "referenceErrorProbe"
                Component.onCompleted: parent.triggered()
            }
            """
        )
        app.processEvents()
    finally:
        qInstallMessageHandler(None)
        _KEEPALIVE.append((app, engine, *engine.rootObjects()))

    assert any("ReferenceError" in message for message in messages), messages


def test_exit_routes_through_the_same_unsaved_changes_guard_as_window_close() -> None:
    app, root, session = _loaded_root(Path("boost.inductor.json"))
    session.apply(replace(session.project, description="edited"))
    assert session.dirty is True

    exit_item = root.findChild(QObject, "exitMenuItem")
    _trigger(exit_item)
    app.processEvents()

    assert root.property("visible") is True
    dialog = root.findChild(QObject, "unsavedProjectDialog")
    assert dialog.property("visible") is True


def test_open_with_unsaved_changes_warns_via_the_same_dialog_first() -> None:
    app, root, session = _loaded_root(Path("boost.inductor.json"))
    session.apply(replace(session.project, description="edited"))
    assert session.dirty is True

    open_item = root.findChild(QObject, "openProjectMenuItem")
    assert open_item.property("enabled") is True
    _trigger(open_item)
    app.processEvents()

    unsaved_dialog = root.findChild(QObject, "unsavedProjectDialog")
    open_dialog = root.findChild(QObject, "openProjectDialog")
    assert unsaved_dialog.property("visible") is True
    assert open_dialog.property("visible") is False

    # Discard: the deferred Open action now runs and the file dialog opens.
    assert (
        QMetaObject.invokeMethod(
            root.findChild(QObject, "unsavedProjectDiscardButton"), "clicked"
        )
        is True
    )
    app.processEvents()

    assert unsaved_dialog.property("visible") is False
    assert open_dialog.property("visible") is True


def test_save_as_moves_the_document_path_and_clears_dirty(tmp_path: Path) -> None:
    app, root, session = _loaded_root(Path("boost.inductor.json"))
    saved: list[object] = []
    session.set_save_callback(saved.append)
    session.apply(replace(session.project, description="edited"))
    assert session.dirty is True

    target = tmp_path / "renamed.inductor.json"
    dialog = root.findChild(QObject, "saveProjectAsDialog")
    _accept_file_dialog(dialog, target)
    app.processEvents()

    assert saved and saved[0].description == "edited"
    assert session.dirty is False
    assert session.document_path == target


def test_about_shows_the_real_version_and_supported_aedt_target() -> None:
    from inductor_designer.ui.app_info_controller import AppInfoController

    _app, root = _bare_root(AppInfoController())

    about_item = root.findChild(QObject, "aboutMenuItem")
    _trigger(about_item)

    dialog = root.findChild(QObject, "aboutDialog")
    assert dialog.property("visible") is True
    version_label = root.findChild(QObject, "aboutVersionLabel")
    assert __version__ in version_label.property("text")
    aedt_label = root.findChild(QObject, "aboutAedtTargetLabel")
    assert str(SUPPORTED_AEDT_RELEASE) in aedt_label.property("text")
    assert SUPPORTED_AEDT_EDITION.value in aedt_label.property("text")


# --- Full `main()` wiring: Open must rebind every screen, and a bad file ---
# --- must report and leave the current project untouched. ------------------

_ENGINES: list[object] = []


def _run_main_with(
    monkeypatch: pytest.MonkeyPatch,
    project_path: Path,
    catalog_index: Path,
    matrix_path: Path,
) -> tuple[object, object]:
    real_app_cls = QtGui.QGuiApplication
    monkeypatch.setattr(
        QtGui,
        "QGuiApplication",
        lambda argv: real_app_cls.instance() or real_app_cls(argv),
    )
    monkeypatch.setattr(real_app_cls, "exec", lambda self: 0)

    real_create_engine = main_module.create_engine

    def capturing_create_engine(*args: object, **kwargs: object) -> object:
        engine = real_create_engine(*args, **kwargs)
        _ENGINES.append((engine, *engine.rootObjects(), *args, *kwargs.values()))
        return engine

    monkeypatch.setattr(main_module, "create_engine", capturing_create_engine)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "inductor-designer",
            "--project",
            str(project_path),
            "--catalog",
            str(catalog_index),
            "--matrix",
            str(matrix_path),
        ],
    )
    result = main_module.main()
    assert result == 0
    engine, root, *_kept = _ENGINES[-1]
    QGuiApplication.instance().processEvents()
    return engine, root


@pytest.fixture
def catalog_index(tmp_path_factory: pytest.TempPathFactory) -> Path:
    index = tmp_path_factory.mktemp("catalog") / "catalog.sqlite"
    build(ROOT / "catalog", ROOT / "schemas" / "catalog", index)
    return index


def test_open_a_valid_project_rebinds_the_windings_screen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, catalog_index: Path
) -> None:
    repository = ProjectRepository(SchemaRepository(ROOT / "schemas"))
    project_a = make_project()
    project_b = replace(
        project_a, design=replace(project_a.design, windings=(make_winding(turns=77),))
    )
    path_a = tmp_path / "a.inductor.json"
    path_b = tmp_path / "b.inductor.json"
    repository.save(project_a, path_a)
    repository.save(project_b, path_b)
    matrix_path = ROOT / "compatibility" / "aedt-matrix.yml"

    engine, root = _run_main_with(monkeypatch, path_a, catalog_index, matrix_path)
    guided = engine.rootContext().contextProperty("guidedStudioController")
    assert guided.windings[0]["turns"] == 20  # make_project()'s default

    open_dialog = root.findChild(QObject, "openProjectDialog")
    _accept_file_dialog(open_dialog, path_b)
    QGuiApplication.instance().processEvents()

    assert guided.windings[0]["turns"] == 77
    session = engine.rootContext().contextProperty("projectSession")
    assert session.documentPath == str(path_b)
    assert session.dirty is False


def test_open_a_corrupt_file_reports_and_leaves_the_project_intact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, catalog_index: Path
) -> None:
    repository = ProjectRepository(SchemaRepository(ROOT / "schemas"))
    project_a = make_project()
    path_a = tmp_path / "a.inductor.json"
    repository.save(project_a, path_a)
    broken_path = tmp_path / "broken.inductor.json"
    broken_path.write_text("not valid json {{{", encoding="utf-8")
    matrix_path = ROOT / "compatibility" / "aedt-matrix.yml"

    engine, root = _run_main_with(monkeypatch, path_a, catalog_index, matrix_path)
    guided = engine.rootContext().contextProperty("guidedStudioController")
    assert guided.windings[0]["turns"] == 20

    open_dialog = root.findChild(QObject, "openProjectDialog")
    _accept_file_dialog(open_dialog, broken_path)
    QGuiApplication.instance().processEvents()

    # Untouched: still the original project, still 20 turns.
    assert guided.windings[0]["turns"] == 20
    session = engine.rootContext().contextProperty("projectSession")
    assert str(path_a) == session.documentPath
    assert "Unable to open" in guided.statusMessage


def test_open_a_project_with_a_different_core_and_material_updates_the_screen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, catalog_index: Path
) -> None:
    """`CoreMaterialController.refresh()` is only reachable via
    `session.projectChanged`; without that wiring, Open replaces the session's
    project but the Core & Material screen keeps showing the previous
    project's core and material. Reading `controller.selectedCore` /
    `selectedMaterial` from Python would not notice this -- both recompute
    fresh from `session.project` on every access, wiring or no wiring -- so
    this asserts on the rendered QML instead: `manualCoreOuterField.text` is
    set imperatively inside a JS function (`CoreMaterialPanel.qml`'s
    `refreshManualFields()`) that only runs when the controller's
    `selectionChanged` fires.
    """
    repository = ProjectRepository(SchemaRepository(ROOT / "schemas"))
    # project_a: a catalog core with its pinned material revision (loaded first).
    project_a = make_project_with_material()
    # project_b: a manual core with no material pinned at all (opened second).
    project_b = replace(
        project_a,
        design=replace(
            project_a.design,
            core=ManualCoreSelection(0.0269, 0.0147, 0.0112, 0.0),
            core_material=None,
        ),
    )
    path_a = tmp_path / "a.inductor.json"
    path_b = tmp_path / "b.inductor.json"
    repository.save(project_a, path_a)
    repository.save(project_b, path_b)
    matrix_path = ROOT / "compatibility" / "aedt-matrix.yml"

    engine, root = _run_main_with(monkeypatch, path_a, catalog_index, matrix_path)
    core_material = engine.rootContext().contextProperty("coreMaterialController")
    outer_field = root.findChild(QObject, "manualCoreOuterField")
    # project_a's core is a catalog core, so the manual-core field is blank,
    # even though Python's own selectedCore already reads back the pinned
    # catalog core correctly (it recomputes fresh; that is not the gap here).
    assert core_material.selectedMaterial != {}
    assert outer_field.property("text") == ""

    open_dialog = root.findChild(QObject, "openProjectDialog")
    _accept_file_dialog(open_dialog, path_b)
    QGuiApplication.instance().processEvents()
    root.grabWindow()
    QGuiApplication.instance().processEvents()

    # project_b's manual core dimensions must now be on screen. Python's own
    # `selectedCore`/`selectedMaterial` would already read back project_b
    # correctly even with the connection deleted -- they recompute fresh on
    # every access -- so the rendered QML is what actually catches the gap.
    assert outer_field.property("text") == "26.9"


def test_open_a_project_with_different_winding_ids_resets_the_selection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, catalog_index: Path
) -> None:
    """The `selectedWindingId` reset branch in `GuidedStudioController.refresh()`
    only matters when Open's target project does not reuse the loaded
    project's winding ids -- which is exactly why the previous Open test (both
    projects default to winding id "w1") never noticed this branch being
    deleted. Here project_a uses "w1" and project_b uses "primary", so a
    missing reset leaves `selectedWindingId` pointing at a winding id ("w1")
    that no longer exists in project_b at all.
    """
    repository = ProjectRepository(SchemaRepository(ROOT / "schemas"))
    project_a = make_project()  # single winding, id "w1" (make_winding()'s default)
    project_b = replace(
        project_a,
        design=replace(
            project_a.design,
            windings=(make_winding(winding_id="primary", turns=42),),
        ),
        operating_point=replace(
            project_a.operating_point,
            windings=(
                replace(project_a.operating_point.windings[0], winding_id="primary"),
            ),
        ),
    )
    path_a = tmp_path / "a.inductor.json"
    path_b = tmp_path / "b.inductor.json"
    repository.save(project_a, path_a)
    repository.save(project_b, path_b)
    matrix_path = ROOT / "compatibility" / "aedt-matrix.yml"

    engine, root = _run_main_with(monkeypatch, path_a, catalog_index, matrix_path)
    guided = engine.rootContext().contextProperty("guidedStudioController")
    assert guided.selectedWindingId == "w1"

    open_dialog = root.findChild(QObject, "openProjectDialog")
    _accept_file_dialog(open_dialog, path_b)
    QGuiApplication.instance().processEvents()

    # The selection must name a winding that actually exists in project_b --
    # "w1" does not exist there at all.
    assert guided.selectedWindingId == "primary"
    assert guided.selectedWindingId in {row["windingId"] for row in guided.windings}

    label_field = root.findChild(QObject, "windingLabelField")
    turns_field = root.findChild(QObject, "windingTurnsField")
    assert turns_field.property("text") == "42"
    assert label_field.property("text") == "Primary"


def test_the_diagnostic_bundle_item_offers_a_name_carrying_no_project_identity() -> None:
    """The dialog's default name is the string users paste into tickets.

    `suggestedFileName` was computed correctly and then never used -- the item
    cleared `currentFile` instead, so the user typed a name, usually the
    project's, putting a customer name in a filename that leaves BRUSA. This
    pins the binding, which no test covered: reverting it to `""` kept every
    other test green.
    """
    from inductor_designer.adapters.system.environment import environment_redaction_context
    from inductor_designer.ui.diagnostics_controller import DiagnosticsController

    app = QGuiApplication.instance() or QGuiApplication([])
    session = ProjectSession(make_project(), Path("CustomerACME") / "boost.inductor.json")
    controller = DiagnosticsController(session, None, environment_redaction_context())
    engine = create_engine(diagnostics_controller=controller, project_session=session)
    root = engine.rootObjects()[0]
    _KEEPALIVE.append((app, engine, *engine.rootObjects(), controller, session))
    app.processEvents()

    _trigger(root.findChild(QObject, "saveDiagnosticBundleMenuItem"))

    dialog = root.findChild(QObject, "saveBundleDialog")
    offered = str(dialog.property("currentFile"))
    assert "diagnostics-" in offered
    assert "CustomerACME" not in offered
    assert "boost" not in offered


def test_new_from_a_dirty_project_warns_first_and_then_blanks_the_session() -> None:
    """File > New must not silently discard unsaved work: it routes through
    the same single guard as File > Open and the window's close button."""
    app, root, session = _loaded_root(Path("boost.inductor.json"))
    session.apply(replace(session.project, description="edited"))
    app.processEvents()

    new_item = root.findChild(QObject, "newProjectMenuItem")
    assert new_item.property("enabled") is True
    _trigger(new_item)
    app.processEvents()

    unsaved_dialog = root.findChild(QObject, "unsavedProjectDialog")
    assert unsaved_dialog.property("visible") is True
    # Nothing replaced yet: the choice has not been made.
    assert session.project.description == "edited"

    assert (
        QMetaObject.invokeMethod(
            root.findChild(QObject, "unsavedProjectDiscardButton"), "clicked"
        )
        is True
    )
    app.processEvents()

    assert session.document_path is None
    assert session.project.design.core is None
    assert session.dirty is False


def test_save_on_a_project_with_no_document_path_offers_save_as_instead() -> None:
    """`Save` writes to the session's document path, and a project started
    from New has none -- the persister raises `RuntimeError` there. The menu
    item has to ask for a name rather than fail."""
    app, root, session = _loaded_root(None)
    session.apply(replace(session.project, description="edited"))
    app.processEvents()

    save_item = root.findChild(QObject, "saveProjectMenuItem")
    assert save_item.property("enabled") is True
    _trigger(save_item)
    app.processEvents()

    assert root.findChild(QObject, "saveProjectAsDialog").property("visible") is True
    # Still unsaved: the dialog is open, nothing has been written.
    assert session.dirty is True


def test_redo_also_answers_the_second_binding_windows_gives_it() -> None:
    """`StandardKey.Redo` is two bindings on Windows -- Ctrl+Y and
    Ctrl+Shift+Z -- and `sequence:` wires up only one of them, which is what
    Qt's "Only binding to one of multiple key bindings" warning at load was
    saying. `sequences:` binds both, so this is the half that used to be dead.
    """
    app, root, session = _loaded_root(Path("boost.inductor.json"))
    session.apply(replace(session.project, description="edited"))
    app.processEvents()
    root.requestActivate()
    app.processEvents()

    QTest.keySequence(root, QKeySequence.Undo)
    app.processEvents()
    assert session.project.description == ""

    messages = _capture_qml_messages()
    try:
        QTest.keySequence(root, QKeySequence("Ctrl+Shift+Z"))
        app.processEvents()

        assert session.project.description == "edited"
        assert not messages, messages
    finally:
        qInstallMessageHandler(None)
