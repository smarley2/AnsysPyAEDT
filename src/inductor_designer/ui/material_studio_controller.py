from __future__ import annotations

import base64
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

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
    MaterialDraftSession,
    approve_material_session,
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
from inductor_designer.materials.identity import MaterialRef
from inductor_designer.materials.records import (
    MaterialRecord,
    MaterialStatus,
    PointSeries,
    SeriesKind,
)
from inductor_designer.materials.validation import MaterialIssue, validate_record
from inductor_designer.ui.material_source import render_material_source


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
        self._dirty = False
        self._status_message = ""
        self._refresh_materials()

    def _get_materials(self) -> list[dict[str, object]]:
        return list(self._materials)

    materials = Property(list, _get_materials, notify=libraryChanged)

    def _get_revisions(self) -> list[dict[str, object]]:
        return list(self._revisions)

    revisions = Property(list, _get_revisions, notify=libraryChanged)

    def _get_selected_revision(self) -> dict[str, object]:
        return dict(self._selected_revision)

    selectedRevision = Property(dict, _get_selected_revision, notify=selectionChanged)

    def _get_series(self) -> list[dict[str, object]]:
        return list(self._series)

    series = Property(list, _get_series, notify=selectionChanged)

    def _get_points(self) -> list[dict[str, object]]:
        return list(self._points)

    points = Property(list, _get_points, notify=selectionChanged)

    def _get_issues(self) -> list[dict[str, object]]:
        return list(self._issues)

    issues = Property(list, _get_issues, notify=selectionChanged)

    def _get_fit(self) -> dict[str, object]:
        return dict(self._fit)

    fit = Property(dict, _get_fit, notify=selectionChanged)

    def _get_source(self) -> dict[str, object]:
        return dict(self._source)

    source = Property(dict, _get_source, notify=sourceChanged)

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
        }

    @staticmethod
    def _issue_dict(issue: MaterialIssue) -> dict[str, object]:
        return {
            "code": issue.code,
            "severity": issue.severity.value,
            "message": issue.message,
        }

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
        self._set_dirty(False)
        self.selectionChanged.emit()
        self.sourceChanged.emit()

    def _set_session(
        self,
        session: MaterialDraftSession,
        *,
        dirty: bool,
        saved: bool,
    ) -> None:
        record = session.record
        issues = validate_record(record)
        selected_revision = self._record_dict(record)
        series = [self._series_dict(item) for item in record.series]
        points = [
            {
                "seriesId": item.series_id,
                "index": index,
                "x": point.x,
                "y": point.y,
            }
            for item in record.series
            for index, point in enumerate(item.points)
        ]
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
        materials = [
            self._material_dict(ref) for ref in self._repository.list_materials()
        ]
        revisions = [
            self._summary_dict(summary)
            for summary in list_material_revision_summaries(self._repository, record.ref)
        ]

        self._session = session
        self._saved = saved
        self._selected_ref = record.ref
        self._selected_revision = selected_revision
        self._series = series
        self._points = points
        self._issues = issue_values
        self._fit = fit_value
        self._materials = materials
        self._revisions = revisions
        self._set_dirty(dirty)
        self.libraryChanged.emit()
        self.selectionChanged.emit()

    def _run_action(self, action: Callable[[], None]) -> None:
        try:
            action()
        except (
            MaterialImportError,
            MaterialLookupError,
            MaterialSelectionError,
            OSError,
            ValueError,
        ) as error:
            self._set_status(str(error))

    @staticmethod
    def _local_path(url: str) -> Path:
        parsed = QUrl(url)
        if parsed.scheme().casefold() != "file" or not parsed.isLocalFile():
            raise ValueError("A local file URL is required.")
        local_file = parsed.toLocalFile()
        if not local_file:
            raise ValueError("A local file URL is required.")
        return Path(local_file)

    @Slot(str, str, str)
    def selectMaterial(self, manufacturer: str, name: str, grade: str) -> None:
        def action() -> None:
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

        self._run_action(action)

    @Slot(str)
    def selectRevision(self, revision_id: str) -> None:
        def action() -> None:
            if self._selected_ref is None:
                raise ValueError("Select a material before selecting a revision.")
            record = self._repository.get(self._selected_ref, revision_id)
            source_files = tuple(
                self._repository.source_bytes(self._selected_ref, revision_id).items()
            )
            self._set_session(
                MaterialDraftSession(record, source_files, None),
                dirty=False,
                saved=True,
            )
            self._set_status("")

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
            self._set_session(session, dirty=True, saved=False)
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
            self._source = source
            self.sourceChanged.emit()
            self._set_status(f"Loaded {path.name}.")

        self._run_action(action)

    @Slot()
    def saveDraft(self) -> None:
        def action() -> None:
            if self._session is None:
                raise ValueError("No material draft is selected.")
            saved = save_material_session(self._repository, self._session)
            self._set_session(saved, dirty=False, saved=True)
            self._set_status("Material draft saved.")

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
            self._set_session(reviewed, dirty=False, saved=True)
            self._set_status("Material draft reviewed.")

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
            self._set_session(approved, dirty=False, saved=True)
            self._set_status("Material revision approved.")

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
            selected_id = bh_series_id if bh_series_id.strip() else None
            if selected_id is None:
                bh_series = tuple(
                    item
                    for item in self._session.record.series
                    if item.kind is SeriesKind.BH_CURVE
                )
                if len(bh_series) == 1:
                    selected_id = bh_series[0].series_id
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
