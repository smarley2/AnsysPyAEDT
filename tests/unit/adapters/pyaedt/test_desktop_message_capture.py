"""AEDT's message channel is captured into the application log at the stage
failure boundary, while the session that knows it still exists.

Verifies: a failed stage writes every channel line to the log; a raising
channel leaves the original stage error and the run's own diagnostic
unchanged; the captured lines reach the log through the redacting formatter
rather than around it; every one of the eight failure boundaries in both
adapters reads the channel, the analyze one included, since that is the
boundary the 2026-08-18 incident travelled through.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest

from inductor_designer.adapters.pyaedt.maxwell2d import PyaedtMaxwell2dExporter
from inductor_designer.adapters.pyaedt.maxwell3d import PyaedtMaxwell3dExporter
from inductor_designer.adapters.system.app_logging import (
    LOGGER_NAME,
    configure_application_logging,
)
from inductor_designer.application.ports.maxwell_exporter import (
    Maxwell3dExportRequest,
    Maxwell3dGeometryOnlyRequest,
)
from inductor_designer.application.services.redaction import RedactionContext
from inductor_designer.domain.aedt_target import AedtEdition, AedtRelease
from inductor_designer.simulation.plan_builder import build_geometry_only_maxwell3d_plan
from tests.contract.test_maxwell2d_exporter_contract import (
    make_request as make_2d_request,
)
from tests.fakes.maxwell2d_app import FakeMaxwell2dApp, FakeMaxwell2dAppFactory
from tests.fakes.maxwell3d_app import FakeMaxwell3dApp, FakeMaxwell3dAppFactory
from tests.unit.simulation.test_plan_builder import (
    BARE,
    CORE,
    build,
    make_definition,
    pack,
)

pytestmark = pytest.mark.usefixtures("fake_maxwell_boundary")


def make_request(tmp_path: Path) -> Maxwell3dExportRequest:
    return Maxwell3dExportRequest(
        plan=build((make_definition(),)),  # type: ignore[arg-type]
        release=AedtRelease(2025, 2),
        edition=AedtEdition.COMMERCIAL,
        non_graphical=True,
        output_directory=tmp_path / "out",
        project_name="Boost_inductor",
    )


def run(tmp_path: Path, app: FakeMaxwell3dApp) -> object:
    exporter = PyaedtMaxwell3dExporter(app_factory=FakeMaxwell3dAppFactory(app))
    return exporter.export(make_request(tmp_path))


@pytest.fixture(autouse=True)
def _reset_logger() -> None:
    # Mirrors adapters/system/test_app_logging.py: each test gets its own
    # handler pointed at its own tmp_path, so tests must not leak handlers.
    yield
    logger = logging.getLogger(LOGGER_NAME)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()


def test_failed_stage_writes_every_channel_line_to_the_log(tmp_path: Path) -> None:
    log_path = configure_application_logging(tmp_path / "logs", RedactionContext())
    app = FakeMaxwell3dApp(raise_on="AssignMatrix")
    app.desktop_message_lines = (
        "Unable to create child process: 3dedy. Please contact Ansys technical support.",
        "Simulation completed with execution error on server: Local Machine.",
    )

    result = run(tmp_path, app)

    assert result.stages[-2].name == "matrix"  # type: ignore[attr-defined]
    assert result.stages[-2].succeeded is False  # type: ignore[attr-defined]
    logging.getLogger(LOGGER_NAME).handlers[0].flush()
    written = log_path.read_text(encoding="utf-8")
    for line in app.desktop_message_lines:
        assert line in written
        assert "AEDT [matrix]:" in written


def test_raising_channel_leaves_the_stage_error_and_diagnostic_unchanged(
    tmp_path: Path,
) -> None:
    log_path = configure_application_logging(tmp_path / "logs", RedactionContext())
    app = FakeMaxwell3dApp(raise_on="AssignMatrix")
    app.fail_desktop_messages = True

    result = run(tmp_path, app)

    stage = result.stages[-2]  # type: ignore[index]
    assert stage.name == "matrix"
    assert stage.succeeded is False
    # The capture attempt must never replace or blank the real stage error.
    assert "boom in AssignMatrix" in stage.message
    logging.getLogger(LOGGER_NAME).handlers[0].flush()
    written = log_path.read_text(encoding="utf-8")
    assert "Could not read AEDT messages after matrix failed" in written
    # No channel line was readable, so no "AEDT [matrix]:" line was written.
    assert "AEDT [matrix]:" not in written


def test_captured_lines_are_redacted_like_every_other_log_line(tmp_path: Path) -> None:
    log_path = configure_application_logging(
        tmp_path / "logs", RedactionContext(user_names=("jane.doe",))
    )
    app = FakeMaxwell3dApp(raise_on="AssignMatrix")
    app.desktop_message_lines = (r"Unable to write C:\Users\jane.doe\model.aedt",)

    run(tmp_path, app)

    logging.getLogger(LOGGER_NAME).handlers[0].flush()
    written = log_path.read_text(encoding="utf-8")
    assert "jane.doe" not in written
    assert "AEDT [matrix]:" in written


# Every stage-failure boundary that can still reach the session must read the
# channel: deleting any one of these calls used to leave the suite green, and
# the analyze boundary is the one the 2026-08-18 incident travelled through.
CHANNEL = ("Unable to create child process: 3dedy",)


class _BrokenModeler:
    """Any use raises, so the geometry-only stage loop fails at its first stage."""

    def __getattr__(self, name: str) -> object:
        raise RuntimeError(f"boom in modeler.{name}")

    def __setattr__(self, name: str, value: object) -> None:
        raise RuntimeError(f"boom in modeler.{name}")


def _armed(app: FakeMaxwell3dApp) -> FakeMaxwell3dApp:
    app.desktop_message_lines = CHANNEL
    return app


def _export_3d(tmp_path: Path, app: FakeMaxwell3dApp, *, solve: bool = False) -> None:
    exporter = PyaedtMaxwell3dExporter(app_factory=FakeMaxwell3dAppFactory(app))
    exporter.export(replace(make_request(tmp_path), solve=solve))


def _export_geometry_only(tmp_path: Path, app: FakeMaxwell3dApp) -> None:
    definition = make_definition()
    exporter = PyaedtMaxwell3dExporter(app_factory=FakeMaxwell3dAppFactory(app))
    exporter.export_geometry_only(
        Maxwell3dGeometryOnlyRequest(
            plan=build_geometry_only_maxwell3d_plan(
                CORE, (pack(definition),), (definition,), {"w1": BARE}
            ),
            release=AedtRelease(2025, 2),
            edition=AedtEdition.COMMERCIAL,
            non_graphical=True,
            output_directory=tmp_path / "out",
            project_name="Boost_inductor",
        )
    )


def _export_2d(tmp_path: Path, app: FakeMaxwell2dApp, *, solve: bool = False) -> None:
    exporter = PyaedtMaxwell2dExporter(app_factory=FakeMaxwell2dAppFactory(app))
    exporter.export(replace(make_2d_request(tmp_path), solve=solve))


def _solve_stage_3d(tmp_path: Path) -> str:
    _export_3d(tmp_path, _armed(FakeMaxwell3dApp(raise_on="AssignMatrix")))
    return "matrix"


def _solve_save_3d(tmp_path: Path) -> str:
    _export_3d(tmp_path, _armed(FakeMaxwell3dApp(raise_on="save_project")))
    return "save"


def _solve_analyze_3d(tmp_path: Path) -> str:
    app = _armed(FakeMaxwell3dApp())
    app.fail_analyze = True
    _export_3d(tmp_path, app, solve=True)
    return "analyze"


def _geometry_stage_3d(tmp_path: Path) -> str:
    app = _armed(FakeMaxwell3dApp())
    app.modeler = _BrokenModeler()
    _export_geometry_only(tmp_path, app)
    return "units"


def _geometry_save_3d(tmp_path: Path) -> str:
    _export_geometry_only(tmp_path, _armed(FakeMaxwell3dApp(raise_on="save_project")))
    return "save"


def _solve_stage_2d(tmp_path: Path) -> str:
    _export_2d(tmp_path, _armed(FakeMaxwell2dApp(raise_on="assign_matrix")))
    return "matrix"


def _solve_save_2d(tmp_path: Path) -> str:
    _export_2d(tmp_path, _armed(FakeMaxwell2dApp(raise_on="save_project")))
    return "save"


def _solve_analyze_2d(tmp_path: Path) -> str:
    app = _armed(FakeMaxwell2dApp())
    app.fail_analyze = True
    _export_2d(tmp_path, app, solve=True)
    return "analyze"


@pytest.mark.parametrize(
    "failing_run",
    [
        _solve_stage_3d,
        _solve_save_3d,
        _solve_analyze_3d,
        _geometry_stage_3d,
        _geometry_save_3d,
        _solve_stage_2d,
        _solve_save_2d,
        _solve_analyze_2d,
    ],
    ids=[
        "3d-stage",
        "3d-save",
        "3d-analyze",
        "3d-geometry-stage",
        "3d-geometry-save",
        "2d-stage",
        "2d-save",
        "2d-analyze",
    ],
)
def test_every_failure_boundary_captures_the_channel(
    tmp_path: Path,
    failing_run: Callable[[Path], str],
) -> None:
    log_path = configure_application_logging(tmp_path / "logs", RedactionContext())

    stage = failing_run(tmp_path)

    logging.getLogger(LOGGER_NAME).handlers[0].flush()
    written = log_path.read_text(encoding="utf-8")
    assert f"AEDT [{stage}]: {CHANNEL[0]}" in written


def test_the_diagnostic_save_s_own_messages_are_captured_too(tmp_path: Path) -> None:
    """The capture reads after the nested save, so what the save told AEDT counts.

    A read taken before that save would miss exactly the messages describing
    why the diagnostic save also failed.
    """
    log_path = configure_application_logging(tmp_path / "logs", RedactionContext())
    app = FakeMaxwell3dApp(raise_on="AssignMatrix")

    def _speak_on_save() -> None:
        app.desktop_message_lines = ("Cannot write project: disk is full.",)

    app.on_call = {"save_project": _speak_on_save}

    _export_3d(tmp_path, app)

    logging.getLogger(LOGGER_NAME).handlers[0].flush()
    written = log_path.read_text(encoding="utf-8")
    assert "AEDT [matrix]: Cannot write project: disk is full." in written
