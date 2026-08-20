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

    @staticmethod
    def _parse_saved_at(saved_at_utc: str) -> datetime | None:
        """Parse an autosave timestamp, treating a naive one as UTC.

        `RecoveryStore.read()` deliberately validates only that this is a
        string and leaves the semantics to the caller, so this must be total
        over every string it can receive -- an index from another build, or
        one mangled out of band, must never raise. A bare `except ValueError`
        around `fromisoformat` is not enough on its own: a *parseable* but
        timezone-naive timestamp gets past it and then compares
        naive-vs-aware against the document's mtime, which raises `TypeError`
        out of `__init__` and takes the whole application down with it.
        """
        try:
            saved_at = datetime.fromisoformat(saved_at_utc)
        except ValueError:
            return None
        if saved_at.tzinfo is None:
            saved_at = saved_at.replace(tzinfo=timezone.utc)
        return saved_at

    def _offerable(self, snapshot: RecoverySnapshot | None) -> RecoverySnapshot | None:
        """Only a snapshot that targets this document, is newer than it, and
        actually differs from it.

        The recovery slot is one global slot per app-data directory, not one
        per project: it holds whatever was being edited when the app last
        exited abnormally. If that is a different document than the one this
        session is opening now, splicing it in would hand the user someone
        else's unsaved edits under the wrong project's name -- so the
        document paths (both None, meaning "never saved", or both equal once
        resolved) must match before anything else is considered. Resolving
        both sides means a document opened as a relative path on one launch
        and an absolute one on another still matches the same file.

        A snapshot older than the saved document describes work the user
        already saved; offering it would invite them to go backwards.

        A snapshot byte-identical to the saved document describes no work at
        all: `undo()` back to the last-saved state still autosaves, so an
        edit-then-undo-then-crash leaves a snapshot that is *newer* than the
        document but changes nothing in it. Offering that trains the user to
        dismiss the one prompt that does matter.
        """
        if snapshot is None:
            return None
        snapshot_path = snapshot.document_path
        session_path = self._session.document_path
        if (snapshot_path is None) != (session_path is None):
            return None
        if (
            snapshot_path is not None
            and session_path is not None
            and snapshot_path.resolve() != session_path.resolve()
        ):
            return None
        document_path = snapshot_path
        # `document_path is None` is a "never saved" snapshot -- ponytail:
        # unreachable today, see `_get_summary`'s comment. A missing file
        # (deleted after the crash, before relaunch) is real and reachable,
        # and there is nothing on disk left to be newer or byte-identical to.
        if document_path is None or not document_path.is_file():
            return snapshot
        saved_at = self._parse_saved_at(snapshot.saved_at_utc)
        if saved_at is None:
            return None
        document_time = datetime.fromtimestamp(
            document_path.stat().st_mtime, tz=timezone.utc
        )
        if saved_at <= document_time:
            return None
        try:
            if snapshot.project_path.read_bytes() == document_path.read_bytes():
                return None
        except OSError:
            # An unreadable file must not crash startup either -- fall
            # through and still offer, rather than guessing it is a match.
            pass
        return snapshot

    def _get_available(self) -> bool:
        return self._snapshot is not None

    available = Property(bool, _get_available, notify=offerChanged)

    def _get_summary(self) -> str:
        snapshot = self._snapshot
        if snapshot is None:
            return ""
        target = (
            # ponytail: unreachable while `main.py` only ever builds this
            # controller inside `if project is not None`, which always
            # supplies a document path -- pre-positioned for a future
            # New-Project flow that can autosave before the first Save As.
            "an unsaved project"
            if snapshot.document_path is None
            else snapshot.document_path.name
        )
        saved_at = self._parse_saved_at(snapshot.saved_at_utc)
        # "recorded at", not "were autosaved at": a crash between the
        # document write and the index write can leave the recorded moment
        # lagging the content, so naming the write is more honest than
        # naming the edit. Rendered in local time -- the raw UTC ISO string
        # reads hours off to a user outside UTC.
        recorded_at = (
            snapshot.saved_at_utc
            if saved_at is None
            else saved_at.astimezone().strftime("%Y-%m-%d %H:%M")
        )
        return (
            f"The last autosave for {target} was recorded at {recorded_at}. "
            "Recover it, or discard it and keep the version on disk."
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
