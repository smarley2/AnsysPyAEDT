from __future__ import annotations

import contextlib
import math
from dataclasses import replace
from typing import TYPE_CHECKING

from PySide6.QtCore import Property, QObject, Signal, Slot

from inductor_designer.application.services.geometry_model import (
    GeometryModelError,
    build_geometry_model,
)
from inductor_designer.domain.project import WindingOperatingPoint
from inductor_designer.domain.winding import (
    ConductorMode,
    CurrentDirection,
    WindingDirection,
)
from inductor_designer.ui.preview_geometry import PreviewEntry, build_preview_entries

if TYPE_CHECKING:
    from inductor_designer.application.ports.catalog import CatalogRepository
    from inductor_designer.domain.project import InductorProject
    from inductor_designer.domain.winding import WindingDefinition
    from inductor_designer.ui.project_session import ProjectSession


_COLORS = ("#e77b49", "#2e65e7", "#157a61", "#8a5cf6")


class GuidedStudioController(QObject):
    """Expose the editable winding slice of Guided Studio to QML.

    The controller reads and writes through the shared `ProjectSession`, which
    is the single owner of the project across every Guided Studio screen.
    """

    windingsChanged = Signal()
    previewEntriesChanged = Signal()
    selectedWindingIdChanged = Signal()
    dirtyChanged = Signal()
    statusMessageChanged = Signal()
    operatingPointChanged = Signal()

    _MINIMUM_NEW_SECTOR_DEG = 10.0
    _PREFERRED_NEW_SECTOR_DEG = 90.0

    def __init__(
        self,
        session: ProjectSession,
        catalog: CatalogRepository,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._session = session
        self._catalog = catalog
        session.dirtyChanged.connect(self.dirtyChanged)
        session.statusMessageChanged.connect(self.statusMessageChanged)
        project = session.project
        self._selected_winding_id = (
            project.design.windings[0].winding_id if project.design.windings else ""
        )
        self._windings = self._winding_rows(
            project.design.windings, project.operating_point.windings
        )
        self._preview_entries = self._build_preview(project)
        # Set around every `self._session.apply(...)` call below: `apply`
        # emits `projectChanged` synchronously, which `main.py` wires back to
        # `refresh()` on this same controller. Without the guard, one accepted
        # edit rebuilds the geometry model and re-emits `windingsChanged` /
        # `previewEntriesChanged` a second time for no reason -- the slot
        # already applied the very state `refresh()` would recompute.
        self._applying = False

    def _build_preview(self, project: InductorProject) -> list[PreviewEntry]:
        model = build_geometry_model(project, self._catalog)
        return build_preview_entries(model)

    def _next_winding_id(self) -> str:
        taken = {winding.winding_id for winding in self._session.project.design.windings}
        index = len(taken) + 1
        while f"w{index}" in taken:
            index += 1
        return f"w{index}"

    def _free_sector(self) -> tuple[float, float] | None:
        """The first gap after the last occupied sector, in degrees.

        Sectors must not overlap (`domain/validation.py`), so a new winding is
        placed after the existing ones rather than on top of them. Returns None
        when the remaining gap is too small to be useful.
        """
        windings = self._session.project.design.windings
        occupied_end = max(
            (winding.start_angle_deg + winding.sector_deg for winding in windings),
            default=0.0,
        )
        if occupied_end >= 360.0 - self._MINIMUM_NEW_SECTOR_DEG:
            return None
        return (occupied_end, min(self._PREFERRED_NEW_SECTOR_DEG, 360.0 - occupied_end))

    @staticmethod
    def _winding_rows(
        windings: tuple[WindingDefinition, ...],
        operating_points: tuple[WindingOperatingPoint, ...],
    ) -> list[dict[str, object]]:
        points_by_id = {item.winding_id: item for item in operating_points}
        return [
            {
                "windingId": winding.winding_id,
                "label": winding.label,
                "turns": winding.turns,
                "conductor": winding.conductor_name,
                "acRmsCurrentA": points_by_id[winding.winding_id].ac_rms_current_a,
                "acPhaseDeg": points_by_id[winding.winding_id].ac_phase_deg,
                "startAngleDeg": winding.start_angle_deg,
                "sectorDeg": winding.sector_deg,
                "spacingMm": winding.min_spacing_m * 1000.0,
                "clearanceMm": winding.min_clearance_m * 1000.0,
                "direction": winding.winding_direction.value,
                "mode": winding.mode.value,
                "terminalIntent": winding.terminal_intent,
                "dcCurrentA": points_by_id[winding.winding_id].dc_current_a,
                "currentDirection": points_by_id[
                    winding.winding_id
                ].current_direction.value,
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
        # PySide6's stubs type `Property` as the descriptor class itself (no
        # `__get__` overload), so mypy sees this attribute access as `Property`
        # rather than `bool`; Qt resolves it to the real value at runtime.
        return bool(self._session.dirty)

    dirty = Property(bool, _get_dirty, notify=dirtyChanged)

    def _get_status_message(self) -> str:
        return str(self._session.statusMessage)

    statusMessage = Property(str, _get_status_message, notify=statusMessageChanged)

    def _get_operating_point(self) -> dict[str, object]:
        operating_point = self._session.project.operating_point
        return {
            "frequencyHz": operating_point.frequency_hz,
            "windingTemperatureC": operating_point.winding_temperature_c,
            "coreTemperatureC": operating_point.core_temperature_c,
        }

    operatingPoint = Property(dict, _get_operating_point, notify=operatingPointChanged)

    def _get_conductor_names(self) -> list[str]:
        return list(self._catalog.list_conductor_names())

    conductorNames = Property(list, _get_conductor_names, constant=True)

    def _get_conductor_modes(self) -> list[str]:
        return [item.value for item in ConductorMode]

    conductorModes = Property(list, _get_conductor_modes, constant=True)

    def _get_winding_directions(self) -> list[str]:
        return [item.value for item in WindingDirection]

    windingDirections = Property(list, _get_winding_directions, constant=True)

    def _get_current_directions(self) -> list[str]:
        return [item.value for item in CurrentDirection]

    currentDirections = Property(list, _get_current_directions, constant=True)

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
        if field == "label":
            return replace(winding, label=value.strip())
        if field == "mode":
            return replace(winding, mode=ConductorMode(value))
        if field == "clearanceMm":
            return replace(
                winding, min_clearance_m=cls._number(value, "Clearance") / 1000.0
            )
        if field == "terminalIntent":
            return replace(winding, terminal_intent=value.strip())
        raise ValueError(f"Unsupported winding field: {field}")

    @classmethod
    def _updated_operating_point(
        cls,
        operating_point: WindingOperatingPoint,
        field: str,
        value: str,
    ) -> WindingOperatingPoint:
        if field == "acRmsCurrentA":
            return replace(
                operating_point,
                ac_rms_current_a=cls._number(value, "AC RMS current"),
            )
        if field == "acPhaseDeg":
            return replace(
                operating_point,
                ac_phase_deg=cls._number(value, "AC phase"),
            )
        if field == "dcCurrentA":
            return replace(
                operating_point, dc_current_a=cls._number(value, "DC current")
            )
        if field == "currentDirection":
            return replace(operating_point, current_direction=CurrentDirection(value))
        raise ValueError(f"Unsupported operating-point field: {field}")

    @Slot(str, str, result=bool)
    def setOperatingPointField(self, field: str, value: str) -> bool:
        """One shared frequency and two shared temperatures (specification 4.2).

        Explicit branches rather than a name-to-attribute mapping: a dynamic
        `replace(operating_point, **{attribute: number})` does not type-check
        under strict mypy, and `_updated_winding` and `_updated_operating_point`
        already dispatch this way.
        """
        project = self._session.project
        operating_point = project.operating_point
        try:
            if field == "frequencyHz":
                label = "Frequency"
                updated_point = replace(
                    operating_point, frequency_hz=self._number(value, label)
                )
            elif field == "windingTemperatureC":
                label = "Winding temperature"
                updated_point = replace(
                    operating_point,
                    winding_temperature_c=self._number(value, label),
                )
            elif field == "coreTemperatureC":
                label = "Core temperature"
                updated_point = replace(
                    operating_point, core_temperature_c=self._number(value, label)
                )
            else:
                self._session.set_status(
                    f"Unable to apply change: unsupported operating-point field: {field}"
                )
                return False
            updated_project = replace(project, operating_point=updated_point)
            preview_entries = self._build_preview(updated_project)
        except (GeometryModelError, ValueError) as error:
            self._session.set_status(f"Unable to apply change: {error}")
            return False
        self._preview_entries = preview_entries
        self._applying = True
        try:
            self._session.apply(updated_project)
        finally:
            self._applying = False
        self._session.set_status(f"Updated {label.casefold()}")
        self.operatingPointChanged.emit()
        self.previewEntriesChanged.emit()
        return True

    @Slot(str, str, str, result=bool)
    def setWindingField(self, winding_id: str, field: str, value: str) -> bool:
        project = self._session.project
        index = next(
            (position for position, item in enumerate(self._windings)
             if item["windingId"] == winding_id),
            None,
        )
        if index is None:
            self._session.set_status(f"Unable to apply change: unknown winding {winding_id}")
            return False

        try:
            if field in {"acRmsCurrentA", "acPhaseDeg", "dcCurrentA", "currentDirection"}:
                operating_points = list(project.operating_point.windings)
                operating_index = next(
                    position
                    for position, item in enumerate(operating_points)
                    if item.winding_id == winding_id
                )
                operating_points[operating_index] = self._updated_operating_point(
                    operating_points[operating_index],
                    field,
                    value,
                )
                updated_project = replace(
                    project,
                    operating_point=replace(
                        project.operating_point,
                        windings=tuple(operating_points),
                    ),
                )
            else:
                updated_windings = list(project.design.windings)
                updated_windings[index] = self._updated_winding(
                    updated_windings[index],
                    field,
                    value,
                )
                updated_project = replace(
                    project,
                    design=replace(
                        project.design,
                        windings=tuple(updated_windings),
                    ),
                )
            preview_entries = self._build_preview(updated_project)
        except (GeometryModelError, StopIteration, ValueError) as error:
            self._session.set_status(f"Unable to apply change: {error}")
            return False

        self._applying = True
        try:
            self._session.apply(updated_project)
        finally:
            self._applying = False
        self._windings = self._winding_rows(
            updated_project.design.windings,
            updated_project.operating_point.windings,
        )
        self._preview_entries = preview_entries
        self._session.set_status(f"Updated {winding_id}")
        self.windingsChanged.emit()
        self.previewEntriesChanged.emit()
        return True

    @Slot(result=bool)
    def addWinding(self) -> bool:
        project = self._session.project
        windings = project.design.windings
        if not windings:
            self._session.set_status(
                "Unable to add a winding: the project has no winding to copy "
                "placement defaults from."
            )
            return False
        placement = self._free_sector()
        if placement is None:
            self._session.set_status(
                "Unable to add a winding: no free sector remains on the core. "
                "Reduce an existing winding's sector first."
            )
            return False
        start_deg, sector_deg = placement
        template = windings[-1]
        winding_id = self._next_winding_id()
        definition = replace(
            template,
            winding_id=winding_id,
            label=f"Winding {len(windings) + 1}",
            turns=1,
            start_angle_deg=start_deg,
            sector_deg=sector_deg,
            terminal_intent="",
        )
        excitation = WindingOperatingPoint(
            winding_id=winding_id,
            ac_rms_current_a=0.0,
            ac_phase_deg=0.0,
            dc_current_a=0.0,
            current_direction=CurrentDirection.FORWARD,
        )
        updated_project = replace(
            project,
            design=replace(project.design, windings=(*windings, definition)),
            operating_point=replace(
                project.operating_point,
                windings=(*project.operating_point.windings, excitation),
            ),
        )
        try:
            preview_entries = self._build_preview(updated_project)
        except GeometryModelError as error:
            self._session.set_status(f"Unable to add a winding: {error}")
            return False
        self._preview_entries = preview_entries
        self._applying = True
        try:
            self._session.apply(updated_project)
        finally:
            self._applying = False
        self._session.set_status(f"Added {winding_id}")
        self._windings = self._winding_rows(
            updated_project.design.windings, updated_project.operating_point.windings
        )
        self._selected_winding_id = winding_id
        self.windingsChanged.emit()
        self.previewEntriesChanged.emit()
        self.selectedWindingIdChanged.emit()
        return True

    @Slot(str, result=bool)
    def removeWinding(self, winding_id: str) -> bool:
        project = self._session.project
        windings = project.design.windings
        if winding_id not in {winding.winding_id for winding in windings}:
            self._session.set_status(
                f"Unable to remove: unknown winding {winding_id}"
            )
            return False
        if len(windings) == 1:
            self._session.set_status(
                "Unable to remove the last winding: a design needs at least one."
            )
            return False
        updated_project = replace(
            project,
            design=replace(
                project.design,
                windings=tuple(
                    winding for winding in windings if winding.winding_id != winding_id
                ),
            ),
            operating_point=replace(
                project.operating_point,
                windings=tuple(
                    item
                    for item in project.operating_point.windings
                    if item.winding_id != winding_id
                ),
            ),
        )
        try:
            preview_entries = self._build_preview(updated_project)
        except GeometryModelError as error:
            self._session.set_status(f"Unable to remove {winding_id}: {error}")
            return False
        self._preview_entries = preview_entries
        self._applying = True
        try:
            self._session.apply(updated_project)
        finally:
            self._applying = False
        self._session.set_status(f"Removed {winding_id}")
        self._windings = self._winding_rows(
            updated_project.design.windings, updated_project.operating_point.windings
        )
        self._selected_winding_id = updated_project.design.windings[0].winding_id
        self.windingsChanged.emit()
        self.previewEntriesChanged.emit()
        self.selectedWindingIdChanged.emit()
        return True

    @Slot(result=bool)
    def saveDraft(self) -> bool:
        return self._session.saveProject()

    @Slot()
    def refresh(self) -> None:
        if self._applying:
            # `projectChanged` was emitted by our own `session.apply(...)`
            # above: the slot that called it already has the up-to-date rows
            # and preview and is about to emit both signals itself. A refresh
            # from a *different* writer (e.g. the Core & Material screen
            # calling `session.apply` directly) still reaches here with
            # `_applying` False and refreshes normally.
            return
        project = self._session.project
        # Keep the last valid preview: a core edit that breaks geometry is
        # reported by its own controller, and a blank canvas would hide the
        # windings the user is about to fix.
        with contextlib.suppress(GeometryModelError):
            self._preview_entries = self._build_preview(project)
        self._windings = self._winding_rows(
            project.design.windings, project.operating_point.windings
        )
        self.windingsChanged.emit()
        self.previewEntriesChanged.emit()
        self.operatingPointChanged.emit()
