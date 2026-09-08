from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from inductor_designer.application.services.run_recovery import (
    INTERRUPTED_DIAGNOSTIC,
    UNSOLVED_ARTIFACT_DIAGNOSTIC,
    find_unfinished_runs,
    reconcile_unfinished_runs,
)
from inductor_designer.simulation.run_contracts import RunStatus

NOW = datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc)


def _project(tmp_path: Path) -> Path:
    path = tmp_path / "boost.inductor.json"
    path.write_text("{}", encoding="utf-8")
    return path


def _run(tmp_path: Path, run_id: str, backend: str, status: str | None) -> Path:
    directory = tmp_path / "runs" / f"{run_id}-{backend}"
    (directory / "results").mkdir(parents=True)
    if status is not None:
        (directory / "run-manifest.json").write_text(
            json.dumps(
                {
                    "runId": run_id,
                    "backend": backend,
                    "mode": "generate-and-solve",
                    "status": status,
                    "startedUtc": "2026-08-18T10:15:00+00:00",
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    return directory


def test_no_runs_directory_finds_nothing(tmp_path: Path) -> None:
    assert find_unfinished_runs(_project(tmp_path)) == ()


def test_a_succeeded_run_is_not_unfinished(tmp_path: Path) -> None:
    project = _project(tmp_path)
    _run(tmp_path, "20260818-101500", "maxwell-3d", RunStatus.SUCCEEDED.value)

    assert find_unfinished_runs(project) == ()


def test_a_running_manifest_is_unfinished(tmp_path: Path) -> None:
    project = _project(tmp_path)
    _run(tmp_path, "20260818-101500", "maxwell-3d", RunStatus.RUNNING.value)

    found = find_unfinished_runs(project)

    assert [run.run_id for run in found] == ["20260818-101500"]
    assert found[0].backend == "maxwell-3d"
    assert found[0].reconciled is False


def test_a_run_directory_without_a_manifest_is_unfinished(tmp_path: Path) -> None:
    project = _project(tmp_path)
    _run(tmp_path, "20260818-101500", "femm", None)

    found = find_unfinished_runs(project)

    assert [run.backend for run in found] == ["femm"]
    assert found[0].started_utc is None


def test_reconcile_rewrites_running_to_interrupted(tmp_path: Path) -> None:
    project = _project(tmp_path)
    directory = _run(tmp_path, "20260818-101500", "maxwell-3d", RunStatus.RUNNING.value)

    reconcile_unfinished_runs(project, now=NOW)

    document = json.loads(
        (directory / "run-manifest.json").read_text(encoding="utf-8")
    )
    assert document["status"] == RunStatus.INTERRUPTED.value
    assert document["startedUtc"] == "2026-08-18T10:15:00+00:00"
    assert document["reconciledUtc"] == "2026-08-18T12:00:00+00:00"
    assert document["results"] is None
    assert any(
        line.startswith(INTERRUPTED_DIAGNOSTIC) for line in document["diagnostics"]
    )


def test_a_saved_but_unsolved_solver_file_is_named_and_never_reused(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path)
    directory = _run(tmp_path, "20260818-101500", "maxwell-3d", RunStatus.RUNNING.value)
    (directory / "Inductor3D.aedt").write_text("saved before the solve", encoding="utf-8")

    reconcile_unfinished_runs(project, now=NOW)

    document = json.loads(
        (directory / "run-manifest.json").read_text(encoding="utf-8")
    )
    advice = next(
        line
        for line in document["diagnostics"]
        if line.startswith(UNSOLVED_ARTIFACT_DIAGNOSTIC)
    )
    assert "new run" in advice.casefold()
    assert document["artifacts"] == [
        {"kind": "unsolved-solver-project", "path": "Inductor3D.aedt"}
    ]
    # The evidence is preserved, not deleted: it is the user's file.
    assert (directory / "Inductor3D.aedt").is_file()


def test_reconcile_is_idempotent(tmp_path: Path) -> None:
    project = _project(tmp_path)
    directory = _run(tmp_path, "20260818-101500", "femm", RunStatus.RUNNING.value)

    reconcile_unfinished_runs(project, now=NOW)
    first = (directory / "run-manifest.json").read_text(encoding="utf-8")
    reconcile_unfinished_runs(
        project, now=datetime(2026, 8, 18, 13, 0, 0, tzinfo=timezone.utc)
    )

    assert (directory / "run-manifest.json").read_text(encoding="utf-8") == first


def test_an_interrupted_run_stays_visible_after_reconciliation(tmp_path: Path) -> None:
    project = _project(tmp_path)
    _run(tmp_path, "20260818-101500", "femm", RunStatus.RUNNING.value)

    reconcile_unfinished_runs(project, now=NOW)
    found = find_unfinished_runs(project)

    assert [run.reconciled for run in found] == [True]


def test_a_cancelled_run_is_not_unfinished(tmp_path: Path) -> None:
    project = _project(tmp_path)
    _run(tmp_path, "20260818-101500", "femm", RunStatus.CANCELLED.value)

    assert find_unfinished_runs(project) == ()


def test_a_directory_without_a_known_backend_suffix_is_ignored(tmp_path: Path) -> None:
    """A `runs/` subdirectory this module did not create (any name not ending
    in a `RunBackend` suffix) must never be treated as a run: not listed as
    unfinished, and never written into by reconcile."""
    project = _project(tmp_path)
    directory = tmp_path / "runs" / "not-a-run"
    directory.mkdir(parents=True)

    assert find_unfinished_runs(project) == ()

    reconcile_unfinished_runs(project, now=NOW)

    assert list(directory.iterdir()) == []
