from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtGui import QGuiApplication  # noqa: E402

from inductor_designer.domain.winding import (  # noqa: E402
    ConductorMode,
    CurrentDirection,
)
from inductor_designer.ui.guided_studio_controller import (  # noqa: E402
    GuidedStudioController,
)
from inductor_designer.ui.preliminary_controller import (  # noqa: E402
    PreliminaryController,
)
from inductor_designer.ui.project_session import ProjectSession  # noqa: E402
from tests.unit.application.test_geometry_model import CATALOG  # noqa: E402
from tests.unit.domain.test_project import make_project, make_winding  # noqa: E402

pytestmark = pytest.mark.ui


class _CountingCatalog:
    """Wraps `CATALOG` and records every catalog call, to prove how many
    times the geometry model gets rebuilt for a single accepted edit."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def get_conductor(self, name: str) -> object:
        self.calls.append("get_conductor")
        return CATALOG.get_conductor(name)

    def list_conductor_names(self) -> tuple[str, ...]:
        self.calls.append("list_conductor_names")
        return CATALOG.list_conductor_names()

    def get_core(self, part_number: str) -> object:
        return CATALOG.get_core(part_number)

    def list_cores(self) -> tuple[object, ...]:
        return CATALOG.list_cores()


def test_editing_winding_rebuilds_real_preview_and_can_be_saved() -> None:
    app = QGuiApplication.instance() or QGuiApplication([])
    saved: list[object] = []
    session = ProjectSession(make_project(), Path("boost.inductor.json"), saved.append)
    controller = GuidedStudioController(session, CATALOG)
    before = controller.previewEntries[1].geometry

    assert app is not None
    assert [item["windingId"] for item in controller.windings] == ["w1"]
    assert controller.selectedWindingId == "w1"
    assert controller.dirty is False
    assert controller.windings[0]["acRmsCurrentA"] == 2.0

    assert controller.setWindingField("w1", "turns", "24") is True
    assert controller.setWindingField("w1", "acRmsCurrentA", "3.5") is True

    assert controller.windings[0]["turns"] == 24
    assert controller.windings[0]["acRmsCurrentA"] == 3.5
    assert controller.previewEntries[1].geometry is not before
    assert controller.dirty is True

    assert controller.saveDraft() is True
    assert saved and saved[0].design.windings[0].turns == 24
    assert saved[0].operating_point.windings[0].ac_rms_current_a == 3.5
    assert controller.dirty is False


def test_invalid_winding_edit_keeps_previous_geometry() -> None:
    app = QGuiApplication.instance() or QGuiApplication([])
    controller = GuidedStudioController(ProjectSession(make_project()), CATALOG)
    before = controller.previewEntries[1].geometry

    assert app is not None
    assert controller.setWindingField("w1", "turns", "0") is False

    assert controller.windings[0]["turns"] == 20
    assert controller.previewEntries[1].geometry is before
    assert "Unable to apply" in controller.statusMessage


def test_refresh_keeps_the_last_valid_preview_when_geometry_breaks() -> None:
    QGuiApplication.instance() or QGuiApplication([])
    session = ProjectSession(make_project())
    controller = GuidedStudioController(session, CATALOG)
    before = controller.previewEntries

    session.apply(
        replace(
            session.project,
            design=replace(
                session.project.design,
                windings=(replace(session.project.design.windings[0], turns=100000),),
            ),
        )
    )
    controller.refresh()

    assert controller.previewEntries is before
    assert controller.windings[0]["turns"] == 100000


def test_operating_point_is_shared_and_editable() -> None:
    QGuiApplication.instance() or QGuiApplication([])
    session = ProjectSession(make_project())
    controller = GuidedStudioController(session, CATALOG)

    assert controller.operatingPoint["frequencyHz"] == 100000.0
    assert controller.operatingPoint["windingTemperatureC"] == 20.0
    assert controller.operatingPoint["coreTemperatureC"] == 25.0

    assert controller.setOperatingPointField("frequencyHz", "250e3") is True
    assert controller.setOperatingPointField("windingTemperatureC", "85") is True
    assert controller.setOperatingPointField("coreTemperatureC", "100") is True

    assert session.project.operating_point.frequency_hz == 250000.0
    assert session.project.operating_point.winding_temperature_c == 85.0
    assert session.project.operating_point.core_temperature_c == 100.0
    assert controller.dirty is True


def test_operating_point_rejects_a_nonpositive_frequency() -> None:
    QGuiApplication.instance() or QGuiApplication([])
    session = ProjectSession(make_project())
    controller = GuidedStudioController(session, CATALOG)

    assert controller.setOperatingPointField("frequencyHz", "0") is False

    assert session.project.operating_point.frequency_hz == 100000.0
    assert controller.dirty is False
    assert "Unable to apply" in controller.statusMessage


def test_operating_point_rejects_an_unknown_field() -> None:
    QGuiApplication.instance() or QGuiApplication([])
    controller = GuidedStudioController(ProjectSession(make_project()), CATALOG)

    assert controller.setOperatingPointField("temperature", "20") is False


def test_every_winding_input_the_specification_lists_is_editable() -> None:
    QGuiApplication.instance() or QGuiApplication([])
    session = ProjectSession(make_project())
    controller = GuidedStudioController(session, CATALOG)

    assert controller.setWindingField("w1", "label", "Primary side") is True
    assert controller.setWindingField("w1", "mode", "stranded") is True
    assert controller.setWindingField("w1", "clearanceMm", "1.5") is True
    assert controller.setWindingField("w1", "dcCurrentA", "5.5") is True
    assert controller.setWindingField("w1", "currentDirection", "reverse") is True
    assert controller.setWindingField("w1", "terminalIntent", "start out") is True

    winding = session.project.design.windings[0]
    excitation = session.project.operating_point.windings[0]
    assert winding.label == "Primary side"
    assert winding.mode is ConductorMode.STRANDED
    assert winding.min_clearance_m == 0.0015
    assert winding.terminal_intent == "start out"
    assert excitation.dc_current_a == 5.5
    assert excitation.current_direction is CurrentDirection.REVERSE
    assert controller.windings[0]["dcCurrentA"] == 5.5
    assert controller.windings[0]["currentDirection"] == "reverse"
    assert controller.windings[0]["clearanceMm"] == 1.5
    assert controller.windings[0]["mode"] == "stranded"


def test_a_negative_dc_current_is_refused_by_the_domain() -> None:
    QGuiApplication.instance() or QGuiApplication([])
    session = ProjectSession(make_project())
    controller = GuidedStudioController(session, CATALOG)

    assert controller.setWindingField("w1", "dcCurrentA", "-1") is False

    assert session.project.operating_point.windings[0].dc_current_a == 5.0
    assert "Unable to apply" in controller.statusMessage


def test_enumerated_choices_and_conductor_names_come_from_the_controller() -> None:
    QGuiApplication.instance() or QGuiApplication([])
    controller = GuidedStudioController(ProjectSession(make_project()), CATALOG)

    assert controller.conductorNames == ["AWG 18"]
    assert controller.conductorModes == ["solid", "stranded"]
    assert controller.windingDirections == ["cw", "ccw"]
    assert controller.currentDirections == ["forward", "reverse"]


def test_adding_a_winding_allocates_a_definition_and_an_excitation() -> None:
    QGuiApplication.instance() or QGuiApplication([])
    session = ProjectSession(make_project())
    controller = GuidedStudioController(session, CATALOG)

    assert controller.addWinding() is True

    design = session.project.design
    excitations = session.project.operating_point.windings
    assert [item.winding_id for item in design.windings] == ["w1", "w2"]
    assert [item.winding_id for item in excitations] == ["w1", "w2"]
    added = design.windings[1]
    assert added.conductor_name == design.windings[0].conductor_name
    assert added.mode is design.windings[0].mode
    assert added.turns == 1
    assert excitations[1].ac_rms_current_a == 0.0
    assert excitations[1].dc_current_a == 0.0
    assert controller.selectedWindingId == "w2"
    assert len(controller.previewEntries) == 3


def test_a_new_winding_does_not_overlap_an_existing_sector() -> None:
    QGuiApplication.instance() or QGuiApplication([])
    session = ProjectSession(make_project())
    controller = GuidedStudioController(session, CATALOG)

    assert controller.addWinding() is True

    first, second = session.project.design.windings
    assert second.start_angle_deg >= first.start_angle_deg + first.sector_deg
    assert second.start_angle_deg + second.sector_deg <= 360.0


def test_a_full_core_refuses_another_winding() -> None:
    QGuiApplication.instance() or QGuiApplication([])
    full = make_winding(start_angle_deg=0.0, sector_deg=360.0)
    project = make_project(design=replace(make_project().design, windings=(full,)))
    controller = GuidedStudioController(ProjectSession(project), CATALOG)

    assert controller.addWinding() is False

    assert "no free sector" in controller.statusMessage


def test_removing_a_winding_drops_its_excitation_too() -> None:
    QGuiApplication.instance() or QGuiApplication([])
    session = ProjectSession(make_project())
    controller = GuidedStudioController(session, CATALOG)
    assert controller.addWinding() is True

    assert controller.removeWinding("w2") is True

    assert [item.winding_id for item in session.project.design.windings] == ["w1"]
    assert [
        item.winding_id for item in session.project.operating_point.windings
    ] == ["w1"]
    assert controller.selectedWindingId == "w1"


def test_the_last_winding_cannot_be_removed() -> None:
    QGuiApplication.instance() or QGuiApplication([])
    session = ProjectSession(make_project())
    controller = GuidedStudioController(session, CATALOG)

    assert controller.removeWinding("w1") is False

    assert len(session.project.design.windings) == 1
    assert "last winding" in controller.statusMessage


def test_removing_an_unknown_winding_changes_nothing() -> None:
    QGuiApplication.instance() or QGuiApplication([])
    session = ProjectSession(make_project())
    controller = GuidedStudioController(session, CATALOG)

    assert controller.removeWinding("w9") is False
    assert len(session.project.design.windings) == 1


def test_a_single_edit_builds_geometry_once_and_emits_each_signal_once() -> None:
    """Wired exactly as `main.py` wires it: `session.projectChanged` is
    connected to both this controller's `refresh` and a
    `PreliminaryController.refresh`, the same synchronous fan-out that let
    one accepted edit rebuild the geometry model a redundant second time and
    emit `windingsChanged` / `previewEntriesChanged` twice each."""
    QGuiApplication.instance() or QGuiApplication([])
    catalog = _CountingCatalog()
    session = ProjectSession(make_project())
    controller = GuidedStudioController(session, catalog)
    preliminary = PreliminaryController(session, catalog)
    session.projectChanged.connect(preliminary.refresh)
    session.projectChanged.connect(controller.refresh)

    windings_emits: list[None] = []
    preview_emits: list[None] = []
    controller.windingsChanged.connect(lambda: windings_emits.append(None))
    controller.previewEntriesChanged.connect(lambda: preview_emits.append(None))

    catalog.calls.clear()
    assert controller.setWindingField("w1", "turns", "24") is True

    assert len(windings_emits) == 1
    assert len(preview_emits) == 1
    # 2 catalog calls (list_conductor_names + get_conductor) for the
    # validation build inside setWindingField, plus whatever
    # PreliminaryController.refresh independently does for its own estimate
    # (also unaffected by this fix) -- not the 7 calls a redundant second
    # geometry-model build produced before the fix.
    assert len(catalog.calls) == 5

    assert controller.windings[0]["turns"] == 24
    assert session.project.design.windings[0].turns == 24
    assert controller.previewEntries[0].geometry is not None


def test_an_edit_applied_by_a_different_writer_still_refreshes_this_controller() -> None:
    """The guard must only silence a controller's echo of its own edit, not
    the `projectChanged` -> `refresh` connection itself. Applying directly
    through `session.apply`, as the Core & Material screen effectively does,
    is a different writer and must still refresh rows and preview here."""
    QGuiApplication.instance() or QGuiApplication([])
    session = ProjectSession(make_project())
    controller = GuidedStudioController(session, CATALOG)
    session.projectChanged.connect(controller.refresh)

    windings_emits: list[None] = []
    controller.windingsChanged.connect(lambda: windings_emits.append(None))

    session.apply(
        replace(
            session.project,
            design=replace(
                session.project.design,
                windings=(replace(session.project.design.windings[0], turns=42),),
            ),
        )
    )

    assert len(windings_emits) == 1
    assert controller.windings[0]["turns"] == 42
