from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtGui import QGuiApplication  # noqa: E402

from inductor_designer.domain.project import InductorProject  # noqa: E402
from inductor_designer.ui.project_session import ProjectSession  # noqa: E402
from tests.unit.domain.test_project import make_project  # noqa: E402

pytestmark = pytest.mark.ui


def test_session_starts_clean_and_publishes_edits() -> None:
    QGuiApplication.instance() or QGuiApplication([])
    session = ProjectSession(make_project())
    changes: list[int] = []
    session.projectChanged.connect(lambda: changes.append(1))

    assert session.dirty is False
    assert session.documentPath == ""

    session.apply(replace(session.project, description="edited"))

    assert session.project.description == "edited"
    assert session.dirty is True
    assert changes == [1]


def test_saving_persists_once_and_clears_dirty(tmp_path: Path) -> None:
    QGuiApplication.instance() or QGuiApplication([])
    saved: list[InductorProject] = []
    session = ProjectSession(
        make_project(),
        document_path=tmp_path / "boost.inductor.json",
        save_callback=saved.append,
    )
    session.apply(replace(session.project, description="edited"))

    assert session.saveProject() is True

    assert [item.description for item in saved] == ["edited"]
    assert session.dirty is False
    assert session.statusMessage == "Saved"
    assert session.documentPath == str(tmp_path / "boost.inductor.json")


def test_a_failed_save_keeps_the_session_dirty() -> None:
    QGuiApplication.instance() or QGuiApplication([])

    def explode(project: InductorProject) -> None:
        raise OSError("disk full")

    session = ProjectSession(
        make_project(), Path("boost.inductor.json"), save_callback=explode
    )
    session.apply(replace(session.project, description="edited"))

    assert session.saveProject() is False

    assert session.dirty is True
    assert "disk full" in session.statusMessage


def test_a_session_without_a_document_path_cannot_save() -> None:
    QGuiApplication.instance() or QGuiApplication([])
    session = ProjectSession(make_project())

    assert session.saveProject() is False
    assert "no project document" in session.statusMessage.casefold()
