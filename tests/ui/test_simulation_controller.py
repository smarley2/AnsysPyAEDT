from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtGui import QGuiApplication  # noqa: E402

from inductor_designer.adapters.system.installations import (  # noqa: E402
    AedtInstallation,
    DetectionRoute,
    UnsupportedAedtInstallation,
)
from inductor_designer.domain.project import RequestedOutput  # noqa: E402
from inductor_designer.simulation.capabilities import (  # noqa: E402
    AedtEdition,
    AedtRelease,
    CapabilityReviewStatus,
    CapabilitySnapshot,
)
from inductor_designer.ui.generation_controller import GenerationController  # noqa: E402
from inductor_designer.ui.generation_lines import UiRunRequest  # noqa: E402
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
    *,
    dirty: bool = False,
    document: Path | None = Path("boost.inductor.json"),
    dc_current_a: float | None = None,
    aedt_installation: AedtInstallation | None = None,
    unsupported_aedt_installation: UnsupportedAedtInstallation | None = None,
) -> tuple[
    ProjectSession,
    list[tuple[str, bool]],
    GenerationController,
    SimulationController,
]:
    QGuiApplication.instance() or QGuiApplication([])
    calls: list[tuple[str, bool]] = []

    def runner(request: UiRunRequest) -> tuple[str, ...]:
        calls.append((request.backend_label, request.show_solver_window))
        return ("done",)

    # make_project()'s default winding already carries 5 A DC; dc_current_a
    # only needs overriding to build the DC-free case.
    project = make_project()
    if dc_current_a is not None:
        project = replace(
            project,
            operating_point=replace(
                project.operating_point,
                windings=(
                    replace(
                        project.operating_point.windings[0], dc_current_a=dc_current_a
                    ),
                ),
            ),
        )
    session = ProjectSession(project, document, lambda project: None)
    generation = GenerationController(runner)
    controller = SimulationController(
        session,
        generation,
        SUPPORTED,
        aedt_installation,
        unsupported_aedt_installation,
    )
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


def test_the_run_mode_defaults_to_generate_only_with_a_stated_reason() -> None:
    _, _, _, controller = build()

    assert controller.modeLabel == "generate-only"
    assert controller.modeOptions == ["generate-only", "generate-and-solve"]
    assert "solve" in controller.modeNote.casefold()

    assert controller.setMode("generate-and-solve") is True
    assert "normalized results" in controller.modeNote.casefold()


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
        session, GenerationController(lambda _request: ("done",)), unsupported
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
        session, GenerationController(lambda _request: ("done",)), SUPPORTED
    )

    assert controller.canGenerate is False
    assert "document path" in controller.blockedReason.casefold()


def test_generating_passes_the_backend_and_the_visibility_choice() -> None:
    app = QGuiApplication.instance() or QGuiApplication([])
    _, calls, generation, controller = build(dc_current_a=0.0)
    controller.setBackend("FEMM 2D")
    controller.setShowSolverWindow(True)

    assert controller.generate() is True
    wait_until_idle(app, generation)

    assert calls == [("FEMM 2D", True)]


# make_project()'s default winding carries 5 A DC (tests/unit/domain/test_project.py),
# matching Fabio Posser's exact reported scenario. Maxwell 3D applies it
# natively under SUPPORTED, so only switching to a 2D/FEMM backend triggers
# the AC-only confirmation gate (decision: Fabio Posser, 2026-08-07).


def test_no_dc_bias_dialog_is_needed_when_the_backend_applies_dc_natively() -> None:
    _, _, _, controller = build()

    assert controller.dcBiasIgnored is False
    assert controller.dcBiasNotice == ""


def test_switching_to_a_2d_or_femm_backend_reports_the_dc_bias_would_be_ignored() -> None:
    _, _, _, controller = build()

    assert controller.setBackend("Maxwell 2D (Ansys)") is True
    assert controller.dcBiasIgnored is True
    assert "AC-only" in controller.dcBiasNotice or "AC" in controller.dcBiasNotice

    assert controller.setBackend("FEMM 2D") is True
    assert controller.dcBiasIgnored is True


