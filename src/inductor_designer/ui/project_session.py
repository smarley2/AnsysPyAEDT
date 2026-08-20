"""The single in-memory project every Guided Studio controller shares.

Five controllers edit one project. Each keeping its own snapshot is how two
screens end up disagreeing about the same design, so they all read and write
here instead. The generation worker runs on another thread, so the actual
storage is the existing lock-protected `CurrentProjectProvider`.
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Property, QObject, QTimer, QUrl, Signal, Slot

from inductor_designer.adapters.system.app_logging import LOGGER_NAME
from inductor_designer.application.services.run_recovery import (
    reconcile_unfinished_runs,
)
from inductor_designer.domain.project import InductorProject
from inductor_designer.ui.generation_controller import CurrentProjectProvider

_logger = logging.getLogger(LOGGER_NAME)

# Deep enough to cover a working session's edits, bounded so a long session
# cannot grow the process without limit. Each entry is one immutable project.
UNDO_DEPTH = 50

# Long enough that dragging a numeric field does not write a file per frame,
# short enough that a crash loses at most this much work.
AUTOSAVE_DEBOUNCE_MS = 2000


class ProjectSession(QObject):
    projectChanged = Signal()
    dirtyChanged = Signal()
    statusMessageChanged = Signal()
    documentPathChanged = Signal()
    undoStackChanged = Signal()

    def __init__(
        self,
        project: InductorProject,
        document_path: Path | None = None,
        save_callback: Callable[[InductorProject], None] | None = None,
        open_callback: Callable[[Path], InductorProject] | None = None,
        autosave_callback: Callable[[InductorProject, Path | None], None] | None = None,
        recovery_cleanup: Callable[[], None] | None = None,
        is_run_busy: Callable[[], bool] | None = None,
        debounce_ms: int = AUTOSAVE_DEBOUNCE_MS,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._provider = CurrentProjectProvider(project)
        self._document_path = document_path
        self._save_callback = save_callback
        self._open_callback = open_callback
        self._is_run_busy = is_run_busy
        self._dirty = False
        self._status_message = "Ready"
        self._undo: list[InductorProject] = []
        self._redo: list[InductorProject] = []
        # The project as it exists on disk, or None when nothing has been
        # written yet. `dirty` is a comparison against this, not a flag: an
        # undo back to the saved state must re-enable the M7c Generate gate.
        self._saved_project: InductorProject | None = (
            project if document_path is not None else None
        )
        self._autosave_callback = autosave_callback
        self._recovery_cleanup = recovery_cleanup
        self._autosave_pending = False
        # Parented to self: Qt tears the timer down (and stops it) when this
        # session is destroyed, with no separate cleanup step to remember.
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.setInterval(debounce_ms)
        self._autosave_timer.timeout.connect(self.flushAutosave)

    @property
    def project(self) -> InductorProject:
        return self._provider.current()

    @property
    def document_path(self) -> Path | None:
        return self._document_path

    def set_save_callback(self, callback: Callable[[InductorProject], None] | None) -> None:
        """Bind the persister after construction.

        `main.py` wants the callback to always write to *this* session's
        current document path, including after Open/Save As move it -- which
        means the callback has to close over the session itself, and the
        session has to exist first.
        """
        self._save_callback = callback

    def set_busy_check(self, is_run_busy: Callable[[], bool] | None) -> None:
        """Bind the run-in-flight check after construction.

        `main.py` builds the `GenerationController` from this session, so the
        session cannot be told at construction time whether a run it starts
        later is in flight -- the same ordering reason `set_save_callback`
        exists.
        """
        self._is_run_busy = is_run_busy

    def apply(self, project: InductorProject) -> None:
        """Accept an already-validated edit as the current session project."""
        self._push_undo(self._provider.current())
        self._redo.clear()
        self._provider.replace(project)
        self._refresh_dirty()
        self.undoStackChanged.emit()
        self.projectChanged.emit()
        self._schedule_autosave()

    def applyRecovered(self, project: InductorProject) -> None:
        """Adopt a recovered snapshot as the current project.

        Deliberately not `apply`: there is no earlier in-session edit to undo
        back to, and the recovered project is not on disk, so it stays dirty.
        """
        self._undo.clear()
        self._redo.clear()
        self._provider.replace(project)
        self._refresh_dirty()
        self.undoStackChanged.emit()
        self.projectChanged.emit()
        self.set_status("Recovered unsaved changes")

    def _push_undo(self, project: InductorProject) -> None:
        self._undo.append(project)
        if len(self._undo) > UNDO_DEPTH:
            del self._undo[0]

    def _refresh_dirty(self) -> None:
        self._set_dirty(self._provider.current() != self._saved_project)

    @Slot(result=bool)
    def undo(self) -> bool:
        if not self._undo:
            return False
        self._redo.append(self._provider.current())
        self._provider.replace(self._undo.pop())
        self._refresh_dirty()
        self.undoStackChanged.emit()
        self.projectChanged.emit()
        self.set_status("Undid the last edit")
        self._schedule_autosave()
        return True

    @Slot(result=bool)
    def redo(self) -> bool:
        if not self._redo:
            return False
        self._push_undo(self._provider.current())
        self._provider.replace(self._redo.pop())
        self._refresh_dirty()
        self.undoStackChanged.emit()
        self.projectChanged.emit()
        self.set_status("Redid the last undone edit")
        self._schedule_autosave()
        return True

    def _get_can_undo(self) -> bool:
        return bool(self._undo)

    canUndo = Property(bool, _get_can_undo, notify=undoStackChanged)

    def _get_can_redo(self) -> bool:
        return bool(self._redo)

    canRedo = Property(bool, _get_can_redo, notify=undoStackChanged)

    def _get_dirty(self) -> bool:
        return self._dirty

    dirty = Property(bool, _get_dirty, notify=dirtyChanged)

    def _get_document_path(self) -> str:
        return "" if self._document_path is None else str(self._document_path)

    documentPath = Property(str, _get_document_path, notify=documentPathChanged)

    def _get_status_message(self) -> str:
        return self._status_message

    statusMessage = Property(str, _get_status_message, notify=statusMessageChanged)

    def _set_dirty(self, value: bool) -> None:
        if value == self._dirty:
            return
        self._dirty = value
        self.dirtyChanged.emit()

    def set_status(self, message: str) -> None:
        self._status_message = message
        self.statusMessageChanged.emit()

    def _schedule_autosave(self) -> None:
        if self._autosave_callback is None:
            return
        self._autosave_pending = True
        # Restarting on every edit, not just starting once, is the coalescing
        # behaviour itself: a timer already running is pushed back out to the
        # full interval, so a burst of edits (e.g. dragging a numeric field)
        # writes once, carrying whatever the LAST edit in the burst was.
        self._autosave_timer.start()

    @Slot()
    def flushAutosave(self) -> None:
        """Write the pending snapshot now. Never raises: a failed autosave must
        not take the edit or the session with it."""
        self._autosave_timer.stop()
        if not self._autosave_pending or self._autosave_callback is None:
            return
        self._autosave_pending = False
        try:
            self._autosave_callback(self.project, self._document_path)
        except Exception as error:  # noqa: BLE001 - autosave must never wedge the UI
            _logger.warning("Autosave failed: %s", error)
            self.set_status(f"Unable to autosave a recovery copy: {error}")

    def _drop_recovery_snapshot(self) -> None:
        """What is now on disk needs no recovery copy."""
        self._autosave_pending = False
        self._autosave_timer.stop()
        if self._recovery_cleanup is not None:
            try:
                self._recovery_cleanup()
            except Exception as error:  # noqa: BLE001 - a locked snapshot must not fail a successful save
                _logger.warning("Unable to clear the recovery snapshot: %s", error)

    @Slot(result=bool)
    def saveProject(self) -> bool:
        # Guard on the persister, not on the path: production always sets both
        # together, and the message must describe the condition actually tested.
        if self._save_callback is None:
            self.set_status(
                "Unable to save: this session has no project document to save "
                "into. Start the application with --project."
            )
            return False
        project = self.project
        try:
            self._save_callback(project)
        except Exception as error:  # noqa: BLE001 - QML needs a safe failure path
            _logger.warning("Save failed: %s", error)
            self.set_status(f"Unable to save project: {error}")
            return False
        self._saved_project = project
        self._refresh_dirty()
        self._drop_recovery_snapshot()
        _logger.info("Project saved to %s.", self._document_path)
        self.set_status("Saved")
        return True

    @Slot(QUrl, result=bool)
    def saveProjectAs(self, target: QUrl) -> bool:
        if self._save_callback is None:
            self.set_status(
                "Unable to save: this session has no way to write a project "
                "file. Start the application with --project."
            )
            return False
        path = Path(target.toLocalFile())
        previous_path = self._document_path
        # Set the new path before calling the callback: the callback (built in
        # main.py) saves to `self.document_path`, so this is what makes "save
        # under this new name" and "save" the same operation underneath.
        self._document_path = path
        project = self.project
        try:
            self._save_callback(project)
        except Exception as error:  # noqa: BLE001 - QML needs a safe failure path
            self._document_path = previous_path
            _logger.warning("Save as %s failed: %s", path, error)
            self.set_status(f"Unable to save project: {error}")
            return False
        self._saved_project = project
        self._refresh_dirty()
        self._drop_recovery_snapshot()
        self.documentPathChanged.emit()
        _logger.info("Project saved to %s.", path)
        self.set_status(f"Saved as {path.name}")
        return True

    @Slot(QUrl, result=bool)
    def openProject(self, source: QUrl) -> bool:
        """Replace the project and document path in place.

        Every Guided Studio controller holds a reference to this session
        (not to the project it wraps), and QML holds references to those
        controllers -- so swapping what is inside the session, rather than
        building a new one, is what makes every screen see the opened
        project without anything having to be reconstructed.
        """
        if self._open_callback is None:
            self.set_status(
                "Unable to open: this session cannot load a different "
                "project file."
            )
            return False
        path = Path(source.toLocalFile())
        try:
            project = self._open_callback(path)
        except Exception as error:  # noqa: BLE001 - a bad file must never crash the app
            self.set_status(f"Unable to open {path.name}: {error}")
            return False
        self._provider.replace(project)
        self._document_path = path
        # A run directory beside the newly opened document may still read
        # "running" from a process that died mid-run; reconcile it to
        # "interrupted" now so Review never reads it as a result. But a run
        # this process is executing right now writes that identical marker,
        # and Open is reachable while one is in flight (the run is a daemon
        # thread, not something the Open menu item is gated on) -- reconciling
        # in that window can catch a just-finished run between its manifest
        # write and this one, permanently overwriting a real "succeeded"
        # record with "interrupted". `_is_run_busy` is the same signal
        # `ReviewController` uses to hide a live run from the interrupted-run
        # list, so skipping the reconcile write under it here closes the same
        # gap rather than adding a second, separate guard. A reconciliation
        # failure must never block the open itself.
        if self._is_run_busy is None or not self._is_run_busy():
            with contextlib.suppress(OSError):
                reconcile_unfinished_runs(path)
        # An Open is not an edit: the history of the previous document must
        # not be able to overwrite the newly opened one.
        self._undo.clear()
        self._redo.clear()
        self._autosave_pending = False
        self._autosave_timer.stop()
        self._saved_project = project
        self._refresh_dirty()
        self.undoStackChanged.emit()
        self.projectChanged.emit()
        self.documentPathChanged.emit()
        _logger.info("Project opened from %s.", path)
        self.set_status(f"Opened {path.name}")
        return True
