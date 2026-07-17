from __future__ import annotations

import threading
from collections.abc import Callable

from PySide6.QtCore import Property, QObject, Signal, Slot


class GenerationController(QObject):
    """Runs a generation backend on a background thread and reports lines to QML.

    `runner` is `(backend_label: str) -> tuple[str, ...]` — typically a closure
    binding a GenerationBackend to `run_generation` with real exporters. Qt
    queues QObject signal delivery across threads, so emitting from the worker
    thread is safe for the queued connections QML/Property notify use.
    """

    linesChanged = Signal()
    busyChanged = Signal()

    def __init__(
        self, runner: Callable[[str], tuple[str, ...]], parent: QObject | None = None
    ) -> None:
        super().__init__(parent)
        self._runner = runner
        self._lines: list[str] = []
        self._busy = False

    def _get_lines(self) -> list[str]:
        return self._lines

    lines = Property(list, _get_lines, notify=linesChanged)

    def _get_busy(self) -> bool:
        return self._busy

    busy = Property(bool, _get_busy, notify=busyChanged)

    @Slot(str)
    def generate(self, backend_label: str) -> None:
        if self._busy:
            return
        self._busy = True
        self.busyChanged.emit()

        def worker() -> None:
            try:
                lines = self._runner(backend_label)
            except Exception as error:  # noqa: BLE001 - UI must never wedge
                lines = (f"Generation failed: {error}",)
            finally:
                self._lines = list(lines)
                self._busy = False
                self.linesChanged.emit()
                self.busyChanged.emit()

        threading.Thread(target=worker, daemon=True).start()
