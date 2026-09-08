from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QSG_RHI_BACKEND", "software")

pytest.importorskip("PySide6")

from PySide6.QtCore import QObject  # noqa: E402
from PySide6.QtGui import QAccessible, QGuiApplication  # noqa: E402

from inductor_designer.ui.guided_studio_controller import (  # noqa: E402
    GuidedStudioController,
)
from inductor_designer.ui.main import create_engine  # noqa: E402
from inductor_designer.ui.project_session import ProjectSession  # noqa: E402
from tests.unit.application.test_geometry_model import CATALOG  # noqa: E402
from tests.unit.domain.test_project import make_project  # noqa: E402

pytestmark = pytest.mark.ui

NUMERIC_FIELDS = (
    "operatingFrequencyField",
    "windingTemperatureField",
    "coreTemperatureField",
    "windingTurnsField",
    "windingCurrentField",
    "windingPhaseField",
    "windingDcCurrentField",
    "windingStartAngleField",
    "windingSectorField",
    "windingSpacingField",
    "windingClearanceField",
)
SELECTORS = (
    "windingConductorCombo",
    "windingModeCombo",
    "windingCurrentDirectionCombo",
    "windingDirectionField",
)

# QQmlApplicationEngine owns the root window it creates; if the engine itself
# is garbage-collected the window (and every child found via findChild) goes
# with it. setContextProperty() also does not take ownership of a parent-less
# QObject, so a GuidedStudioController built inline as a call argument is
# collected the moment the call expression is done with it, silently nulling
# windingsPanel.controller and every ComboBox model bound to it. Both the
# engine and the controller are pinned here for the lifetime of the test
# process instead of being dropped the moment the helper returns.
_ENGINES: list[object] = []


def open_windings() -> tuple[QGuiApplication, QObject, ProjectSession]:
    app = QGuiApplication.instance() or QGuiApplication([])
    session = ProjectSession(make_project())
    controller = GuidedStudioController(session, CATALOG)
    engine = create_engine(guided_studio_controller=controller)
    _ENGINES.append((engine, controller))
    root = engine.rootObjects()[0]
    root.findChild(QObject, "guidedStepList").setProperty("currentIndex", 1)
    app.processEvents()
    return app, root, session


def test_every_specified_winding_and_operating_point_input_is_present() -> None:
    _, root, _ = open_windings()

    for name in (
        *NUMERIC_FIELDS,
        *SELECTORS,
        "windingLabelField",
        "windingTerminalIntentField",
        "addWindingButton",
        "removeWindingButton",
    ):
        assert root.findChild(QObject, name) is not None, name


def test_numeric_fields_carry_a_native_validator_and_an_accessible_name() -> None:
    """`field.property("Accessible.name")` cannot see the attached
    `Accessible.name` property at all -- it always returns `None` -- and
    `field.property("text") is not None` is always `True` for a `TextField`
    (even an empty one reads back `""`, never `None`), so the original `or`
    assertion passed regardless of whether `Accessible.name` was set. Query
    the real accessibility bridge instead.
    """
    _, root, _ = open_windings()

    for name in NUMERIC_FIELDS:
        field = root.findChild(QObject, name)
        assert field.property("validator") is not None, name
        interface = QAccessible.queryAccessibleInterface(field)
        assert interface is not None, name
        assert interface.text(QAccessible.Name) != "", name


def test_turns_accept_only_integers() -> None:
    _, root, _ = open_windings()
    turns = root.findChild(QObject, "windingTurnsField")

    turns.setProperty("text", "24")
    assert turns.property("acceptableInput") is True

    turns.setProperty("text", "24.5")
    assert turns.property("acceptableInput") is False


def test_negative_values_are_accepted_where_they_are_valid() -> None:
    _, root, _ = open_windings()
    phase = root.findChild(QObject, "windingPhaseField")

    phase.setProperty("text", "-90")

    assert phase.property("acceptableInput") is True


def test_a_negative_dc_current_is_rejected_by_the_editor() -> None:
    _, root, _ = open_windings()
    dc = root.findChild(QObject, "windingDcCurrentField")

    dc.setProperty("text", "-1")

    assert dc.property("acceptableInput") is False


def test_selectors_offer_exactly_the_controller_values() -> None:
    _, root, _ = open_windings()

    assert list(root.findChild(QObject, "windingConductorCombo").property("model")) == [
        "AWG 18"
    ]
    assert list(root.findChild(QObject, "windingModeCombo").property("model")) == [
        "solid",
        "stranded",
    ]
    assert list(
        root.findChild(QObject, "windingCurrentDirectionCombo").property("model")
    ) == ["forward", "reverse"]


def test_the_operating_point_shows_the_shared_project_values() -> None:
    _, root, session = open_windings()

    assert root.findChild(QObject, "operatingFrequencyField").property("text") == str(
        session.project.operating_point.frequency_hz
    )
    assert root.findChild(QObject, "coreTemperatureField").property("text") == str(
        session.project.operating_point.core_temperature_c
    )


def test_remove_is_disabled_for_the_last_winding() -> None:
    _, root, _ = open_windings()

    assert root.findChild(QObject, "removeWindingButton").property("enabled") is False


def test_the_conductor_review_notice_is_on_screen_while_the_wires_are_draft() -> None:
    """Every shipped conductor is a draft transcription, and every winding is
    sized on one. The notice is rendered rather than only exposed on the
    controller, because a property nobody displays warns nobody."""
    _app, root, _session = open_windings()
    notice = root.findChild(QObject, "conductorReviewNotice")
    assert notice is not None
    assert notice.property("visible") is True
    assert "draft" in notice.property("text")
