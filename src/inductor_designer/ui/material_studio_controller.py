from __future__ import annotations

import base64
import logging
import math
from collections.abc import Callable
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot

from inductor_designer.adapters.materials import (
    export_material_record_xlsx,
    material_import_template,
)
from inductor_designer.application.ports.material_repository import (
    MaterialLookupError,
    MaterialRepository,
)
from inductor_designer.application.services.material_drafts import (
    ImageSeriesInput,
    MaterialDraftSession,
    approve_material_session,
    clone_revision_as_draft,
    image_draft_session,
    replace_image_series,
    replace_table_series,
    review_material_session,
    save_material_session,
    session_from_upload,
)
from inductor_designer.application.services.material_import import MaterialImportError
from inductor_designer.application.services.material_library import (
    MaterialRevisionSummary,
    list_material_revision_summaries,
)
from inductor_designer.application.services.material_selection import (
    MaterialSelectionError,
    pin_material_revision,
)
from inductor_designer.domain.project import InductorProject
from inductor_designer.materials.calibration import (
    AxisCalibration,
    AxisScale,
    CropRegion,
    ExtractionRecord,
    PixelPoint,
)
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
from inductor_designer.ui.material_source import render_material_source

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
    sourceChanged = Signal()
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
        self._issues: list[dict[str, object]] = []
        self._fit: dict[str, object] = {}
        self._source: dict[str, object] = {}
        self._source_data: bytes | None = None
        self._source_url = ""
        self._source_page: int | None = None
        self._crop_values: dict[str, Any] = {}
        self._x_axis_values: dict[str, Any] = {}
        self._y_axis_values: dict[str, Any] = {}
        self._pixel_points: list[PixelPoint] = []
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

    def _get_selected_revision(self) -> dict[str, object]:
        return deepcopy(self._selected_revision)

    selectedRevision = Property(dict, _get_selected_revision, notify=selectionChanged)

    def _get_series(self) -> list[dict[str, object]]:
        return deepcopy(self._series)

    series = Property(list, _get_series, notify=selectionChanged)

    def _get_points(self) -> list[dict[str, object]]:
        return deepcopy(self._points)

    points = Property(list, _get_points, notify=selectionChanged)

    def _get_issues(self) -> list[dict[str, object]]:
        return deepcopy(self._issues)

    issues = Property(list, _get_issues, notify=selectionChanged)

    def _get_fit(self) -> dict[str, object]:
        return deepcopy(self._fit)

    fit = Property(dict, _get_fit, notify=selectionChanged)

    def _get_source(self) -> dict[str, object]:
        return deepcopy(self._source)

    source = Property(dict, _get_source, notify=sourceChanged)

    def _get_image_editing(self) -> dict[str, Any]:
        return {
            "crop": deepcopy(self._crop_values),
            "xAxis": deepcopy(self._x_axis_values),
            "yAxis": deepcopy(self._y_axis_values),
            "pixelPoints": [
                {"xPx": point.x_px, "yPx": point.y_px}
                for point in self._pixel_points
            ],
            "metadata": deepcopy(self._metadata_values),
        }

    imageEditing = Property(dict, _get_image_editing, notify=sourceChanged)

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
            and self._session.record.status is MaterialStatus.APPROVED
            and self._project is not None
            and self._project_save_callback is not None
        )

    canUseInProject = Property(bool, _get_can_use_in_project, notify=selectionChanged)

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
    def _series_dict(series: PointSeries) -> dict[str, object]:
        return {
            "seriesId": series.series_id,
            "kind": series.kind.value,
            "xUnit": series.x_unit,
            "yUnit": series.y_unit,
            "frequencyHz": series.conditions.frequency_hz,
            "temperatureC": series.conditions.temperature_c,
            "dcBiasAPerM": series.conditions.dc_bias_a_per_m,
            "pointCount": len(series.points),
            "imageBacked": series.extraction is not None,
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
                "x": point.x,
                "y": point.y,
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
        self._crop_values = {"left": 0, "top": 0, "width": 0, "height": 0}
        axis = {
            "scale": AxisScale.LINEAR.value,
            "pixelA": 0.0,
            "valueA": 0.0,
            "pixelB": 0.0,
            "valueB": 0.0,
        }
        self._x_axis_values = dict(axis)
        self._y_axis_values = dict(axis)
        self._pixel_points = []
        self._metadata_values = {
            "seriesId": "bh-manual",
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
        extraction = target.extraction
        if extraction is None:
            self._crop_values = {"left": 0, "top": 0, "width": 0, "height": 0}
            self._x_axis_values = {
                "scale": AxisScale.LINEAR.value,
                "pixelA": 0.0,
                "valueA": 0.0,
                "pixelB": 0.0,
                "valueB": 0.0,
            }
            self._y_axis_values = dict(self._x_axis_values)
            self._pixel_points = []
            return
        self._crop_values = {
            "left": extraction.crop.left,
            "top": extraction.crop.top,
            "width": extraction.crop.width,
            "height": extraction.crop.height,
        }
        self._x_axis_values = self._axis_dict(extraction.x_axis)
        self._y_axis_values = self._axis_dict(extraction.y_axis)
        self._pixel_points = list(extraction.pixel_points)

    @staticmethod
    def _axis_dict(axis: AxisCalibration) -> dict[str, Any]:
        return {
            "scale": axis.scale.value,
            "pixelA": axis.pixel_a,
            "valueA": axis.value_a,
            "pixelB": axis.pixel_b,
            "valueB": axis.value_b,
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
            "issues": deepcopy(self._issues),
            "fit": deepcopy(self._fit),
            "source": deepcopy(self._source),
            "source_data": self._source_data,
            "source_url": self._source_url,
            "source_page": self._source_page,
            "crop": deepcopy(self._crop_values),
            "x_axis": deepcopy(self._x_axis_values),
            "y_axis": deepcopy(self._y_axis_values),
            "pixel_points": list(self._pixel_points),
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
        self._issues = deepcopy(values["issues"])
        self._fit = deepcopy(values["fit"])
        self._source = deepcopy(values["source"])
        self._source_data = values["source_data"]
        self._source_url = str(values["source_url"])
        self._source_page = values["source_page"]
        self._crop_values = deepcopy(values["crop"])
        self._x_axis_values = deepcopy(values["x_axis"])
        self._y_axis_values = deepcopy(values["y_axis"])
        self._pixel_points = list(values["pixel_points"])
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
        self.sourceChanged.emit()

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
        self._issues = []
        self._fit = {}
        self._source = {}
        self._source_data = None
        self._source_url = ""
        self._source_page = None
        self._reset_editor()
        self._invalid_editor_groups.clear()
        self._editor_valid = True
        self._set_dirty(False)
        self.selectionChanged.emit()
        self.sourceChanged.emit()

    def _set_session(
        self,
        session: MaterialDraftSession,
        *,
        dirty: bool,
        saved: bool,
        clear_source: bool,
        materials: list[dict[str, object]] | None = None,
        revisions: list[dict[str, object]] | None = None,
        source_state: tuple[dict[str, object], bytes | None, str, int | None]
        | None = None,
        pending_editor_groups: set[str] | None = None,
        notify_source: bool = True,
    ) -> None:
        record = session.record
        self._sync_editor_from_record(record)
        issues = validate_record(record)
        selected_revision = self._record_dict(record)
        series = [self._series_dict(item) for item in record.series]
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
            }
        )
        self._session = session
        self._saved = saved
        self._selected_ref = record.ref
        self._selected_revision = selected_revision
        self._series = series
        self._points = points
        self._issues = issue_values
        self._fit = fit_value
        self._invalid_editor_groups = set(pending_editor_groups or ())
        self._editor_valid = not self._invalid_editor_groups
        if materials is not None:
            self._materials = materials
        if revisions is not None:
            self._revisions = revisions
        if source_state is not None:
            (
                self._source,
                self._source_data,
                self._source_url,
                self._source_page,
            ) = source_state
        elif clear_source:
            self._source = {}
            self._source_data = None
            self._source_url = ""
            self._source_page = None
        self._set_dirty(dirty)
        if materials is not None or revisions is not None:
            self.libraryChanged.emit()
        self.selectionChanged.emit()
        if notify_source:
            self.sourceChanged.emit()

    def _finish_persisted_session(
        self,
        session: MaterialDraftSession,
        success_message: str,
    ) -> None:
        self._set_session(
            session,
            dirty=False,
            saved=True,
            clear_source=False,
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

    @staticmethod
    def _rendered_source_state(
        session: MaterialDraftSession,
        series: PointSeries,
    ) -> tuple[dict[str, object], bytes | None, str, int | None]:
        if series.extraction is None:
            return {}, None, "", None
        provenance = next(
            source
            for source in session.record.sources
            if source.filename == series.source_filename
        )
        source_data = dict(session.source_files)[series.source_filename]
        rendered = render_material_source(
            provenance.filename,
            source_data,
            page_index=provenance.page or 0,
        )
        return (
            {
                "dataUrl": "data:image/png;base64,"
                + base64.b64encode(rendered.png_data).decode("ascii"),
                "filename": provenance.filename,
                "width": rendered.width_px,
                "height": rendered.height_px,
                "pageCount": rendered.page_count,
                "pageIndex": rendered.page_index,
                "url": provenance.url,
                "page": provenance.page,
                "capturedAt": provenance.captured_at,
                "description": provenance.description,
                "sha256": provenance.sha256,
            },
            source_data,
            provenance.url,
            provenance.page,
        )

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
            active = record.series[0] if record.series else None
            source_state = (
                ({}, None, "", None)
                if active is None
                else self._rendered_source_state(session, active)
            )
            materials, revisions = self._library_values(record.ref)
            self._active_series_id = "" if active is None else active.series_id
            self._set_session(
                session,
                dirty=False,
                saved=True,
                clear_source=False,
                materials=materials,
                revisions=revisions,
                source_state=source_state,
            )
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
            source_state = self._rendered_source_state(self._session, target)
            self._active_series_id = target.series_id
            self._sync_editor_from_record(self._session.record)
            self._points = self._point_dicts(target)
            (
                self._source,
                self._source_data,
                self._source_url,
                self._source_page,
            ) = source_state
            self.selectionChanged.emit()
            self.sourceChanged.emit()
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
            destination.write_bytes(download.data)
            self._set_status(f"Saved {download.filename}.")

        self._run_action(action)

    def _import_table(self, source_url: str, success_message: str) -> None:
        if not source_url:
            return

        def action() -> None:
            path = self._local_path(source_url)
            data = path.read_bytes()
            session = session_from_upload(path.name, data, created_at=self._now())
            materials, revisions = self._library_values(session.record.ref)
            self._remember_clean_state()
            self._set_session(
                session,
                dirty=True,
                saved=False,
                clear_source=True,
                materials=materials,
                revisions=revisions,
            )
            self._set_status(success_message)

        self._run_action(action)

    @Slot(str)
    def importTable(self, source_url: str) -> None:
        self._import_table(source_url, "Imported material table as a draft.")

    @Slot(str)
    def exportSelectedWorkbook(self, destination_url: str) -> None:
        if not destination_url:
            return

        def action() -> None:
            if self._session is None:
                raise ValueError("Select a material revision before exporting.")
            destination = self._local_path(destination_url)
            download = export_material_record_xlsx(self._session.record)
            destination.write_bytes(download.data)
            self._set_status(f"Saved {download.filename}.")

        self._run_action(action)

    @Slot(str)
    def importEditedWorkbook(self, source_url: str) -> None:
        self._import_table(source_url, "Imported edited workbook as a draft.")

    @Slot(str, int)
    def importSourceImage(self, source_url: str, page_index: int) -> None:
        if not source_url:
            return

        def action() -> None:
            path = self._local_path(source_url)
            data = path.read_bytes()
            rendered = render_material_source(path.name, data, page_index=page_index)
            source = {
                "dataUrl": "data:image/png;base64,"
                + base64.b64encode(rendered.png_data).decode("ascii"),
                "filename": path.name,
                "width": rendered.width_px,
                "height": rendered.height_px,
                "pageCount": rendered.page_count,
                "pageIndex": rendered.page_index,
            }
            self._remember_clean_state()
            self._source = source
            self._source_data = data
            self._source_url = source_url
            self._source_page = (
                rendered.page_index if path.suffix.casefold() == ".pdf" else None
            )
            self._reset_editor()
            self._crop_values = {
                "left": 0,
                "top": 0,
                "width": rendered.width_px,
                "height": rendered.height_px,
            }
            self._session = None
            self._saved = False
            self._selected_revision = {}
            self._series = []
            self._points = []
            self._issues = []
            self._fit = {}
            self._active_series_id = ""
            self._invalid_editor_groups = {"source"}
            self._editor_valid = False
            self._set_dirty(True)
            self.sourceChanged.emit()
            self.selectionChanged.emit()
            self._set_status(f"Loaded {path.name}.")

        self._run_action(action)

    @staticmethod
    def _optional_condition(value: float) -> float | None:
        return None if math.isnan(value) else value

    @staticmethod
    def _axis_from_values(values: dict[str, Any]) -> AxisCalibration:
        return AxisCalibration(
            AxisScale(str(values["scale"])),
            float(values["pixelA"]),
            float(values["valueA"]),
            float(values["pixelB"]),
            float(values["valueB"]),
        )

    def _current_extraction(self) -> ExtractionRecord:
        left = int(self._crop_values["left"])
        top = int(self._crop_values["top"])
        width = int(self._crop_values["width"])
        height = int(self._crop_values["height"])
        source_width_value = self._source.get("width", 0)
        source_height_value = self._source.get("height", 0)
        source_width = (
            int(source_width_value)
            if isinstance(source_width_value, (int, float))
            else 0
        )
        source_height = (
            int(source_height_value)
            if isinstance(source_height_value, (int, float))
            else 0
        )
        if source_width > 0 and source_height > 0 and (
            left < 0
            or top < 0
            or width <= 0
            or height <= 0
            or left + width > source_width
            or top + height > source_height
        ):
            raise ValueError("Crop must stay within loaded source bounds.")
        return ExtractionRecord(
            CropRegion(left, top, width, height),
            self._axis_from_values(self._x_axis_values),
            self._axis_from_values(self._y_axis_values),
            tuple(self._pixel_points),
        )

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
        return clone_revision_as_draft(
            self._repository,
            self._session.record.ref,
            self._session.record.revision_id,
        )

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
        if target.extraction is None:
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
        return replace_image_series(
            draft,
            target_series_id,
            series_id=series_id,
            kind=series_kind,
            x_unit=x_unit,
            y_unit=y_unit,
            conditions=conditions,
            extraction=self._current_extraction(),
        )

    def _edit_editor(
        self,
        mutation: Callable[[], None],
        replacement: Callable[[], MaterialDraftSession | None],
        success_message: str,
        resolved_group: str,
    ) -> None:
        unresolved_groups = self._invalid_editor_groups - {"source"}
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
                    clear_source=False,
                    pending_editor_groups=remaining_groups,
                    notify_source=not (remaining_groups - {"source"}),
                )
            else:
                self._invalid_editor_groups = remaining_groups
                self._editor_valid = not remaining_groups
                if not (remaining_groups - {"source"}):
                    self._emit_editor_change()
            self._invalid_editor_groups = remaining_groups
            self._editor_valid = not self._invalid_editor_groups
            self._set_status(success_message)
        except _KNOWN_ACTION_ERRORS as error:
            _LOGGER.exception("Material Studio editor mutation failed")
            self._invalid_editor_groups = pending_groups or {resolved_group}
            self._editor_valid = False
            if not (pending_groups - {resolved_group, "source"}):
                self._emit_editor_change()
            self._set_status(str(error))
        self.selectionChanged.emit()

    def _edit_extraction(
        self,
        mutation: Callable[[], None],
        resolved_group: str,
    ) -> None:
        target_series_id = self._active_series_id
        self._edit_editor(
            mutation,
            lambda: self._replacement_editor_series(target_series_id),
            "Image extraction updated.",
            resolved_group,
        )

    @Slot(str, str)
    def invalidateEditorInput(self, group: str, message: str) -> None:
        self._mark_edit()
        self._invalid_editor_groups.add(group)
        self._editor_valid = False
        _LOGGER.warning("Material Studio editor input is pending or invalid: %s", message)
        self._set_status(message)
        self.selectionChanged.emit()

    @Slot(int, int, int, int)
    def setCrop(self, left: int, top: int, width: int, height: int) -> None:
        self._edit_extraction(
            lambda: self._crop_values.update(
                left=left,
                top=top,
                width=width,
                height=height,
            ),
            "crop",
        )

    @Slot(str, float, float, float, float)
    def setXAxis(
        self,
        scale: str,
        pixel_a: float,
        value_a: float,
        pixel_b: float,
        value_b: float,
    ) -> None:
        self._edit_extraction(
            lambda: self._x_axis_values.update(
                scale=scale,
                pixelA=pixel_a,
                valueA=value_a,
                pixelB=pixel_b,
                valueB=value_b,
            ),
            "x-axis",
        )

    @Slot(str, float, float, float, float)
    def setYAxis(
        self,
        scale: str,
        pixel_a: float,
        value_a: float,
        pixel_b: float,
        value_b: float,
    ) -> None:
        self._edit_extraction(
            lambda: self._y_axis_values.update(
                scale=scale,
                pixelA=pixel_a,
                valueA=value_a,
                pixelB=pixel_b,
                valueB=value_b,
            ),
            "y-axis",
        )

    @Slot(float, float)
    def addPixelPoint(self, x_px: float, y_px: float) -> None:
        self._edit_extraction(
            lambda: self._pixel_points.append(PixelPoint(x_px, y_px)),
            "points",
        )

    @Slot(int, float, float)
    def movePixelPoint(self, index: int, x_px: float, y_px: float) -> None:
        def mutation() -> None:
            if index < 0 or index >= len(self._pixel_points):
                raise ValueError("Point index is out of range.")
            self._pixel_points[index] = PixelPoint(x_px, y_px)

        self._edit_extraction(mutation, "points")

    @Slot(int)
    def deletePoint(self, index: int) -> None:
        target = (
            None
            if self._session is None
            else next(
                (
                    item
                    for item in self._session.record.series
                    if item.series_id == self._active_series_id
                ),
                None,
            )
        )
        if target is not None and target.extraction is None:
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
                    clear_source=False,
                )
                self._set_status("Canonical point deleted.")

            self._run_action(action)
            return

        def mutation() -> None:
            if index < 0 or index >= len(self._pixel_points):
                raise ValueError("Point index is out of range.")
            del self._pixel_points[index]

        self._edit_extraction(mutation, "points")

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
                self._active_series_id = series_id
            return updated

        self._edit_editor(
            mutation,
            replacement,
            "Series metadata updated.",
            "metadata",
        )

    @Slot(str, str, str, str)
    def createImageDraft(
        self,
        manufacturer: str,
        name: str,
        grade: str,
        source_description: str,
    ) -> None:
        def action() -> None:
            if self._invalid_editor_groups - {"source"}:
                raise ValueError("Apply or correct the visible editor input first.")
            if self._source_data is None or not self._source:
                raise ValueError("Load an image or PDF page before creating a draft.")
            stamp = self._now()
            session = image_draft_session(
                ImageSeriesInput(
                    ref=MaterialRef(manufacturer, name, grade),
                    source_filename=str(self._source["filename"]),
                    source_data=self._source_data,
                    source_url=self._source_url,
                    source_page=self._source_page,
                    captured_at=stamp,
                    source_description=source_description,
                    series_id=str(self._metadata_values["seriesId"]),
                    kind=SeriesKind(str(self._metadata_values["kind"])),
                    x_unit=str(self._metadata_values["xUnit"]),
                    y_unit=str(self._metadata_values["yUnit"]),
                    conditions=self._current_conditions(),
                    extraction=self._current_extraction(),
                    created_at=stamp,
                )
            )
            materials, revisions = self._library_values(session.record.ref)
            self._active_series_id = session.record.series[0].series_id
            self._set_session(
                session,
                dirty=True,
                saved=False,
                clear_source=False,
                materials=materials,
                revisions=revisions,
            )
            self._set_status("Image material draft created.")

        self._run_action(action)

    @Slot(str, int, float, float)
    def setCanonicalPoint(
        self,
        series_id: str,
        index: int,
        x: float,
        y: float,
    ) -> None:
        def action() -> None:
            self._require_editor_valid()
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
            was_image = target.extraction is not None
            self._active_series_id = target.series_id
            self._set_session(updated, dirty=True, saved=False, clear_source=False)
            if was_image:
                self._set_status(
                    "Numeric editing converted the image-backed series to a direct "
                    "table edit; the original image/PDF remains as supplemental "
                    "provenance."
                )
            else:
                self._set_status("Canonical point updated.")

        self._run_action(action)

    @Slot(result=bool)
    def discardChanges(self) -> bool:
        if not self._dirty:
            return True
        self._restore_clean_state()
        self._set_dirty(False)
        self.libraryChanged.emit()
        self.selectionChanged.emit()
        self.sourceChanged.emit()
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
                raise ValueError("Select an approved material revision first.")
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
