from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone

from inductor_designer.application.ports.material_repository import MaterialLookupError
from inductor_designer.geometry.naming import sanitize_identifier
from inductor_designer.materials.identity import MaterialRef
from inductor_designer.materials.records import MaterialRecord, MaterialStatus
from inductor_designer.materials.serde import sha256_hex


class InMemoryMaterialRepository:
    def __init__(self) -> None:
        self._records: dict[tuple[MaterialRef, str], MaterialRecord] = {}
        self._sources: dict[tuple[MaterialRef, str], dict[str, bytes]] = {}

    @staticmethod
    def _validated_sources(
        record: MaterialRecord, sources: Mapping[str, bytes]
    ) -> dict[str, bytes]:
        verified = {}
        for provenance in record.sources:
            try:
                source = sources[provenance.filename]
            except KeyError as error:
                raise ValueError(
                    f"sha256 verification requires source {provenance.filename}"
                ) from error
            if sha256_hex(source) != provenance.sha256:
                raise ValueError(f"sha256 mismatch for source {provenance.filename}")
            verified[provenance.filename] = source
        return verified

    @staticmethod
    def _material_path_key(ref: MaterialRef) -> tuple[str, str, str]:
        values = tuple(
            sanitize_identifier(value).casefold()
            for value in (ref.manufacturer, ref.name, ref.grade)
        )
        return (values[0], values[1], values[2])

    @staticmethod
    def _created_at_key(record: MaterialRecord) -> tuple[float, str]:
        timestamp = datetime.fromisoformat(record.created_at.replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        return (timestamp.timestamp(), record.revision_id)

    def list_revisions(self, ref: MaterialRef) -> tuple[str, ...]:
        return tuple(
            sorted(
                revision for material_ref, revision in self._records if material_ref == ref
            )
        )

    def get(self, ref: MaterialRef, revision_id: str) -> MaterialRecord:
        try:
            return self._records[(ref, revision_id)]
        except KeyError as error:
            raise MaterialLookupError(
                f"unknown material revision: {ref!r} {revision_id}"
            ) from error

    def latest_approved(self, ref: MaterialRef) -> MaterialRecord | None:
        approved = (
            record
            for (material_ref, _), record in self._records.items()
            if material_ref == ref and record.status is MaterialStatus.APPROVED
        )
        return max(
            approved,
            key=self._created_at_key,
            default=None,
        )

    def save(self, record: MaterialRecord, sources: Mapping[str, bytes]) -> None:
        verified = self._validated_sources(record, sources)
        requested_key = self._material_path_key(record.ref)
        if any(
            stored_ref != record.ref and self._material_path_key(stored_ref) == requested_key
            for stored_ref, _ in self._records
        ):
            raise ValueError("material identity paths collide after sanitizing")
        source_names = [
            sanitize_identifier(source.filename).casefold() for source in record.sources
        ]
        if len(source_names) != len(set(source_names)):
            raise ValueError("source filenames collide after sanitizing")
        points_names = [
            sanitize_identifier(series.series_id).casefold() for series in record.series
        ]
        if len(points_names) != len(set(points_names)):
            raise ValueError("series identifiers collide after sanitizing")
        key = (record.ref, record.revision_id)
        stored = self._records.get(key)
        if stored is not None and stored.status is MaterialStatus.APPROVED:
            raise ValueError("approved material revisions are immutable")
        self._records[key] = record
        self._sources[key] = verified

    def source_bytes(self, ref: MaterialRef, revision_id: str) -> Mapping[str, bytes]:
        self.get(ref, revision_id)
        return dict(self._sources[(ref, revision_id)])
