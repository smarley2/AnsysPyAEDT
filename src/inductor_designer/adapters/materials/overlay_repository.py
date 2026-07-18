from __future__ import annotations

import json
import shutil
import tempfile
import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from inductor_designer.application.ports.material_repository import MaterialLookupError
from inductor_designer.geometry.naming import sanitize_identifier
from inductor_designer.materials.identity import MaterialRef
from inductor_designer.materials.records import MaterialRecord, MaterialStatus
from inductor_designer.materials.serde import (
    material_record_from_json,
    material_record_json,
    material_record_to_json,
    parse_points_csv,
    points_csv,
    sha256_hex,
)


class FileOverlayMaterialRepository:
    def __init__(self, root: Path) -> None:
        self._root = root

    def _material_directory(self, ref: MaterialRef) -> Path:
        return (
            self._root
            / sanitize_identifier(ref.manufacturer)
            / sanitize_identifier(ref.name)
            / sanitize_identifier(ref.grade)
        )

    def _revision_directory(self, ref: MaterialRef, revision_id: str) -> Path:
        return self._material_directory(ref) / sanitize_identifier(revision_id)

    @staticmethod
    def _source_name(filename: str) -> str:
        return sanitize_identifier(filename)

    @staticmethod
    def _points_name(series_id: str) -> str:
        return f"points-{sanitize_identifier(series_id)}.csv"

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

    @staticmethod
    def _document(path: Path) -> Mapping[str, Any]:
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            raise ValueError(f"missing persisted material artifact: {path.name}") from error
        if not isinstance(document, Mapping):
            raise ValueError("persisted material record must be a JSON object")
        return document

    def _load_record(
        self,
        ref: MaterialRef,
        revision_id: str,
        revision_directory: Path,
        *,
        alias_is_unknown: bool = False,
    ) -> MaterialRecord:
        record = material_record_from_json(self._document(revision_directory / "record.json"))
        if record.ref != ref:
            if alias_is_unknown:
                raise MaterialLookupError(f"unknown material revision: {ref!r} {revision_id}")
            raise ValueError("persisted material identity does not match its repository path")
        if record.revision_id != revision_id:
            if alias_is_unknown and sanitize_identifier(record.revision_id).casefold() == (
                sanitize_identifier(revision_id).casefold()
            ):
                raise MaterialLookupError(f"unknown material revision: {ref!r} {revision_id}")
            raise ValueError("persisted material identity does not match its repository path")
        return record

    def _reject_material_path_alias(self, ref: MaterialRef) -> None:
        requested_key = self._material_path_key(ref)
        for path in self._root.glob("*/*/*/*/record.json"):
            stored = material_record_from_json(self._document(path))
            if stored.ref != ref and self._material_path_key(stored.ref) == requested_key:
                raise ValueError("material identity paths collide after sanitizing")

    @staticmethod
    def _validate_source_mapping(
        record: MaterialRecord, sources: Mapping[str, bytes]
    ) -> None:
        expected = {provenance.filename for provenance in record.sources}
        if set(sources) != expected:
            raise ValueError("sources mapping keys must exactly match provenance filenames")
        for provenance in record.sources:
            source = sources[provenance.filename]
            if sha256_hex(source) != provenance.sha256:
                raise ValueError(f"sha256 mismatch for source {provenance.filename}")

    @staticmethod
    def _validate_canonical_points(record: MaterialRecord) -> None:
        if any(
            value != round(value, 9)
            for series in record.series
            for point in series.points
            for value in (point.x, point.y)
        ):
            raise ValueError("material points must already satisfy round(9)")

    def _read_sources(
        self, record: MaterialRecord, revision_directory: Path
    ) -> dict[str, bytes]:
        sources: dict[str, bytes] = {}
        for provenance in record.sources:
            path = revision_directory / "sources" / self._source_name(provenance.filename)
            try:
                sources[provenance.filename] = path.read_bytes()
            except FileNotFoundError as error:
                raise ValueError(
                    f"missing persisted source {provenance.filename}"
                ) from error
        self._validate_source_mapping(record, sources)
        return sources

    def _verify_points(self, record: MaterialRecord, revision_directory: Path) -> None:
        for series in record.series:
            path = revision_directory / self._points_name(series.series_id)
            try:
                stored = parse_points_csv(path.read_text(encoding="utf-8"))
            except FileNotFoundError as error:
                raise ValueError(
                    f"missing persisted points CSV for series {series.series_id}"
                ) from error
            expected = tuple((point.x, point.y) for point in series.points)
            if stored != expected:
                raise ValueError(f"CSV/JSON point disagreement for series {series.series_id}")

    def _load_verified(
        self, ref: MaterialRef, revision_id: str
    ) -> tuple[MaterialRecord, dict[str, bytes]]:
        revision_directory = self._revision_directory(ref, revision_id)
        if not revision_directory.is_dir():
            raise MaterialLookupError(f"unknown material revision: {ref!r} {revision_id}")
        record = self._load_record(
            ref, revision_id, revision_directory, alias_is_unknown=True
        )
        sources = self._read_sources(record, revision_directory)
        self._verify_points(record, revision_directory)
        return record, sources

    def list_revisions(self, ref: MaterialRef) -> tuple[str, ...]:
        material_directory = self._material_directory(ref)
        if not material_directory.is_dir():
            return ()
        revisions = []
        for path in material_directory.iterdir():
            if not path.is_dir() or path.name.startswith("."):
                continue
            record = material_record_from_json(self._document(path / "record.json"))
            if record.ref != ref:
                return ()
            revisions.append(record.revision_id)
        return tuple(sorted(revisions))

    def get(self, ref: MaterialRef, revision_id: str) -> MaterialRecord:
        record, _ = self._load_verified(ref, revision_id)
        return record

    def latest_approved(self, ref: MaterialRef) -> MaterialRecord | None:
        approved = (
            record
            for revision_id in self.list_revisions(ref)
            if (record := self.get(ref, revision_id)).status is MaterialStatus.APPROVED
        )
        return max(
            approved,
            key=self._created_at_key,
            default=None,
        )

    def save(self, record: MaterialRecord, sources: Mapping[str, bytes]) -> None:
        self._validate_source_mapping(record, sources)
        self._validate_canonical_points(record)
        self._reject_material_path_alias(record.ref)
        source_names = [
            self._source_name(source.filename).casefold() for source in record.sources
        ]
        if len(source_names) != len(set(source_names)):
            raise ValueError("source filenames collide after sanitizing")
        points_names = [
            self._points_name(series.series_id).casefold() for series in record.series
        ]
        if len(points_names) != len(set(points_names)):
            raise ValueError("series identifiers collide after sanitizing")

        revision_directory = self._revision_directory(record.ref, record.revision_id)
        if revision_directory.exists():
            stored = self._load_record(record.ref, record.revision_id, revision_directory)
            if stored.status is MaterialStatus.APPROVED:
                raise ValueError("approved material revisions are immutable")

        record_text = material_record_json(record)
        point_texts = {
            self._points_name(series.series_id): points_csv(series) for series in record.series
        }
        revision_directory.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(
            tempfile.mkdtemp(
                prefix=f".{revision_directory.name}.staging-",
                dir=revision_directory.parent,
            )
        )
        backup = revision_directory.parent / (
            f".{revision_directory.name}.backup-{uuid.uuid4().hex}"
        )
        try:
            (staging / "sources").mkdir()
            (staging / "record.json").write_text(
                record_text, encoding="utf-8", newline=""
            )
            for filename, text in point_texts.items():
                (staging / filename).write_text(text, encoding="utf-8", newline="")
            for provenance in record.sources:
                (staging / "sources" / self._source_name(provenance.filename)).write_bytes(
                    sources[provenance.filename]
                )

            staged = self._load_record(record.ref, record.revision_id, staging)
            canonical_record = material_record_from_json(material_record_to_json(record))
            if staged != canonical_record:
                raise ValueError("staged material record does not match the requested record")
            self._read_sources(staged, staging)
            self._verify_points(staged, staging)

            if revision_directory.exists():
                revision_directory.replace(backup)
            try:
                staging.replace(revision_directory)
            except BaseException:
                if backup.exists():
                    backup.replace(revision_directory)
                raise
            if backup.exists():
                try:
                    shutil.rmtree(backup)
                except BaseException:
                    revision_directory.replace(staging)
                    backup.replace(revision_directory)
                    shutil.rmtree(staging, ignore_errors=True)
                    raise
        finally:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)

    def source_bytes(self, ref: MaterialRef, revision_id: str) -> Mapping[str, bytes]:
        _, sources = self._load_verified(ref, revision_id)
        return sources
