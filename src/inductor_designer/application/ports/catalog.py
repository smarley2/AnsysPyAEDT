from __future__ import annotations

from typing import Protocol

from inductor_designer.domain.catalog_records import ConductorRecord, CoreRecord


class CatalogRepository(Protocol):
    """Read access to the compiled commercial catalog index."""

    def get_core(self, part_number: str) -> CoreRecord | None: ...

    def list_cores(self) -> tuple[CoreRecord, ...]: ...

    def get_conductor(self, name: str) -> ConductorRecord | None: ...

    def list_conductor_names(self) -> tuple[str, ...]: ...
