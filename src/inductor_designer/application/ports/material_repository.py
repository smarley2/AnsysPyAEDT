from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from inductor_designer.materials.identity import MaterialRef
from inductor_designer.materials.records import MaterialRecord


class MaterialLookupError(KeyError):
    """Raised when a requested material revision does not exist."""


class MaterialRepository(Protocol):
    def list_revisions(self, ref: MaterialRef) -> tuple[str, ...]: ...

    def get(self, ref: MaterialRef, revision_id: str) -> MaterialRecord: ...

    def latest_approved(self, ref: MaterialRef) -> MaterialRecord | None: ...

    def save(self, record: MaterialRecord, sources: Mapping[str, bytes]) -> None: ...

    def source_bytes(self, ref: MaterialRef, revision_id: str) -> Mapping[str, bytes]: ...
