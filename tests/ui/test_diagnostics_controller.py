from __future__ import annotations

import os
import zipfile
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtCore import QUrl  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

from inductor_designer.adapters.system.diagnostic_archive import (  # noqa: E402
    BUNDLE_SUFFIX,
)
from inductor_designer.application.services.redaction import (  # noqa: E402
    RedactionContext,
)
from inductor_designer.ui.diagnostics_controller import (  # noqa: E402
    DiagnosticsController,
)
from inductor_designer.ui.project_session import ProjectSession  # noqa: E402
from tests.unit.domain.test_project import make_project  # noqa: E402

pytestmark = pytest.mark.ui


def _controller(tmp_path: Path) -> DiagnosticsController:
    QGuiApplication.instance() or QGuiApplication([])
    document = tmp_path / "boost.inductor.json"
    document.write_text("{}", encoding="utf-8")
    log_path = tmp_path / "logs" / "inductor-designer.log"
    log_path.parent.mkdir()
    log_path.write_text(r"warn C:\Users\jane.doe\b.aedt" + "\n", encoding="utf-8")
    session = ProjectSession(make_project(), document_path=document)
    return DiagnosticsController(
        session, log_path, RedactionContext(user_names=("jane.doe",))
    )


def test_saving_writes_a_redacted_archive(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    target = tmp_path / f"out{BUNDLE_SUFFIX}"

    assert controller.saveBundle(QUrl.fromLocalFile(str(target))) is True

    with zipfile.ZipFile(target) as archive:
        payload = "".join(
            archive.read(name).decode("utf-8") for name in archive.namelist()
        )
    assert "jane.doe" not in payload
    assert "no file paths" in controller.message


def test_an_unwritable_target_is_reported_not_raised(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    target = tmp_path / "missing-directory-file" / "x.zip"
    (tmp_path / "missing-directory-file").write_text("blocked", encoding="utf-8")

    assert controller.saveBundle(QUrl.fromLocalFile(str(target))) is False
    assert "Unable to write" in controller.message


def test_the_suggested_name_carries_the_bundle_suffix(tmp_path: Path) -> None:
    """A timestamped name only -- no path, no project name. This is the one
    string that gets pasted into e-mails and ticket titles, so a mutant that
    returns the full absolute document path must fail here, not just a
    suffix check that a full path would also satisfy.
    """
    name = _controller(tmp_path).suggestedFileName

    assert name.endswith(BUNDLE_SUFFIX)
    assert "/" not in name
    assert "\\" not in name
    assert "boost" not in name  # the project document's stem


def test_the_outcome_reaches_the_visible_status_bar(tmp_path: Path) -> None:
    """`message` was bound nowhere in QML and the result was discarded.

    So a failed write looked exactly like a successful one -- the user attached a
    file that did not exist -- and the success sentence, the one place the
    application says the artifact is safe to share, never rendered anywhere. Both
    outcomes now go through `ProjectSession.set_status`, which drives a status bar
    every other controller already uses.
    """
    controller = _controller(tmp_path)
    session = controller._session

    assert controller.saveBundle(
        QUrl.fromLocalFile(str(tmp_path / f"out{BUNDLE_SUFFIX}"))
    ) is True
    assert "no file paths" in session.statusMessage

    # A directory as the target is a write that cannot succeed.
    refused = tmp_path / "refused"
    refused.mkdir()
    assert controller.saveBundle(QUrl.fromLocalFile(str(refused))) is False
    assert "Unable to write the diagnostic bundle" in session.statusMessage
