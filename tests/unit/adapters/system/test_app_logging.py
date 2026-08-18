from __future__ import annotations

import logging
from pathlib import Path

from inductor_designer.adapters.system.app_logging import (
    APP_LOG_FILENAME,
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
    # A machine always has at least one of the two; an empty context would
    # silently disable token redaction.
    assert context.user_names or context.host_names


def test_log_line_is_written_redacted(tmp_path: Path) -> None:
    path = configure_application_logging(
        tmp_path, RedactionContext(user_names=("jane.doe",))
    )
    logging.getLogger(LOGGER_NAME).warning(r"save failed: C:\Users\jane.doe\b.json")
    logging.shutdown()

    written = path.read_text(encoding="utf-8")
    assert path.name == APP_LOG_FILENAME
    assert "jane.doe" not in written
    assert f"{REDACTED_PATH}.json" in written
    assert "WARNING" in written


def test_traceback_text_is_written_redacted(tmp_path: Path) -> None:
    path = configure_application_logging(
        tmp_path, RedactionContext(user_names=("jane.doe",))
    )
    try:
        raise OSError(r"cannot open C:\Users\jane.doe\model.aedt")
    except OSError:
        logging.getLogger(LOGGER_NAME).exception("autosave failed")
    logging.shutdown()

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
    logging.shutdown()

    rotated = path.with_name(f"{path.name}.1")
    assert rotated.exists()
    written = rotated.read_text(encoding="utf-8")
    assert "jane.doe" not in written
