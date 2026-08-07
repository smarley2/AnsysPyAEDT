"""Regression test for Fabio's "context panel content is far wider than the
panel" report: labels clipped, input fields pushed off the right edge.

Two independent, unrelated mechanisms were found and fixed, and this test
guards both. Screen visit order ("visited while hidden") was the leading
hypothesis going in but was directly refuted (the bug reproduced with
`CoreMaterialPanel` fully visible from the moment it was constructed, in a
standalone instance with no `Main.qml`, no `StackLayout`, and no controller
at all) -- so this test does not key its scenarios off visit order for its
own sake, only because the actual mechanisms happen to be sensitive to it:

1. A non-`Layout.fillWidth`, non-wrapping `Label` (a screen title, or a
   `CheckBox`'s own built-in label) with long text has an implicit width
   Qt Quick Layouts cannot shrink; a `ColumnLayout` has to grow to
   accommodate it, and every `Layout.fillWidth` sibling is then stretched to
   that same oversized width instead of the panel's real width (observed:
   1032px against a real 378px panel). Fixed by giving every such `Label`
   `Layout.fillWidth: true` plus `wrapMode: Text.WordWrap` (or, for the one
   `CheckBox`, splitting its long label out into a separate wrapping
   `Label` beside a text-less `CheckBox`), and by letting fixed-width table
   columns shrink (`Layout.minimumWidth: 0`) instead of demanding their
   full preferred width.
2. Separately, `RowLayout`/`ColumnLayout`/`StackLayout` were observed to
   sometimes not re-arrange a child after a *later* geometry change --
   most visibly, `contextPanel` failing to widen for Preliminary/Review, and
   a screen's fields failing to shrink back down after `contextPanel` had
   been wide for a different screen and then narrowed again. Fixed by
   replacing the `RowLayout` that sizes `contextPanel` with plain anchors
   and `width` bindings, and by replacing the `StackLayout` that swaps the
   five screens with a plain `Item` whose screens stay permanently
   `visible: true` (shown/hidden with `opacity`/`enabled` instead) -- both
   swaps trade a `Layout`'s internal "did I actually re-arrange" bookkeeping
   for ordinary property bindings, which were never observed to go stale.

This walks every visible descendant of `contextPanel` (the Rectangle that
hosts all five screens) and asserts none of them extends past its right
edge, for each of the five screens, at a narrow and a wide window size, and
both when the screen is the first one visited and after visiting others
first.
"""

from __future__ import annotations

import gc
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QSG_RHI_BACKEND", "software")

pytest.importorskip("PySide6")

from PySide6.QtCore import QObject, QPointF  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

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

NARROW_WIDTH = 1000  # window.minimumWidth
WIDE_WIDTH = 1786

STEP_NAMES = (
    "coreMaterialPanel",
    "windingsPanel",
    "preliminaryPage",
    "simulationPanel",
    "reviewPage",
)

# QQmlApplicationEngine owns the root window; the Python wrapper for the
# engine (and every controller passed to it) must outlive the test or the
# window is torn down under us. Same idiom as the other ui test modules --
# except here the list is cleared on every call rather than accumulating for
# the whole session: this module builds a full five-controller engine per
# parametrized case (20 of them), and every prior engine's window and
# StackLayout kept alive at once was observed to perturb later cases' Qt
# Quick Layouts polish/relayout timing enough to make otherwise-passing
# scenarios flaky. One live engine at a time is enough for each test to
# outlive its own assertions.
_ENGINES: list[object] = []


class _RecordingOpener:
    def open_path(self, path: Path) -> None:
        pass


