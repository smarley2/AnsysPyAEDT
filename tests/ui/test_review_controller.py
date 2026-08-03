from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtGui import QGuiApplication  # noqa: E402

from inductor_designer.ui.generation_controller import GenerationController  # noqa: E402
from inductor_designer.ui.preliminary_controller import (  # noqa: E402
    PreliminaryController,
)
from inductor_designer.ui.project_session import ProjectSession  # noqa: E402
from inductor_designer.ui.review_controller import ReviewController  # noqa: E402
from tests.unit.application.test_geometry_model import CATALOG  # noqa: E402
from tests.unit.domain.test_project import (  # noqa: E402
    make_material_record,
    make_project_with_material,
)

pytestmark = pytest.mark.ui


class RecordingOpener:
    def __init__(self) -> None:
        self.opened: list[Path] = []

    def open_path(self, path: Path) -> None:
        self.opened.append(path)


def build() -> tuple[RecordingOpener, GenerationController, ReviewController]:
    QGuiApplication.instance() or QGuiApplication([])
    session = ProjectSession(make_project_with_material(), Path("boost.inductor.json"))
    generation = GenerationController(lambda label, show: ("done",))
    opener = RecordingOpener()
    controller = ReviewController(
        session,
        PreliminaryController(session, CATALOG),
        generation,
        CATALOG,
        opener,
    )
    return opener, generation, controller


def test_review_shows_the_paired_core_material_operating_point_and_estimates() -> None:
    _, _, controller = build()

    titles = [section["title"] for section in controller.sections]
    assert titles == [
        "Core and material",
        "Shared operating point",
        "Winding excitations",
        "Preliminary estimates",
        "Run request",
    ]
    assert any(
        make_material_record().revision_id in row["text"]
        for section in controller.sections
        for row in section["rows"]
    )
    assert any(
        row["label"] == "Total wire loss"
        for section in controller.sections
        for row in section["rows"]
    )


def test_review_lists_validation_findings() -> None:
    _, _, controller = build()

    assert all(
        set(finding) == {"category", "code", "message"} for finding in controller.findings
    )


def test_open_actions_are_disabled_before_a_run() -> None:
    opener, _, controller = build()

    assert controller.canOpenGeneratedFile is False
    assert controller.canOpenRunFolder is False
    assert controller.openGeneratedFile() is False
    assert controller.openRunFolder() is False
    assert opener.opened == []
    assert "no generated" in controller.message.casefold()


def test_open_actions_use_the_last_run_evidence(tmp_path: Path) -> None:
    opener, generation, controller = build()
    run_directory = tmp_path / "runs" / "20260730-101500-femm"
    run_directory.mkdir(parents=True)
    generated = run_directory / "inductor.fem"
    generated.write_text("", encoding="utf-8")
    generation.record_run_evidence(run_directory, generated)
    controller.refresh()

    assert controller.canOpenGeneratedFile is True
    assert controller.canOpenRunFolder is True
    assert controller.openGeneratedFile() is True
    assert controller.openRunFolder() is True

    assert opener.opened == [generated, run_directory]


def test_an_opener_failure_is_reported_not_raised(tmp_path: Path) -> None:
    QGuiApplication.instance() or QGuiApplication([])
    session = ProjectSession(make_project_with_material(), Path("boost.inductor.json"))
    generation = GenerationController(lambda label, show: ("done",))

    class Failing:
        def open_path(self, path: Path) -> None:
            raise OSError("no association")

    controller = ReviewController(
        session,
        PreliminaryController(session, CATALOG),
        generation,
        CATALOG,
        Failing(),
    )
    run_directory = tmp_path / "runs" / "20260730-101500-femm"
    run_directory.mkdir(parents=True)
    generation.record_run_evidence(run_directory, None)

    assert controller.openRunFolder() is False
    assert "no association" in controller.message


def test_an_opener_runtime_error_is_reported_not_raised(tmp_path: Path) -> None:
    """The one production `PathOpener`, `DesktopPathOpener`, raises `RuntimeError`
    from `_shell_launcher()` on any non-`win32` platform -- exactly what the
    Linux CI quality job runs on.
    """
    QGuiApplication.instance() or QGuiApplication([])
    session = ProjectSession(make_project_with_material(), Path("boost.inductor.json"))
    generation = GenerationController(lambda label, show: ("done",))

    class Failing:
        def open_path(self, path: Path) -> None:
            raise RuntimeError(
                "Opening a path from the application is supported on Windows only."
            )

    controller = ReviewController(
        session,
        PreliminaryController(session, CATALOG),
        generation,
        CATALOG,
        Failing(),
    )
    run_directory = tmp_path / "runs" / "20260730-101500-femm"
    run_directory.mkdir(parents=True)
    generation.record_run_evidence(run_directory, None)

    assert controller.openRunFolder() is False
    assert "Windows only" in controller.message


def test_review_refreshes_after_preliminary_catches_up_to_an_edit() -> None:
    """Finding 2 (M7c final review): `ReviewController.__init__` connects
    `session.projectChanged` to its own `refresh` BEFORE `main.py` connects
    `preliminary_controller.refresh` to the same signal. Qt fires connections
    in registration order, so on every edit Review re-renders while
    Preliminary's row cache still holds the pre-edit values. Wire the
    controllers exactly as `main.py` does (including the ordering) and prove
    Review eventually reflects the fresh estimate rather than staying stuck
    one edit behind.
    """
    QGuiApplication.instance() or QGuiApplication([])
    session = ProjectSession(make_project_with_material())
    generation = GenerationController(lambda label, show: ("done",))
    preliminary = PreliminaryController(session, CATALOG)
    controller = ReviewController(
        session, preliminary, generation, CATALOG, RecordingOpener()
    )
    # Replicates main.py's `session.projectChanged.connect(preliminary_controller.refresh)`,
    # which is registered after ReviewController's own constructor already
    # connected `session.projectChanged` to `self.refresh` above.
    session.projectChanged.connect(preliminary.refresh)

    def total_wire_loss_text() -> str:
        return next(
            row["text"]
            for section in controller.sections
            for row in section["rows"]
            if row["label"] == "Total wire loss"
        )

    # Captured inside the reviewChanged handler, the way a QML binding would
    # re-read the property each time the signal fires -- not read cold
    # afterward, which would already see Preliminary's updated cache.
    snapshots: list[str] = []
    controller.reviewChanged.connect(lambda: snapshots.append(total_wire_loss_text()))

    before = total_wire_loss_text()
    session.apply(
        replace(
            session.project,
            operating_point=replace(
                session.project.operating_point,
                windings=(
                    replace(
                        session.project.operating_point.windings[0],
                        ac_rms_current_a=8.0,
                    ),
                ),
            ),
        )
    )

    assert snapshots, "reviewChanged never fired after the edit"
    assert snapshots[-1] != before
