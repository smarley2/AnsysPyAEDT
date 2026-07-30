"""Project-local run directories (ADR 0007).

A run lives next to the saved project document:

    <project-directory>/runs/<run-id>-<backend>/

Directories are created with ``exist_ok=False`` so a run can never overwrite an
earlier one, and the run id carries a ``-2``, ``-3`` ... suffix when an earlier
run already owns that UTC second. The run id in ``run-manifest.json`` and the
directory name always match.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from inductor_designer.simulation.run_contracts import RunBackend

RUNS_DIRECTORY_NAME = "runs"
RESULTS_DIRECTORY_NAME = "results"
MANIFEST_FILENAME = "run-manifest.json"

# A second holding this many runs is a runaway caller, not a double click.
_MAX_RUNS_PER_SECOND = 100


class RunDirectoryError(ValueError):
    """A run directory could not be allocated."""


@dataclass(frozen=True, slots=True)
class RunLocation:
    """Where one run writes. Paths are absolute; manifest paths are relative."""

    run_id: str
    project_directory: Path
    directory: Path
    results_directory: Path

    @property
    def manifest_path(self) -> Path:
        return self.directory / MANIFEST_FILENAME


def run_id_for(moment: datetime) -> str:
    """UTC ``YYYYMMDD-HHMMSS``; a local moment is converted, never truncated."""
    return moment.astimezone(timezone.utc).strftime("%Y%m%d-%H%M%S")


def allocate_run_directory(
    project_document_path: Path,
    backend: RunBackend,
    *,
    now: datetime | None = None,
) -> RunLocation:
    """Create one new run directory beside the saved project document."""
    if not project_document_path.exists():
        raise RunDirectoryError(
            f"Project document {project_document_path} does not exist; "
            "save the project before starting a run."
        )
    if not project_document_path.is_file():
        raise RunDirectoryError(
            f"Project document {project_document_path} is not a file; "
            "save the project before starting a run."
        )
    project_directory = project_document_path.resolve().parent
    base_id = run_id_for(datetime.now(timezone.utc) if now is None else now)
    runs_root = project_directory / RUNS_DIRECTORY_NAME
    for attempt in range(1, _MAX_RUNS_PER_SECOND + 1):
        run_id = base_id if attempt == 1 else f"{base_id}-{attempt}"
        directory = runs_root / f"{run_id}-{backend.value}"
        try:
            directory.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            continue
        results_directory = directory / RESULTS_DIRECTORY_NAME
        try:
            results_directory.mkdir()
        except OSError:
            directory.rmdir()
            raise
        return RunLocation(
            run_id=run_id,
            project_directory=project_directory,
            directory=directory,
            results_directory=results_directory,
        )
    raise RunDirectoryError(
        f"Could not allocate a run directory under {runs_root}: "
        f"{_MAX_RUNS_PER_SECOND} runs already exist for {base_id}."
    )


def artifact_path_for_manifest(path: Path, project_directory: Path) -> str:
    """Relative POSIX path so the project directory can be moved (ADR 0007).

    An artifact outside the project directory keeps an absolute path rather than
    a misleading ``../..`` chain.
    """
    resolved = path.resolve()
    try:
        return resolved.relative_to(project_directory.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def discard_empty_run_directory(location: RunLocation) -> bool:
    """Remove a run directory a blocked run never wrote into.

    Returns ``False`` and changes nothing when any evidence is present: a failed
    run keeps its directory and manifest.
    """
    try:
        location.results_directory.rmdir()
    except OSError:
        return False
    try:
        location.directory.rmdir()
    except OSError:
        location.results_directory.mkdir(exist_ok=True)
        return False
    return True
