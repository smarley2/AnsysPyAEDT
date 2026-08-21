"""Help > Save diagnostic bundle.

The bundle is written where the user asks. Nothing is uploaded, and nothing
leaves the machine on its own: the user chooses whether to share the file.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot

from inductor_designer import __version__
from inductor_designer.adapters.system.app_logging import LOGGER_NAME
from inductor_designer.adapters.system.diagnostic_archive import (
    BUNDLE_SUFFIX,
    collect_bundle_sources,
    write_diagnostic_archive,
)
from inductor_designer.application.services.diagnostic_bundle import (
    build_bundle_entries,
)

if TYPE_CHECKING:
    from inductor_designer.application.services.redaction import RedactionContext
    from inductor_designer.ui.project_session import ProjectSession


class DiagnosticsController(QObject):
    messageChanged = Signal()

    def __init__(
        self,
        session: ProjectSession,
        log_path: Path | None,
        context: RedactionContext,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._session = session
        self._log_path = log_path
        self._context = context
        self._message = ""

    def _get_message(self) -> str:
        return self._message

    message = Property(str, _get_message, notify=messageChanged)

    def _get_suggested_file_name(self) -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        return f"diagnostics-{stamp}{BUNDLE_SUFFIX}"

    suggestedFileName = Property(str, _get_suggested_file_name, constant=False)

    @Slot(QUrl, result=bool)
    def saveBundle(self, target: QUrl) -> bool:
        path = Path(target.toLocalFile())
        try:
            entries = build_bundle_entries(
                collect_bundle_sources(self._session.document_path, self._log_path),
                self._context,
                application_version=__version__,
                created_utc=datetime.now(timezone.utc).isoformat(),
            )
            written = write_diagnostic_archive(path, entries)
        except Exception as error:  # noqa: BLE001 - the UI must never crash here
            logging.getLogger(LOGGER_NAME).warning("Bundle failed: %s", error)
            # Not `{error}`: an OSError's text carries the absolute target
            # path, and this message is exactly the copy a user pastes into
            # an e-mail or a ticket.
            self._message = f"Unable to write the diagnostic bundle: {type(error).__name__}"
            self.messageChanged.emit()
            return False
        logging.getLogger(LOGGER_NAME).info(
            "Diagnostic bundle written with %d entries.", len(entries)
        )
        self._message = (
            f"Saved {written.name}. It contains no file paths, machine names, "
            "licence servers, user names, or e-mail addresses."
        )
        self.messageChanged.emit()
        return True