def test_a_dc_free_project_never_triggers_the_dialog_on_a_2d_or_femm_backend() -> None:
    _, _, _, controller = build(dc_current_a=0.0)

    assert controller.setBackend("FEMM 2D") is True
    assert controller.dcBiasIgnored is False
    assert controller.dcBiasNotice == ""


def test_generate_refuses_to_start_an_unconfirmed_ac_only_run() -> None:
    _, calls, _, controller = build()
    controller.setBackend("FEMM 2D")

    assert controller.dcBiasIgnored is True
    assert controller.generate() is False
    assert calls == []


def test_proceed_ac_only_starts_the_run_after_confirmation() -> None:
    app = QGuiApplication.instance() or QGuiApplication([])
    _, calls, generation, controller = build()
    controller.setBackend("FEMM 2D")

    assert controller.generate() is False
    assert controller.proceedAcOnly() is True
    wait_until_idle(app, generation)

    assert calls == [("FEMM 2D", False)]


# Finding 1 (review, 2026-08-10): proceedAcOnly() must only authorise the run
# a refused generate() actually warned about -- naming the backend that was
# pending, not just "some generate() was refused at some point" -- so a
# caller that skips the dialog (a shortcut, a second dialog, MCP automation)
# cannot start an unconfirmed AC-only run.


def test_proceed_ac_only_without_a_pending_confirmation_refuses() -> None:
    _, calls, _, controller = build()
    controller.setBackend("FEMM 2D")

    assert controller.proceedAcOnly() is False
    assert calls == []


def test_proceed_ac_only_refuses_once_the_backend_no_longer_matches() -> None:
    _, calls, _, controller = build()
    controller.setBackend("FEMM 2D")
    assert controller.generate() is False

    assert controller.setBackend("Maxwell 2D (Ansys)") is True
    assert controller.proceedAcOnly() is False
    assert calls == []


def test_a_second_proceed_ac_only_after_a_successful_run_refuses() -> None:
    app = QGuiApplication.instance() or QGuiApplication([])
    _, calls, generation, controller = build()
    controller.setBackend("FEMM 2D")
    assert controller.generate() is False

    assert controller.proceedAcOnly() is True
    wait_until_idle(app, generation)

    assert controller.proceedAcOnly() is False
    assert calls == [("FEMM 2D", False)]


# M10 Task 2: the detected AEDT target, if any, is visible before a run is
# started -- an unsupported release or an absent one calls for a different
# remedy than a failed run's own advice, and must be visible earlier.


def test_aedt_status_notice_is_silent_when_femm_is_selected() -> None:
    _, _, _, controller = build()
    controller.setBackend("FEMM 2D")

    assert controller.aedtStatusNotice == ""


def test_aedt_status_notice_is_silent_when_the_supported_release_is_installed() -> None:
    installed = AedtInstallation(
        AedtRelease(2025, 2), Path("C:/Program Files/ANSYS Inc"), DetectionRoute.STANDARD_LOCATION
    )
    _, _, _, controller = build(aedt_installation=installed)

    assert controller.aedtStatusNotice == ""


def test_aedt_status_notice_names_an_unsupported_release_found() -> None:
    found = UnsupportedAedtInstallation(
        AedtRelease(2024, 2), Path("C:/Program Files/ANSYS Inc"), DetectionRoute.REGISTRY
    )
    _, _, _, controller = build(unsupported_aedt_installation=found)

    notice = controller.aedtStatusNotice
    assert "2024.2" in notice
    assert "2025.2" in notice


def test_aedt_status_notice_reports_absence_when_nothing_was_found() -> None:
    _, _, _, controller = build()

    notice = controller.aedtStatusNotice
    assert "not found" in notice
    assert "2025.2" in notice


def test_aedt_status_notice_updates_when_the_backend_changes() -> None:
    _, _, _, controller = build()
    assert controller.aedtStatusNotice != ""

    assert controller.setBackend("FEMM 2D") is True

    assert controller.aedtStatusNotice == ""
