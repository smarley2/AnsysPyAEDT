from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import replace
from typing import TYPE_CHECKING

from PySide6.QtCore import Property, QObject, Signal, Slot

from inductor_designer.application.services.geometry_model import (
    GeometryModelError,
    build_geometry_model,
)
from inductor_designer.domain.winding import WindingDirection
from inductor_designer.ui.preview_geometry import PreviewEntry, build_preview_entries

if TYPE_CHECKING:
    from inductor_designer.application.ports.catalog import CatalogRepository
    from inductor_designer.domain.project import InductorProject
    from inductor_designer.domain.winding import WindingDefinition


_COLORS = ("#e77b49", "#2e65e7", "#157a61", "#8a5cf6")


class GuidedStudioController(QObject):
    """Expose the editable winding slice of Guided Studio to QML.

    The controller owns only the current session copy. A save callback persists
    the immutable project and updates the generation provider after the UI has
    successfully rebuilt the real geometry preview.
    """

    windingsChanged = Signal()
    previewEntriesChanged = Signal()
    selectedWindingIdChanged = Signal()
    dirtyChanged = Signal()
    statusMessageChanged = Signal()

    def __init__(
        self,
        project: InductorProject,
        catalog: CatalogRepository,
        save_callback: Callable[[InductorProject], None] | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._project = project
        self._catalog = catalog
        self._save_callback = save_callback
        self._selected_winding_id = project.windings[0].winding_id if project.windings else ""
        self._dirty = False
        self._status_message = "Ready"
        self._windings = self._winding_rows(project.windings)
        self._preview_entries = self._build_preview(project)

    def _build_preview(self, project: InductorProject) -> list[PreviewEntry]:
        model = build_geometry_model(project, self._catalog)
        return build_preview_entries(model)

    @staticmethod
    def _winding_rows(windings: tuple[WindingDefinition, ...]) -> list[dict[str, object]]:
        return [
            {
                "windingId": winding.winding_id,
                "label": winding.label,
                "turns": winding.turns,
                "conductor": winding.conductor_name,
                "acMagnitudeA": winding.ac_magnitude_a,
                "acPhaseDeg": winding.ac_phase_deg,
                "startAngleDeg": winding.start_angle_deg,
                "sectorDeg": winding.sector_deg,
                "spacingMm": winding.min_spacing_m * 1000.0,
                "clearanceMm": winding.min_clearance_m * 1000.0,
                "direction": winding.winding_direction.value,
                "color": _COLORS[index % len(_COLORS)],
            }
            for index, winding in enumerate(windings)
        ]

    def _get_windings(self) -> list[dict[str, object]]:
        return self._windings

    windings = Property(list, _get_windings, notify=windingsChanged)

    def _get_preview_entries(self) -> list[PreviewEntry]:
        return self._preview_entries

    previewEntries = Property(list, _get_preview_entries, notify=previewEntriesChanged)

    def _get_selected_winding_id(self) -> str:
        return self._selected_winding_id

    selectedWindingId = Property(
        str,
        _get_selected_winding_id,
        notify=selectedWindingIdChanged,
    )

    def _get_dirty(self) -> bool:
        return self._dirty

    dirty = Property(bool, _get_dirty, notify=dirtyChanged)

    def _get_status_message(self) -> str:
        return self._status_message

    statusMessage = Property(str, _get_status_message, notify=statusMessageChanged)

    def _set_status(self, message: str) -> None:
        self._status_message = message
        self.statusMessageChanged.emit()

    def _set_dirty(self, value: bool) -> None:
        if value == self._dirty:
            return
        self._dirty = value
        self.dirtyChanged.emit()

    @Slot(str, result=bool)
    def selectWinding(self, winding_id: str) -> bool:
        if winding_id not in {item["windingId"] for item in self._windings}:
            return False
        if winding_id != self._selected_winding_id:
            self._selected_winding_id = winding_id
            self.selectedWindingIdChanged.emit()
        return True

    @staticmethod
    def _number(value: str, label: str) -> float:
        try:
            parsed = float(value.strip().replace(",", "."))
        except ValueError as error:
            raise ValueError(f"{label} must be a number") from error
        if not math.isfinite(parsed):
            raise ValueError(f"{label} must be finite")
        return parsed

    @classmethod
    def _updated_winding(
        cls,
        winding: WindingDefinition,
        field: str,
        value: str,
    ) -> WindingDefinition:
        if field == "turns":
            number = cls._number(value, "Turns")
            if not number.is_integer():
                raise ValueError("Turns must be an integer")
            turns = int(number)
            return replace(winding, turns=turns)
        if field == "conductor":
            return replace(winding, conductor_name=value.strip())
        if field == "acMagnitudeA":
            return replace(winding, ac_magnitude_a=cls._number(value, "AC current"))
        if field == "acPhaseDeg":
            return replace(winding, ac_phase_deg=cls._number(value, "AC phase"))
        if field == "startAngleDeg":
            return replace(winding, start_angle_deg=cls._number(value, "Start angle"))
        if field == "sectorDeg":
            return replace(winding, sector_deg=cls._number(value, "Sector"))
        if field == "spacingMm":
            return replace(
                winding,
                min_spacing_m=cls._number(value, "Spacing") / 1000.0,
            )
        if field == "direction":
            return replace(winding, winding_direction=WindingDirection(value))
        raise ValueError(f"Unsupported winding field: {field}")

    @Slot(str, str, str, result=bool)
    def setWindingField(self, winding_id: str, field: str, value: str) -> bool:
        index = next(
            (position for position, item in enumerate(self._windings)
             if item["windingId"] == winding_id),
            None,
        )
        if index is None:
            self._set_status(f"Unable to apply change: unknown winding {winding_id}")
            return False

        current = self._project.windings[index]
        try:
            updated_winding = self._updated_winding(current, field, value)
            updated_windings = list(self._project.windings)
            updated_windings[index] = updated_winding
            updated_project = replace(self._project, windings=tuple(updated_windings))
            preview_entries = self._build_preview(updated_project)
        except (GeometryModelError, ValueError) as error:
            self._set_status(f"Unable to apply change: {error}")
            return False

        self._project = updated_project
        self._windings = self._winding_rows(updated_project.windings)
        self._preview_entries = preview_entries
        self._set_dirty(True)
        self._set_status(f"Updated {winding_id}")
        self.windingsChanged.emit()
        self.previewEntriesChanged.emit()
        return True

    @Slot(result=bool)
    def saveDraft(self) -> bool:
        if self._save_callback is not None:
            try:
                self._save_callback(self._project)
            except Exception as error:  # noqa: BLE001 - QML needs a safe failure path
                self._set_status(f"Unable to save project: {error}")
                return False
        self._set_dirty(False)
        self._set_status("Saved")
        return True
