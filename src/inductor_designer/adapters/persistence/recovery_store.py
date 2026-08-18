"""The autosaved recovery snapshot: one project, plus where it came from.

The snapshot document is written by `ProjectRepository`, so it inherits
schema-v5 validation, the non-finite refusal, and the atomic temp-file replace.
A snapshot that cannot be loaded back is therefore never written.

The index is written after the document, so a half-written pair is detected as
"no snapshot" rather than restored as a project.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from inductor_designer.adapters.persistence.project_repository import ProjectRepository
from inductor_designer.domain.project import InductorProject

RECOVERY_INDEX_FILENAME = "recovery-index.json"
RECOVERY_DOCUMENT_FILENAME = "recovery.inductor.json"


def _write_atomic(path: Path, text: str) -> None:
    """Write `text` to `path` so a crash mid-write never leaves a truncated
    file behind. Mirrors `ProjectRepository.save`'s mkstemp + os.replace, kept
    on the same volume as `path` so the replace is guaranteed atomic."""
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
            descriptor = -1
            stream.write(text)
            stream.flush()
        os.replace(temporary_path, path)
    finally:
        if descriptor != -1:
            os.close(descriptor)
        temporary_path.unlink(missing_ok=True)


@dataclass(frozen=True, slots=True)
class RecoverySnapshot:
    """One autosaved project: where it belongs, when it was taken, where it is."""

    document_path: Path | None
    saved_at_utc: str
    project_path: Path


class RecoveryStore:
    def __init__(self, directory: Path, repository: ProjectRepository) -> None:
        self._directory = directory
        self._repository = repository

    @property
    def index_path(self) -> Path:
        return self._directory / RECOVERY_INDEX_FILENAME

    @property
    def document_path(self) -> Path:
        return self._directory / RECOVERY_DOCUMENT_FILENAME

    def write(
        self,
        project: InductorProject,
        document_path: Path | None,
        *,
        now: datetime | None = None,
    ) -> RecoverySnapshot:
        """Overwrite the snapshot. Raises rather than writing an invalid one."""
        self._directory.mkdir(parents=True, exist_ok=True)
        moment = (datetime.now(timezone.utc) if now is None else now).astimezone(
            timezone.utc
        )
        self._repository.save(project, self.document_path)
        _write_atomic(
            self.index_path,
            json.dumps(
                {
                    "documentPath": None if document_path is None else str(document_path),
                    "savedAtUtc": moment.isoformat(),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
        )
        return RecoverySnapshot(
            document_path=document_path,
            saved_at_utc=moment.isoformat(),
            project_path=self.document_path,
        )

    def read(self) -> RecoverySnapshot | None:
        """The snapshot, or None when there is nothing trustworthy to offer."""
        if not self.index_path.is_file() or not self.document_path.is_file():
            return None
        try:
            index = json.loads(self.index_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(index, dict):
            return None
        raw_path = index.get("documentPath")
        saved_at = index.get("savedAtUtc")
        if not isinstance(saved_at, str):
            return None
        return RecoverySnapshot(
            document_path=Path(raw_path) if isinstance(raw_path, str) else None,
            saved_at_utc=saved_at,
            project_path=self.document_path,
        )

    def load_project(self, snapshot: RecoverySnapshot) -> InductorProject:
        return self._repository.load(snapshot.project_path)

    def clear(self) -> None:
        self.index_path.unlink(missing_ok=True)
        self.document_path.unlink(missing_ok=True)
