from __future__ import annotations

import logging
import math
import os
import tempfile
from collections.abc import Callable
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot

from inductor_designer.adapters.materials import (
    export_material_record_xlsx,
    import_material_file_as_draft,
    import_material_file_as_imported,
    material_import_template,
)
from inductor_designer.application.ports.material_repository import (
    MaterialLookupError,
    MaterialRepository,
)
from inductor_designer.application.services.material_drafts import (
    MaterialDraftSession,
    add_table_series,
    approve_material_session,
    derive_workbook_draft,
    remove_series,
    replace_table_series,
    review_material_session,
    save_material_session,
    session_from_import,
)
from inductor_designer.application.services.material_import import (
    GENERATED_SERIES_SOURCE_DESCRIPTION,
    MaterialImportError,
)
from inductor_designer.application.services.material_library import (
    MaterialRevisionSummary,
    list_material_revision_summaries,
)
from inductor_designer.application.services.material_selection import (
    MaterialSelectionError,
    pin_material_revision,
)
from inductor_designer.domain.project import InductorProject
from inductor_designer.domain.units import from_canonical
from inductor_designer.materials.identity import MaterialRef
from inductor_designer.materials.records import (
    CurveConditions,
    CurvePoint,
    MaterialRecord,
    MaterialStatus,
    PointSeries,
    SeriesKind,
)
from inductor_designer.materials.validation import MaterialIssue, validate_record

