from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtGui import QGuiApplication  # noqa: E402

from inductor_designer.domain.project import RequestedOutput  # noqa: E402
from inductor_designer.simulation.capabilities import (  # noqa: E402
    AedtEdition,
    AedtRelease,
    CapabilityReviewStatus,
    CapabilitySnapshot,
)
from inductor_designer.ui.generation_controller import GenerationController  # noqa: E402
from inductor_designer.ui.project_session import ProjectSession  # noqa: E402
from inductor_designer.ui.simulation_controller import (  # noqa: E402
    SimulationController,
)
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


def build(
    *, dirty: bool = False, document: Path | None = Path("boost.inductor.json")
) -> tuple[
    ProjectSession,
    list[tuple[str, bool]],
    GenerationController,
    SimulationController,
]:
    QGuiApplication.instance() or QGuiApplication([])
    calls: list[tuple[str, bool]] = []

    def runner(backend_label: str, show_solver_window: bool) -> tuple[str, ...]:
        calls.append((backend_label, show_solver_window))
        return ("done",)

    session = ProjectSession(make_project(), document, lambda project: None)
    generation = GenerationController(runner)
    controller = SimulationController(session, generation, SUPPORTED)
    if dirty:
        session.apply(replace(session.project, description="edited"))
    return session, calls, generation, controller


def test_the_recipe_is_exposed_and_editable() -> None:
    session, _, _, controller = build()

    assert controller.backend == "Maxwell 3D"
    assert controller.backendOptions == ["Maxwell 3D", "Maxwell 2D (Ansys)", "FEMM 2D"]
    assert controller.meshIntentOptions == ["standard"]
    assert controller.maximumPasses == session.project.simulation_recipe.maximum_passes

    assert controller.setMaximumPasses("12") is True
    assert controller.setPercentError("0.5") is True

    assert session.project.simulation_recipe.maximum_passes == 12
    assert session.project.simulation_recipe.percent_error == 0.5


def test_an_invalid_recipe_value_is_refused_without_changing_the_project() -> None:
    session, _, _, controller = build()

    assert controller.setMaximumPasses("0") is False
    assert controller.setPercentError("-1") is False

    assert session.project.simulation_recipe.maximum_passes == 10
    assert session.project.simulation_recipe.percent_error == 1.0


def test_requested_outputs_toggle_into_the_recipe() -> None:
    session, _, _, controller = build()

    assert controller.toggleRequestedOutput(RequestedOutput.INDUCTANCE.value, True) is True

    assert RequestedOutput.INDUCTANCE in session.project.simulation_recipe.requested_outputs
    assert any(
        row["value"] == RequestedOutput.INDUCTANCE.value and row["selected"]
        for row in controller.requestedOutputs
    )

    # make_project() seeds RESISTANCE and INDUCTANCE; toggling INDUCTANCE off
    # must leave the untouched RESISTANCE entry alone rather than clearing it.
    assert controller.toggleRequestedOutput(RequestedOutput.INDUCTANCE.value, False) is True
    assert session.project.simulation_recipe.requested_outputs == (RequestedOutput.RESISTANCE,)


def test_the_run_mode_is_generate_only_with_a_stated_reason() -> None:
    _, _, _, controller = build()

    assert controller.modeLabel == "generate-only"
    assert "M8" in controller.modeNote or "solve" in controller.modeNote.casefold()


def test_visible_window_support_follows_the_backend() -> None:
    _, _, _, controller = build()

    assert controller.visibleWindowSupported is True
    assert controller.visibleWindowReason == ""

    assert controller.setBackend("FEMM 2D") is True
    assert controller.visibleWindowSupported is True


def test_an_unsupported_visible_window_is_disabled_with_a_reason() -> None:
    QGuiApplication.instance() or QGuiApplication([])
    # include_dc_fields_3d=True is refused before 2025 R1 by
    # CapabilitySnapshot.__post_init__, so it must be cleared alongside the
    # older release to build a valid (if unsupported) snapshot.
    unsupported = replace(
        SUPPORTED, release=AedtRelease(2024, 2), include_dc_fields_3d=False
    )
    session = ProjectSession(make_project(), Path("boost.inductor.json"), lambda p: None)
    controller = SimulationController(
        session, GenerationController(lambda label, show: ("done",)), unsupported
    )

    assert controller.setBackend("Maxwell 3D") is True

    assert controller.visibleWindowSupported is False
    assert controller.visibleWindowReason != ""
    assert controller.setShowSolverWindow(True) is False
    assert controller.showSolverWindow is False


def test_generation_is_blocked_while_the_project_has_unsaved_edits() -> None:
    session, calls, _, controller = build(dirty=True)

    assert controller.canGenerate is False
    assert "save" in controller.blockedReason.casefold()
    assert controller.generate() is False
    assert calls == []

    assert session.saveProject() is True

    assert controller.canGenerate is True
    assert controller.blockedReason == ""


def test_generation_is_blocked_without_a_document_path() -> None:
    QGuiApplication.instance() or QGuiApplication([])
    session = ProjectSession(make_project())
    controller = SimulationController(
        session, GenerationController(lambda label, show: ("done",)), SUPPORTED
    )

    assert controller.canGenerate is False
    assert "document path" in controller.blockedReason.casefold()


def test_generating_passes_the_backend_and_the_visibility_choice() -> None:
    app = QGuiApplication.instance() or QGuiApplication([])
    _, calls, generation, controller = build()
    controller.setBackend("FEMM 2D")
    controller.setShowSolverWindow(True)

    assert controller.generate() is True
    wait_until_idle(app, generation)

    assert calls == [("FEMM 2D", True)]
