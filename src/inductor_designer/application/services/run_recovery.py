"""Reconcile the runs a killed process left behind (ADR 0007, roadmap 8).

`start_project_run` writes a `"status": "running"` marker before it dispatches
to an adapter and overwrites it with the real manifest when the run ends. A
document still reading `running` therefore means the process died mid-run, and
the only truthful thing to say about it is that it was interrupted and produced
no result.

Recovery never re-solves. The Maxwell solve sequence saves the project before
it analyses, so an interrupted run leaves a saved-but-unsolved `*.aedt` behind;
re-solving such a directory was observed on 2026-08-18 to fail with AEDT's
`Engine Detected Error` on a missing `.adp`. The reconciled record therefore
names the unsolved artifact and tells the user to start a new run, which gets
its own directory. Nothing here deletes a solver file: it is the user's output.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from inductor_designer.application.services.run_directory import (
    MANIFEST_FILENAME,
    RUNS_DIRECTORY_NAME,
)
from inductor_designer.simulation.run_contracts import RunStatus

INTERRUPTED_DIAGNOSTIC = "run.interrupted_before_completion"
UNSOLVED_ARTIFACT_DIAGNOSTIC = "run.artifact_saved_but_unsolved"

UNSOLVED_ARTIFACT_KIND = "unsolved-solver-project"
_SOLVER_FILE_SUFFIXES = (".aedt", ".fem")
_UNFINISHED_STATUSES = frozenset({RunStatus.RUNNING.value, RunStatus.INTERRUPTED.value})

_INTERRUPTED_MESSAGE = (
    "The application or the solver stopped before this run finished. No "
    "result was produced, and no part of this run may be read as a result."
)
_UNSOLVED_ARTIFACT_MESSAGE = (
    "A solver project was saved before the analysis ran, so it holds geometry "
    "and setup but no solution. Start a new run, which gets its own "
    "directory; solving this directory again fails on its missing solver data."
)


@dataclass(frozen=True, slots=True)
class UnfinishedRun:
    """One run directory that holds no outcome."""

    run_id: str
    backend: str
    mode: str | None
    directory: Path
    manifest_path: Path
    started_utc: str | None
    reconciled: bool


def _runs_root(project_document_path: Path) -> Path:
    return project_document_path.resolve().parent / RUNS_DIRECTORY_NAME


def _read_document(path: Path) -> dict[str, object] | None:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return loaded if isinstance(loaded, dict) else None


def _identity_from_directory(directory: Path) -> tuple[str, str]:
    """`<run-id>-<backend>` split from the right, because a run id has hyphens."""
    name = directory.name
    for backend in ("maxwell-3d", "maxwell-2d", "femm"):
        suffix = f"-{backend}"
        if name.endswith(suffix):
            return name[: -len(suffix)], backend
    return name, "unknown"


def find_unfinished_runs(project_document_path: Path) -> tuple[UnfinishedRun, ...]:
    """Every run directory that holds no outcome, oldest first.

    A directory with no manifest at all counts: `start_project_run` writes the
    marker immediately after allocating the directory (see
    `_write_running_marker` in `application/services/project_run.py`), so the
    window between "directory exists" and "marker exists" is a few
    microseconds today. Treating a missing manifest as unfinished rather than
    ignoring it is deliberately on the safe side of that race: silently
    skipping it would hide a lost run, and the assumption only breaks if that
    window is ever widened.
    """
    runs_root = _runs_root(project_document_path)
    if not runs_root.is_dir():
        return ()
    unfinished: list[UnfinishedRun] = []
    for directory in sorted(entry for entry in runs_root.iterdir() if entry.is_dir()):
        manifest_path = directory / MANIFEST_FILENAME
        document = _read_document(manifest_path) if manifest_path.is_file() else None
        if document is None:
            run_id, backend = _identity_from_directory(directory)
            unfinished.append(
                UnfinishedRun(
                    run_id=run_id,
                    backend=backend,
                    mode=None,
                    directory=directory,
                    manifest_path=manifest_path,
                    started_utc=None,
                    reconciled=False,
                )
            )
            continue
        status = document.get("status")
        if status not in _UNFINISHED_STATUSES:
            continue
        run_id_value = document.get("runId")
        backend_value = document.get("backend")
        mode_value = document.get("mode")
        started_value = document.get("startedUtc")
        fallback_id, fallback_backend = _identity_from_directory(directory)
        unfinished.append(
            UnfinishedRun(
                run_id=run_id_value if isinstance(run_id_value, str) else fallback_id,
                backend=(
                    backend_value
                    if isinstance(backend_value, str)
                    else fallback_backend
                ),
                mode=mode_value if isinstance(mode_value, str) else None,
                directory=directory,
                manifest_path=manifest_path,
                started_utc=started_value if isinstance(started_value, str) else None,
                reconciled=status == RunStatus.INTERRUPTED.value,
            )
        )
    return tuple(unfinished)


def _unsolved_artifacts(directory: Path) -> tuple[dict[str, str], ...]:
    return tuple(
        {"kind": UNSOLVED_ARTIFACT_KIND, "path": path.name}
        for path in sorted(directory.iterdir())
        if path.is_file() and path.suffix.casefold() in _SOLVER_FILE_SUFFIXES
    )


def reconcile_unfinished_runs(
    project_document_path: Path, *, now: datetime | None = None
) -> tuple[UnfinishedRun, ...]:
    """Rewrite every unreconciled record as interrupted. Idempotent.

    Returns every unfinished run, reconciled or already reconciled, so a caller
    can display them without a second scan.

    Not written atomically (mkstemp + os.replace): the manifest writes this
    reconciles after -- `_write_running_document` and `_write_manifest` in
    `application/services/project_run.py` -- are themselves plain
    `Path.write_text` calls, not the mkstemp-then-`os.replace` pattern used for
    the project document and the recovery snapshot. This follows that existing
    (non-atomic) run-manifest practice rather than silently introducing a
    stronger guarantee only for the reconciled record.
    """
    moment = (datetime.now(timezone.utc) if now is None else now).astimezone(
        timezone.utc
    )
    for run in find_unfinished_runs(project_document_path):
        if run.reconciled:
            continue
        artifacts = _unsolved_artifacts(run.directory)
        diagnostics = [f"{INTERRUPTED_DIAGNOSTIC}: {_INTERRUPTED_MESSAGE}"]
        if artifacts:
            diagnostics.append(
                f"{UNSOLVED_ARTIFACT_DIAGNOSTIC}: {_UNSOLVED_ARTIFACT_MESSAGE}"
            )
        document = {
            "runId": run.run_id,
            "backend": run.backend,
            "mode": run.mode,
            "status": RunStatus.INTERRUPTED.value,
            "startedUtc": run.started_utc,
            "reconciledUtc": moment.isoformat(),
            "diagnostics": diagnostics,
            "artifacts": [dict(artifact) for artifact in artifacts],
            # Never a result: an interrupted run has none, and an absent key
            # would let a reader assume one was simply not exported.
            "results": None,
        }
        run.manifest_path.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return find_unfinished_runs(project_document_path)
