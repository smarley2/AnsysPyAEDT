"""The read-only Preliminary screen (specification sections 4.3 and 5).

The controller asks for one immutable `PreliminaryResult` and converts it to
rows. It never computes a quantity, never invents a reason, and never starts a
solver.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Property, QObject, Signal, Slot

from inductor_designer.application.services.geometry_model import (
    GeometryModelError,
    build_geometry_model,
)
from inductor_designer.application.services.preliminary_inputs import (
    build_preliminary_request,
)
from inductor_designer.simulation.preliminary import estimate_preliminary
from inductor_designer.ui.preliminary_rows import core_rows, total_rows, winding_rows

if TYPE_CHECKING:
    from inductor_designer.application.ports.catalog import CatalogRepository
    from inductor_designer.ui.project_session import ProjectSession


class PreliminaryController(QObject):
    resultChanged = Signal()

    def __init__(
        self,
        session: ProjectSession,
        catalog: CatalogRepository,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._session = session
        self._catalog = catalog
        self._core_rows: list[dict[str, object]] = []
        self._winding_rows: list[dict[str, object]] = []
        self._total_rows: list[dict[str, object]] = []
        self._assumptions: list[str] = []
        self._geometry_issues: list[str] = []
        self._material_revision_id = ""
        self._bh_series_id = ""
        self.refresh()

    def _get_core_rows(self) -> list[dict[str, object]]:
        return self._core_rows

    coreRows = Property(list, _get_core_rows, notify=resultChanged)

    def _get_winding_rows(self) -> list[dict[str, object]]:
        return self._winding_rows

    windingRows = Property(list, _get_winding_rows, notify=resultChanged)

    def _get_total_rows(self) -> list[dict[str, object]]:
        return self._total_rows

    totalRows = Property(list, _get_total_rows, notify=resultChanged)

    def _get_assumptions(self) -> list[str]:
        return self._assumptions

    assumptions = Property(list, _get_assumptions, notify=resultChanged)

    def _get_geometry_issues(self) -> list[str]:
        return self._geometry_issues

    geometryIssues = Property(list, _get_geometry_issues, notify=resultChanged)

    def _get_material_revision_id(self) -> str:
        return self._material_revision_id

    materialRevisionId = Property(str, _get_material_revision_id, notify=resultChanged)

    def _get_bh_series_id(self) -> str:
        return self._bh_series_id

    bhSeriesId = Property(str, _get_bh_series_id, notify=resultChanged)

    @Slot()
    def refresh(self) -> None:
        """Re-estimate after any valid project edit (specification section 2)."""
        project = self._session.project
        try:
            geometry = build_geometry_model(project, self._catalog)
            issues: list[str] = []
        except GeometryModelError as error:
            # Only packing-derived quantities lose their input; the estimator
            # reports exactly those as unavailable, so nothing else is disturbed.
            geometry = None
            issues = list(error.issues)
        try:
            result = estimate_preliminary(
                build_preliminary_request(project, self._catalog, geometry)
            )
        except Exception as error:  # noqa: BLE001 - the screen must never crash
            # An estimator invariant violation is a defect to report, not a
            # crash: numbers the user typed can still overflow the model.
            self._geometry_issues = [*issues, f"Preliminary estimate failed: {error}"]
            self.resultChanged.emit()
            return
        self._core_rows = core_rows(result)
        self._winding_rows = winding_rows(result)
        self._total_rows = total_rows(result)
        self._assumptions = list(result.notes)
        self._geometry_issues = issues
        self._material_revision_id = result.material_revision_id or ""
        self._bh_series_id = result.bh_series_id or ""
        self.resultChanged.emit()
