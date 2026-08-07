from __future__ import annotations

import gc
import time
from collections.abc import Iterator
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from PySide6.QtGui import QGuiApplication

    from inductor_designer.ui.generation_controller import GenerationController


# ponytail: the QML tests pin their engines in module-level lists, because a
# collected engine takes its root window with it mid-test. Those engines then
# outlive the last test and are destroyed during interpreter finalization, in
# whatever order CPython happens to clear module dicts. On Linux/Python 3.13
# that lands after the QGuiApplication is gone and segfaults - every test green,
# then exit 139. Delete them here instead, while the application still exists.
# The application itself is left alone: Qt tolerates its own teardown, it is the
# orphaned engines that do not.
@pytest.fixture(scope="session", autouse=True)
def delete_qml_engines_while_the_application_is_alive() -> Iterator[None]:
    yield
    try:
        import shiboken6
        from PySide6.QtGui import QGuiApplication
        from PySide6.QtQml import QQmlApplicationEngine
    except ImportError:  # the UI extra is not installed; nothing was created
        return
    app = QGuiApplication.instance()
    if app is None:
        return
    for engine in [o for o in gc.get_objects() if isinstance(o, QQmlApplicationEngine)]:
        if shiboken6.isValid(engine):
            shiboken6.delete(engine)
    app.processEvents()


# ponytail: QGuiApplication, not QCoreApplication - this file shares a process
# with test_qml_smoke.py/test_preview_smoke.py under `pytest -m ui`, and once
# one test creates the base QCoreApplication the others' QGuiApplication([])
# call crashes (native Qt singleton mismatch). Same app class everywhere
# sidesteps the ordering hazard.
def wait_until_idle(app: QGuiApplication, controller: GenerationController) -> None:
    deadline = time.monotonic() + 5.0
    while controller.busy:
        if time.monotonic() > deadline:
            raise TimeoutError("generation controller stayed busy")
        app.processEvents()
        time.sleep(0.01)
