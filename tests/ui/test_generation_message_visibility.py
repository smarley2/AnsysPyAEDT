"""Finding 2 (review, 2026-08-10): long generation/status messages must be
fully readable, not clipped or overflowing.

The prior fix (commit 5ee9280) switched both messages from `elide:
Text.ElideRight` to `wrapMode: Text.WordWrap` so a long reason would wrap
instead of being truncated -- but neither container was resized to fit the
wrapped content:

- `simulationRunLog` in SimulationPanel.qml sized itself with
  `Layout.preferredHeight: Math.min(180, count * 22)`, which assumes exactly
  one 22px line per log entry. A single wrapped entry that is actually many
  lines tall gets a container far shorter than its wrapped content.
- The status-bar copy in Main.qml's `statusDock` is a fixed-height (50px)
  `Rectangle` with `clip: false`, so a long wrapped label overflows into
  surrounding UI instead of being contained.

This reproduces both with a realistic long stage-failure line of the shape
`generation_lines.py::_stage_lines` actually produces
(`f"{stage.name}: {'ok'/'FAILED'} - {stage.message}"`).
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
from PySide6.QtQuick import QQuickWindow  # noqa: E402, F401

from inductor_designer.simulation.capabilities import (  # noqa: E402
    AedtEdition,
    AedtRelease,
    CapabilityReviewStatus,
    CapabilitySnapshot,
)
from inductor_designer.ui.generation_controller import GenerationController  # noqa: E402
from inductor_designer.ui.generation_lines import UiRunRequest  # noqa: E402
from inductor_designer.ui.main import create_engine  # noqa: E402
from inductor_designer.ui.project_session import ProjectSession  # noqa: E402
from inductor_designer.ui.simulation_controller import SimulationController  # noqa: E402
from tests.ui.conftest import wait_until_idle  # noqa: E402
from tests.unit.domain.test_project import make_project  # noqa: E402

pytestmark = pytest.mark.ui

SUPPORTED = CapabilitySnapshot(
    release=AedtRelease(2025, 2),
    edition=AedtEdition.COMMERCIAL,
    include_dc_fields_3d=True,
    discovered_limits=(),
    evidence_source="test",
    review_status=CapabilityReviewStatus.REVIEWED,
)

LONG_STAGE_LINE = (
    "mesh: FAILED - the adaptive mesh refinement did not converge within the "
    "maximum number of adaptive passes; the reported percent error of 4.82% "
    "still exceeds the requested convergence criterion of 1.00% after 12 "
    "passes on this geometry, check the mesh intent and consider increasing "
    "the maximum passes or relaxing the convergence criterion before "
    "retrying the run"
)

# QQmlApplicationEngine owns the window it loads; pin the engine and every
# controller for the test process lifetime (same idiom as the other ui test
# modules, e.g. test_simulation_dc_bias_dialog.py).
_ENGINES: list[object] = []


def _settle(app: QGuiApplication, root: QObject, count: int = 10) -> None:
    for _ in range(count):
        app.processEvents()
    # grabWindow() forces the polish/re-arrange pass the offscreen QPA
    # platform otherwise never runs on its own (see
    # test_panel_layout_containment.py for the same idiom).
    root.grabWindow()
    for _ in range(count):
        app.processEvents()


def _build() -> tuple[QGuiApplication, QObject, GenerationController]:
    gc.collect()
    app = QGuiApplication.instance() or QGuiApplication([])
    for _ in range(5):
        app.processEvents()
    session = ProjectSession(make_project(), Path("boost.inductor.json"), lambda p: None)

    def runner(request: UiRunRequest) -> tuple[str, ...]:
        return (LONG_STAGE_LINE,)

    generation = GenerationController(runner)
    simulation = SimulationController(session, generation, SUPPORTED)
    engine = create_engine(
        simulation_controller=simulation,
        generation_controller=generation,
        project_session=session,
    )
    _ENGINES.clear()
    _ENGINES.append((engine, session, generation, simulation))
    root = engine.rootObjects()[0]
    root.setProperty("width", 1200)
    root.setProperty("height", 900)
    return app, root, generation


def _bottom_edge(item: QObject, ancestor: QObject) -> float:
    origin = item.mapToItem(ancestor, QPointF(0.0, 0.0))
    return float(origin.y() + item.property("height"))


def test_a_long_stage_failure_is_fully_visible_in_the_run_log() -> None:
    app, root, generation = _build()
    steps = root.findChild(QObject, "guidedStepList")
    steps.setProperty("currentIndex", 3)
    _settle(app, root)

    generation.generate("FEMM 2D", False)
    wait_until_idle(app, generation)
    _settle(app, root)

    view = root.findChild(QObject, "simulationRunLog")
    assert view is not None
    height = float(view.property("height"))
    content_height = float(view.property("contentHeight"))
    print(f"\nrun log: height={height} contentHeight={content_height}")

    # Bounded: a hundred log lines must never grow the layout without limit.
    assert height <= 180 + 1

    # The real defect: the old `count * 22` heuristic sized this view far
    # below its actual wrapped content (22px for this one long entry).
    assert height >= min(180.0, content_height) - 1, (
        f"height={height} content_height={content_height}: the container "
        "was not sized to its wrapped content"
    )

    if content_height > height + 1:
        # Bounded region: the rest of the message must still be reachable.
        assert view.property("interactive") is True, (
            f"content_height={content_height} exceeds height={height} but "
            "the view cannot be scrolled to reach the rest of the message"
        )


def test_a_long_status_message_does_not_overflow_the_status_dock() -> None:
    app, root, generation = _build()

    generation.generate("FEMM 2D", False)
    wait_until_idle(app, generation)
    _settle(app, root)

    dock = root.findChild(QObject, "statusDock")
    assert dock is not None
    dock_height = float(dock.property("height"))

    def walk(item: QObject) -> list[float]:
        edges: list[float] = []
        for child in item.childItems():
            if not child.property("visible"):
                continue
            edges.append(_bottom_edge(child, dock))
            edges.extend(walk(child))
        return edges

    bottom_edges = walk(dock)
    assert bottom_edges, "expected at least one descendant to measure"
    print(f"\nstatus dock: height={dock_height} max_child_bottom={max(bottom_edges)}")

    overflow = [edge for edge in bottom_edges if edge > dock_height + 1]
    assert not overflow, (
        f"content overflowed statusDock (height={dock_height}): {overflow}"
    )
