from __future__ import annotations

import threading
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING

from PySide6.QtCore import Property, QObject, Signal, Slot

from inductor_designer.application.services.project_run import ProjectRunFailed
from inductor_designer.ui.generation_lines import GenerationResult

if TYPE_CHECKING:
    from pathlib import Path

    from inductor_designer.domain.project import InductorProject
    from inductor_designer.simulation.run_contracts import RunManifest


class CurrentProjectProvider:
    """Share the latest persisted project with generation without global state."""

    def __init__(self, project: InductorProject) -> None:
        self._project = project
        self._lock = threading.Lock()

    def current(self) -> InductorProject:
        with self._lock:
            return self._project

    def replace(self, project: InductorProject) -> None:
        with self._lock:
            self._project = project


class GenerationController(QObject):
    """Runs a generation backend on a background thread and reports lines to QML.

    `runner` binds a GenerationBackend to `run_generation` with real exporters.
    Qt queues QObject signal delivery across threads, so emitting from the
    worker thread is safe for the queued connections QML/Property notify use.
    """

    linesChanged = Signal()
    busyChanged = Signal()

    def __init__(
        self,
        runner: Callable[[str], GenerationResult | Sequence[str]],
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._runner = runner
        self._lines: list[str] = []
        self._failed_manifest: RunManifest | None = None
        self._last_run_directory: Path | None = None
        self._last_generated_file: Path | None = None
        self._busy = False

    def _get_lines(self) -> list[str]:
        return self._lines

    lines = Property(list, _get_lines, notify=linesChanged)

    def _get_busy(self) -> bool:
        return self._busy

    busy = Property(bool, _get_busy, notify=busyChanged)

    @property
    def failed_manifest(self) -> RunManifest | None:
        return self._failed_manifest

    @property
    def last_run_directory(self) -> Path | None:
        return self._last_run_directory

    @property
    def last_generated_file(self) -> Path | None:
        return self._last_generated_file

    @Slot(str)
    def generate(self, backend_label: str) -> None:
        if self._busy:
            return
        self._busy = True
        self._failed_manifest = None
        self._last_run_directory = None
        self._last_generated_file = None
        self.busyChanged.emit()

        def worker() -> None:
            try:
                raw_result = self._runner(backend_label)
                result = (
                    raw_result
                    if isinstance(raw_result, GenerationResult)
                    else GenerationResult(
                        tuple(raw_result),
                        failed_manifest=getattr(
                            raw_result,
                            "failed_manifest",
                            None,
                        ),
                    )
                )
            except ProjectRunFailed as error:
                result = GenerationResult(
                    tuple(
                        f"Generation failed: {diagnostic}"
                        for diagnostic in error.manifest.diagnostics
                    ),
                    failed_manifest=error.manifest,
                    run_directory=error.location.directory,
                )
            except Exception as error:  # noqa: BLE001 - UI must never wedge
                result = GenerationResult((f"Generation failed: {error}",))
            finally:
                self._lines = list(result.lines)
                self._failed_manifest = result.failed_manifest
                self._last_run_directory = result.run_directory
                self._last_generated_file = result.generated_file
                self._busy = False
                self.linesChanged.emit()
                self.busyChanged.emit()

        threading.Thread(target=worker, daemon=True).start()
