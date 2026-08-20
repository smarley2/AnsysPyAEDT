"""Read the bundle's sources from disk and write the archive.

Reading and zipping live here because they touch the filesystem; deciding what
is shareable lives in `application/services/diagnostic_bundle.py`. This module
never writes text it did not receive as a `BundleEntry`.
"""

from __future__ import annotations

import zipfile
from collections.abc import Sequence
from pathlib import Path

from inductor_designer.application.services.diagnostic_bundle import (
    BundleEntry,
    BundleSource,
)
from inductor_designer.application.services.run_directory import (
    MANIFEST_FILENAME,
    RESULTS_DIRECTORY_NAME,
    RUNS_DIRECTORY_NAME,
)

BUNDLE_SUFFIX = ".diagnostics.zip"
# A rotated log can be a megabyte; the tail is where the failure is.
_MAX_SOURCE_BYTES = 512_000
_RESULT_FILENAMES = ("solve-log.txt", "results.json", "results.csv")


def _read_tail(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    if len(text) <= _MAX_SOURCE_BYTES:
        return text
    return (
        "[earlier lines omitted to keep the bundle small]\n"
        + text[-_MAX_SOURCE_BYTES:]
    )


def collect_bundle_sources(
    project_document_path: Path | None, log_path: Path | None
) -> tuple[BundleSource, ...]:
    """The application log and every run's evidence. Missing files are skipped.

    `project_document_path` is used only to find `runs/` beside it. The document
    itself is never opened, by the 2026-08-18 ruling: it holds user-authored text
    that no redaction rule can classify, and every physical input it carries is in
    the run manifests anyway. `test_the_project_document_never_becomes_an_entry`
    is what stops this from being "fixed" into reading it.

    Only our own manifest and result files are collected out of a run directory
    -- never AEDT's own `.aedt`/`.fem` project files or its `batch.log`, which
    are excluded from the bundle entirely (2026-08-18 ruling) because their
    format and redaction are not ours to audit.
    """
    sources: list[BundleSource] = []
    if log_path is not None:
        for candidate in (log_path, *sorted(log_path.parent.glob(f"{log_path.name}.*"))):
            text = _read_tail(candidate) if candidate.is_file() else None
            if text is not None:
                sources.append(
                    BundleSource(name=f"logs/{candidate.name}", text=text)
                )
    if project_document_path is None:
        return tuple(sources)
    runs_root = project_document_path.resolve().parent / RUNS_DIRECTORY_NAME
    if not runs_root.is_dir():
        return tuple(sources)
    for directory in sorted(entry for entry in runs_root.iterdir() if entry.is_dir()):
        for relative in (
            Path(MANIFEST_FILENAME),
            *(Path(RESULTS_DIRECTORY_NAME) / name for name in _RESULT_FILENAMES),
        ):
            candidate = directory / relative
            text = _read_tail(candidate) if candidate.is_file() else None
            if text is not None:
                sources.append(
                    BundleSource(
                        name=f"runs/{directory.name}/{relative.as_posix()}",
                        text=text,
                    )
                )
    return tuple(sources)


def write_diagnostic_archive(path: Path, entries: Sequence[BundleEntry]) -> Path:
    """Write one deterministic, deflated archive of already-redacted entries."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for entry in entries:
            archive.writestr(entry.name, entry.text)
    return path
