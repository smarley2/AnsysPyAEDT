from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from inductor_designer.application.services.run_directory import (
    _MAX_RUNS_PER_SECOND,
    MANIFEST_FILENAME,
    RESULTS_DIRECTORY_NAME,
    RunDirectoryError,
    RunLocation,
    allocate_run_directory,
    artifact_path_for_manifest,
    discard_empty_run_directory,
    run_id_for,
)
from inductor_designer.simulation.run_contracts import RunBackend

MOMENT = datetime(2026, 7, 30, 10, 15, 0, tzinfo=timezone.utc)


def saved_project(tmp_path: Path) -> Path:
    path = tmp_path / "boost.inductor.json"
    path.write_text("{}", encoding="utf-8")
    return path


def test_run_id_is_a_utc_timestamp() -> None:
    assert run_id_for(MOMENT) == "20260730-101500"


def test_run_id_converts_a_local_moment_to_utc() -> None:
    local = MOMENT.astimezone(timezone(timedelta(hours=2)))

    assert run_id_for(local) == "20260730-101500"


def test_allocation_creates_the_adr_layout_next_to_the_project(tmp_path: Path) -> None:
    document = saved_project(tmp_path)

    location = allocate_run_directory(document, RunBackend.MAXWELL_3D, now=MOMENT)

    assert isinstance(location, RunLocation)
    assert location.run_id == "20260730-101500"
    assert location.project_directory == tmp_path.resolve()
    assert location.directory == tmp_path.resolve() / "runs" / "20260730-101500-maxwell-3d"
    assert location.directory.is_dir()
    assert location.results_directory == location.directory / "results"
    assert location.results_directory.is_dir()
    assert location.manifest_path == location.directory / MANIFEST_FILENAME


def test_each_backend_gets_its_own_directory(tmp_path: Path) -> None:
    document = saved_project(tmp_path)

    first = allocate_run_directory(document, RunBackend.MAXWELL_2D, now=MOMENT)
    second = allocate_run_directory(document, RunBackend.FEMM, now=MOMENT)

    assert first.directory.name == "20260730-101500-maxwell-2d"
    assert second.directory.name == "20260730-101500-femm"


def test_a_second_run_in_the_same_second_suffixes_the_run_id(tmp_path: Path) -> None:
    document = saved_project(tmp_path)

    first = allocate_run_directory(document, RunBackend.FEMM, now=MOMENT)
    second = allocate_run_directory(document, RunBackend.FEMM, now=MOMENT)
    third = allocate_run_directory(document, RunBackend.FEMM, now=MOMENT)

    assert first.run_id == "20260730-101500"
    assert second.run_id == "20260730-101500-2"
    assert third.run_id == "20260730-101500-3"
    assert second.directory.name == "20260730-101500-2-femm"
    assert len({first.directory, second.directory, third.directory}) == 3


def test_an_existing_run_directory_is_never_overwritten(tmp_path: Path) -> None:
    document = saved_project(tmp_path)
    existing = tmp_path / "runs" / "20260730-101500-femm"
    existing.mkdir(parents=True)
    (existing / "keep.txt").write_text("evidence", encoding="utf-8")

    location = allocate_run_directory(document, RunBackend.FEMM, now=MOMENT)

    assert location.directory != existing
    assert (existing / "keep.txt").read_text(encoding="utf-8") == "evidence"


def test_a_failed_results_mkdir_removes_the_empty_run_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    document = saved_project(tmp_path)
    original_mkdir = Path.mkdir

    def _failing_mkdir(self: Path, *args: object, **kwargs: object) -> None:
        if self.name == RESULTS_DIRECTORY_NAME:
            raise OSError("simulated: results directory could not be created")
        original_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", _failing_mkdir)

    with pytest.raises(OSError, match="simulated"):
        allocate_run_directory(document, RunBackend.FEMM, now=MOMENT)

    runs_root = tmp_path.resolve() / "runs"
    assert list(runs_root.iterdir()) == []


def test_allocation_is_refused_once_a_second_is_exhausted(tmp_path: Path) -> None:
    document = saved_project(tmp_path)
    runs_root = tmp_path.resolve() / "runs"
    base_id = run_id_for(MOMENT)
    for attempt in range(1, _MAX_RUNS_PER_SECOND + 1):
        run_id = base_id if attempt == 1 else f"{base_id}-{attempt}"
        (runs_root / f"{run_id}-femm").mkdir(parents=True)

    with pytest.raises(RunDirectoryError, match="100 runs already exist"):
        allocate_run_directory(document, RunBackend.FEMM, now=MOMENT)


def test_an_unsaved_project_is_refused_with_an_actionable_message(tmp_path: Path) -> None:
    with pytest.raises(RunDirectoryError, match="save the project"):
        allocate_run_directory(
            tmp_path / "never-saved.inductor.json",
            RunBackend.MAXWELL_3D,
            now=MOMENT,
        )


def test_a_directory_instead_of_a_document_is_refused(tmp_path: Path) -> None:
    with pytest.raises(RunDirectoryError, match="is not a file"):
        allocate_run_directory(tmp_path, RunBackend.MAXWELL_3D, now=MOMENT)


def test_artifact_paths_are_relative_to_the_project_directory(tmp_path: Path) -> None:
    artifact = tmp_path / "runs" / "20260730-101500-femm" / "Boost_2d.fem"

    assert (
        artifact_path_for_manifest(artifact, tmp_path)
        == "runs/20260730-101500-femm/Boost_2d.fem"
    )


def test_an_artifact_outside_the_project_directory_stays_absolute(tmp_path: Path) -> None:
    outside = tmp_path.parent / "elsewhere" / "Boost.aedt"

    value = artifact_path_for_manifest(outside, tmp_path)

    assert value == outside.resolve().as_posix()
    assert value.endswith("elsewhere/Boost.aedt")


def test_an_empty_run_directory_is_discarded(tmp_path: Path) -> None:
    location = allocate_run_directory(saved_project(tmp_path), RunBackend.FEMM, now=MOMENT)

    assert discard_empty_run_directory(location) is True
    assert not location.directory.exists()


def test_a_run_directory_holding_evidence_is_kept(tmp_path: Path) -> None:
    location = allocate_run_directory(saved_project(tmp_path), RunBackend.FEMM, now=MOMENT)
    location.manifest_path.write_text("{}", encoding="utf-8")

    assert discard_empty_run_directory(location) is False
    assert location.manifest_path.is_file()
