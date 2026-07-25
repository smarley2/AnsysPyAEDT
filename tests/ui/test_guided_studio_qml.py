from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QSG_RHI_BACKEND", "software")

pytest.importorskip("PySide6")

from PySide6.QtCore import QObject  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

from inductor_designer.ui.guided_studio_controller import (  # noqa: E402
    GuidedStudioController,
)
from inductor_designer.ui.main import create_engine  # noqa: E402
from tests.unit.application.test_geometry_model import CATALOG  # noqa: E402
from tests.unit.domain.test_project import make_project  # noqa: E402

pytestmark = pytest.mark.ui


def test_canvas_first_shell_exposes_real_winding_workspace() -> None:
    app = QGuiApplication.instance() or QGuiApplication([])
    controller = GuidedStudioController(make_project(), CATALOG)
    engine = create_engine(guided_studio_controller=controller)
    root = engine.rootObjects()[0]
    app.processEvents()

    assert root.objectName() == "canvasFirstShell"
    assert root.findChild(QObject, "topbar") is not None
    assert root.findChild(QObject, "guidedStepList") is not None
    assert root.findChild(QObject, "previewPane") is not None
    assert root.findChild(QObject, "contextPanel") is not None
    assert root.findChild(QObject, "windingsPanel") is not None
    assert root.findChild(QObject, "windingList") is not None
    assert root.findChild(QObject, "windingTurnsField") is not None
    assert root.findChild(QObject, "statusDock") is not None
    assert root.findChild(QObject, "saveProjectButton") is not None
    assert controller.previewEntries
