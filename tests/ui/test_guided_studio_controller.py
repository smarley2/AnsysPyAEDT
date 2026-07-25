from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtGui import QGuiApplication  # noqa: E402

from inductor_designer.ui.guided_studio_controller import (  # noqa: E402
    GuidedStudioController,
)
from tests.unit.application.test_geometry_model import CATALOG  # noqa: E402
from tests.unit.domain.test_project import make_project  # noqa: E402

pytestmark = pytest.mark.ui


def test_editing_winding_rebuilds_real_preview_and_can_be_saved() -> None:
    app = QGuiApplication.instance() or QGuiApplication([])
    saved: list[object] = []
    controller = GuidedStudioController(make_project(), CATALOG, saved.append)
    before = controller.previewEntries[1].geometry

    assert app is not None
    assert [item["windingId"] for item in controller.windings] == ["w1"]
    assert controller.selectedWindingId == "w1"
    assert controller.dirty is False

    assert controller.setWindingField("w1", "turns", "24") is True

    assert controller.windings[0]["turns"] == 24
    assert controller.previewEntries[1].geometry is not before
    assert controller.dirty is True

    assert controller.saveDraft() is True
    assert saved and saved[0].windings[0].turns == 24
    assert controller.dirty is False


def test_invalid_winding_edit_keeps_previous_geometry() -> None:
    app = QGuiApplication.instance() or QGuiApplication([])
    controller = GuidedStudioController(make_project(), CATALOG)
    before = controller.previewEntries[1].geometry

    assert app is not None
    assert controller.setWindingField("w1", "turns", "0") is False

    assert controller.windings[0]["turns"] == 20
    assert controller.previewEntries[1].geometry is before
    assert "Unable to apply" in controller.statusMessage
