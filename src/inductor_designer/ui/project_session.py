"""The single in-memory project every Guided Studio controller shares.

Five controllers edit one project. Each keeping its own snapshot is how two
screens end up disagreeing about the same design, so they all read and write
here instead. The generation worker runs on another thread, so the actual
storage is the existing lock-protected `CurrentProjectProvider`.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Property, QObject, Signal, Slot

from inductor_designer.domain.project import InductorProject
from inductor_designer.ui.generation_controller import CurrentProjectProvider


class ProjectSession(QObject):
    projectChanged = Signal()
    dirtyChanged = Signal()
    statusMessageChanged = Signal()

    def __init__(
        self,
        project: InductorProject,
        document_path: Path | None = None,
        save_callback: Callable[[InductorProject], None] | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._provider = CurrentProjectProvider(project)
        self._document_path = document_path
        self._save_callback = save_callback
        self._dirty = False
        self._status_message = "Ready"

    @property
    def project(self) -> InductorProject:
        return self._provider.current()

    @property
    def document_path(self) -> Path | None:
        return self._document_path

    def apply(self, project: InductorProject) -> None:
        """Accept an already-validated edit as the current session project."""
        self._provider.replace(project)
        self._set_dirty(True)
        self.projectChanged.emit()

    def _get_dirty(self) -> bool:
        return self._dirty

    dirty = Property(bool, _get_dirty, notify=dirtyChanged)

    def _get_document_path(self) -> str:
        return "" if self._document_path is None else str(self._document_path)

    documentPath = Property(str, _get_document_path, constant=True)

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
        try:
            self._save_callback(self.project)
        except Exception as error:  # noqa: BLE001 - QML needs a safe failure path
            self.set_status(f"Unable to save project: {error}")
            return False
        self._set_dirty(False)
        self.set_status("Saved")
        return True
