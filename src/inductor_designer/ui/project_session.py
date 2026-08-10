"""The single in-memory project every Guided Studio controller shares.

Five controllers edit one project. Each keeping its own snapshot is how two
screens end up disagreeing about the same design, so they all read and write
here instead. The generation worker runs on another thread, so the actual
storage is the existing lock-protected `CurrentProjectProvider`.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot

from inductor_designer.domain.project import InductorProject
from inductor_designer.ui.generation_controller import CurrentProjectProvider


class ProjectSession(QObject):
    projectChanged = Signal()
    dirtyChanged = Signal()
    statusMessageChanged = Signal()
    documentPathChanged = Signal()

    def __init__(
        self,
        project: InductorProject,
        document_path: Path | None = None,
        save_callback: Callable[[InductorProject], None] | None = None,
        open_callback: Callable[[Path], InductorProject] | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._provider = CurrentProjectProvider(project)
        self._document_path = document_path
        self._save_callback = save_callback
        self._open_callback = open_callback
        self._dirty = False
        self._status_message = "Ready"

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
        try:
            self._save_callback(self.project)
        except Exception as error:  # noqa: BLE001 - QML needs a safe failure path
            self._document_path = previous_path
            self.set_status(f"Unable to save project: {error}")
            return False
        self._set_dirty(False)
        self.documentPathChanged.emit()
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
        self._set_dirty(False)
        self.projectChanged.emit()
        self.documentPathChanged.emit()
        self.set_status(f"Opened {path.name}")
        return True
