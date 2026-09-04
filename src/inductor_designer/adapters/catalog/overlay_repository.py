"""A user's own cores, layered over the shipped catalog index.

Design: ``docs/superpowers/specs/2026-09-04-user-core-catalog-design.md``.

Reading goes through the same ``CatalogRepository`` port as the shipped
index, so every screen, service and exporter sees imported cores without
knowing they exist -- ``list_cores()`` simply returns more. Writing is a file
per core, named for the part number, under the per-user data directory.

Two rules live here rather than in the caller, because both are about what a
core record is allowed to claim:

* A shipped part number is never replaced by a local file. Import refuses the
  collision (``write_overlay_core``), and on the one path that refusal cannot
  cover -- a release adding a part number a user had already imported -- the
  shipped record wins on read and the ignored file is reported by name.
* An imported core is always ``draft``. ``catalog/README.md`` rules that only
  a human reviewer may set ``reviewed``, after checking every number against
  the cited source page, and an import is not that reviewer.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from inductor_designer.adapters.persistence.record_serde import (
    core_record_from_json,
    core_record_to_json,
)
from inductor_designer.domain.catalog_records import ReviewStatus
from inductor_designer.geometry.naming import sanitize_identifier

if TYPE_CHECKING:
    from inductor_designer.application.ports.catalog import CatalogRepository
    from inductor_designer.domain.catalog_records import ConductorRecord, CoreRecord

#: The subdirectory cores occupy inside the overlay root, so conductors or
#: another record type can be added later without moving files.
CORES_DIRECTORY_NAME = "cores"


class CoreOverlayError(ValueError):
    """A core cannot be added to the overlay, with the reason a user reads."""


def _core_path(overlay_root: Path, part_number: str) -> Path:
    return (
        overlay_root
        / CORES_DIRECTORY_NAME
        / f"{sanitize_identifier(part_number)}.json"
    )


def write_overlay_core(
    overlay_root: Path,
    record: CoreRecord,
    shipped: CatalogRepository | None = None,
) -> Path:
    """Store one core in the overlay, as a draft, and return its file path.

    ``shipped`` is what makes the collision refusal possible, so import passes
    it. Called without it, this writes whatever it is given -- which is how the
    shadowing test reproduces a file the catalog only grew a conflict with
    later.
    """
    if shipped is not None and shipped.get_core(record.part_number) is not None:
        raise CoreOverlayError(
            f"{record.part_number} is already a catalog core. Local cores "
            "cannot replace a shipped part: rename yours, or use the shipped "
            "one."
        )
    stored = replace(record, review_status=ReviewStatus.DRAFT, reviewed_by=None)
    path = _core_path(overlay_root, stored.part_number)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(core_record_to_json(stored), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


class OverlayCatalogRepository:
    """The shipped index plus the user's own cores, behind one port."""

    def __init__(self, shipped: CatalogRepository, overlay_root: Path) -> None:
        self._shipped = shipped
        self._overlay_root = overlay_root

    @property
    def overlay_root(self) -> Path:
        return self._overlay_root

    def _overlay_files(self) -> tuple[Path, ...]:
        directory = self._overlay_root / CORES_DIRECTORY_NAME
        if not directory.is_dir():
            return ()
        return tuple(sorted(directory.glob("*.json")))

    def _read(self) -> tuple[dict[str, CoreRecord], tuple[str, ...], tuple[str, ...]]:
        """Every readable overlay core, plus what had to be set aside.

        Returns the usable records by part number, the part numbers the
        shipped index also has (shadowed, so ignored), and the filenames that
        could not be parsed at all. One corrupt file must not take the whole
        core list with it -- the same tolerance
        ``FileOverlayMaterialRepository._parse_or_skip`` already has.
        """
        records: dict[str, CoreRecord] = {}
        shadowed: list[str] = []
        unreadable: list[str] = []
        for path in self._overlay_files():
            try:
                record = core_record_from_json(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError, KeyError, TypeError):
                unreadable.append(path.name)
                continue
            if self._shipped.get_core(record.part_number) is not None:
                shadowed.append(record.part_number)
                continue
            records[record.part_number] = record
        return records, tuple(shadowed), tuple(unreadable)

    def get_core(self, part_number: str) -> CoreRecord | None:
        # Shipped first: a local file must never answer for a catalog part.
        shipped = self._shipped.get_core(part_number)
        if shipped is not None:
            return shipped
        return self._read()[0].get(part_number)

    def list_cores(self) -> tuple[CoreRecord, ...]:
        records, _shadowed, _unreadable = self._read()
        return tuple(
            sorted(
                (*self._shipped.list_cores(), *records.values()),
                key=lambda core: core.part_number,
            )
        )

    def get_conductor(self, name: str) -> ConductorRecord | None:
        return self._shipped.get_conductor(name)

    def list_conductor_names(self) -> tuple[str, ...]:
        return self._shipped.list_conductor_names()

    def overlay_part_numbers(self) -> tuple[str, ...]:
        """Which of the offered cores came from the user's own overlay.

        The Core & Material screen labels each core's origin from this, so a
        transcribed core never looks like a datasheet-reviewed shipped part.
        Exposed as part numbers rather than records so the application layer
        never has to know this adapter's type.
        """
        return tuple(sorted(self._read()[0]))

    def shadowed_part_numbers(self) -> tuple[str, ...]:
        return self._read()[1]

    def unreadable_files(self) -> tuple[str, ...]:
        return self._read()[2]
