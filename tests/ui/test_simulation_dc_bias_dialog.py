"""AC-only confirmation for a 2D/FEMM backend on a DC-biased project.

Decision: Fabio Posser, 2026-08-07. Maxwell 2D and FEMM linearize about zero
bias and cannot carry a DC premagnetization into an AC solve, so instead of
refusing outright (the old `BLOCKED` behavior) the run proceeds AC-only after
an explicit confirmation. These tests exercise the real QML wiring: clicking
`simulationGenerateButton` opens `dcBiasConfirmDialog` when the project has a
nonzero DC winding current, Cancel starts nothing, and Proceed runs.
"""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QSG_RHI_BACKEND", "software")

pytest.importorskip("PySide6")

from PySide6.QtCore import QMetaObject, QObject  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtQuick import QQuickWindow  # noqa: E402, F401

from inductor_designer.simulation.capabilities import (  # noqa: E402
    AedtEdition,
    AedtRelease,
    CapabilityReviewStatus,
    CapabilitySnapshot,
)
from inductor_designer.ui.generation_controller import GenerationController  # noqa: E402
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

# QQmlApplicationEngine owns the window it loads; pin the engine and every
# controller for the test process lifetime (same idiom as
# test_flow_screens_qml.py and test_main_close_dialog.py).
_ENGINES: list[object] = []


def _click(button: object) -> None:
    assert QMetaObject.invokeMethod(button, "clicked") is True


def open_simulation_step(
    *, dc_current_a: float
) -> tuple[QGuiApplication, QObject, list[tuple[str, bool]], GenerationController]:
    app = QGuiApplication.instance() or QGuiApplication([])
    project = make_project()
    project = replace(
        project,
        operating_point=replace(
            project.operating_point,
            windings=(
                replace(project.operating_point.windings[0], dc_current_a=dc_current_a),
            ),
        ),
    )
    session = ProjectSession(project, Path("boost.inductor.json"), lambda p: None)
    calls: list[tuple[str, bool]] = []

    def runner(backend_label: str, show_solver_window: bool) -> tuple[str, ...]:
        calls.append((backend_label, show_solver_window))
        return ("done",)

    generation = GenerationController(runner)
    simulation = SimulationController(session, generation, SUPPORTED)
    engine = create_engine(
        simulation_controller=simulation,
        generation_controller=generation,
        project_session=session,
    )
    _ENGINES.append((engine, session, generation, simulation))
    root = engine.rootObjects()[0]
    root.findChild(QObject, "guidedStepList").setProperty("currentIndex", 3)
    assert simulation.setBackend("FEMM 2D") is True
    app.processEvents()
    return app, root, calls, generation


def test_dc_biased_project_opens_the_dialog_and_cancel_starts_nothing() -> None:
    app, root, calls, _generation = open_simulation_step(dc_current_a=5.0)

    _click(root.findChild(QObject, "simulationGenerateButton"))
    app.processEvents()

    dialog = root.findChild(QObject, "dcBiasConfirmDialog")
    assert dialog is not None
    assert dialog.property("visible") is True
    message = root.findChild(QObject, "dcBiasConfirmMessage")
    assert "AC" in message.property("text")

    _click(root.findChild(QObject, "dcBiasConfirmCancelButton"))
    app.processEvents()

    assert dialog.property("visible") is False
    assert calls == []


def test_proceeding_from_the_dialog_starts_an_ac_only_run() -> None:
    app, root, calls, generation = open_simulation_step(dc_current_a=5.0)

    _click(root.findChild(QObject, "simulationGenerateButton"))
    app.processEvents()
    _click(root.findChild(QObject, "dcBiasConfirmProceedButton"))
    app.processEvents()
    wait_until_idle(app, generation)

    assert calls == [("FEMM 2D", False)]


def test_a_dc_free_project_never_shows_the_dialog_and_generates_directly() -> None:
    app, root, calls, generation = open_simulation_step(dc_current_a=0.0)

    _click(root.findChild(QObject, "simulationGenerateButton"))
    app.processEvents()

    dialog = root.findChild(QObject, "dcBiasConfirmDialog")
    assert dialog.property("visible") is False
    wait_until_idle(app, generation)

    assert calls == [("FEMM 2D", False)]
