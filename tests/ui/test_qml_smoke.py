import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QSG_RHI_BACKEND", "software")

pytest.importorskip("PySide6")

from PySide6.QtGui import QGuiApplication  # noqa: E402

from inductor_designer.ui.main import create_engine  # noqa: E402


@pytest.mark.ui
def test_guided_studio_qml_loads() -> None:
    app = QGuiApplication.instance() or QGuiApplication([])
    engine = create_engine()

    assert app is not None
    assert len(engine.rootObjects()) == 1
