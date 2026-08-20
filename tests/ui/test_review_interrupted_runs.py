"""The Review screen must name an interrupted run and never offer to resume it."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtGui import QGuiApplication  # noqa: E402

from inductor_designer.simulation.run_contracts import RunStatus  # noqa: E402

pytestmark = pytest.mark.ui


def _interrupted_run(project_document_path: Path) -> Path:
    directory = (
        project_document_path.parent / "runs" / "20260818-101500-maxwell-3d"
    )
    (directory / "results").mkdir(parents=True)
    (directory / "run-manifest.json").write_text(
        json.dumps(
            {
                "runId": "20260818-101500",
                "backend": "maxwell-3d",
                "mode": "generate-and-solve",
                "status": RunStatus.RUNNING.value,
                "startedUtc": "2026-08-18T10:15:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    return directory


def test_an_interrupted_run_appears_in_the_run_section(tmp_path: Path) -> None:
    QGuiApplication.instance() or QGuiApplication([])
    from tests.ui.test_review_controller import review_controller_environment

    env = review_controller_environment(tmp_path)
    _interrupted_run(env.document_path)
    env.controller.refresh()

    run_section = next(
        section
        for section in env.controller.sections
        if section["title"] == "Run request"
    )
    texts = [row["text"] for row in run_section["rows"]]
    assert any("20260818-101500" in text for text in texts)
    assert any("cannot be solved again" in text for text in texts)
    assert not any("resume" in text.casefold() for text in texts)


def test_open_run_folder_by_id_reaches_the_path_opener(tmp_path: Path) -> None:
    QGuiApplication.instance() or QGuiApplication([])
    from tests.ui.test_review_controller import review_controller_environment

    env = review_controller_environment(tmp_path)
    directory = _interrupted_run(env.document_path)
    env.controller.refresh()

    assert env.controller.openRunFolderById("20260818-101500") is True
    assert env.opener.opened == [directory]


def test_an_unknown_run_id_opens_nothing(tmp_path: Path) -> None:
    QGuiApplication.instance() or QGuiApplication([])
    from tests.ui.test_review_controller import review_controller_environment

    env = review_controller_environment(tmp_path)
    env.controller.refresh()

    assert env.controller.openRunFolderById("19700101-000000") is False
    assert env.opener.opened == []
