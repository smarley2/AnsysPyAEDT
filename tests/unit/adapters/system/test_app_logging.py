from __future__ import annotations

import io
import logging
import logging.handlers
import sys
from pathlib import Path

import pytest

from inductor_designer.adapters.system.app_logging import (
    LOGGER_NAME,
    configure_application_logging,
)
from inductor_designer.adapters.system.environment import (
    application_data_directory,
    environment_redaction_context,
    log_directory,
    recovery_directory,
)
from inductor_designer.application.services.redaction import (
    REDACTED_PATH,
    RedactionContext,
)


def test_directories_are_nested_under_one_application_directory() -> None:
    root = application_data_directory()
    assert recovery_directory().parent == root
    assert log_directory().parent == root


def test_environment_context_reports_this_machine() -> None:
    context = environment_redaction_context()
    assert isinstance(context, RedactionContext)
    # `platform.node()` is not environment-derived, so a host token is always
    # available; an empty tuple here would silently disable host redaction.
    assert context.host_names
    if sys.platform == "win32":
        # USERNAME is always set in a Windows session.
        assert context.user_names


def test_short_and_whitespace_tokens_are_filtered_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("USERNAME", "ab")
    monkeypatch.setenv("COMPUTERNAME", " \t ")
    context = environment_redaction_context()
    for token in (*context.user_names, *context.host_names):
        assert token == token.strip()
        assert len(token) >= 3


def test_log_line_is_written_redacted(tmp_path: Path) -> None:
    directory = tmp_path / "InductorDesigner" / "logs"
    path = configure_application_logging(
        directory, RedactionContext(user_names=("jane.doe",))
    )
    logger = logging.getLogger(LOGGER_NAME)
    assert logger.handlers[0].maxBytes == 1_000_000
    logger.info(r"save failed: C:\Users\jane.doe\b.json")
    logger.handlers[0].flush()

    written = path.read_text(encoding="utf-8")
    assert path.name == "inductor-designer.log"
    assert "jane.doe" not in written
    assert f"{REDACTED_PATH}.json" in written
    assert "INFO" in written


def test_traceback_text_is_written_redacted(tmp_path: Path) -> None:
    path = configure_application_logging(
        tmp_path, RedactionContext(user_names=("jane.doe",))
    )
    logger = logging.getLogger(LOGGER_NAME)
    try:
        raise OSError(r"cannot open C:\Users\jane.doe\model.aedt")
    except OSError:
        logger.exception("autosave failed")
    logger.handlers[0].flush()

    written = path.read_text(encoding="utf-8")
    assert "jane.doe" not in written
    assert "OSError" in written


def test_configuring_twice_does_not_duplicate_handlers(tmp_path: Path) -> None:
    configure_application_logging(tmp_path, RedactionContext())
    configure_application_logging(tmp_path, RedactionContext())
    assert len(logging.getLogger(LOGGER_NAME).handlers) == 1


def test_rotated_log_file_is_also_redacted(tmp_path: Path) -> None:
    # Task 8 collects rotated files from the log directory too, so a
    # rotated backup must have gone through the same redacting formatter
    # as the active file, not just the file RotatingFileHandler is
    # currently appending to.
    path = configure_application_logging(
        tmp_path, RedactionContext(user_names=("jane.doe",))
    )
    logger = logging.getLogger(LOGGER_NAME)
    handler = logger.handlers[0]
    assert isinstance(handler, logging.handlers.RotatingFileHandler)
    handler.maxBytes = 1
    for _ in range(3):
        logger.warning(r"save failed: C:\Users\jane.doe\b.json")
    handler.flush()

    rotated = path.with_name(f"{path.name}.1")
    assert rotated.exists()
    written = rotated.read_text(encoding="utf-8")
    assert "jane.doe" not in written


def test_root_logger_never_receives_a_line(tmp_path: Path) -> None:
    # `propagate = False` is the only thing stopping a line from reaching
    # whatever handler another library (or `logging.lastResort`) has bound to
    # the root logger, none of which run through `RedactingFormatter`.
    configure_application_logging(
        tmp_path, RedactionContext(user_names=("jane.doe",))
    )
    root = logging.getLogger()
    sink = io.StringIO()
    handler = logging.StreamHandler(sink)
    root.addHandler(handler)
    try:
        logging.getLogger(LOGGER_NAME).warning(
            r"save failed: C:\Users\jane.doe\b.json"
        )
    finally:
        root.removeHandler(handler)
    assert sink.getvalue() == ""
