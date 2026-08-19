"""Offer the last autosaved snapshot after an abnormal exit.

Recovery loads the snapshot into the running session and leaves it dirty: the
recovered project is explicitly *not* on disk, so the user still has to save it,
and the M7c Generate gate still refuses to run it until they do. Nothing here
writes the user's project document.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from PySide6.QtCore import Property, QObject, Signal, Slot

from inductor_designer.adapters.system.app_logging import LOGGER_NAME

if TYPE_CHECKING:
    from inductor_designer.adapters.persistence.recovery_store import (
        RecoverySnapshot,
        RecoveryStore,
    )
    from inductor_designer.ui.project_session import ProjectSession

_logger = logging.getLogger(LOGGER_NAME)


class RecoveryController(QObject):
    offerChanged = Signal()

    def __init__(
        self,
        store: RecoveryStore,
        session: ProjectSession,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._store = store
        self._session = session
        self._snapshot = self._offerable(store.read())

    def _offerable(self, snapshot: RecoverySnapshot | None) -> RecoverySnapshot | None:
        """Only a snapshot that targets this document and is newer than it.

        The recovery slot is one global slot per app-data directory, not one
        per project: it holds whatever was being edited when the app last
        exited abnormally. If that is a different document than the one this
        session is opening now, splicing it in would hand the user someone
        else's unsaved edits under the wrong project's name -- so the
        document paths (both None, meaning "never saved", or both equal)
        must match before anything else is considered.

        A snapshot older than the saved document describes work the user
        already saved; offering it would invite them to go backwards.
        """
        if snapshot is None:
            return None
        if snapshot.document_path != self._session.document_path:
            return None
        document_path = snapshot.document_path
        if document_path is None or not document_path.is_file():
            return snapshot
        try:
            saved_at = datetime.fromisoformat(snapshot.saved_at_utc)
        except ValueError:
            return None
        document_time = datetime.fromtimestamp(
            document_path.stat().st_mtime, tz=timezone.utc
        )
        return snapshot if saved_at > document_time else None

    def _get_available(self) -> bool:
        return self._snapshot is not None

    available = Property(bool, _get_available, notify=offerChanged)

    def _get_summary(self) -> str:
        snapshot = self._snapshot
        if snapshot is None:
            return ""
        target = (
            "an unsaved project"
            if snapshot.document_path is None
            else snapshot.document_path.name
        )
        return (
            f"Unsaved changes to {target} were autosaved at "
            f"{snapshot.saved_at_utc}. Recover them, or discard them and keep "
            "the version on disk."
        )

    summary = Property(str, _get_summary, notify=offerChanged)

    @Slot(result=bool)
    def recover(self) -> bool:
        snapshot = self._snapshot
        if snapshot is None:
            return False
        try:
            project = self._store.load_project(snapshot)
        except Exception as error:  # noqa: BLE001 - a bad snapshot must not crash
            _logger.warning("Recovery snapshot could not be loaded: %s", error)
            self._session.set_status(f"Unable to recover the autosaved changes: {error}")
            self._snapshot = None
            self.offerChanged.emit()
            return False
        self._session.applyRecovered(project)
        _logger.info("Recovered autosaved project changes.")
        self._snapshot = None
        self.offerChanged.emit()
        return True

    @Slot(result=bool)
    def discard(self) -> bool:
        self._store.clear()
        self._snapshot = None
        self.offerChanged.emit()
        return True
