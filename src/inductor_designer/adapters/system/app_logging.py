"""One rotating application log, redacted as each line is written.

Redacting in the formatter rather than at the call site is what makes the file
shareable by construction: no caller can forget, tracebacks are covered by the
same pass, and the log the user finds on disk is exactly the text the
diagnostic bundle carries.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from inductor_designer.application.services.redaction import (
    RedactionContext,
    redact_text,
)

LOGGER_NAME = "inductor_designer"
APP_LOG_FILENAME = "inductor-designer.log"
_FORMAT = "%(asctime)s\t%(levelname)s\t%(name)s\t%(message)s"
_MAX_BYTES = 1_000_000
_BACKUP_COUNT = 2


class RedactingFormatter(logging.Formatter):
    """Formats the record, then redacts the whole rendered line."""

    def __init__(self, context: RedactionContext) -> None:
        super().__init__(_FORMAT)
        self._context = context

    def format(self, record: logging.LogRecord) -> str:
        return redact_text(super().format(record), self._context)


def configure_application_logging(
    directory: Path, context: RedactionContext
) -> Path:
    """Install the single redacting handler and return the log file path."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / APP_LOG_FILENAME
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    # Replace rather than append: a second call (a test, a restarted session in
    # the same process) must not double every line.
    for existing in list(logger.handlers):
        logger.removeHandler(existing)
        existing.close()
    handler = RotatingFileHandler(
        path,
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
        delay=True,
    )
    handler.setFormatter(RedactingFormatter(context))
    logger.addHandler(handler)
    # The root logger has no redacting handler, so nothing may escape upwards.
    logger.propagate = False
    return path
