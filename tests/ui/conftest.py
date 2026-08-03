from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtGui import QGuiApplication

    from inductor_designer.ui.generation_controller import GenerationController


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
