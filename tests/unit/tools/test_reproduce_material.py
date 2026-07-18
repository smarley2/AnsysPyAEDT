from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from inductor_designer.application.ports.material_repository import MaterialLookupError
from inductor_designer.materials.identity import MaterialRef
from inductor_designer.materials.replay import ReproductionReport
from tools import reproduce_material


class StubRepository:
    def __init__(self, root: Path, *, error: Exception | None = None) -> None:
        self.root = root
        self.error = error
        self.ref: MaterialRef | None = None
        self.revision = ""

    def get(self, ref: MaterialRef, revision_id: str) -> object:
        self.ref = ref
        self.revision = revision_id
        if self.error is not None:
            raise self.error
        return SimpleNamespace(ref=ref, revision_id=revision_id)

    def source_bytes(self, ref: MaterialRef, revision_id: str) -> dict[str, bytes]:
        assert ref == self.ref
        assert revision_id == self.revision
        return {"source.csv": b"x,y\n"}


def _arguments(root: Path) -> list[str]:
    return [
        "--overlay-root",
        str(root),
        "--manufacturer",
        "Example",
        "--name",
        "Ferrite",
        "--grade",
        "F1",
        "--revision",
        "0123456789ab",
    ]


def test_main_prints_match_and_uses_requested_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repository = StubRepository(tmp_path)
    monkeypatch.setattr(
        reproduce_material, "FileOverlayMaterialRepository", lambda root: repository
    )
    monkeypatch.setattr(
        reproduce_material,
        "reproduce_record",
        lambda record, sources: ReproductionReport(True, ()),
    )

    assert reproduce_material.main(_arguments(tmp_path)) == 0
    assert capsys.readouterr().out == "MATCH\n"
    assert repository.root == tmp_path
    assert repository.ref == MaterialRef("Example", "Ferrite", "F1")
    assert repository.revision == "0123456789ab"


def test_main_prints_each_replay_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repository = StubRepository(tmp_path)
    monkeypatch.setattr(
        reproduce_material, "FileOverlayMaterialRepository", lambda root: repository
    )
    monkeypatch.setattr(
        reproduce_material,
        "reproduce_record",
        lambda record, sources: ReproductionReport(
            False, ("series 'bh' points mismatch", "revision ID mismatch")
        ),
    )

    assert reproduce_material.main(_arguments(tmp_path)) == 1
    assert capsys.readouterr().out == (
        "series 'bh' points mismatch\nrevision ID mismatch\n"
    )


@pytest.mark.parametrize(
    "error, message",
    [
        (MaterialLookupError("missing"), "unknown material revision"),
        (
            ValueError("CSV/JSON point disagreement for series bh"),
            "CSV/JSON point disagreement for series bh",
        ),
    ],
)
def test_main_reports_repository_errors_without_traceback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    error: Exception,
    message: str,
) -> None:
    repository = StubRepository(tmp_path, error=error)
    monkeypatch.setattr(
        reproduce_material, "FileOverlayMaterialRepository", lambda root: repository
    )

    assert reproduce_material.main(_arguments(tmp_path)) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == f"ERROR: {message}\n"


def test_main_reports_invalid_material_identity_without_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    arguments = _arguments(tmp_path)
    arguments[arguments.index("--manufacturer") + 1] = " "

    assert reproduce_material.main(arguments) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "ERROR: MaterialRef manufacturer cannot be blank\n"