def _build_engine() -> tuple[QGuiApplication, QObject, QObject]:
    """One engine hosting real (non-null) controllers for all five screens."""
    _ENGINES.clear()
    # QML's parent/child and signal/slot connections form reference cycles
    # CPython's refcounting alone cannot break; without an explicit collect
    # the previous test's engine (and its whole window and StackLayout) can
    # survive well past `.clear()`, which is exactly the cross-test
    # interference this helper exists to avoid. The C++ side of a
    # `deleteLater()`'d QQuickItem also only actually goes away once the
    # event loop next spins, so a couple of `processEvents()` calls follow
    # the collect to let that finish too.
    gc.collect()
    app = QGuiApplication.instance() or QGuiApplication([])
    for _ in range(5):
        app.processEvents()
    session = ProjectSession(
        make_project_with_material(), Path("boost.inductor.json"), lambda project: None
    )
    material_repository = InMemoryMaterialRepository()
    material_repository.save(make_material_record(), {})
    guided = GuidedStudioController(session, CATALOG)
    core_material = CoreMaterialController(session, CATALOG, material_repository)
    preliminary = PreliminaryController(session, CATALOG)
    generation = GenerationController(lambda label, show: ("done",))
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
    _ENGINES.append((engine, guided, core_material, preliminary, simulation, review, generation))
    root = engine.rootObjects()[0]
    steps = root.findChild(QObject, "guidedStepList")
    return app, root, steps


def _settle(app: QGuiApplication, root: QObject, count: int = 10) -> None:
    for _ in range(count):
        app.processEvents()
    # The offscreen QPA platform has no screen to repaint, so nothing
    # guarantees `QQuickWindow`'s polish-and-sync pass (which is what
    # actually runs a dirty `ColumnLayout`'s re-arrange) ever runs just from
    # draining the event queue -- `grabWindow()` forces exactly that pass
    # synchronously. Without this, whether a Layout's pending re-arrange had
    # actually been applied by the time the test asserts depended on
    # incidental scheduling from *other* windows/timers in the process,
    # which is what made this test flaky before this call was added.
    root.grabWindow()
    for _ in range(count):
        app.processEvents()


def _go_to(app: QGuiApplication, steps: QObject, root: QObject, index: int) -> None:
    steps.setProperty("currentIndex", index)
    _settle(app, root)


def _overflowing_descendants(container: QObject, tolerance: float = 2.0) -> list[str]:
    """Every visible descendant of `container` whose right edge (mapped into
    `container`'s coordinate space) extends past `container`'s own width.
    """
    limit = container.property("width")
    violations: list[str] = []

    def walk(item: QObject) -> None:
        for child in item.childItems():
            # `visible` alone is not enough: the five screens hide their
            # inactive siblings with `opacity: 0` (see Main.qml), not
            # `visible: false`, so an invisible-to-the-user screen still
            # reports `visible == True`. Skip anything the user cannot
            # actually see, the same way a real overflow complaint would be
            # scoped to what is on screen.
            if not child.property("visible") or child.property("opacity") <= 0:
                continue
            origin = child.mapToItem(container, QPointF(0.0, 0.0))
            right_edge = origin.x() + child.property("width")
            if right_edge > limit + tolerance:
                label = child.property("objectName") or child.metaObject().className()
                violations.append(
                    f"{label}: right_edge={right_edge:.1f} > container_width={limit:.1f}"
                )
            walk(child)

    walk(container)
    return violations


@pytest.mark.parametrize("width", (NARROW_WIDTH, WIDE_WIDTH))
@pytest.mark.parametrize("index", range(5))
def test_screen_content_fits_the_context_panel_when_visited_first(
    index: int, width: int
) -> None:
    app, root, steps = _build_engine()
    root.setProperty("width", width)
    _go_to(app, steps, root, index)

    context_panel = root.findChild(QObject, "contextPanel")
    violations = _overflowing_descendants(context_panel)
    assert not violations, (
        f"{STEP_NAMES[index]} at width={width}, visited first: {violations}"
    )


@pytest.mark.parametrize("width", (NARROW_WIDTH, WIDE_WIDTH))
@pytest.mark.parametrize("index", range(5))
def test_screen_content_fits_the_context_panel_after_visiting_others(
    index: int, width: int
) -> None:
    app, root, steps = _build_engine()
    root.setProperty("width", width)
    _settle(app, root)
    for other in range(5):
        if other != index:
            _go_to(app, steps, root, other)
    _go_to(app, steps, root, index)

    context_panel = root.findChild(QObject, "contextPanel")
    violations = _overflowing_descendants(context_panel)
    assert not violations, (
        f"{STEP_NAMES[index]} at width={width}, visited after others: {violations}"
    )
