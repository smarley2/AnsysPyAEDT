from __future__ import annotations

import os
import threading
import time
from dataclasses import replace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtGui import QGuiApplication  # noqa: E402

from inductor_designer.ui.generation_controller import (  # noqa: E402
    CurrentProjectProvider,
    GenerationController,
)
from inductor_designer.ui.main import _persist_and_publish_project  # noqa: E402
from tests.unit.domain.test_project import make_project  # noqa: E402

pytestmark = pytest.mark.ui


# ponytail: QGuiApplication, not QCoreApplication - this file shares a process
# with test_qml_smoke.py/test_preview_smoke.py under `pytest -m ui`, and once
# one test creates the base QCoreApplication the others' QGuiApplication([])
# call crashes (native Qt singleton mismatch). Same app class everywhere
# sidesteps the ordering hazard.
def _wait_until_idle(app: QGuiApplication, controller: GenerationController) -> None:
    deadline = time.monotonic() + 5.0
    while controller.busy:
        if time.monotonic() > deadline:
            raise TimeoutError("generation controller stayed busy")
        app.processEvents()
        time.sleep(0.01)


def test_generate_runs_stub_runner_and_reports_lines() -> None:
    app = QGuiApplication.instance() or QGuiApplication([])
    controller = GenerationController(lambda backend_label: ("a", "b"))

    assert controller.lines == []
    assert controller.busy is False

    controller.generate("Maxwell 3D")
    _wait_until_idle(app, controller)

    assert controller.lines == ["a", "b"]
    assert controller.busy is False


def test_generate_ignores_calls_while_busy() -> None:
    app = QGuiApplication.instance() or QGuiApplication([])
    calls: list[str] = []
    release = threading.Event()

    def runner(backend_label: str) -> tuple[str, ...]:
        calls.append(backend_label)
        release.wait(timeout=5.0)
        return ("done",)

    controller = GenerationController(runner)
    controller.generate("Maxwell 3D")
    controller.generate("FEMM 2D")  # ignored: busy
    release.set()
    _wait_until_idle(app, controller)

    assert calls == ["Maxwell 3D"]
    assert controller.lines == ["done"]


def test_generate_handles_runner_exception() -> None:
    app = QGuiApplication.instance() or QGuiApplication([])

    def failing_runner(backend_label: str) -> tuple[str, ...]:
        raise ValueError("test error from runner")

    controller = GenerationController(failing_runner)
    controller.generate("Maxwell 3D")
    _wait_until_idle(app, controller)

    assert controller.busy is False
    assert len(controller.lines) == 1
    assert "Generation failed:" in controller.lines[0]
    assert "test error from runner" in controller.lines[0]


def test_project_provider_publishes_only_after_persistence_succeeds() -> None:
    original = make_project()
    updated = replace(original, name="updated")
    provider = CurrentProjectProvider(original)

    def failing_save(_project: object) -> None:
        raise OSError("disk save failed")

    with pytest.raises(OSError, match="disk save failed"):
        _persist_and_publish_project(updated, failing_save, provider)
    assert provider.current() is original

    saved: list[object] = []
    _persist_and_publish_project(updated, saved.append, provider)
    assert saved == [updated]
    assert provider.current() is updated