_LOGGER = logging.getLogger(__name__)
_KNOWN_ACTION_ERRORS = (
    MaterialImportError,
    MaterialLookupError,
    MaterialSelectionError,
    OSError,
    ValueError,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MaterialStudioController(QObject):
    """Synchronous QML adapter for Material Studio application services."""

    libraryChanged = Signal()
    selectionChanged = Signal()
    editorReset = Signal()
    dirtyChanged = Signal()
    statusMessageChanged = Signal()

    def __init__(
        self,
        repository: MaterialRepository,
        project: InductorProject | None = None,
        project_save_callback: Callable[[InductorProject], None] | None = None,
        *,
        now: Callable[[], str] = _utc_now,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._repository = repository
        self._project = project
        self._project_save_callback = project_save_callback
        self._now = now
        self._selected_ref: MaterialRef | None = None
        self._session: MaterialDraftSession | None = None
        self._saved = False
        self._materials: list[dict[str, object]] = []
        self._revisions: list[dict[str, object]] = []
        self._selected_revision: dict[str, object] = {}
        self._series: list[dict[str, object]] = []
        self._points: list[dict[str, object]] = []
        self._source_points: list[dict[str, object]] = []
        self._source_point_snapshots: dict[str, tuple[CurvePoint, ...] | None] = {}
        self._issues: list[dict[str, object]] = []
        self._fit: dict[str, object] = {}
        self._metadata_values: dict[str, Any] = {}
        self._active_series_id = ""
        self._invalid_editor_groups: set[str] = set()
        self._editor_valid = True
        self._dirty = False
        self._status_message = ""
        self._clean_state: dict[str, Any] | None = None
        self._reset_editor()
        self._refresh_materials()
        self._set_clean_state()

    def _get_materials(self) -> list[dict[str, object]]:
        return deepcopy(self._materials)

    materials = Property(list, _get_materials, notify=libraryChanged)

    def _get_revisions(self) -> list[dict[str, object]]:
        return deepcopy(self._revisions)

    revisions = Property(list, _get_revisions, notify=libraryChanged)

    def _get_selected_material(self) -> dict[str, object]:
        return (
            {} if self._selected_ref is None else self._material_dict(self._selected_ref)
        )

    selectedMaterial = Property(dict, _get_selected_material, notify=selectionChanged)

    def _get_selected_revision(self) -> dict[str, object]:
        return deepcopy(self._selected_revision)

    selectedRevision = Property(dict, _get_selected_revision, notify=selectionChanged)

    def _get_series(self) -> list[dict[str, object]]:
        return deepcopy(self._series)

    series = Property(list, _get_series, notify=selectionChanged)

    def _get_points(self) -> list[dict[str, object]]:
        return deepcopy(self._points)

    points = Property(list, _get_points, notify=selectionChanged)

    def _get_source_points(self) -> list[dict[str, object]]:
        return deepcopy(self._source_points)

    sourcePoints = Property(list, _get_source_points, notify=selectionChanged)

    def _get_source_comparison_available(self) -> bool:
        return bool(self._source_points)

    sourceComparisonAvailable = Property(
        bool,
        _get_source_comparison_available,
        notify=selectionChanged,
    )

    def _get_issues(self) -> list[dict[str, object]]:
        return deepcopy(self._issues)

    issues = Property(list, _get_issues, notify=selectionChanged)

    def _get_fit(self) -> dict[str, object]:
        return deepcopy(self._fit)

    fit = Property(dict, _get_fit, notify=selectionChanged)

    def _get_table_editing(self) -> dict[str, Any]:
        return {"metadata": deepcopy(self._metadata_values)}

    tableEditing = Property(dict, _get_table_editing, notify=selectionChanged)

    def _get_dirty(self) -> bool:
        return self._dirty

    dirty = Property(bool, _get_dirty, notify=dirtyChanged)

    def _get_status_message(self) -> str:
        return self._status_message

    statusMessage = Property(str, _get_status_message, notify=statusMessageChanged)

    def _get_can_save(self) -> bool:
        return (
            self._session is not None
            and self._session.record.status is MaterialStatus.DRAFT
            and self._dirty
            and bool(self._session.source_files)
            and self._editor_valid
        )

    canSave = Property(bool, _get_can_save, notify=selectionChanged)

    def _has_validation_errors(self) -> bool:
        return any(issue["severity"] == "error" for issue in self._issues)

    def _get_can_review(self) -> bool:
        return (
            self._session is not None
            and self._session.record.status is MaterialStatus.DRAFT
            and self._saved
            and not self._has_validation_errors()
        )

    canReview = Property(bool, _get_can_review, notify=selectionChanged)

    def _get_can_approve(self) -> bool:
        return (
            self._session is not None
            and self._session.record.status is MaterialStatus.REVIEWED
            and self._saved
            and not self._has_validation_errors()
        )

    canApprove = Property(bool, _get_can_approve, notify=selectionChanged)

    def _get_can_use_in_project(self) -> bool:
        return (
            self._session is not None
            and self._session.record.status in (MaterialStatus.IMPORTED, MaterialStatus.APPROVED)
            and self._project is not None
            and self._project_save_callback is not None
        )

    canUseInProject = Property(bool, _get_can_use_in_project, notify=selectionChanged)

    def _get_has_project(self) -> bool:
        return self._project is not None

    hasProject = Property(bool, _get_has_project, constant=True)

    @staticmethod
    def _material_dict(ref: MaterialRef) -> dict[str, object]:
        return {
            "manufacturer": ref.manufacturer,
            "name": ref.name,
            "grade": ref.grade,
        }

    @classmethod
    def _summary_dict(cls, summary: MaterialRevisionSummary) -> dict[str, object]:
        return {
            **cls._material_dict(summary.ref),
            "revisionId": summary.revision_id,
            "status": summary.status.value,
            "createdAt": summary.created_at,
            "reviewedBy": summary.reviewed_by or "",
            "approvedBy": summary.approved_by or "",
            "seriesCount": summary.series_count,
            "validationErrors": summary.validation_errors,
            "validationWarnings": summary.validation_warnings,
            "isLatestApproved": summary.is_latest_approved,
        }

    @staticmethod
    def _series_dict(series: PointSeries, source_kind: str) -> dict[str, object]:
        return {
            "seriesId": series.series_id,
            "kind": series.kind.value,
            "xUnit": series.x_unit,
            "yUnit": series.y_unit,
            "frequencyHz": series.conditions.frequency_hz,
            "temperatureC": series.conditions.temperature_c,
            "dcBiasAPerM": series.conditions.dc_bias_a_per_m,
            "pointCount": len(series.points),
            "sourceKind": source_kind,
            "sourceFilename": series.source_filename,
        }

    @staticmethod
    def _issue_dict(issue: MaterialIssue) -> dict[str, object]:
        return {
            "code": issue.code,
            "severity": issue.severity.value,
            "message": issue.message,
        }

    @staticmethod
    def _point_dicts(series: PointSeries) -> list[dict[str, object]]:
        return [
            {
                "seriesId": series.series_id,
                "index": index,
                "x": from_canonical(point.x, series.x_unit),
                "y": from_canonical(point.y, series.y_unit),
            }
            for index, point in enumerate(series.points)
        ]

    @classmethod
    def _record_dict(cls, record: MaterialRecord) -> dict[str, object]:
        return {
            **cls._material_dict(record.ref),
            "revisionId": record.revision_id,
            "status": record.status.value,
            "createdAt": record.created_at,
            "reviewedBy": record.reviewed_by or "",
            "approvedBy": record.approved_by or "",
            "seriesCount": len(record.series),
            "relativePermeability": record.relative_permeability,
            "notes": record.notes,
            "sources": [
                {
                    "kind": source.kind.value,
                    "filename": source.filename,
                    "sha256": source.sha256,
                    "url": source.url,
                    "page": source.page,
                    "capturedAt": source.captured_at,
                    "description": source.description,
                }
                for source in record.sources
            ],
        }

    def _refresh_materials(self) -> None:
        self._materials = [
            self._material_dict(ref) for ref in self._repository.list_materials()
        ]

    def _refresh_revisions(self, ref: MaterialRef) -> None:
        self._revisions = [
            self._summary_dict(summary)
            for summary in list_material_revision_summaries(self._repository, ref)
        ]

    def _reset_editor(self) -> None:
        self._metadata_values = {
            "seriesId": "bh-series",
            "kind": SeriesKind.BH_CURVE.value,
            "xUnit": "A/m",
            "yUnit": "T",
            "frequencyHz": None,
            "temperatureC": None,
            "dcBiasAPerM": None,
        }
        self._active_series_id = ""

    def _sync_editor_from_record(self, record: MaterialRecord) -> None:
        if not record.series:
            self._reset_editor()
            return
        target = next(
            (
                item
                for item in record.series
                if item.series_id == self._active_series_id
            ),
            record.series[0],
        )
        self._active_series_id = target.series_id
        self._metadata_values = {
            "seriesId": target.series_id,
            "kind": target.kind.value,
            "xUnit": target.x_unit,
            "yUnit": target.y_unit,
            "frequencyHz": target.conditions.frequency_hz,
            "temperatureC": target.conditions.temperature_c,
            "dcBiasAPerM": target.conditions.dc_bias_a_per_m,
        }
    def _state_values(self) -> dict[str, Any]:
        return {
            "selected_ref": self._selected_ref,
            "session": self._session,
            "saved": self._saved,
            "materials": deepcopy(self._materials),
            "revisions": deepcopy(self._revisions),
            "selected_revision": deepcopy(self._selected_revision),
            "series": deepcopy(self._series),
            "points": deepcopy(self._points),
            "source_points": deepcopy(self._source_points),
            "source_point_snapshots": deepcopy(self._source_point_snapshots),
            "issues": deepcopy(self._issues),
            "fit": deepcopy(self._fit),
            "metadata": deepcopy(self._metadata_values),
            "active_series_id": self._active_series_id,
            "invalid_editor_groups": set(self._invalid_editor_groups),
            "editor_valid": self._editor_valid,
        }

    def _set_clean_state(self) -> None:
        self._clean_state = self._state_values()

    def _remember_clean_state(self) -> None:
        if not self._dirty:
            self._set_clean_state()

    def _restore_clean_state(self) -> None:
        if self._clean_state is None:
            return
        values = self._clean_state
        self._selected_ref = values["selected_ref"]
        self._session = values["session"]
        self._saved = bool(values["saved"])
        self._materials = deepcopy(values["materials"])
        self._revisions = deepcopy(values["revisions"])
        self._selected_revision = deepcopy(values["selected_revision"])
        self._series = deepcopy(values["series"])
        self._points = deepcopy(values["points"])
        self._source_points = deepcopy(values["source_points"])
        self._source_point_snapshots = deepcopy(values["source_point_snapshots"])
        self._issues = deepcopy(values["issues"])
        self._fit = deepcopy(values["fit"])
        self._metadata_values = deepcopy(values["metadata"])
        self._active_series_id = str(values["active_series_id"])
        self._invalid_editor_groups = set(values["invalid_editor_groups"])
        self._editor_valid = bool(values["editor_valid"])

    def _mark_edit(self) -> None:
        self._remember_clean_state()
        self._saved = False
        self._set_dirty(True)

    def _emit_editor_change(self) -> None:
        self.selectionChanged.emit()

    def _library_values(
        self,
        ref: MaterialRef,
    ) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        materials = [
            self._material_dict(item) for item in self._repository.list_materials()
        ]
        revisions = [
            self._summary_dict(summary)
            for summary in list_material_revision_summaries(self._repository, ref)
        ]
        return materials, revisions

    def _set_status(self, message: str) -> None:
        if self._status_message == message:
            return
        self._status_message = message
        self.statusMessageChanged.emit()

    def _set_dirty(self, dirty: bool) -> None:
        if self._dirty == dirty:
            return
        self._dirty = dirty
        self.dirtyChanged.emit()

    def _clear_selection(self) -> None:
        self._session = None
        self._saved = False
        self._selected_revision = {}
        self._series = []
        self._points = []
        self._source_points = []
        self._source_point_snapshots = {}
        self._issues = []
        self._fit = {}
        self._reset_editor()
        self._invalid_editor_groups.clear()
        self._editor_valid = True
        self._set_dirty(False)
        self.selectionChanged.emit()
        self.editorReset.emit()

    def _set_session(
        self,
        session: MaterialDraftSession,
        *,
        dirty: bool,
        saved: bool,
        materials: list[dict[str, object]] | None = None,
        revisions: list[dict[str, object]] | None = None,
        pending_editor_groups: set[str] | None = None,
    ) -> None:
        record = session.record
        self._sync_editor_from_record(record)
        issues = validate_record(record)
        selected_revision = self._record_dict(record)
        source_kinds = {source.filename: source.kind.value for source in record.sources}
        series = [
            self._series_dict(item, source_kinds[item.source_filename])
            for item in record.series
        ]
        active = next(
            (
                item
                for item in record.series
                if item.series_id == self._active_series_id
            ),
            None,
        )
        points = [] if active is None else self._point_dicts(active)
        issue_values = [self._issue_dict(issue) for issue in issues]
        fit = record.steinmetz
        fit_value: dict[str, object] = (
            {}
            if fit is None
            else {
                "k": fit.k,
                "alpha": fit.alpha,
                "beta": fit.beta,
                "rmsRelativeResidual": fit.rms_relative_residual,
                "maxRelativeResidual": fit.max_relative_residual,
                "lossSeriesIds": [
                    item.series_id
                    for item in record.series
                    if item.kind is SeriesKind.LOSS_TABLE
                    and item.conditions.frequency_hz is not None
                    and item.conditions.frequency_hz > 0
                    and any(point.x > 0 and point.y > 0 for point in item.points)
                ],
            }
        )
        self._session = session
        self._saved = saved
        self._selected_ref = record.ref
        self._selected_revision = selected_revision
        self._series = series
        self._points = points
        snapshot = (
            None
            if active is None
            else self._source_point_snapshots.get(active.series_id)
        )
        self._source_points = (
            []
            if active is None or snapshot is None
            else self._point_dicts(replace(active, points=snapshot))
        )
        self._issues = issue_values
        self._fit = fit_value
        self._invalid_editor_groups = set(pending_editor_groups or ())
        self._editor_valid = not self._invalid_editor_groups
        if materials is not None:
            self._materials = materials
        if revisions is not None:
            self._revisions = revisions
        self._set_dirty(dirty)
        if materials is not None or revisions is not None:
            self.libraryChanged.emit()
        self.selectionChanged.emit()

    def _finish_persisted_session(
        self,
        session: MaterialDraftSession,
        success_message: str,
    ) -> None:
        self._set_session(
            session,
            dirty=False,
            saved=True,
        )
        self._set_clean_state()
        try:
            materials, revisions = self._library_values(session.record.ref)
        except _KNOWN_ACTION_ERRORS as error:
            _LOGGER.exception("Material Studio refresh failed after persistence")
            self._set_status(f"{success_message} Library refresh failed: {error}")
            return
        self._materials = materials
        self._revisions = revisions
        self._set_clean_state()
        self.libraryChanged.emit()
        self._set_status(success_message)

    def _run_action(self, action: Callable[[], None]) -> None:
        try:
            action()
        except _KNOWN_ACTION_ERRORS as error:
            _LOGGER.exception("Material Studio action failed")
            self._set_status(str(error))

    def _source_snapshots(
        self,
        session: MaterialDraftSession,
    ) -> dict[str, tuple[CurvePoint, ...] | None]:
        snapshots: dict[str, tuple[CurvePoint, ...] | None] = {}
        base: MaterialRecord | None = None
        if session.base_revision_id is not None:
            try:
                base = self._repository.get(
                    session.record.ref,
                    session.base_revision_id,
                )
            except MaterialLookupError:
                base = None
        provenance = {source.filename: source for source in session.record.sources}
        for series in session.record.series:
            base_series = (
                None
                if base is None
                else next(
                    (item for item in base.series if item.series_id == series.series_id),
                    None,
                )
            )
            source = provenance.get(series.source_filename)
            if base_series is not None:
                snapshots[series.series_id] = base_series.points
            elif (
                source is not None
                and source.description != GENERATED_SERIES_SOURCE_DESCRIPTION
            ):
                snapshots[series.series_id] = series.points
            else:
                snapshots[series.series_id] = None
        return snapshots

    @staticmethod
    def _atomic_write_bytes(destination: Path, data: bytes) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=destination.parent,
                prefix=f".{destination.name}.",
                suffix=".tmp",
                delete=False,
            ) as stream:
                temporary = Path(stream.name)
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, destination)
            temporary = None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def _reject_dirty_import(self) -> bool:
        if not self._dirty:
            return False
        self._set_status(
            "Save or discard unsaved material changes before importing another source."
        )
        return True

    def _reject_dirty_library_selection(self) -> bool:
        if not self._dirty:
            return False
        self._set_status(
            "Save or discard unsaved material changes before changing library "
            "selection."
        )
        return True

    def _require_editor_valid(self) -> None:
        if not self._editor_valid:
            raise ValueError("Apply or correct the visible editor input first.")

    @staticmethod
    def _local_path(url: str) -> Path:
        parsed = QUrl(url)
        if parsed.scheme().casefold() != "file" or not parsed.isLocalFile():
            raise ValueError("A local file URL is required.")
        local_file = parsed.toLocalFile()
        if not local_file:
            raise ValueError("A local file URL is required.")
        return Path(local_file)

    @Slot(str, str, str, result=bool)
    def selectMaterial(self, manufacturer: str, name: str, grade: str) -> bool:
        selected = False

        def action() -> None:
            nonlocal selected
            if self._reject_dirty_library_selection():
                return
            ref = MaterialRef(manufacturer, name, grade)
            revisions = [
                self._summary_dict(summary)
                for summary in list_material_revision_summaries(self._repository, ref)
            ]
            self._selected_ref = ref
            self._revisions = revisions
            self._clear_selection()
            self.libraryChanged.emit()
            self._set_status("")
            self._set_clean_state()
            selected = True

        self._run_action(action)
        if selected and self._revisions:
            return self.selectRevision(str(self._revisions[0]["revisionId"]))
        if selected:
            self._set_status("The selected material has no stored revisions.")
        return selected

    @Slot(str, result=bool)
    def selectRevision(self, revision_id: str) -> bool:
        selected = False

        def action() -> None:
            nonlocal selected
            if self._reject_dirty_library_selection():
                return
            if self._selected_ref is None:
                raise ValueError("Select a material before selecting a revision.")
            record = self._repository.get(self._selected_ref, revision_id)
            source_files = tuple(
                self._repository.source_bytes(self._selected_ref, revision_id).items()
            )
            session = MaterialDraftSession(record, source_files, None)
            source_snapshots = self._source_snapshots(session)
            active = record.series[0] if record.series else None
            materials, revisions = self._library_values(record.ref)
            self._source_point_snapshots = source_snapshots
            self._active_series_id = "" if active is None else active.series_id
            self._set_session(
                session,
                dirty=False,
                saved=True,
                materials=materials,
                revisions=revisions,
            )
            self.editorReset.emit()
            self._set_status("")
            self._set_clean_state()
            selected = True

        self._run_action(action)
        return selected

    @Slot(str)
    def selectSeries(self, series_id: str) -> None:
        def action() -> None:
            self._require_editor_valid()
            if self._session is None:
                raise ValueError("Select a material revision before selecting a series.")
            target = next(
                (
                    item
                    for item in self._session.record.series
                    if item.series_id == series_id
                ),
                None,
            )
            if target is None:
                raise ValueError(f"Series '{series_id}' does not exist.")
            self._active_series_id = target.series_id
            self._sync_editor_from_record(self._session.record)
            self._points = self._point_dicts(target)
            snapshot = self._source_point_snapshots.get(target.series_id)
            self._source_points = (
                []
                if snapshot is None
                else self._point_dicts(replace(target, points=snapshot))
            )
            self.selectionChanged.emit()
            self._set_status("")
            if not self._dirty:
                self._set_clean_state()

        self._run_action(action)

    @Slot(str, str)
    def downloadTemplate(self, file_format: str, destination_url: str) -> None:
        if not destination_url:
            return

        def action() -> None:
            destination = self._local_path(destination_url)
            download = material_import_template(file_format)
            self._atomic_write_bytes(destination, download.data)
            self._set_status(f"Saved {download.filename}.")

        self._run_action(action)

    def _import_table(self, source_url: str, success_message: str) -> None:
        if not source_url:
            return

        def action() -> None:
            if self._reject_dirty_import():
                return
            path = self._local_path(source_url)
            data = path.read_bytes()
            imported = import_material_file_as_imported(
                path.name,
                data,
                created_at=self._now(),
            )
            session = session_from_import(imported.record, imported.source_files)
            source_snapshots: dict[str, tuple[CurvePoint, ...] | None] = {
                item.series_id: item.points for item in session.record.series
            }
            self._repository.save(session.record, dict(session.source_files))
            materials, revisions = self._library_values(session.record.ref)
            self._source_point_snapshots = source_snapshots
            self._set_session(
                session,
                dirty=False,
                saved=True,
                materials=materials,
                revisions=revisions,
            )
            self._set_clean_state()
            self.editorReset.emit()
            self._set_status(success_message)

        self._run_action(action)

    @Slot(str)
    def importTable(self, source_url: str) -> None:
        self._import_table(source_url, "Imported material revision and stored it.")

    @Slot(str)
    def replaceSelectedMaterial(self, source_url: str) -> None:
        if not source_url:
            return

        def action() -> None:
            if self._reject_dirty_import():
                return
            if self._session is None or self._selected_ref is None:
                raise ValueError("Select a material revision before replacing it.")
            path = self._local_path(source_url)
            imported = import_material_file_as_imported(
                path.name,
                path.read_bytes(),
                created_at=self._now(),
            )
            if imported.record.ref != self._selected_ref:
                raise ValueError(
                    "Replacement material identity must match the selected manufacturer, "
                    "material name, and grade."
                )
            previous = self._session.record
            replacement = session_from_import(imported.record, imported.source_files)
            self._repository.save(replacement.record, dict(replacement.source_files))
            pinned = {
                selection.revision_id
                for selection in (() if self._project is None else self._project.materials)
                if selection.ref == previous.ref
            }
            if (
                previous.status is MaterialStatus.IMPORTED
                and previous.revision_id != replacement.record.revision_id
                and previous.revision_id not in pinned
            ):
                self._repository.delete_revision(previous.ref, previous.revision_id)
            source_snapshots: dict[str, tuple[CurvePoint, ...] | None] = {
                item.series_id: item.points for item in replacement.record.series
            }
            materials, revisions = self._library_values(replacement.record.ref)
            self._source_point_snapshots = source_snapshots
            self._set_session(
                replacement,
                dirty=False,
                saved=True,
                materials=materials,
                revisions=revisions,
            )
            self._set_clean_state()
            self.editorReset.emit()
            self._set_status("Replaced selected material and stored the new revision.")

        self._run_action(action)

    @Slot()
    def deleteSelectedMaterial(self) -> None:
        def action() -> None:
            if self._reject_dirty_import():
                return
            if self._selected_ref is None:
                raise ValueError("Select a material before deleting it.")
            pinned = tuple(
                selection.revision_id
                for selection in (() if self._project is None else self._project.materials)
                if selection.ref == self._selected_ref
            )
            self._repository.delete_material(self._selected_ref, pinned)
            self._selected_ref = None
            self._revisions = []
            self._clear_selection()
            self._refresh_materials()
            self._set_clean_state()
            self.libraryChanged.emit()
            self._set_status("Deleted selected material.")

        self._run_action(action)

    @Slot(str)
    def exportSelectedWorkbook(self, destination_url: str) -> None:
        if not destination_url:
            return

        def action() -> None:
            if self._session is None:
                raise ValueError("Select a material revision before exporting.")
            destination = self._local_path(destination_url)
            download = export_material_record_xlsx(
                self._session.record,
                exported_at=self._now(),
            )
            self._atomic_write_bytes(destination, download.data)
            self._set_status(f"Saved {download.filename}.")

        self._run_action(action)

    @Slot(str)
    def importEditedWorkbook(self, source_url: str) -> None:
        if not source_url:
            return

        def action() -> None:
            if self._session is None or not self._saved or self._dirty:
                raise ValueError(
                    "Select a clean, saved material revision before reimporting its workbook."
                )
            path = self._local_path(source_url)
            data = path.read_bytes()
            imported = import_material_file_as_draft(
                path.name,
                data,
                created_at=self._now(),
            )
            if imported.base_ref is None or imported.base_revision_id is None:
                raise ValueError(
                    "Edited workbook does not identify an exported base revision."
                )
            if (
                imported.base_ref != self._session.record.ref
                or imported.base_revision_id != self._session.record.revision_id
            ):
                raise ValueError(
                    "Edited workbook does not match the selected revision."
                )
            session = derive_workbook_draft(
                self._session,
                imported.record,
                imported.source_files,
            )
            source_snapshots = self._source_snapshots(session)
            materials, revisions = self._library_values(session.record.ref)
            self._remember_clean_state()
            self._source_point_snapshots = source_snapshots
            self._set_session(
                session,
                dirty=True,
                saved=False,
                materials=materials,
                revisions=revisions,
            )
            self.editorReset.emit()
            self._set_status("Imported edited workbook as a draft.")

        self._run_action(action)

    @staticmethod
    def _optional_condition(value: float) -> float | None:
        return None if math.isnan(value) else value

    def _current_conditions(self) -> CurveConditions:
        return CurveConditions(
            self._metadata_values["frequencyHz"],
            self._metadata_values["temperatureC"],
            self._metadata_values["dcBiasAPerM"],
        )

    def _draft_for_edit(self) -> MaterialDraftSession:
        if self._session is None:
            raise ValueError("No material draft is selected.")
        if self._session.record.status is MaterialStatus.DRAFT:
            return self._session
        raise ValueError("Imported and approved material revisions are read-only.")

    def _replacement_editor_series(
        self,
        target_series_id: str,
    ) -> MaterialDraftSession | None:
        series_kind = SeriesKind(str(self._metadata_values["kind"]))
        conditions = self._current_conditions()
        if self._session is None or not target_series_id:
            self._set_status("")
            return None
        draft = self._draft_for_edit()
        target = next(
            (
                item
                for item in draft.record.series
                if item.series_id == target_series_id
            ),
            None,
        )
        if target is None:
            raise ValueError(f"Series '{target_series_id}' does not exist.")
        series_id = str(self._metadata_values["seriesId"])
        x_unit = str(self._metadata_values["xUnit"])
        y_unit = str(self._metadata_values["yUnit"])
        return replace_table_series(
            draft,
            target_series_id,
            series_id=series_id,
            kind=series_kind,
            x_unit=x_unit,
            y_unit=y_unit,
            conditions=conditions,
            points=target.points,
        )

    def _edit_editor(
        self,
        mutation: Callable[[], None],
        replacement: Callable[[], MaterialDraftSession | None],
        success_message: str,
        resolved_group: str,
    ) -> None:
        if self._session is not None and self._session.record.status is not MaterialStatus.DRAFT:
            self._set_status("Imported and approved material revisions are read-only.")
            self.selectionChanged.emit()
            return
        unresolved_groups = set(self._invalid_editor_groups)
        if unresolved_groups and resolved_group not in unresolved_groups:
            self._set_status("Apply or correct the visible editor input first.")
            self.selectionChanged.emit()
            return
        self._mark_edit()
        pending_groups = set(self._invalid_editor_groups)
        try:
            mutation()
            updated = replacement()
            remaining_groups = pending_groups - {resolved_group}
            if updated is not None:
                self._set_session(
                    updated,
                    dirty=True,
                    saved=False,
                    pending_editor_groups=remaining_groups,
                )
            else:
                self._invalid_editor_groups = remaining_groups
                self._editor_valid = not remaining_groups
                self._emit_editor_change()
            self._invalid_editor_groups = remaining_groups
            self._editor_valid = not self._invalid_editor_groups
            self._set_status(success_message)
        except _KNOWN_ACTION_ERRORS as error:
            _LOGGER.exception("Material Studio editor mutation failed")
            self._invalid_editor_groups = pending_groups or {resolved_group}
            self._editor_valid = False
            if not (pending_groups - {resolved_group}):
                self._emit_editor_change()
            self._set_status(str(error))
        self.selectionChanged.emit()

    @Slot(str, str)
    def invalidateEditorInput(self, group: str, message: str) -> None:
        self._mark_edit()
        self._invalid_editor_groups.add(group)
        self._editor_valid = False
        _LOGGER.warning("Material Studio editor input is pending or invalid: %s", message)
        self._set_status(message)
        self.selectionChanged.emit()

    @Slot(int)
    def deletePoint(self, index: int) -> None:
        def action() -> None:
            self._require_editor_valid()
            draft = self._draft_for_edit()
            current = next(
                item
                for item in draft.record.series
                if item.series_id == self._active_series_id
            )
            if index < 0 or index >= len(current.points):
                raise ValueError("Point index is out of range.")
            self._mark_edit()
            updated = replace_table_series(
                draft,
                current.series_id,
                series_id=current.series_id,
                kind=current.kind,
                x_unit=current.x_unit,
                y_unit=current.y_unit,
                conditions=current.conditions,
                points=tuple(
                    point
                    for point_index, point in enumerate(current.points)
                    if point_index != index
                ),
            )
            self._set_session(
                updated,
                dirty=True,
                saved=False,
            )
            self._set_status("Canonical point deleted.")

        self._run_action(action)

    @Slot(str, str, str, str, float, float, float)
    def setSeriesMetadata(
        self,
        series_id: str,
        kind: str,
        x_unit: str,
        y_unit: str,
        frequency_hz: float,
        temperature_c: float,
        dc_bias_a_per_m: float,
    ) -> None:
        target_series_id = self._active_series_id
        def mutation() -> None:
            self._metadata_values = {
                "seriesId": series_id,
                "kind": kind,
                "xUnit": x_unit,
                "yUnit": y_unit,
                "frequencyHz": self._optional_condition(frequency_hz),
                "temperatureC": self._optional_condition(temperature_c),
                "dcBiasAPerM": self._optional_condition(dc_bias_a_per_m),
            }

        def replacement() -> MaterialDraftSession | None:
            updated = self._replacement_editor_series(target_series_id)
            if updated is not None:
                if series_id != target_series_id:
                    self._source_point_snapshots[series_id] = (
                        self._source_point_snapshots.pop(target_series_id, None)
                    )
                self._active_series_id = series_id
            return updated

        self._edit_editor(
            mutation,
            replacement,
            "Series metadata updated.",
            "metadata",
        )

    @Slot(str, int, float, float, result=bool)
    def setCanonicalPoint(
        self,
        series_id: str,
        index: int,
        x: float,
        y: float,
    ) -> bool:
        group = f"canonical:{series_id}:{index}"
        if self._invalid_editor_groups - {group}:
            self._set_status("Apply or correct the visible editor input first.")
            return False
        if not math.isfinite(x) or not math.isfinite(y):
            self._mark_edit()
            self._invalid_editor_groups.add(group)
            self._editor_valid = False
            self._set_status("Canonical point values must be finite numbers.")
            self.selectionChanged.emit()
            return False
        succeeded = False

        def action() -> None:
            nonlocal succeeded
            draft = self._draft_for_edit()
            target = next(
                (item for item in draft.record.series if item.series_id == series_id),
                None,
            )
            if target is None:
                raise ValueError(f"Series '{series_id}' does not exist.")
            if index < 0 or index >= len(target.points):
                raise ValueError("Point index is out of range.")
            points = list(target.points)
            points[index] = CurvePoint(x, y)
            self._mark_edit()
            updated = replace_table_series(
                draft,
                series_id,
                series_id=target.series_id,
                kind=target.kind,
                x_unit=target.x_unit,
                y_unit=target.y_unit,
                conditions=target.conditions,
                points=tuple(points),
            )
            self._active_series_id = target.series_id
            self._set_session(
                updated,
                dirty=True,
                saved=False,
                pending_editor_groups=self._invalid_editor_groups - {group},
            )
            self._set_status("Canonical point updated.")
            succeeded = True

        self._run_action(action)
        if not succeeded:
            self._invalid_editor_groups.add(group)
            self._editor_valid = False
            self.selectionChanged.emit()
        return succeeded

    @Slot(str, str, str, str, float, float, float, list, result=bool)
    def addTableSeries(
        self,
        series_id: str,
        kind: str,
        x_unit: str,
        y_unit: str,
        frequency_hz: float,
        temperature_c: float,
        dc_bias_a_per_m: float,
        points: list[object],
    ) -> bool:
        succeeded = False

        def action() -> None:
            nonlocal succeeded
            self._require_editor_valid()
            draft = self._draft_for_edit()
            parsed_points: list[CurvePoint] = []
            for value in points:
                if not isinstance(value, dict):
                    raise ValueError("Each table point must contain numeric x and y values.")
                x = float(value.get("x", math.nan))
                y = float(value.get("y", math.nan))
                if not math.isfinite(x) or not math.isfinite(y):
                    raise ValueError("Each table point must contain finite x and y values.")
                parsed_points.append(CurvePoint(x, y))
            if not parsed_points:
                raise ValueError("A table series requires at least one point.")
            updated = add_table_series(
                draft,
                series_id=series_id,
                kind=SeriesKind(kind),
                x_unit=x_unit,
                y_unit=y_unit,
                conditions=CurveConditions(
                    self._optional_condition(frequency_hz),
                    self._optional_condition(temperature_c),
                    self._optional_condition(dc_bias_a_per_m),
                ),
                points=tuple(parsed_points),
                captured_at=self._now(),
            )
            self._mark_edit()
            added = updated.record.series[-1]
            self._source_point_snapshots[added.series_id] = added.points
            self._set_session(updated, dirty=True, saved=False)
            self._set_status("Table series added.")
            succeeded = True

        self._run_action(action)
        return succeeded

    @Slot(str, result=bool)
    def removeSeries(self, series_id: str) -> bool:
        succeeded = False

        def action() -> None:
            nonlocal succeeded
            self._require_editor_valid()
            draft = self._draft_for_edit()
            updated = remove_series(draft, series_id)
            self._mark_edit()
            self._source_point_snapshots.pop(series_id, None)
            self._active_series_id = updated.record.series[0].series_id
            self._set_session(updated, dirty=True, saved=False)
            self._set_status("Series removed.")
            succeeded = True

        self._run_action(action)
        return succeeded

    @Slot(result=bool)
    def discardChanges(self) -> bool:
        if not self._dirty:
            return True
        self._restore_clean_state()
        self._set_dirty(False)
        self.editorReset.emit()
        self.libraryChanged.emit()
        self.selectionChanged.emit()
        self._set_status("Unsaved changes discarded.")
        return True

    @Slot()
    def saveDraft(self) -> None:
        def action() -> None:
            if self._session is None:
                raise ValueError("No material draft is selected.")
            if not self._editor_valid:
                raise ValueError("Resolve the invalid editor input before saving.")
            saved = save_material_session(self._repository, self._session)
            self._finish_persisted_session(saved, "Material draft saved.")

        self._run_action(action)

    @Slot(str)
    def reviewDraft(self, reviewer: str) -> None:
        def action() -> None:
            if self._session is None:
                raise ValueError("No material draft is selected.")
            reviewed = review_material_session(
                self._repository,
                self._session,
                reviewer,
            )
            self._finish_persisted_session(reviewed, "Material draft reviewed.")

        self._run_action(action)

    @Slot(str)
    def approveRevision(self, approver: str) -> None:
        def action() -> None:
            if self._session is None:
                raise ValueError("No reviewed material revision is selected.")
            approved = approve_material_session(
                self._repository,
                self._session,
                approver,
            )
            self._finish_persisted_session(
                approved,
                "Material revision approved.",
            )

        self._run_action(action)

    @Slot(str)
    def useInProject(self, bh_series_id: str) -> None:
        def action() -> None:
            if self._project is None:
                raise ValueError("No project is loaded.")
            if self._project_save_callback is None:
                raise ValueError("Project persistence is unavailable.")
            if self._session is None:
                raise ValueError("Select an imported or approved material revision first.")
            selected_id = bh_series_id.strip() or None
            updated = pin_material_revision(
                self._project,
                self._session.record,
                bh_series_id=selected_id,
            )
            self._project_save_callback(updated)
            self._project = updated
            self.selectionChanged.emit()
            self._set_status("Material revision saved to the project.")

        self._run_action(action)
