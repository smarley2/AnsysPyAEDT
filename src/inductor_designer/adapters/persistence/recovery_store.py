"""The autosaved recovery snapshot: one project, plus where it came from.

The snapshot document is written by `ProjectRepository`, so it inherits
schema-v5 validation, the non-finite refusal, and the atomic temp-file replace.
A snapshot that cannot be loaded back is therefore never written.

The index is written after the document, so a half-written pair is detected as
"no snapshot" rather than restored as a project.

Each project document gets its own SLOT (Task 9 follow-up 1): two windows
editing two different projects used to share one global index/document pair,
so the later autosave silently overwrote the earlier one -- and because the
recovery offer only fires when the document path matches, the loser's work
was never even offered back. A slot is named from a hash of the resolved,
case-folded document path rather than the path itself, so this directory's
contents stay shareable-adjacent (it sits next to the log directory the
diagnostic bundle collects from) even though nothing here redacts a filename.
"""

from __future__ import annotations

import hashlib
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

# An unsaved project (`document_path is None`) has nothing to hash, and only
# one such project can exist per window -- so it gets one fixed reserved slot
# instead of a digest. Not a valid hex digest itself, so it cannot collide
# with one.
_UNSAVED_SLOT_KEY = "unsaved"


def _slot_key(document_path: Path | None) -> str:
    """A short, path-free name for the document's slot.

    Case-folded: Windows paths are case-insensitive and `WindowsPath.__eq__`
    already compares that way, so `C:\\W\\boost` and `c:\\w\\boost` must hash
    to the same slot. Resolved: `main.py` passes `args.project` unresolved,
    so a relative launch and an absolute one of the same file must land in
    the same slot too (`RecoveryController._offerable` resolves both sides
    of its own comparison for the identical reason).
    """
    if document_path is None:
        return _UNSAVED_SLOT_KEY
    digest = hashlib.sha256(str(document_path.resolve()).casefold().encode())
    return digest.hexdigest()[:16]


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


@dataclass(frozen=True, slots=True)
class RecoverySlot:
    """The two files that make up one project document's recovery snapshot.

    `snapshot_path`, not `document_path`: this is the SNAPSHOT file living in
    the recovery directory, the opposite of `RecoverySnapshot.document_path`
    above, which is the USER's project file. Sharing a name between the two
    would let `store.read(slot.document_path)` type-check while silently
    keying a slot off a slot.
    """

    index_path: Path
    snapshot_path: Path


class RecoveryStore:
    def __init__(self, directory: Path, repository: ProjectRepository) -> None:
        self._directory = directory
        self._repository = repository

    def slot_for(self, document_path: Path | None) -> RecoverySlot:
        """The index/document pair that belongs to `document_path`."""
        key = _slot_key(document_path)
        return RecoverySlot(
            index_path=self._directory / f"{key}.{RECOVERY_INDEX_FILENAME}",
            snapshot_path=self._directory / f"{key}.{RECOVERY_DOCUMENT_FILENAME}",
        )

    def write(
        self,
        project: InductorProject,
        document_path: Path | None,
        *,
        now: datetime | None = None,
    ) -> RecoverySnapshot:
        """Overwrite the snapshot for `document_path`'s slot only.

        Raises rather than writing an invalid one.
        """
        slot = self.slot_for(document_path)
        self._directory.mkdir(parents=True, exist_ok=True)
        moment = (datetime.now(timezone.utc) if now is None else now).astimezone(
            timezone.utc
        )
        self._repository.save(project, slot.snapshot_path)
        _write_atomic(
            slot.index_path,
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
            project_path=slot.snapshot_path,
        )

    def read(self, document_path: Path | None) -> RecoverySnapshot | None:
        """`document_path`'s slot, or None when there is nothing trustworthy
        to offer."""
        slot = self.slot_for(document_path)
        if not slot.index_path.is_file() or not slot.snapshot_path.is_file():
            return None
        try:
            index = json.loads(slot.index_path.read_text(encoding="utf-8"))
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
            project_path=slot.snapshot_path,
        )

    def load_project(self, snapshot: RecoverySnapshot) -> InductorProject:
        return self._repository.load(snapshot.project_path)

    def clear(self, document_path: Path | None) -> None:
        """Clear `document_path`'s slot only -- a save in one window must not
        discard another window's recovery copy."""
        slot = self.slot_for(document_path)
        slot.index_path.unlink(missing_ok=True)
        slot.snapshot_path.unlink(missing_ok=True)
