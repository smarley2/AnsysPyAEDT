"""Regression test for Fabio's "context panel content is far wider than the
panel" report: labels clipped, input fields pushed off the right edge.

Three independent, unrelated mechanisms were found and fixed, and this test
guards all three. Screen visit order ("visited while hidden") was an early
hypothesis but was directly refuted (the first mechanism below reproduced
with `CoreMaterialPanel` fully visible from the moment it was constructed, in
a standalone instance with no `Main.qml`, no `StackLayout`, and no controller
at all) -- so this test does not key its scenarios off visit order for its
own sake, only because the second mechanism happens to be sensitive to it:

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
3. The first round's version of this test measured every screen's content
   against `contextPanel`'s own width. That boundary is wrong: each screen's
   content sits inside a `ScrollView`, and a `ScrollView`'s vertical
   scrollbar is an overlay that does not shrink `contextPanel` -- it only
   shrinks the `ScrollView`'s own `availableWidth` once there is enough
   content to need scrolling. Every one of the five screens sized its inner
   `ColumnLayout` off the *panel's* width minus a hand-picked constant
   (`windingsPanel.width - 24`) rather than the `ScrollView`'s
   `availableWidth`, so a field could satisfy the old (too-loose)
   `contextPanel`-width test while still being visually clipped or hidden
   behind the scrollbar -- exactly what Fabio's Windings screenshot showed.
   Fixed by giving every screen's `ScrollView` an `id` and binding its
   `ColumnLayout`'s `width` to that `ScrollView`'s own `availableWidth`,
   mirroring the pattern `MaterialStudioPage.qml` already used correctly.

This walks every visible descendant of each screen's `ScrollView` and
asserts none of them extends past that `ScrollView`'s own `availableWidth`
(not `contextPanel`'s width), for each of the five screens, at a narrow and
a wide window width, with the vertical scrollbar both absent (content
shorter than the viewport) and present (content taller than the viewport),
and both when the screen is the first one visited and after visiting others
first.
"""

from __future__ import annotations

import gc
import os
import sys
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

# Windows-only: this test asserts on exact pixel geometry, and both of its
# inputs are platform-specific. The Qt Quick Controls style differs (the
# Windows style's vertical `ScrollBar` is 17px wide, the Basic style Linux
# falls back to is 8px), and so do the default font metrics, which decide how
# tall each screen's content is and therefore whether a vertical scrollbar is
# there at all at the heights below. On Linux the same code reports overflows
# of 3-9px that no Windows user can see. The application only runs on Windows
# (Ansys AEDT and FEMM are Windows-only), so the containment guard is kept
# where it describes something real rather than being retuned per platform.
pytestmark = [
    pytest.mark.ui,
    pytest.mark.skipif(
        sys.platform != "win32",
        reason="pixel-exact layout assertions are tuned to the Windows Qt style and fonts",
    ),
]

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

# Window heights chosen (see scratchpad probing during development) so that,
# at both NARROW_WIDTH and WIDE_WIDTH, every one of the five screens' own
# `ScrollView` reports no vertical scrollbar reserve at ROOMY_HEIGHT
# (`availableWidth == width`) and a reserve at CRAMPED_HEIGHT
# (`availableWidth < width`) -- one pair of heights that reliably exercises
# both the "no scrollbar" and "scrollbar visible" cases across all five
# screens' differing content lengths, rather than a bespoke height per
# screen. This deliberately goes below `window.minimumHeight` (700):
# `minimumHeight` only constrains interactive resizing, and setting `height`
# directly (like `width` above, at `NARROW_WIDTH` == `minimumWidth`) is the
# same idiom the rest of this file already relies on to reach a specific
# layout state under the offscreen QPA platform.
ROOMY_HEIGHT = 1119  # no screen's content needs to scroll
CRAMPED_HEIGHT = 300  # every screen's content needs to scroll

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


