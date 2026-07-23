from __future__ import annotations

from collections.abc import Collection, Mapping
from typing import Protocol

from inductor_designer.materials.identity import MaterialRef
from inductor_designer.materials.records import MaterialRecord


class MaterialLookupError(KeyError):
    """Raised when a requested material revision does not exist."""


class MaterialRepository(Protocol):
    def list_materials(self) -> tuple[MaterialRef, ...]: ...

    def list_revisions(self, ref: MaterialRef) -> tuple[str, ...]: ...

    def get(self, ref: MaterialRef, revision_id: str) -> MaterialRecord: ...

    def latest_approved(self, ref: MaterialRef) -> MaterialRecord | None: ...

    def save(self, record: MaterialRecord, sources: Mapping[str, bytes]) -> None: ...

    def source_bytes(self, ref: MaterialRef, revision_id: str) -> Mapping[str, bytes]: ...

    def delete_revision(self, ref: MaterialRef, revision_id: str) -> None: ...

    def delete_material(
        self, ref: MaterialRef, protected_revision_ids: Collection[str] = ()
    ) -> None: ...
