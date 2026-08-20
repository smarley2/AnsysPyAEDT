from __future__ import annotations

import gc
import logging
import time
from collections.abc import Iterator
from typing import TYPE_CHECKING

import pytest

from inductor_designer.adapters.system.app_logging import LOGGER_NAME

if TYPE_CHECKING:
    from pathlib import Path

    from PySide6.QtGui import QGuiApplication

    from inductor_designer.ui.generation_controller import GenerationController


# `main()` calls `configure_application_logging(log_directory(), ...)`, and
# `log_directory()` reads LOCALAPPDATA -- without this, running the UI suite
# creates and writes to the developer's real
# `%LOCALAPPDATA%\InductorDesigner\logs\` directory, which is product-visible
# state pytest must not leave behind.
@pytest.fixture(autouse=True)
def redirect_local_appdata_to_a_temp_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))


# `configure_application_logging` sets `propagate = False` on this named
# logger so its (redacted) lines never double up into the root logger in
# production. Any test that runs `main()` (e.g. test_main_wiring.py) leaves
# that set for the rest of the process, which silently breaks every later
# test's plain `caplog.at_level(logger=LOGGER_NAME)` -- caplog's handler
# lives on the root logger, and records that don't propagate never reach it.
# Reset before each test instead of every affected test attaching
# `caplog.handler` to this logger directly.
@pytest.fixture(autouse=True)
def reset_recovery_logger_propagation() -> None:
    logging.getLogger(LOGGER_NAME).propagate = True


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