def _scroll_view_of(panel: QObject) -> QObject:
    """The screen's own `ScrollView`.

    Found by walking the panel's direct children for the control's class
    name, not by `objectName` -- the fix under test is precisely what gives
    each screen's `ScrollView` an `id`/`objectName`, and this lookup has to
    work identically whether or not that fix is present so the "this test
    fails on the old code" claim is about the boundary the test checks, not
    about infrastructure the fix happens to add.
    """
    for child in panel.children():
        if "ScrollView" in child.metaObject().className():
            return child
    raise AssertionError(f"{panel.objectName()} has no ScrollView")


def _overflowing_descendants(scroll_view: QObject, tolerance: float = 2.0) -> list[str]:
    """Every visible descendant of `scroll_view` whose right edge (mapped
    into `scroll_view`'s own coordinate space) extends past `scroll_view`'s
    `availableWidth` -- the correct containment boundary. `contextPanel`'s
    width is not: it does not shrink when the vertical scrollbar appears, so
    content can satisfy a `contextPanel`-width check while still sitting
    under the scrollbar.
    """
    limit = scroll_view.property("availableWidth")
    violations: list[str] = []

    def walk(item: QObject) -> None:
        for child in item.childItems():
            if "ScrollBar" in child.metaObject().className():
                # The scrollbar itself (and its internal handle/track items)
                # lives in the band `availableWidth` reserves for it -- it is
                # the thing content must stay clear of, not content itself.
                continue
            # `visible` alone is not enough: the five screens hide their
            # inactive siblings with `opacity: 0` (see Main.qml), not
            # `visible: false`, so an invisible-to-the-user screen still
            # reports `visible == True`. Skip anything the user cannot
            # actually see, the same way a real overflow complaint would be
            # scoped to what is on screen.
            if not child.property("visible") or child.property("opacity") <= 0:
                continue
            origin = child.mapToItem(scroll_view, QPointF(0.0, 0.0))
            right_edge = origin.x() + child.property("width")
            if right_edge > limit + tolerance:
                label = child.property("objectName") or child.metaObject().className()
                violations.append(
                    f"{label}: right_edge={right_edge:.1f} > available_width={limit:.1f}"
                )
            walk(child)

    walk(scroll_view)
    return violations


@pytest.mark.parametrize("height", (ROOMY_HEIGHT, CRAMPED_HEIGHT))
@pytest.mark.parametrize("width", (NARROW_WIDTH, WIDE_WIDTH))
@pytest.mark.parametrize("index", range(5))
def test_screen_content_fits_the_scroll_view_when_visited_first(
    index: int, width: int, height: int
) -> None:
    app, root, steps = _build_engine()
    root.setProperty("width", width)
    root.setProperty("height", height)
    _go_to(app, steps, root, index)

    panel = root.findChild(QObject, STEP_NAMES[index])
    scroll_view = _scroll_view_of(panel)
    violations = _overflowing_descendants(scroll_view)
    assert not violations, (
        f"{STEP_NAMES[index]} at width={width}, height={height}, visited first: "
        f"{violations}"
    )


@pytest.mark.parametrize("height", (ROOMY_HEIGHT, CRAMPED_HEIGHT))
@pytest.mark.parametrize("width", (NARROW_WIDTH, WIDE_WIDTH))
@pytest.mark.parametrize("index", range(5))
def test_screen_content_fits_the_scroll_view_after_visiting_others(
    index: int, width: int, height: int
) -> None:
    app, root, steps = _build_engine()
    root.setProperty("width", width)
    root.setProperty("height", height)
    _settle(app, root)
    for other in range(5):
        if other != index:
            _go_to(app, steps, root, other)
    _go_to(app, steps, root, index)

    panel = root.findChild(QObject, STEP_NAMES[index])
    scroll_view = _scroll_view_of(panel)
    violations = _overflowing_descendants(scroll_view)
    assert not violations, (
        f"{STEP_NAMES[index]} at width={width}, height={height}, "
        f"visited after others: {violations}"
    )
