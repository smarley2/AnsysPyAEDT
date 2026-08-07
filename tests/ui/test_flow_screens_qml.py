from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QSG_RHI_BACKEND", "software")

pytest.importorskip("PySide6")

from PySide6.QtCore import QObject  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

from inductor_designer.simulation.capabilities import (  # noqa: E402
    AedtEdition,
    AedtRelease,
    CapabilityReviewStatus,
    CapabilitySnapshot,
)
from inductor_designer.ui.generation_controller import GenerationController  # noqa: E402
from inductor_designer.ui.main import create_engine  # noqa: E402
from inductor_designer.ui.preliminary_controller import (  # noqa: E402
    PreliminaryController,
)
from inductor_designer.ui.project_session import ProjectSession  # noqa: E402
from inductor_designer.ui.review_controller import ReviewController  # noqa: E402
from inductor_designer.ui.simulation_controller import (  # noqa: E402
    SimulationController,
)
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


class RecordingOpener:
    def __init__(self) -> None:
        self.opened: list[Path] = []

    def open_path(self, path: Path) -> None:
        self.opened.append(path)


# QQmlApplicationEngine owns the window it loads: once the Python wrapper for
# the engine is garbage collected, the root window (and everything under it)
# is destroyed too, even though `root` is still referenced by the caller.
# Pin the engine and every controller passed to it for the test process
# lifetime instead of letting them drop the moment the helper returns (see
# tests/ui/test_winding_panel_qml.py for the same idiom).
_ENGINES: list[object] = []


def open_flow(
    step: int, *, dirty: bool = False
) -> tuple[QGuiApplication, QObject, ProjectSession]:
    app = QGuiApplication.instance() or QGuiApplication([])
    session = ProjectSession(
        make_project_with_material(), Path("boost.inductor.json"), lambda project: None
    )
    preliminary = PreliminaryController(session, CATALOG)
    generation = GenerationController(lambda label, show: ("done",))
    simulation = SimulationController(session, generation, SUPPORTED)
    review = ReviewController(
        session, preliminary, generation, CATALOG, RecordingOpener()
    )
    if dirty:
        session.apply(replace(session.project, description="edited"))
    engine = create_engine(
        preliminary_controller=preliminary,
        simulation_controller=simulation,
        review_controller=review,
        generation_controller=generation,
        project_session=session,
    )
    _ENGINES.append((engine, preliminary, generation, simulation, review))
    root = engine.rootObjects()[0]
    root.findChild(QObject, "guidedStepList").setProperty("currentIndex", step)
    app.processEvents()
    return app, root, session


def test_preliminary_page_shows_core_winding_totals_and_assumptions() -> None:
    _, root, _ = open_flow(2)

    for name in (
        "preliminaryPage",
        "preliminaryCoreTable",
        "preliminaryWindingTable",
        "preliminaryTotalsTable",
        "preliminaryAssumptions",
        "preliminaryMaterialLabel",
    ):
        assert root.findChild(QObject, name) is not None, name
    assert root.findChild(QObject, "preliminaryCoreTable").property("count") == 6
    assert root.findChild(QObject, "preliminaryTotalsTable").property("count") == 3
    assert (
        make_material_record().revision_id
        in root.findChild(QObject, "preliminaryMaterialLabel").property("text")
    )


def test_simulation_panel_exposes_every_run_choice() -> None:
    _, root, _ = open_flow(3)

    for name in (
        "simulationPanel",
        "simulationBackendCombo",
        "simulationModeLabel",
        "simulationMeshIntentCombo",
        "simulationMaximumPassesField",
        "simulationPercentErrorField",
        "simulationRequestedOutputs",
        "showSolverWindowCheckBox",
        "simulationGenerateButton",
    ):
        assert root.findChild(QObject, name) is not None, name
    assert root.findChild(QObject, "showSolverWindowCheckBox").property("enabled") is True


def test_generate_is_disabled_and_explained_while_the_project_is_dirty() -> None:
    _, root, _ = open_flow(3, dirty=True)

    assert root.findChild(QObject, "simulationGenerateButton").property("enabled") is False
    reason = root.findChild(QObject, "simulationBlockedReason")
    assert reason is not None
    assert "save" in reason.property("text").casefold()


def test_review_page_lists_sections_and_disabled_open_actions() -> None:
    _, root, _ = open_flow(4)

    for name in (
        "reviewPage",
        "reviewSections",
        "reviewFindings",
        "openGeneratedFileButton",
        "openRunFolderButton",
        "reviewMessage",
    ):
        assert root.findChild(QObject, name) is not None, name
    assert root.findChild(QObject, "reviewSections").property("count") == 5
    assert root.findChild(QObject, "openGeneratedFileButton").property("enabled") is False
    assert root.findChild(QObject, "openRunFolderButton").property("enabled") is False
