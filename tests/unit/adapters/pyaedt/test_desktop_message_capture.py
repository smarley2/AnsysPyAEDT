"""AEDT's message channel is captured into the application log at the stage
failure boundary, while the session that knows it still exists.

Verifies: a failed stage writes every channel line to the log; a raising
channel leaves the original stage error and the run's own diagnostic
unchanged; the captured lines reach the log through the redacting formatter
rather than around it.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from inductor_designer.adapters.pyaedt.maxwell3d import PyaedtMaxwell3dExporter
from inductor_designer.adapters.system.app_logging import (
    LOGGER_NAME,
    configure_application_logging,
)
from inductor_designer.application.ports.maxwell_exporter import Maxwell3dExportRequest
from inductor_designer.application.services.redaction import RedactionContext
from inductor_designer.domain.aedt_target import AedtEdition, AedtRelease
from tests.fakes.maxwell3d_app import FakeMaxwell3dApp, FakeMaxwell3dAppFactory
from tests.unit.simulation.test_plan_builder import build, make_definition

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
