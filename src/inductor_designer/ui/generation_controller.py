from __future__ import annotations

import threading
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Property, QObject, Signal, Slot

from inductor_designer.application.services.project_run import ProjectRunFailed
from inductor_designer.ui.generation_lines import GenerationResult

if TYPE_CHECKING:
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
    The worker thread's only interaction with Qt is one `_finished` emit, whose
    queued delivery publishes the result on the thread that owns this object;
    see `_publish` for why the worker must not publish it itself.
    """

    linesChanged = Signal()
    busyChanged = Signal()
    # Carries a GenerationResult from the worker thread to `_publish`. Private:
    # nothing outside this class may connect to it, or that receiver would run
    # on the worker thread's terms rather than this object's.
    _finished = Signal(object)

    def __init__(
        self,
        runner: Callable[[str, bool], GenerationResult | Sequence[str]],
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._runner = runner
        self._lines: list[str] = []
        self._failed_manifest: RunManifest | None = None
        self._last_run_directory: Path | None = None
        self._last_generated_file: Path | None = None
        self._busy = False
        self._worker: threading.Thread | None = None
        # Auto connection, and the receiver is this object: emitted from the
        # worker thread, delivery is queued onto the thread that owns it.
        self._finished.connect(self._publish)

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

    def record_run_evidence(
        self, run_directory: Path | None, generated_file: Path | None
    ) -> None:
        """Publish where the last run landed. Called by `_publish`, and by tests."""
        self._last_run_directory = run_directory
        self._last_generated_file = generated_file
        self.linesChanged.emit()

    @Slot(object)
    def _publish(self, result: GenerationResult) -> None:
        """Adopt a finished run's result, on the thread that owns this object.

        The worker used to publish it itself: set `_busy = False` and then emit
        `linesChanged`/`busyChanged`. That let the owning thread see the run as
        finished, and tear the controller and everything wired to those signals
        down, while the worker thread was still alive and mid-emit. Under
        `pytest -n 8` that killed an xdist worker with a Windows access
        violation (sometimes heap corruption instead) roughly one run in five;
        the fault always landed in the teardown right after a finished run, and
        it never happened for a controller that had not started one.

        So the worker now computes and emits, and only that: this slot adopts
        the result on the owning thread, and joins the worker first, so by the
        time `busy` reads False the thread that ran the generation is gone. The
        join is immediate in practice -- the worker emits `_finished` as its
        last statement, so it is already returning when this runs.
        """
        worker = self._worker
        self._worker = None
        if worker is not None and worker is not threading.current_thread():
            worker.join(timeout=5.0)
        self._lines = list(result.lines)
        self._failed_manifest = result.failed_manifest
        self.record_run_evidence(result.run_directory, result.generated_file)
        self._busy = False
        self.linesChanged.emit()
        self.busyChanged.emit()

    @Slot(str, bool)
    def generate(self, backend_label: str, show_solver_window: bool = False) -> None:
        if self._busy:
            return
        self._busy = True
        self._failed_manifest = None
        self._last_run_directory = None
        self._last_generated_file = None
        self.busyChanged.emit()

        def worker() -> None:
            try:
                raw_result = self._runner(backend_label, show_solver_window)
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
                self._finished.emit(result)

        self._worker = threading.Thread(target=worker, daemon=True)
        self._worker.start()
