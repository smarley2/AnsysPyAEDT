"""Regression test for the hand-rolled screen switcher in `Main.qml`.

The M7c Guided Studio commit replaced the shell's `StackLayout` with five
plain `Item`s (`CoreMaterialPanel`, `WindingPanel`, `PreliminaryPage`,
`SimulationPanel`, `ReviewPage`) that stay permanently `visible: true` and
are shown or hidden with `opacity`/`enabled` bindings instead (see the
`stepPagesHost` comment in `Main.qml` for why `StackLayout` was dropped). A
reviewer verified by hand that exactly one screen is active at a time, that
a hidden screen cannot take focus, and that Tab traversal cannot land on
one -- but nothing in CI protected any of that: reverting the whole change
back to a `StackLayout` still leaves every other ui test green, since none
of them ever inspect `opacity`/`enabled` or attempt to focus a hidden
screen's content.

This file is what closes that gap. It does not need `activeFocusOnTab` or
Tab-key simulation to catch a regression: `enabled: false` is what Qt Quick
uses to refuse focus to a subtree in the first place, so a direct,
programmatic `forceActiveFocus()` call is the more direct probe of the same
mechanism -- if it can plant `activeFocus` on a hidden screen's control, Tab
traversal landing there is just as broken.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QSG_RHI_BACKEND", "software")

pytest.importorskip("PySide6")

from PySide6.QtCore import QObject  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtQuick import QQuickWindow  # noqa: E402, F401

from inductor_designer.simulation.capabilities import (  # noqa: E402
    AedtEdition,
    AedtRelease,
    CapabilityReviewStatus,
    CapabilitySnapshot,
)
from inductor_designer.ui.core_material_controller import (  # noqa: E402
    CoreMaterialController,
)
from inductor_designer.ui.generation_controller import GenerationController  # noqa: E402
from inductor_designer.ui.guided_studio_controller import (  # noqa: E402
    GuidedStudioController,
)
from inductor_designer.ui.main import create_engine  # noqa: E402
from inductor_designer.ui.preliminary_controller import (  # noqa: E402
    PreliminaryController,
)
from inductor_designer.ui.project_session import ProjectSession  # noqa: E402
from inductor_designer.ui.review_controller import ReviewController  # noqa: E402
from inductor_designer.ui.simulation_controller import (  # noqa: E402
    SimulationController,
)
from tests.fakes.material_repository import InMemoryMaterialRepository  # noqa: E402
from tests.unit.application.test_geometry_model import CATALOG  # noqa: E402
from tests.unit.domain.test_project import (  # noqa: E402
    make_material_record,
    make_project_with_material,
)

pytestmark = pytest.mark.ui

SUPPORTED = CapabilitySnapshot(
    release=AedtRelease(2025, 2),
    edition=AedtEdition.COMMERCIAL,
    include_dc_fields_3d=True,
    discovered_limits=(),
    evidence_source="test",
    review_status=CapabilityReviewStatus.REVIEWED,
)

SCREEN_NAMES = (
    "coreMaterialPanel",
    "windingsPanel",
    "preliminaryPage",
    "simulationPanel",
    "reviewPage",
)

# One real descendant control per screen (not the screen's own root, whose
# own `enabled` would trivially block focus regardless of whether disabling
# actually *propagates* to its content) -- used to prove the hidden screen's
# whole subtree, not just its root item, refuses focus. Preliminary has no
# text field or button (it is read-only estimates), so its own results
# `ListView` stands in.
SCREEN_PROBE_CONTROLS = (
    "manualCoreOuterField",
    "operatingFrequencyField",
    "preliminaryWindingTable",
    "simulationMaximumPassesField",
    "openGeneratedFileButton",
)


class _RecordingOpener:
    def open_path(self, path: Path) -> None:
        pass


# QQmlApplicationEngine owns the window it loads: once the Python wrapper for
# the engine is garbage collected, the root window (and everything under it)
# is destroyed too, even though `root` is still referenced by the caller.
# Pin the engine and every controller passed to it for the test process
# lifetime instead (same idiom as tests/ui/test_panel_layout_containment.py).
_ENGINES: list[object] = []


def _build_shell() -> tuple[QGuiApplication, QObject, QObject]:
    app = QGuiApplication.instance() or QGuiApplication([])
    session = ProjectSession(
        make_project_with_material(), Path("boost.inductor.json"), lambda project: None
    )
    material_repository = InMemoryMaterialRepository()
    material_repository.save(make_material_record(), {})
    guided = GuidedStudioController(session, CATALOG)
    core_material = CoreMaterialController(session, CATALOG, material_repository)
    preliminary = PreliminaryController(session, CATALOG)
    generation = GenerationController(lambda _request: ("done",))
    simulation = SimulationController(session, generation, SUPPORTED)
    review = ReviewController(session, preliminary, generation, CATALOG, _RecordingOpener())
    engine = create_engine(
        guided_studio_controller=guided,
        core_material_controller=core_material,
        preliminary_controller=preliminary,
        simulation_controller=simulation,
        review_controller=review,
        generation_controller=generation,
        project_session=session,
    )
    _ENGINES.append(
        (engine, guided, core_material, preliminary, simulation, review, generation)
    )
    root = engine.rootObjects()[0]
    steps = root.findChild(QObject, "guidedStepList")
    return app, root, steps


def _settle(app: QGuiApplication, root: QObject) -> None:
    # Offscreen QPA has no screen to repaint, so nothing guarantees the
    # polish-and-sync pass that actually applies a pending opacity/enabled
    # change runs from draining the event queue alone; `grabWindow()` forces
    # it synchronously (same idiom as test_panel_layout_containment.py).
    root.grabWindow()
    for _ in range(10):
        app.processEvents()


@pytest.mark.parametrize("active_index", range(5))
def test_exactly_one_screen_is_active_at_a_time(active_index: int) -> None:
    app, root, steps = _build_shell()
    steps.setProperty("currentIndex", active_index)
    _settle(app, root)

    for index, name in enumerate(SCREEN_NAMES):
        panel = root.findChild(QObject, name)
        assert panel is not None, name
        if index == active_index:
            assert panel.property("opacity") == 1, (name, active_index)
            assert panel.property("enabled") is True, (name, active_index)
        else:
            assert panel.property("opacity") == 0, (name, active_index)
            assert panel.property("enabled") is False, (name, active_index)


@pytest.mark.parametrize("active_index", range(5))
def test_a_hidden_screens_control_cannot_take_focus(active_index: int) -> None:
    """Reverting `enabled: guidedStepList.currentIndex === N` back to an
    unconditional `enabled: true` (e.g. while "simplifying" the switcher)
    reintroduces a focus leak into an invisible screen without failing any
    of the other pre-existing ui tests -- this is the one that catches it.
    """
    app, root, steps = _build_shell()
    steps.setProperty("currentIndex", active_index)
    _settle(app, root)

    for index, control_name in enumerate(SCREEN_PROBE_CONTROLS):
        if index == active_index:
            continue
        control = root.findChild(QObject, control_name)
        assert control is not None, control_name
        control.forceActiveFocus()
        _settle(app, root)
        assert control.property("activeFocus") is False, (
            SCREEN_NAMES[index],
            control_name,
            active_index,
        )
